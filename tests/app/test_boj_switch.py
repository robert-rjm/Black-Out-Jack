"""
tests/app/test_boj_switch.py
=============================
"Switch to BOJ" poll on a Normal table: majority switches the whole table,
a minority splits off into a new Drinking room (after a cancel window).
"""

import pytest

from app import create_app
from app.services.session_store import game_sessions


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _table(c, names=("Rob", "Amy", "Cy"), npcs=("Bot",)):
    """Normal digital table; one device per human seat (cid_<name>), Rob admin."""
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid_Rob", "players": list(names) + list(npcs),
            "npcs": list(npcs), "dealer_index": 0, "mode": "digital",
            "drinking": False, "bet_amount": 10, "starting_bankroll": 100,
            "num_hands": 1, "wager": 1}
    assert c.post("/setup", json=body).get_json().get("ok", True)
    s = game_sessions[code]
    s._room_clients["cid_Rob"] = {"name": "Rob", "local_names": ["Rob"],
                                  "role": "admin", "kicked": False}
    for n in names[1:]:
        s._room_clients[f"cid_{n}"] = {"name": n, "local_names": [n],
                                       "role": "player", "kicked": False}
    return code, s


def _post(c, path, code, who, **kw):
    return c.post(path, json={"room_code": code, "client_id": f"cid_{who}", **kw}).get_json()


def test_majority_yes_switches_whole_table(client):
    code, s = _table(client)
    assert _post(client, "/boj/propose", code, "Rob")["ok"]
    assert s._boj_poll is not None             # 1 of 3: still open
    _post(client, "/boj/vote", code, "Amy", vote=True)
    assert s._boj_poll is None
    assert s._queued_settings["drinking_mode"] is True
    assert s._boj_split is None
    assert s.drinking_mode is False            # applied at the next round, same room


def test_minority_yes_splits_to_new_room(client):
    code, s = _table(client)
    _post(client, "/boj/propose", code, "Amy")
    _post(client, "/boj/vote", code, "Rob", vote=False)
    assert s._boj_poll is not None             # 1 yes, 1 no, 1 undecided: still open
    _post(client, "/boj/vote", code, "Cy", vote=False)
    assert s._boj_poll is None
    assert "drinking_mode" not in s._queued_settings
    plan = s._boj_split
    assert list(plan["clients"]) == ["cid_Amy"]
    new_code = plan["new_room"]

    # Still inside the cancel window: no redirect yet.
    assert not _post(client, "/boj/split/go", code, "Amy")["ok"]
    plan["go_at"] = 0
    r = _post(client, "/boj/split/go", code, "Amy")
    assert r["ok"] and r["room_code"] == new_code

    new = game_sessions[new_code]
    assert new.drinking_mode is True
    assert [p.name for p in new.all_players] == ["Amy"]
    info = new._room_clients["cid_Amy"]
    assert info["name"] == "Amy" and info["role"] == "admin"
    # Amy is already registered there: her next /state poll just works.
    st = client.get(f"/state?room_code={new_code}&client_id=cid_Amy").get_json()
    assert st["my_name"] == "Amy" and st["drinking_mode"] is True

    assert "cid_Amy" not in s._room_clients
    assert s._queued_settings["remove_players"] == ["Amy"]
    assert s._boj_split is None


def test_mover_can_cancel_before_redirect(client):
    code, s = _table(client)
    _post(client, "/boj/propose", code, "Amy")
    _post(client, "/boj/vote", code, "Rob", vote=False)
    _post(client, "/boj/vote", code, "Cy", vote=False)
    new_code = s._boj_split["new_room"]
    assert _post(client, "/boj/split/cancel", code, "Amy")["ok"]
    assert s._boj_split is None
    assert new_code not in game_sessions       # reserved room released
    assert "cid_Amy" in s._room_clients
    assert "remove_players" not in s._queued_settings


def test_proposer_alone_is_the_minority_and_splits(client):
    code, s = _table(client)
    _post(client, "/boj/propose", code, "Rob")
    _post(client, "/boj/vote", code, "Amy", vote=False)
    _post(client, "/boj/vote", code, "Cy", vote=False)
    assert "drinking_mode" not in s._queued_settings
    assert list(s._boj_split["clients"]) == ["cid_Rob"]


def test_solo_new_table_can_play_a_round(client):
    code, s = _table(client)
    _post(client, "/boj/propose", code, "Amy")
    _post(client, "/boj/vote", code, "Rob", vote=False)
    _post(client, "/boj/vote", code, "Cy", vote=False)
    s._boj_split["go_at"] = 0
    new_code = _post(client, "/boj/split/go", code, "Amy")["room_code"]
    r = client.post("/command", json={"room_code": new_code, "client_id": "cid_Amy",
                                      "cmd": "deal"}).get_json()
    assert r.get("ok", True) is not False
    assert game_sessions[new_code].round_count >= 1


def test_leaving_dealer_hands_on_the_deal(client):
    code, s = _table(client)                   # Rob (index 0) is the dealer
    _post(client, "/boj/propose", code, "Rob")
    _post(client, "/boj/vote", code, "Amy", vote=False)
    _post(client, "/boj/vote", code, "Cy", vote=False)
    s._boj_split["go_at"] = 0
    assert _post(client, "/boj/split/go", code, "Rob")["ok"]
    assert s.dealer_name == "Rob"
    from app.services.room_manager import apply_queued_settings
    apply_queued_settings(s)
    names = [p.name for p in s.all_players]
    assert "Rob" not in names
    assert s.dealer_name in names and s._get_dealer() is not None


def test_only_one_human_switches_table(client):
    code, s = _table(client, names=("Rob",))
    assert _post(client, "/boj/propose", code, "Rob")["ok"]
    assert s._queued_settings["drinking_mode"] is True


def test_cannot_propose_in_drinking_mode(client):
    code = client.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid_Rob", "players": ["Rob", "Amy"],
            "npcs": [], "dealer_index": 0, "mode": "digital", "drinking": True}
    client.post("/setup", json=body)
    r = _post(client, "/boj/propose", code, "Rob")
    assert r["ok"] is False
