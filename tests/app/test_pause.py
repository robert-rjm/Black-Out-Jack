"""Tests for app/services/pause.py: host pause freezes tick and shifts clocks on resume."""

import time

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand
from app.models.game_room import GameRoom, GameConfig
from app.services.pause import pause_game, resume_game, is_paused
from app.services.serializer import serialize_state
from app.services.tick import tick


def _room():
    players = [make_player(n, hands=[make_hand(("5", "S"), ("6", "H"))]) for n in ("Alice", "Bob")]
    room = GameRoom(session=RefereeSession(players, "Alice", wager=1, num_hands=1),
                    config=GameConfig(mode="digital", drinking_mode=False))
    room._room_clients = {"a": {"name": "Alice", "role": "admin", "local_names": ["Alice"]}}
    return room


def test_pause_is_idempotent():
    room = _room()
    assert pause_game(room) and is_paused(room)
    assert not pause_game(room)
    assert resume_game(room) and not is_paused(room)
    assert not resume_game(room)


def test_tick_does_not_expire_deadlines_while_paused():
    room = _room()
    room.round._bust_handout_expires_at = time.monotonic() - 1   # already expired
    pause_game(room)
    tick(room)
    assert room.round._bust_handout_expires_at is not None


def test_resume_shifts_clocks_by_paused_time():
    room = _room()
    now = time.monotonic()
    room.round._bust_vote_expires_at = now + 20
    room.round._pending_milestone = {"expires_at": now + 30}
    room.stats.session_started_at = now - 100
    pause_game(room)
    room._paused_at -= 50      # pretend we sat paused for 50s
    resume_game(room)
    assert 69 < room.round._bust_vote_expires_at - time.monotonic() < 71
    assert 79 < room.round._pending_milestone["expires_at"] - time.monotonic() < 81
    # session clock was at 100s when we paused 50s ago -> reads 50s (pause time excluded)
    assert 49 < time.monotonic() - room.stats.session_started_at < 51


def test_duration_frozen_while_paused():
    room = _room()
    room.stats.session_started_at = time.monotonic() - 10
    pause_game(room)
    room._paused_at -= 30   # paused 30s ago, so the clock should read ~-20 -> clamped
    s = serialize_state(room, "a")
    assert s["paused"] is True
    assert s["kpi_stats"]["session"]["session_seconds"] == 0
