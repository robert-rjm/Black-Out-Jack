"""
tests/app/test_l_handout_round.py
=================================
The comeback handout (L badge, Rules.md §5.8) across the round boundary and
the tick: a handout nobody picked a recipient for is drunk by its giver when
the next round starts, the countdown waits while another handout prompt is
open, and /state shows it only to the giver's own client.
"""

import time

import pytest

from app import create_app
from app.config import L_HANDOUT_WINDOW_SECONDS
from app.models.state_schema import AppState
from app.services.session_store import game_sessions
from app.services.tick import tick


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _new(c):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": ["Rob", "Ann"],
            "dealer_index": 0, "mode": "digital", "drinking": True}
    assert c.post("/setup", json=body).get_json().get("ok", True)
    return code, game_sessions[code]


def _pending(s, giver="Rob", sips=2, streak=7):
    s.round._l_handout_pending = {giver: sips}
    s.round._l_handout_streaks = {giver: streak}
    s.round._l_handout_given = set()
    s.round._l_handout_expires_at = time.monotonic() + L_HANDOUT_WINDOW_SECONDS


def test_an_unclaimed_handout_is_drunk_by_the_giver_at_newround(client):
    code, s = _new(client)
    _pending(s)
    client.post("/command", json={"room_code": code, "client_id": "cid", "cmd": "newround"})
    assert s.drinks.sip_ticker.get("Rob") == 2
    assert s.round._l_handout_pending == {}            # the new round starts clean


def test_state_offers_the_handout_to_the_giver_only(client):
    code, s = _new(client)
    _pending(s)
    mine = client.get(f"/state?room_code={code}&client_id=cid").get_json()
    AppState(**mine)
    assert mine["my_l_handouts"] == {"Rob": 2}
    assert 0 < mine["l_handout_seconds_left"] <= L_HANDOUT_WINDOW_SECONDS
    s._room_clients["c-ann"] = {"name": "Ann", "role": "player", "local_names": ["Ann"]}
    theirs = client.get(f"/state?room_code={code}&client_id=c-ann").get_json()
    assert theirs["my_l_handouts"] == {}


def test_the_give_route_checks_the_seat_belongs_to_the_caller(client):
    code, s = _new(client)
    _pending(s)
    s._room_clients["c-ann"] = {"name": "Ann", "role": "player", "local_names": ["Ann"]}
    bad = client.post("/l_handout/give", json={"room_code": code, "client_id": "c-ann",
                                               "giver_name": "Rob", "recipient_name": "Ann"}).get_json()
    assert bad["ok"] is False
    ok = client.post("/l_handout/give", json={"room_code": code, "client_id": "cid",
                                              "giver_name": "Rob", "recipient_name": "Ann"}).get_json()
    assert ok["ok"] and s.drinks.sip_ticker["Ann"] == 2


def test_the_countdown_waits_while_a_milestone_handout_is_open(client):
    code, s = _new(client)
    _pending(s)
    s.round._l_handout_expires_at = time.monotonic() - 1          # would have run out
    s.round._pending_milestone = {"winner": "Ann", "boundary": 50, "handout": 5,
                                  "expires_at": time.monotonic() + 30}
    tick(s)
    assert s.drinks.sip_ticker.get("Rob") is None                 # not forfeited
    assert s.round._l_handout_expires_at > time.monotonic() + 30
