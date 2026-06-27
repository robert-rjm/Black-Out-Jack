"""
Tests for DrinkingRules.check_four_aces, _bj_multiplier / on_blackjack, and
resolve_insurance_vote — engine/drinking_rules.py
"""

import pytest

from engine.drinking_rules import DrinkingRules, _bj_multiplier
from tests.conftest import make_card, make_hand


# ---------------------------------------------------------------------------
# check_four_aces
# ---------------------------------------------------------------------------

def _cards(*specs):
    return [make_card(r, s) for r, s in specs]


@pytest.mark.parametrize("triggered_first_deal", [True, False])
def test_fewer_than_four_aces_passthrough(triggered_first_deal):
    cards = _cards(("A", "S"), ("A", "H"), ("K", "C"))
    msgs, flag = DrinkingRules.check_four_aces(cards, "first_deal", triggered_first_deal)
    assert msgs == []
    assert flag == triggered_first_deal


def test_four_aces_first_deal():
    cards = _cards(("A", "S"), ("A", "H"), ("A", "D"), ("A", "C"))
    msgs, flag = DrinkingRules.check_four_aces(cards, "first_deal", False)
    assert flag is True
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient == "all"
    assert sips == 2
    assert "first deal" in reason


def test_four_aces_end_of_round_not_triggered():
    cards = _cards(("A", "S"), ("A", "H"), ("A", "D"), ("A", "C"))
    msgs, flag = DrinkingRules.check_four_aces(cards, "end_of_round", False)
    assert flag is False
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient == "all"
    assert sips == 1
    assert "end of round" in reason


def test_four_aces_end_of_round_already_triggered_first_deal():
    """No double-firing in the same round."""
    cards = _cards(("A", "S"), ("A", "H"), ("A", "D"), ("A", "C"))
    msgs, flag = DrinkingRules.check_four_aces(cards, "end_of_round", True)
    assert msgs == []
    assert flag is True


def test_more_than_four_aces_still_fires():
    """Multi-deck shoes can have duplicate aces; >=4 still fires."""
    cards = _cards(("A", "S"), ("A", "H"), ("A", "D"), ("A", "C"), ("A", "S"))
    msgs, flag = DrinkingRules.check_four_aces(cards, "first_deal", False)
    assert flag is True
    assert len(msgs) == 1


# ---------------------------------------------------------------------------
# _bj_multiplier
# ---------------------------------------------------------------------------

def test_multiplier_plain():
    hand = make_hand(("A", "H"), ("K", "D"))
    assert _bj_multiplier(hand) == 1


def test_multiplier_suited_only():
    hand = make_hand(("A", "H"), ("K", "H"))
    assert _bj_multiplier(hand) == 2


def test_multiplier_aj_only():
    hand = make_hand(("A", "H"), ("J", "D"))
    assert _bj_multiplier(hand) == 2


def test_multiplier_both_black_only():
    hand = make_hand(("K", "S"), ("Q", "C"))
    assert _bj_multiplier(hand) == 2


def test_multiplier_suited_and_aj():
    hand = make_hand(("A", "H"), ("J", "H"))
    assert _bj_multiplier(hand) == 4


def test_multiplier_suited_and_aj_and_black():
    hand = make_hand(("A", "C"), ("J", "C"))
    assert _bj_multiplier(hand) == 8


# ---------------------------------------------------------------------------
# on_blackjack
# ---------------------------------------------------------------------------

def test_on_blackjack_plain_excludes_self():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    msgs = DrinkingRules.on_blackjack("Alice", hand, ["Alice", "Bob", "Carol"])
    assert {m[0] for m in msgs} == {"Bob", "Carol"}
    for _, sips, reason in msgs:
        assert sips == 1
        assert "Blackjack by Alice" in reason
        assert "x2" not in reason and "x4" not in reason and "x8" not in reason


def test_on_blackjack_suited_aj_black_detail_and_sips():
    hand = make_hand(("A", "C"), ("J", "C"), result="win")
    msgs = DrinkingRules.on_blackjack("Alice", hand, ["Alice", "Bob"])
    recipient, sips, reason = msgs[0]
    assert recipient == "Bob"
    assert sips == 8
    assert "suited x2" in reason
    assert "A+J x2" in reason
    assert "both black x2" in reason


