"""
Tests for DrinkingRules.on_hand_resolved, check_all_hands_sweep,
dealer_21_five_cards, and on_dealer_hand_revealed — engine/drinking_rules.py
"""

import pytest

from engine.drinking_rules import DrinkingRules
from tests.conftest import make_hand


ALL = ["Alice", "Bob", "Carol"]


# ---------------------------------------------------------------------------
# on_hand_resolved
# ---------------------------------------------------------------------------

def test_loss_no_special_conditions_returns_empty():
    hand = make_hand(("K", "S"), ("9", "H"), result="loss")
    assert DrinkingRules.on_hand_resolved("Alice", hand, ALL) == []


def test_push_no_special_conditions_returns_empty():
    hand = make_hand(("K", "S"), ("Q", "H"), result="push")
    assert DrinkingRules.on_hand_resolved("Alice", hand, ALL) == []


@pytest.mark.parametrize("result", ["win", "loss", "push"])
def test_21_with_5_cards_handout_fires_regardless_of_result(result):
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"),
                      result=result)
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)
    handout_msgs = [m for m in msgs if len(m) == 4 and m[3] == "handout"]
    assert len(handout_msgs) == 1
    recipient, sips, reason, role = handout_msgs[0]
    assert recipient == "Alice"
    assert sips == -5
    assert role == "handout"
    if result != "win":
        # No win-bonus messages should accompany a non-win 21/5-card hand
        assert msgs == handout_msgs


def test_dealer_bj_suppresses_21_five_card_handout():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"),
                      result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL, dealer_bj=True)
    assert not any(len(m) == 4 and m[3] == "handout" for m in msgs)


def test_doubled_win_not_suited_immunity_exception():
    hand = make_hand(("K", "S"), ("9", "H"), doubled=True, result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)
    assert {m[0] for m in msgs} == {"Bob", "Carol"}
    for _, sips, reason in msgs:
        assert sips == 1
        assert "immunity exception" in reason


def test_doubled_win_suited_skips_doubled_branch_uses_suited_4():
    hand = make_hand(("K", "S"), ("9", "S"), doubled=True, result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)
    assert {m[0] for m in msgs} == {"Bob", "Carol"}
    for _, sips, reason in msgs:
        assert sips == 4
        assert "immunity exception" not in reason
        assert "won suited hand" in reason


def test_suited_win_not_blackjack_not_doubled():
    hand = make_hand(("K", "S"), ("9", "S"), result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)
    assert {m[0] for m in msgs} == {"Bob", "Carol"}
    for _, sips, reason in msgs:
        assert sips == 1
        assert "won suited hand" in reason


def test_suited_blackjack_suppresses_suited_bonus():
    hand = make_hand(("A", "S"), ("K", "S"), result="win")  # is_blackjack True
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)
    assert msgs == []


def test_win_with_5plus_cards_stacks_with_others():
    """21, suited, doubled, 5+ cards, win => handout + suited(x4) + 5-card-win,
    all stacking in one call."""
    hand = make_hand(("2", "H"), ("3", "H"), ("4", "H"), ("5", "H"), ("7", "H"),
                      doubled=True, result="win")
    assert hand.score() == 21
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL)

    handout_msgs = [m for m in msgs if len(m) == 4 and m[3] == "handout"]
    assert len(handout_msgs) == 1
    assert handout_msgs[0][1] == -5

    suited_msgs = [m for m in msgs if "won suited hand" in m[2]]
    assert {m[0] for m in suited_msgs} == {"Bob", "Carol"}
    for _, sips, _ in suited_msgs:
        assert sips == 4  # doubled

    fivecard_msgs = [m for m in msgs if "won with" in m[2]]
    assert {m[0] for m in fivecard_msgs} == {"Bob", "Carol"}
    for _, sips, _ in fivecard_msgs:
        assert sips == 1

    # Doubled-immunity branch should NOT also fire (suited is True)
    assert not any("immunity exception" in m[2] for m in msgs)


def test_dealer_excluded_from_bonus_but_handout_unaffected():
    hand = make_hand(("2", "H"), ("3", "H"), ("4", "H"), ("5", "H"), ("7", "H"),
                      result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ALL, dealer_name="Bob")

    handout_msgs = [m for m in msgs if len(m) == 4 and m[3] == "handout"]
    assert len(handout_msgs) == 1
    assert handout_msgs[0][0] == "Alice"  # handout unaffected by dealer_name

    bonus_msgs = [m for m in msgs if len(m) == 3]
    assert {m[0] for m in bonus_msgs} == {"Carol"}  # Bob excluded as dealer


def test_two_player_table_single_other():
    hand = make_hand(("K", "S"), ("9", "S"), result="win")
    msgs = DrinkingRules.on_hand_resolved("Alice", hand, ["Alice", "Bob"])
    assert len(msgs) == 1
    assert msgs[0][0] == "Bob"


# ---------------------------------------------------------------------------
# check_all_hands_sweep
# ---------------------------------------------------------------------------

