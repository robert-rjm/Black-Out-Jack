"""
app/routes/drink_rate.py
=========================
Drink Rate Mode routes (docs/planning/DrinkTypeMode.md).

POST /drink_rate/set      — A player changes the rate of a seat they control
                            (only drinking more is allowed without a vote)
POST /drink_rate/propose  — Admin proposes a rate for some or all seats
POST /drink_rate/vote     — Connected seated player votes Yes/No on the proposal
POST /drink_rate/dismiss_offer — Decline the recommended late-joiner boost
"""

from flask import Blueprint, jsonify, request

from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.drink_rate import (
    set_own_rate, open_rate_proposal, cast_rate_vote, dismiss_late_join_offer,
)

bp = Blueprint("drink_rate", __name__)


def _session_and_ids(data: dict):
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    return game_sessions.get(room_code), client_id


def _reply(session, client_id: str, ok: bool, err: str = ""):
    if not ok:
        return jsonify({"ok": False, "error": err})
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/drink_rate/set", methods=["POST"])
def drink_rate_set():
    """Body: { room_code, client_id, seat, rate }"""
    data = request.json or {}
    session, client_id = _session_and_ids(data)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    with session._registry_lock:
        ok, err = set_own_rate(session, client_id, (data.get("seat") or "").strip(), data.get("rate"))
    return _reply(session, client_id, ok, err)


@bp.route("/drink_rate/propose", methods=["POST"])
def drink_rate_propose():
    """Body: { room_code, client_id, seats: "all" | [names], rate }"""
    data = request.json or {}
    session, client_id = _session_and_ids(data)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    seats = data.get("seats")
    if seats != "all" and not isinstance(seats, list):
        return jsonify({"ok": False, "error": "Pick the seats to change."})
    with session._registry_lock:
        ok, err = open_rate_proposal(session, client_id, seats, data.get("rate"))
    return _reply(session, client_id, ok, err)


@bp.route("/drink_rate/vote", methods=["POST"])
def drink_rate_vote():
    """Body: { room_code, client_id, vote: bool }"""
    data = request.json or {}
    session, client_id = _session_and_ids(data)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    with session._registry_lock:
        ok, err = cast_rate_vote(session, client_id, bool(data.get("vote")))
    return _reply(session, client_id, ok, err)


@bp.route("/drink_rate/dismiss_offer", methods=["POST"])
def drink_rate_dismiss_offer():
    """Body: { room_code, client_id }"""
    data = request.json or {}
    session, client_id = _session_and_ids(data)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    with session._registry_lock:
        dismiss_late_join_offer(session, client_id)
    return _reply(session, client_id, True)
