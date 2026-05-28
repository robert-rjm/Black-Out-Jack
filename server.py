"""
app.py
======
Flask web server supporting two modes:

  referee — physical deck; you type cards as they are dealt; app tracks drinks.
  digital — virtual shoe; app deals cards automatically; full playable blackjack.

Run:
    python app.py

Then open http://<your-PC-IP>:5000 on any phone on the same WiFi.
"""

import csv
import io
import contextlib
import os
import socket
import time
from collections import defaultdict
from datetime import datetime

from flask import Flask, request, jsonify, render_template, Response, send_from_directory

from referee import RefereeSession
from blackjack import Player, Hand, Shoe, HandEvaluator, NPC_Player
from drinking_rules import DrinkingRules
from app.config import (
    MILESTONE_STEP, MILESTONE_HANDOUT_SIPS, MILESTONE_TTL,
)
from app.services.session_store import (
    game_sessions,
    reserve_room, get_session, set_session, find_room_code,
    is_join_rate_limited,
)
from app.services.validators import sanitize_name, get_client_info, is_dealer_client
from app.services.serializer import (
    serialize_state, serialize_card,
    round_phase, current_turn, hand_done, play_order,
)
from app.services.game_engine import (
    deal_card, deal_pending_split_cards,
    get_player_hand, initial_deal, dealer_turn, auto_play_npc_turns,
)

app = Flask(__name__)




# ---------------------------------------------------------------------------
# Null tracker — used in non-drinking mode so all tracker.apply() calls
# become silent no-ops without touching referee.py or drinking_rules.py.
# ---------------------------------------------------------------------------

class _NullTracker:
    """Drop-in replacement for DrinkTracker when drinking mode is off."""
    def apply(self, msgs):                    pass
    def apply_ace_clubs_credit(self, player): pass
    def print_round_summary(self):            pass
    def _handle_handout(self, *a, **kw):      pass


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------

def _patch_tracker(session: RefereeSession):
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web version never blocks waiting for terminal input.
    """
    tracker = session.tracker

    def web_handout(giver: str, total: int, reason: str):
        print(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        print(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21, auto)", "player")
            print(f"    -> {t.name} +1 sip")

    tracker._handle_handout = web_handout


def _capture(fn, *args):
    """Call fn(*args) and return everything it printed as a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _classify_rule(reason: str):
    """
    Normalise a raw drink-reason string to a short canonical rule name.
    Returns None for bookkeeping entries that should not appear in the CSV.
    Mirrors classify_rule() in simulation.py.
    """
    r = reason
    if "A♣" in r and "credit" in r:          return None
    if "protects" in r:                        return None
    if "exempt" in r:                          return None
    if "Hard Dealer Switch" in r:             return "Hard Dealer Switch"
    if "net loss" in r:                       return "Net hand losses"
    if "lost a doubled hand" in r:            return "Lost doubled hand"
    if "lost a suited hand" in r:             return "Lost suited hand"
    if "immunity exception" in r:             return "Doubled win (immunity break)"
    if "won suited hand" in r:                return "Suited winning hand"
    if "split hand" in r:                     return "Split win (immunity break)"
    if "swept all hands" in r:               return "Other-player sweep"
    if "Blackjack by" in r:                   return "Blackjack bonus"
    if "4 Aces" in r and "first deal" in r:  return "Four Aces (first deal)"
    if "4 Aces" in r and "end of round" in r: return "Four Aces (end of round)"
    if "Dealer hand is all" in r:             return "Dealer suited hand"
    if "handed" in r and "5-card 21" in r:   return "5-card 21 handout received"
    if "won with" in r and "cards" in r:      return "5+ card win"
    if "A♠" in r and "to dealer" in r:       return "Ace dealt: Ace of Spades (dealer hand)"
    if "A♥" in r and "dealer" in r:          return "Ace dealt: Ace of Hearts (dealer hand)"
    if "A♦" in r and "dealer" in r:          return "Ace dealt: Ace of Diamonds (dealer hand)"
    if "A♠" in r:                            return "Ace dealt: Ace of Spades (player hand)"
    if "A♥" in r:                            return "Ace dealt: Ace of Hearts (player hand)"
    if "A♦" in r:                            return "Ace dealt: Ace of Diamonds (player hand)"
    return "Other"


