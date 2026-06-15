"""
tests/test_payout_tracker.py
=============================
Phase B (cash wager / bankroll) tests for Normal mode (drinking_mode=False,
mode="digital").

Covers:
- init_bankrolls seeds each player's starting bankroll
- apply_payouts: win (1:1), loss, push, blackjack (3:2) payout math
- multi-round bankroll persistence
- bank-run detection at $0 and cmd_rebuy resetting back to starting bankroll
- apply_payouts is a no-op in drinking mode / referee mode
"""

from engine.referee import RefereeSession
from app.models.game_room import GameRoom
from app.services.payout_tracker import init_bankrolls, apply_payouts, cmd_rebuy
from tests.conftest import make_player, make_hand


def _make_room(players, bet_amount=10, starting_bankroll=100,
                drinking_mode=False, mode="digital"):
    session = RefereeSession(players, players[0].name, wager=1, num_hands=1)
    room = GameRoom(
        session=session,
        mode=mode,
        drinking_mode=drinking_mode,
        bet_amount=bet_amount,
        starting_bankroll=starting_bankroll,
    )
    return room


def test_init_bankrolls_seeds_starting_balance():
    p1 = make_player("Alice")
    p2 = make_player("Bob")
    room = _make_room([p1, p2])

    init_bankrolls(room)

    assert room._bankrolls == {"Alice": 100, "Bob": 100}


def test_apply_payouts_win_loss_push_blackjack():
    p1 = make_player("Alice", hands=[make_hand(("10", "S"), ("9", "H"), result="win")])
    p2 = make_player("Bob",   hands=[make_hand(("10", "C"), ("8", "D"), result="loss")])
    p3 = make_player("Cara",  hands=[make_hand(("10", "H"), ("9", "S"), result="push")])
    p4 = make_player("Dana",  hands=[make_hand(("A", "S"), ("K", "H"), result="win")])  # blackjack
    room = _make_room([p1, p2, p3, p4], bet_amount=10, starting_bankroll=100)

    apply_payouts(room)

    assert room._bankrolls["Alice"] == 110     # +10 (1:1 win)
    assert room._bankrolls["Bob"]   == 90      # -10 (loss)
    assert room._bankrolls["Cara"]  == 100     # push, no change
    assert room._bankrolls["Dana"]  == 115     # +15 (blackjack 3:2)

    assert room._last_round_payouts == {"Alice": 10, "Bob": -10, "Dana": 15}


def test_apply_payouts_persists_across_rounds():
    p1 = make_player("Alice", hands=[make_hand(("10", "S"), ("9", "H"), result="win")])
    room = _make_room([p1], bet_amount=10, starting_bankroll=100)

    apply_payouts(room)
    assert room._bankrolls["Alice"] == 110

    # Round 2: another win
    p1.hands = [make_hand(("10", "S"), ("9", "H"), result="win")]
    apply_payouts(room)
    assert room._bankrolls["Alice"] == 120

    # Round 3: a loss
    p1.hands = [make_hand(("10", "C"), ("8", "D"), result="loss")]
    apply_payouts(room)
    assert room._bankrolls["Alice"] == 110


def test_biggest_round_payouts_tracked():
    p1 = make_player("Alice", hands=[make_hand(("A", "S"), ("K", "H"), result="win")])  # +15
    room = _make_room([p1], bet_amount=10, starting_bankroll=100)
    apply_payouts(room)

    p1.hands = [make_hand(("10", "C"), ("8", "D"), result="loss")]  # -10
    apply_payouts(room)

    assert room._biggest_round_payouts["Alice"]["best"] == 15
    assert room._biggest_round_payouts["Alice"]["worst"] == -10


def test_bank_run_detected_and_rebuy_resets():
    p1 = make_player("Alice", hands=[make_hand(("10", "C"), ("8", "D"), result="loss")])
    room = _make_room([p1], bet_amount=10, starting_bankroll=10)

    apply_payouts(room)
    assert room._bankrolls["Alice"] == 0
    assert "Alice" in room._bank_run_players

    ok = cmd_rebuy(room, "Alice")
    assert ok is True
    assert room._bankrolls["Alice"] == 10
    assert "Alice" not in room._bank_run_players

    # Re-buying a player who isn't in bank-run state is a no-op
    assert cmd_rebuy(room, "Alice") is False


def test_apply_payouts_noop_in_drinking_mode():
    p1 = make_player("Alice", hands=[make_hand(("10", "S"), ("9", "H"), result="win")])
    room = _make_room([p1], drinking_mode=True)

    apply_payouts(room)

    assert room._bankrolls == {}
    assert room._last_round_payouts == {}


def test_apply_payouts_noop_in_referee_mode():
    p1 = make_player("Alice", hands=[make_hand(("10", "S"), ("9", "H"), result="win")])
    room = _make_room([p1], drinking_mode=False, mode="referee")

    apply_payouts(room)

    assert room._bankrolls == {}