def test_sweep_dealer_bj_returns_empty():
    hands = [make_hand(("2", "H"), ("3", "H")), make_hand(("4", "H"), ("5", "H"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1, dealer_bj=True)
    assert msgs == []


def test_sweep_single_hand_returns_empty():
    hands = [make_hand(("2", "H"), ("3", "H"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    assert msgs == []


def test_sweep_empty_hands_returns_empty():
    hands = [make_hand(), make_hand()]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    assert msgs == []


def test_sweep_all_same_suit_not_all_21():
    hands = [make_hand(("2", "H"), ("3", "H")), make_hand(("4", "H"), ("6", "H"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    main = [m for m in msgs if "drinks" in m[2]]
    assert {m[0] for m in main} == {"Bob", "Carol"}
    for _, sips, reason in main:
        assert sips == 1 * 2
        assert "suited across all hands" in reason


def test_sweep_all_21_not_same_suit():
    hands = [make_hand(("A", "H"), ("K", "D")), make_hand(("7", "S"), ("4", "C"), ("K", "H"))]
    for h in hands:
        assert h.score() == 21
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    main = [m for m in msgs if "drinks" in m[2]]
    assert {m[0] for m in main} == {"Bob", "Carol"}
    for _, sips, reason in main:
        assert sips == 1 * 2
        assert "all hands scored 21" in reason


def test_sweep_both_conditions_x4():
    hands = [make_hand(("A", "H"), ("K", "H")), make_hand(("J", "H"), ("Q", "H"), ("A", "H"))]
    # both hands all-hearts and all score 21
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    main = [m for m in msgs if "drinks" in m[2]]
    for _, sips, reason in main:
        assert sips == 1 * 4
        assert "(x4)" in reason


def test_sweep_neither_condition_returns_empty():
    hands = [make_hand(("2", "H"), ("3", "D")), make_hand(("4", "S"), ("6", "C"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    assert msgs == []


@pytest.mark.parametrize("wager,multiplier", [(1, 2), (2, 2)])
def test_sweep_wager_scaling(wager, multiplier):
    hands = [make_hand(("2", "H"), ("3", "H")), make_hand(("4", "H"), ("6", "H"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, wager)
    main = [m for m in msgs if "drinks" in m[2]]
    for _, sips, _ in main:
        assert sips == wager * multiplier


def test_sweep_cancellation_for_winning_doubled_nonsuited_hands():
    hands = [
        make_hand(("A", "S"), ("K", "D")),                                            # 21, not suited
        make_hand(("7", "D"), ("4", "C"), ("K", "H"), doubled=True, result="win"),    # 21, doubled, not suited
    ]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1)
    cancel_msgs = [m for m in msgs if "Sweep cancels" in m[2]]
    assert {m[0] for m in cancel_msgs} == {"Bob", "Carol"}
    for _, sips, _ in cancel_msgs:
        assert sips == -1


def test_sweep_excludes_dealer_and_player():
    hands = [make_hand(("2", "H"), ("3", "H")), make_hand(("4", "H"), ("6", "H"))]
    msgs = DrinkingRules.check_all_hands_sweep("Alice", hands, ALL, 1, dealer_name="Bob")
    main = [m for m in msgs if "drinks" in m[2]]
    assert {m[0] for m in main} == {"Carol"}


# ---------------------------------------------------------------------------
# dealer_21_five_cards
# ---------------------------------------------------------------------------

def test_dealer_21_five_cards_true():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"))
    assert DrinkingRules.dealer_21_five_cards(hand) is True


def test_dealer_21_four_cards_false():
    hand = make_hand(("A", "H"), ("2", "D"), ("3", "C"), ("5", "S"))
    assert hand.score() == 21
    assert DrinkingRules.dealer_21_five_cards(hand) is False


def test_dealer_20_six_cards_false():
    hand = make_hand(("2", "H"), ("2", "D"), ("2", "C"), ("2", "S"), ("3", "H"), ("9", "D"))
    assert hand.score() == 20
    assert DrinkingRules.dealer_21_five_cards(hand) is False


def test_dealer_21_via_soft_ace_recount_5_cards():
    hand = make_hand(("A", "H"), ("A", "D"), ("A", "C"), ("A", "S"), ("7", "H"))
    assert hand.score() == 21
    assert DrinkingRules.dealer_21_five_cards(hand) is True


# ---------------------------------------------------------------------------
# on_dealer_hand_revealed
# ---------------------------------------------------------------------------

def test_dealer_hand_all_same_suit():
    hand = make_hand(("2", "H"), ("3", "H"), ("4", "H"))
    msgs = DrinkingRules.on_dealer_hand_revealed(hand)
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient == "all"
    assert sips == 2
    assert "Dealer hand is all" in reason


def test_dealer_hand_mixed_suits_returns_empty():
    hand = make_hand(("2", "H"), ("3", "D"))
    assert DrinkingRules.on_dealer_hand_revealed(hand) == []


def test_dealer_hand_single_card_returns_empty():
    hand = make_hand(("2", "H"))
    assert DrinkingRules.on_dealer_hand_revealed(hand) == []
