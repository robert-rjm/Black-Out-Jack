"""
scripts/simulation.py -- 10,000-round Drinking Blackjack simulation.
3 NPC players, 2 hands each, dealer rotates every 3 rounds.
Outputs: simulation_results.txt, simulation_log.csv
Run: python simulation.py
"""
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


import io, os, csv, contextlib  # noqa: E402
from collections import defaultdict  # noqa: E402
from datetime import datetime  # noqa: E402

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    from engine.blackjack import NPC_Player, Shoe, RoundManager
    from drinking_rules import DrinkTracker

NUM_ROUNDS   = 10000
PLAYER_NAMES = ["Alice", "Bob", "Charlie"]
NUM_HANDS    = 2
WAGER        = 1
NUM_DECKS    = 2
HERE = os.path.dirname(os.path.abspath(__file__))


def classify_rule(reason):
    r = reason
    if "A♣" in r and "credit" in r:           return None
    if "protects" in r:                         return None
    if "exempt" in r:                           return None
    if "Hard Dealer Switch (A♣ half protection)" in r: return "Hard Dealer Switch (half, A♣)"
    if "Hard Dealer Switch" in r:              return "Hard Dealer Switch"
    if "net loss" in r:                        return "Net hand losses"
    if "lost a doubled hand" in r:             return "Lost doubled hand"
    if "lost a suited hand" in r:              return "Lost suited hand"
    if "immunity exception" in r:              return "Doubled win (immunity break)"
    if "won suited hand" in r:                 return "Suited winning hand"
    if "split hand" in r:                      return "Split win (immunity break)"
    if "swept all hands" in r:                 return "Other-player sweep"
    if "all-hands sweep" in r:                 return "All-hands sweep"
    if "auto-insurance" in r:                  return "Dealer BJ (auto-insurance)"
    if "Insurance" in r and "dealer BJ" in r and "own bonus" in r: return "Insurance: BJ holder drinks own bonus"
    if "Insurance" in r and "no dealer BJ" in r:                   return "Insurance: group drinks double BJ bonus"
    if "Blackjack by" in r:                    return "Blackjack bonus"
    if "4 Aces" in r and "first deal" in r:   return "Four Aces (first deal)"
    if "4 Aces" in r and "end of round" in r:  return "Four Aces (end of round)"
    if "Dealer hand is all" in r:              return "Dealer suited hand"
    if "handed" in r and "5-card 21" in r:    return "5-card 21 handout received"
    if "won with" in r and "cards" in r:       return "5+ card win"
    if "A♠" in r and "to dealer" in r:   return "Ace dealt: A♠ (dealer hand)"
    if "A♥" in r and "dealer" in r:       return "Ace dealt: A♥ (dealer hand)"
    if "A♦" in r and "dealer" in r:       return "Ace dealt: A♦ (dealer hand)"
    if "A♠" in r:                         return "Ace dealt: A♠ (player hand)"
    if "A♥" in r:                         return "Ace dealt: A♥ (player hand)"
    if "A♦" in r:                         return "Ace dealt: A♦ (player hand)"
    return "Other"


def run_simulation():
    shoe = Shoe(NUM_DECKS)
    with contextlib.redirect_stdout(io.StringIO()):
        shoe.shuffle()

    player_sips = {n: defaultdict(int) for n in PLAYER_NAMES}
    dealer_sips = {n: defaultdict(int) for n in PLAYER_NAMES}
    event_log   = []
    dealer_idx  = 0

    for round_num in range(1, NUM_ROUNDS + 1):
        players       = [NPC_Player(name) for name in PLAYER_NAMES]
        dealer_name   = PLAYER_NAMES[dealer_idx % len(PLAYER_NAMES)]
        dealer_player = next(p for p in players if p.name == dealer_name)
        dealer_player.is_dealer = True
        tracker = DrinkTracker(players, dealer_player)
        rm = RoundManager(players, dealer_player, shoe, tracker,
                          WAGER, NUM_HANDS, drinking_mode=True)
        with contextlib.redirect_stdout(io.StringIO()):
            rm.play_round()

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

        dealer_idx = (dealer_idx + 1) % len(PLAYER_NAMES)
        if round_num % 1000 == 0:
            print(f"  [{round_num:>5}/{NUM_ROUNDS}] rounds complete...", flush=True)

    return player_sips, dealer_sips, event_log


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


def write_csv(event_log, path):
    if not event_log:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["round","dealer","player","role","rule","sips"])
        w.writeheader()
        w.writerows(event_log)
    print(f"  Event log -> {path}")


if __name__ == "__main__":
    print(f"Running {NUM_ROUNDS:,}-round simulation...")
    print(f"Players : {', '.join(PLAYER_NAMES)}  |  {NUM_HANDS} hands each  |  Wager: {WAGER} sip")
    print(f"Shoe    : {NUM_DECKS} decks  |  Dealer rotates every {len(PLAYER_NAMES)} rounds")
    print()

    player_sips, dealer_sips, event_log = run_simulation()

    print("\nDone. Writing output files...")
    write_summary(player_sips, dealer_sips, os.path.join(HERE, "simulation_results.txt"))
    write_csv(event_log,                    os.path.join(HERE, "simulation_log.csv"))

    print("\n  GRAND TOTALS")
    print("  " + "-" * 40)
    for name in PLAYER_NAMES:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        print(f"  {name:<12} {(pt+dt)/NUM_ROUNDS:>5.2f} sips/round"
              f"  (player: {pt/NUM_ROUNDS:.2f}, dealer: {dt/NUM_ROUNDS:.2f})")
    print()
