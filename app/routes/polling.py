"""
app/routes/polling.py
======================
GET /state — full game-state snapshot (client polling).

Registration, suggestions, votes, handouts and the other player routes that
used to live here are in registration.py, suggestions.py, side_bets.py,
dealer_lottery.py, boj.py and targeted_drinking.py.
"""

import logging
import time as _time

from flask import Blueprint, jsonify, request

from app.services.session_store import (
    game_sessions,
    _room_last_access,
    cleanup_stale_sessions,
    mark_waiting_client,
    get_waiting_clients,
)
from app.services.serializer import serialize_state
from app.services.afk import touch_client
from app.services.tick import tick

log = logging.getLogger(__name__)

_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 3600   # run cleanup at most once per hour

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
    if session is not None:
        touch_client(session, client_id)
        tick(session)

    if session is None:
        if room_code in game_sessions:
            mark_waiting_client(room_code, client_id)
            return jsonify({
                "ok": True,
                "waiting": True,
                "waiting_count": len(get_waiting_clients(room_code)),
            })
        return jsonify({"ok": False})

    return jsonify(serialize_state(session, client_id))
