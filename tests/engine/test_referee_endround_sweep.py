"""
Regression test for RefereeSession.cmd_endround()'s all-hands sweep call
(engine/referee.py) -- the referee-mode ("physical cards") counterpart to
tests/app/test_game_engine.py's digital-mode version of the same bug.
"""

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand


def test_referee_all_hands_sweep_still_pays_dealer_on_hard_switch():
    """The Player All-Hand Bonus (Rules.md Sec 5.5) must stack with the Hard
    Dealer Switch payout. on_hard_dealer_switch() only tallies
    blackjack/doubled/regular wins -- nothing about all-21 or all-suited --
    so exempting the dealer from AllHandsSweepEvent during a hard switch (as
    the old code did) silently dropped the bonus whenever the sweeping
    player was the only other player (heads-up), since that always
    triggers a hard switch."""
    alice = make_player("Alice", hands=[
        make_hand(("9", "H"), ("7", "D"), ("5", "C"), result="win", stood=True),
        make_hand(("8", "S"), ("6", "H"), ("7", "C"), result="win", stood=True, from_split=True),
    ])
    bob = make_player("Bob", is_dealer=True,
                       dealer_hand=make_hand(("5", "S"), ("Q", "D")))

    session = RefereeSession([bob, alice], "Bob", wager=1, num_hands=2, verbose=False)
    session.cmd_endround()

    assert bob.drinks_owed() == 4   # 2 (Hard Switch: 2 regular wins) + 2 (all-21 sweep)
    reasons = [reason for _, reason, _ in bob.drink_log]
    assert any("Hard Dealer Switch" in r for r in reasons)
    assert any("all-hands sweep" in r for r in reasons)
