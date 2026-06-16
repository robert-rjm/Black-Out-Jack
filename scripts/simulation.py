"""
scripts/simulation.py -- 100,000-round Drinking Blackjack simulation.
Prompts for player count and deck count, 2 hands each, dealer rotates
every N rounds (N = player count).
Outputs: simulation_results.txt, simulation_log.csv, benchmarks.json,
static/js/benchmarks.js (per-config, see BENCHMARKS_BY_CONFIG).
Run: python simulation.py
"""
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import io  # noqa: E402
import os  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import contextlib  # noqa: E402
from collections import defaultdict  # noqa: E402
from datetime import datetime  # noqa: E402

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    from engine.blackjack import NPC_Player, Shoe, RoundManager
    from engine.drinking_rules import DrinkTracker
from app.services.utils import classify_rule

NUM_ROUNDS   = 100000
NUM_HANDS    = 2
WAGER        = 1
HERE = os.path.dirname(os.path.abspath(__file__))

# single source of truth (also used by app/services/drink_tracker.py for the
# live web CSV export). A local copy here previously drifted out of sync with
# the engine's rule set (missing A♣ protection/credit cases, "Other" buckets
# for newer reason strings, etc.) — see docs/TODO.md.


def _ask_int(prompt, default, lo, hi):
    """Prompt for an int within [lo, hi], falling back to `default` on
    blank input, non-numeric input, or non-interactive runs (EOF)."""
    try:
        raw = input(prompt).strip()
    except EOFError:
        raw = ""
    if not raw:
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, v))


if __name__ == "__main__":
    # Allow non-interactive use: `python scripts/simulation.py <players> <decks>`
    # (used by scripts/run_all_configs.py to batch multiple configs without
    # prompting). Falls back to interactive prompts if no args are given.
    if len(_sys.argv) >= 3:
        NUM_PLAYERS = max(2, min(6, int(_sys.argv[1])))
        NUM_DECKS   = max(1, min(8, int(_sys.argv[2])))
    else:
        NUM_PLAYERS = _ask_int("Number of players (2-6, default 3): ", 3, 2, 6)
        NUM_DECKS   = _ask_int("Number of decks (1-8, default 1): ", 1, 1, 8)
else:
    NUM_PLAYERS = 3
    NUM_DECKS   = 1

PLAYER_NAMES = [f"Player{i + 1}" for i in range(NUM_PLAYERS)]
CONFIG_KEY   = f"{NUM_PLAYERS}p_{NUM_DECKS}d"


