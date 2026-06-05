"""
app/services/validators.py
===========================
Input sanitisation and client/turn authorisation checks.

These functions are pure helpers — they take values in and return results.
They do not write to the session store or produce side-effects.
"""

import re

# ---------------------------------------------------------------------------
# Name sanitisation
# ---------------------------------------------------------------------------

_NAME_STRIP_RE = re.compile(r"[<>\"'`\\]")


def sanitize_name(raw: str) -> str:
    """Sanitize a player name before storing it.

    Strips HTML tags, removes characters that could break out of HTML
    attribute or script contexts (<>"'`\\), trims whitespace, capitalizes,
    and caps length at 20 characters.  Returns an empty string if nothing
    is left after sanitization.
    """
    raw = raw[:40]                            # cap before regex (ReDoS guard)
    name = re.sub(r"<[^>]*>", "", raw)        # strip HTML tags
    name = _NAME_STRIP_RE.sub("", name)       # strip dangerous chars
    name = name.strip()
    if not name:
        return ""
    return name.capitalize()[:20]


# ---------------------------------------------------------------------------
# Client identity / authorisation
# ---------------------------------------------------------------------------

def get_client_info(session, client_id: str) -> dict:
    """Return role/name/is_dealer info for a client_id.

    Returned dict always contains: role, name, is_dealer.
    """
    clients = session._room_clients
    info    = clients.get(client_id)
    if info is None:
        return {"role": None, "name": None, "is_dealer": False}
    if info.get("kicked"):
        return {"role": "kicked", "name": None, "is_dealer": False}
    role        = info.get("role") or "spectator"
    name        = info.get("name")
    local_names = info.get("local_names") or ([name] if name else [])
    god_mode    = getattr(session, "_god_mode", False)
    is_dealer   = bool(name and name.lower() == session.dealer_name.lower()) or (role == "admin" and god_mode)
    return {"role": role, "name": name, "local_names": local_names, "is_dealer": is_dealer}


def is_dealer_client(session, client_id: str) -> bool:
    """True if this client is the admin or is registered as the current dealer."""
    info = get_client_info(session, client_id)
    god_mode = getattr(session, "_god_mode", False)
    return info["is_dealer"] or (info.get("role") == "admin" and god_mode)
