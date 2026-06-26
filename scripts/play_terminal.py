"""
scripts/play_terminal.py -- Play Drinking Blackjack interactively in the terminal.

Wraps the shared engine (engine.blackjack.RoundManager + engine.drinking_rules
.DrinkTracker) with a small interactive setup + round loop, so the exact same
rules/logic used by the Flask web app can be played at the command line.

Run: python scripts/play_terminal.py
"""
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from engine.blackjack import Player, NPC_Player, Shoe, Hand, RoundManager  # noqa: E402
from engine.drinking_rules import DrinkTracker  # noqa: E402
from scripts._cli import safe_int as _safe_int, yes_no as _yes_no  # noqa: E402


def setup_session():
    print("\n" + "=" * 52)
    print("  DRINKING BLACKJACK -- TERMINAL MODE")
    print("=" * 52)
    print("  Same rules engine as the web app, played from the console.\n")

    n = _safe_int("  Number of human players (1-4): ", default=1, lo=1, hi=4)

    names = []
    for i in range(n):
        try:
            name = input(f"  Name for player {i + 1}: ").strip() or f"Player {i + 1}"
        except EOFError:
            name = f"Player {i + 1}"
        names.append(name.capitalize())

    num_npcs = _safe_int("  Number of NPC (bot) players (0-3): ", default=0, lo=0, hi=3)
    for i in range(num_npcs):
        names.append(f"Bot{i + 1}")

    if len(names) < 2:
        # RoundManager expects at least a dealer + one player; fall back to House NPC.
        names.append("House")

    num_decks = _safe_int("  Number of decks (1-8): ", default=1, lo=1, hi=8)
    wager     = _safe_int("  Sips per hand wager (default 1): ", default=1, lo=1, hi=20)
    num_hands = _safe_int("  Hands per player (default 2): ", default=2, lo=1, hi=10)
    drinking_mode = _yes_no("  Enable drinking mode (house rules + sip tracking)?", default=True)

    # Build players -- humans first, then NPCs
    players = []
    for name in names[:n]:
        players.append(Player(name))
    for name in names[n:]:
        players.append(NPC_Player(name))

    print("\n  Who is the dealer for round 1?")
    for i, p in enumerate(players):
        print(f"    {i + 1}. {p.name}")

    dealer_idx = 0
    try:
        raw = input("  Enter number (default 1): ").strip()
    except EOFError:
        raw = ""
    if raw.isdigit() and 1 <= int(raw) <= len(players):
        dealer_idx = int(raw) - 1

    for i, p in enumerate(players):
        p.is_dealer = (i == dealer_idx)
        if p.is_dealer:
            p.dealer_hand = Hand()

    shoe = Shoe(num_decks)
    shoe.shuffle()

    print("\n  Session ready.")
    print(f"  Players: {', '.join(p.name for p in players)}")
    print(f"  Dealer:  {players[dealer_idx].name}")
    print(f"  Wager:   {wager} sip(s)/hand  |  {num_hands} hands/player")
    print(f"  Drinking mode: {'ON' if drinking_mode else 'off'}\n")

    return players, dealer_idx, shoe, wager, num_hands, drinking_mode


def main():
    players, dealer_idx, shoe, wager, num_hands, drinking_mode = setup_session()

    while True:
        dealer_player = players[dealer_idx]
        tracker = DrinkTracker(players, dealer_player)
        rm = RoundManager(players, dealer_player, shoe, tracker,
                          wager=wager, num_hands=num_hands, drinking_mode=drinking_mode)
        rm.play_round()

        if shoe.just_reshuffled:
            print("\n  (Shoe ran low and was reshuffled mid-round.)")
            shoe.just_reshuffled = False

        try:
            again = input("\n  Play another round? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  Exiting. Thanks for playing!")
            break
        if again.startswith("n"):
            print("\n  Exiting. Thanks for playing!")
            break

        if _yes_no("  Rotate dealer?", default=True):
            dealer_idx = (dealer_idx + 1) % len(players)
            for i, p in enumerate(players):
                p.is_dealer = (i == dealer_idx)
                p.dealer_hand = Hand() if p.is_dealer else None


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Exiting. Thanks for playing!")
