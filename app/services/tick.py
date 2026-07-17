"""
app/services/tick.py
=====================
Per-poll side-effect tick applied on every /state request.

Extracted from app/routes/polling.py so the logic is unit-testable
without a Flask request context.

Call ``tick(session)`` once per /state poll, after the session lookup
but before serializing the response.
"""

import contextlib
import io
import logging

from app.config import (
    INSURANCE_VOTE_TIMEOUT,
    BUST_VOTE_WINDOW_SECONDS,
    BUST_HANDOUT_WINDOW_SECONDS,
)
from app.services.serializer import round_phase
from app.services.drink_tracker import apply_milestone_forfeit, apply_bust_handout_forfeit
from app.services.dealer_lottery import (
    maybe_start_dealer_lottery,
    apply_dealer_lottery_entry_forfeit,
    apply_dealer_lottery_handout_forfeit,
)
from app.services.targeted_drinking import apply_targeted_drinking_vote_forfeit
from app.services.game_engine import dealer_turn, auto_play_npc_turns
from app.services.round_pipeline import apply_endround_pipeline

import time as _time

log = logging.getLogger(__name__)


def _run_deferred_dealer_play(session) -> None:
    """Run the dealer sequence when the bust-vote window has just closed.

    Safe to call speculatively — checks round_phase and window state before acting.
    """
    if round_phase(session) != "dealer-ready":
        return
    if (session.round._bust_vote_expires_at is not None
            and _time.monotonic() < session.round._bust_vote_expires_at):
        return
    log.debug("\n  (Bust vote closed — dealer plays automatically)")
    dealer_turn(session)
    with contextlib.redirect_stdout(io.StringIO()):
        session.cmd_endround()
    apply_endround_pipeline(session)


def tick(session) -> None:
    """Apply all per-poll side effects for *session*.

    Side effects (in order):
    1. Auto-resolve expired or complete insurance votes.
    2. Freeze the bust-vote countdown while any insurance vote is open.
    3. Apply milestone-handout forfeit if the claim window has expired.
    4. Pause the bust-handout countdown while a milestone handout is pending.
    5. Apply bust-vote handout forfeit if that window has expired.
    6. Start the Dealer Lottery's entry window, now that any milestone has
       cleared (no-op unless this round was flagged eligible).
    7. Apply Dealer Lottery entry-window forfeit (defaults unset entries to
       0 and resolves) if that window has expired.
    8. Apply Dealer Lottery handout-window forfeit if that window has
       expired (mirrors the bust-vote handout forfeit).
    9. Apply Targeted Drinking Mode vote forfeit if that window has
       expired (defaults unanswered targets to "stand" -- does not itself
       resolve; scoring only happens once the round genuinely ends, via
       apply_endround_pipeline). The window itself is opened at deal time
       (_cmd_deal_digital, mirroring bust-vote's own window), not here --
       so starting the subgame mid-round never interrupts the round already
       in progress; the first prompt waits for the next deal.
    10. Unblock NPC turns and trigger deferred dealer play when the bust-vote
        window closes (or all eligible players have voted).
    11. Safety-net: trigger dealer play when stuck at dealer-ready with no
        bust-vote window (e.g. bust-vote disabled, or all-BJ deal).
    """
    now = _time.monotonic()

    # 1. Auto-resolve expired or fully-voted insurance votes
    any_insurance_pending = False
    for v in session.round._insurance_votes:
        if v.get("resolved"):
            continue
        bj_player    = v["player"]
        votes_needed = sum(
            1 for p in session.all_players
            if p.name.lower() != bj_player.lower()
            and not getattr(p, "is_npc", False)
        )
        if now - v.get("started_at", now) >= INSURANCE_VOTE_TIMEOUT:
            v["resolved"] = True   # auto-resolve expired vote as decline
        elif len(v["votes"]) >= votes_needed:
            v["resolved"] = True   # everyone eligible has voted — resolve now
        else:
            any_insurance_pending = True

    # 2. Freeze bust-vote countdown while insurance is open
    if any_insurance_pending and session.round._bust_vote_expires_at is not None:
        session.round._bust_vote_expires_at = max(
            session.round._bust_vote_expires_at,
            now + BUST_VOTE_WINDOW_SECONDS,
        )

    # 3. Milestone-handout forfeit
    apply_milestone_forfeit(session)

    # 4. Pause bust-handout countdown while milestone handout is pending
    if session.round._pending_milestone and session.round._bust_handout_expires_at is not None:
        ms_expires = session.round._pending_milestone.get("expires_at")
        if ms_expires is not None:
            session.round._bust_handout_expires_at = max(
                session.round._bust_handout_expires_at,
                ms_expires + BUST_HANDOUT_WINDOW_SECONDS,
            )

    # 5. Bust-vote handout forfeit
    apply_bust_handout_forfeit(session)

    # 6. Start the Dealer Lottery entry window (waits for milestone to clear)
    maybe_start_dealer_lottery(session)

    # 7. Dealer Lottery entry-window forfeit
    apply_dealer_lottery_entry_forfeit(session)

    # 8. Dealer Lottery handout-window forfeit
    apply_dealer_lottery_handout_forfeit(session)

    # 9. Targeted-drinking vote-window forfeit
    apply_targeted_drinking_vote_forfeit(session)

    # 10. Bust-vote window closed — unblock NPCs and run dealer if ready
    if (session.round._bust_vote_expires_at is not None
            and now >= session.round._bust_vote_expires_at):
        if round_phase(session) == "playing":
            auto_play_npc_turns(session)
        _run_deferred_dealer_play(session)
    # 11. Safety net: dealer-ready with no bust-vote window
    elif round_phase(session) == "dealer-ready" and session.round._bust_vote_expires_at is None:
        _run_deferred_dealer_play(session)
