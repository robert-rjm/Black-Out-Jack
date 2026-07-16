"""
Tests for the registration/seat-transfer registry lock
(docs/planning/Code-Audit-2026-07.md #4):
  - GameRoom._registry_lock exists and guards /register, /request_local_seat,
    /handle_registration, /handle_seat_transfer (app/routes/polling.py).

Two concurrent requests for the same room used to be able to both pass a
"is this seat/request already claimed?" check before either write landed
(a classic check-then-mutate race). The actual vulnerable window is a
handful of pure-Python dict operations with no I/O in between, so it can't
be forced to interleave deterministically without an artificial delay --
these tests add one (via a patched serialize_state, which now runs *inside*
the locked section) and prove mutual exclusion by wall-clock time: if two
concurrent requests are each individually slowed by `DELAY` seconds and the
lock genuinely serializes them, total elapsed time is ~2x DELAY; if they
ran concurrently instead, it would be ~1x DELAY regardless of how many
requests overlap. This is a stronger and more reliable signal than trying
to catch the original race red-handed, which the GIL makes too rare to
trigger reliably in a plain scheduling test.
"""

import threading
import time as _time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player
from app import create_app
from app.models.game_room import GameRoom, GameConfig
from app.services.session_store import game_sessions, set_session
import app.routes.polling as polling_mod

DELAY = 0.2


def _make_room(num_players=2):
    names = ["Alice", "Bob", "Carol"][:num_players]
    players = [make_player(n) for n in names]
    raw_session = RefereeSession(players, names[0], wager=1, num_hands=1)
    return GameRoom(session=raw_session, config=GameConfig(mode="digital"))


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def slow_serialize(monkeypatch):
    """Make every serialize_state call (which now runs inside
    session._registry_lock, at the tail of each guarded route) sleep for
    DELAY seconds -- see module docstring for why this proves mutual
    exclusion via wall-clock time rather than trying to catch the race."""
    real_serialize = polling_mod.serialize_state

    def _slow(*args, **kwargs):
        _time.sleep(DELAY)
        return real_serialize(*args, **kwargs)

    monkeypatch.setattr(polling_mod, "serialize_state", _slow)


def test_registry_lock_is_a_real_lock():
    room = _make_room()
    assert isinstance(room._registry_lock, type(threading.Lock()))


def test_register_calls_for_the_same_room_are_serialized(client, slow_serialize):
    """Two /register calls for different seats in the same room must not
    overlap: session._registry_lock is acquired for the whole route body,
    so two individually-slowed calls take ~2x DELAY in total, not ~1x."""
    room_code = "RaceRoom1"
    room = _make_room(num_players=2)   # Alice, Bob -- both unclaimed
    set_session(room_code, room)

    results = {}

    def claim(client_id, name):
        resp = client.post("/register", json={
            "room_code": room_code, "client_id": client_id, "name": name,
        })
        results[client_id] = resp.get_json()

    try:
        t1 = threading.Thread(target=claim, args=("client-A", "Alice"))
        t2 = threading.Thread(target=claim, args=("client-B", "Bob"))
        start = _time.monotonic()
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        elapsed = _time.monotonic() - start

        assert results["client-A"]["ok"] is True
        assert results["client-B"]["ok"] is True
        # Serialized: ~2x DELAY. Concurrent (no lock): ~1x DELAY. Use the
        # midpoint as the threshold so normal scheduling jitter can't flip it.
        assert elapsed >= 1.5 * DELAY
    finally:
        game_sessions.pop(room_code, None)


def test_handle_registration_serializes_and_prevents_double_claim(client, slow_serialize):
    """The original bug shape: two pending requests for the same unclaimed
    seat 'Alice' (nothing stops two different pending entries naming the
    same seat -- /register only rejects a name already held by an *approved*
    player), each approved concurrently by the admin. Without serialization,
    both approvals could read 'seat unclaimed' before either writes it,
    letting both claim it. With the lock: ~2x DELAY total elapsed (proving
    they ran one at a time) AND exactly one ends up holding the seat."""
    room_code = "RaceRoom2"
    room = _make_room(num_players=3)   # Alice, Bob, Carol
    room._room_clients["admin-1"] = {"name": "Carol", "role": "admin", "kicked": False}
    room._pending_registrations = [
        {"client_id": "client-X", "name": "Alice"},
        {"client_id": "client-Y", "name": "Alice"},
    ]
    set_session(room_code, room)

    results = {}

    def approve(target_client_id):
        resp = client.post("/handle_registration", json={
            "room_code": room_code, "client_id": "admin-1",
            "target_client_id": target_client_id, "approve": True,
        })
        results[target_client_id] = resp.get_json()

    try:
        t1 = threading.Thread(target=approve, args=("client-X",))
        t2 = threading.Thread(target=approve, args=("client-Y",))
        start = _time.monotonic()
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        elapsed = _time.monotonic() - start

        assert elapsed >= 1.5 * DELAY   # proves the two approvals were serialized
        assert results["client-X"]["ok"] is True
        assert results["client-Y"]["ok"] is True

        claimants = [c for c in room._room_clients.values()
                     if (c.get("name") or "").lower() == "alice"]
        assert len(claimants) == 1   # never both, regardless of scheduling order
    finally:
        game_sessions.pop(room_code, None)
