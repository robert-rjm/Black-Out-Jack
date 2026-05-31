"""
app/services/session_store.py
==============================
Single source of truth for all in-memory room/session state.

Only this module owns the dicts.  Every other module that needs to read
or write room state must go through the getters/setters here — or import
the dicts directly and treat them as read-only outside this module.
"""

import secrets
import time
from collections import defaultdict

from app.config import (
    ROOM_WORDS,
    JOIN_RATE_LIMIT, JOIN_RATE_WINDOW,
    SESSION_TTL,
)

# ---------------------------------------------------------------------------
# Primary store — keyed by room code (e.g. "Jack21")
# ---------------------------------------------------------------------------

# Value is None while a room is reserved but not yet set up via /setup,
# and a GameRoom once the game is configured.
game_sessions: dict = {}          # room_code → GameRoom | None

_room_created_at: dict[str, float] = {}   # room_code → time.monotonic() at creation

# ---------------------------------------------------------------------------
# Join rate-limiter — per source IP, applied to /join_room only
# ---------------------------------------------------------------------------

_join_attempts: dict[str, list[float]] = defaultdict(list)

# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------

def generate_room_code() -> str:
    """Return a unique code like 'Jack21' not already in game_sessions."""
    while True:
        word   = secrets.choice(ROOM_WORDS)
        number = 1 + secrets.randbelow(999)   # 1–999
        code   = f"{word}{number}"
        if code not in game_sessions:
            return code

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def is_join_rate_limited(ip: str) -> bool:
    """Return True when this IP has exceeded the failed-join rate limit.

    Side-effect: records this attempt so repeated calls accumulate.
    """
    now    = time.monotonic()
    cutoff = now - JOIN_RATE_WINDOW
    prev   = _join_attempts[ip]
    _join_attempts[ip] = [t for t in prev if t > cutoff]   # drop expired
    if len(_join_attempts[ip]) >= JOIN_RATE_LIMIT:
        return True
    _join_attempts[ip].append(now)
    return False

# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------

def reserve_room() -> str:
    """Reserve a new room slot and return its code.

    Runs stale-session cleanup first so the store doesn't grow unbounded.
    The slot is set to None until /setup initialises the game.
    """
    cleanup_stale_sessions()
    code = generate_room_code()
    game_sessions[code]    = None
    _room_created_at[code] = time.monotonic()
    return code


def get_session(room_code: str):
    """Return the session for room_code, or None if not found / not set up."""
    return game_sessions.get(room_code)


def set_session(room_code: str, session) -> None:
    """Store an initialised session against room_code."""
    game_sessions[room_code] = session


def room_exists(room_code: str) -> bool:
    """True if the room code is in the store (even if not yet set up)."""
    return room_code in game_sessions


def find_room_code(raw: str) -> str | None:
    """Case-insensitive lookup; returns the canonical-cased code or None."""
    return next((k for k in game_sessions if k.lower() == raw.lower()), None)


def cleanup_stale_sessions() -> None:
    """Drop rooms that were never set up (value is None) and are past TTL."""
    cutoff = time.monotonic() - SESSION_TTL
    stale  = [
        code for code, s in game_sessions.items()
        if s is None and _room_created_at.get(code, 0) < cutoff
    ]
    for code in stale:
        del game_sessions[code]
        _room_created_at.pop(code, None)
