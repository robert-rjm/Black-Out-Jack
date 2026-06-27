"""
Tests for DrinkingRules.on_hard_dealer_switch — engine/drinking_rules.py
"""

import math

from engine.drinking_rules import DrinkingRules
from tests.conftest import make_hand


def test_empty_winning_hands_returns_zero_sip_info_message():
    msgs = DrinkingRules.on_hard_dealer_switch("Dealer", [])
    assert len(msgs) == 1
    recipient, sips, reason, role = msgs[0]
    assert recipient == "Dealer"
    assert sips == 0
    assert role == "dealer"


def test_mixed_hand_types_sum_and_join():
    bj_hand     = make_hand(("A", "H"), ("K", "D"))           # blackjack
    doubled_hand = make_hand(("K", "S"), ("9", "H"), doubled=True)
    regular_hand = make_hand(("8", "H"), ("9", "D"))

    winning_hands = [
        ("Dealer", bj_hand),       # dealer's own BJ -> 1
        ("Bob", bj_hand),          # other's BJ -> 2
        ("Carol", doubled_hand),   # doubled win -> 2
        ("Dave", regular_hand),    # regular win -> 1
    ]
    msgs = DrinkingRules.on_hard_dealer_switch("Dealer", winning_hands)
    assert len(msgs) == 1
    recipient, sips, reason, role = msgs[0]
    assert recipient == "Dealer"
    assert sips == 1 + 2 + 2 + 1
    assert role == "dealer"
    assert reason.count(";") == 3  # 4 lines joined by "; "
    assert "1 sip (no multiplier)" in reason
    assert "2 sips" in reason


def test_half_protected_total_gt_zero_halves_and_labels():
    regular_hand = make_hand(("8", "H"), ("9", "D"))
    doubled_hand = make_hand(("K", "S"), ("9", "H"), doubled=True)
    winning_hands = [("Bob", regular_hand), ("Carol", doubled_hand)]
    total = 1 + 2  # = 3

    msgs = DrinkingRules.on_hard_dealer_switch("Dealer", winning_hands, half_protected=True)
    recipient, sips, reason, role = msgs[0]
    assert sips == math.ceil(total / 2)
    assert "half protection" in reason
    assert f"(halved from {total}:" in reason


def test_half_protected_total_zero_falls_through_to_normal():
    msgs = DrinkingRules.on_hard_dealer_switch("Dealer", [], half_protected=True)
    recipient, sips, reason, role = msgs[0]
    assert sips == 0
    assert "halved" not in reason
    assert "half protection" not in reason


def test_dealer_own_bj_is_1_other_bj_is_2_same_call():
    bj_hand = make_hand(("A", "H"), ("K", "D"))
    winning_hands = [("Dealer", bj_hand), ("Bob", bj_hand)]
    msgs = DrinkingRules.on_hard_dealer_switch("Dealer", winning_hands)
    recipient, sips, reason, role = msgs[0]
    assert sips == 1 + 2
    assert "Dealer blackjack (own hand) => 1 sip (no multiplier)" in reason
    assert "Bob blackjack => 2 sips" in reason
