"""
app/routes/lobby.py
====================
Room lifecycle routes: creating a room, joining, and initial game setup.

POST /create_room — Reserve a new room code
POST /join_room   — Client joins an existing room
POST /setup       — Admin configures and starts the game session
"""

from flask import Blueprint, jsonify, request

from blackjack import Player, Hand, Shoe, NPC_Player

from app.services.session_store import (
    game_sessions,
    reserve_room, set_session, find_room_code,
    is_join_rate_limited,
)
from app.services.validators  import sanitize_name
from app.services.serializer  import serialize_state
from app.services.room_manager import NullTracker, patch_tracker, capture

bp = Blueprint("lobby", __name__)


# ---------------------------------------------------------------------------
# Create room
# ---------------------------------------------------------------------------

@bp.route("/create_room", methods=["POST"])
def create_room():
    code = reserve_room()
    return jsonify({"ok": True, "code": code})


# ---------------------------------------------------------------------------
# Join room
# ---------------------------------------------------------------------------

@bp.route("/join_room", methods=["POST"])
def join_room():
    data      = request.json or {}
    raw       = (data.get("code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    # Generic error — same message whether code is malformed or absent,
    # so the response cannot be used as a room-existence oracle.
    _bad = {"ok": False, "error": "Invalid room code. Check the code and try again."}

    # Rate-limit failed join attempts per source IP to slow enumeration.
    ip   = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if is_join_rate_limited(ip):
        return jsonify({"ok": False, "error": "Too many attempts. Please wait a moment."}), 429

    # Case-insensitive lookup (codes are stored as "Ace427" etc.)
    code = find_room_code(raw)
    if code is None:
        return jsonify(_bad)

    session  = game_sessions[code]
    has_game = session is not None
    state    = serialize_state(session, client_id)
    state["ok"]        = True
    state["has_game"]  = has_game
    state["room_code"] = code   # return canonical casing
    return jsonify(state)


# ---------------------------------------------------------------------------
# Setup (game configuration)
# ---------------------------------------------------------------------------

@bp.route("/setup", methods=["POST"])
def setup():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"ok": False, "output": "Invalid request body."})

    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    if room_code not in game_sessions:
        return jsonify({"ok": False, "output": "Room not found."})

    # Prevent any client from overwriting an active game.
    # The admin (session creator) may reconfigure; everyone else is blocked.
    existing = game_sessions[room_code]
    if existing is not None:
        clients = getattr(existing, "_room_clients", {})
        if clients.get(client_id, {}).get("role") != "admin":
            return jsonify({"ok": False, "output": "Game already in progress."})

    raw_players = data.get("players")
    if not isinstance(raw_players, list):
        return jsonify({"ok": False, "output": "Invalid players list."})
    names = [sanitize_name(n) for n in raw_players if isinstance(n, str) and n.strip()]
    names = [n for n in names if n]   # drop any that became empty after sanitization
    if not names:
        return jsonify({"ok": False, "output": "No player names provided."})

    try:
        mode       = data.get("mode", "referee")   # "referee" | "digital"
        dealer_idx = int(data.get("dealer_index", 0))
        wager      = max(1, int(data.get("wager", 1)))
        num_hands  = max(1, int(data.get("num_hands", 2)))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "output": "Invalid numeric field."})
    dealer_name = names[min(dealer_idx, len(names) - 1)]

    npc_names = {sanitize_name(n) for n in data.get("npcs", []) if n.strip()}

    players = []
    for name in names:
        p           = NPC_Player(name) if name in npc_names else Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    drinking = bool(data.get("drinking", True))

    from referee import RefereeSession
    game_session                         = RefereeSession(players, dealer_name, wager, num_hands)
    set_session(room_code, game_session)
    game_session.mode                    = mode
    game_session.drinking_mode           = drinking
    game_session.rounds_this_dealer      = 1   # rounds the current dealer has held the role
    game_session.switch_this_round       = None  # None | "hard" | "soft"
    game_session._dealer_rotate_every    = len(players)   # rotate after N rounds (one full cycle)
    # Shared log — broadcast to all players via /state polling
    game_session._log_entries            = []
    game_session._log_version            = 0
    game_session._deferred_hole_card_msgs = []
    # CSV accumulator — survives across rounds; never reset between newrounds
    game_session._drink_csv_rows         = []
    # Live sip ticker — cumulative across all rounds
    game_session._sip_ticker             = {}
    game_session._drink_log_harvested    = False
    game_session._last_round_sips        = {}   # per-player sips in the last completed round
    game_session._last_round_drinks      = []   # detailed drink entries for the Drinks pane
    game_session._prev_round_sips        = {}   # sips from the round before last (for comparison)
    game_session._prev_round_drinks      = []   # drinks from the round before last
    game_session._dealer_role_ticker     = {}   # cumulative sips earned while acting as dealer
    # Identity — session creator is admin, auto-registered with the dealer's name
    game_session._room_clients  = {}
    game_session._preselections = {}
    game_session._suggestions   = {}   # pending dealer→player action suggestions
    game_session._kick_votes    = {}   # {target_name_lower: set(voter_name_lower)}
    game_session._rejoin_requests = []  # [{client_id, display_name}] — kicked players asking to rejoin
    game_session._anim_default  = True # admin's animation preference, broadcast to joiners
    game_session._queued_settings = {}  # settings queued to apply at start of next round
    game_session._hand_stats            = {}   # {player: {wins, losses, pushes, ...}}
    game_session._dealer_hand_stats     = {}   # {dealer_name: {wins, losses, pushes, hands}}
    game_session._milestones_claimed    = {}   # boundary → winner name; never reset
    game_session._pending_milestone     = None # current unclaimed handout (or None)
    game_session._last_milestone_result = None # most recent claim result, shown ~15s
    if client_id:
        game_session._room_clients[client_id] = {
            "name": dealer_name, "role": "admin", "kicked": False,
        }

    if mode == "digital":
        num_decks         = int(data.get("num_decks", 1))
        game_session.shoe = Shoe(num_decks)
        game_session.shoe.shuffle()

    if drinking:
        patch_tracker(game_session)
    else:
        game_session.tracker = NullTracker()

    output = capture(game_session.start_round)
    if output.strip():
        game_session._log_entries.append(output)
    state  = serialize_state(game_session, client_id)
    state["output"] = output   # kept for host's immediate display
    return jsonify(state)
