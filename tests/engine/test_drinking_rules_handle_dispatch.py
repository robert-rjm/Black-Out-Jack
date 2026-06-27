"""
Tests for DrinkingRules.handle() dispatch — engine/drinking_rules.py
"""

from unittest.mock import patch
import pytest

from engine.drinking_rules import DrinkingRules
from engine.events import (
    CardDealtEvent,
    BlackjackEvent,
    InsuranceResolvedEvent,
    HandResolvedEvent,
    AllHandsSweepEvent,
    DealerHandRevealedEvent,
    RoundEndEvent,
    HardDealerSwitchEvent,
)
from tests.conftest import make_card, make_hand, make_player


def test_card_dealt_dispatch():
    card = make_card("A", "H")
    event = CardDealtEvent(
        card=card, recipient="Alice", card_pos=1,
        all_names=["Alice", "Bob"], dealer_name="Bob",
        ace_clubs_flag={}, is_dealer_hand=False,
    )
    with patch.object(DrinkingRules, "on_card_dealt", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(
        card, "Alice", 1, ["Alice", "Bob"], "Bob", {}, is_dealer_hand=False,
    )
    assert result == "SENTINEL"


def test_blackjack_dispatch():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    event = BlackjackEvent(player_name="Alice", hand=hand, all_names=["Alice", "Bob"])
    with patch.object(DrinkingRules, "on_blackjack", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with("Alice", hand, ["Alice", "Bob"], hard_switch_dealer="")
    assert result == "SENTINEL"


def test_insurance_resolved_dispatch():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    event = InsuranceResolvedEvent(
        player_name="Alice", hand=hand, all_names=["Alice", "Bob"],
        insured=True, dealer_bj=False,
    )
    with patch.object(DrinkingRules, "resolve_insurance_vote", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(
        "Alice", hand, ["Alice", "Bob"], insured=True, dealer_bj=False,
        hard_switch_dealer="",
    )
    assert result == "SENTINEL"


def test_hand_resolved_dispatch():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    event = HandResolvedEvent(player_name="Alice", hand=hand, all_names=["Alice", "Bob"])
    with patch.object(DrinkingRules, "on_hand_resolved", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(
        "Alice", hand, ["Alice", "Bob"], dealer_bj=False, dealer_name="",
    )
    assert result == "SENTINEL"


def test_all_hands_sweep_dispatch():
    hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    event = AllHandsSweepEvent(
        player_name="Alice", player_hands=hands, all_names=["Alice", "Bob"], wager=1,
    )
    with patch.object(DrinkingRules, "check_all_hands_sweep", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(
        "Alice", hands, ["Alice", "Bob"], 1, dealer_name="", dealer_bj=False,
    )
    assert result == "SENTINEL"


def test_dealer_hand_revealed_dispatch():
    hand = make_hand(("A", "H"), ("K", "H"))
    event = DealerHandRevealedEvent(dealer_hand=hand)
    with patch.object(DrinkingRules, "on_dealer_hand_revealed", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(hand)
    assert result == "SENTINEL"


def test_round_end_dispatch():
    p = make_player("Alice", hands=[make_hand(("A", "H"), ("K", "D"), result="win")])
    event = RoundEndEvent(players=[p], wager=1)
    with patch.object(DrinkingRules, "on_round_end", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with(
        [p], 1, dealer_bj=False, hard_switch_dealer="", num_hands=0,
    )
    assert result == "SENTINEL"


def test_hard_dealer_switch_dispatch():
    hand = make_hand(("A", "H"), ("K", "D"))
    event = HardDealerSwitchEvent(dealer_name="Dealer", winning_hands=[("Bob", hand)])
    with patch.object(DrinkingRules, "on_hard_dealer_switch", return_value="SENTINEL") as m:
        result = DrinkingRules.handle(event)
    m.assert_called_once_with("Dealer", [("Bob", hand)], half_protected=False)
    assert result == "SENTINEL"


def test_unrecognized_event_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        DrinkingRules.handle(object())
