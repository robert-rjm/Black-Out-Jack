"""
tests/app/test_normal_mode_casino.py
=====================================
Web-path regression tests for Normal (casino) mode: no sips/milestones,
doubles are charged, bankrolls never go negative, dealer peek, no
mid-round reshuffle, and the bet / hand-index fixes.
"""

import random

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


def _deal(c, code):
    """Normal mode: the first Deal opens the stake window, a second one deals."""
    st = _cmd(c, code, "deal")
    if st.get("phase") == "pre-deal":
        st = _cmd(c, code, "deal")
    return st


def _rig(s, seq):
    s.shoe.cards = [parse_card(x.lower()) for x in reversed(seq)]
    s.shoe.penetration = 1.0
    s.shoe.total_cards = 10 ** 6


def test_double_win_is_paid_on_doubled_stake(client):
    code, s = _new(client)
    # Rob 5+6, Bot 10+10, dealer 10+7; Rob doubles into a 10 -> 21
    _rig(s, ["5S", "10S", "10H", "6D", "10D", "7C", "10C"])
    _deal(client, code)
    assert s._bankrolls["Rob"] == 90
    _cmd(client, code, "double Rob hand1")
    assert s._bankrolls["Rob"] == 120          # 100 - 10 - 10 + 40
    assert s._last_round_payouts["Rob"] == 20


def test_dealer_blackjack_peek_ends_round_before_play(client):
    code, s = _new(client, players=("Rob", "Amy", "Bot"), npcs=("Bot",))
    # Rob 8,8 ; Amy 10,10 ; Bot 10,9 ; dealer A,K (blackjack)
    _rig(s, ["8S", "10S", "10H", "AH", "8D", "10D", "9C", "KC"])
    st = _deal(client, code)
    assert st["phase"] == "round-over"
    assert s._bankrolls["Rob"] == 90           # only the opening bet lost
    assert s._last_round_payouts["Rob"] == -10


def test_no_drinks_or_milestones_in_normal_mode(client):
    random.seed(3)
    code, s = _new(client, players=("Rob", "Bot1", "Bot2"),
                   npcs=("Bot1", "Bot2"), num_hands=2, starting_bankroll=100000)
    for _ in range(70):
        st = _deal(client, code)
        for _ in range(4):
            if st.get("current_turn") == "Rob":
                _cmd(client, code, "stand Rob hand1")
                st = _cmd(client, code, "stand Rob hand2")
        _cmd(client, code, "newround")
    assert s.drinks.sip_ticker == {}
    assert s.drinks.csv_rows == []
    assert s.drinks.milestones_claimed == {}
    assert s.round._pending_milestone is None
    assert all(not p.drink_log for p in s.all_players)
    assert s.stats.l_badge_holders == []
    assert s.round._l_handout_pending == {}
    assert s.stats.hand_stats["Rob"]["hands"] > 0     # blackjack stats still tracked


def test_deal_refused_when_player_cannot_cover_bet(client):
    code, s = _new(client, starting_bankroll=5)
    st = _cmd(client, code, "deal")
    assert s._bankrolls["Rob"] == 5            # nothing deducted
    assert all(not h.cards for h in s._get_player("Rob").hands)


def test_cannot_double_without_funds(client):
    code, s = _new(client, starting_bankroll=15)
    _rig(s, ["5S", "10S", "10H", "6D", "10D", "7C", "10C"])
    _deal(client, code)
    assert s._bankrolls["Rob"] == 5
    _cmd(client, code, "double Rob hand1")
    hand = s._get_player("Rob").hands[0]
    assert not hand.doubled and s._bankrolls["Rob"] == 5


def test_no_mid_round_reshuffle(client):
    code, s = _new(client)
    _rig(s, ["5S", "10S", "10H", "6D", "10D", "7C", "10C", "2C"])
    s.shoe.penetration = 0.0                   # "needs reshuffle" is true throughout
    s.shoe.total_cards = 10 ** 6
    _deal(client, code)
    assert not s.round._reshuffle_events
    assert len(s.shoe.cards) == 2


def test_set_player_bet_returns_ok_and_caps_to_bankroll(client):
    code, s = _new(client, starting_bankroll=12.5)
    r = client.post("/set_player_bet", json={"room_code": code, "client_id": "cid",
                                              "player_name": "Rob", "bet": 50})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] and body["bet"] == 12.5   # capped to bankroll


def test_absurd_hand_index_rejected(client):
    code, s = _new(client, mode="referee", drinking=True)
    _cmd(client, code, "deal Rob 2h hand400000")
    assert len(s._get_player("Rob").hands) < 25


# ---------------------------------------------------------------------------
# Round-ended gate (all modes)
# ---------------------------------------------------------------------------

def test_repeat_dealer_and_endround_do_not_repay_in_normal_mode(client):
    code, s = _new(client)
    _rig(s, ["5S", "10S", "10H", "6D", "10D", "7C", "10C"])
    _deal(client, code)
    _cmd(client, code, "double Rob hand1")
    after = dict(s._bankrolls)
    for c in ("dealer", "endround", "deal"):
        assert _cmd(client, code, c).get("rejected") is True
    assert s._bankrolls == after


def test_repeat_dealer_does_not_refire_drinks(client):
    code, s = _new(client, drinking=True, num_hands=1)
    _rig(s, ["10S", "9S", "10H", "9D", "10D", "7C"])
    _cmd(client, code, "deal")
    for _ in range(3):
        _cmd(client, code, "stand Rob hand1")
    before = {p.name: list(p.drink_log) for p in s.all_players}
    assert _cmd(client, code, "dealer").get("rejected") is True
    assert {p.name: list(p.drink_log) for p in s.all_players} == before


def test_referee_endround_twice_is_rejected_and_newround_reopens(client):
    code, s = _new(client, players=("Rob", "Amy"), npcs=(), mode="referee", drinking=True)
    for c in ["deal Rob 10h", "deal Amy 8s", "deal dealer 10c", "deal Rob 9d",
              "deal Amy 9d", "deal dealer 7d", "result Rob win", "result Amy loss"]:
        _cmd(client, code, c)
    _cmd(client, code, "endround")
    before = {p.name: list(p.drink_log) for p in s.all_players}
    assert _cmd(client, code, "endround").get("rejected") is True
    assert _cmd(client, code, "result Rob loss").get("rejected") is True
    assert {p.name: list(p.drink_log) for p in s.all_players} == before
    _cmd(client, code, "newround")
    assert not _cmd(client, code, "deal Rob 2h").get("rejected")
