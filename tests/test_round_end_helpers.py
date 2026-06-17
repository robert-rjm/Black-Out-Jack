"""
Direct unit tests for the private DrinkingRules.on_round_end helpers
extracted in M8: _net_loss_drinks, _dealer_bj_drinks, _extra_loss_drinks,
_split_win_drinks, _wins_all_drinks.

These are @staticmethods on DrinkingRules so no session is needed.
The on_round_end integration is already covered by
test_drinking_rules_round_end.py — these tests focus on the helpers
in isolation, especially the BJ=2-wins house rule moved here from
Player.net_losses() in L11.
"""

import pytest

from engine.drinking_rules import DrinkingRules
from tests.conftest import make_hand, make_player


# ---------------------------------------------------------------------------
# _net_loss_drinks — BJ multiplier (moved from Player.net_losses in L11)
# ---------------------------------------------------------------------------

def test_net_loss_bj_offsets_two_losses():
    """BJ win counts as 2 effective wins -> offsets two losses -> net 0."""
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),   # BJ
        make_hand(("5", "S"), ("9", "H"), result="loss"),
        make_hand(("6", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules._net_loss_drinks([p], wager=1, hard_switch_dealer="")
    assert msgs == []


def test_net_loss_bj_does_not_offset_three_losses():
    """BJ = 2 effective wins; three losses still leaves net 1."""
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),   # BJ
        make_hand(("5", "S"), ("9", "H"), result="loss"),
        make_hand(("6", "S"), ("8", "H"), result="loss"),
        make_hand(("7", "S"), ("2", "H"), result="loss"),
    ])
    msgs = DrinkingRules._net_loss_drinks([p], wager=1, hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][1] == 1   # 3 losses - 2 effective = net 1


def test_net_loss_regular_win_counts_as_one():
    """Non-BJ win offsets only one loss."""
    p = make_player("Alice", hands=[
        make_hand(("K", "H"), ("Q", "D"), result="win"),   # plain win
        make_hand(("5", "S"), ("9", "H"), result="loss"),
        make_hand(("6", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules._net_loss_drinks([p], wager=1, hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][1] == 1   # 2 losses - 1 win = net 1


def test_net_loss_wager_scales_sips():
    p = make_player("Alice", hands=[
        make_hand(("5", "S"), ("9", "H"), result="loss"),
        make_hand(("6", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules._net_loss_drinks([p], wager=3, hard_switch_dealer="")
    assert msgs[0][1] == 6   # 2 net losses * wager 3


def test_net_loss_hard_switch_dealer_excluded():
    p = make_player("Alice", hands=[
        make_hand(("5", "S"), ("9", "H"), result="loss"),
    ])
    msgs = DrinkingRules._net_loss_drinks([p], wager=1, hard_switch_dealer="Alice")
    assert msgs == []


def test_net_loss_multiple_players_independent():
    alice = make_player("Alice", hands=[make_hand(("5", "S"), ("9", "H"), result="loss")])
    bob   = make_player("Bob",   hands=[make_hand(("K", "H"), ("Q", "D"), result="win")])
    msgs = DrinkingRules._net_loss_drinks([alice, bob], wager=1, hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][0] == "Alice"


# ---------------------------------------------------------------------------
# _dealer_bj_drinks
# ---------------------------------------------------------------------------

def test_dealer_bj_basic_charge():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules._dealer_bj_drinks([p], wager=1, num_hands=2, hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][1] == 2


def test_dealer_bj_push_reduces_charge():
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="push"),  # BJ push
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules._dealer_bj_drinks([p], wager=1, num_hands=0, hard_switch_dealer="")
    assert msgs[0][1] == 1   # base 2 - 1 bj_push = 1


def test_dealer_bj_all_pushes_no_message():
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="push"),
        make_hand(("A", "S"), ("K", "C"), result="push"),
    ])
    msgs = DrinkingRules._dealer_bj_drinks([p], wager=1, num_hands=0, hard_switch_dealer="")
    assert msgs == []


def test_dealer_bj_excluded_player_skipped():
    p = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "H"), result="loss")])
    msgs = DrinkingRules._dealer_bj_drinks([p], wager=1, num_hands=1, hard_switch_dealer="Alice")
    assert msgs == []


# ---------------------------------------------------------------------------
# _extra_loss_drinks
# ---------------------------------------------------------------------------

