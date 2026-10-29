"""
app/routes/rule_votes.py
========================
Players' say in the house rules (logic in services/rule_votes.py).

POST /rules/suggest         — Player suggests switching a rule on or off
POST /rules/suggestion      — Admin accepts or dismisses a suggestion
POST /rules/propose_voting  — Player asks the table to decide rule changes by vote
POST /rules/vote            — Player votes Yes/No on the open rule vote
"""

from flask import Blueprint, jsonify, request
from markupsafe import escape

from app.routes._auth import _require_admin
from app.services.rule_votes import (
    answer_suggestion, cast_rule_vote, propose_rule_voting, suggest_rule,
)
from app.services.serializer import serialize_state
from app.services.session_store import game_sessions

bp = Blueprint("rule_votes", __name__)


def _player(data: dict):
    """(session, client_id, info, name, error) for a seated, non-kicked client."""
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return None, None, None, None, "Room not found."
    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return None, None, None, None, "Not registered."
    name = info.get("name") or ""
    if not name or info.get("role") == "spectator":
        return None, None, None, None, "Spectators can't take part in rule changes."
    return session, client_id, info, name, None


def _reply(session, client_id, err):
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/rules/suggest", methods=["POST"])
def rules_suggest():
    """Body: { room_code, client_id, rule_id, on: bool }"""
    data = request.json or {}
    session, client_id, info, name, err = _player(data)
    if err:
        return jsonify({"ok": False, "error": err})
    if info.get("role") == "admin" and not session._rule_voting:
        return jsonify({"ok": False, "error": "You can change the rules directly."})
    rule_id = data.get("rule_id")
    if not isinstance(rule_id, str):
        return jsonify({"ok": False, "error": "Unknown rule."})
    return _reply(session, client_id, suggest_rule(session, name, rule_id, bool(data.get("on"))))


@bp.route("/rules/suggestion", methods=["POST"])
def rules_suggestion():
    """Admin answers a suggestion. Body: { room_code, client_id, index, accept: bool }"""
    data = request.json or {}
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    try:
        index = int(data.get("index"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "That suggestion is gone."})
    return _reply(session, client_id, answer_suggestion(session, index, bool(data.get("accept"))))


@bp.route("/rules/propose_voting", methods=["POST"])
def rules_propose_voting():
    """Body: { room_code, client_id }"""
    data = request.json or {}
    session, client_id, _, name, err = _player(data)
    if err:
        return jsonify({"ok": False, "error": err})
    return _reply(session, client_id, propose_rule_voting(session, name))


@bp.route("/rules/vote", methods=["POST"])
def rules_vote():
    """Body: { room_code, client_id, vote: bool }"""
    data = request.json or {}
    session, client_id, _, name, err = _player(data)
    if err:
        return jsonify({"ok": False, "error": err})
    if not cast_rule_vote(session, name, bool(data.get("vote"))):
        return jsonify({"ok": False, "error": "No rule vote is open for you."})
    return _reply(session, client_id, None)
