"""
tests/app/test_mode_switch.py
==============================
Admin can flip a table between Normal and Drinking mode without going back
through the lobby; the switch is queued and takes effect at the next round.
"""

import pytest

from app import create_app
from app.services.session_store import game_sessions
from engine.referee import parse_card


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _new(c, drinking):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": ["Rob", "Bot"],
            "npcs": ["Bot"], "dealer_index": 0, "mode": "digital",
            "drinking": drinking, "bet_amount": 10, "starting_bankroll": 100,
            "num_hands": 1, "wager": 1}
    assert c.post("/setup", json=body).get_json().get("ok", True)
    return code, game_sessions[code]


def _cmd(c, code, text):
    return c.post("/command", json={"room_code": code, "client_id": "cid",
                                    "cmd": text}).get_json()


def _settings(c, code, **kw):
    return c.post("/update_settings",
                  json={"room_code": code, "client_id": "cid", **kw}).get_json()


def _play_round(c, code, s):
    st = _cmd(c, code, "deal")
    if st.get("phase") == "pre-deal":
        st = _cmd(c, code, "deal")
    for _ in range(6):
        if st.get("phase") == "round-over":
            break
        for name in ("Rob", "Bot"):
            st = _cmd(c, code, f"stand {name} hand1")
    assert st.get("phase") == "round-over"


def test_switch_is_queued_not_immediate(client):
    code, s = _new(client, drinking=False)
    st = _settings(client, code, drinking_mode=True)
    assert st["ok"]
    assert st["queued_settings"]["drinking_mode"] is True
    assert s.drinking_mode is False


def test_requesting_current_mode_cancels_pending_switch(client):
    code, s = _new(client, drinking=False)
    _settings(client, code, drinking_mode=True)
    st = _settings(client, code, drinking_mode=False)
    assert "drinking_mode" not in st["queued_settings"]


def test_normal_to_drinking_applies_at_next_round(client):
    code, s = _new(client, drinking=False)
    _settings(client, code, drinking_mode=True)
    _play_round(client, code, s)
    assert s.drinking_mode is False            # still the old mode mid-cycle
    st = _cmd(client, code, "newround")
    assert s.drinking_mode is True
    assert st["drinking_mode"] is True
    assert "drinking_mode" not in st["queued_settings"]
    assert type(s.session.tracker).__name__ == "DrinkTracker"


def test_drinking_table_cannot_switch_to_normal(client):
    code, s = _new(client, drinking=True)
    st = _settings(client, code, drinking_mode=False)
    assert st["ok"] is False
    assert "drinking_mode" not in s._queued_settings
    _play_round(client, code, s)
    _cmd(client, code, "newround")
    assert s.drinking_mode is True


# ---------------------------------------------------------------------------
# Buy-in handouts (Normal mode): players above the buy-in hand out a sip
# ---------------------------------------------------------------------------

def _rig(s, seq):
    s.shoe.cards = [parse_card(x.lower()) for x in reversed(seq)]
    s.shoe.penetration = 1.0
    s.shoe.total_cards = 10 ** 6


def _win_round_for_rob(c, code, s):
    # Rob 10+10 stands on 20; Bot 10+8; dealer 10+7 -> Rob wins
    _rig(s, ["10S", "10H", "10D", "10C", "8D", "7C"])
    _play_round(c, code, s)


def test_handout_pending_for_player_above_buyin(client):
    code, s = _new(client, drinking=False)
    _settings(client, code, buyin_handouts=True)
    _win_round_for_rob(client, code, s)
    assert s._bankrolls["Rob"] > 100
    st = client.get(f"/state?room_code={code}&client_id=cid").get_json()
    assert st["my_buyin_handouts"] == {"Rob": 1}
    r = client.post("/buyin_handout/give", json={
        "room_code": code, "client_id": "cid",
        "giver_name": "Rob", "recipient_name": "Bot"}).get_json()
    assert r["ok"] and r["my_buyin_handouts"] == {}
    assert any("hands 1 sip(s) to Bot" in l for l in s.round._log_entries)
    assert s.drinks.sip_ticker == {}           # Normal mode still records no sips


def test_no_handout_when_setting_off(client):
    code, s = _new(client, drinking=False)
    _win_round_for_rob(client, code, s)
    assert s.round._buyin_pending == {}


def test_handout_cannot_target_self_or_be_claimed_twice(client):
    code, s = _new(client, drinking=False)
    _settings(client, code, buyin_handouts=True)
    _win_round_for_rob(client, code, s)
    def give(to):
        return client.post("/buyin_handout/give", json={
            "room_code": code, "client_id": "cid",
            "giver_name": "Rob", "recipient_name": to}).get_json()
    assert not give("Rob")["ok"]
    assert give("")["ok"]                      # pass
    assert not give("Bot")["ok"]               # already resolved
