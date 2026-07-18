"""
Tests for the Wild Card Easter egg's "targeted" outcome (app/routes/wild_card.py):
launching Targeted Drinking Mode in place of the old flat "dud".
"""

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player
from app import create_app
from app.models.game_room import GameRoom, GameConfig
from app.services.session_store import game_sessions, set_session
import app.routes.wild_card as wild_card_route


def _make_room(num_players=3):
    names = ["Alice", "Bob", "Carol"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    return GameRoom(
        session=raw_session,
        config=GameConfig(mode="digital", drinking_mode=True, wild_card_enabled=True),
    )


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def _fixed_random(values):
    it = iter(values)
    return lambda: next(it)


def _room_setup(room_code="TestWildCard"):
    room = _make_room()
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice"], "role": "admin", "kicked": False,
    }
    set_session(room_code, room)
    return room_code, room


@pytest.fixture
def wild_card_room():
    room_code, room = _room_setup()
    yield room_code, room
    game_sessions.pop(room_code, None)


def test_targeted_roll_targets_presser(client, wild_card_room, monkeypatch):
    room_code, room = wild_card_room
    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")
    monkeypatch.setattr(
        wild_card_route.random, "random",
        _fixed_random([0.40, 0.10]),   # outer roll -> targeted band; inner -> < 1/3 -> self
    )
    monkeypatch.setattr(wild_card_route.random, "choice", lambda seq: seq[0])

    resp = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"})
    data = resp.get_json()

    assert data["wild_card_outcome"] == "targeted"
    assert room._targeted_drinking_active is True
    assert room._targeted_drinking_targets == ["Alice"]
    assert room.drinks.wild_card_presses["Alice"]["targeted"] == 1


def test_targeted_roll_targets_random_player(client, wild_card_room, monkeypatch):
    room_code, room = wild_card_room
    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")
    monkeypatch.setattr(
        wild_card_route.random, "random",
        _fixed_random([0.40, 0.90]),   # outer roll -> targeted band; inner -> >= 1/3 -> random
    )
    monkeypatch.setattr(wild_card_route.random, "choice", lambda seq: seq[0])

    resp = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"})
    data = resp.get_json()

    assert data["wild_card_outcome"] == "targeted"
    assert room._targeted_drinking_active is True
    # random.choice patched to always return the first candidate
    assert room._targeted_drinking_targets == [room.all_players[0].name]


def test_targeted_roll_falls_back_to_dud_when_subgame_already_active(client, wild_card_room, monkeypatch):
    room_code, room = wild_card_room
    room._targeted_drinking_active = True   # a subgame is already running
    room._targeted_drinking_targets = ["Bob"]

    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")
    monkeypatch.setattr(
        wild_card_route.random, "random",
        _fixed_random([0.40, 0.10]),
    )
    monkeypatch.setattr(wild_card_route.random, "choice", lambda seq: seq[0])

    resp = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"})
    data = resp.get_json()

    assert data["wild_card_outcome"] == "dud"
    # The already-running subgame's targets are untouched, not overwritten.
    assert room._targeted_drinking_targets == ["Bob"]
    assert room.drinks.wild_card_presses["Alice"]["dud"] == 1
    assert room.drinks.wild_card_presses["Alice"]["targeted"] == 0
