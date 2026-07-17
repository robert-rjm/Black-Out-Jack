"""
app/services/targeted_drinking.py
===================================
Targeted Drinking Mode (Rules.md §5.10): an admin-started subgame that
forces one or more specific players into a standalone bust/stand mini-game,
played between normal rounds, until they "graduate" (enough correct
guesses in a row) or the subgame is cancelled. This is the MVP scope only
-- majority-vote start/end, escalating loss penalties, cooldown
consent-override, and AFK handling are deliberately deferred.

Unlike Bust Vote (opt-in, single round, guesses against that round's real
dealer hand), this deals its own isolated dealer-only hand from a fresh
shuffled deck -- same "never touches session.shoe" isolation Dealer
Lottery uses, for the same reason (this event shouldn't skew the main
game's card economy). It does NOT ride alongside normal play: it's its own
mini-round, triggered once a normal round ends (`check_targeted_drinking_trigger`,
called from round_pipeline.py, mirrors `check_dealer_lottery_trigger`) and
opened on the next tick once milestone/Dealer Lottery are clear
(`maybe_start_targeted_drinking_round`, mirrors `maybe_start_dealer_lottery`)
-- so it never stacks with those either. Targets vote blind (the isolated
hand isn't dealt until the vote window closes), then the hand is dealt and
resolved in one shot (`resolve_targeted_drinking_round`) for the frontend
to reveal card-by-card, the same way Dealer Lottery's redeal is.

Once triggered, mini-rounds chain back-to-back until the subgame ends
(every target graduates, or the admin cancels) -- resolve_targeted_drinking_round
re-arms `_targeted_drinking_eligible` immediately if the subgame is still
running, instead of waiting for an entire normal round to play out before
the next one. A short TARGETED_DRINKING_REVEAL_PAUSE_SECONDS breather after
each result keeps the next vote prompt from popping over the previous
reveal before anyone's had a chance to see it.
"""

from __future__ import annotations

import random
import time

from engine.blackjack import Card, Deck, Hand
from app.models.game_room import GameRoom
from app.config import (
    TARGETED_DRINKING_VOTE_WINDOW_SECONDS,
    TARGETED_DRINKING_REVEAL_PAUSE_SECONDS,
    TARGETED_DRINKING_STREAK_TO_GRADUATE,
    TARGETED_DRINKING_COOLDOWN_ROUNDS,
)
from app.services.drink_tracker import award_sips
from app.services.serializer import serialize_card, round_phase


def start_targeted_drinking(session: GameRoom, target_names: list[str]) -> bool:
    """Admin-only entry point. Returns False (no-op) if the subgame is
    already running, the cooldown hasn't elapsed yet, no targets were
    given, or any name isn't a currently-connected, non-kicked player.
    On success, marks the subgame active with a fresh (zeroed) graduation
    streak for each target. The first mini-round doesn't open until the
    current normal round ends (see check_targeted_drinking_trigger) -- this
    never interrupts a round already in progress.

    check_targeted_drinking_trigger only ever fires once, at the moment a
    round *transitions into* round-over (called from the end-round
    pipeline) -- if the subgame is started while already sitting between
    rounds (round-over already reached, admin just hasn't dealt the next
    one yet), that trigger has already come and gone for this round-over
    period and won't fire again until a whole *new* round completes,
    stranding the subgame active but never eligible. So: if the room is
    already in round-over when this starts, arm eligibility immediately
    instead of waiting for it.
    """
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
    session._targeted_drinking_total_sips = {name: 0 for name in target_names}
    session._targeted_drinking_correct_counts = {name: 0 for name in target_names}
    session._targeted_drinking_wrong_counts = {name: 0 for name in target_names}
    session._targeted_drinking_dealer_hands = 0
    session._targeted_drinking_dealer_busts = 0
    if round_phase(session) == "round-over":
        session.round._targeted_drinking_eligible = True
    return True


