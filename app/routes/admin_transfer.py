"""
app/routes/admin_transfer.py
============================
Admin-role handover routes.

POST /transfer_admin, /admin_afk/open, /admin_afk/vote
"""

from flask import Blueprint, jsonify, request
from markupsafe import escape
from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.room_manager import auto_transfer_admin, transfer_local_names
from app.services.validators import sanitize_name
from app.services.afk import open_admin_afk_vote, cast_admin_afk_vote
from app.routes._auth import _require_admin

bp = Blueprint("admin_transfer", __name__)


@bp.route("/transfer_admin", methods=["POST"])
def transfer_admin():
    """Admin hands admin role to another connected player.
    Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    target_name = sanitize_name(data.get("target_name") or "")
    session, client_id, admin_info, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    # Find the target client
    target_cid = next(
        (cid for cid, info in clients.items()
         if cid != client_id
         and not info.get("kicked")
         and (info.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if not target_cid:
        return jsonify({"ok": False, "error": f"No connected player named '{escape(target_name)}'."})

    # Transfer: demote old admin, promote new one.
    # Move local_names to the new admin so they retain control of any local
    # multiplayer seats.  The old admin only keeps their own single seat name.
    old_local_names = admin_info.get("local_names") or []
    old_admin_name  = (admin_info.get("name") or "").lower()
    # Exclude the old admin's own primary seat — they keep it; the new admin
    # should NOT receive control of it (would let them cast votes on the old
    # admin's behalf).
    seats_to_transfer = [n for n in old_local_names if n.lower() != old_admin_name]
    admin_info["role"]          = "player"
    admin_info["local_names"]   = []   # old admin loses multi-seat control
    new_admin_info              = clients[target_cid]
    new_admin_info["role"]      = "admin"
    transfer_local_names(seats_to_transfer, new_admin_info)

    return jsonify({**serialize_state(session, client_id), "ok": True})


def _hand_admin_to_voter(session, old_cid: str, voter_cids: list[str]) -> None:
    """After a passed admin-AFK vote: promote the first Yes-voter (they just
    proved they are connected -- auto_transfer_admin's "first eligible
    client" could pick someone who is gone) and demote the old admin to a
    plain player. The old admin keeps only their own seat; any extra seats
    they controlled (e.g. absorbed AFK seats) go to the new admin."""
    clients = session._room_clients
    new_cid = next((cid for cid in voter_cids if cid in clients and cid != old_cid), None)
    if new_cid is None:
        auto_transfer_admin(session, old_cid)
        new_cid = next((cid for cid, i in clients.items()
                        if i.get("role") == "admin" and cid != old_cid), None)
    else:
        old_name = (clients[old_cid].get("name") or "").lower()
        moved = [n for n in (clients[old_cid].get("local_names") or []) if n.lower() != old_name]
        clients[new_cid]["role"] = "admin"
        transfer_local_names(moved, clients[new_cid])
    clients[old_cid]["role"] = "player"
    clients[old_cid]["local_names"] = []
    if new_cid and session._admin_afk_last_result:
        session._admin_afk_last_result["new_admin"] = clients[new_cid].get("name")


def _admin_cid(session) -> str | None:
    return next((c for c, i in session._room_clients.items() if i.get("role") == "admin"), None)


@bp.route("/admin_afk/open", methods=["POST"])
def admin_afk_open():
    """A connected seated player starts the unanimous "admin is AFK" vote.
    Only allowed while the game is waiting on the admin.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    with session._registry_lock:
        admin_cid = _admin_cid(session)
        ok, err, passed = open_admin_afk_vote(session, client_id)
        if not ok:
            return jsonify({"ok": False, "error": err})
        if passed and admin_cid:
            _hand_admin_to_voter(session, admin_cid, [client_id])
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/admin_afk/vote", methods=["POST"])
def admin_afk_vote():
    """Cast a Yes/No vote on the open admin-AFK vote. One No fails it; all
    Yes (unanimous) hands the admin role to the first Yes-voter.
    Body: { room_code, client_id, vote: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    with session._registry_lock:
        admin_cid = _admin_cid(session)
        voters = list((session.round._pending_admin_afk_vote or {}).get("votes", {}))
        ok, err, outcome = cast_admin_afk_vote(session, client_id, bool(data.get("vote")))
        if not ok:
            return jsonify({"ok": False, "error": err})
        if outcome == "passed" and admin_cid:
            _hand_admin_to_voter(session, admin_cid, voters)
    return jsonify({**serialize_state(session, client_id), "ok": True})
