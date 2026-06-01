"""
app/routes/polling.py
======================
Read-mostly player-interaction routes: state polling, client registration,
pre-selections, dealer suggestions, and insurance votes.

GET  /state           — Full game-state snapshot (SSE-style polling)
POST /register        — Joining client claims a seat or becomes spectator
POST /preselect       — Player pre-votes their intended action
POST /suggest_action  — Dealer suggests a different action to a player
POST /respond_suggest — Player accepts or declines a dealer suggestion
POST /vote_insurance  — Player casts their insurance vote
"""

from flask import Blueprint, jsonify, request

from app.services.session_store import game_sessions, _room_last_access, cleanup_stale_sessions
import time as _time

_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 3600   # run cleanup at most once per hour
from app.services.validators    import sanitize_name, is_dealer_client
from app.services.serializer    import serialize_state

bp = Blueprint("polling", __name__)


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@bp.route("/state")
def state():
    global _last_cleanup
    room_code = request.args.get("room_code", "")
    client_id = request.args.get("client_id", "")
    session   = game_sessions.get(room_code)
    if session is not None:
        _room_last_access[room_code] = _time.monotonic()
    # Periodically evict sessions idle for more than 24 hours
    now = _time.monotonic()
    if now - _last_cleanup > _CLEANUP_INTERVAL:
        _last_cleanup = now
        cleanup_stale_sessions()
    return jsonify(serialize_state(session, client_id))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@bp.route("/register", methods=["POST"])
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

    existing = session._room_clients.get(client_id, {})
    if existing.get("kicked"):
        if not name:
            # Kicked player wants to spectate — allow it, clear kicked flag
            session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
            # Remove any pending rejoin request for this client
            session._rejoin_requests = [r for r in session._rejoin_requests
                                        if r["client_id"] != client_id]
            return jsonify({**serialize_state(session, client_id), "ok": True})
        return jsonify({"ok": False, "error": "You have been removed from this session."})

    if not name:
        # Spectating — no approval needed
        session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
        return jsonify({**serialize_state(session, client_id), "ok": True})

    valid_names = [p.name for p in session.all_players]
    if name not in valid_names:
        return jsonify({"ok": False,
                        "error": f"'{name}' is not a seat. Available: {', '.join(valid_names)}"})

    # Check seat is not already claimed
    for cid, info in session._room_clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == name.lower()):
            return jsonify({"ok": False, "error": f"'{name}' is already taken."})

    # Admin registering their own seat — immediate, no approval needed
    if existing.get("role") == "admin":
        session._room_clients[client_id] = {"name": name, "role": "admin", "kicked": False}
        return jsonify({**serialize_state(session, client_id), "ok": True})

    # Block clients who have been denied too many times
    MAX_REG_DENIALS = 2
    if existing.get("reg_denials", 0) >= MAX_REG_DENIALS:
        return jsonify({"ok": False,
                        "error": "You have been denied too many times and cannot request to join."})

    # Cancel any previous pending request from this client (counts as one slot)
    prev_pending = [r for r in session._pending_registrations if r["client_id"] != client_id]

    # Cap: no more pending requests than there are unclaimed seats
    total_seats   = len(session.all_players)
    claimed_seats = sum(
        1 for info in session._room_clients.values()
        if info.get("name") and not info.get("kicked")
    )
    available_seats = total_seats - claimed_seats
    if len(prev_pending) >= available_seats:
        return jsonify({"ok": False,
                        "error": "Too many pending requests — wait for the host to review."})

    session._pending_registrations = prev_pending
    session._pending_registrations.append({"client_id": client_id, "name": name})
    session._room_clients[client_id] = {**existing, "name": None, "role": "pending", "kicked": False}
    return jsonify({**serialize_state(session, client_id), "ok": True, "pending": True})


# ---------------------------------------------------------------------------
# Registration approval
# ---------------------------------------------------------------------------