def check_targeted_drinking_trigger(session: GameRoom) -> None:
    """Mark this round eligible for a Targeted Drinking mini-round, if the
    subgame is active. Call once per round from the end-round pipeline
    (mirrors check_dealer_lottery_trigger) -- unlike Dealer Lottery there's
    no rare-hand condition to check, just whether the subgame is running.
    Only sets the *eligible* flag -- does not open the vote window yet (see
    maybe_start_targeted_drinking_round), so a pending milestone or Dealer
    Lottery draw doesn't eat into this window's clock, and prompts never
    stack."""
    if not session.drinking_mode:
        return
    if not session._targeted_drinking_active:
        return
    if session.round._pending_targeted_drinking is not None:
        return  # already running (shouldn't happen same-round, but stay idempotent)
    session.round._targeted_drinking_eligible = True


def _targeted_drinking_ready_to_open(session: GameRoom) -> bool:
    """Internal: every condition EXCEPT the "Start Targeting Now" gate has
    cleared and a mini-round's vote window could open right now -- shared
    by maybe_start_targeted_drinking_round (which additionally requires
    the start-request gate) and targeted_drinking_awaiting_start (which
    reports the opposite: ready to open, but nobody's tapped the button
    yet)."""
    if not session.round._targeted_drinking_eligible:
        return False
    if session.round._pending_targeted_drinking is not None:
        return False
    if session.round._pending_milestone is not None:
        return False
    if session.round._dealer_lottery_eligible or session.round._pending_dealer_lottery is not None:
        return False
    last_result = session.drinks.last_targeted_drinking_result
    if last_result and time.monotonic() - last_result["set_at"] < TARGETED_DRINKING_REVEAL_PAUSE_SECONDS:
        return False
    return True


def targeted_drinking_awaiting_start(session: GameRoom) -> bool:
    """True when the *first* mini-round after a normal round's end could
    open right now but is waiting on someone to tap "Start Targeting Now"
    -- lets the table finish drinking for the round that just ended before
    the mini-game takes over the screen. Never true for a back-to-back
    continuation (resolve_targeted_drinking_round re-requests the start
    for itself) or once the vote window is already open."""
    return (
        _targeted_drinking_ready_to_open(session)
        and not session.round._targeted_drinking_start_requested
    )


def request_targeted_drinking_start(session: GameRoom) -> bool:
    """Any registered player taps "Start Targeting Now" to open the
    waiting mini-round. Returns False (no-op) if there's nothing waiting
    to start."""
    if not _targeted_drinking_ready_to_open(session):
        return False
    session.round._targeted_drinking_start_requested = True
    return True


def maybe_start_targeted_drinking_round(session: GameRoom) -> None:
    """Open this mini-round's vote window, if eligible, nothing is
    blocking it, and someone's tapped "Start Targeting Now" (or this is a
    back-to-back continuation, which re-requests the start for itself --
    see resolve_targeted_drinking_round). Safe to call on every /state tick.

    Waits for any pending milestone AND any pending-or-not-yet-opened
    Dealer Lottery draw to clear first, so at most one of these three
    post-round modals is ever open at once. Also waits out a short breather
    after the previous mini-round's reveal (if this is a back-to-back
    continuation, not the chain's first round) so the next vote prompt
    doesn't pop in before anyone's had a chance to see that result."""
    if not _targeted_drinking_ready_to_open(session):
        return
    if not session.round._targeted_drinking_start_requested:
        return

    session.round._pending_targeted_drinking = {
        "expires_at": time.monotonic() + TARGETED_DRINKING_VOTE_WINDOW_SECONDS,
        "votes": {name: None for name in session._targeted_drinking_targets},
    }


def submit_targeted_drinking_vote(session: GameRoom, player_name: str, vote: str) -> bool:
    """Records `player_name`'s vote ("bust" or "stand") for the current
    mini-round. Returns False if there's no open vote window or they
    aren't one of this mini-round's targets."""
    if vote not in ("bust", "stand"):
        return False
    pending = session.round._pending_targeted_drinking
    if not pending or player_name not in pending["votes"]:
        return False
    pending["votes"][player_name] = vote
    if all(v is not None for v in pending["votes"].values()):
        resolve_targeted_drinking_round(session)
    return True