def test_on_blackjack_excludes_hard_switch_dealer():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    msgs = DrinkingRules.on_blackjack(
        "Alice", hand, ["Alice", "Bob", "Carol"], hard_switch_dealer="Bob"
    )
    assert {m[0] for m in msgs} == {"Carol"}


def test_on_blackjack_two_player_hard_switch_dealer_yields_empty():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    msgs = DrinkingRules.on_blackjack(
        "Alice", hand, ["Alice", "Bob"], hard_switch_dealer="Bob"
    )
    assert msgs == []


# ---------------------------------------------------------------------------
# resolve_insurance_vote
# ---------------------------------------------------------------------------

def test_insurance_insured_dealer_bj_holder_drinks_own_bonus():
    hand = make_hand(("A", "C"), ("J", "C"), result="push")  # mult = 8
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob"], insured=True, dealer_bj=True,
    )
    assert len(msgs) == 2
    holder_msg, push_msg = msgs
    assert holder_msg[0] == "Alice"
    assert holder_msg[1] == 8
    assert "drinks own BJ bonus" in holder_msg[2]
    assert push_msg[0] is None
    assert push_msg[1] == 0
    assert "pushes" in push_msg[2]


def test_insurance_insured_no_dealer_bj_group_drinks_double():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")  # mult = 1
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob", "Carol"], insured=True, dealer_bj=False,
    )
    assert {m[0] for m in msgs} == {"Bob", "Carol"}
    for _, sips, reason in msgs:
        assert sips == 2  # mult * 2
        assert "double BJ bonus" in reason


def test_insurance_declined_dealer_bj_info_only():
    hand = make_hand(("A", "H"), ("K", "D"), result="push")
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob"], insured=False, dealer_bj=True,
    )
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient is None
    assert sips == 0
    assert "auto-insurance applies" in reason


def test_insurance_declined_no_dealer_bj_delegates_to_on_blackjack():
    hand = make_hand(("A", "C"), ("J", "C"), result="win")
    direct = DrinkingRules.on_blackjack("Alice", hand, ["Alice", "Bob"])
    via_insurance = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob"], insured=False, dealer_bj=False,
    )
    assert via_insurance == direct


def test_insurance_declined_no_dealer_bj_propagates_hard_switch_dealer():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    direct = DrinkingRules.on_blackjack(
        "Alice", hand, ["Alice", "Bob", "Carol"], hard_switch_dealer="Bob"
    )
    via_insurance = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob", "Carol"],
        insured=False, dealer_bj=False, hard_switch_dealer="Bob",
    )
    assert via_insurance == direct
    assert {m[0] for m in via_insurance} == {"Carol"}


def test_insurance_insured_no_dealer_bj_hard_switch_dealer_in_group():
    """Case 2 sub-case A: dealer is a group member (not the BJ holder).
    Others drink 2× BJ bonus; dealer drinks 1× (hard switch penalty applies separately)."""
    hand = make_hand(("A", "H"), ("K", "D"), result="win")  # mult = 1
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob", "Carol"],
        insured=True, dealer_bj=False, hard_switch_dealer="Bob",
    )
    recipients = {m[0]: m[1] for m in msgs}
    assert "Carol" in recipients
    assert recipients["Carol"] == 2          # double
    assert "Bob" in recipients
    assert recipients["Bob"] == 1            # softened to 1× (hard switch applies separately)
    assert "Alice" not in recipients         # BJ holder drinks nothing in Case 2


def test_insurance_insured_no_dealer_bj_hard_switch_dealer_is_bj_holder():
    """Case 2 sub-case B: dealer IS the BJ holder.
    Group drinks double; dealer/BJ holder drinks nothing from insurance."""
    hand = make_hand(("A", "H"), ("K", "D"), result="win")  # mult = 1
    msgs = DrinkingRules.resolve_insurance_vote(
        "Alice", hand, ["Alice", "Bob", "Carol"],
        insured=True, dealer_bj=False, hard_switch_dealer="Alice",
    )
    recipients = {m[0]: m[1] for m in msgs}
    assert "Bob" in recipients and recipients["Bob"] == 2
    assert "Carol" in recipients and recipients["Carol"] == 2
    assert "Alice" not in recipients         # dealer = BJ holder — excluded entirely
