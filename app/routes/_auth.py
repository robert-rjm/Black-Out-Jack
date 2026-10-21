"""
app/routes/_auth.py
===================
Shared request-auth helpers for admin-style routes. Lives in its own module so
route files never have to import from each other.
"""

from app.services.session_store import game_sessions
from app.services.validators    import is_dealer_client


def _require_admin(data: dict):
    """Validate room_code + client_id and verify admin role.

    Returns (session, client_id, admin_info, None) on success, or
    (None, None, None, error_message) on failure.  Every admin-only route
    calls this instead of repeating the same 6-line block.
    """
    room_code  = (data.get("room_code") or "").strip()
    client_id  = (data.get("client_id") or "").strip()
    session    = game_sessions.get(room_code)
    if not session:
        return None, None, None, "Room not found."
    admin_info = session._room_clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return None, None, None, "Admin only."
    return session, client_id, admin_info, None


def _require_host_or_dealer(data: dict):
    """Same shape as _require_admin, but also passes for the current
    dealer (is_dealer_client already folds in admin-with-god-mode) --
    used by Targeted Drinking flow-control routes (begin/cancel/continue)
    where the host-override power (/targeted_drinking/start, which picks
    targets and force-launches) should stay stricter than just operating
    the mini-round windows of an already-running subgame.

    Returns (session, client_id, info, None) on success, or
    (None, None, None, error_message) on failure.
    """
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return None, None, None, "Room not found."
    info = session._room_clients.get(client_id, {})
    if info.get("role") != "admin" and not is_dealer_client(session, client_id):
        return None, None, None, "Host or dealer only."
    return session, client_id, info, None
