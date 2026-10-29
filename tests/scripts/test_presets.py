"""
tests/scripts/test_presets.py
=============================
House-rule presets outside the web app (RuleToggles-Implementation.md §4.3,
§6.3): the ``--preset`` flag shared by the terminal, referee and simulation
scripts, and the simulation smoke test that Starter really is gentler.
"""

import contextlib
import io

import pytest

from engine.rules_registry import FULL, STARTER
from scripts._cli import preset_arg, preset_rules
from scripts.simulation import run_simulation


def test_preset_flag_defaults_to_full_and_ignores_other_args():
    assert preset_arg([]) == "full"
    assert preset_arg(["3", "1", "--preset", "starter", "--personalities", "rob"]) == "starter"
    assert preset_rules(["--preset", "starter"]) == STARTER
    assert preset_rules([]) == FULL


def test_preset_flag_rejects_unknown_names():
    with pytest.raises(SystemExit):
        preset_arg(["--preset", "spicy"])


def _sips_per_round(preset, rounds=1500):
    with contextlib.redirect_stdout(io.StringIO()):
        player_sips, dealer_sips, *_ = run_simulation(
            num_players=3, num_decks=1, num_rounds=rounds, seed=11, preset=preset)
    total = sum(sum(d.values()) for d in list(player_sips.values()) + list(dealer_sips.values()))
    return total / rounds


def test_starter_runs_and_drinks_less_than_full():
    starter, full = _sips_per_round("starter"), _sips_per_round("full")
    assert 0 < starter < full
    # RuleToggles-StarterSet.md §6 target: Starter is about 50-65% of Full.
    # A short run is noisy, so only check it's clearly gentler.
    assert starter < 0.8 * full
