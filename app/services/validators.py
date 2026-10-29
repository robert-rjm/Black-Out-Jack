"""
app/services/validators.py
===========================
Input sanitisation and client/turn authorisation checks.

These functions are pure helpers — they take values in and return results.
They do not write to the session store or produce side-effects.
"""

import re

from better_profanity import profanity

profanity.load_censor_words()

# ---------------------------------------------------------------------------
# Name sanitisation
# ---------------------------------------------------------------------------

_NAME_STRIP_RE = re.compile(r"[<>\"'`\\]")

# Unicode bidi-control characters (RTL/LTR override and embedding marks),
# zero-width/invisible joiners, and the BOM (U+FEFF) -- these have no visible
# glyph but could be used to visually spoof or reorder a player's name
# wherever it's displayed (lists, kick prompts, leaderboards, etc.)
_BIDI_CONTROL_RE = re.compile(
    "[​-‏‪-‮⁠-⁩﻿]"
)


def sanitize_name(raw: str) -> str:
    """Sanitize a player name before storing it.

    Strips HTML tags, removes characters that could break out of HTML
    attribute or script contexts (<>"'`\\), strips invisible Unicode
    bidi-control/formatting characters that could visually spoof the name,
    trims whitespace, capitalizes, and caps length at 20 characters.
    Returns an empty string if nothing is left after sanitization.
    """
    raw = raw[:40]                            # cap before regex (ReDoS guard)
    name = re.sub(r"<[^>]*>", "", raw)        # strip HTML tags
    name = _NAME_STRIP_RE.sub("", name)       # strip dangerous chars
    name = _BIDI_CONTROL_RE.sub("", name)     # strip invisible bidi/formatting chars
    name = name.strip()
    if not name:
        return ""
    return name.capitalize()[:20]


def is_offensive_name(name: str) -> bool:
    """True if `name` (already run through sanitize_name) contains
    profanity, per better-profanity's wordlist + leetspeak normalization.

    Call this only at the handful of entry points where a brand-new
    free-text name is created (room setup, add player, rejoin display
    name) -- not at routes that just match an existing player/seat name,
    since that name was already checked when it was first created.
    """
    return bool(name) and profanity.contains_profanity(name)


# ---------------------------------------------------------------------------
# Numeric settings
# ---------------------------------------------------------------------------

def clamp_int(raw, lo: int, hi: int) -> int:
    """int(raw) forced into [lo, hi]. Raises ValueError/TypeError on junk,
    same as int(), so callers keep their existing "Invalid numeric" reply."""
    return max(lo, min(hi, int(raw)))


def clamp_float(raw, lo: float, hi: float) -> float:
    """float(raw) forced into [lo, hi]; rejects nan/inf, which slip past
    min/max comparisons."""
    v = float(raw)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError("not a finite number")
    return max(lo, min(hi, v))


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
    god_mode    = session._god_mode
    dealer_low  = session.dealer_name.lower()
    is_dealer   = (dealer_low in {(n or "").lower() for n in local_names}) or (role == "admin" and god_mode)
    return {"role": role, "name": name, "local_names": local_names, "is_dealer": is_dealer}


def is_dealer_client(session, client_id: str) -> bool:
    """True if this client is the admin or is registered as the current dealer."""
    return get_client_info(session, client_id)["is_dealer"]
