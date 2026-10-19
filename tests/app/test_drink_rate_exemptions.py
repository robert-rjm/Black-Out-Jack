"""Drink Rate multiplier must not touch aces, bust vote, Devil's Hand /
Lucky Sevens or Wild Card sips -- only ordinary hand-result drinks."""

from engine.blackjack import Card, Rank, Suit
from engine.drinking_rules import DrinkingRules, DrinkTracker
from tests.conftest import make_player


def _players(rate=0.4):
    ps = [make_player("Alice", is_dealer=True), make_player("Bob")]
    for p in ps:
        p.effective_drink_rate = rate
    return ps


def test_add_drink_scales_by_default_and_not_when_exempt():
    p = _players()[1]
    p.add_drink(5, "normal")
    p.add_drink(5, "exempt", scale=False)
    assert [e[0] for e in p.drink_log] == [2, 5]


def test_ace_drinks_ignore_rate():
    alice, bob = _players()
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    msgs = DrinkingRules.on_card_dealt(
        Card(Rank.ACE, Suit.HEARTS), "Bob", 1, ["Alice", "Bob"], "Alice", {},
        is_dealer_hand=False, wager=5)
    tracker.apply(msgs)
    assert [e[0] for e in bob.drink_log] == [5]


def test_four_aces_ignore_rate():
    alice, bob = _players()
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    cards = [Card(Rank.ACE, s) for s in Suit]
    msgs, _ = DrinkingRules.check_four_aces(cards, "first_deal", False, wager=5)
    tracker.apply(msgs)
    assert [e[0] for e in alice.drink_log] == [10]
    assert [e[0] for e in bob.drink_log] == [10]


def test_ordinary_hand_drink_still_scales():
    alice, bob = _players()
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    tracker.apply([("Bob", 5, "lost a hand")])
    assert [e[0] for e in bob.drink_log] == [2]
