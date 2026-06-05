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
POST /give_bust_sip   — Bust vote winner hands out their 1-sip reward
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
        # Auto-resolve expired insurance votes (treat as decline)
    if session is not None:
        _now = _time.monotonic()
        for _v in session._insurance_votes:
            if not _v.get("resolved") and _now - _v.get("started_at", _now) >= 60:
                _v["resolved"] = True
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
        # Preserve existing local_names; ensure the newly claimed name is in it
        local_names = existing.get("local_names") or []
        if name not in local_names:
            local_names = [name] + [n for n in local_names if n != name]
        session._room_clients[client_id] = {
            **existing, "name": name, "role": "admin", "kicked": False,
            "local_names": local_names,
        }
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


@bp.route("/request_local_seat", methods=["POST"])
def request_local_seat():
    """Registered player requests to add another seat as a local player.
    Body: { room_code, client_id, name }
    Goes through the same admin-approval flow as /register, but on approval
    the name is appended to the requester's local_names rather than replacing
    their primary registration.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    name      = sanitize_name((data.get("name") or "").strip())

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    existing = session._room_clients.get(client_id, {})
    role = existing.get("role")
    if role not in ("player", "admin"):
        return jsonify({"ok": False, "error": "Must be registered to add a local seat."})

    if not name:
        return jsonify({"ok": False, "error": "Name required."})

    valid_names = [p.name for p in session.all_players]
    if name not in valid_names:
        return jsonify({"ok": False, "error": f"'{name}' is not a seat in this game."})

    # Seat must be unclaimed
    for cid, info in session._room_clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == name.lower()):
            return jsonify({"ok": False, "error": f"'{name}' is already taken."})

    # Already a local name for this client
    local_names = existing.get("local_names") or []
    if name.lower() in {(n or "").lower() for n in local_names}:
        return jsonify({"ok": False, "error": f"'{name}' is already a local seat."})

    # Queue as pending with add_to_local flag
    session._pending_registrations = [
        r for r in session._pending_registrations if r["client_id"] != client_id
    ]
    session._pending_registrations.append({
        "client_id":    client_id,
        "name":         name,
        "add_to_local": True,
    })
    return jsonify({**serialize_state(session, client_id), "ok": True, "pending": True})


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
        if pending.get("add_to_local"):
            # Append to requester local_names without changing primary name/role
            existing_local = list(target_existing.get("local_names") or [])
            if name not in existing_local:
                existing_local.append(name)
            session._room_clients[target_client_id] = {
                **target_existing, "local_names": existing_local, "kicked": False
            }
        else:
            session._room_clients[target_client_id] = {
                **target_existing, "name": name, "role": "player", "kicked": False
            }
        # Seat is now claimed — remove from admin's local_names
        for info in session._room_clients.values():
            if info.get("role") == "admin":
                local_names = info.get("local_names") or []
                info["local_names"] = [n for n in local_names if n.lower() != name.lower()]
                break
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

    client_info = session._room_clients.get(client_id, {})
    voter_name  = client_info.get("name")
    if not voter_name:
        return jsonify({"ok": False, "error": "Not registered."})

    # Optional: vote on behalf of a specific local player (local multiplayer)
    player_name = sanitize_name((data.get("player_name") or "").strip())
    if player_name:
        local_names = client_info.get("local_names") or [voter_name]
        if player_name not in local_names:
            return jsonify({"ok": False, "error": "Not one of your local players."})
        # Validate that the named player actually exists in the game
        valid_names = {p.name for p in session.all_players}
        if player_name not in valid_names:
            return jsonify({"ok": False, "error": "Player not found."})
        voter_name = player_name

    session._bust_votes[voter_name] = vote
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Bust vote sip handout
# ---------------------------------------------------------------------------

@bp.route("/give_bust_sip", methods=["POST"])
def give_bust_sip():
    """Bust-vote winner gives their 1-sip reward to a chosen player.
    Body: { room_code, client_id, winner_name, recipient_name }
    winner_name must be one of the client's local_names and a confirmed winner.
    """
    data           = request.json or {}
    room_code      = (data.get("room_code")      or "").strip()
    client_id      = (data.get("client_id")      or "").strip()
    winner_name    = sanitize_name(data.get("winner_name")    or "")
    recipient_name = sanitize_name(data.get("recipient_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    client_info = session._room_clients.get(client_id, {})
    if not client_info.get("name"):
        return jsonify({"ok": False, "error": "Not registered."})

    # winner_name must be one of this client's local players
    local_names = client_info.get("local_names") or [client_info["name"]]
    if winner_name not in local_names:
        return jsonify({"ok": False, "error": "Not one of your local players."})

    result = session._bust_vote_result or {}
    if not result.get("dealer_busted") or winner_name not in result.get("winners", []):
        return jsonify({"ok": False, "error": "No pending handout for this player."})

    if winner_name in session._bust_handouts_given:
        return jsonify({"ok": False, "error": "Already given."})

    # Recipient must be a player in the game, not the winner themselves
    valid_names = {p.name for p in session.all_players}
    if recipient_name not in valid_names:
        return jsonify({"ok": False, "error": "Recipient not found."})
    if recipient_name.lower() == winner_name.lower():
        return jsonify({"ok": False, "error": "Cannot give to yourself."})

    recipient = session._get_player(recipient_name)
    if recipient:
        recipient.add_drink(1, f"Bust vote handout from {winner_name}: +1 sip", "player")
        print(f"  [bust vote] {winner_name} gives 1 sip to {recipient_name}")

    session._bust_handouts_given.add(winner_name)

    # harvest_drink_log already ran — patch the round snapshots directly so
    # the sip shows up in the drinks panel and cumulative ticker without waiting
    # for the next round.
    reason_label = f"Bust bet handout (from {winner_name}): +1 sip"
    session._last_round_drinks.append({
        "name":   recipient_name,
        "sips":   1,
        "reason": reason_label,
    })
    session._last_round_sips[recipient_name] = (
        session._last_round_sips.get(recipient_name, 0) + 1
    )
    session._sip_ticker[recipient_name] = (
        session._sip_ticker.get(recipient_name, 0) + 1
    )
    session._drink_csv_rows.append({
        "round":  session.round_count,
        "dealer": session.dealer_name,
        "player": recipient_name,
        "role":   "player",
        "rule":   "Bust vote handout",
        "sips":   1,
    })

    # Log entry visible to all players
    log_line = f"  💥 Bust bet: {winner_name} called it — {recipient_name} drinks 1 sip\n"
    session._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})
