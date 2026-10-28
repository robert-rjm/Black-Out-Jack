"""
app/routes/suggestions.py
=========================
Pre-selection and action-suggestion routes.

POST /preselect, /suggest_action, /respond_suggest
"""

from flask import Blueprint, jsonify, request
from app.services.session_store import game_sessions
from app.services.validators import is_dealer_client
from app.services.serializer import serialize_state
from app.services.stats import compute_mandatory_split10
from app.services.round_state import round_phase, current_turn, hand_done

bp = Blueprint("suggestions", __name__)


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

    # House rule: pre-selecting HIT, STAND, or DOUBLE on a hand the
    # "mandatory split 10s" rule applies to opens the "Play with honor /
    # <action> without honor (1× wager)" prompt (state.honor_pending) instead
    # of recording a plain action vote.
    _ACTION_NAMES = {"h": "hit", "s": "stand", "d": "double"}
    if (action in _ACTION_NAMES and session.drinking_mode
            and current_turn(session)
            and current_turn(session).lower() == name.lower()
            and compute_mandatory_split10(session, current_turn(session), round_phase(session))):
        player      = session._get_player(name)
        active_hand = next((h for h in player.hands if not hand_done(h)), None)
        if player and active_hand:
            session.round._honor_pending = {
                "player":  player.name,
                "hand_id": id(active_hand),
                "action":  _ACTION_NAMES[action],
                "reason":  "tens",
            }
            return jsonify({**serialize_state(session, client_id), "ok": True})

    session.round._preselections[f"{name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/suggest_action", methods=["POST"])
def suggest_action():
    """Dealer suggests a different action to a player, or any player suggests
    a move for an NPC bot's turn (the bot will play it automatically).
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

    target_player = session._get_player(target_name)
    target_is_npc = bool(target_player and getattr(target_player, "is_npc", False))

    info = session._room_clients.get(client_id, {})
    if info.get("kicked") or (info.get("role") or "spectator") == "spectator":
        return jsonify({"ok": False, "error": "Spectators can't suggest actions."})

    if not target_is_npc and not is_dealer_client(session, client_id):
        return jsonify({"ok": False, "error": "Only the dealer can suggest actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    session.round._suggestions[f"{target_name.lower()}:{hand}"] = action
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

    suggestion  = session.round._suggestions.get(key)
    if not suggestion:
        return jsonify({"ok": False, "error": "No pending suggestion."})

    if accept:
        session.round._preselections[key] = suggestion

    session.round._suggestions.pop(key, None)
    return jsonify({**serialize_state(session, client_id), "ok": True})
