"""
Tests for app/services/game_engine.py's dealer_turn() end-of-round wiring.
"""

from engine.blackjack import Card, Hand, Player, Rank, Suit, Shoe
from engine.referee import RefereeSession
from app.models.game_room import GameRoom, GameConfig
from app.services.game_engine import dealer_turn


def _hand(*cards, from_split=False):
    h = Hand(from_split=from_split)
    for r, s in cards:
        h.cards.append(Card(getattr(Rank, r), getattr(Suit, s)))
    h.stood = True
    return h


def test_all_hands_sweep_still_pays_dealer_on_hard_switch():
    """Regression: the Player All-Hand Bonus (Rules.md Sec 5.5) must stack
    with the Hard Dealer Switch payout, not be swallowed by it.

    dealer_turn() exempts the dealer from the *per-hand* win events
    (HandResolvedEvent/BlackjackEvent) during a hard switch because
    on_hard_dealer_switch() already charges the dealer for those same wins.
    But on_hard_dealer_switch() only tallies blackjack/doubled/regular wins
    -- it has no term for "all hands scored 21" or "all hands same suit" --
    so exempting the dealer from AllHandsSweepEvent too (as the old code
    did) silently dropped the bonus whenever the sweeping player was the
    only other player (heads-up), since that always triggers a hard switch.
    """
    alice = Player("Alice")
    alice.hands = [
        _hand(("NINE", "HEARTS"), ("SEVEN", "DIAMONDS"), ("FIVE", "CLUBS")),   # 21
        _hand(("EIGHT", "SPADES"), ("SIX", "HEARTS"), ("SEVEN", "CLUBS"), from_split=True),  # 21
    ]

    bob = Player("Bob")
    bob.is_dealer = True
    bob.dealer_hand = _hand(("FIVE", "SPADES"), ("FIVE", "DIAMONDS"))  # 10, hits once

    raw_session = RefereeSession([bob, alice], "Bob", wager=1, num_hands=2)
    room = GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=True))
    room.shoe = Shoe(1)
    room.shoe.cards = [Card(Rank.SEVEN, Suit.SPADES)]  # dealer's one hit -> 17, stands
    # Without this, needs_reshuffle() sees 1 card against a 52-card
    # penetration threshold and silently reshuffles in a fresh random deck
    # before the queued card is ever dealt (mirrors _load_shoe() in
    # test_round_manager_integration.py).
    room.shoe.penetration = 1.0
    room.shoe.total_cards = len(room.shoe.cards)

    dealer_turn(room)

    assert alice.hands[0].result == "win"
    assert alice.hands[1].result == "win"

    reasons = [m[2] for m in room.round._eor_msgs_buffer]
    assert any("Hard Dealer Switch" in r for r in reasons)
    sweep_msgs = [m for m in room.round._eor_msgs_buffer if "all-hands sweep" in m[2]]
    assert len(sweep_msgs) == 1
    giver, sips, reason = sweep_msgs[0]
    assert giver == "Bob"
    assert sips == 2  # wager(1) x 2 for all-21
    assert "all hands scored 21" in reason
