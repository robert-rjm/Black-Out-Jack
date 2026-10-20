"""
app/services/pause.py
======================
Host-controlled table pause (e.g. a break to chat).

While paused, ``tick`` is skipped (no forfeits, no auto-play) and the
frontend covers the screen with a "Paused" overlay. On resume every
monotonic deadline / timestamp is pushed forward by the time spent paused,
so countdowns (votes, handouts, milestone) and the session Duration clock
pick up exactly where they stopped.
"""

import time

from app.models.game_room import GameRoom

# RoundState attributes holding a bare monotonic deadline.
_ROUND_DEADLINES = (
    "_stake_window_expires_at",
    "_bust_vote_expires_at",
    "_bust_handout_expires_at",
    "_dealer_lottery_handout_expires_at",
    "_dealer_lottery_reveal_deadline",
    "_targeted_drinking_handout_expires_at",
)

# RoundState attributes holding a dict with monotonic "expires_at" / "set_at" / "started_at".
_ROUND_DICTS = (
    "_pending_milestone",
    "_pending_dealer_lottery",
    "_pending_targeted_drinking",
    "_pending_target_proposal",
    "_pending_admin_afk_vote",
    "_pending_rate_proposal",
)
_DICT_KEYS = ("expires_at", "set_at", "started_at")

# DrinkLedger attributes: dicts carrying a monotonic "set_at".
_LEDGER_DICTS = (
    "last_milestone_result",
    "last_dealer_lottery_result",
    "last_targeted_drinking_result",
    "last_targeted_drinking_summary",
    "last_target_proposal_result",
)


def is_paused(session: GameRoom) -> bool:
    return session._paused_at is not None


def _shift_dict(d, delta: float) -> None:
    if not isinstance(d, dict):
        return
    for key in _DICT_KEYS:
        if isinstance(d.get(key), (int, float)):
            d[key] += delta


def pause_game(session: GameRoom) -> bool:
    """Freeze the table. Returns False if it was already paused."""
    if is_paused(session):
        return False
    session._paused_at = time.monotonic()
    return True


def resume_game(session: GameRoom) -> bool:
    """Unfreeze the table, shifting every running clock by the paused time."""
    if not is_paused(session):
        return False
    delta = time.monotonic() - session._paused_at
    session._paused_at = None

    rnd = session.round
    for attr in _ROUND_DEADLINES:
        if getattr(rnd, attr) is not None:
            setattr(rnd, attr, getattr(rnd, attr) + delta)
    for attr in _ROUND_DICTS:
        _shift_dict(getattr(rnd, attr), delta)
    for v in rnd._insurance_votes:
        _shift_dict(v, delta)

    for attr in _LEDGER_DICTS:
        _shift_dict(getattr(session.drinks, attr), delta)

    session.stats.session_started_at += delta
    if session._admin_blocking is not None:
        sig, since = session._admin_blocking
        session._admin_blocking = (sig, since + delta)
    # Everyone looked "silent" for the whole pause only if they stopped
    # polling; refresh presence so nobody is flagged AFK the instant it ends.
    now = time.monotonic()
    for cid in session._client_last_seen:
        session._client_last_seen[cid] = now
    return True
