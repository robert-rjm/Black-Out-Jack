"""
tests/app/test_setup_limits.py
===============================
/setup and /update_settings clamp every numeric field at both ends and reject
malformed bot lists (CodeAudit-2026-10 B2): the server runs a single worker
thread, so one oversized request must not be able to freeze every table.
"""

import pytest

from app import create_app
from app.config import (
    MAX_BANKROLL, MAX_BET_AMOUNT, MAX_NUM_DECKS, MAX_NUM_HANDS, MAX_PLAYERS, MAX_WAGER,
)
from app.services.session_store import game_sessions
from app.services.validators import clamp_float, clamp_int


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _setup(c, **overrides):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": ["Rob", "Bot"],
            "npcs": ["Bot"], "dealer_index": 0, "mode": "digital", "drinking": True,
            "num_hands": 1, "wager": 1, **overrides}
    return code, c.post("/setup", json=body).get_json()


def test_clamp_helpers():
    assert clamp_int("7", 1, 5) == 5 and clamp_int(-3, 1, 5) == 1
    assert clamp_float(1e30, 0, 10) == 10
    for junk in ("nan", "inf", "-inf"):
        with pytest.raises(ValueError):
            clamp_float(junk, 0, 10)
    with pytest.raises((ValueError, TypeError)):
        clamp_int(None, 1, 5)


def test_huge_values_are_clamped(client):
    code, st = _setup(client, num_hands=1_000_000, wager=10**9, num_decks=10**6,
                      bet_amount=1e30, starting_bankroll=1e30)
    assert st.get("ok", True)
    room = game_sessions[code]
    assert room.session.num_hands == MAX_NUM_HANDS
    assert room.wager == MAX_WAGER
    assert len(room._get_player("Rob").hands) == MAX_NUM_HANDS
    assert room.bet_amount == MAX_BET_AMOUNT
    assert room.starting_bankroll == MAX_BANKROLL
    assert len(room.session.shoe.cards) <= 52 * MAX_NUM_DECKS


def test_too_many_players_is_rejected(client):
    names = [f"P{i}" for i in range(MAX_PLAYERS + 1)]
    _, st = _setup(client, players=names, npcs=[])
    assert st["ok"] is False and "Too many players" in st["error"]


@pytest.mark.parametrize("overrides", [
    {"npcs": "Bot"},
    {"personalities": ["rob"]},
    {"mode": "chaos"},
    {"bet_amount": "nan"},
])
def test_malformed_fields_get_a_clean_error(client, overrides):
    _, st = _setup(client, **overrides)
    assert st["ok"] is False


def test_non_string_bot_names_are_skipped_not_a_crash(client):
    code, st = _setup(client, npcs=[1, None, "Bot"])
    assert st.get("ok", True)
    assert game_sessions[code]._get_player("Bot").is_npc


def test_personality_cannot_name_a_path(client):
    code, st = _setup(client, personalities={"Bot": "../../data/profile_backups/2026-07-18/rob"})
    assert st.get("ok", True)
    assert game_sessions[code]._get_player("Bot").personality == "basic"


def test_update_settings_ignores_out_of_range_values(client):
    code, _ = _setup(client)
    r = client.post("/update_settings", json={"room_code": code, "client_id": "cid",
                                              "wager": MAX_WAGER + 1, "num_hands": 10**6,
                                              "num_decks": 99}).get_json()
    assert r.get("ok", True)
    queued = game_sessions[code]._queued_settings
    assert not {"wager", "num_hands", "num_decks"} & queued.keys()


def test_update_settings_stops_adding_seats_at_the_cap(client):
    code, _ = _setup(client)
    room = game_sessions[code]
    for i in range(MAX_PLAYERS - len(room.all_players)):
        r = client.post("/update_settings", json={"room_code": code, "client_id": "cid",
                                                  "add_player": f"Extra{i}"}).get_json()
        assert r.get("ok", True)
    r = client.post("/update_settings", json={"room_code": code, "client_id": "cid",
                                              "add_player": "OneTooMany"}).get_json()
    assert r["ok"] is False and "full" in r["error"]
