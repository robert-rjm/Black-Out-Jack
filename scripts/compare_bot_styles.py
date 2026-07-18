"""
scripts/compare_bot_styles.py -- run the drinking-blackjack simulation twice,
once with generic basic-strategy bots and once with named player-mimicry
profiles (engine/player_profiles/<name>.json), and print a side-by-side diff.

Both runs share the same random seed, so both conditions see identical
shoes/cards -- isolating the effect of a bot's mined decision profile
(hand deviations + Dealer Lottery stakes) from ordinary card-luck variance.

This never touches scripts/benchmarks.json or static/js/benchmarks.js (the
basic-strategy baseline kpi.js compares live sessions against) -- it only
prints a comparison table.

Usage:
    python scripts/compare_bot_styles.py
    python scripts/compare_bot_styles.py --personalities rob marko
    python scripts/compare_bot_styles.py --decks 2 --rounds 20000 --seed 7
"""
import os
import sys
import random
import argparse
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from scripts.simulation import run_simulation  # noqa: E402
from engine.style_strategy import available_profiles  # noqa: E402

# (column header, benchmark key, format)
COLUMNS = [
    ("Avg sips/rd",   "avg_sips_per_round", "{:.2f}"),
    ("Std sips/rd",   "std_sips_per_round", "{:.2f}"),
    ("Blackjack %",   "blackjack_rate_pct", "{:.1f}"),
    ("Bust %",        "bust_rate_pct",      "{:.1f}"),
    ("Win %",         "win_rate_pct",       "{:.1f}"),
    ("Loss %",        "loss_rate_pct",      "{:.1f}"),
    ("Push %",        "push_rate_pct",      "{:.1f}"),
    ("Dealer bust %", "dealer_bust_pct",    "{:.1f}"),
]


def _derive_stats(hand_totals, dealer_bust_rounds, std_sips_per_round, num_rounds, rule_totals):
    def pct(n, d): return round(n / d * 100, 1) if d else None
    hands = hand_totals["hands"]
    return {
        "avg_sips_per_round": round(sum(rule_totals.values()) / num_rounds, 3),
        "std_sips_per_round": round(std_sips_per_round, 3),
        "blackjack_rate_pct": pct(hand_totals["blackjacks"], hands),
        "bust_rate_pct":      pct(hand_totals["busts"], hands),
        "win_rate_pct":       pct(hand_totals["wins"], hands),
        "loss_rate_pct":      pct(hand_totals["losses"], hands),
        "push_rate_pct":      pct(hand_totals["pushes"], hands),
        "dealer_bust_pct":    pct(dealer_bust_rounds, num_rounds),
    }


def _run(num_players, num_decks, num_rounds, seed, personalities):
    (player_sips, dealer_sips, _event_log, hand_totals,
     dealer_bust_rounds, std_sips_per_round) = run_simulation(
        num_players=num_players, num_decks=num_decks, num_rounds=num_rounds,
        seed=seed, personalities=personalities,
    )
    rule_totals = defaultdict(int)
    for d in list(player_sips.values()) + list(dealer_sips.values()):
        for rule, s in d.items():
            rule_totals[rule] += s
    stats = _derive_stats(hand_totals, dealer_bust_rounds, std_sips_per_round, num_rounds, rule_totals)
    return stats, player_sips, dealer_sips


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--personalities", nargs="+", default=None,
                         help="Profile names to compare against basic strategy "
                              "(default: every profile in engine/player_profiles/)")
    parser.add_argument("--decks", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=20000,
                         help="Rounds per run (default 20000 -- lower than "
                              "simulation.py's full 100k default for faster iteration)")
    parser.add_argument("--seed", type=int, default=None,
                         help="Seed shared by both runs so they see identical "
                              "shoes/cards. Default: a fresh random seed each run.")
    args = parser.parse_args()

    personalities = [p.lower() for p in (args.personalities or available_profiles())]
    if not personalities:
        print("Error: no player profiles found in engine/player_profiles/ and "
              "none given via --personalities.", file=sys.stderr)
        sys.exit(1)

    num_players = len(personalities)
    seed = args.seed if args.seed is not None else random.randrange(2**32)

    print(f"Basic-strategy bots  vs.  personalities: {', '.join(personalities)}")
    print(f"{num_players} players | {args.decks} deck(s) | {args.rounds:,} rounds/run | seed={seed}\n")

    basic_names   = [f"Player{i + 1}" for i in range(num_players)]
    persona_names = [p.capitalize() for p in personalities]

    basic_stats, basic_player_sips, basic_dealer_sips = _run(
        num_players, args.decks, args.rounds, seed, None)
    persona_stats, persona_player_sips, persona_dealer_sips = _run(
        num_players, args.decks, args.rounds, seed, personalities)

    headers = ["Metric", "Basic", "Personas", "Delta"]
    rows = []
    for header, key, fmt in COLUMNS:
        b, p = basic_stats.get(key), persona_stats.get(key)
        if b is None or p is None:
            rows.append([header, "-", "-", "-"])
            continue
        rows.append([header, fmt.format(b), fmt.format(p), f"{p - b:+.2f}"])

    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    fmt_row = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt_row.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row.format(*row))

    print(f"\n  Per-seat sips/round ({args.rounds:,} rounds, same seed/shoe both runs):")
    seat_headers = ["Seat", "Basic name", "Basic sips/rd", "Persona name", "Persona sips/rd", "Delta"]
    seat_rows = []
    for i, (bname, pname) in enumerate(zip(basic_names, persona_names)):
        b_total = (sum(basic_player_sips[bname].values()) + sum(basic_dealer_sips[bname].values())) / args.rounds
        p_total = (sum(persona_player_sips[pname].values()) + sum(persona_dealer_sips[pname].values())) / args.rounds
        seat_rows.append([str(i + 1), bname, f"{b_total:.2f}", pname, f"{p_total:.2f}", f"{p_total - b_total:+.2f}"])
    seat_widths = [max(len(str(h)), *(len(str(r[i])) for r in seat_rows)) for i, h in enumerate(seat_headers)]
    seat_fmt = "  ".join(f"{{:<{w}}}" for w in seat_widths)
    print("  " + seat_fmt.format(*seat_headers))
    print("  " + "  ".join("-" * w for w in seat_widths))
    for row in seat_rows:
        print("  " + seat_fmt.format(*row))


if __name__ == "__main__":
    main()
