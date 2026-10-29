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
        config=GameConfig(mode="digital", drinking_mode=True),
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


def test_targeted_roll_falls_back_to_random_drink_when_subgame_already_active(client, wild_card_room, monkeypatch):
    """A "targeted" roll that can't actually start the subgame (already
    running) must not waste the press on a no-op dud -- it falls back to a
    random drink instead, so every press always lands on self/random/targeted."""
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

    assert data["wild_card_outcome"] == "random"
    # The already-running subgame's targets are untouched, not overwritten.
    assert room._targeted_drinking_targets == ["Bob"]
    assert "dud" not in room.drinks.wild_card_presses["Alice"]
    assert room.drinks.wild_card_presses["Alice"]["random"] == 1
    assert room.drinks.wild_card_presses["Alice"]["targeted"] == 0


@pytest.mark.parametrize("milestones_on", [True, False])
def test_milestone_block_only_applies_when_milestones_are_on(client, wild_card_room, monkeypatch, milestones_on):
    room_code, room = wild_card_room
    if not milestones_on:
        room.rules = room.rules.with_rule("milestone.handout", False)
    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")
    monkeypatch.setattr(wild_card_route, "compute_sip_totals", lambda s: {"Alice": 45})   # 5 from 50
    monkeypatch.setattr(wild_card_route.random, "random", _fixed_random([0.0]))         # self drinks

    data = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"}).get_json()

    if milestones_on:
        assert data["ok"] is False and "milestone" in data["output"]
    else:
        assert data["wild_card_outcome"] == "self"


def test_wild_card_off(client, wild_card_room, monkeypatch):
    room_code, room = wild_card_room
    room.rules = room.rules.with_rule("event.wild_card", False)
    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")

    data = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"}).get_json()

    assert data["ok"] is False and "disabled" in data["output"]
    assert room.drinks.wild_card_presses == {}


def test_targeted_roll_falls_back_to_random_drink_when_the_rule_is_off(client, wild_card_room, monkeypatch):
    room_code, room = wild_card_room
    room.rules = room.rules.with_rule("event.wild_card.targeted", False)
    monkeypatch.setattr(wild_card_route, "round_phase", lambda s: "playing")
    monkeypatch.setattr(wild_card_route.random, "random", _fixed_random([0.40, 0.10]))   # targeted band
    monkeypatch.setattr(wild_card_route.random, "choice", lambda seq: seq[0])

    data = client.post("/wild_card", json={"room_code": room_code, "client_id": "client-1"}).get_json()

    assert data["wild_card_outcome"] == "random"
    assert room._targeted_drinking_active is False
