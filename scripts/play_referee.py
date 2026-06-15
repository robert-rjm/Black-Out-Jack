"""
scripts/play_referee.py -- Real-life referee for Drinking Blackjack (physical deck).

Wraps the shared engine.referee.RefereeSession (same rules engine used by the
Flask web app's referee mode) with an interactive setup + command loop, so a
real-deck game can be scored/tracked from the command line.

Run: python scripts/play_referee.py
"""
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from engine.blackjack import Player, Hand  # noqa: E402
from engine.referee import RefereeSession  # noqa: E402


COMMAND_MAP = {
    "deal":            "cmd_deal",
    "action":          "cmd_action",
    "result":          "cmd_result",
    "dealer":          "cmd_dealer",
    "fouraces":        "cmd_fouraces",
    "bustvote":        "cmd_bustvote",
    "bustvotetoggle":  "cmd_bustvotetoggle",
}


def _setup_session() -> "RefereeSession":
    """Prompt for players, dealer, wager, and hands-per-player, then build a
    RefereeSession ready for round 1."""
    print("=" * 52)
    print("  BLACK(OUT)JACK — REFEREE MODE")
    print("=" * 52)
    print("Enter player names one at a time (blank line to finish).")
    print("Include yourself and everyone else at the table.\n")

    names = []
    while True:
        raw = input(f"  Player {len(names) + 1} name (or blank to finish): ").strip()
        if not raw:
            if len(names) >= 2:
                break
            print("  Need at least 2 players.")
            continue
        names.append(raw.capitalize())

    print(f"\nPlayers: {', '.join(names)}")

    while True:
        raw = input(f"  Who is the dealer? [{names[0]}]: ").strip()
        if not raw:
            dealer_name = names[0]
            break
        match = next((n for n in names if n.lower() == raw.strip().lower()), None)
        if match:
            dealer_name = match
            break
        print(f"  Unknown player. Choose from: {', '.join(names)}")

    while True:
        raw = input("  Wager (sips per hand) [1]: ").strip()
        if not raw:
            wager = 1
            break
        try:
            wager = max(1, int(raw))
            break
        except ValueError:
            print("  Enter a whole number.")

    while True:
        raw = input("  Hands per player [2]: ").strip()
        if not raw:
            num_hands = 2
            break
        try:
            num_hands = max(1, int(raw))
            break
        except ValueError:
            print("  Enter a whole number.")

    raw = input("  Enable dealer-bust side bet? (y/N): ").strip().lower()
    bust_vote_enabled = raw in ("y", "yes")

    players = [Player(n) for n in names]
    for p in players:
        if p.name.lower() == dealer_name.lower():
            p.is_dealer   = True
            p.dealer_hand = Hand()

    session = RefereeSession(
        players, dealer_name, wager=wager, num_hands=num_hands,
        bust_vote_enabled=bust_vote_enabled,
    )
    return session


def main():
    """Interactive referee loop — `python scripts/play_referee.py`."""
    session = _setup_session()
    session.start_round()

    print("\nType 'help' for the full command reference, 'quit' to exit.")

    while True:
        try:
            raw = input("\nreferee> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        parts = raw.split()
        cmd   = parts[0].lower()

        if cmd in ("quit", "exit"):
            break
        elif cmd == "help":
            RefereeSession.print_help()
        elif cmd == "status":
            session.cmd_status()
        elif cmd == "endround":
            session.cmd_endround()
        elif cmd == "newround":
            session.start_round()
        elif cmd in COMMAND_MAP:
            getattr(session, COMMAND_MAP[cmd])(parts)
        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for the command reference.")


if __name__ == "__main__":
    main()
