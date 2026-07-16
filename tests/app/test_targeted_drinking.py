"""
Tests for Targeted Drinking Mode (docs/planning/TargetedDrinkingMode.md,
MVP scope): app/services/targeted_drinking.py.
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand
from app.models.game_room import GameRoom, GameConfig
from app.services.targeted_drinking import (
    start_targeted_drinking,
    maybe_open_targeted_drinking_vote,
    submit_targeted_drinking_vote,
    apply_targeted_drinking_vote_forfeit,
    resolve_targeted_drinking_round,
    end_targeted_drinking,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(num_players=3, dealer_hand=None):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    room = GameRoom(session=raw_session, config=GameConfig(mode="digital"))
    return room


# ---------------------------------------------------------------------------
# start_targeted_drinking
# ---------------------------------------------------------------------------

def test_start_fails_with_no_targets():
    room = _make_room()
    assert start_targeted_drinking(room, []) is False
    assert room._targeted_drinking_active is False


def test_start_fails_for_unknown_player():
    room = _make_room()
    assert start_targeted_drinking(room, ["Nobody"]) is False
    assert room._targeted_drinking_active is False


def test_start_succeeds_and_zeroes_streaks():
    room = _make_room()
    assert start_targeted_drinking(room, ["Bob", "Carol"]) is True
    assert room._targeted_drinking_active is True
    assert room._targeted_drinking_targets == ["Bob", "Carol"]
    assert room._targeted_drinking_streaks == {"Bob": 0, "Carol": 0}


def test_start_is_case_insensitive_on_names():
    room = _make_room()
    assert start_targeted_drinking(room, ["bob"]) is True


def test_start_fails_if_already_active():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert start_targeted_drinking(room, ["Carol"]) is False
    # Original subgame untouched
    assert room._targeted_drinking_targets == ["Bob"]


def test_start_fails_during_cooldown():
    room = _make_room()
    room._targeted_drinking_cooldown_until_round = 5
    room.session.round_count = 2
    assert start_targeted_drinking(room, ["Bob"]) is False


def test_start_succeeds_once_cooldown_elapsed():
    room = _make_room()
    room._targeted_drinking_cooldown_until_round = 5
    room.session.round_count = 5
    assert start_targeted_drinking(room, ["Bob"]) is True


# ---------------------------------------------------------------------------
# maybe_open_targeted_drinking_vote
# ---------------------------------------------------------------------------

def test_maybe_open_vote_noop_when_inactive():
    room = _make_room()
    maybe_open_targeted_drinking_vote(room)
    assert room.round._targeted_drinking_expires_at is None


def test_maybe_open_vote_sets_expiry_once():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    maybe_open_targeted_drinking_vote(room)
    first_expiry = room.round._targeted_drinking_expires_at
    assert first_expiry is not None and first_expiry > time.monotonic()

    # Calling again before the window closes must not reset the countdown
    maybe_open_targeted_drinking_vote(room)
    assert room.round._targeted_drinking_expires_at == first_expiry


# ---------------------------------------------------------------------------
# submit_targeted_drinking_vote
# ---------------------------------------------------------------------------

def test_submit_vote_rejects_non_target():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Carol", "bust") is False
    assert "Carol" not in room.round._targeted_drinking_votes


def test_submit_vote_rejects_invalid_value():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "maybe") is False


def test_submit_vote_records_valid_vote():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "bust") is True
    assert room.round._targeted_drinking_votes["Bob"] == "bust"


# ---------------------------------------------------------------------------
# resolve_targeted_drinking_round
# ---------------------------------------------------------------------------

def test_resolve_noop_if_not_active():
    room = _make_room()
    resolve_targeted_drinking_round(room)  # must not raise
    assert room._targeted_drinking_streaks == {}


def test_resolve_noop_if_no_dealer_hand():
    room = _make_room(dealer_hand=make_hand())
    room._get_dealer().dealer_hand = None
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")
    resolve_targeted_drinking_round(room)
    # No crash, and nothing resolved (streak untouched)
    assert room._targeted_drinking_streaks == {"Bob": 0}


def test_resolve_correct_guess_increments_streak_without_graduating():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # 25 -> bust
    room = _make_room(dealer_hand=busted_hand)
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # correct: dealer busted
    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert "Bob" in room._targeted_drinking_targets   # not graduated yet (needs 3)
    assert room._targeted_drinking_active is True
    bob = room._get_player("Bob")
    assert bob.drink_log == []   # no sip awarded on a correct guess


def test_resolve_wrong_guess_resets_streak_and_awards_sip():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    room._targeted_drinking_streaks["Bob"] = 2   # pretend they were on a streak
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong: dealer stood

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 0
    assert "Bob" in room._targeted_drinking_targets   # still targeted
    assert room.drinks.last_round_sips["Bob"] == 1
    assert room.drinks.last_round_drinks[-1]["reason"].startswith(
        "Targeted Drinking: guessed bust, dealer stood"
    )


def test_resolve_graduates_after_streak_threshold_and_ends_subgame():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])

    for _ in range(3):
        submit_targeted_drinking_vote(room, "Bob", "stand")  # correct each time
        resolve_targeted_drinking_round(room)
        room.round._targeted_drinking_votes.clear()   # simulate a fresh round's votes

    assert room._targeted_drinking_active is False   # subgame ended: everyone graduated
    assert room._targeted_drinking_targets == []
    assert room._targeted_drinking_cooldown_until_round == room.session.round_count + 3


def test_resolve_unanswered_vote_defaults_to_stand():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    # No vote submitted at all -- resolve_targeted_drinking_round itself
    # treats a missing vote as "stand" (apply_targeted_drinking_vote_forfeit
    # additionally writes this into the votes dict before resolving).
    resolve_targeted_drinking_round(room)
    assert room._targeted_drinking_streaks["Bob"] == 1   # "stand" was correct


def test_resolve_only_targets_still_in_subgame_are_scored():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(num_players=3, dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob", "Carol"])
    submit_targeted_drinking_vote(room, "Bob", "stand")   # correct
    submit_targeted_drinking_vote(room, "Carol", "bust")  # wrong

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert room._targeted_drinking_streaks["Carol"] == 0
    assert "Bob" in room._targeted_drinking_targets
    assert "Carol" in room._targeted_drinking_targets
    assert room.drinks.last_round_sips.get("Bob") is None
    assert room.drinks.last_round_sips["Carol"] == 1


# ---------------------------------------------------------------------------
# apply_targeted_drinking_vote_forfeit
# ---------------------------------------------------------------------------

def test_forfeit_noop_before_expiry():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    room.round._targeted_drinking_expires_at = time.monotonic() + 100
    apply_targeted_drinking_vote_forfeit(room)
    assert room._targeted_drinking_streaks["Bob"] == 0   # unresolved, unchanged
    assert room.round._targeted_drinking_votes == {}


def test_forfeit_noop_when_no_window_open():
    room = _make_room()
    apply_targeted_drinking_vote_forfeit(room)  # must not raise with no window at all


def test_forfeit_defaults_unanswered_votes_and_resolves():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    room.round._targeted_drinking_expires_at = time.monotonic() - 1   # already expired

    apply_targeted_drinking_vote_forfeit(room)

    assert room.round._targeted_drinking_votes["Bob"] == "stand"
    assert room._targeted_drinking_streaks["Bob"] == 1   # defaulted "stand" was correct


def test_forfeit_does_not_override_an_explicit_vote():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # bust
    room = _make_room(dealer_hand=busted_hand)
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # explicit, correct
    room.round._targeted_drinking_expires_at = time.monotonic() - 1

    apply_targeted_drinking_vote_forfeit(room)

    assert room.round._targeted_drinking_votes["Bob"] == "bust"
    assert room._targeted_drinking_streaks["Bob"] == 1


# ---------------------------------------------------------------------------
# end_targeted_drinking
# ---------------------------------------------------------------------------

def test_end_clears_state_and_sets_cooldown():
    room = _make_room()
    start_targeted_drinking(room, ["Bob", "Carol"])
    room.session.round_count = 10

    end_targeted_drinking(room, reason="admin_cancelled")

    assert room._targeted_drinking_active is False
    assert room._targeted_drinking_targets == []
    assert room._targeted_drinking_streaks == {}
    assert room._targeted_drinking_cooldown_until_round == 13


def test_end_is_idempotent():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    room.session.round_count = 10
    end_targeted_drinking(room, reason="admin_cancelled")
    cooldown_after_first_end = room._targeted_drinking_cooldown_until_round

    room.session.round_count = 999   # would produce a different cooldown if re-applied
    end_targeted_drinking(room, reason="admin_cancelled")
    assert room._targeted_drinking_cooldown_until_round == cooldown_after_first_end