def run_simulation(num_players=None, num_decks=None, num_rounds=None, seed=None):
    """Run the drinking-blackjack simulation and return aggregate stats.

    Parameters are optional and default to the module-level NUM_PLAYERS /
    NUM_DECKS / NUM_ROUNDS (set from CLI args or interactive prompts) so the
    existing `__main__` behavior is unchanged. Passing explicit values lets
    callers (e.g. regression tests) run smaller/seeded simulations for other
    configs without touching module globals.

    `seed`, if given, seeds the shared `random` module before shuffling the
    shoe, making the run reproducible. Default `None` leaves production
    behavior (unseeded) unchanged.
    """
    num_players = NUM_PLAYERS if num_players is None else num_players
    num_decks   = NUM_DECKS if num_decks is None else num_decks
    num_rounds  = NUM_ROUNDS if num_rounds is None else num_rounds
    player_names = [f"Player{i + 1}" for i in range(num_players)]

    if seed is not None:
        random.seed(seed)

    shoe = Shoe(num_decks)
    with contextlib.redirect_stdout(io.StringIO()):
        shoe.shuffle()

    player_sips = {n: defaultdict(int) for n in player_names}
    dealer_sips = {n: defaultdict(int) for n in player_names}
    event_log   = []
    dealer_idx  = 0

    # Hand-outcome tallies, used to derive benchmark rates (blackjack %,
    # bust %, win/loss/push %, dealer bust %) for the live web UI.
    hand_totals = {"hands": 0, "blackjacks": 0, "busts": 0,
                   "wins": 0, "losses": 0, "pushes": 0}
    dealer_bust_rounds = 0

    # Running sum / sum-of-squares of total sips per round, used to derive
    # std_sips_per_round (for z-score-based benchmark coloring in kpi.js).
    round_sips_sum   = 0.0
    round_sips_sumsq = 0.0

    for round_num in range(1, num_rounds + 1):
        players       = [NPC_Player(name) for name in player_names]
        dealer_name   = player_names[dealer_idx % len(player_names)]
        dealer_player = next(p for p in players if p.name == dealer_name)
        dealer_player.is_dealer = True
        tracker = DrinkTracker(players, dealer_player)
        rm = RoundManager(players, dealer_player, shoe, tracker,
                          WAGER, NUM_HANDS, drinking_mode=True)
        with contextlib.redirect_stdout(io.StringIO()):
            rm.play_round()

        for p in players:
            for hand in p.hands:
                hand_totals["hands"] += 1
                if hand.is_blackjack():
                    hand_totals["blackjacks"] += 1
                if hand.is_bust():
                    hand_totals["busts"] += 1
                if hand.result == "win":
                    hand_totals["wins"] += 1
                elif hand.result == "loss":
                    hand_totals["losses"] += 1
                elif hand.result == "push":
                    hand_totals["pushes"] += 1

        round_total_sips = 0
        for p in players:
            for sips, reason, role in p.drink_log:
                if sips <= 0:
                    continue
                rule = classify_rule(reason)
                if rule is None:
                    continue
                (dealer_sips if role == "dealer" else player_sips)[p.name][rule] += sips
                event_log.append({"round": round_num, "dealer": dealer_name,
                                   "player": p.name, "role": role,
                                   "rule": rule, "sips": sips})
                round_total_sips += sips

        round_sips_sum   += round_total_sips
        round_sips_sumsq += round_total_sips ** 2

        if dealer_player.dealer_hand and dealer_player.dealer_hand.is_bust():
            dealer_bust_rounds += 1

        dealer_idx = (dealer_idx + 1) % len(player_names)
        if num_rounds >= 10 and round_num % (num_rounds // 10) == 0:
            pct = round_num * 100 // num_rounds
            print(f"  [{round_num:>5}/{num_rounds}] rounds complete... ({pct}%)", flush=True)

    n = num_rounds
    mean_sips = round_sips_sum / n
    var_sips  = max(0.0, round_sips_sumsq / n - mean_sips ** 2)
    std_sips_per_round = var_sips ** 0.5

    return player_sips, dealer_sips, event_log, hand_totals, dealer_bust_rounds, std_sips_per_round


SESSION = 10  # rounds per session — unit used throughout the summary


def write_summary(player_sips, dealer_sips, path):
    all_rules = sorted(
        {r for d in list(player_sips.values()) + list(dealer_sips.values()) for r in d}
    )
    rule_totals = defaultdict(int)
    for name in PLAYER_NAMES:
        for rule, s in player_sips[name].items(): rule_totals[rule] += s
        for rule, s in dealer_sips[name].items(): rule_totals[rule] += s
    grand_total   = sum(rule_totals.values())
    N             = NUM_ROUNDS
    S             = SESSION
    dealer_rounds = N // len(PLAYER_NAMES)
    W             = 72

    def per_session(sips): return sips / N * S

    L = []
    L += [
        "=" * W,
        f"  DRINKING BLACKJACK -- {N:,}-ROUND SIMULATION RESULTS",
        f"  Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  Players   : {', '.join(PLAYER_NAMES)}  ({NUM_HANDS} hands each per round)",
        f"  Wager     : {WAGER} sip/net-loss  |  Shoe: {NUM_DECKS} decks",
        f"  Dealer    : rotates every {len(PLAYER_NAMES)} rounds ({dealer_rounds:,} rounds each)",
        f"  All averages shown per {S}-round session",
        "=" * W,
    ]

    for name in PLAYER_NAMES:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        gt = pt + dt
        L.append(f"\n  {name}  --  {per_session(gt):.1f} sips / {S}-round session"
                 f"  (as player: {per_session(pt):.1f}  |  as dealer: {per_session(dt):.1f})")
        L.append("  " + "-" * 62)
        L.append(f"    {'Rule':<46} {f'sips/{S}rnd':>9}  {'% of own':>8}")
        L.append("  " + "-" * 62)
        for rule in all_rules:
            ps = player_sips[name].get(rule, 0)
            ds = dealer_sips[name].get(rule, 0)
            total = ps + ds
            if total == 0:
                continue
            note = f"  [player: {per_session(ps):.1f}  dealer: {per_session(ds):.1f}]" if ds > 0 else ""
            L.append(f"    {rule:<46} {per_session(total):>9.1f}  {total/gt*100:>7.1f}%{note}")

    L += [
        "",
        "=" * W,
        f"  RULE BREAKDOWN -- all players combined, per {S}-round session",
        f"  {'Rule':<48} {f'sips/{S}rnd':>9}  {'% total':>8}",
        "  " + "-" * W,
    ]
    for rule in sorted(rule_totals, key=lambda r: -rule_totals[r]):
        L.append(f"  {rule:<50} {per_session(rule_totals[rule]):>9.1f}"
                 f"  {rule_totals[rule]/grand_total*100:>7.1f}%")

    L += [
        "",
        f"  A typical {S}-round session : ~{per_session(grand_total):.0f} sips across all players"
        f"  ({grand_total:,} total over {N:,} rounds)",
        "=" * W,
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"  Summary  -> {path}")


def _load_existing_config_dict(path):
    """Load an existing benchmarks file (.json or .js) as a dict keyed by
    config (e.g. "3p_1d"). Returns {} if missing, unreadable, or in the old
    single-config format (no config-keyed wrapper)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        if path.endswith(".js"):
            content = content[content.index("{"): content.rindex("}") + 1]
        data = json.loads(content)
    except Exception:
        return {}
    # Old format had top-level keys like "blackjack_rate_pct" directly —
    # discard rather than trying to migrate it under a guessed config key.
    if "blackjack_rate_pct" in data:
        return {}
    return data


def write_benchmarks(player_sips, dealer_sips, hand_totals, dealer_bust_rounds,
                      std_sips_per_round, json_path, js_path):
    """
    Derive benchmark rates/averages from this run and merge them into a
    config-keyed JSON file and `BENCHMARKS_BY_CONFIG` JS constant consumed by
    static/js/ui/kpi.js for "vs. expected" % coloring. Each run's results are
    stored under a key like "3p_1d" (players + decks), so results for
    different table sizes accumulate across runs instead of overwriting
    each other.

    These replace previously hand-picked magic numbers (e.g. "expected
    ~4.8%" blackjack rate, "casino avg ~28%" dealer bust rate) with values
    derived from the actual current rule set / table config, so they stay
    accurate as engine/drinking_rules.py evolves — just re-run this script.
    """
    N = NUM_ROUNDS
    hands = hand_totals["hands"]

    rule_totals = defaultdict(int)
    for name in PLAYER_NAMES:
        for rule, s in player_sips[name].items(): rule_totals[rule] += s
        for rule, s in dealer_sips[name].items(): rule_totals[rule] += s

    def pct(n, d): return round(n / d * 100, 1) if d else None

    benchmarks = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "num_rounds": N,
            "num_players": NUM_PLAYERS,
            "num_decks": NUM_DECKS,
            "hands_per_round": NUM_HANDS,
        },
        "blackjack_rate_pct": pct(hand_totals["blackjacks"], hands),
        "bust_rate_pct":      pct(hand_totals["busts"], hands),
        "win_rate_pct":       pct(hand_totals["wins"], hands),
        "loss_rate_pct":      pct(hand_totals["losses"], hands),
        "push_rate_pct":      pct(hand_totals["pushes"], hands),
        "dealer_bust_pct":    pct(dealer_bust_rounds, N),
        "avg_sips_per_round": round(sum(rule_totals.values()) / N, 3),
        "std_sips_per_round": round(std_sips_per_round, 3),
        "sips_per_round_by_rule": {
            rule: round(total / N, 4) for rule, total in rule_totals.items()
        },
    }

    all_json = _load_existing_config_dict(json_path)
    all_json[CONFIG_KEY] = benchmarks
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_json, f, indent=2)
    print(f"  Benchmarks (json) -> {json_path}  [{CONFIG_KEY}]")

    all_js = _load_existing_config_dict(js_path)
    all_js[CONFIG_KEY] = benchmarks
    js = (
        "// AUTO-GENERATED by scripts/simulation.py — do not edit by hand.\n"
        "// Re-run `python scripts/simulation.py` to refresh/add a config\n"
        "// after any change to engine/drinking_rules.py or engine/blackjack.py.\n"
        "// Used by static/js/ui/kpi.js for benchmark-relative % coloring.\n"
        "// Keyed by \"<players>p_<decks>d\", e.g. \"3p_1d\".\n"
        f"const BENCHMARKS_BY_CONFIG = {json.dumps(all_js, indent=2)};\n"
    )
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(js)
    print(f"  Benchmarks (js)   -> {js_path}  [{CONFIG_KEY}]")


def write_csv(event_log, path):
    if not event_log:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["round", "dealer", "player", "role", "rule", "sips"])
        w.writeheader()
        w.writerows(event_log)
    print(f"  Event log -> {path}")


if __name__ == "__main__":
    print(f"\nRunning {NUM_ROUNDS:,}-round simulation... [{CONFIG_KEY}]")
    print(f"Players : {', '.join(PLAYER_NAMES)}  |  {NUM_HANDS} hands each  |  Wager: {WAGER} sip")
    print(f"Shoe    : {NUM_DECKS} deck(s)  |  Dealer rotates every {len(PLAYER_NAMES)} rounds")
    print()

    player_sips, dealer_sips, event_log, hand_totals, dealer_bust_rounds, std_sips_per_round = run_simulation()

    print("\nDone. Writing output files...")
    write_summary(player_sips, dealer_sips, os.path.join(HERE, "simulation_results.txt"))
    write_csv(event_log,                    os.path.join(HERE, "simulation_log.csv"))
    write_benchmarks(
        player_sips, dealer_sips, hand_totals, dealer_bust_rounds, std_sips_per_round,
        json_path=os.path.join(HERE, "benchmarks.json"),
        js_path=os.path.join(os.path.dirname(HERE), "static", "js", "benchmarks.js"),
    )

    print("\n  GRAND TOTALS")
    print("  " + "-" * 40)
    for name in PLAYER_NAMES:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        print(f"  {name:<12} {(pt+dt)/NUM_ROUNDS:>5.2f} sips/round"
              f"  (player: {pt/NUM_ROUNDS:.2f}, dealer: {dt/NUM_ROUNDS:.2f})")
    print()
