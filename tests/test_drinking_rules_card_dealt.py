"""
Tests for DrinkingRules.on_card_dealt — engine/drinking_rules.py
"""

import pytest

from engine.drinking_rules import DrinkingRules
from tests.conftest import make_card


# ---------------------------------------------------------------------------
# Non-ace cards never fire
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rank", ["2", "5", "9", "10", "J", "Q", "K"])
@pytest.mark.parametrize("suit", ["S", "H", "D", "C"])
def test_non_ace_returns_empty(rank, suit, ace_clubs_flag):
    card = make_card(rank, suit)
    msgs = DrinkingRules.on_card_dealt(
        card, "Alice", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
    )
    assert msgs == []


# ---------------------------------------------------------------------------
# Player-hand aces
# ---------------------------------------------------------------------------

def test_ace_clubs_to_non_dealer_player(ace_clubs_flag):
    card = make_card("A", "C")
    msgs = DrinkingRules.on_card_dealt(
        card, "Alice", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
    )
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient == "Alice"
    assert sips == -1
    assert "credit at round end" in reason
    # Should NOT touch the ace_clubs_flag — that's the dealer-player branch only
    assert "partial_protected" not in ace_clubs_flag


def test_ace_clubs_to_dealer_player(ace_clubs_flag):
    card = make_card("A", "C")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
    )
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient is None
    assert sips == 0
    assert ace_clubs_flag["partial_protected"] is True
    assert ace_clubs_flag["dealer_player_pending_credit"] == "Bob"
    assert "partial Hard Switch protection" in reason


def test_ace_clubs_to_dealer_player_case_insensitive(ace_clubs_flag):
    """recipient/dealer_name comparison is case-insensitive."""
    card = make_card("A", "C")
    msgs = DrinkingRules.on_card_dealt(
        card, "bob", 1, ["alice", "bob"], "Bob", ace_clubs_flag,
    )
    recipient, sips, reason = msgs[0]
    assert recipient is None
    assert sips == 0
    assert ace_clubs_flag["partial_protected"] is True


@pytest.mark.parametrize("n_players", [2, 3, 4, 6])
@pytest.mark.parametrize("card_pos", [1, 2, 3, 4])
def test_ace_spades_target_wraps_correctly(n_players, card_pos, ace_clubs_flag):
    all_names = [f"P{i}" for i in range(n_players)]
    card = make_card("A", "S")
    for idx, recipient in enumerate(all_names):
        msgs = DrinkingRules.on_card_dealt(
            card, recipient, card_pos, all_names, "P0", ace_clubs_flag,
        )
        assert len(msgs) == 1
        target_recv, sips, reason = msgs[0]
        expected_target = all_names[(idx + card_pos) % len(all_names)]
        assert target_recv == expected_target
        assert sips == 1
        assert "drinks 1 sip" in reason


def test_ace_spades_target_can_be_self(ace_clubs_flag):
    """When (idx + card_pos) % n == idx, the recipient targets themselves."""
    all_names = ["A", "B"]
    card = make_card("A", "S")
    # idx=0, card_pos=2 -> (0+2) % 2 == 0 -> self
    msgs = DrinkingRules.on_card_dealt(
        card, "A", 2, all_names, "A", ace_clubs_flag,
    )
    target_recv, sips, reason = msgs[0]
    assert target_recv == "A"


def test_ace_hearts_player_drinks_self(ace_clubs_flag):
    card = make_card("A", "H")
    msgs = DrinkingRules.on_card_dealt(
        card, "Alice", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
    )
    recipient, sips, reason = msgs[0]
    assert recipient == "Alice"
    assert sips == 1
    assert "drinks 1 sip" in reason


def test_ace_diamonds_dealer_drinks(ace_clubs_flag):
    card = make_card("A", "D")
    msgs = DrinkingRules.on_card_dealt(
        card, "Alice", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
    )
    assert len(msgs) == 1
    msg = msgs[0]
    recipient, sips, reason, role = msg
    assert recipient == "Bob"
    assert sips == 1
    assert role == "dealer"
    assert "(dealer) drinks 1 sip" in reason


# ---------------------------------------------------------------------------
# Dealer-hand aces (is_dealer_hand=True)
# ---------------------------------------------------------------------------

def test_ace_clubs_to_dealer_hand(ace_clubs_flag):
    card = make_card("A", "C")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
        is_dealer_hand=True,
    )
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient is None
    assert sips == 0
    assert ace_clubs_flag["half_protected"] is True
    assert "half Hard Switch protection" in reason


def test_ace_spades_dealer_hand_odd_pos(ace_clubs_flag):
    card = make_card("A", "S")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
        is_dealer_hand=True,
    )
    recipient, sips, reason, role = msgs[0]
    assert recipient == "Bob"
    assert sips == 1
    assert role == "dealer"
    assert "odd" in reason


def test_ace_spades_dealer_hand_even_pos(ace_clubs_flag):
    card = make_card("A", "S")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 2, ["Alice", "Bob"], "Bob", ace_clubs_flag,
        is_dealer_hand=True,
    )
    recipient, sips, reason = msgs[0]
    assert recipient == "all"
    assert sips == 1
    assert "even" in reason


def test_ace_hearts_dealer_hand_all_drink(ace_clubs_flag):
    card = make_card("A", "H")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
        is_dealer_hand=True,
    )
    recipient, sips, reason = msgs[0]
    assert recipient == "all"
    assert sips == 1


def test_ace_diamonds_dealer_hand_players_only(ace_clubs_flag):
    card = make_card("A", "D")
    msgs = DrinkingRules.on_card_dealt(
        card, "Bob", 1, ["Alice", "Bob"], "Bob", ace_clubs_flag,
        is_dealer_hand=True,
    )
    recipient, sips, reason = msgs[0]
    assert recipient == "players_only"
    assert sips == 1
