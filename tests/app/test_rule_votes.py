"""
tests/app/test_rule_votes.py
============================
Players' say in the house rules (services/rule_votes.py): suggestions to
the admin, the table vote that turns rule voting on, and the per-change
votes after that.
"""

import time

import pytest

from app import create_app
from app.models.state_schema import AppState
from app.services.rule_votes import apply_rule_vote_forfeit
from app.services.session_store import game_sessions


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _new(c, players=("Rob", "Ann", "Ben")):
    """Rob is the admin (cid); Ann and Ben are connected players (c-ann, c-ben)."""
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": list(players),
            "dealer_index": 0, "mode": "digital", "drinking": True}
    assert c.post("/setup", json=body).get_json().get("ok", True)
    s = game_sessions[code]
    for name in players[1:]:
        s._room_clients[f"c-{name.lower()}"] = {"name": name, "role": "player", "local_names": [name]}
    return code, s


def _post(c, url, code, client_id, **kw):
    return c.post(url, json={"room_code": code, "client_id": client_id, **kw}).get_json()


# ---------------------------------------------------------------------------
# Suggestions to the admin
# ---------------------------------------------------------------------------

def test_a_suggestion_lands_in_the_admin_inbox(client):
    code, s = _new(client)
    st = _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    assert st["ok"]
    assert st["rule_votes"]["suggestions"] == []          # players don't see the inbox
    assert st["rule_votes"]["suggestion_count"] == 1
    admin = _post(client, "/update_settings", code, "cid")
    assert admin["rule_votes"]["suggestions"] == [
        {"ids": ["event.dealer_lottery"], "on": False, "by": "Ann"}]
    assert "rules" not in s._queued_settings              # nothing changes yet


def test_accepting_queues_the_change_and_dismissing_drops_it(client):
    code, s = _new(client)
    _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    _post(client, "/rules/suggest", code, "c-ben", rule_id="cards.devils_hand", on=False)
    st = _post(client, "/rules/suggestion", code, "cid", index=0, accept=True)
    assert "event.dealer_lottery" not in st["rules"]["queued"]
    st = _post(client, "/rules/suggestion", code, "cid", index=0, accept=False)
    assert "cards.devils_hand" in st["rules"]["queued"]
    assert st["rule_votes"]["suggestion_count"] == 0


def test_suggesting_a_child_on_brings_its_off_parent(client):
    code, s = _new(client)
    s.rules = s.rules.with_changes(off=["switch.hard", "ace.clubs.dealer"])
    _post(client, "/rules/suggest", code, "c-ann", rule_id="ace.clubs.dealer", on=True)
    assert s._rule_suggestions[0]["ids"] == ["switch.hard", "ace.clubs.dealer"]


def test_a_newer_suggestion_for_the_same_rule_replaces_the_old(client):
    code, s = _new(client)
    _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    _post(client, "/rules/suggest", code, "c-ben", rule_id="event.dealer_lottery", on=False)
    assert [x["by"] for x in s._rule_suggestions] == ["Ben"]


@pytest.mark.parametrize("rule_id, on, needle", [
    ("core.net_loss", False, "game itself"),
    ("event.dealer_lottery", True, "already on"),
    ("nope", True, "Unknown rule"),
])
def test_bad_suggestions_are_refused(client, rule_id, on, needle):
    code, s = _new(client)
    st = _post(client, "/rules/suggest", code, "c-ann", rule_id=rule_id, on=on)
    assert st["ok"] is False and needle in st["error"]


def test_only_the_admin_answers_suggestions(client):
    code, s = _new(client)
    _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    st = _post(client, "/rules/suggestion", code, "c-ben", index=0, accept=True)
    assert st["ok"] is False and len(s._rule_suggestions) == 1


def test_spectators_cannot_suggest_or_vote(client):
    code, s = _new(client)
    s._room_clients["c-spec"] = {"name": "", "role": "spectator"}
    for url, kw in (("/rules/suggest", {"rule_id": "event.dealer_lottery", "on": False}),
                    ("/rules/propose_voting", {}), ("/rules/vote", {"vote": True})):
        assert _post(client, url, code, "c-spec", **kw)["ok"] is False


# ---------------------------------------------------------------------------
# Table votes
# ---------------------------------------------------------------------------

def test_the_table_can_vote_rule_voting_on(client):
    code, s = _new(client)
    st = _post(client, "/rules/propose_voting", code, "c-ann")
    pending = st["rule_votes"]["pending"]
    assert pending["kind"] == "enable" and pending["yes_count"] == 1 and pending["needed"] == 2
    st = _post(client, "/rules/vote", code, "c-ben", vote=True)
    assert st["rule_votes"]["voting"] is True and st["rule_votes"]["pending"] is None
    assert st["rule_votes"]["result"]["passed"] is True
    AppState(**st)


def test_a_vote_fails_as_soon_as_a_majority_is_out_of_reach(client):
    code, s = _new(client)
    _post(client, "/rules/propose_voting", code, "c-ann")
    _post(client, "/rules/vote", code, "c-ben", vote=False)
    st = _post(client, "/rules/vote", code, "cid", vote=False)
    assert st["rule_votes"]["voting"] is False
    assert st["rule_votes"]["result"]["passed"] is False


def test_with_rule_voting_on_a_suggestion_opens_a_vote_that_queues_the_change(client):
    code, s = _new(client)
    s._rule_voting = True
    st = _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    assert st["rule_votes"]["pending"]["kind"] == "change"
    assert s._rule_suggestions == []
    st = _post(client, "/rules/vote", code, "cid", vote=True)
    assert "event.dealer_lottery" not in st["rules"]["queued"]
    assert any("voted to switch off Dealer Lottery" in e for e in st["log_entries"])


def test_one_rule_vote_at_a_time(client):
    code, s = _new(client)
    s._rule_voting = True
    _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    st = _post(client, "/rules/suggest", code, "c-ben", rule_id="cards.devils_hand", on=False)
    assert st["ok"] is False and "already open" in st["error"]


def test_a_vote_that_times_out_fails_and_freezes_the_proposer(client):
    code, s = _new(client)
    s._rule_voting = True
    _post(client, "/rules/suggest", code, "c-ann", rule_id="event.dealer_lottery", on=False)
    s._pending_rule_vote["expires_at"] = time.monotonic() - 1
    apply_rule_vote_forfeit(s)
    assert s._pending_rule_vote is None and s.rules.on("event.dealer_lottery")
    st = _post(client, "/rules/suggest", code, "c-ann", rule_id="cards.devils_hand", on=False)
    assert st["ok"] is False and "next round" in st["error"]


def test_the_admin_can_switch_rule_voting_off_and_suggests_directly_otherwise(client):
    code, s = _new(client)
    s._rule_voting = True
    st = _post(client, "/update_settings", code, "cid", rule_voting=False)
    assert st["rule_votes"]["voting"] is False
    st = _post(client, "/rules/suggest", code, "cid", rule_id="event.dealer_lottery", on=False)
    assert st["ok"] is False and "directly" in st["error"]
