"""
scripts/run_all_configs.py -- run scripts/simulation.py for a batch of
player/deck configs without manual prompts.

Usage:
    python scripts/run_all_configs.py
    python scripts/run_all_configs.py --players 2 3 4 --decks 1 2 3 4

Each (players, decks) combination is run as:
    python scripts/simulation.py <players> <decks>

which merges its result into scripts/benchmarks.json and
static/js/benchmarks.js under the "<players>p_<decks>d" key (existing
entries for other configs are preserved).

With --snapshot [label], each config is also saved via:
    python scripts/snapshot.py <label>_<players>p_<decks>d

into scripts/snapshots/<players>p/<decks>deck/<label>_<players>p_<decks>d/.

With --compare <label>, each config is run and then compared against the
named snapshot. Metrics that deviate by more than their threshold are
flagged. Exit code is 1 if any deviation is found.
"""
import sys
import json
import subprocess
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Metrics to compare and their maximum allowed relative deviation (0.05 = 5%).
# Sip rate is tighter because it's the primary correctness signal; hand-outcome
# rates are noisier so they get a slightly looser threshold.
COMPARE_THRESHOLDS = {
    "avg_sips_per_round": 0.03,
    "blackjack_rate_pct": 0.05,
    "bust_rate_pct":      0.05,
    "win_rate_pct":       0.05,
    "loss_rate_pct":      0.05,
    "push_rate_pct":      0.05,
    "dealer_bust_pct":    0.05,
}


def _compare_with_snapshot(config_key, snapshot_label, num_players, num_decks):
    """Compare the just-written benchmarks.json entry against a snapshot.

    Returns True if all metrics are within threshold, False if any deviate.
    """
    snap_dir = os.path.join(
        HERE, "snapshots",
        f"{num_players}p", f"{num_decks}deck",
        f"{snapshot_label}_{config_key}",
    )
    snap_benchmarks = os.path.join(snap_dir, "benchmarks.json")

    if not os.path.exists(snap_benchmarks):
        print(f"  [compare] No snapshot at {snap_benchmarks} — skipping.")
        return True

    with open(snap_benchmarks, encoding="utf-8") as f:
        snap_all = json.load(f)
    with open(os.path.join(HERE, "benchmarks.json"), encoding="utf-8") as f:
        curr_all = json.load(f)

    snap_cfg = snap_all.get(config_key, {})
    curr_cfg = curr_all.get(config_key, {})
    if not snap_cfg or not curr_cfg:
        print(f"  [compare] Config '{config_key}' missing from benchmark file — skipping.")
        return True

    deviations = []
    for metric, threshold in COMPARE_THRESHOLDS.items():
        snap_val = snap_cfg.get(metric)
        curr_val = curr_cfg.get(metric)
        if snap_val is None or curr_val is None or snap_val == 0:
            continue
        rel_diff = (curr_val - snap_val) / abs(snap_val)
        if abs(rel_diff) > threshold:
            deviations.append((metric, snap_val, curr_val, rel_diff))

    if deviations:
        print(f"  [compare] *** DEVIATIONS in {config_key} (vs '{snapshot_label}') ***")
        for metric, snap_val, curr_val, rel_diff in deviations:
            arrow = "▲" if rel_diff > 0 else "▼"
            print(f"    {arrow} {metric:<24}  snapshot={snap_val:.3f}  now={curr_val:.3f}"
                  f"  ({rel_diff*100:+.1f}%  threshold=±{COMPARE_THRESHOLDS[metric]*100:.0f}%)")
        return False

    print(f"  [compare] {config_key}: all metrics within threshold ✓")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", type=int, nargs="+", default=[2, 3, 4])
    parser.add_argument("--decks", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--snapshot", nargs="?", const="baseline", default=None,
                         help="Save a snapshot for each config after running it "
                              "(default label: 'baseline')")
    parser.add_argument("--compare", default=None, metavar="LABEL",
                         help="After each simulation, compare results against the "
                              "named snapshot. Flags metrics that deviate beyond "
                              "their threshold and exits with code 1 if any do.")
    args = parser.parse_args()

    # 4+ players with 1 deck reshuffles constantly mid-round; results are
    # meaningless. Enforce a minimum of 2 decks for 4+ players.
    MIN_DECKS_FOR_PLAYERS = 2  # applies when player count >= 4
    skipped = [(p, d) for p in args.players for d in args.decks
               if p >= 4 and d < MIN_DECKS_FOR_PLAYERS]
    if skipped:
        print("Skipping thin configs (< 2 decks for 4+ players): "
              + ", ".join(f"{p}p_{d}d" for p, d in skipped))
    configs = [(p, d) for p in args.players for d in args.decks
               if not (p >= 4 and d < MIN_DECKS_FOR_PLAYERS)]
    print(f"Running {len(configs)} configs: "
          + ", ".join(f"{p}p_{d}d" for p, d in configs))

    any_deviation = False

    for p, d in configs:
        config_key = f"{p}p_{d}d"
        print(f"\n=== {config_key} ===")
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "simulation.py"), str(p), str(d)]
        )
        if result.returncode != 0:
            print(f"Error: simulation failed for {config_key} (exit {result.returncode})")
            sys.exit(result.returncode)

        if args.compare is not None:
            ok = _compare_with_snapshot(config_key, args.compare, p, d)
            if not ok:
                any_deviation = True

        if args.snapshot is not None:
            label = f"{args.snapshot}_{config_key}"
            snap_result = subprocess.run(
                [sys.executable, os.path.join(HERE, "snapshot.py"), label]
            )
            if snap_result.returncode != 0:
                print(f"Error: snapshot failed for {config_key} (exit {snap_result.returncode})")
                sys.exit(snap_result.returncode)

    if any_deviation:
        print("\n*** One or more configs deviated from the snapshot. ***")
        sys.exit(1)
    elif args.compare is not None:
        print("\nAll configs match the snapshot.")


if __name__ == "__main__":
    main()
