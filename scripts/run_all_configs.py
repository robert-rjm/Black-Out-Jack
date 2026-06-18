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
"""
import sys
import subprocess
import argparse
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--players", type=int, nargs="+", default=[2, 3, 4])
    parser.add_argument("--decks", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--snapshot", nargs="?", const="baseline", default=None,
                         help="Also save a snapshot for each config, labeled "
                              "'<label>_<players>p_<decks>d' (default label: 'baseline')")
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

    for p, d in configs:
        print(f"\n=== {p}p_{d}d ===")
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "simulation.py"), str(p), str(d)]
        )
        if result.returncode != 0:
            print(f"Error: simulation failed for {p}p_{d}d (exit {result.returncode})")
            sys.exit(result.returncode)

        if args.snapshot is not None:
            label = f"{args.snapshot}_{p}p_{d}d"
            snap_result = subprocess.run(
                [sys.executable, os.path.join(HERE, "snapshot.py"), label]
            )
            if snap_result.returncode != 0:
                print(f"Error: snapshot failed for {p}p_{d}d (exit {snap_result.returncode})")
                sys.exit(snap_result.returncode)


if __name__ == "__main__":
    main()