def _harvest_drink_log(session: RefereeSession):
    """
    Copy the current round's drink_log entries from every player into the
    session-wide CSV accumulator.  Call this right after cmd_endround() and
    before start_round() resets drink_log to [].
    """
    rows = getattr(session, "_drink_csv_rows", [])
    round_num = session.round_count
    dealer    = session.dealer_name
    for p in session.all_players:
        for entry in p.drink_log:
            sips   = entry[0]
            reason = entry[1]
            role   = entry[2] if len(entry) > 2 else "player"
            if sips <= 0:
                continue
            rule = _classify_rule(reason)
            if rule is None:
                continue
            rows.append({
                "round":  round_num,
                "dealer": dealer,
                "player": p.name,
                "role":   role,
                "rule":   rule,
                "sips":   sips,
            })
    session._drink_csv_rows = rows
    # Update live sip ticker (raw totals, unfiltered)
    ticker = getattr(session, "_sip_ticker", {})
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            if sips > 0:
                ticker[p.name] = ticker.get(p.name, 0) + sips
    session._sip_ticker          = ticker
    session._drink_log_harvested = True

    # Track cumulative dealer-role sips separately (shown in dealer panel)
    d_ticker = getattr(session, "_dealer_role_ticker", {})
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            role = entry[2] if len(entry) > 2 else "player"
            if sips > 0 and role == "dealer":
                d_ticker[p.name] = d_ticker.get(p.name, 0) + sips
    session._dealer_role_ticker = d_ticker

    # Shift previous snapshot before overwriting (enables round-over comparison)
    session._prev_round_sips   = getattr(session, "_last_round_sips",   {})
    session._prev_round_drinks = getattr(session, "_last_round_drinks", [])

    # Snapshot this round's per-player sip totals for the "Last Round" panel
    last = {}
    for p in session.all_players:
        total = sum(e[0] for e in p.drink_log if e and e[0] > 0)
        if total > 0:
            last[p.name] = total
    session._last_round_sips = last

    # Detailed per-entry drink list with reasons for the Drinks pane
    drinks_detail = []
    for p in session.all_players:
        for entry in p.drink_log:
            if entry and len(entry) >= 2 and entry[0] > 0:
                sips   = entry[0]
                reason = entry[1]
                if _classify_rule(reason) is None:   # skip bookkeeping entries
                    continue
                drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})
    session._last_round_drinks = drinks_detail

    # Track hand outcomes (win/loss/push, split and double breakdowns) per player
    hand_stats = getattr(session, "_hand_stats", {})
    for p in session.all_players:
        if p.is_dealer:
            continue
        if p.name not in hand_stats:
            hand_stats[p.name] = {
                "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
                "split_hands": 0, "split_wins": 0,
                "double_hands": 0, "double_wins": 0,
            }
        hs = hand_stats[p.name]
        for hand in p.hands:
            result = getattr(hand, "result", None)
            if result not in ("win", "loss", "push"):
                continue
            hs["hands"] += 1
            if result == "win":    hs["wins"]   += 1
            elif result == "loss": hs["losses"] += 1
            elif result == "push": hs["pushes"] += 1
            if getattr(hand, "from_split", False):
                hs["split_hands"] += 1
                if result == "win": hs["split_wins"] += 1
            if getattr(hand, "doubled", False):
                hs["double_hands"] += 1
                if result == "win": hs["double_wins"] += 1
    session._hand_stats = hand_stats

    # Track how each player fared as dealer — wins/losses/pushes from dealer's POV
    # (Player hand "win" = dealer lost that hand, and vice versa)
    dealer_stats = getattr(session, "_dealer_hand_stats", {})
    dname = session.dealer_name
    if dname not in dealer_stats:
        dealer_stats[dname] = {"hands": 0, "wins": 0, "losses": 0, "pushes": 0}
    ds = dealer_stats[dname]
    for p in session.all_players:
        if p.is_dealer:
            continue
        for hand in p.hands:
            result = getattr(hand, "result", None)
            if result not in ("win", "loss", "push"):
                continue
            ds["hands"] += 1
            if result == "win":    ds["losses"] += 1  # player wins = dealer lost
            elif result == "loss": ds["wins"]   += 1  # player loses = dealer won
            elif result == "push": ds["pushes"] += 1
    session._dealer_hand_stats = dealer_stats


