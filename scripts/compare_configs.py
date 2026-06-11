"""
scripts/compare_configs.py -- print a comparison table of key benchmark
stats across all simulated player/deck configs.

Reads scripts/benchmarks.json (BENCHMARKS_BY_CONFIG, written by
scripts/simulation.py) and prints one row per "<players>p_<decks>d" config,
sorted by player count then deck count.

Usage:
    python scripts/compare_configs.py
"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
BENCHMARKS_PATH = os.path.join(HERE, "benchmarks.json")

# (column header, key, format)
COLUMNS = [
    ("Avg sips/rd",   "avg_sips_per_round", "{:.2f}"),
    ("Std sips/rd",   "std_sips_per_round", "{:.2f}"),
    ("Sips/rd/player", None,                "{:.2f}"),  # derived
    ("Blackjack %",   "blackjack_rate_pct", "{:.1f}"),
    ("Bust %",        "bust_rate_pct",      "{:.1f}"),
    ("Win %",         "win_rate_pct",       "{:.1f}"),
    ("Loss %",        "loss_rate_pct",      "{:.1f}"),
    ("Push %",        "push_rate_pct",      "{:.1f}"),
    ("Dealer bust %", "dealer_bust_pct",    "{:.1f}"),
]


def main():
    if not os.path.exists(BENCHMARKS_PATH):
        print(f"Error: {BENCHMARKS_PATH} not found. Run `python scripts/simulation.py` first.")
        return

    with open(BENCHMARKS_PATH, encoding="utf-8") as f:
        all_benchmarks = json.load(f)

    if not all_benchmarks:
        print("No configs found in benchmarks.json.")
        return

    rows = []
    for key, data in all_benchmarks.items():
        cfg = data.get("config", {})
        players = cfg.get("num_players")
        decks = cfg.get("num_decks")
        rows.append((players, decks, key, data))
    rows.sort(key=lambda r: (r[0] or 0, r[1] or 0))

    headers = ["Config", "Players", "Decks"] + [c[0] for c in COLUMNS]
    table = []
    for players, decks, key, data in rows:
        row = [key, players, decks]
        for header, stat_key, fmt in COLUMNS:
            if stat_key is None:  # "Sips/rd/player" derived
                val = data.get("avg_sips_per_round", 0) / players if players else None
            else:
                val = data.get(stat_key)
            row.append(fmt.format(val) if val is not None else "-")
        table.append(row)

    widths = [max(len(str(h)), *(len(str(r[i])) for r in table)) for i, h in enumerate(headers)]
    fmt_row = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt_row.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in table:
        print(fmt_row.format(*row))


if __name__ == "__main__":
    main()
