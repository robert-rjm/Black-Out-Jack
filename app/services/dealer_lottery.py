"""
app/services/dealer_lottery.py
================================
Dealer Lottery: a post-round bonus event, separate from normal play, when
the dealer's final hand happens to be a paired 18 (9-9) or 20 (any two
ten-value cards). See docs/planning/DealerLottery-Plan.md for the full
mechanic and the reasoning behind each design decision.

Sequencing: runs strictly after bust-vote resolution and milestone handout
are both fully settled, and strictly before players drink for the round.
Never touches the round's own recorded result/stats -- a pure bolt-on.

Uses an isolated one-off deck for the draw -- never touches session.shoe
(mirrors engine/busfahrer.py's identical call for the identical reason:
this event shouldn't skew the real shoe's card economy for the next round).
"""

from __future__ import annotations

import math
import random
import time

from engine.blackjack import Deck, Hand
from app.models.game_room import GameRoom
from app.config import DEALER_LOTTERY_ENTRY_WINDOW_SECONDS
from app.services.drink_tracker import award_sips
from app.services.serializer import serialize_card

# Only these two matching-value two-card totals can leave the dealer
# standing without a third card (dealer always hits below 17) -- 9-9 (18)
# or any two ten-value cards (20). Reuses Hand.can_split()'s definition of
# "pair" (matching blackjack_value, not matching rank) for consistency.
_TRIGGER_VALUES = (9, 10)


def _dealer_pair_trigger(session: GameRoom) -> bool:
    """True if this round's dealer hand is exactly two cards of matching
    blackjack value, worth 18 or 20."""
    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand:
        return False
    cards = dealer.dealer_hand.cards
    if len(cards) != 2:
        return False
    v0, v1 = cards[0].rank.blackjack_value, cards[1].rank.blackjack_value
    return v0 == v1 and v0 in _TRIGGER_VALUES


def check_dealer_lottery_trigger(session: GameRoom) -> None:
    """Mark this round eligible for the lottery, if it qualifies.

    Call once per round from the end-round pipeline, right after
    check_and_set_milestone(session). Only sets the *eligible* flag --
    does not start the entry countdown yet (see maybe_start_dealer_lottery),
    so a pending milestone doesn't eat into the entry window's clock.
    """
    if not session.drinking_mode:
        return
    if session.round._pending_dealer_lottery is not None:
        return  # already running (shouldn't happen same-round, but stay idempotent)
    if not _dealer_pair_trigger(session):
        return
    session.round._dealer_lottery_eligible = True


def maybe_start_dealer_lottery(session: GameRoom) -> None:
    """Open the entry window now, if this round is eligible and nothing is
    blocking it. Safe to call on every /state tick.

    Waits for any pending milestone to clear first -- the entry window's
    countdown only starts once the milestone modal is out of the way.
    """
    if not session.round._dealer_lottery_eligible:
        return
    if session.round._pending_dealer_lottery is not None:
        return
    if session.round._pending_milestone is not None:
        return

    session.round._pending_dealer_lottery = {
        "expires_at": time.monotonic() + DEALER_LOTTERY_ENTRY_WINDOW_SECONDS,
        "entries": {
            p.name: (0 if getattr(p, "is_npc", False) else None)
            for p in session.all_players
        },
    }


def submit_dealer_lottery_entry(session: GameRoom, player_name: str, x: int) -> bool:
    """Record `player_name`'s entry (0-5). Returns False if there's no
    pending lottery or the name isn't a recognised entrant."""
    pending = session.round._pending_dealer_lottery
    if not pending or player_name not in pending["entries"]:
        return False
    pending["entries"][player_name] = max(0, min(5, int(x)))
    return True


def apply_dealer_lottery_entry_forfeit(session: GameRoom) -> None:
    """If the entry window has expired, default every unset entry to 0 and
    resolve. Safe to call on every /state tick."""
    pending = session.round._pending_dealer_lottery
    if not pending or time.monotonic() < pending["expires_at"]:
        return
    for name, x in pending["entries"].items():
        if x is None:
            pending["entries"][name] = 0
    resolve_dealer_lottery(session)


def _play_out_new_hand(first_card, deck) -> Hand:
    """Deal one dealer-style hand starting from `first_card`, hitting from
    `deck` until standing at 17+ (matches the real dealer's soft-17 stand
    behavior -- Hand.score() already resolves the best ace interpretation,
    so this is exactly the same `while score() < 17: hit` the real dealer
    turn uses)."""
    hand = Hand()
    hand.cards.append(first_card)
    hand.cards.append(deck.cards.pop())
    while hand.score() < 17:
        hand.cards.append(deck.cards.pop())
    return hand


