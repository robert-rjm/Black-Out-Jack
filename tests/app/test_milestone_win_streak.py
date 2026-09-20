"""
Tests for app/services/drink_tracker.py's back-to-back milestone run --
the log callout a player earns by winning AND handing out two (or more)
milestones in a row (note_milestone_assigned). Only real handouts keep a
run alive: a forfeited window or a solo winner with nobody to give to
breaks it.
"""

import time

from engine.referee import RefereeSession
from tests.conftest import make_player
from app.models.game_room import GameRoom, GameConfig
from app.services.serializer import serialize_state
from app.services.drink_tracker import (
    apply_milestone_forfeit,
    note_milestone_assigned,
    _distribute_milestone_round_robin,
)

FIRE = "🔥"


def _make_room(num_players=3, npc_names=()):
    """Minimal GameRoom with num_players players (Alice is dealer) -- same
    shape as test_award_sips_round_avg.py's own _make_room."""
    names   = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n, is_npc=(n in npc_names)) for n in names]
    players[0].is_dealer = True
    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    return GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=True))


def _fire_lines(room):
    return [e for e in room.round._log_entries if FIRE in e]


# ---------------------------------------------------------------------------
# note_milestone_assigned: the run itself
# ---------------------------------------------------------------------------

def test_single_handout_logs_nothing():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    assert room.drinks.milestone_win_streak == 1
    assert _fire_lines(room) == []


def test_two_in_a_row_logs_back_to_back():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "Bob")

    assert room.drinks.milestone_win_streak == 2
    lines = _fire_lines(room)
    assert len(lines) == 1
    assert "Bob" in lines[0] and "back-to-back" in lines[0]


def test_third_in_a_row_counts_the_run():
    room = _make_room()
    for _ in range(3):
        note_milestone_assigned(room, "Bob")

    assert room.drinks.milestone_win_streak == 3
    assert "3 milestones in a row" in _fire_lines(room)[-1]


def test_different_winner_breaks_the_run():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "Carol")

    assert room.drinks.last_milestone_winner == "Carol"
    assert room.drinks.milestone_win_streak == 1
    assert _fire_lines(room) == []


def test_run_is_case_insensitive():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "bob")
    assert room.drinks.milestone_win_streak == 2
    assert len(_fire_lines(room)) == 1


def test_log_version_bumps_only_when_logged():
    room = _make_room()
    before = room._log_version
    note_milestone_assigned(room, "Bob")
    assert room._log_version == before
    note_milestone_assigned(room, "Bob")
    assert room._log_version == before + 1


# ---------------------------------------------------------------------------
# What breaks a run
# ---------------------------------------------------------------------------

def test_forfeit_breaks_the_run():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    room.round._pending_milestone = {
        "boundary": 100, "winner": "Bob", "handout": 6,
        "expires_at": time.monotonic() - 1,      # already closed
    }
    apply_milestone_forfeit(room)

    assert room.drinks.last_milestone_winner is None
    assert room.drinks.milestone_win_streak == 0

    # The next win starts over rather than landing as back-to-back.
    note_milestone_assigned(room, "Bob")
    assert _fire_lines(room) == []


def test_solo_npc_winner_breaks_the_run():
    """Nobody to hand out to -- the winner just drinks it, so it is not a
    handout and cannot extend a run."""
    room = _make_room(num_players=1, npc_names=("Alice",))
    note_milestone_assigned(room, "Alice")
    _distribute_milestone_round_robin(room, "Alice", 50, 5)

    assert room.drinks.last_milestone_winner is None
    assert room.drinks.milestone_win_streak == 0
    assert _fire_lines(room) == []


# ---------------------------------------------------------------------------
# NPC round-robin handouts count
# ---------------------------------------------------------------------------

def test_npc_round_robin_handouts_build_a_run():
    room = _make_room(npc_names=("Bob",))
    _distribute_milestone_round_robin(room, "Bob", 50, 5)
    assert _fire_lines(room) == []

    _distribute_milestone_round_robin(room, "Bob", 100, 6)
    lines = _fire_lines(room)
    assert len(lines) == 1
    assert "back-to-back" in lines[0]
    assert room.drinks.milestone_win_streak == 2


# ---------------------------------------------------------------------------
# What the seat badge reads
# ---------------------------------------------------------------------------

def test_run_not_serialized_until_it_is_a_run():
    """One handout is not a run -- no badge."""
    room = _make_room()
    note_milestone_assigned(room, "Bob")

    state = serialize_state(room, "client-1")
    assert state["milestone_run_holder"] is None
    assert state["milestone_run_length"] == 0


def test_run_serialized_for_the_seat_badge():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "Bob")

    state = serialize_state(room, "client-1")
    assert state["milestone_run_holder"] == "Bob"
    assert state["milestone_run_length"] == 2


def test_broken_run_clears_the_seat_badge():
    room = _make_room()
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "Bob")
    note_milestone_assigned(room, "Carol")

    state = serialize_state(room, "client-1")
    assert state["milestone_run_holder"] is None
    assert state["milestone_run_length"] == 0
