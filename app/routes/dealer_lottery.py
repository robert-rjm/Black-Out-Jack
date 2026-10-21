"""
app/routes/dealer_lottery.py
============================
Dealer Lottery routes.

POST /dealer_lottery/enter, /dealer_lottery/ack_reveal, /dealer_lottery/give_sip
"""

import time as _time
from flask import Blueprint, jsonify, request
from app.services.session_store import game_sessions
from app.services.validators import sanitize_name
from app.services.serializer import serialize_state
from app.services.dealer_lottery import (
    submit_dealer_lottery_entry,
    resolve_dealer_lottery,
    give_dealer_lottery_sip,
    ack_dealer_lottery_reveal,
    maybe_start_dealer_lottery_handout,
)

bp = Blueprint("dealer_lottery", __name__)


@bp.route("/dealer_lottery/enter", methods=["POST"])
def dealer_lottery_enter():
    """Player submits their Dealer Lottery entry (0-5 sips).
    Body: { room_code, client_id, x, player_name? }
    Can be re-submitted any time before the entry window closes — last
    value wins. `player_name` optionally submits on behalf of one of this
    client's local players (shared-device seats), mirroring /cast_bust_vote.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    try:
        x = int(data.get("x"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "x must be a number."})
    if not (0 <= x <= 5):
        return jsonify({"ok": False, "error": "x must be between 0 and 5."})

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if not session.round._pending_dealer_lottery:
        return jsonify({"ok": False, "error": "No dealer lottery is open."})
    if _time.monotonic() >= session.round._pending_dealer_lottery["expires_at"]:
        return jsonify({"ok": False, "error": "Entry window is closed."})

    client_info = session._room_clients.get(client_id, {})
    entrant_name = client_info.get("name")
    if not entrant_name:
        return jsonify({"ok": False, "error": "Not registered."})

    player_name = sanitize_name((data.get("player_name") or "").strip())
    if player_name:
        local_names = client_info.get("local_names") or [entrant_name]
        if player_name not in local_names:
            return jsonify({"ok": False, "error": "Not one of your local players."})
        entrant_name = player_name

    if not submit_dealer_lottery_entry(session, entrant_name, x):
        return jsonify({"ok": False, "error": "Not an entrant in this lottery."})

    # If every entry is in (no one still awaiting a submission), resolve
    # immediately rather than making the table wait out the full window.
    pending = session.round._pending_dealer_lottery
    if pending and all(v is not None for v in pending["entries"].values()):
        resolve_dealer_lottery(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/dealer_lottery/ack_reveal", methods=["POST"])
def dealer_lottery_ack_reveal():
    """Client closed the draw-reveal modal; the handout waits for all of them.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if client_id not in session._room_clients:
        return jsonify({"ok": False, "error": "Not registered."})
    ack_dealer_lottery_reveal(session, client_id)
    maybe_start_dealer_lottery_handout(session)
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/dealer_lottery/give_sip", methods=["POST"])
def dealer_lottery_give_sip():
    """Dealer Lottery credit-winner hands their sip(s) to a chosen player.
    Body: { room_code, client_id, giver_name, recipient_name }
    giver_name must be one of the client's local_names and have a pending
    handout. Mirrors /give_bust_sip exactly.
    """
    data           = request.json or {}
    room_code      = (data.get("room_code")      or "").strip()
    client_id      = (data.get("client_id")      or "").strip()
    giver_name     = sanitize_name(data.get("giver_name")     or "")
    recipient_name = sanitize_name(data.get("recipient_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    client_info = session._room_clients.get(client_id, {})
    if not client_info.get("name"):
        return jsonify({"ok": False, "error": "Not registered."})

    local_names = client_info.get("local_names") or [client_info["name"]]
    if giver_name not in local_names:
        return jsonify({"ok": False, "error": "Not one of your local players."})

    result = session.drinks.last_dealer_lottery_result or {}
    if giver_name not in result.get("pending_handouts", {}):
        return jsonify({"ok": False, "error": "No pending handout for this player."})
    if giver_name in session.round._dealer_lottery_handouts_given:
        return jsonify({"ok": False, "error": "Already given."})

    if not give_dealer_lottery_sip(session, giver_name, recipient_name):
        return jsonify({"ok": False, "error": "Could not give sip — check the recipient."})

    log_line = f"  🎰 Dealer Lottery: {giver_name} gives their sip(s) to {recipient_name}\n"
    session.round._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})