def apply_targeted_drinking_vote_forfeit(session: GameRoom) -> None:
    """If the vote window has expired, default every unanswered target to
    "stand" -- the same "default the unset value to something safe/neutral"
    precedent apply_dealer_lottery_entry_forfeit already uses (it defaults
    an unset stake to 0) -- then deal and resolve the mini-round's isolated
    dealer hand. Safe to call every tick."""
    pending = session.round._pending_targeted_drinking
    if not pending or time.monotonic() < pending["expires_at"]:
        return
    for name in pending["votes"]:
        if pending["votes"][name] is None:
            pending["votes"][name] = "stand"
    resolve_targeted_drinking_round(session)


def _draw(deck) -> Card:
    """Pop the next card from `deck`, replenishing with a fresh shuffled
    52-card deck if it runs dry mid-hand -- mirrors dealer_lottery.py's own
    _draw() (a long run of low-card hits reaching 17 can plausibly exceed
    one deck's 52 cards; without this, deck.cards.pop() would raise
    IndexError and crash the /state poll for the whole room)."""
    if not deck.cards:
        deck.cards.extend(Deck().cards)
        random.shuffle(deck.cards)
    return deck.cards.pop()


def resolve_targeted_drinking_round(session: GameRoom) -> None:
    """Resolve the current mini-round: deals a fresh dealer-only hand from
    an isolated one-off deck (never touches session.shoe, same isolation
    Dealer Lottery's redeal uses) and plays it out under the normal
    dealer-hits-to-17 rule -- the hand isn't dealt until this point (the
    vote window has just closed), so nobody could have voted with
    foreknowledge of the outcome.

    For each target: a correct guess advances their graduation streak
    (removing them from the target list once it reaches
    TARGETED_DRINKING_STREAK_TO_GRADUATE); a wrong guess resets their
    streak to 0 and costs them a flat 1 sip (no escalating penalty tiers
    in the MVP). Ends the subgame once every target has graduated.

    Also updates the run-wide statistics table (Rules.md §5.10):
    _targeted_drinking_correct_counts/_wrong_counts per target, and
    _targeted_drinking_dealer_hands/_dealer_busts for the isolated dealer
    hand's own bust rate this run. These are exposed live in every state
    poll (not gated behind a seq, unlike last_targeted_drinking_result)
    so targeted players can factor the running dealer-bust% into their
    next call while the mini-round is still open.

    Stores the dealt hand + per-target outcome on
    session.drinks.last_targeted_drinking_result for the frontend to
    reveal card-by-card (mirrors last_dealer_lottery_result), and bumps
    _targeted_drinking_result_seq so the frontend can detect a new result
    exactly once (mirrors _dealer_lottery_result_seq).
    """
    pending = session.round._pending_targeted_drinking
    if not pending:
        return

    session.round._pending_targeted_drinking = None
    session.round._targeted_drinking_eligible = False

    deck = Deck()
    random.shuffle(deck.cards)
    hand = Hand()
    hand.cards.append(_draw(deck))
    hand.cards.append(_draw(deck))
    while hand.score() < 17:
        hand.cards.append(_draw(deck))

    dealer_busted = hand.is_bust()
    votes = pending["votes"]

    session._targeted_drinking_dealer_hands += 1
    if dealer_busted:
        session._targeted_drinking_dealer_busts += 1

    correct: dict[str, bool] = {}
    sips: dict[str, int] = {}
    graduated: list[str] = []

    for name in list(session._targeted_drinking_targets):
        vote = votes.get(name) or "stand"
        is_correct = (vote == "bust") == dealer_busted
        correct[name] = is_correct

        if is_correct:
            session._targeted_drinking_correct_counts[name] = (
                session._targeted_drinking_correct_counts.get(name, 0) + 1
            )
            streak = session._targeted_drinking_streaks.get(name, 0) + 1
            session._targeted_drinking_streaks[name] = streak
            if streak >= TARGETED_DRINKING_STREAK_TO_GRADUATE:
                session._targeted_drinking_targets.remove(name)
                graduated.append(name)
                session.round._log_entries.append(
                    f"  🎯 {name} graduated from Targeted Drinking Mode "
                    f"({streak} correct in a row)\n"
                )
                session._log_version += 1
        else:
            session._targeted_drinking_wrong_counts[name] = (
                session._targeted_drinking_wrong_counts.get(name, 0) + 1
            )
            session._targeted_drinking_streaks[name] = 0
            sips[name] = 1
            session._targeted_drinking_total_sips[name] = (
                session._targeted_drinking_total_sips.get(name, 0) + 1
            )
            award_sips(
                session, name, 1, "Targeted Drinking wrong guess",
                reason=f"Targeted Drinking: guessed {vote}, dealer "
                       f"{'busted' if dealer_busted else 'stood'} -- +1 sip",
                count_toward_round=False,
            )

    session.drinks.last_targeted_drinking_result = {
        "hand": {
            "cards": [serialize_card(c) for c in hand.cards],
            "score": hand.score(),
            "bust":  dealer_busted,
        },
        "votes":     dict(votes),
        "correct":   correct,
        "streaks":   dict(session._targeted_drinking_streaks),
        "graduated": graduated,
        "sips":      sips,
        "set_at":    time.monotonic(),
    }
    session.drinks._targeted_drinking_result_seq += 1

    if not session._targeted_drinking_targets:
        end_targeted_drinking(session, reason="all_graduated")
    else:
        # Still running -- re-arm eligibility immediately so the next
        # mini-round opens as soon as the reveal breather elapses (see
        # maybe_start_targeted_drinking_round), instead of waiting for an
        # entire normal round to play out first. Mini-rounds chain
        # back-to-back until the subgame ends -- re-request the start too,
        # so the "Start Targeting Now" gate only ever applies to the first
        # mini-round after a normal round ends, never mid-chain.
        session.round._targeted_drinking_eligible = True
        session.round._targeted_drinking_start_requested = True