def test_extra_loss_doubled_fires():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), doubled=True, result="loss"),
    ])
    msgs = DrinkingRules._extra_loss_drinks([p], wager=2, hard_switch_dealer="")
    assert any("doubled" in m[2] for m in msgs)
    assert msgs[0][1] == 2


def test_extra_loss_suited_fires():
    p = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "S"), result="loss")])
    msgs = DrinkingRules._extra_loss_drinks([p], wager=1, hard_switch_dealer="")
    assert any("suited" in m[2] for m in msgs)


def test_extra_loss_win_does_not_fire():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "S"), doubled=True, result="win"),
    ])
    msgs = DrinkingRules._extra_loss_drinks([p], wager=1, hard_switch_dealer="")
    assert msgs == []


def test_extra_loss_excluded_player_skipped():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "S"), doubled=True, result="loss"),
    ])
    msgs = DrinkingRules._extra_loss_drinks([p], wager=1, hard_switch_dealer="Alice")
    assert msgs == []


# ---------------------------------------------------------------------------
# _split_win_drinks
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("split_wins,expected_sips", [(0, 0), (1, 0), (2, 1), (3, 2)])
def test_split_win_sips_formula(split_wins, expected_sips):
    """sips = max(0, split_wins - 1)."""
    winner_hands = [
        make_hand(("7", "H"), ("8", "D"), result="win", from_split=True)
        for _ in range(split_wins)
    ] or [make_hand(("7", "H"), ("8", "D"), result="win")]
    winner = make_player("Winner", hands=winner_hands)
    other  = make_player("Other",  hands=[make_hand(("4", "H"), ("5", "D"), result="loss")])

    msgs = DrinkingRules._split_win_drinks([winner, other], hard_switch_dealer="")
    split_msgs = [m for m in msgs if m[0] == "Other"]
    if expected_sips == 0:
        assert split_msgs == []
    else:
        assert split_msgs[0][1] == expected_sips


def test_split_win_excluded_not_charged():
    winner = make_player("Winner", hands=[
        make_hand(("7", "H"), ("8", "D"), result="win", from_split=True),
        make_hand(("7", "S"), ("9", "D"), result="win", from_split=True),
    ])
    dealer = make_player("Dealer", hands=[make_hand(("4", "H"), ("5", "D"), result="loss")])
    msgs = DrinkingRules._split_win_drinks([winner, dealer], hard_switch_dealer="Dealer")
    assert msgs == []


# ---------------------------------------------------------------------------
# _wins_all_drinks
# ---------------------------------------------------------------------------

def test_wins_all_winner_with_loss_suppressed():
    not_winner = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("5", "S"), ("6", "H"), result="loss"),
    ])
    other = make_player("Bob", hands=[make_hand(("2", "H"), ("3", "D"), result="loss")])
    msgs = DrinkingRules._wins_all_drinks([not_winner, other], hard_switch_dealer="")
    assert msgs == []


def test_wins_all_pure_winner_other_immune():
    """Other with no losses/pushes is fully immune."""
    winner = make_player("Alice", hands=[make_hand(("A", "H"), ("K", "D"), result="win")])
    other  = make_player("Bob",   hands=[make_hand(("A", "S"), ("K", "C"), result="win")])
    msgs = DrinkingRules._wins_all_drinks([winner, other], hard_switch_dealer="")
    assert msgs == []


def test_wins_all_other_with_losses_drinks_winner_wins():
    winner = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    other = make_player("Bob", hands=[make_hand(("5", "S"), ("6", "H"), result="loss")])
    msgs = DrinkingRules._wins_all_drinks([winner, other], hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][0] == "Bob"
    assert msgs[0][1] == 2   # w_wins = 2


def test_wins_all_other_zero_losses_partial_sips():
    """Other with pushes but no losses: sips = max(0, w_wins - o_wins)."""
    winner = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    other = make_player("Bob", hands=[
        make_hand(("2", "H"), ("3", "D"), result="win"),
        make_hand(("4", "H"), ("5", "D"), result="push"),
    ])
    msgs = DrinkingRules._wins_all_drinks([winner, other], hard_switch_dealer="")
    assert len(msgs) == 1
    assert msgs[0][1] == 1   # 2 - 1


def test_wins_all_excluded_not_charged():
    winner = make_player("Alice", hands=[make_hand(("A", "H"), ("K", "D"), result="win")])
    dealer = make_player("Dealer", hands=[make_hand(("5", "S"), ("6", "H"), result="loss")])
    msgs = DrinkingRules._wins_all_drinks([winner, dealer], hard_switch_dealer="Dealer")
    assert msgs == []
