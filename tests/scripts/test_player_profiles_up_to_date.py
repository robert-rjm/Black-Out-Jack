"""
tests/scripts/test_player_profiles_up_to_date.py
===================================================
Schema-conformance check for the committed engine/player_profiles/*.json
bot profiles: catches drift between what scripts/build_player_profiles.py
currently produces (and what engine/style_strategy.py currently reads) and
what's actually committed to disk -- e.g. a profile generated before a
schema change (a new required field, a renamed key) that was never
regenerated afterward.

This is NOT a data-freshness check (whether newer decision logs exist in
data/decisions/ that haven't been mined in yet) -- that data is gitignored
and local-only, so a repo-level test has no way to know about it. If a
test here fails, the fix is almost always the hint printed in the
assertion message: re-run scripts/build_player_profiles.py.
"""

import json
from pathlib import Path

import pytest

from engine.style_strategy import _profiles_dir, best_play_for, decide_dealer_lottery_stake
from tests.conftest import make_card, make_hand

_PROFILE_TOP_LEVEL_KEYS = {
    "player", "generated", "source_decisions", "thresholds",
    "deviations", "lottery_stakes",
}
# Required because engine/style_strategy.py's _build_index() reads these
# via direct d[...] indexing -- a missing one is a KeyError at decision time,
# not a graceful fallback.
_DEVIATION_REQUIRED_KEYS = {
    "hand_total", "is_soft", "dealer_upcard_rank", "can_split",
    "can_double", "player_action",
}
_LOTTERY_STAKE_REQUIRED_KEYS = {"owed_bucket", "avg_stake", "samples"}
_VALID_OWED_BUCKETS = {"none", "low", "high"}  # engine/style_strategy.py's _owed_bucket()


def _regen_hint(name: str) -> str:
    return f"Regenerate with: python scripts/build_player_profiles.py --player {name}"


def _profile_paths() -> list[Path]:
    return sorted(_profiles_dir().glob("*.json"))


@pytest.mark.parametrize("path", _profile_paths(), ids=lambda p: p.stem)
def test_profile_is_valid_json(path):
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"{path.name} is not valid JSON: {exc}\n{_regen_hint(path.stem)}")


@pytest.mark.parametrize("path", _profile_paths(), ids=lambda p: p.stem)
def test_profile_has_expected_top_level_shape(path):
    profile = json.loads(path.read_text(encoding="utf-8"))
    actual_keys = set(profile.keys())
    assert actual_keys == _PROFILE_TOP_LEVEL_KEYS, (
        f"{path.name} has keys {sorted(actual_keys)}, expected exactly "
        f"{sorted(_PROFILE_TOP_LEVEL_KEYS)} "
        f"(missing: {sorted(_PROFILE_TOP_LEVEL_KEYS - actual_keys)}, "
        f"unexpected: {sorted(actual_keys - _PROFILE_TOP_LEVEL_KEYS)}).\n"
        f"This means the file predates a schema change in "
        f"scripts/build_player_profiles.py. {_regen_hint(path.stem)}"
    )
    assert isinstance(profile["deviations"], list), f"{path.name}: deviations must be a list"
    assert isinstance(profile["lottery_stakes"], list), f"{path.name}: lottery_stakes must be a list"
    missing_thresholds = {"min_samples", "min_majority"} - set(profile["thresholds"].keys())
    assert not missing_thresholds, (
        f"{path.name}: thresholds missing {sorted(missing_thresholds)}. {_regen_hint(path.stem)}"
    )


@pytest.mark.parametrize("path", _profile_paths(), ids=lambda p: p.stem)
def test_profile_deviations_have_required_fields(path):
    profile = json.loads(path.read_text(encoding="utf-8"))
    for i, d in enumerate(profile["deviations"]):
        missing = _DEVIATION_REQUIRED_KEYS - set(d.keys())
        assert not missing, (
            f"{path.name} deviations[{i}] is missing {sorted(missing)} -- "
            f"engine/style_strategy.py's _build_index() reads these directly "
            f"and will KeyError on a real decision. {_regen_hint(path.stem)}"
        )


@pytest.mark.parametrize("path", _profile_paths(), ids=lambda p: p.stem)
def test_profile_lottery_stakes_have_required_fields(path):
    profile = json.loads(path.read_text(encoding="utf-8"))
    for i, s in enumerate(profile["lottery_stakes"]):
        missing = _LOTTERY_STAKE_REQUIRED_KEYS - set(s.keys())
        assert not missing, (
            f"{path.name} lottery_stakes[{i}] is missing {sorted(missing)}. "
            f"{_regen_hint(path.stem)}"
        )
        assert s["owed_bucket"] in _VALID_OWED_BUCKETS, (
            f"{path.name} lottery_stakes[{i}] has owed_bucket={s['owed_bucket']!r}, "
            f"expected one of {sorted(_VALID_OWED_BUCKETS)}. {_regen_hint(path.stem)}"
        )


@pytest.mark.parametrize("path", _profile_paths(), ids=lambda p: p.stem)
def test_profile_resolves_without_error(path):
    """Functional smoke test: the profile actually drives a real decision
    through the current resolver code without crashing -- catches type
    drift (e.g. a stringified number) that a pure key-presence check would
    miss."""
    profile = json.loads(path.read_text(encoding="utf-8"))

    hand = make_hand(("6", "S"), ("7", "H"))
    dealer_up = make_card("7", "D")
    try:
        action = best_play_for(profile, hand, dealer_up, ["h", "s", "d"])
    except Exception as exc:
        pytest.fail(f"{path.name}: best_play_for raised {exc!r}. {_regen_hint(path.stem)}")
    assert action in ("h", "s", "d")

    try:
        stake = decide_dealer_lottery_stake(profile, current_owed=0)
    except Exception as exc:
        pytest.fail(f"{path.name}: decide_dealer_lottery_stake raised {exc!r}. {_regen_hint(path.stem)}")
    assert 0 <= stake <= 5
