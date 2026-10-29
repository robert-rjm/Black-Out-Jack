"""
Tests for engine/rules_registry.py: registry consistency, RuleSet semantics
and the doc / CSV-label links (RuleToggles-Implementation §6.1).
"""
import ast
import re
from pathlib import Path

import pytest

from engine import rules_registry as reg
from engine.rules_registry import (
    DEFAULT_RULES, FULL, LOCKED, PRESETS, RULES, RULES_BY_ID, STANDARD, STARTER, RuleSet,
)

ROOT = Path(__file__).resolve().parents[2]


def _slug(text: str) -> str:
    """Python twin of static/js/ui/rules.js `_ruleSlug`."""
    return re.sub(r"[^a-z0-9_\- ]", "", text.lower().strip()).replace(" ", "-")


def _rules_md_slugs() -> set[str]:
    slugs: set[str] = set()
    seen: dict[str, int] = {}
    for line in (ROOT / "docs" / "Rules.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"#{1,4}\s+(.*)", line)
        if not m:
            continue
        base = _slug(re.sub(r"<[^>]+>", "", m.group(1)))
        if not base:
            continue
        seen[base] = seen.get(base, 0) + 1
        slugs.add(base if seen[base] == 1 else f"{base}-{seen[base] - 1}")
    return slugs


def _classify_rule_outputs() -> set[str]:
    tree = ast.parse((ROOT / "app" / "services" / "utils.py").read_text(encoding="utf-8"))
    return {n.value.value for n in ast.walk(tree)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_validates_at_import():
    reg._validate()   # raises if anything is inconsistent


def test_registry_has_all_catalog_rules():
    assert len(RULES) == 44


def test_presets_are_nested_and_full_is_everything():
    assert LOCKED <= PRESETS["starter"] <= PRESETS["standard"] <= PRESETS["full"]
    assert PRESETS["full"] == frozenset(RULES_BY_ID)


def test_starter_matches_the_starter_doc():
    assert PRESETS["starter"] == {
        "core.net_loss", "core.dealer_rotation", "table.split_tens", "loss.doubled",
        "bonus.blackjack", "others.wins_all", "switch.hard", "insurance.auto_cap",
        "milestone.handout", "milestone.back_to_back",
    }


def test_unlock_steps_run_one_to_twenty_two_without_gaps():
    steps = sorted({r.unlock_step for r in RULES if r.unlock_step is not None})
    assert steps == list(range(1, 23))


def test_every_csv_label_is_a_real_classify_rule_output():
    outputs = _classify_rule_outputs()
    for r in RULES:
        for label in r.csv_labels:
            assert label in outputs, f"{r.id}: {label!r} is not a classify_rule() output"


def test_every_doc_anchor_is_a_rules_md_heading():
    slugs = _rules_md_slugs()
    for r in RULES:
        assert r.doc_anchor in slugs, f"{r.id}: #{r.doc_anchor} is not a Rules.md heading"


def test_live_rules_are_bust_vote_and_wild_card():
    assert {r.id for r in RULES if r.live} == {"side.bust_vote", "event.wild_card"}


# ---------------------------------------------------------------------------
# RuleSet
# ---------------------------------------------------------------------------

def test_full_has_everything_on():
    assert all(FULL.on(r.id) for r in RULES)
    assert FULL.preset == "full"


def test_locked_rules_are_always_on():
    empty = RuleSet(frozenset())
    assert all(empty.on(i) for i in LOCKED)
    assert not empty.on("ace.hearts.player")


def test_child_reads_off_when_parent_is_off():
    rs = FULL.with_changes(off=["switch.hard"])
    assert "ace.clubs.dealer" in rs.enabled
    assert not rs.on("ace.clubs.dealer")


def test_child_comes_back_with_its_parent():
    rs = FULL.with_changes(off=["switch.hard"]).with_changes(on=["switch.hard"])
    assert rs.on("ace.clubs.dealer")


def test_wild_card_targeted_needs_both_parents():
    assert not FULL.with_changes(off=["event.targeted"]).on("event.wild_card.targeted")
    assert not FULL.with_changes(off=["event.wild_card"]).on("event.wild_card.targeted")


def test_on_raises_on_unknown_id():
    with pytest.raises(KeyError):
        FULL.on("ace.heart.player")


def test_locked_rule_cannot_be_turned_off():
    with pytest.raises(ValueError):
        FULL.with_changes(off=["core.net_loss"])


def test_unknown_ids_are_rejected():
    with pytest.raises(ValueError):
        FULL.with_changes(off=["nope"])
    with pytest.raises(ValueError):
        RuleSet(frozenset({"nope"}))


def test_preset_label_follows_the_set():
    assert STARTER.with_changes(on=["ace.hearts.player"]).preset is None
    assert FULL.with_changes(off=["ace.hearts.player"]).preset is None
    custom = STANDARD.with_changes(on=["event.dealer_lottery"])
    assert custom.preset is None
    assert custom.with_changes(off=["event.dealer_lottery"]).preset == "standard"


def test_rule_sets_are_hashable_and_equal_by_content():
    assert RuleSet.from_preset("full") == FULL
    assert len({FULL, RuleSet.from_preset("full")}) == 1


def test_a_set_built_from_ids_matches_its_preset():
    # Locked rules are implied, and the preset label comes from the content.
    rs = RuleSet(PRESETS["starter"] - LOCKED)
    assert rs == STARTER and rs.preset == "starter" and hash(rs) == hash(STARTER)
    assert RuleSet(frozenset(r.id for r in RULES)) == FULL


def test_waiting_on_parent_lists_children_of_off_parents():
    rs = FULL.with_changes(off=["switch.hard"])
    assert rs.waiting_on_parent() == {"ace.clubs.dealer"}
    assert FULL.waiting_on_parent() == frozenset()


# ---------------------------------------------------------------------------
# Room default
# ---------------------------------------------------------------------------

def test_default_rules_are_full_minus_bust_vote():
    assert not DEFAULT_RULES.on("side.bust_vote")
    assert DEFAULT_RULES.enabled == FULL.enabled - {"side.bust_vote"}
    assert DEFAULT_RULES.on("event.wild_card")


def test_game_room_flags_read_and_write_the_ruleset():
    from app.models.game_room import GameConfig, GameRoom
    from engine.referee import RefereeSession
    from tests.conftest import make_player

    players = [make_player("Alice"), make_player("Bob")]
    players[0].is_dealer = True
    room = GameRoom(session=RefereeSession(players, "Alice", wager=1, num_hands=1),
                    config=GameConfig(mode="digital"))
    assert room.bust_vote_enabled is False and room.wild_card_enabled is True

    room.bust_vote_enabled = True
    room.wild_card_enabled = False
    assert room.config.rules.on("side.bust_vote")
    assert not room.config.rules.on("event.wild_card")
    assert room.bust_vote_enabled is True and room.wild_card_enabled is False
