"""
scripts/snapshot.py -- save the current simulation output as a regression
snapshot for later comparison.

Copies scripts/simulation_results.txt and scripts/benchmarks.json into
scripts/snapshots/<players>p/<decks>deck/<label>/, so you can diff future
simulation runs against a known-good engine state. The config (player/deck
count) is read from the most-recently-generated entry in benchmarks.json.

Usage:
    python scripts/simulation.py          # generate fresh output first
    python scripts/snapshot.py [label] [--overwrite]    # save it as a snapshot

If no label is given, a timestamp (YYYYMMDD_HHMMSS) is used. An existing
snapshot with the same label is refused unless --overwrite is passed
(run_all_configs.py --snapshot always passes it).

To compare a later run against a snapshot:
    python scripts/simulation.py
    diff scripts/snapshots/<players>p/<decks>deck/<label>/simulation_results.txt scripts/simulation_results.txt
"""
import os
import sys
import json
import shutil
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(HERE, "snapshots")

FILES_TO_SNAPSHOT = ["simulation_results.txt", "benchmarks.json"]


def _latest_config(benchmarks_path):
    """Return the (players, decks) config of the most recently generated
    entry in benchmarks.json."""
    with open(benchmarks_path, encoding="utf-8") as f:
        all_benchmarks = json.load(f)
    if not all_benchmarks:
        print("Error: benchmarks.json is empty.")
        sys.exit(1)
    latest_key = max(all_benchmarks, key=lambda k: all_benchmarks[k].get("generated", ""))
    cfg = all_benchmarks[latest_key].get("config", {})
    return cfg.get("num_players"), cfg.get("num_decks"), latest_key


def main():
    args = [a for a in sys.argv[1:] if a != "--overwrite"]
    overwrite = "--overwrite" in sys.argv[1:]
    label = args[0] if args else datetime.now().strftime("%Y%m%d_%H%M%S")

    benchmarks_path = os.path.join(HERE, "benchmarks.json")
    missing = [f for f in FILES_TO_SNAPSHOT if not os.path.exists(os.path.join(HERE, f))]
    if missing:
        print("Error: missing simulation output files: " + ", ".join(missing))
        print("Run `python scripts/simulation.py` first.")
        sys.exit(1)

    num_players, num_decks, config_key = _latest_config(benchmarks_path)
    if num_players is None or num_decks is None:
        print("Error: could not determine player/deck config from benchmarks.json.")
        sys.exit(1)

    dest_dir = os.path.join(SNAPSHOTS_DIR, f"{num_players}p", f"{num_decks}deck", label)

    if os.path.exists(dest_dir):
        if not overwrite:
            print(f"Error: snapshot '{label}' already exists at {dest_dir} (use --overwrite to replace it)")
            sys.exit(1)
        # Overwrite the files in place: deleting the folder fails on Windows
        # when OneDrive / Explorer holds a handle on it.
        print(f"Replacing existing snapshot '{label}'.")

    os.makedirs(dest_dir, exist_ok=True)
    for f in FILES_TO_SNAPSHOT:
        shutil.copy2(os.path.join(HERE, f), os.path.join(dest_dir, f))

    print(f"Snapshot saved -> {dest_dir}  [{config_key}]")
    for f in FILES_TO_SNAPSHOT:
        print(f"  - {f}")


if __name__ == "__main__":
    main()
