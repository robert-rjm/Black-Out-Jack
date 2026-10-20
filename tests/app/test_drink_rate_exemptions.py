"""Aces, bust vote, Devil's Hand / Lucky Sevens and Wild Card sips take a
discount rate but never a booster; ordinary hand-result drinks take both."""

from engine.blackjack import Card, Rank, Suit
from engine.drinking_rules import DrinkingRules, DrinkTracker
from tests.conftest import make_player


def _players(rate=0.4):
    ps = [make_player("Alice", is_dealer=True), make_player("Bob")]
    for p in ps:
        p.effective_drink_rate = rate
    return ps


def test_add_drink_exempt_takes_discount_but_not_booster():
    p = _players()[1]
    p.add_drink(5, "normal")
    p.add_drink(5, "exempt", scale=False)
    assert [e[0] for e in p.drink_log] == [2, 2]
    assert p.drink_log[1].raw == 5 and p.drink_log[1].rate == 0.4
    p.effective_drink_rate = 1.5
    p.add_drink(5, "normal")
    p.add_drink(5, "exempt", scale=False)
    assert [e[0] for e in p.drink_log][2:] == [8, 5]
    assert p.drink_log[3].rate == 1.0


def test_ace_drinks_take_discount():
    alice, bob = _players()
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    msgs = DrinkingRules.on_card_dealt(
        Card(Rank.ACE, Suit.HEARTS), "Bob", 1, ["Alice", "Bob"], "Alice", {},
        is_dealer_hand=False, wager=5)
    tracker.apply(msgs)
    assert [e[0] for e in bob.drink_log] == [2]


def test_ace_drinks_ignore_booster():
    alice, bob = _players(rate=1.5)
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    msgs = DrinkingRules.on_card_dealt(
        Card(Rank.ACE, Suit.HEARTS), "Bob", 1, ["Alice", "Bob"], "Alice", {},
        is_dealer_hand=False, wager=5)
    tracker.apply(msgs)
    assert [e[0] for e in bob.drink_log] == [5]


def test_four_aces_take_discount_not_booster():
    cards = [Card(Rank.ACE, s) for s in Suit]
    for rate, expected in ((0.4, 4), (1.5, 10)):
        alice, bob = _players(rate=rate)
        tracker = DrinkTracker([alice, bob], alice, verbose=False)
        msgs, _ = DrinkingRules.check_four_aces(cards, "first_deal", False, wager=5)
        tracker.apply(msgs)
        assert [e[0] for e in alice.drink_log] == [expected]
        assert [e[0] for e in bob.drink_log] == [expected]


def test_ordinary_hand_drink_still_scales():
    alice, bob = _players()
    tracker = DrinkTracker([alice, bob], alice, verbose=False)
    tracker.apply([("Bob", 5, "lost a hand")])
    assert [e[0] for e in bob.drink_log] == [2]
