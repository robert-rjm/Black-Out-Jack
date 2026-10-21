"""
app/routes/boj.py
=================
"Switch to BOJ" poll routes.

POST /boj/propose, /boj/vote, /boj/split/cancel, /boj/split/go
"""

from flask import Blueprint, jsonify, request
from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.boj_switch import start_boj_poll, submit_boj_vote, cancel_split, go_split

bp = Blueprint("boj", __name__)


def _boj_client(data):
    """Resolve (session, client_id, info, error) for a /boj/* request."""
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session = game_sessions.get(room_code)
    if not session:
        return None, client_id, {}, "Room not found."
    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return session, client_id, {}, "Not registered."
    return session, client_id, info, None


@bp.route("/boj/propose", methods=["POST"])
def boj_propose():
    """A seated player asks a Normal table to switch to BOJ (opens the poll).
    Body: { room_code, client_id }"""
    session, client_id, info, err = _boj_client(request.json or {})
    if err:
        return jsonify({"ok": False, "error": err})
    if not info.get("name") or info.get("role") == "spectator":
        return jsonify({"ok": False, "error": "Spectators cannot start this vote."})
    ok, error = start_boj_poll(session, info["name"])
    if not ok:
        return jsonify({"ok": False, "error": error})
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/boj/vote", methods=["POST"])
def boj_vote():
    """Cast a Yes/No vote on the open switch-to-BOJ poll.
    Body: { room_code, client_id, vote: bool }"""
    data = request.json or {}
    session, client_id, info, err = _boj_client(data)
    if err:
        return jsonify({"ok": False, "error": err})
    if not info.get("name"):
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if not submit_boj_vote(session, info["name"], bool(data.get("vote"))):
        return jsonify({"ok": False, "error": "No vote is currently open for you."})
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/boj/split/cancel", methods=["POST"])
def boj_split_cancel():
    """A player about to leave for a new BOJ table backs out (cancel modal).
    Body: { room_code, client_id }"""
    session, client_id, _info, err = _boj_client(request.json or {})
    if err:
        return jsonify({"ok": False, "error": err})
    if not cancel_split(session, client_id):
        return jsonify({"ok": False, "error": "Too late to cancel."})
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/boj/split/go", methods=["POST"])
def boj_split_go():
    """Redirect a mover to the new BOJ table once the cancel window has passed.
    Returns { ok, room_code } -- the client then polls that room, where it is
    already registered with its seats.
    Body: { room_code, client_id }"""
    session, client_id, _info, err = _boj_client(request.json or {})
    if err:
        return jsonify({"ok": False, "error": err})
    code = go_split(session, client_id)
    if not code:
        return jsonify({"ok": False, "error": "Nothing to move to."})
    return jsonify({"ok": True, "room_code": code})