def end_targeted_drinking(session: GameRoom, reason: str) -> None:
    """Ends the subgame (idempotent -- no-op if not active), clearing
    active/targets/streaks and any in-flight mini-round, and setting a
    flat cooldown before a new subgame can start (no repeat-target special
    case in the MVP). A mini-round cancelled mid-vote is simply discarded
    -- nobody's vote gets scored.

    Snapshots the whole run's per-target sip tally AND its statistics
    table (correct/wrong counts, dealer bust rate) into
    last_targeted_drinking_summary first (reason + totals + stats),
    bumping _targeted_drinking_summary_seq, so the frontend can show a
    one-shot "here's what everyone drank" recap -- mirrors
    last_targeted_drinking_result's own one-shot seq pattern, just for
    the subgame's *end* rather than each mini-round."""
    if not session._targeted_drinking_active:
        return
    session.drinks.last_targeted_drinking_summary = {
        "reason": reason,
        "totals": dict(session._targeted_drinking_total_sips),
        "correct": dict(session._targeted_drinking_correct_counts),
        "wrong": dict(session._targeted_drinking_wrong_counts),
        "dealer_hands": session._targeted_drinking_dealer_hands,
        "dealer_busts": session._targeted_drinking_dealer_busts,
        "set_at": time.monotonic(),
    }
    session.drinks._targeted_drinking_summary_seq += 1
    session._targeted_drinking_active = False
    session._targeted_drinking_targets = []
    session._targeted_drinking_streaks = {}
    session._targeted_drinking_total_sips = {}
    session._targeted_drinking_correct_counts = {}
    session._targeted_drinking_wrong_counts = {}
    session._targeted_drinking_dealer_hands = 0
    session._targeted_drinking_dealer_busts = 0
    session._targeted_drinking_cooldown_until_round = (
        session.round_count + TARGETED_DRINKING_COOLDOWN_ROUNDS
    )
    session.round._pending_targeted_drinking = None
    session.round._targeted_drinking_eligible = False
    session.round._log_entries.append(
        f"  🎯 Targeted Drinking Mode ended ({reason})\n"
    )
    session._log_version += 1