def _check_and_set_milestone(session: RefereeSession):
    """
    After harvesting a round's drink log, check whether any player has newly
    crossed a MILESTONE_STEP boundary.  If so, record the winner in
    session._pending_milestone so the frontend can display the handout UI.

    Tiebreak: if two players hit the same boundary this round, the one with
    fewest sips THIS round wins (prevents gaming the last round).  Alphabetical
    name order breaks any remaining tie.

    A boundary is only triggered once (tracked in session._milestones_claimed).
    """
    ticker  = getattr(session, "_sip_ticker", {})
    last    = getattr(session, "_last_round_sips", {})
    claimed = getattr(session, "_milestones_claimed", {})

    # Build (boundary → list of candidates) for thresholds newly crossed
    newly_hit: dict[int, list[tuple[int, str]]] = {}  # boundary → [(round_sips, name)]
    for name, total in ticker.items():
        # Find the highest unclaimed boundary this player has crossed
        highest = (total // MILESTONE_STEP) * MILESTONE_STEP
        if highest <= 0:
            continue
        # Walk backwards to find the lowest newly-crossed boundary for this player
        prev_total = total - last.get(name, 0)
        prev_boundary = (prev_total // MILESTONE_STEP) * MILESTONE_STEP
        for boundary in range(prev_boundary + MILESTONE_STEP, highest + 1, MILESTONE_STEP):
            if claimed.get(boundary):
                continue  # someone else already owns this boundary
            if boundary not in newly_hit:
                newly_hit[boundary] = []
            newly_hit[boundary].append((last.get(name, 0), name))

    if not newly_hit:
        return

    # Only the lowest unclaimed boundary fires (one milestone at a time per round)
    boundary = min(newly_hit.keys())
    candidates = newly_hit[boundary]

    # Tiebreak: fewest sips this round wins; alphabetical on tie
    candidates.sort(key=lambda t: (t[0], t[1].lower()))
    _round_sips, winner = candidates[0]

    claimed[boundary] = winner
    session._milestones_claimed = claimed
    session._pending_milestone  = {
        "boundary":   boundary,
        "winner":     winner,
        "handout":    MILESTONE_HANDOUT_SIPS,
        "expires_at": time.monotonic() + MILESTONE_TTL,
    }




def _apply_queued_settings(session: RefereeSession) -> list[str]:
    """Apply any queued settings to the session before a new round starts.
    Returns a list of human-readable change descriptions."""
    queued = getattr(session, "_queued_settings", {})
    if not queued:
        return []

    changes = []

    if "wager" in queued:
        session.wager = queued["wager"]
        changes.append(f"Sips/hand set to {queued['wager']}")

    if "num_hands" in queued:
        session.num_hands = queued["num_hands"]
        changes.append(f"Hands/player set to {queued['num_hands']}")

    if "num_decks" in queued and getattr(session, "mode", "referee") == "digital":
        from blackjack import Shoe
        session.shoe = Shoe(queued["num_decks"])
        session.shoe.shuffle()
        changes.append(f"Deck count set to {queued['num_decks']}")

    for entry in queued.get("add_players", []):
        name   = entry["name"]
        is_npc = entry["is_npc"]
        if not any(p.name == name for p in session.all_players):
            p = NPC_Player(name) if is_npc else Player(name)
            p.is_dealer = False
            session.all_players.append(p)
            changes.append(f"Added {'bot' if is_npc else 'player'} {name}")

    for name in queued.get("remove_players", []):
        before = len(session.all_players)
        session.all_players = [p for p in session.all_players if p.name != name or p.is_dealer]
        if len(session.all_players) < before:
            changes.append(f"Removed player {name}")

    session._queued_settings = {}
    return changes


def _newround_rotate(session: RefereeSession):
    """Rotate the dealer role one seat clockwise."""
    all_names  = [p.name for p in session.all_players]
    cur_idx    = all_names.index(session.dealer_name)
    new_dealer = all_names[(cur_idx + 1) % len(all_names)]
    for p in session.all_players:
        p.is_dealer   = (p.name == new_dealer)
        p.dealer_hand = Hand() if p.is_dealer else None
    session.dealer_name = new_dealer
    print(f"  Dealer rotates => {new_dealer} is now dealer.")






# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def no_cache(response):
    """Prevent Safari from caching JSON polling responses."""
    if response.content_type and "json" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


_ROOT = os.path.dirname(os.path.abspath(__file__))

@app.route("/logo.png")
def serve_logo():
    return send_from_directory(os.path.join(_ROOT, "static"), "Logo-BlackOutJack.png")

@app.route("/manifest.json")
def serve_manifest():
    return jsonify({
        "name":             "Black-Out Jack",
        "short_name":       "Black-Out Jack",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#0f1117",
        "theme_color":      "#0f1117",
        "icons": [
            {"src": "/logo.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


# ---------------------------------------------------------------------------
# Lobby routes
# ---------------------------------------------------------------------------

@app.route("/create_room", methods=["POST"])
def create_room():
    code = reserve_room()
    return jsonify({"ok": True, "code": code})


@app.route("/join_room", methods=["POST"])
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


@app.route("/setup", methods=["POST"])
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
        _patch_tracker(game_session)
    else:
        game_session.tracker = _NullTracker()

    output = _capture(game_session.start_round)
    if output.strip():
        game_session._log_entries.append(output)
    state  = serialize_state(game_session, client_id)
    state["output"] = output   # kept for host's immediate display
    return jsonify(state)


@app.route("/command", methods=["POST"])
def command():
    _req         = request.json or {}
    room_code    = _req.get("room_code", "")
    game_session = game_sessions.get(room_code)
    if not game_session:
        return jsonify({"ok": False, "output": "No active session — set up a game first."})

    cmd_str = _req.get("cmd", "").strip()
    client_id = _req.get("client_id", "")
    if not cmd_str:
        return jsonify({"ok": False, "output": "Empty command."})

    parts = cmd_str.split()
    cmd   = parts[0].lower()
    mode  = getattr(game_session, "mode", "referee")

    # Turn-order gate: in digital mode, per-player actions must come from the
    # player whose turn it currently is. (deal/dealer/endround/newround/status/help
    # are session-wide and bypass the gate.)
    TURN_GATED = {"hit", "stand", "double", "split", "insurance", "blackjack"}
    if mode == "digital" and cmd in TURN_GATED and len(parts) >= 2:
        current = current_turn(game_session)
        target  = parts[1].strip().capitalize()
        if current is None:
            return jsonify({
                **serialize_state(game_session),
                "output": "  Not in play phase — deal cards or run dealer turn.\n",
            })
        if target.lower() != current.lower():
            return jsonify({
                **serialize_state(game_session),
                "output": f"  Out of order — it's {current}'s turn (not {target}).\n",
            })

    # Gate the dealer-reveal command too: only allow when all players are done
    if mode == "digital" and cmd == "dealer":
        phase = round_phase(game_session)
        if phase == "pre-deal":
            return jsonify({
                **serialize_state(game_session),
                "output": "  Deal cards first.\n",
            })
        if phase == "playing":
            current = current_turn(game_session) or "a player"
            return jsonify({
                **serialize_state(game_session),
                "output": f"  Cannot reveal dealer — {current} still has hands to play.\n",
            })

    # Dealer-gate: only dealer or admin may execute game-changing commands
    DEALER_GATED_CMDS = {
        "deal", "hit", "stand", "double", "split", "insurance", "blackjack",
        "dealer", "endround", "newround", "peek", "action", "result", "fouraces",
    }
    if (cmd in DEALER_GATED_CMDS
            and getattr(game_session, "_room_clients", None)
            and not is_dealer_client(game_session, client_id)):
        state = serialize_state(game_session, client_id)
        state["output"] = "  Not authorised — only the dealer can do that.\n"
        return jsonify(state)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):

        # ── Digital-only commands ────────────────────────────────────────────
        if mode == "digital":

            if cmd == "deal":
                # Initial deal — no card args; shoe deals automatically
                game_session._last_peeked = None   # peeked card is now stale
                game_session._preselections = {}
                game_session._suggestions   = {}
                initial_deal(game_session)
                auto_play_npc_turns(game_session)

            elif cmd == "hit":
                # hit <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: hit <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            card = deal_card(game_session, hand, player.name)
                            print(f"  {player.name} {hand_label} hits {card}: {hand}")
                            if hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                print("  BUST!")
                            elif hand.score() == 21:
                                hand.stood = True
                                print(f"  {player.name} {hand_label}: auto-stands at 21.")

            elif cmd == "stand":
                # stand <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: stand <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label  = parts[2] if len(parts) > 2 else "hand1"
                        hand        = get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            hand.stood  = True
                            print(f"  {player.name} {hand_label}: stands at {hand.score()}.")

            elif cmd == "double":
                # double <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: double <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if len(hand.cards) != 2:
                            print("  Can only double on first two cards.")
                        elif hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            hand.doubled = True
                            deal_card(game_session, hand, player.name)
                            hand.stood   = True
                            print(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
                            if hand.is_bust():
                                hand.bust = True
                                hand.result = "loss"

            elif cmd == "split":
                # split <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: split <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if not hand.can_split():
                            # Give a specific message when the split limit is the reason
                            if (len(hand.cards) == 2
                                    and hand.cards[0].rank.blackjack_value == hand.cards[1].rank.blackjack_value
                                    and hand.split_count >= Hand.MAX_SPLITS):
                                print(f"  Max splits reached ({Hand.MAX_SPLITS} splits per hand).")
                            else:
                                print("  Cannot split this hand.")
                        else:
                            # Move second card to new hand (no second cards dealt yet)
                            new_hand = Hand(from_split=True)
                            new_hand.cards.append(hand.cards.pop())
                            hand.from_split   = True
                            hand.split_count += 1
                            new_hand.split_count = hand.split_count  # child inherits so chain limit holds
                            idx       = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
                            new_label = f"hand{idx + 2}"
                            player.hands.insert(idx + 1, new_hand)
                            # Deal second card to H1; check for instant 21/bust
                            deal_card(game_session, hand, player.name)
                            if hand.score() == 21:
                                hand.stood = True
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  (21 — auto-stands)")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            elif hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  BUST!")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            else:
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  ← play this hand first")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")

            elif cmd == "insurance":
                # insurance <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: insurance <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if not hand.is_blackjack():
                            print("  Insurance only applies when the player has a Blackjack (dealer shows Ace).")
                        else:
                            hand.insured = True
                            # Sync with the vote system: force all voters' votes to True so
                            # dealer_turn resolves this hand as insured via voted_keys.
                            hand_idx   = player.hands.index(hand)
                            vote_entry = next(
                                (v for v in getattr(game_session, "_insurance_votes", [])
                                 if v["player"] == player.name and v["hand_idx"] == hand_idx
                                 and not v.get("resolved")),
                                None,
                            )
                            if vote_entry:
                                voters = [x for x in game_session.all_players if x.name != player.name]
                                for x in voters:
                                    vote_entry["votes"][x.name] = True
                            print(f"  {player.name} {hand_label}: insured.")

            elif cmd == "blackjack":
                # blackjack <player> [hand<n>] — confirm natural BJ, fire drink rules
                if len(parts) < 2:
                    print("  Usage: blackjack <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        hand.stood = True
                        all_names  = [p.name for p in game_session.all_players]
                        game_session.tracker.apply(
                            DrinkingRules.on_blackjack(player.name, hand, all_names))
                        print(f"  {player.name} BLACKJACK confirmed.")

            elif cmd == "peek":
                # Toggle: hide peeked card if already shown, otherwise reveal it
                shoe = getattr(game_session, "shoe", None)
                if getattr(game_session, "_last_peeked", None):
                    # Already showing — toggle off
                    game_session._last_peeked = None
                    print("  Next card hidden.")
                elif shoe and shoe.cards:
                    card = shoe.cards[-1]   # pop() takes from the end
                    print(f"  Next card in shoe: {card}")
                    print(f"  ({len(shoe.cards)} cards remaining)")
                    game_session._last_peeked = serialize_card(card)
                else:
                    print("  Shoe is empty or not available.")
                    game_session._last_peeked = None

            elif cmd == "dealer":
                # Auto-run dealer turn + evaluate all hands + assign drinks
                dealer_turn(game_session)
                game_session.cmd_endround()
                _harvest_drink_log(game_session)
                _check_and_set_milestone(game_session)

            elif cmd == "endround":
                game_session.cmd_endround()
                _harvest_drink_log(game_session)
                _check_and_set_milestone(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = _apply_queued_settings(game_session)
                for msg in setting_changes:
                    print(f"  ⚙️  {msg}")
                if rotate:
                    _newround_rotate(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = getattr(game_session, "rounds_this_dealer", 0) + 1
                game_session.switch_this_round = None
                # Clear shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = getattr(game_session, "_log_version", 0) + 1
                game_session._deferred_hole_card_msgs = []
                game_session._last_peeked = None
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._drink_log_harvested = False
                game_session._kick_votes    = {}  # reset vote-kick tally each round
                game_session._pending_milestone = None  # clear between rounds
                if getattr(game_session, "drinking_mode", True) or game_session.shoe.needs_reshuffle():
                    game_session.shoe.reset()
                    print("  Shoe reshuffled.")
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                _print_digital_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

            # Clear the pre-selection for the player whose action just executed
            if cmd in {"hit", "stand", "double", "split"} and len(parts) >= 2:
                _p  = parts[1].strip().capitalize()
                _h  = (parts[2] if len(parts) > 2 else "hand1").strip().lower()
                if hasattr(game_session, "_preselections"):
                    game_session._preselections.pop(f"{_p.lower()}:{_h}", None)

            # After any player action: deal pending second cards to split hands
            # whose predecessor just finished, then check if dealer should auto-play
            if cmd in {"hit", "stand", "double", "split"}:
                deal_pending_split_cards(game_session)
                auto_play_npc_turns(game_session)
                if round_phase(game_session) == "dealer-ready":
                    print("\n  (All players done — dealer plays automatically)")
                    dealer_turn(game_session)
                    game_session.cmd_endround()
                    _harvest_drink_log(game_session)
                    _check_and_set_milestone(game_session)

        # ── Referee mode (original behaviour, unchanged) ─────────────────────
        else:

            if cmd == "deal":
                game_session.cmd_deal(parts)

            elif cmd == "action":
                game_session.cmd_action(parts)

            elif cmd == "result":
                game_session.cmd_result(parts)

            elif cmd == "dealer":
                game_session.cmd_dealer(parts)

            elif cmd == "fouraces":
                game_session.cmd_fouraces(parts)

            elif cmd == "endround":
                game_session.cmd_endround()
                _harvest_drink_log(game_session)
                _check_and_set_milestone(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = _apply_queued_settings(game_session)
                for msg in setting_changes:
                    print(f"  ⚙️  {msg}")
                if rotate:
                    _newround_rotate(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = getattr(game_session, "rounds_this_dealer", 0) + 1
                game_session.switch_this_round = None
                # Clear the shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = getattr(game_session, "_log_version", 0) + 1
                game_session._last_peeked = None
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._drink_log_harvested = False
                game_session._kick_votes    = {}  # reset vote-kick tally each round
                game_session._pending_milestone = None  # clear between rounds
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                RefereeSession.print_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    output = buf.getvalue()
    # Append to the shared log so polling clients see this output too.
    # newround already cleared _log_entries above; appending here adds the
    # new-round start text to the fresh log.
    if output.strip():
        game_session._log_entries.append(output)
    state = serialize_state(game_session, client_id)
    state["output"] = output   # kept for immediate display on the sender's side
    # peeked_card is included in serialize_state and persists until cleared
    # by newround/deal so all polling clients can see it.
    return jsonify(state)


@app.route("/register", methods=["POST"])
def register():
    """A joining client claims a seat or becomes spectator.
    Body: { room_code, client_id, name }  — name="" means spectator."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    name      = sanitize_name((data.get("name") or "").strip())

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    if not hasattr(session, "_room_clients"):
        session._room_clients = {}

    existing = session._room_clients.get(client_id, {})
    if existing.get("kicked"):
        if not name:
            # Kicked player wants to spectate — allow it, clear kicked flag
            session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
            # Remove any pending rejoin request for this client
            session._rejoin_requests = [r for r in getattr(session, "_rejoin_requests", [])
                                        if r["client_id"] != client_id]
            return jsonify({**serialize_state(session, client_id), "ok": True})
        return jsonify({"ok": False, "error": "You have been removed from this session."})

    if not name:
        session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
        return jsonify({**serialize_state(session, client_id), "ok": True})

    valid_names = [p.name for p in session.all_players]
    if name not in valid_names:
        return jsonify({"ok": False,
                        "error": f"'{name}' is not a seat. Available: {', '.join(valid_names)}"})

    for cid, info in session._room_clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == name.lower()):
            return jsonify({"ok": False, "error": f"'{name}' is already taken."})

    role = "admin" if existing.get("role") == "admin" else "player"
    session._room_clients[client_id] = {"name": name, "role": role, "kicked": False}
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/kick", methods=["POST"])
def kick():
    """Admin removes a client. Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    admin_name_lc = (admin_info.get("name") or "").lower()
    if target_name.lower() == admin_name_lc:
        return jsonify({"ok": False, "error": "Cannot kick yourself."})

    for cid, info in clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == target_name.lower()):
            info["kicked"] = True
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})


@app.route("/undo_kick", methods=["POST"])
def undo_kick():
    """Admin reinstates a previously kicked client as a spectator.
    Body: { room_code, client_id, target_client_id }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    target_info = clients.get(target_client_id)
    if not target_info:
        return jsonify({"ok": False, "error": "Client not found."})
    if not target_info.get("kicked"):
        return jsonify({"ok": False, "error": "Player is not kicked."})

    # Reinstate as spectator — they can then request to rejoin as a player
    target_info["kicked"] = False
    target_info["role"]   = "spectator"

    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/make_bot", methods=["POST"])
def make_bot():
    """Admin converts a seated player to an NPC bot.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    player = next(
        (p for p in getattr(session, "all_players", [])
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{target_name}' not found."})
    if getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{target_name}' is already a bot."})

    player.is_npc = True

    # Disconnect the player's client connection if present
    for cid, info in list(clients.items()):
        if cid != client_id and (info.get("name") or "").lower() == target_name.lower():
            info["kicked"] = True  # marks as disconnected so poll loop drops them

    # Clear any pending preselections / suggestions for this player
    key_prefix = f"{target_name.lower()}:"
    for d in (getattr(session, "_preselections", {}), getattr(session, "_suggestions", {})):
        for k in [k for k in d if k.startswith(key_prefix)]:
            d.pop(k, None)

    # If it's the new bot's turn, auto-play immediately
    if round_phase(session) == "playing":
        auto_play_npc_turns(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/transfer_admin", methods=["POST"])
def transfer_admin():
    """Admin hands admin role to another connected player.
    Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Find the target client
    target_cid = next(
        (cid for cid, info in clients.items()
         if cid != client_id
         and not info.get("kicked")
         and (info.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if not target_cid:
        return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})

    # Transfer: demote old admin, promote new one
    admin_info["role"]            = "player"
    clients[target_cid]["role"]   = "admin"

    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/set_anim_pref", methods=["POST"])
def set_anim_pref():
    """Admin pushes their animation preference so new joiners inherit it.
    Body: { room_code, client_id, enabled: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    enabled   = bool(data.get("enabled", True))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    if clients.get(client_id, {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    session._anim_default = enabled
    return jsonify({"ok": True})


@app.route("/vote_kick", methods=["POST"])
def vote_kick():
    """Player casts or retracts a kick vote for a target player.
    Body: { room_code, client_id, target_name }
    Toggles the vote — calling again retracts it.
    Auto-kicks when strict majority of eligible voters agree."""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    voter_name = (info.get("name") or "").lower()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote to kick."})
    if voter_name == target_name.lower():
        return jsonify({"ok": False, "error": "Cannot vote to kick yourself."})

    # Verify target exists as a connected, non-bot, non-admin player
    target_info = next(
        (v for v in clients.values()
         if not v.get("kicked") and (v.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if target_info and target_info.get("role") == "admin":
        return jsonify({"ok": False, "error": "Cannot vote to kick the admin."})
    target_connected = target_info is not None
    if not target_connected:
        return jsonify({"ok": False, "error": f"'{target_name}' is not in the session."})

    if not hasattr(session, "_kick_votes"):
        session._kick_votes = {}

    key = target_name.lower()
    votes = session._kick_votes.setdefault(key, set())

    # Toggle
    if voter_name in votes:
        votes.discard(voter_name)
    else:
        votes.add(voter_name)

    # Count eligible voters: all non-kicked, named, non-bot players except the target
    all_players_lc = {
        (v.get("name") or "").lower()
        for v in clients.values()
        if not v.get("kicked") and v.get("name") and v.get("role") != "spectator"
    }
    eligible = all_players_lc - {key}  # exclude target

    # Auto-kick at strict majority
    kicked = False
    if len(eligible) > 0 and len(votes) > len(eligible) / 2:
        for cid, v in list(clients.items()):
            if (v.get("name") or "").lower() == key:
                v["kicked"] = True
        session._kick_votes.pop(key, None)
        kicked = True

    state = serialize_state(session, client_id)
    state["ok"]    = True
    state["kicked"] = kicked
    return jsonify(state)


@app.route("/request_rejoin", methods=["POST"])
def request_rejoin():
    """Spectator (formerly kicked) asks admin to let them rejoin.
    Body: { room_code, client_id, display_name }"""
    data         = request.json or {}
    room_code    = (data.get("room_code") or "").strip()
    client_id    = (data.get("client_id") or "").strip()
    display_name = sanitize_name((data.get("display_name") or "").strip()) or "Unknown"

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not in session."})

    requests_list = getattr(session, "_rejoin_requests", [])
    # Avoid duplicate requests
    if any(r["client_id"] == client_id for r in requests_list):
        return jsonify({**serialize_state(session, client_id), "ok": True})

    requests_list.append({"client_id": client_id, "display_name": display_name or "Unknown"})
    session._rejoin_requests = requests_list
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/handle_rejoin", methods=["POST"])
def handle_rejoin():
    """Admin approves or denies a rejoin request.
    Body: { room_code, client_id, target_client_id, approve: bool }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Remove from rejoin requests regardless of decision
    session._rejoin_requests = [r for r in getattr(session, "_rejoin_requests", [])
                                 if r["client_id"] != target_client_id]

    if approve:
        # Remove the client entry so they get the register overlay on next poll
        clients.pop(target_client_id, None)

    state = serialize_state(session, client_id)
    state["ok"] = True
    return jsonify(state)


@app.route("/vote_insurance", methods=["POST"])
def vote_insurance():
    """
    Player casts their insurance vote for a specific blackjack hand.
    Body: { room_code, client_id, bj_player, hand_idx, vote: true=insure/false=decline }
    Can be called multiple times — last vote wins.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    bj_player = (data.get("bj_player") or "").strip().capitalize()
    try:
        hand_idx = int(data.get("hand_idx", 0))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid hand index."})
    vote = bool(data.get("vote", False))   # True = insure, False = decline

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    voter_name = (info.get("name") or "").strip()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if voter_name.lower() == bj_player.lower():
        return jsonify({"ok": False, "error": "You cannot vote on your own blackjack."})

    insurance_votes = getattr(session, "_insurance_votes", [])
    vote_entry = next(
        (v for v in insurance_votes
         if v["player"].lower() == bj_player.lower() and v["hand_idx"] == hand_idx),
        None,
    )
    if not vote_entry:
        return jsonify({"ok": False, "error": "No insurance vote open for that hand."})
    if vote_entry.get("resolved"):
        return jsonify({"ok": False, "error": "This vote has already been resolved."})

    vote_entry["votes"][voter_name] = vote
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/preselect", methods=["POST"])
def preselect():
    """Player pre-votes their intended action. Dealer sees this in the UI.
    Body: { room_code, client_id, hand, action }  action: h|s|d|sp"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    action    = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    name = info.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Spectators cannot pre-select actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    if not hasattr(session, "_preselections"):
        session._preselections = {}

    session._preselections[f"{name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/suggest_action", methods=["POST"])
def suggest_action():
    """Dealer suggests a different action to a player.
    Body: { room_code, client_id, player_name, hand, action }  action: h|s|d|sp"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()
    hand        = (data.get("hand") or "hand1").strip().lower()
    action      = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    if not is_dealer_client(session, client_id):
        return jsonify({"ok": False, "error": "Only the dealer can suggest actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    if not hasattr(session, "_suggestions"):
        session._suggestions = {}

    session._suggestions[f"{target_name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/respond_suggest", methods=["POST"])
def respond_suggest():
    """Player accepts or declines a dealer suggestion.
    Body: { room_code, client_id, hand, accept: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    accept    = bool(data.get("accept", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    name = info.get("name", "")
    key  = f"{name.lower()}:{hand}"

    suggestions = getattr(session, "_suggestions", {})
    suggestion  = suggestions.get(key)
    if not suggestion:
        return jsonify({"ok": False, "error": "No pending suggestion."})

    if accept:
        if not hasattr(session, "_preselections"):
            session._preselections = {}
        session._preselections[key] = suggestion

    session._suggestions.pop(key, None)
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/export_csv")
def export_csv():
    """
    Return a CSV file of all drinks recorded so far in this session.
    Columns: round, dealer, player, role, rule, sips
    Usage: GET /export_csv?room_code=Jack-21
    """
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return Response("No active session.", status=404, mimetype="text/plain")

    rows = getattr(session, "_drink_csv_rows", [])

    # Aggregate: player_sips[player][rule] and dealer_sips[player][rule]
    player_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    dealer_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    num_rounds = max((r["round"] for r in rows), default=1)
    players_seen: list[str] = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        bucket = dealer_sips if row["role"] == "dealer" else player_sips
        bucket[name][row["rule"]] += row["sips"]

    all_rules = sorted({row["rule"] for row in rows})

    # Build summary CSV
    buf = io.StringIO()
    w   = csv.writer(buf)

    hand_stats  = getattr(session, "_hand_stats",       {})
    milestones  = getattr(session, "_milestones_claimed", {})

    def _pct(n, d):
        return f"{n/d*100:.1f}%" if d else "—"

    # Header metadata
    w.writerow(["Drinking Blackjack — Session Summary"])
    w.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    w.writerow(["Rounds completed", num_rounds])
    w.writerow([])

    # Milestone winners — who crossed each 50-sip threshold first
    if milestones:
        w.writerow(["MILESTONES"])
        w.writerow(["Threshold", "First to reach"])
        for boundary in sorted(milestones):
            w.writerow([f"{boundary} sips", milestones[boundary]])
        w.writerow([])

    # Per-player tables
    for name in players_seen:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        gt = pt + dt
        w.writerow([
            f"{name}",
            f"total sips: {gt}",
            f"as player: {pt}",
            f"as dealer: {dt}",
            f"sips/round: {gt/num_rounds:.2f}",
        ])
        # Hand outcome stats
        hs = hand_stats.get(name)
        if hs and hs["hands"]:
            h = hs["hands"]
            row = [
                f"Hands: {h}",
                f"Won: {hs['wins']} ({_pct(hs['wins'], h)})",
                f"Lost: {hs['losses']} ({_pct(hs['losses'], h)})",
                f"Push: {hs['pushes']} ({_pct(hs['pushes'], h)})",
            ]
            if hs["split_hands"]:
                row.append(
                    f"Splits won: {hs['split_wins']} of {hs['split_hands']}"
                    f" ({_pct(hs['split_wins'], hs['split_hands'])})")
            if hs["double_hands"]:
                row.append(
                    f"Doubles won: {hs['double_wins']} of {hs['double_hands']}"
                    f" ({_pct(hs['double_wins'], hs['double_hands'])})")
            w.writerow(row)
        w.writerow(["Rule", "Player sips", "Dealer sips", "Total", "Sips/round", "% of own"])
        for rule in all_rules:
            ps = player_sips[name].get(rule, 0)
            ds = dealer_sips[name].get(rule, 0)
            total = ps + ds
            if total == 0:
                continue
            pct = f"{total/gt*100:.1f}%" if gt else "—"
            w.writerow([rule, ps, ds, total, f"{total/num_rounds:.2f}", pct])
        w.writerow([])

    # Grand totals table
    rule_totals: dict[str, int] = defaultdict(int)
    for name in players_seen:
        for rule, s in player_sips[name].items():
            rule_totals[rule] += s
        for rule, s in dealer_sips[name].items():
            rule_totals[rule] += s
    grand_total = sum(rule_totals.values())

    w.writerow(["ALL PLAYERS COMBINED"])
    w.writerow(["Rule", "Total sips", "Sips/round", "% of total"])
    for rule in sorted(rule_totals, key=lambda r: -rule_totals[r]):
        total = rule_totals[rule]
        pct   = f"{total/grand_total*100:.1f}%" if grand_total else "—"
        w.writerow([rule, total, f"{total/num_rounds:.2f}", pct])
    w.writerow([])
    w.writerow(["Grand total", grand_total, f"{grand_total/num_rounds:.2f} sips/round"])

    # Hand stats summary table (all players)
    w.writerow([])
    w.writerow(["HAND OUTCOMES"])
    w.writerow(["Player", "Hands", "Won", "Win%", "Lost", "Loss%", "Push", "Push%",
                "Splits won", "Split win%", "Doubles won", "Double win%"])
    for name in players_seen:
        hs = hand_stats.get(name, {
            "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
            "split_hands": 0, "split_wins": 0, "double_hands": 0, "double_wins": 0,
        })
        h  = hs["hands"]
        w.writerow([
            name, h if h else "-",
            hs["wins"]   if h else "-", _pct(hs["wins"],   h),
            hs["losses"] if h else "-", _pct(hs["losses"],  h),
            hs["pushes"] if h else "-", _pct(hs["pushes"],  h),
            f"{hs['split_wins']} of {hs['split_hands']}" if hs["split_hands"]  else "-",
            _pct(hs["split_wins"],  hs["split_hands"]),
            f"{hs['double_wins']} of {hs['double_hands']}" if hs["double_hands"] else "-",
            _pct(hs["double_wins"], hs["double_hands"]),
        ])

    # Dealer stats
    dealer_stats = getattr(session, "_dealer_hand_stats", {})
    if dealer_stats:
        w.writerow([])
        w.writerow(["DEALER STATS (per dealing stint)"])
        w.writerow(["Dealer", "Hands dealt", "Won", "Win%", "Lost", "Loss%", "Push", "Push%"])
        for dname, ds in sorted(dealer_stats.items()):
            dh = ds["hands"]
            w.writerow([
                dname, dh,
                ds["wins"],   _pct(ds["wins"],   dh),
                ds["losses"], _pct(ds["losses"],  dh),
                ds["pushes"], _pct(ds["pushes"],  dh),
            ])

    return Response(
        b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"),  # UTF-8 BOM for Excel
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="drinks_summary.csv"'},
    )


@app.route("/summary_json")
def summary_json():
    """Return session drink summary as JSON for on-screen display."""
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    rows       = getattr(session, "_drink_csv_rows", [])
    num_rounds = max((r["round"] for r in rows), default=0)

    player_sips: dict[str, int] = defaultdict(int)
    dealer_sips: dict[str, int] = defaultdict(int)
    players_seen: list[str]     = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        if row["role"] == "dealer":
            dealer_sips[name] += row["sips"]
        else:
            player_sips[name] += row["sips"]

    summary = []
    for name in players_seen:
        ps = player_sips[name]
        ds = dealer_sips[name]
        summary.append({"name": name, "player_sips": ps,
                         "dealer_sips": ds, "total_sips": ps + ds})
    summary.sort(key=lambda x: -x["total_sips"])

    return jsonify({"ok": True, "rounds": num_rounds, "players": summary})


@app.route("/state")
def state():
    room_code = request.args.get("room_code", "")
    client_id = request.args.get("client_id", "")
    session   = game_sessions.get(room_code)
    return jsonify(serialize_state(session, client_id))


@app.route("/update_settings", methods=["POST"])
def update_settings():
    """Queue game settings to apply at the start of the next round (admin only)."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    admin_name_lc = (admin_info.get("name") or "").lower()
    queued = getattr(session, "_queued_settings", {})

    # Validate and queue each provided setting
    try:
        if "wager" in data:
            v = int(data["wager"])
            if v >= 1:
                queued["wager"] = v

        if "num_hands" in data:
            v = int(data["num_hands"])
            if v >= 1:
                queued["num_hands"] = v

        if "num_decks" in data:
            v = int(data["num_decks"])
            if 1 <= v <= 8:
                queued["num_decks"] = v
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid numeric setting."})

    if "add_player" in data:
        name = str(data["add_player"]).strip().capitalize()
        is_npc = bool(data.get("add_player_npc", False))
        if name:
            adds = queued.get("add_players", [])
            if not any(a["name"] == name for a in adds):
                adds.append({"name": name, "is_npc": is_npc})
            queued["add_players"] = adds

    if "remove_player" in data:
        name = str(data["remove_player"]).strip().capitalize()
        if name:
            if name.lower() == admin_name_lc:
                return jsonify({"ok": False, "error": "Cannot remove your own seat."})
            target = next(
                (p for p in session.all_players if p.name.lower() == name.lower()),
                None,
            )
            if target and getattr(target, "is_dealer", False):
                return jsonify({"ok": False, "error": "Cannot remove the current dealer's seat."})
            removes = queued.get("remove_players", [])
            if name not in removes:
                removes.append(name)
            queued["remove_players"] = removes

    if "clear_queued" in data and data["clear_queued"]:
        queued = {}

    # dealer_rotate_every is a live setting — applied immediately, not queued
    if "dealer_rotate_every" in data:
        try:
            v = int(data["dealer_rotate_every"])
            if v >= 1:
                session._dealer_rotate_every = v
        except (ValueError, TypeError):
            pass   # silently ignore a malformed value; non-critical setting

    session._queued_settings = queued
    state = serialize_state(session, client_id)
    state["output"] = ""
    return jsonify(state)


@app.route("/claim_milestone", methods=["POST"])
def claim_milestone():
    """
    Winner submits their sip-handout allocation.
    Body: { room_code, client_id, allocations: {player_name: sips, ...} }

    Rules enforced server-side:
      - Only the milestone winner may submit.
      - Cannot allocate to self.
      - Total must equal MILESTONE_HANDOUT_SIPS (5).
      - Each allocation must be a non-negative integer.
      - Must be submitted before the TTL expires.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    milestone = getattr(session, "_pending_milestone", None)
    if not milestone:
        return jsonify({"ok": False, "error": "No active milestone."})
    if time.monotonic() >= milestone["expires_at"]:
        session._pending_milestone = None
        return jsonify({"ok": False, "error": "Milestone claim window has expired."})

    # Verify caller is the winner
    clients     = getattr(session, "_room_clients", {})
    caller_info = clients.get(client_id, {})
    caller_name = caller_info.get("name", "")
    if caller_name.lower() != milestone["winner"].lower():
        return jsonify({"ok": False, "error": "Only the milestone winner can submit the handout."})

    raw_alloc = data.get("allocations", {})
    if not isinstance(raw_alloc, dict):
        return jsonify({"ok": False, "error": "allocations must be an object."})

    # Validate: non-negative ints, no self-allocation, sum = handout total
    alloc: dict[str, int] = {}
    for name, sips in raw_alloc.items():
        try:
            s = int(sips)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": f"Invalid sip count for {name}."})
        if s < 0:
            return jsonify({"ok": False, "error": "Sip counts must be non-negative."})
        if name.lower() == caller_name.lower():
            return jsonify({"ok": False, "error": "Cannot assign sips to yourself."})
        if s > 0:
            alloc[name] = s

    total = sum(alloc.values())
    if total != MILESTONE_HANDOUT_SIPS:
        return jsonify({"ok": False,
                        "error": f"Must distribute exactly {MILESTONE_HANDOUT_SIPS} sips (got {total})."})

    # Apply to sip ticker — these sips go to the recipients, not to the winner
    ticker = getattr(session, "_sip_ticker", {})
    for name, s in alloc.items():
        ticker[name] = ticker.get(name, 0) + s
    session._sip_ticker = ticker

    # Write milestone handout into the CSV accumulator so it appears in exports
    winner    = milestone["winner"]
    boundary  = milestone["boundary"]
    csv_rows  = getattr(session, "_drink_csv_rows", [])
    for name, s in alloc.items():
        csv_rows.append({
            "round":  session.round_count,
            "dealer": session.dealer_name,
            "player": name,
            "role":   "player",
            "rule":   "Milestone handout",
            "sips":   s,
        })
    session._drink_csv_rows = csv_rows

    # Log the handout
    log_lines = [f"🎉 {winner} reached {boundary} sips — milestone handout!"]
    for name, s in alloc.items():
        sip_word = "sip" if s == 1 else "sips"
        log_lines.append(f"  → {name} drinks {s} {sip_word}")
    session._log_entries = getattr(session, "_log_entries", []) + ["\n".join(log_lines)]
    session._log_version = getattr(session, "_log_version", 0) + 1

    session._pending_milestone     = None
    session._last_milestone_result = {
        "winner":      winner,
        "boundary":    boundary,
        "allocations": alloc,         # {name: sips} — only non-zero entries
        "set_at":      time.monotonic(),
    }
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/rotate_dealer", methods=["POST"])
def rotate_dealer():
    """Admin immediately rotates the dealer to the next player (lobby/name order).
    Resets rounds_this_dealer to 1. Does not start a new round.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    _newround_rotate(session)
    session.rounds_this_dealer = 1
    return jsonify({**serialize_state(session, client_id), "ok": True})


@app.route("/rules")
def rules():
    """Serve the Rules.md content as plain text for frontend markdown rendering."""
    rules_path = os.path.join(os.path.dirname(__file__), "docs", "Rules.md")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except FileNotFoundError:
        return jsonify({"ok": False, "content": "# Rules\n\nRules file not found."})

# ---------------------------------------------------------------------------
# Digital help
# ---------------------------------------------------------------------------

def _print_digital_help():
    print("""
  DIGITAL MODE COMMANDS
  =====================
  deal
      Deal initial 2 cards to all hands from the shoe.

  hit <player> [hand<n>]
      Deal one card from the shoe to that hand.
      Example: hit Rob hand1

  stand <player> [hand<n>]
      Mark the hand as stood.
      Example: stand Alice hand2

  double <player> [hand<n>]
      Double down -- deal one card then stand. Must be on first two cards.
      Example: double Rob hand1

  split <player> [hand<n>]
      Split the hand and deal one card to each resulting hand.
      Example: split Rob hand1

  insurance <player> [hand<n>]
      Mark the hand as insured (when dealer shows Ace).

  blackjack <player> [hand<n>]
      Confirm a natural blackjack and fire drinking rules.

  dealer
      Reveal the hole card, hit until 17+, then auto-evaluate all hands.

  endround
      Finalise the round -- fire end-of-round drinking rules and print summary.

  newround [rotate]
      Start a new round. Add 'rotate' to pass the dealer role clockwise.

  status
      Show current state of all hands.
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"

    print("\n  Drinking Blackjack Referee -- Web Mode")
    print("  Local:   http://localhost:5000")
    print(f"  iPhone:  http://{local_ip}:5000  (same WiFi)")
    print("  (Ctrl+C to stop)\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
