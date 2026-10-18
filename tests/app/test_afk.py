"""
Tests for app/services/afk.py: presence, normal-round AFK (disconnected
client's turn -> admin absorbs the seat) and the unanimous admin-AFK vote
(service + /admin_afk/* routes).
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand
from app import create_app
from app.config import AFK_DISCONNECT_SECONDS
from app.models.game_room import GameRoom, GameConfig
from app.services.session_store import game_sessions, set_session
from app.services.serializer import serialize_state
from app.services.afk import (
    admin_is_blocking, apply_normal_round_afk, apply_admin_afk_vote_forfeit,
    cast_admin_afk_vote, eligible_voter_cids, open_admin_afk_vote,
)
from app.services.tick import tick


def _live_hand(stood=False):
    return make_hand(("5", "S"), ("6", "H"), stood=stood)


def _room(admin_turn=False):
    """Alice (dealer + admin), Bob, Carol, Dave. Turn order: Bob, Carol, Dave,
    Alice. By default it's Bob's turn; admin_turn=True stands everyone but
    Alice so it's the admin's turn."""
    names = ["Alice", "Bob", "Carol", "Dave"]
    players = []
    for n in names:
        stood = admin_turn and n != "Alice"
        players.append(make_player(n, hands=[_live_hand(stood=stood)], is_dealer=(n == "Alice")))
    players[0].dealer_hand = make_hand(("K", "S"), ("7", "H"))
    raw = RefereeSession(players, "Alice", wager=1, num_hands=1)
    room = GameRoom(session=raw, config=GameConfig(mode="digital", drinking_mode=False))
    room._room_clients = {
        "admin-cid": {"name": "Alice", "role": "admin", "local_names": ["Alice"]},
        "bob-cid":   {"name": "Bob",   "role": "player"},
        "carol-cid": {"name": "Carol", "role": "player"},
        "dave-cid":  {"name": "Dave",  "role": "player"},
    }
    now = time.monotonic()
    for cid in room._room_clients:
        room._client_last_seen[cid] = now
    return room


def _go_silent(room, cid):
    room._client_last_seen[cid] = time.monotonic() - AFK_DISCONNECT_SECONDS - 1


# ---------------------------------------------------------------------------
# Normal-round AFK
# ---------------------------------------------------------------------------

def test_disconnected_client_on_its_turn_is_absorbed_by_admin():
    room = _room()
    _go_silent(room, "bob-cid")
    apply_normal_round_afk(room)
    assert room._room_clients["bob-cid"]["role"] == "spectator"
    assert room._room_clients["bob-cid"]["name"] is None
    assert room._room_clients["admin-cid"]["local_names"] == ["Alice", "Bob"]
    assert room._room_clients["bob-cid"]["afk_notice"]["context"] == "turn"
    assert any("Bob disconnected" in e for e in room.round._log_entries)


def test_connected_client_is_not_absorbed():
    room = _room()
    apply_normal_round_afk(room)
    assert room._room_clients["bob-cid"]["role"] == "player"


def test_silent_client_not_on_turn_is_left_alone():
    room = _room()
    _go_silent(room, "carol-cid")   # Carol is silent but it's Bob's turn
    apply_normal_round_afk(room)
    assert room._room_clients["carol-cid"]["role"] == "player"


def test_never_stamped_client_is_not_absorbed():
    room = _room()
    del room._client_last_seen["bob-cid"]
    apply_normal_round_afk(room)
    assert room._room_clients["bob-cid"]["role"] == "player"


def test_bot_and_admin_turns_are_never_absorbed():
    room = _room(admin_turn=True)   # Alice (admin) is up
    _go_silent(room, "admin-cid")
    apply_normal_round_afk(room)
    assert room._room_clients["admin-cid"]["local_names"] == ["Alice"]


def test_tick_runs_normal_round_afk():
    room = _room()
    _go_silent(room, "bob-cid")
    tick(room)
    assert room._room_clients["admin-cid"]["local_names"] == ["Alice", "Bob"]


# ---------------------------------------------------------------------------
# admin_is_blocking / eligible voters
# ---------------------------------------------------------------------------

def test_admin_not_blocking_on_someone_elses_turn():
    assert admin_is_blocking(_room()) is False


def test_admin_blocking_on_own_turn():
    assert admin_is_blocking(_room(admin_turn=True)) is True


def test_admin_blocking_with_pending_registration():
    room = _room()
    room._pending_registrations.append({"client_id": "x", "name": "Eve"})
    assert admin_is_blocking(room) is True


def test_eligible_voters_exclude_admin_and_disconnected():
    room = _room(admin_turn=True)
    _go_silent(room, "dave-cid")
    assert sorted(eligible_voter_cids(room)) == ["bob-cid", "carol-cid"]


# ---------------------------------------------------------------------------
# Admin-AFK vote (service)
# ---------------------------------------------------------------------------

def test_cannot_open_vote_when_admin_not_blocking():
    room = _room()
    ok, err, _ = open_admin_afk_vote(room, "bob-cid")
    assert not ok and "waiting on the admin" in err


def test_admin_and_spectators_cannot_open_vote():
    room = _room(admin_turn=True)
    assert open_admin_afk_vote(room, "admin-cid")[0] is False
    room._room_clients["spec"] = {"name": None, "role": "spectator"}
    room._client_last_seen["spec"] = time.monotonic()
    assert open_admin_afk_vote(room, "spec")[0] is False


def test_vote_requires_every_eligible_player_to_agree():
    room = _room(admin_turn=True)
    assert open_admin_afk_vote(room, "bob-cid") == (True, "", False)
    assert cast_admin_afk_vote(room, "carol-cid", True) == (True, "", None)
    assert cast_admin_afk_vote(room, "dave-cid", True) == (True, "", "passed")
    assert room._admin_afk_last_result["passed"] is True
    assert room.round._pending_admin_afk_vote is None


def test_single_no_fails_the_vote():
    room = _room(admin_turn=True)
    open_admin_afk_vote(room, "bob-cid")
    assert cast_admin_afk_vote(room, "carol-cid", False) == (True, "", "failed")
    assert room._admin_afk_last_result["passed"] is False


def test_sole_eligible_voter_passes_immediately():
    room = _room(admin_turn=True)
    _go_silent(room, "carol-cid")
    _go_silent(room, "dave-cid")
    assert open_admin_afk_vote(room, "bob-cid") == (True, "", True)


def test_vote_expires():
    room = _room(admin_turn=True)
    open_admin_afk_vote(room, "bob-cid")
    room.round._pending_admin_afk_vote["expires_at"] = time.monotonic() - 1
    apply_admin_afk_vote_forfeit(room)
    assert room._admin_afk_last_result["reason"] == "timed out"
    assert room.round._pending_admin_afk_vote is None


def test_vote_cancelled_when_admin_acts():
    room = _room(admin_turn=True)
    open_admin_afk_vote(room, "bob-cid")
    # Admin stands: the turn moves on, so the game is no longer waiting on them.
    room._get_player("Alice").hands[0].stood = True
    apply_admin_afk_vote_forfeit(room)
    assert room._admin_afk_last_result["reason"] == "admin is back"


def test_non_voter_cannot_vote():
    room = _room(admin_turn=True)
    open_admin_afk_vote(room, "bob-cid")
    assert cast_admin_afk_vote(room, "admin-cid", True)[0] is False


# ---------------------------------------------------------------------------
# Routes + serialization
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def route_room():
    code = "AfkRoom1"
    room = _room(admin_turn=True)
    set_session(code, room)
    yield code, room
    game_sessions.pop(code, None)


def _post(client, path, code, cid, **extra):
    return client.post(path, json={"room_code": code, "client_id": cid, **extra}).get_json()


def test_unanimous_vote_hands_admin_to_first_yes_voter(client, route_room):
    code, room = route_room
    assert _post(client, "/admin_afk/open", code, "bob-cid")["ok"]
    _post(client, "/admin_afk/vote", code, "carol-cid", vote=True)
    data = _post(client, "/admin_afk/vote", code, "dave-cid", vote=True)
    assert data["ok"]
    assert room._room_clients["bob-cid"]["role"] == "admin"
    assert room._room_clients["admin-cid"]["role"] == "player"
    assert room._admin_afk_last_result["new_admin"] == "Bob"


def test_vote_with_a_no_leaves_admin_unchanged(client, route_room):
    code, room = route_room
    _post(client, "/admin_afk/open", code, "bob-cid")
    _post(client, "/admin_afk/vote", code, "carol-cid", vote=False)
    assert room._room_clients["admin-cid"]["role"] == "admin"


def test_route_rejects_open_when_not_blocking(client):
    code = "AfkRoom2"
    room = _room()
    set_session(code, room)
    try:
        data = _post(client, "/admin_afk/open", code, "bob-cid")
        assert data["ok"] is False
    finally:
        game_sessions.pop(code, None)


def test_state_exposes_admin_afk_block(client, route_room):
    code, room = route_room
    s = serialize_state(room, "bob-cid")["admin_afk_vote"]
    assert s["can_open"] is True and s["pending"] is None
    assert serialize_state(room, "admin-cid")["admin_afk_vote"]["can_open"] is False
    open_admin_afk_vote(room, "bob-cid")
    s = serialize_state(room, "carol-cid")["admin_afk_vote"]
    assert s["pending"]["eligible"] is True and s["pending"]["yes_count"] == 1
    assert s["can_open"] is False


def test_state_poll_stamps_presence(client, route_room):
    code, room = route_room
    _go_silent(room, "bob-cid")
    client.get(f"/state?room_code={code}&client_id=bob-cid")
    assert time.monotonic() - room._client_last_seen["bob-cid"] < 5
