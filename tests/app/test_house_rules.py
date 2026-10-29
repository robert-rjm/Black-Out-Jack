"""
tests/app/test_house_rules.py
=============================
Phase 3 of the rule toggles (RuleToggles-Implementation.md §4, §6.4): the
admin edits house rules through /update_settings, live rules apply at once,
the rest queue as a full target set and apply at the next round with a
round-log notice, and /state and /rules_registry describe them.
"""

import pytest

from app import create_app
from app.models.state_schema import AppState
from app.services.house_rules import describe_rule_diff
from app.services.session_store import game_sessions
from app.services.targeted_drinking import start_targeted_drinking
from engine.rules_registry import FULL, RULES, STANDARD, STARTER, RuleSet


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _new(c):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": ["Rob", "Ann", "Bot"],
            "npcs": ["Bot"], "dealer_index": 0, "mode": "digital",
            "drinking": True, "num_hands": 1, "wager": 1}
    assert c.post("/setup", json=body).get_json().get("ok", True)
    return code, game_sessions[code]


def _settings(c, code, client_id="cid", **kw):
    return c.post("/update_settings",
                  json={"room_code": code, "client_id": client_id, **kw}).get_json()


def _newround(c, code):
    return c.post("/command", json={"room_code": code, "client_id": "cid",
                                    "cmd": "newround"}).get_json()


# ---------------------------------------------------------------------------
# Queue and apply
# ---------------------------------------------------------------------------

def test_a_rule_change_queues_and_leaves_the_live_rules_alone(client):
    code, s = _new(client)
    st = _settings(client, code, rules_off=["event.dealer_lottery"])
    assert st["ok"]
    assert s.rules.on("event.dealer_lottery")
    assert "event.dealer_lottery" not in st["rules"]["queued"]
    assert st["queued_settings"]["rules"] == st["rules"]["queued"]


def test_the_queue_holds_a_target_set_so_edits_collapse(client):
    code, s = _new(client)
    _settings(client, code, rules_off=["event.dealer_lottery"])
    st = _settings(client, code, rules_on=["event.dealer_lottery"])
    # Back where the table already is: nothing left to queue.
    assert st["rules"]["queued"] is None
    assert "rules" not in st["queued_settings"]


def test_queued_rules_apply_at_the_next_round_with_a_log_notice(client):
    code, s = _new(client)
    _settings(client, code, rules_off=["event.dealer_lottery", "ace.hearts.player"])
    st = _newround(client, code)
    assert not s.rules.on("event.dealer_lottery")
    assert not s.session.rules.on("ace.hearts.player")   # the engine sees it too
    assert st["rules"]["queued"] is None
    notices = [e for e in st["log_entries"] if "House rules changed" in e]
    assert len(notices) == 1
    assert "Dealer Lottery" in notices[0] and "off" in notices[0]


def test_a_preset_replaces_the_set(client):
    code, s = _new(client)
    st = _settings(client, code, rules_preset="starter")
    # Wild Card is live: the preset turned it off at once, not at the round.
    assert not s.wild_card_enabled
    assert set(st["rules"]["queued"]) == STARTER.enabled
    _newround(client, code)
    assert s.rules == STARTER and s.rules.preset == "starter"


def test_next_rule_turns_on_the_lowest_unlock_step_with_its_pair(client):
    code, s = _new(client)
    s.rules = STARTER
    st = _settings(client, code, rules_next=True)
    queued = set(st["rules"]["queued"])
    assert queued - STARTER.enabled == {"ace.hearts.player", "ace.hearts.dealer"}


def test_next_rule_also_turns_on_an_off_parent():
    rules = FULL.with_changes(off=["bonus.blackjack", "insurance.bj_vote"])
    assert rules.next_unlock() == {"insurance.bj_vote", "bonus.blackjack"}
    assert FULL.next_unlock() == frozenset()


def test_discard_drops_only_the_queued_rules(client):
    code, s = _new(client)
    _settings(client, code, wager=3, rules_off=["event.dealer_lottery"])
    st = _settings(client, code, rules_discard=True)
    assert "rules" not in st["queued_settings"]
    assert st["queued_settings"]["wager"] == 3


# ---------------------------------------------------------------------------
# Live rules
# ---------------------------------------------------------------------------

def test_live_rules_apply_immediately(client):
    code, s = _new(client)
    s.round._bust_votes = {"Ann": "bust"}
    st = _settings(client, code, rules_on=["side.bust_vote"], rules_off=["event.wild_card"])
    assert s.bust_vote_enabled and not s.wild_card_enabled
    assert s.round._bust_votes == {}
    assert st["bust_vote_enabled"] is True
    assert st["rules"]["queued"] is None


