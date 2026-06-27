"""
tests/test_regression_snapshots.py
===================================
Test-Plan.md §7 — regression against `scripts/snapshots/.../benchmarks.json`.

Runs a smaller, seeded simulation for a sample of snapshotted configs and
checks the resulting rates / per-rule sip averages are statistically
consistent with the 100k-round baselines. These are NOT exact-match
targets -- tolerances are derived from the baseline's `std_sips_per_round`
(with a flat relative floor for low-frequency rules).
"""

import io
import os
import json
import math
import contextlib
from collections import defaultdict

import pytest

from scripts.simulation import run_simulation, classify_rule  # noqa: F401  (re-export check)

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS = os.path.join(HERE, "..", "..", "scripts", "snapshots")

# (num_players, num_decks, seed) -- one config sampled per player count to
# keep runtime reasonable while still covering 2p/3p/4p tables.
SAMPLE_CONFIGS = [
    (2, 1, 1001),
    (3, 1, 1002),
    (4, 2, 1003),
]

NUM_ROUNDS = 3000


def _snapshot_path(num_players, num_decks):
    label = f"baseline_{num_players}p_{num_decks}d"
    return os.path.join(SNAPSHOTS, f"{num_players}p", f"{num_decks}deck", label, "benchmarks.json")


def _load_baseline(num_players, num_decks):
    path = _snapshot_path(num_players, num_decks)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get(f"{num_players}p_{num_decks}d")


def _compute_benchmarks(player_sips, dealer_sips, hand_totals, dealer_bust_rounds,
                         std_sips_per_round, num_rounds, player_names):
    """Mirror scripts/simulation.py::write_benchmarks, but parameterized
    (no module-level globals) and returned as a dict instead of written
    to disk."""
    hands = hand_totals["hands"]

    rule_totals = defaultdict(int)
    for name in player_names:
        for rule, s in player_sips[name].items():
            rule_totals[rule] += s
        for rule, s in dealer_sips[name].items():
            rule_totals[rule] += s

    def pct(n, d):
        return round(n / d * 100, 1) if d else None

    return {
        "blackjack_rate_pct": pct(hand_totals["blackjacks"], hands),
        "bust_rate_pct":      pct(hand_totals["busts"], hands),
        "win_rate_pct":       pct(hand_totals["wins"], hands),
        "loss_rate_pct":      pct(hand_totals["losses"], hands),
        "push_rate_pct":      pct(hand_totals["pushes"], hands),
        "dealer_bust_pct":    pct(dealer_bust_rounds, num_rounds),
        "avg_sips_per_round": round(sum(rule_totals.values()) / num_rounds, 3),
        "sips_per_round_by_rule": {
            rule: round(total / num_rounds, 4) for rule, total in rule_totals.items()
        },
    }


def _rate_tol(baseline_pct):
    """Tolerance band for a percentage-rate stat."""
    if baseline_pct is None:
        return None
    return max(3.0, 0.15 * baseline_pct)


def _rule_tol(baseline_val, std, n_new):
    """Tolerance band for a per-rule sips/round stat."""
    stat_tol = 3 * (std / math.sqrt(n_new)) if std else 0.0
    return max(stat_tol, 0.25 * baseline_val, 0.05)


@pytest.mark.parametrize("num_players,num_decks,seed", SAMPLE_CONFIGS)
def test_regression_against_snapshot(num_players, num_decks, seed):
    baseline = _load_baseline(num_players, num_decks)
    if baseline is None:
        pytest.skip(f"No snapshot for {num_players}p_{num_decks}d")

    player_names = [f"Player{i + 1}" for i in range(num_players)]

    with contextlib.redirect_stdout(io.StringIO()):
        (player_sips, dealer_sips, event_log, hand_totals,
         dealer_bust_rounds, std_sips_per_round) = run_simulation(
            num_players=num_players, num_decks=num_decks,
            num_rounds=NUM_ROUNDS, seed=seed,
        )

    new = _compute_benchmarks(
        player_sips, dealer_sips, hand_totals, dealer_bust_rounds,
        std_sips_per_round, NUM_ROUNDS, player_names,
    )

    std = baseline["std_sips_per_round"]

    # --- overall rates -----------------------------------------------------
    for key in ("blackjack_rate_pct", "bust_rate_pct", "dealer_bust_pct",
                 "win_rate_pct", "loss_rate_pct", "push_rate_pct"):
        base_val = baseline[key]
        tol = _rate_tol(base_val)
        new_val = new[key]
        assert abs(new_val - base_val) <= tol, (
            f"{key}: new={new_val} baseline={base_val} tol={tol}"
        )

    # --- avg sips per round -------------------------------------------------
    base_avg = baseline["avg_sips_per_round"]
    tol_avg = _rule_tol(base_avg, std, NUM_ROUNDS)
    assert abs(new["avg_sips_per_round"] - base_avg) <= tol_avg, (
        f"avg_sips_per_round: new={new['avg_sips_per_round']} "
        f"baseline={base_avg} tol={tol_avg}"
    )

    # --- per-rule sips per round ---------------------------------------------
    base_rules = baseline["sips_per_round_by_rule"]
    new_rules  = new["sips_per_round_by_rule"]

    for rule, base_val in base_rules.items():
        tol = _rule_tol(base_val, std, NUM_ROUNDS)
        new_val = new_rules.get(rule, 0.0)
        # Only flag a rule as "missing" if the baseline rate implies we'd
        # expect to see it at least a handful of times in NUM_ROUNDS.
        if rule not in new_rules and base_val * NUM_ROUNDS >= 5:
            pytest.fail(f"Rule '{rule}' present in baseline (~{base_val}/round) "
                        f"but absent from new run of {NUM_ROUNDS} rounds")
        assert abs(new_val - base_val) <= tol, (
            f"sips_per_round_by_rule[{rule!r}]: new={new_val} "
            f"baseline={base_val} tol={tol}"
        )

    # Any brand-new rule the baseline doesn't know about at all -> classify_rule
    # likely changed; surface it loudly rather than silently passing.
    unexpected = set(new_rules) - set(base_rules)
    assert not unexpected, (
        f"New rule key(s) not present in baseline: {sorted(unexpected)}"
    )
