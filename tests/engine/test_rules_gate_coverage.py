"""
Safety nets for the rule gates (CodeAudit-2026-10 G10, G11).

1. Every toggleable rule in the registry names the test that proves its gate
   ("off means off"). Adding a rule without a gate test fails here.
2. Every call into a rule-aware helper or event in app/ and engine/ passes the
   room's rules. These all default to FULL, so a missed ``rules=`` silently
   means "everything on" (that is how G3 happened).
"""
import ast
import inspect
from pathlib import Path

import pytest

import engine.drinking_rules as drinking_rules
import engine.events as events
from engine.rules_registry import RULES

ROOT = Path(__file__).resolve().parents[2]

# rule ID -> "test file::test name" of the test that switches the rule off.
_ENGINE = "tests/engine/test_rules_gates.py"
_APP    = "tests/app/test_rules_gates_app.py"
GATE_TESTS = {
    "table.split_tens":                _APP + "::test_split_tens_gate",
    "table.split_aces":                _APP + "::test_split_aces_gate",
    "table.split_ace_bj":              _APP + "::test_split_ace_21_is_a_plain_21_when_the_rule_is_off",
    "insurance.auto_cap":              _ENGINE + "::test_auto_insurance_cap_off_falls_through_to_normal_rules",
    "insurance.bj_vote":               _ENGINE + "::test_insurance_vote_off_resolves_as_decline",
    "switch.hard":                     _ENGINE + "::test_hard_switch_penalty_off",
    "ace.clubs.player":                _ENGINE + "::test_ace_rules_off_means_off",
    "ace.spades.player":               _ENGINE + "::test_ace_rules_off_means_off",
    "ace.hearts.player":               _ENGINE + "::test_ace_rules_off_means_off",
    "ace.diamonds.player":             _ENGINE + "::test_ace_rules_off_means_off",
    "ace.clubs.dealer":                _ENGINE + "::test_ace_clubs_dealer_sets_half_protection_only_with_rule_on",
    "ace.spades.dealer":               _ENGINE + "::test_ace_rules_off_means_off",
    "ace.hearts.dealer":               _ENGINE + "::test_ace_rules_off_means_off",
    "ace.diamonds.dealer":             _ENGINE + "::test_ace_rules_off_means_off",
    "dealer.suited_hand":              _ENGINE + "::test_dealer_suited_hand_off",
    "four_aces.first_deal":            _ENGINE + "::test_four_aces_first_deal_off",
    "four_aces.end_round":             _ENGINE + "::test_four_aces_end_round_off",
    "side.bust_vote":                  "tests/app/test_bust_vote.py::test_disabled_is_noop",
    "cards.devils_hand":               _APP + "::test_devils_hand_off",
    "cards.lucky_sevens":              _APP + "::test_lucky_sevens_off",
    "loss.doubled":                    _ENGINE + "::test_loss_doubled_off_scores_doubles_as_one",
    "loss.suited":                     _ENGINE + "::test_only_loss_doubled_on_adds_no_extra",
    "others.wins_all":                 _ENGINE + "::test_wins_all_off",
    "others.immunity.doubled":         _ENGINE + "::test_immunity_doubled_off",
    "others.immunity.split":           _ENGINE + "::test_immunity_split_off",
    "others.immunity.suited":          _ENGINE + "::test_immunity_suited_off",
    "bonus.blackjack":                 _ENGINE + "::test_blackjack_bonus_off",
    "bonus.blackjack.multipliers":     _ENGINE + "::test_blackjack_multipliers_off_is_flat",
    "five_card.player_21":             _ENGINE + "::test_five_card_player_21_handout_off",
    "five_card.player_win":            _ENGINE + "::test_five_card_player_win_off",
    "five_card.dealer_21":             _ENGINE + "::test_dealer_five_card_21_off",
    "sweep.same_suit":                 _ENGINE + "::test_sweep_same_suit_off",
    "sweep.all_21":                    _ENGINE + "::test_sweep_all_21_off",
    "milestone.handout":               _APP + "::test_milestone_handout_off",
    "milestone.back_to_back":          _APP + "::test_back_to_back_callout_off",
    "milestone.worst_average":         "tests/app/test_award_sips_round_avg.py::test_worst_average_penalty_off",
    "streak.l_badge":                  _APP + "::test_l_badge_off_means_no_badge_and_no_comeback_handout",
    "event.dealer_lottery":            _APP + "::test_lottery_trigger_off",
    "event.targeted":                  _APP + "::test_targeted_drinking_off_blocks_every_entry_point",
    "event.targeted.perfect_handout":  "tests/app/test_targeted_drinking.py::test_perfect_graduation_handout_off",
    "event.wild_card":                 "tests/app/test_wild_card.py::test_wild_card_off",
    "event.wild_card.targeted":        ("tests/app/test_wild_card.py::"
                                        "test_targeted_roll_falls_back_to_random_drink_when_the_rule_is_off"),
}


def _test_names(rel_path: str) -> set[str]:
    tree = ast.parse((ROOT / rel_path).read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")}


def test_every_toggleable_rule_has_a_gate_test():
    toggleable = {r.id for r in RULES if r.preset != "locked"}
    assert set(GATE_TESTS) == toggleable, (
        f"missing: {sorted(toggleable - set(GATE_TESTS))}, "
        f"unknown: {sorted(set(GATE_TESTS) - toggleable)}")


@pytest.mark.parametrize("rule_id", sorted(GATE_TESTS))
def test_the_named_gate_test_exists(rule_id):
    path, name = GATE_TESTS[rule_id].split("::")
    assert name in _test_names(path), f"{rule_id}: {GATE_TESTS[rule_id]} not found"


# ---------------------------------------------------------------------------
# Every call passes the room's rules
# ---------------------------------------------------------------------------

def _rules_aware_callables() -> dict[str, int]:
    """Name -> positional index of the ``rules`` parameter, for every event
    class and DrinkingRules helper that takes one."""
    found = {}
    candidates = [(n, o) for n, o in vars(events).items() if n.endswith("Event") and inspect.isclass(o)]
    candidates += list(vars(drinking_rules.DrinkingRules).items())
    candidates += [(n, getattr(drinking_rules, n)) for n in ("_bj_breakdown", "_bj_multiplier")]
    for name, obj in candidates:
        fn = obj.__func__ if isinstance(obj, staticmethod) else obj
        if not callable(fn):
            continue
        params = list(inspect.signature(fn).parameters)
        if "rules" in params:
            found[name] = params.index("rules")
    return found


def _scanned_files() -> list[Path]:
    files = sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "engine").glob("*.py"))
    return [f for f in files if f.name not in ("events.py", "rules_registry.py")]


def test_every_rule_aware_call_passes_rules():
    targets = _rules_aware_callables()
    assert {"CardDealtEvent", "RoundEndEvent", "check_four_aces", "_bj_multiplier"} <= targets.keys()
    missing = []
    for path in _scanned_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in targets:
                continue
            has_kw = any(k.arg == "rules" for k in node.keywords)
            if not has_kw and len(node.args) <= targets[name]:
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno} {name}(...)")
    assert not missing, "calls without rules=:\n" + "\n".join(missing)
