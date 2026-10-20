"""
tests/app/test_stake_window.py
===============================
Normal mode: the first Deal opens a stake window (change or accept your
stake) instead of dealing; the cards go out once every human accepted or the
window ran out. Bot stakes can't be changed. The bet panel never shows at
round-over.
"""

import time

import pytest

from app import create_app
from app.services.session_store import game_sessions
from app.services.tick import tick


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _new(c, players=("Rob", "Bot"), npcs=("Bot",), **kw):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": list(players),
            "npcs": list(npcs), "dealer_index": 0, "mode": "digital",
            "drinking": False, "bet_amount": 10, "starting_bankroll": 100,
            "num_hands": 1, "wager": 1}
    body.update(kw)
    assert c.post("/setup", json=body).get_json().get("ok", True)
    return code, game_sessions[code]


def _cmd(c, code, text):
    return c.post("/command", json={"room_code": code, "client_id": "cid",
                                    "cmd": text}).get_json()


def _dealt(s):
    return any(h.cards for p in s.all_players for h in p.hands)


def test_first_deal_opens_window_without_dealing(client):
    code, s = _new(client)
    st = _cmd(client, code, "deal")
    assert not _dealt(s)
    assert st["phase"] == "pre-deal"
    assert st["stake_window_open"] is True
    assert 1 <= st["stake_window_seconds_left"] <= 15
    assert s._bankrolls.get("Rob", 100) == 100        # nothing deducted yet


def test_window_deals_when_everyone_accepts(client):
    code, s = _new(client)
    _cmd(client, code, "deal")
    r = client.post("/confirm_stake", json={"room_code": code, "client_id": "cid"})
    assert r.get_json()["stake_confirmed"] == ["Rob"]   # the bot is never listed
    tick(s)
    assert _dealt(s)
    assert s.round._stake_window_expires_at is None


def test_window_deals_on_timeout_with_changed_stake(client):
    code, s = _new(client)
    _cmd(client, code, "deal")
    r = client.post("/set_player_bet", json={"room_code": code, "client_id": "cid",
                                              "player_name": "Rob", "bet": 20}).get_json()
    assert r["ok"] and r["bet"] == 20
    tick(s)
    assert not _dealt(s)                                # still waiting for Rob
    s.round._stake_window_expires_at = time.monotonic() - 1
    tick(s)
    assert _dealt(s)
    assert s._bankrolls["Rob"] == 80                    # the changed stake was taken


def test_second_deal_during_window_deals_now(client):
    code, s = _new(client)
    _cmd(client, code, "deal")
    _cmd(client, code, "deal")
    assert _dealt(s)
    assert s.round._stake_window_expires_at is None


def test_all_bot_table_deals_immediately(client):
    code, s = _new(client, players=("Bot1", "Bot2"), npcs=("Bot1", "Bot2"))
    _cmd(client, code, "deal")
    assert _dealt(s)


def test_bot_stake_cannot_be_changed(client):
    code, s = _new(client, players=("Rob", "Bot"), npcs=("Bot",))
    # the human client also controls the bot's seat (e.g. a seat turned into a bot)
    s._room_clients["cid"]["local_names"] = ["Rob", "Bot"]
    s._player_bets["Bot"] = 15
    r = client.post("/set_player_bet", json={"room_code": code, "client_id": "cid",
                                              "player_name": "Bot", "bet": 50}).get_json()
    assert r["ok"] is False
    assert s._player_bets["Bot"] == 15


def test_stake_cannot_be_changed_at_round_over(client):
    code, s = _new(client)
    _cmd(client, code, "deal")
    _cmd(client, code, "deal")
    for p in s.all_players:
        for h in p.hands:
            h.result = "loss"
    r = client.post("/set_player_bet", json={"room_code": code, "client_id": "cid",
                                              "player_name": "Rob", "bet": 20}).get_json()
    assert r["ok"] is False


def test_window_does_not_exist_in_drinking_mode(client):
    code, s = _new(client, drinking=True)
    _cmd(client, code, "deal")
    assert _dealt(s)
