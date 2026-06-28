"""
scripts/build_player_profiles.py
==================================
Build per-player deviation tables from accumulated decision-log CSVs and
write them to engine/player_profiles/<name>.json.

Usage:
    python scripts/build_player_profiles.py [--dir data/decisions] [--out engine/player_profiles]
    python scripts/build_player_profiles.py --player Rob  # one player only

Thresholds (adjustable via flags):
    --min-samples   Minimum decisions at a spot to record anything  (default: 3)
    --min-majority  Minimum fraction for the majority action         (default: 0.60)

Only deviations from basic_strategy_action are stored; spots where the player
agrees with basic strategy are omitted (the fallback handles those).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rank(card_str: str) -> str:
    """Extract rank from a card string like '7♣', 'J♦', '10♥', 'A♠'."""
    # Suits are single unicode chars; strip the last character.
    return card_str[:-1] if card_str else ""


def _load_csvs(directory: str) -> list[dict]:
    rows = []
    d = Path(directory)
    for path in sorted(d.glob("decision_log_*.csv")):
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        print(f"  loaded {path.name}")
    return rows


def _parse_bool(val: str) -> bool:
    return val.strip().lower() == "true"


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def build_profile(rows: list[dict], player_name: str,
                  min_samples: int = 3, min_majority: float = 0.60) -> dict:
    """
    Return a profile dict for one player.

    Groups decisions by (hand_total, is_soft, dealer_upcard_rank, can_split,
    can_double) and records a deviation entry where the player's majority
    action differs from basic_strategy_action and meets the thresholds.
    """
    # Filter: this player, human only, non-insurance, has a basic_strategy_action
    player_rows = [
        r for r in rows
        if r["player"].strip().lower() == player_name.lower()
        and not _parse_bool(r.get("is_npc", "False"))
        and r.get("action_taken", "") not in ("insurance", "decline")
        and r.get("basic_strategy_action", "").strip()
    ]

    # Group by lookup key
    groups: dict[tuple, list[str]] = defaultdict(list)
    basic_for_key: dict[tuple, str] = {}

    for r in player_rows:
        valid = r.get("valid_actions", "")
        can_split  = "sp" in valid
        can_double = "d"  in valid
        try:
            total = int(r["hand_total_before"])
        except (ValueError, KeyError):
            continue
        is_soft     = _parse_bool(r.get("is_soft", "False"))
        dealer_rank = _rank(r.get("dealer_upcard", "").strip())
        if not dealer_rank:
            continue
        action  = r["action_taken"].strip()
        bs_action = r["basic_strategy_action"].strip()

        key = (total, is_soft, dealer_rank, can_split, can_double)
        groups[key].append(action)
        basic_for_key[key] = bs_action  # same for any row at this key

    # Build deviation entries
    deviations = []
    for key, actions in groups.items():
        n = len(actions)
        if n < min_samples:
            continue
        counts: dict[str, int] = defaultdict(int)
        for a in actions:
            counts[a] += 1
        majority_action = max(counts, key=lambda a: counts[a])
        majority_frac   = counts[majority_action] / n
        if majority_frac < min_majority:
            continue
        bs = basic_for_key[key]
        if majority_action == bs:
            continue  # agrees with basic strategy — no deviation to store

        total, is_soft, dealer_rank, can_split, can_double = key
        deviations.append({
            "hand_total":        total,
            "is_soft":           is_soft,
            "dealer_upcard_rank": dealer_rank,
            "can_split":         can_split,
            "can_double":        can_double,
            "basic_strategy":    bs,
            "player_action":     majority_action,
            "samples":           n,
            "majority":          round(majority_frac, 3),
            "action_counts":     dict(counts),
        })

    deviations.sort(key=lambda d: (d["hand_total"], d["is_soft"],
                                   d["dealer_upcard_rank"]))

    return {
        "player":           player_name,
        "generated":        str(date.today()),
        "source_decisions": len(player_rows),
        "thresholds": {
            "min_samples":  min_samples,
            "min_majority": min_majority,
        },
        "deviations": deviations,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build player deviation profiles.")
    parser.add_argument("--dir",          default="data/decisions",
                        help="Directory containing decision_log_*.csv files")
    parser.add_argument("--out",          default="engine/player_profiles",
                        help="Output directory for <name>.json profiles")
    parser.add_argument("--player",       default=None,
                        help="Build profile for one player only")
    parser.add_argument("--min-samples",  type=int,   default=3)
    parser.add_argument("--min-majority", type=float, default=0.60)
    args = parser.parse_args()

    print(f"Loading decision logs from {args.dir} ...")
    rows = _load_csvs(args.dir)
    if not rows:
        print("No rows loaded — check --dir path.")
        sys.exit(1)

    # Discover players
    all_players = sorted({r["player"].strip() for r in rows
                          if not _parse_bool(r.get("is_npc", "False"))})
    targets = [args.player] if args.player else all_players

    os.makedirs(args.out, exist_ok=True)

    for name in targets:
        profile = build_profile(rows, name, args.min_samples, args.min_majority)
        n_dev   = len(profile["deviations"])
        out_path = Path(args.out) / f"{name.lower()}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        print(f"\n{name}: {profile['source_decisions']} decisions, "
              f"{n_dev} deviation(s) recorded → {out_path}")
        for d in profile["deviations"]:
            hand_desc = f"{'soft' if d['is_soft'] else 'hard'} {d['hand_total']}"
            flags = []
            if d["can_split"]:  flags.append("splittable")
            if d["can_double"]: flags.append("doubling available")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {hand_desc} vs {d['dealer_upcard_rank']}{flag_str}: "
                  f"{d['basic_strategy']} → {d['player_action']} "
                  f"({d['samples']} samples, {d['majority']*100:.0f}%)")


if __name__ == "__main__":
    main()
