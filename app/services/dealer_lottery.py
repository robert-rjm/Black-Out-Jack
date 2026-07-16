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
from app.services.decision_log import record_dealer_lottery_entry
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

    entries: dict[str, int | None] = {}
    for p in session.all_players:
        if not getattr(p, "is_npc", False):
            entries[p.name] = None
            continue
        # NPC entry is a real per-personality decision (mirrors NPC hand
        # decisions in game_engine.py) -- "basic" personality or a bot with
        # no profile just opts out (0), same as before this was a decision.
        current_owed = max(0, session.drinks.last_round_sips.get(p.name, 0))
        x = p.decide_dealer_lottery_stake(current_owed) if hasattr(p, "decide_dealer_lottery_stake") else 0
        entries[p.name] = x
        record_dealer_lottery_entry(session, p.name, x, is_npc=True)

    session.round._pending_dealer_lottery = {
        "expires_at": time.monotonic() + DEALER_LOTTERY_ENTRY_WINDOW_SECONDS,
        "entries": entries,
    }


def submit_dealer_lottery_entry(session: GameRoom, player_name: str, x: int) -> bool:
    """Record `player_name`'s entry (0-5). Returns False if there's no
    pending lottery or the name isn't a recognised entrant."""
    pending = session.round._pending_dealer_lottery
    if not pending or player_name not in pending["entries"]:
        return False
    clamped = max(0, min(5, int(x)))
    pending["entries"][player_name] = clamped
    record_dealer_lottery_entry(session, player_name, clamped, is_npc=False)
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


def _deal_and_resolve_hand(hand: Hand, deck) -> list[Hand]:
    """Deal `hand`'s second card (assumes exactly one card so far) and
    resolve it: hit from `deck` until standing at 17+ (matches the real
    dealer's soft-17 stand behavior -- Hand.score() already resolves the
    best ace interpretation), unless the new card forms another matching
    pair -- then it re-splits instead of standing on the pair, exactly like
    a real player hand (Hand.split()/can_split(), same MAX_SPLITS=4 cap the
    main game already uses, so a hot run of 9s/tens can't spin out an
    unbounded hand tree -- capped at 5 hands per original starting card,
    10 total across both).

    Returns every hand this branch ultimately produces (1, unless it
    (re-)split)."""
    hand.cards.append(deck.cards.pop())
    if hand.can_split():
        sibling = hand.split()  # pops hand's 2nd card into sibling; both now hold 1 card
        return _deal_and_resolve_hand(hand, deck) + _deal_and_resolve_hand(sibling, deck)
    while hand.score() < 17:
        hand.cards.append(deck.cards.pop())
    return [hand]


def _play_out_new_hand(first_card, deck) -> list[Hand]:
    """Deal one dealer-style hand starting from `first_card` -- see
    _deal_and_resolve_hand for the hit/stand/re-split logic. Returns a list
    since a re-split branch can produce more than one hand."""
    hand = Hand()
    hand.cards.append(first_card)
    return _deal_and_resolve_hand(hand, deck)


def resolve_dealer_lottery(session: GameRoom) -> None:
    """Resolve the pending lottery.

    No-ops (clears pending state, no draw) if every entry is 0. Otherwise
    splits the dealer's pair into fresh hands from an isolated deck --
    always at least two, more if a hand re-splits (see
    _deal_and_resolve_hand) -- plays every one out, and pays out every
    X > 0 entrant per the payout table in docs/planning/DealerLottery-Plan.md
    §1:

      - Every hand busts: credit yourself min(X, your current owed sips
        this round) -- floored at 0, never negative -- and open a handout
        window to give ceil(X/2) (if halving is active) or X to another
        player, mirroring /give_bust_sip's exact pattern.
      - No hand busts: drink the full X -- never halved. Only the handout
        (above) is halved; halving softens what you hand to someone else,
        not what you owe yourself.
      - Anything in between (some hands bust, some don't): nothing
        happens -- no drink, no credit.

    This is a binary win/lose rule keyed on the two extremes (all-bust /
    none-bust) rather than the hand count, so it scales to however many
    hands a re-split produces without new cases: more hands only ever makes
    both extremes rarer (harder to bust every hand, harder to stand every
    hand), which makes the whole event gentler on average, never harsher.

    halving_active reuses the exact flag DrinkTracker.apply_end_of_round
    already uses: easy_mode or 4+ players -- but only for the handout here,
    unlike apply_end_of_round where it halves everything.
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

    hands = _play_out_new_hand(original_cards[0], deck) + _play_out_new_hand(original_cards[1], deck)
    n_hands = len(hands)
    busted = sum(1 for h in hands if h.is_bust())

    halving_active = session.easy_mode or len(session.all_players) >= 4

    # Reset handout tracking for this draw (mirrors the bust-vote's reset
    # of _bust_handouts_given / _bust_handout_log at resolution time).
    session.round._dealer_lottery_handouts_given = set()
    session.round._dealer_lottery_handout_log = []
    pending_handouts: dict[str, int] = {}  # giver -> amount still to hand out
    drink_amounts: dict[str, int] = {}     # name -> sips this lottery makes them drink
    credit_amounts: dict[str, int] = {}    # name -> sips this lottery credits off their owed total

    for name, x in entries.items():
        if x <= 0:
            continue
        if busted == n_hands:
            current_owed = max(0, session.drinks.last_round_sips.get(name, 0))
            credit = min(x, current_owed)
            if credit > 0:
                award_sips(
                    session, name, -credit, "Dealer Lottery credit",
                    reason=f"Dealer Lottery: every split hand busted -- -{credit} sip credit",
                )
                credit_amounts[name] = credit
            handout_amt = math.ceil(x / 2) if halving_active else x
            if handout_amt > 0:
                pending_handouts[name] = handout_amt
        elif busted == 0:
            # Drink is never halved -- only the handout is (halving softens
            # what you hand to someone else, not what you owe yourself).
            award_sips(
                session, name, x, "Dealer Lottery drink",
                reason=f"Dealer Lottery: no split hand busted -- drink {x} sip(s)",
            )
            drink_amounts[name] = x
        # 0 < busted < n_hands: some hands busted, some didn't -- nothing happens.

    if pending_handouts:
        session.round._dealer_lottery_handout_expires_at = (
            time.monotonic() + DEALER_LOTTERY_ENTRY_WINDOW_SECONDS
        )
    else:
        session.round._dealer_lottery_handout_expires_at = None

    session.drinks.last_dealer_lottery_result = {
        "hands": [
            {"cards": [serialize_card(c) for c in h.cards], "score": h.score(), "bust": h.is_bust()}
            for h in hands
        ],
        "busted": busted,
        "entries": dict(entries),
        "pending_handouts": pending_handouts,
        "drink_amounts": drink_amounts,
        "credit_amounts": credit_amounts,
        "set_at": time.monotonic(),
    }
    session.drinks._dealer_lottery_result_seq += 1


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
