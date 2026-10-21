"""
app/routes/moderation.py
========================
Kick / vote-kick / rejoin / leave routes.

POST /kick, /undo_kick, /vote_kick, /request_rejoin, /handle_rejoin, /leave_room
"""

from flask import Blueprint, jsonify, request
from markupsafe import escape
from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.room_manager import auto_transfer_admin
from app.services.validators import sanitize_name, is_offensive_name
from app.routes._auth import _require_admin

bp = Blueprint("moderation", __name__)


@bp.route("/kick", methods=["POST"])
def kick():
    """Admin removes a client. Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    target_name = sanitize_name(data.get("target_name") or "")
    session, client_id, admin_info, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    admin_name_lc = (admin_info.get("name") or "").lower()
    if target_name.lower() == admin_name_lc:
        return jsonify({"ok": False, "error": "Cannot kick yourself."})

    for cid, info in clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == target_name.lower()):
            info["kicked"] = True
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"No connected player named '{escape(target_name)}'."})


@bp.route("/undo_kick", methods=["POST"])
def undo_kick():
    """Admin reinstates a previously kicked client as a spectator.
    Body: { room_code, client_id, target_client_id }"""
    data             = request.json or {}
    target_client_id = (data.get("target_client_id") or "").strip()
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    target_info = clients.get(target_client_id)
    if not target_info:
        return jsonify({"ok": False, "error": "Client not found."})
    if not target_info.get("kicked"):
        return jsonify({"ok": False, "error": "Player is not kicked."})

    # Reinstate as spectator — they can then request to rejoin as a player
    target_info["kicked"] = False
    target_info["role"]   = "spectator"

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/vote_kick", methods=["POST"])
def vote_kick():
    """Player casts or retracts a kick vote for a target player.
    Body: { room_code, client_id, target_name }
    Toggles the vote — calling again retracts it.
    Auto-kicks when strict majority of eligible voters agree."""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = sanitize_name(data.get("target_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
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
        return jsonify({"ok": False, "error": f"'{escape(target_name)}' is not in the session."})

    key   = target_name.lower()
    votes = session.round._kick_votes.setdefault(key, set())

    # Toggle
    if voter_name in votes:
        votes.discard(voter_name)
    else:
        votes.add(voter_name)

    # Count eligible voters: all non-kicked, named, non-spectator players except the target
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
        session.round._kick_votes.pop(key, None)
        kicked = True

    state = serialize_state(session, client_id)
    state["ok"]     = True
    state["kicked"] = kicked
    return jsonify(state)


@bp.route("/request_rejoin", methods=["POST"])
def request_rejoin():
    """Spectator (formerly kicked) asks admin to let them rejoin.
    Body: { room_code, client_id, display_name }"""
    data         = request.json or {}
    room_code    = (data.get("room_code") or "").strip()
    client_id    = (data.get("client_id") or "").strip()
    display_name = sanitize_name((data.get("display_name") or "").strip()) or "Unknown"
    if is_offensive_name(display_name):
        display_name = "Unknown"

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not in session."})

    requests_list = session._rejoin_requests
    # Avoid duplicate requests
    if any(r["client_id"] == client_id for r in requests_list):
        return jsonify({**serialize_state(session, client_id), "ok": True})

    requests_list.append({"client_id": client_id, "display_name": display_name or "Unknown"})
    session._rejoin_requests = requests_list
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/handle_rejoin", methods=["POST"])
def handle_rejoin():
    """Admin approves or denies a rejoin request.
    Body: { room_code, client_id, target_client_id, approve: bool }"""
    data             = request.json or {}
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    # Remove from rejoin requests regardless of decision
    session._rejoin_requests = [r for r in session._rejoin_requests
                                 if r["client_id"] != target_client_id]

    if approve:
        # Remove the client entry so they get the register overlay on next poll
        clients.pop(target_client_id, None)

    state = serialize_state(session, client_id)
    state["ok"] = True
    return jsonify(state)


@bp.route("/leave_room", methods=["POST"])
def leave_room():
    """Client cleanly leaves the room.
    If they were admin, the role is auto-transferred to another player.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": True})   # room already gone, nothing to do

    clients = session._room_clients
    info    = clients.get(client_id, {})

    if info.get("role") == "admin":
        auto_transfer_admin(session, client_id)

    # Remove the leaving client entirely
    clients.pop(client_id, None)
    # Clean up any pending registration requests from this client
    session._pending_registrations = [
        r for r in session._pending_registrations if r["client_id"] != client_id
    ]
    return jsonify({"ok": True})
