"""
app/services/targeted_drinking.py
===================================
Targeted Drinking Mode (Rules.md §5.10): an admin-started subgame that
forces one or more specific players to cast a mandatory bust/stand vote
against the real dealer hand, every round, until they "graduate" (enough
correct guesses in a row) or the subgame is cancelled. This is the MVP
scope only -- majority-vote start/end, escalating loss penalties, cooldown
consent-override, and AFK handling are deliberately deferred.

Unlike Bust Vote (opt-in, single round, any player), this is mandatory
once a player is targeted and persists across multiple rounds. Unlike
Busfahrer, it never pauses normal round flow -- it rides alongside it.
Its own vote window (`maybe_open_targeted_drinking_vote`/
`apply_targeted_drinking_vote_forfeit`, ticked every poll) never blocks
anything and only ever defaults an unanswered vote to "stand" -- actual
resolution (`resolve_targeted_drinking_round`) is called exactly once per
round, from `round_pipeline.py`'s `apply_endround_pipeline`, after the
round has genuinely ended and `harvest_drink_log()` has already run.
"""

from __future__ import annotations

import time

from app.models.game_room import GameRoom
from app.config import (
    TARGETED_DRINKING_VOTE_WINDOW_SECONDS,
    TARGETED_DRINKING_STREAK_TO_GRADUATE,
    TARGETED_DRINKING_COOLDOWN_ROUNDS,
)
from app.services.drink_tracker import award_sips


def start_targeted_drinking(session: GameRoom, target_names: list[str]) -> bool:
    """Admin-only entry point. Returns False (no-op) if the subgame is
    already running, the cooldown hasn't elapsed yet, no targets were
    given, or any name isn't a currently-connected, non-kicked player.
    On success, marks the subgame active with a fresh (zeroed) graduation
    streak for each target."""
    if session._targeted_drinking_active:
        return False
    if session.round_count < session._targeted_drinking_cooldown_until_round:
        return False
    if not target_names:
        return False

    valid_names = {p.name.lower() for p in session.all_players}
    if any(name.lower() not in valid_names for name in target_names):
        return False

    session._targeted_drinking_active = True
    session._targeted_drinking_targets = list(target_names)
    session._targeted_drinking_streaks = {name: 0 for name in target_names}
    return True


def maybe_open_targeted_drinking_vote(session: GameRoom) -> None:
    """Open this round's vote window, if the subgame is active and no
    window is open yet. Safe to call every tick (mirrors
    maybe_start_dealer_lottery). Callers should gate this behind any
    pending milestone/insurance vote the same way tick.py already gates
    Dealer Lottery, so prompts never stack."""
    if not session._targeted_drinking_active:
        return
    if session.round._targeted_drinking_expires_at is not None:
        return
    session.round._targeted_drinking_expires_at = (
        time.monotonic() + TARGETED_DRINKING_VOTE_WINDOW_SECONDS
    )


def submit_targeted_drinking_vote(session: GameRoom, player_name: str, vote: str) -> bool:
    """Records `player_name`'s vote ("bust" or "stand") for this round.
    Returns False if they're not a current target or the vote value is
    invalid."""
    if vote not in ("bust", "stand"):
        return False
    if player_name not in session._targeted_drinking_targets:
        return False
    session.round._targeted_drinking_votes[player_name] = vote
    return True


def apply_targeted_drinking_vote_forfeit(session: GameRoom) -> None:
    """If this round's vote window has expired, default every unanswered
    target to "stand" -- the same "default the unset value to something
    safe/neutral" precedent apply_dealer_lottery_entry_forfeit already
    uses (it defaults an unset stake to 0). Safe to call every tick.

    Deliberately does NOT resolve the round itself. Unlike Bust Vote's own
    countdown (which blocks dealer play until it closes, so vote-close and
    dealer-resolve happen in lockstep), this window rides alongside normal
    play without pausing it (see module docstring / §3) -- a round can
    easily outlast the 15s window. Resolving here would score the vote
    against whatever `dealer.dealer_hand` currently holds, which during a
    still-in-progress round is either the previous round's stale result or
    an empty pre-deal Hand() that reads as "not bust" -- neither is the
    real outcome. Only resolve_targeted_drinking_round(), called once from
    apply_endround_pipeline() after the round has genuinely ended, may
    score a vote. This function only locks in the "stand" default early so
    the UI can show it; resolve_targeted_drinking_round()'s own
    `votes.get(name) or "stand"` fallback would apply the same default
    regardless, even if this never ran."""
    expires_at = session.round._targeted_drinking_expires_at
    if expires_at is None or time.monotonic() < expires_at:
        return
    for name in session._targeted_drinking_targets:
        session.round._targeted_drinking_votes.setdefault(name, "stand")


def resolve_targeted_drinking_round(session: GameRoom) -> None:
    """Resolve this round's targeted-drinking votes against the real
    dealer hand's actual bust/stand outcome. Call once the round's dealer
    hand is fully known (mirrors apply_bust_vote_penalties's own
    dealer.dealer_hand.is_bust() check). No-ops if the subgame isn't
    active or the dealer hand isn't resolved yet.

    For each target: a correct guess advances their graduation streak
    (removing them from the target list once it reaches
    TARGETED_DRINKING_STREAK_TO_GRADUATE); a wrong guess resets their
    streak to 0 and costs them a flat 1 sip (no escalating penalty tiers
    in the MVP). Ends the subgame once every target has graduated.
    """
    if not session._targeted_drinking_active:
        return
    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand:
        return

    dealer_busted = dealer.dealer_hand.is_bust()
    votes = session.round._targeted_drinking_votes

    for name in list(session._targeted_drinking_targets):
        vote = votes.get(name) or "stand"
        correct = (vote == "bust") == dealer_busted

        if correct:
            streak = session._targeted_drinking_streaks.get(name, 0) + 1
            session._targeted_drinking_streaks[name] = streak
            if streak >= TARGETED_DRINKING_STREAK_TO_GRADUATE:
                session._targeted_drinking_targets.remove(name)
                session.round._log_entries.append(
                    f"  🎯 {name} graduated from Targeted Drinking Mode "
                    f"({streak} correct in a row)\n"
                )
                session._log_version += 1
        else:
            session._targeted_drinking_streaks[name] = 0
            award_sips(
                session, name, 1, "Targeted Drinking wrong guess",
                reason=f"Targeted Drinking: guessed {vote}, dealer "
                       f"{'busted' if dealer_busted else 'stood'} -- +1 sip",
            )

    if not session._targeted_drinking_targets:
        end_targeted_drinking(session, reason="all_graduated")


def end_targeted_drinking(session: GameRoom, reason: str) -> None:
    """Ends the subgame (idempotent -- no-op if not active), clearing
    active/targets/streaks and setting a flat cooldown before a new
    subgame can start (no repeat-target special case in the MVP)."""
    if not session._targeted_drinking_active:
        return
    session._targeted_drinking_active = False
    session._targeted_drinking_targets = []
    session._targeted_drinking_streaks = {}
    session._targeted_drinking_cooldown_until_round = (
        session.round_count + TARGETED_DRINKING_COOLDOWN_ROUNDS
    )
    session.round._log_entries.append(
        f"  🎯 Targeted Drinking Mode ended ({reason})\n"
    )
    session._log_version += 1
