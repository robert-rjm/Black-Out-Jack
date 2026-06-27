"""
Tests for DrinkingRules.on_round_end — engine/drinking_rules.py

Covers both the dealer_bj (auto-insurance) branch and the normal branch
(net losses, doubled/suited losses, split-win immunity break,
other-player-wins-all).
"""

import pytest

from engine.drinking_rules import DrinkingRules
from tests.conftest import make_hand, make_player


def _msgs_for(messages, player_name, substring=None):
    out = [m for m in messages if m[0] == player_name]
    if substring is not None:
        out = [m for m in out if substring in m[2]]
    return out


# ---------------------------------------------------------------------------
# dealer_bj branch
# ---------------------------------------------------------------------------

def test_dealer_bj_num_hands_fallback_counts_nonsplit_hands():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1, dealer_bj=True, num_hands=0)
    assert len(msgs) == 1
    recipient, sips, reason = msgs[0]
    assert recipient == "Alice"
    assert sips == 2  # 2 non-split hands * wager 1
    assert "auto-insurance" in reason


def test_dealer_bj_pushes_reduce_charge():
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="push"),  # BJ push
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1, dealer_bj=True, num_hands=0)
    assert len(msgs) == 1
    assert msgs[0][1] == 1  # base=2, bj_pushes=1 -> starting_losses=1


def test_dealer_bj_starting_losses_zero_no_message():
    p = make_player("Alice", hands=[
        make_hand(("A", "H"), ("K", "D"), result="push"),
        make_hand(("A", "S"), ("K", "C"), result="push"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1, dealer_bj=True, num_hands=0)
    assert msgs == []


def test_dealer_bj_hard_switch_dealer_excluded():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end(
        [p], wager=1, dealer_bj=True, num_hands=0, hard_switch_dealer="Alice"
    )
    assert msgs == []


def test_dealer_bj_splits_do_not_reduce_charge():
    """Player started with 2 hands (num_hands=2), split one into 2 -> 3 total.
    Charge is still based on num_hands, not the post-split hand count."""
    p = make_player("Alice", hands=[
        make_hand(("8", "S"), ("8", "H"), result="loss", from_split=True),
        make_hand(("8", "S"), ("9", "H"), result="loss", from_split=True),
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1, dealer_bj=True, num_hands=2)
    assert len(msgs) == 1
    assert msgs[0][1] == 2  # num_hands=2, no BJ pushes


# ---------------------------------------------------------------------------
# normal branch — net losses
# ---------------------------------------------------------------------------

def test_net_losses_positive_fires_message():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
        make_hand(("Q", "S"), ("8", "H"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1)
    net_msgs = _msgs_for(msgs, "Alice", "net loss")
    assert len(net_msgs) == 1
    assert net_msgs[0][1] == 2


def test_net_losses_zero_no_message():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
        make_hand(("7", "S"), ("8", "H"), result="win"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1)
    assert _msgs_for(msgs, "Alice", "net loss") == []


# ---------------------------------------------------------------------------
# normal branch — doubled / suited losses
# ---------------------------------------------------------------------------

def test_lost_doubled_hand_extra_sip():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "H"), doubled=True, result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1)
    doubled_msgs = _msgs_for(msgs, "Alice", "lost a doubled hand")
    assert len(doubled_msgs) == 1
    assert doubled_msgs[0][1] == 1


def test_lost_suited_hand_extra_sip():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "S"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=1)
    suited_msgs = _msgs_for(msgs, "Alice", "lost a suited hand")
    assert len(suited_msgs) == 1
    assert suited_msgs[0][1] == 1


def test_lost_doubled_and_suited_hand_stacks_two_messages():
    p = make_player("Alice", hands=[
        make_hand(("K", "S"), ("9", "S"), doubled=True, result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([p], wager=2)
    doubled_msgs = _msgs_for(msgs, "Alice", "lost a doubled hand")
    suited_msgs = _msgs_for(msgs, "Alice", "lost a suited hand")
    assert len(doubled_msgs) == 1
    assert len(suited_msgs) == 1
    assert doubled_msgs[0][1] == 2
    assert suited_msgs[0][1] == 2


# ---------------------------------------------------------------------------
# normal branch — split wins break immunity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("split_wins,expected_sips", [(0, 0), (1, 0), (2, 1), (3, 2)])
def test_split_wins_break_immunity(split_wins, expected_sips):
    winner_hands = [
        make_hand(("2", "H"), ("3", "D"), result="win", from_split=True)
        for _ in range(split_wins)
    ]
    if not winner_hands:
        # need at least one hand so net_losses()/round_* don't error oddly
        winner_hands = [make_hand(("2", "H"), ("3", "D"), result="win")]
    winner = make_player("Winner", hands=winner_hands)
    other = make_player("Other", hands=[make_hand(("4", "H"), ("5", "D"), result="win")])

    msgs = DrinkingRules.on_round_end([winner, other], wager=1)
    split_msgs = [m for m in msgs if "split hand" in m[2]]

    if expected_sips == 0:
        assert split_msgs == []
    else:
        assert len(split_msgs) == 1
        recipient, sips, reason = split_msgs[0]
        assert recipient == "Other"
        assert sips == expected_sips


def test_split_win_message_excludes_hard_switch_dealer():
    winner_hands = [
        make_hand(("2", "H"), ("3", "D"), result="win", from_split=True)
        for _ in range(2)
    ]
    winner = make_player("Winner", hands=winner_hands)
    dealer = make_player("Dealer", hands=[make_hand(("4", "H"), ("5", "D"), result="win")])
    msgs = DrinkingRules.on_round_end([winner, dealer], wager=1, hard_switch_dealer="Dealer")
    split_msgs = [m for m in msgs if "split hand" in m[2]]
    assert split_msgs == []


# ---------------------------------------------------------------------------
# normal branch — other-player-wins-all
# ---------------------------------------------------------------------------

def test_sweep_other_immune_when_no_losses_or_pushes():
    winner = make_player("Winner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    other = make_player("Other", hands=[
        make_hand(("2", "H"), ("3", "D"), result="win"),
    ])
    msgs = DrinkingRules.on_round_end([winner, other], wager=1)
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2]]
    assert sweep_msgs == []


def test_sweep_other_zero_pushes_diff_can_be_zero():
    """other has 0 losses, >0 pushes, w_wins - o_wins == 0 -> no message."""
    winner = make_player("Winner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
    ])
    other = make_player("Other", hands=[
        make_hand(("2", "H"), ("3", "D"), result="win"),
        make_hand(("4", "H"), ("5", "D"), result="push"),
    ])
    msgs = DrinkingRules.on_round_end([winner, other], wager=1)
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2]]
    assert sweep_msgs == []


