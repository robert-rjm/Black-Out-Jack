"""
app/routes/lobby.py
====================
Room lifecycle routes: creating a room, joining, and initial game setup.

POST /create_room — Reserve a new room code
POST /join_room   — Client joins an existing room
POST /setup       — Admin configures and starts the game session
"""

from flask import Blueprint, jsonify, request

from engine.blackjack import Player, Hand, Shoe, NPC_Player
from engine.referee import RefereeSession

from app.models.game_room import GameRoom
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
# Delete room (cancel before game starts)
# ---------------------------------------------------------------------------

@bp.route("/delete_room", methods=["POST"])
def delete_room():
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    if room_code not in game_sessions:
        return jsonify({"ok": True})  # already gone, that's fine

    session = game_sessions[room_code]

    # Slot is None before /setup is called — safe to delete immediately
    if session is None:
        del game_sessions[room_code]
        return jsonify({"ok": True})

    # Only allow deletion if the game hasn't started yet
    if session.round_count > 0:
        return jsonify({"ok": False, "error": "Game already in progress."})

    # Verify requester is the admin
    info = session._room_clients.get(client_id, {})
    if info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Only the room creator can delete it."})

    del game_sessions[room_code]
    return jsonify({"ok": True})


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
        if existing._room_clients.get(client_id, {}).get("role") != "admin":
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

    raw_session = RefereeSession(players, dealer_name, wager, num_hands)
    room = GameRoom(
        session             = raw_session,
        mode                = mode,
        drinking_mode       = drinking,
        rounds_this_dealer  = 1,
        switch_this_round   = None,
        _dealer_rotate_every = len(players),
        bust_vote_enabled   = bool(data.get("bust_vote_enabled", False)),
    )
    if client_id:
        # All non-NPC seats start as local — a seat moves to remote only when
        # another device registers and claims it (handle_registration removes it).
        local_names = [p.name for p in players if p.name not in npc_names]
        # Admin is always seated at Player1 (first non-NPC seat) regardless of
        # who the dealer is. god_mode keeps them in game control either way.
        # This ensures that when they transfer admin, they retain a player seat
        # automatically without any extra steps.
        admin_seat = local_names[0] if local_names else dealer_name
        room._room_clients[client_id] = {
            "name": admin_seat, "local_names": local_names,
            "role": "admin", "kicked": False,
        }
    set_session(room_code, room)

    if mode == "digital":
        default_decks    = 2 if len(players) >= 4 else 1
        num_decks        = int(data.get("num_decks", default_decks))
        raw_session.shoe = Shoe(num_decks)
        raw_session.shoe.shuffle(quiet=True)

    if not drinking:
        raw_session.tracker = NullTracker()

    output = capture(raw_session.start_round)
    if drinking:
        patch_tracker(raw_session)  # must run AFTER start_round creates a fresh tracker
    if output.strip():
        room._log_entries.append(output)
    state  = serialize_state(room, client_id)
    state["output"] = output   # kept for host's immediate display
    return jsonify(state)
