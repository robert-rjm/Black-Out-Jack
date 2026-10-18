"""
Every drinking penalty/credit is expressed in wagers: at wager W the sip
amounts below are W times the wager-1 amounts. engine/drinking_rules.py
"""

import pytest

from engine.drinking_rules import DrinkingRules
from engine.blackjack import Card, Rank, Suit
from tests.conftest import make_hand

ALL = ["Alice", "Bob", "Carol"]
W = 3


def _card(rank, suit):
    return Card(rank, suit)


def test_blackjack_bonus_scales():
    hand = make_hand(("A", "S"), ("J", "S"))            # suited + A+J + black = x8
    msgs = DrinkingRules.on_blackjack("Alice", hand, ALL, wager=W)
    assert {m[1] for m in msgs} == {8 * W}


def test_insurance_double_bonus_scales():
    hand = make_hand(("A", "S"), ("J", "S"))
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ALL, insured=True, dealer_bj=False, wager=W)
    assert {m[1] for m in msgs} == {16 * W}


def test_dealer_suited_hand_scales():
    hand = make_hand(("2", "H"), ("3", "H"), ("4", "H"))
    msgs = DrinkingRules.on_dealer_hand_revealed(hand, wager=W)
    assert msgs[0][1] == 2 * W


def test_four_aces_scale():
    aces = [_card(Rank.ACE, s) for s in Suit]
    msgs, fd = DrinkingRules.check_four_aces(aces, "first_deal", False, wager=W)
    assert msgs[0][1] == 2 * W and fd is True
    msgs, _ = DrinkingRules.check_four_aces(aces, "end_of_round", False, wager=W)
    assert msgs[0][1] == W


@pytest.mark.parametrize("suit,expected", [
    (Suit.HEARTS, ("Alice", W)),
    (Suit.DIAMONDS, ("Dealer", W)),
])
def test_player_ace_effects_scale(suit, expected):
    msgs = DrinkingRules.on_card_dealt(
        _card(Rank.ACE, suit), "Alice", 1, ["Alice", "Bob", "Dealer"], "Dealer", {},
        wager=W)
    assert (msgs[0][0], msgs[0][1]) == expected


def test_ace_of_clubs_credit_scales():
    msgs = DrinkingRules.on_card_dealt(
        _card(Rank.ACE, Suit.CLUBS), "Alice", 1, ["Alice", "Bob", "Dealer"], "Dealer", {},
        wager=W)
    assert msgs[0][1] == -W


def test_dealer_ace_effects_scale():
    msgs = DrinkingRules.on_card_dealt(
        _card(Rank.ACE, Suit.HEARTS), "Dealer", 1, ["Alice", "Dealer"], "Dealer", {},
        is_dealer_hand=True, wager=W)
    assert msgs[0][1] == W


def test_five_card_21_handout_scales():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "S"), ("5", "C"), ("7", "H"))
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL, wager=W)
    handout = [m for m in msgs if len(m) > 3 and m[3] == "handout"]
    assert handout[0][1] == -5 * W


def test_hard_switch_scales():
    reg = make_hand(("9", "H"), ("8", "D"), result="win")
    dbl = make_hand(("5", "H"), ("6", "D"), ("K", "S"), doubled=True, result="win")
    msgs = DrinkingRules.on_hard_dealer_switch(
        "Dealer", [("Bob", reg), ("Carol", dbl)], wager=W)
    assert msgs[0][1] == (1 + 2) * W