@bp.route("/handle_registration", methods=["POST"])
def handle_registration():
    """Admin approves or denies a pending player registration.
    Body: { room_code, client_id (admin), target_client_id, approve: bool }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if session._room_clients.get(client_id, {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    pending = next(
        (r for r in session._pending_registrations if r["client_id"] == target_client_id),
        None,
    )
    if not pending:
        return jsonify({"ok": False, "error": "No pending request found."})

    session._pending_registrations = [
        r for r in session._pending_registrations if r["client_id"] != target_client_id
    ]

    target_existing = session._room_clients.get(target_client_id, {})

    if approve:
        name = pending["name"]
        # Ensure seat is still unclaimed before approving
        for cid, info in session._room_clients.items():
            if (cid != target_client_id and not info.get("kicked")
                    and (info.get("name") or "").lower() == name.lower()):
                # Seat taken while pending — count as a denial
                denials = target_existing.get("reg_denials", 0) + 1
                session._room_clients[target_client_id] = {
                    **target_existing, "name": None, "role": "denied",
                    "kicked": False, "reg_denials": denials,
                }
                return jsonify({**serialize_state(session, client_id), "ok": True})
        session._room_clients[target_client_id] = {
            **target_existing, "name": name, "role": "player", "kicked": False
        }
    else:
        denials = target_existing.get("reg_denials", 0) + 1
        session._room_clients[target_client_id] = {
            **target_existing, "name": None, "role": "denied",
            "kicked": False, "reg_denials": denials,
        }

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/reset_registration", methods=["POST"])
def reset_registration():
    """Admin clears a client's denial count, allowing them to request again.
    Body: { room_code, client_id (admin), target_client_id }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if session._room_clients.get(client_id, {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    target = session._room_clients.get(target_client_id)
    if not target:
        return jsonify({"ok": False, "error": "Client not found."})

    session._room_clients[target_client_id] = {
        **target, "role": "spectator", "reg_denials": 0
    }
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Pre-selections and suggestions
# ---------------------------------------------------------------------------

@bp.route("/preselect", methods=["POST"])
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

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    name = info.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Spectators cannot pre-select actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    session._preselections[f"{name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/suggest_action", methods=["POST"])
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

    session._suggestions[f"{target_name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/respond_suggest", methods=["POST"])
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

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    name = info.get("name", "")
    key  = f"{name.lower()}:{hand}"

    suggestion  = session._suggestions.get(key)
    if not suggestion:
        return jsonify({"ok": False, "error": "No pending suggestion."})

    if accept:
        session._preselections[key] = suggestion

    session._suggestions.pop(key, None)
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Insurance voting
# ---------------------------------------------------------------------------

@bp.route("/vote_insurance", methods=["POST"])
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

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    voter_name = (info.get("name") or "").strip()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if voter_name.lower() == bj_player.lower():
        return jsonify({"ok": False, "error": "You cannot vote on your own blackjack."})

    vote_entry = next(
        (v for v in session._insurance_votes
         if v["player"].lower() == bj_player.lower() and v["hand_idx"] == hand_idx),
        None,
    )
    if not vote_entry:
        return jsonify({"ok": False, "error": "No insurance vote open for that hand."})
    if vote_entry.get("resolved"):
        return jsonify({"ok": False, "error": "This vote has already been resolved."})

    vote_entry["votes"][voter_name] = vote
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Bust vote side bet
# ---------------------------------------------------------------------------

@bp.route("/cast_bust_vote", methods=["POST"])
def cast_bust_vote():
    """Player casts or updates their dealer-bust confidence vote.
    Body: { room_code, client_id, vote: "bust" | "win" }
    Can be re-cast any time before round-over — last vote wins.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    vote      = (data.get("vote") or "").strip()

    if vote not in ("bust", "pass"):
        return jsonify({"ok": False, "error": "vote must be 'bust' or 'pass'."})

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if not session.bust_vote_enabled:
        return jsonify({"ok": False, "error": "Bust vote not enabled."})

    # Reject if window is expired (simple timestamp check — avoids double-calling serializer helper)
    expires = session._bust_vote_expires_at
    if not expires or _time.monotonic() >= expires:
        return jsonify({"ok": False, "error": "Vote window is closed."})

    voter_name = session._room_clients.get(client_id, {}).get("name")
    if not voter_name:
        return jsonify({"ok": False, "error": "Not registered."})

    session._bust_votes[voter_name] = vote
    return jsonify({**serialize_state(session, client_id), "ok": True})
