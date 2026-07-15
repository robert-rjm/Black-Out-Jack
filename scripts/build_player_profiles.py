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

# Repo root on sys.path so we can reuse the table_bias/owed-sips bucket
# thresholds from engine/style_strategy.py instead of re-deriving them here.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.style_strategy import _table_bias_bucket as _bias_bucket  # noqa: E402
from engine.style_strategy import _owed_bucket  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rank(card_str: str) -> str:
    """Extract rank from a card string like '7♣', 'J♦', '10♥', 'A♠'."""
    # Suits are single unicode chars; strip the last character.
    return card_str[:-1] if card_str else ""


def _hand_index(row: dict) -> int:
    try:
        return int(row.get("hand_index") or 0)
    except ValueError:
        return 0


def _majority(actions: list[str]) -> tuple[str, float, dict[str, int]]:
    """Return (majority_action, majority_fraction, action_counts) for a list
    of action strings."""
    counts: dict[str, int] = defaultdict(int)
    for a in actions:
        counts[a] += 1
    majority_action = max(counts, key=lambda a: counts[a])
    return majority_action, counts[majority_action] / len(actions), dict(counts)


def _load_csvs(directory: str, pattern: str = "decision_log_*.csv") -> list[dict]:
    rows = []
    d = Path(directory)
    for path in sorted(d.glob(pattern)):
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

    Also groups the same decisions by that same key *plus* table_bias
    (bucketed from the row's visible_cards) and sibling_awaiting_deal
    (whether another of the player's hands this round, from a split, was
    still undealt at decision time). A table-aware deviation is only kept
    when its majority action differs from what the coarser (plain 5-field)
    grouping would already produce -- otherwise the extra context is noise
    and the coarser deviation (or basic strategy) already covers the spot.
    """
    # Filter: this player, human only, non-insurance, has a basic_strategy_action
    player_rows = [
        r for r in rows
        if r["player"].strip().lower() == player_name.lower()
        and not _parse_bool(r.get("is_npc", "False"))
        and r.get("action_taken", "") not in ("insurance", "decline")
        and r.get("basic_strategy_action", "").strip()
    ]

    # A hand_index greater than this row's own, anywhere in the same round
    # for this player, means that hand was still undealt (1 card, from a
    # split) at the moment of this decision -- splits are dealt and played
    # strictly in hand_index order (see engine/style_strategy.py's
    # _sibling_awaiting_deal docstring for why).
    max_hand_index_by_round: dict[str, int] = defaultdict(int)
    for r in player_rows:
        rnd = r.get("round", "")
        max_hand_index_by_round[rnd] = max(max_hand_index_by_round[rnd], _hand_index(r))

    groups: dict[tuple, list[str]] = defaultdict(list)
    basic_for_key: dict[tuple, str] = {}
    fine_groups: dict[tuple, list[str]] = defaultdict(list)
    fine_basic_for_key: dict[tuple, str] = {}

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
        action    = r["action_taken"].strip()
        bs_action = r["basic_strategy_action"].strip()

        base_key = (total, is_soft, dealer_rank, can_split, can_double)
        groups[base_key].append(action)
        basic_for_key[base_key] = bs_action  # same for any row at this key

        bias    = _bias_bucket(r.get("visible_cards", "").split())
        sibling = max_hand_index_by_round[r.get("round", "")] > _hand_index(r)
        fine_key = base_key + (bias, sibling)
        fine_groups[fine_key].append(action)
        fine_basic_for_key[fine_key] = bs_action

    # --- Coarse (5-field) deviations -- unchanged behavior ---
    deviations = []
    coarse_action_by_key: dict[tuple, str] = {}
    for key, actions in groups.items():
        n = len(actions)
        if n < min_samples:
            continue
        majority_action, majority_frac, counts = _majority(actions)
        if majority_frac < min_majority:
            continue
        bs = basic_for_key[key]
        if majority_action == bs:
            continue  # agrees with basic strategy — no deviation to store

        coarse_action_by_key[key] = majority_action
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
            "action_counts":     counts,
        })

    # --- Fine (table-aware) deviations -- only where the extra context
    # actually reveals a different tendency than the coarse tier above ---
    for fine_key, actions in fine_groups.items():
        n = len(actions)
        if n < min_samples:
            continue
        majority_action, majority_frac, counts = _majority(actions)
        if majority_frac < min_majority:
            continue

        base_key = fine_key[:5]
        bias, sibling = fine_key[5], fine_key[6]
        bs = fine_basic_for_key[fine_key]
        baseline = coarse_action_by_key.get(base_key, bs)
        if majority_action == baseline:
            continue  # no different from the coarser spot -- not worth recording

        total, is_soft, dealer_rank, can_split, can_double = base_key
        deviations.append({
            "hand_total":            total,
            "is_soft":               is_soft,
            "dealer_upcard_rank":    dealer_rank,
            "can_split":             can_split,
            "can_double":            can_double,
            "table_bias":            bias,
            "sibling_awaiting_deal": sibling,
            "basic_strategy":        bs,
            "player_action":         majority_action,
            "samples":               n,
            "majority":              round(majority_frac, 3),
            "action_counts":         counts,
        })

    deviations.sort(key=lambda d: (d["hand_total"], d["is_soft"], d["dealer_upcard_rank"],
                                   d.get("table_bias") or "", d.get("sibling_awaiting_deal", False)))

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


def build_lottery_stakes(rows: list[dict], player_name: str,
                          min_samples: int = 3) -> list[dict]:
    """
    Group this player's (human) Dealer Lottery entries -- rows from
    dealer_lottery_decisions_*.csv, written by
    app.services.decision_log.record_dealer_lottery_entry -- by how many
    sips they owed this round when the entry window opened, and record
    their average stake per bucket.

    This is what engine/style_strategy.py's decide_dealer_lottery_stake
    looks up to drive an NPC using this profile; a bucket without enough
    samples is simply omitted (NPC falls back to opting out, same as a
    "basic" personality).
    """
    player_rows = [
        r for r in rows
        if r["player"].strip().lower() == player_name.lower()
        and not _parse_bool(r.get("is_npc", "False"))
    ]

    buckets: dict[str, list[int]] = defaultdict(list)
    for r in player_rows:
        try:
            owed = int(r.get("current_owed", "") or 0)
            x    = int(r.get("x_entered", "") or 0)
        except ValueError:
            continue
        buckets[_owed_bucket(owed)].append(x)

    stakes = []
    for bucket, values in buckets.items():
        n = len(values)
        if n < min_samples:
            continue
        stakes.append({
            "owed_bucket": bucket,
            "avg_stake":   round(sum(values) / n, 2),
            "samples":     n,
        })
    stakes.sort(key=lambda s: s["owed_bucket"])
    return stakes


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

    lottery_rows = _load_csvs(args.dir, pattern="dealer_lottery_decisions_*.csv")

    # Discover players
    all_players = sorted({r["player"].strip() for r in rows
                          if not _parse_bool(r.get("is_npc", "False"))})
    targets = [args.player] if args.player else all_players

    os.makedirs(args.out, exist_ok=True)

    for name in targets:
        profile = build_profile(rows, name, args.min_samples, args.min_majority)
        profile["lottery_stakes"] = build_lottery_stakes(lottery_rows, name, args.min_samples)
        n_dev   = len(profile["deviations"])
        n_stake = len(profile["lottery_stakes"])
        out_path = Path(args.out) / f"{name.lower()}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        print(f"\n{name}: {profile['source_decisions']} decisions, "
              f"{n_dev} deviation(s), {n_stake} lottery-stake bucket(s) recorded → {out_path}")
        for d in profile["deviations"]:
            hand_desc = f"{'soft' if d['is_soft'] else 'hard'} {d['hand_total']}"
            flags = []
            if d["can_split"]:  flags.append("splittable")
            if d["can_double"]: flags.append("doubling available")
            if "table_bias" in d:
                flags.append(f"table_bias={d['table_bias']}")
                flags.append(f"sibling_awaiting_deal={d['sibling_awaiting_deal']}")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  {hand_desc} vs {d['dealer_upcard_rank']}{flag_str}: "
                  f"{d['basic_strategy']} → {d['player_action']} "
                  f"({d['samples']} samples, {d['majority']*100:.0f}%)")
        for s in profile["lottery_stakes"]:
            print(f"  dealer lottery, owed={s['owed_bucket']}: "
                  f"avg stake {s['avg_stake']} ({s['samples']} samples)")


if __name__ == "__main__":
    main()