def resolve_dealer_lottery(session: GameRoom) -> None:
    """Resolve the pending lottery.

    No-ops (clears pending state, no draw) if every entry is 0. Otherwise
    splits the dealer's pair into two fresh hands from an isolated deck,
    plays each out, and pays out every X > 0 entrant per the payout table
    in docs/planning/DealerLottery-Plan.md §1:

      - Both new hands bust: credit yourself min(X, your current owed
        sips this round) -- floored at 0, never negative -- and open a
        handout window to give ceil(X/2) (if halving is active) or X to
        another player, mirroring /give_bust_sip's exact pattern.
      - Otherwise: drink ceil(((2 - busted) * X) / 2) if halving is
        active, else (2 - busted) * X.

    halving_active reuses the exact flag DrinkTracker.apply_end_of_round
    already uses: easy_mode or 4+ players.
    """
    pending = session.round._pending_dealer_lottery
    if not pending:
        return

    entries = {name: (x or 0) for name, x in pending["entries"].items()}
    session.round._pending_dealer_lottery = None
    session.round._dealer_lottery_eligible = False

    if all(x == 0 for x in entries.values()):
        return  # everyone opted out -- no draw, nothing logged

    dealer = session._get_dealer()
    original_cards = dealer.dealer_hand.cards  # the triggering pair

    deck = Deck()
    random.shuffle(deck.cards)

    hand_a = _play_out_new_hand(original_cards[0], deck)
    hand_b = _play_out_new_hand(original_cards[1], deck)
    busted = sum(1 for h in (hand_a, hand_b) if h.is_bust())

    halving_active = session.easy_mode or len(session.all_players) >= 4

    # Reset handout tracking for this draw (mirrors the bust-vote's reset
    # of _bust_handouts_given / _bust_handout_log at resolution time).
    session.round._dealer_lottery_handouts_given = set()
    session.round._dealer_lottery_handout_log = []
    pending_handouts: dict[str, int] = {}  # giver -> amount still to hand out

    for name, x in entries.items():
        if x <= 0:
            continue
        if busted == 2:
            current_owed = max(0, session.drinks.last_round_sips.get(name, 0))
            credit = min(x, current_owed)
            if credit > 0:
                award_sips(
                    session, name, -credit, "Dealer Lottery credit",
                    reason=f"Dealer Lottery: both split hands busted -- -{credit} sip credit",
                )
            handout_amt = math.ceil(x / 2) if halving_active else x
            if handout_amt > 0:
                pending_handouts[name] = handout_amt
        else:
            raw = (2 - busted) * x
            actual = math.ceil(raw / 2) if halving_active else raw
            if actual > 0:
                award_sips(
                    session, name, actual, "Dealer Lottery drink",
                    reason=(
                        f"Dealer Lottery: {2 - busted} of 2 new hands stood -- "
                        f"drink {actual} sip(s)"
                    ),
                )

    if pending_handouts:
        session.round._dealer_lottery_handout_expires_at = (
            time.monotonic() + DEALER_LOTTERY_ENTRY_WINDOW_SECONDS
        )
    else:
        session.round._dealer_lottery_handout_expires_at = None

    session.drinks.last_dealer_lottery_result = {
        "hand_a": [serialize_card(c) for c in hand_a.cards],
        "hand_b": [serialize_card(c) for c in hand_b.cards],
        "hand_a_score": hand_a.score(),
        "hand_b_score": hand_b.score(),
        "hand_a_bust": hand_a.is_bust(),
        "hand_b_bust": hand_b.is_bust(),
        "busted": busted,
        "entries": dict(entries),
        "pending_handouts": pending_handouts,
        "set_at": time.monotonic(),
    }
    session.round._dealer_lottery_result_seq += 1


def give_dealer_lottery_sip(session: GameRoom, giver_name: str, recipient_name: str) -> bool:
    """Giver assigns their credited handout sip(s) to `recipient_name`.
    Mirrors /give_bust_sip exactly. Returns False if there's nothing
    pending for this giver or the recipient is invalid."""
    result = session.drinks.last_dealer_lottery_result or {}
    pending_handouts = result.get("pending_handouts", {})
    amount = pending_handouts.get(giver_name)
    if not amount:
        return False
    if giver_name in session.round._dealer_lottery_handouts_given:
        return False
    if recipient_name.lower() == giver_name.lower():
        return False
    if not any(p.name == recipient_name for p in session.all_players):
        return False

    award_sips(
        session, recipient_name, amount, "Dealer Lottery handout",
        reason=f"Dealer Lottery handout (from {giver_name}): +{amount} sip(s)",
    )
    session.round._dealer_lottery_handouts_given.add(giver_name)
    session.round._dealer_lottery_handout_log.append({
        "giver": giver_name, "recipient": recipient_name, "forfeited": False,
    })
    if all(g in session.round._dealer_lottery_handouts_given for g in pending_handouts):
        session.round._dealer_lottery_handout_expires_at = None
    return True


def apply_dealer_lottery_handout_forfeit(session: GameRoom) -> None:
    """If the handout window expires before a giver assigns their sip(s),
    they keep (drink) them instead. Safe to call on every /state tick."""
    expires_at = session.round._dealer_lottery_handout_expires_at
    if not expires_at or time.monotonic() < expires_at:
        return

    result = session.drinks.last_dealer_lottery_result or {}
    pending_handouts = result.get("pending_handouts", {})
    for giver_name, amount in pending_handouts.items():
        if giver_name in session.round._dealer_lottery_handouts_given:
            continue
        award_sips(
            session, giver_name, amount, "Dealer Lottery handout forfeit",
            reason=(
                f"Dealer Lottery handout forfeited -- {giver_name} didn't assign "
                f"in time: +{amount} sip(s)"
            ),
        )
        session.round._dealer_lottery_handouts_given.add(giver_name)
        session.round._dealer_lottery_handout_log.append({
            "giver": giver_name, "recipient": None, "forfeited": True,
        })

    session.round._dealer_lottery_handout_expires_at = None