def test_a_live_toggle_after_queuing_is_not_undone_by_the_queue(client):
    code, s = _new(client)
    _settings(client, code, rules_off=["event.dealer_lottery"])
    _settings(client, code, bust_vote_enabled=True)   # the old pill toggle
    _newround(client, code)
    assert s.bust_vote_enabled
    assert not s.rules.on("event.dealer_lottery")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload, needle", [
    ({"rules_off": ["core.net_loss"]}, "part of the game"),
    ({"rules_on": ["core.dealer_rotation"]}, "part of the game"),
    ({"rules_off": ["ace.typo"]}, "Unknown rule"),
    ({"rules_on": "ace.hearts.player"}, "lists of rule IDs"),
    ({"rules_on": ["loss.doubled"], "rules_off": ["loss.doubled"]}, "on and off"),
    ({"rules_preset": "spicy"}, "Unknown preset"),
])
def test_bad_rule_payloads_are_rejected_and_change_nothing(client, payload, needle):
    code, s = _new(client)
    before = s.rules
    st = _settings(client, code, **payload)
    assert st["ok"] is False and needle in st["error"]
    assert s.rules == before and "rules" not in s._queued_settings


def test_non_admins_cannot_change_rules(client):
    code, s = _new(client)
    st = _settings(client, code, client_id="stranger", rules_off=["event.dealer_lottery"])
    assert st["ok"] is False
    assert "rules" not in s._queued_settings


# ---------------------------------------------------------------------------
# Live events finish on their own
# ---------------------------------------------------------------------------

def test_turning_off_targeted_drinking_does_not_cancel_a_running_one(client):
    code, s = _new(client)
    assert start_targeted_drinking(s, ["Ann"])
    _settings(client, code, rules_off=["event.targeted"])
    _newround(client, code)
    assert s._targeted_drinking_active
    assert not s.rules.on("event.targeted")
    # ...and it can't start again.
    s._targeted_drinking_active = False
    assert start_targeted_drinking(s, ["Ann"]) is False


# ---------------------------------------------------------------------------
# Room creation with a preset (Phase 4)
# ---------------------------------------------------------------------------

def _setup(c, **kw):
    code = c.post("/create_room").get_json()["code"]
    body = {"room_code": code, "client_id": "cid", "players": ["Rob", "Ann"],
            "dealer_index": 0, "mode": "digital", "drinking": True, **kw}
    return c.post("/setup", json=body).get_json(), game_sessions.get(code)


def test_setup_defaults_to_full_with_the_bust_vote_toggle(client):
    st, s = _setup(client)
    assert s.rules == FULL.with_changes(off=["side.bust_vote"])
    assert st["rules"]["preset"] == "full"
    st, s = _setup(client, bust_vote_enabled=True)
    assert s.rules == FULL


def test_setup_starts_a_starter_table(client):
    st, s = _setup(client, rules_preset="starter", bust_vote_enabled=True)
    assert st["rules"]["preset"] == "starter"
    assert not s.rules.on("ace.hearts.player") and not s.wild_card_enabled
    # The setup screen's bust-vote toggle still decides that one rule.
    assert s.bust_vote_enabled


def test_setup_rejects_an_unknown_preset(client):
    st, s = _setup(client, rules_preset="spicy")
    assert st["ok"] is False and "preset" in st["error"]


# ---------------------------------------------------------------------------
# State, registry, notice text
# ---------------------------------------------------------------------------

def test_state_rules_block_validates_and_resolves_dependencies(client):
    code, s = _new(client)
    s.rules = FULL.with_changes(off=["switch.hard"])
    st = client.get(f"/state?room_code={code}&client_id=cid").get_json()
    AppState(**st)
    assert "ace.clubs.dealer" in st["rules"]["enabled"]
    assert "ace.clubs.dealer" not in st["rules"]["effective"]
    assert st["rules"]["preset"] is None


def test_state_names_the_preset(client):
    code, s = _new(client)
    s.rules = STANDARD
    st = client.get(f"/state?room_code={code}&client_id=cid").get_json()
    assert st["rules"]["preset"] == "standard"


def test_rules_registry_lists_every_rule_in_order(client):
    resp = client.get("/rules_registry")
    data = resp.get_json()
    assert "max-age" in resp.headers["Cache-Control"]
    assert [r["id"] for r in data["rules"]] == [r.id for r in RULES]
    assert {g["id"] for g in data["groups"]} >= {r["group"] for r in data["rules"]}
    assert set(data["presets"]["starter"]) == STARTER.enabled
    ace = next(r for r in data["rules"] if r["id"] == "ace.clubs.dealer")
    assert ace["depends_on"] == ["switch.hard"] and ace["doc_anchor"]


def test_notice_names_a_few_rules_and_counts_many():
    assert describe_rule_diff(FULL, FULL) == ""
    one = describe_rule_diff(FULL, FULL.with_changes(off=["event.dealer_lottery"]))
    assert one == "📜 House rules changed: Dealer Lottery off"
    many = describe_rule_diff(STARTER, FULL)
    assert many.startswith("📜 House rules changed: ") and "rules on" in many
    # A child switched on while its parent stays off changes nothing visible.
    waiting = RuleSet(STARTER.enabled - {"switch.hard"})
    assert describe_rule_diff(waiting, waiting.with_changes(on=["ace.clubs.dealer"])) == ""