def test_sweep_other_zero_pushes_positive_diff():
    """other has 0 losses, >0 pushes, w_wins > o_wins -> sips = w_wins - o_wins."""
    winner = make_player("Winner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    other = make_player("Other", hands=[
        make_hand(("2", "H"), ("3", "D"), result="win"),
        make_hand(("4", "H"), ("5", "D"), result="push"),
    ])
    msgs = DrinkingRules.on_round_end([winner, other], wager=1)
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2] and m[0] == "Other"]
    assert len(sweep_msgs) == 1
    assert sweep_msgs[0][1] == 1  # 2 - 1


def test_sweep_other_has_losses_sips_equals_winner_wins():
    winner = make_player("Winner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    other = make_player("Other", hands=[
        make_hand(("2", "H"), ("3", "D"), result="loss"),
        make_hand(("4", "H"), ("5", "D"), result="win"),
        make_hand(("6", "H"), ("7", "D"), result="win"),
    ])
    msgs = DrinkingRules.on_round_end([winner, other], wager=1)
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2] and m[0] == "Other"]
    assert len(sweep_msgs) == 1
    assert sweep_msgs[0][1] == 2  # w_wins, regardless of o_wins/o_pushes


def test_sweep_winner_with_loss_or_push_does_not_fire():
    not_winner = make_player("NotWinner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("2", "H"), ("3", "D"), result="loss"),
    ])
    other = make_player("Other", hands=[
        make_hand(("4", "H"), ("5", "D"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([not_winner, other], wager=1)
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2] and m[0] == "Other"]
    assert sweep_msgs == []


def test_sweep_excludes_hard_switch_dealer_as_other():
    winner = make_player("Winner", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("A", "S"), ("K", "C"), result="win"),
    ])
    dealer = make_player("Dealer", hands=[
        make_hand(("2", "H"), ("3", "D"), result="loss"),
    ])
    msgs = DrinkingRules.on_round_end([winner, dealer], wager=1, hard_switch_dealer="Dealer")
    sweep_msgs = [m for m in msgs if "swept all hands" in m[2] and m[0] == "Dealer"]
    assert sweep_msgs == []


# ---------------------------------------------------------------------------
# all-excluded edge case
# ---------------------------------------------------------------------------

def test_two_player_hard_switch_dealer_graceful_empty():
    dealer = make_player("Dealer", hands=[
        make_hand(("K", "S"), ("9", "H"), result="loss"),
    ])
    other = make_player("Other", hands=[
        make_hand(("A", "H"), ("K", "D"), result="win"),
    ])
    # dealer is the only "winner"-eligible loser; hard_switch_dealer excludes them
    msgs = DrinkingRules.on_round_end([dealer, other], wager=1, hard_switch_dealer="Dealer")
    # Dealer excluded entirely from net-loss/doubled/suited/split/sweep checks
    assert _msgs_for(msgs, "Dealer") == []
