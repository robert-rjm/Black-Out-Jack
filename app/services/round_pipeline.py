"""
app/services/round_pipeline.py
================================
The five post-``cmd_endround`` steps that must run at the end of every round.

Extracted here so both the command route (game_commands.py) and the
deferred-dealer-play hook in polling.py share one authoritative sequence.
Any change to pipeline ordering or membership only needs to be made once.
"""

from app.services.drink_tracker import (
    apply_bust_vote_penalties,
    harvest_drink_log,
    check_and_set_milestone,
)
from app.services.dealer_lottery import check_dealer_lottery_trigger
from app.services.targeted_drinking import check_targeted_drinking_trigger
from app.services.payout_tracker import apply_payouts
from app.services.decision_log import backfill_hand_results


def apply_endround_pipeline(session) -> None:
    """Run the bookkeeping steps that finalise a completed round.

    ``session.cmd_endround()`` must be called by the caller *before* this
    function — the two sites need different stdout handling around that call
    so it is intentionally left outside this helper.
    """
    apply_bust_vote_penalties(session)
    harvest_drink_log(session)
    check_and_set_milestone(session)
    check_dealer_lottery_trigger(session)
    # Targeted Drinking Mode is its own standalone mini-game played between
    # rounds (Rules.md §5.10), not resolved here -- this only flags the
    # round as eligible to start one (mirrors check_dealer_lottery_trigger).
    # tick.py's maybe_start_targeted_drinking_round() opens the vote window
    # once milestone/Dealer Lottery are clear, and
    # apply_targeted_drinking_vote_forfeit() resolves it once that window
    # closes.
    check_targeted_drinking_trigger(session)
    apply_payouts(session)
    backfill_hand_results(session)
