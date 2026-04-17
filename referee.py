"""
referee.py
==========
Real-life referee for Drinking Blackjack.

Use when playing with a physical deck. You deal real cards and make real
decisions — this script acts as a scorekeeper and drink tracker. Tell it
what cards were dealt and what happened, and it fires all the drinking rules
in real time.

Run:
    python referee.py

Commands (type 'help' in-session for full reference):
    deal <player> <card> [hand<n>]   — register a card dealt
    action <player> <action> [hand<n>] — register an action (double/split/insurance)
    result <player> <result> [hand<n>] — set hand outcome (win/loss/push)
    endround                          — finalise round, print drink summary
    newround                          — start next round
    status                            — show current round state
    help                              — show command reference
    quit                              — exit

Card format:   <rank><suit>
    rank:  2-9, 10, J, Q, K, A
    suit:  h=hearts  d=diamonds  c=clubs  s=spades
    e.g.:  Ah  10s  Kd  3c

Examples:
    deal Rob Ah hand1          — Rob's hand 1 receives Ace of Hearts
    deal dealer 7d             — dealer receives 7 of Diamonds
    action Rob double hand1    — Rob doubles down on hand 1
    result Rob win hand1       — Rob's hand 1 wins
    result dealer bust         — dealer busts (all non-busted players win)
"""

import sys
from blackjack import (
    Rank, Suit, Card, Hand, Player, HandEvaluator
)
from drinking_rules import DrinkingRules, DrinkTracker
from tabulate import tabulate


# =============================================================================
# Card parsing
# =============================================================================

RANK_MAP = {
    "2": Rank.TWO,   "3": Rank.THREE, "4": Rank.FOUR,  "5": Rank.FIVE,
    "6": Rank.SIX,   "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE,
    "10": Rank.TEN,  "j": Rank.JACK,  "q": Rank.QUEEN, "k": Rank.KING,
    "a": Rank.ACE,
}
SUIT_MAP = {
    "h": Suit.HEARTS, "d": Suit.DIAMONDS,
    "c": Suit.CLUBS,  "s": Suit.SPADES,
}


def parse_card(token: str) -> Card:
    """
    Parse a card string like 'Ah', '10s', 'Kd', '3c'.
    Raises ValueError with a helpful message on bad input.
    """
    token = token.strip().lower()
    if len(token) < 2:
        raise ValueError(f"Cannot parse card '{token}' — use format like Ah, 10s, Kd")

    suit_char = token[-1]
    rank_str  = token[:-1]

    if suit_char not in SUIT_MAP:
        raise ValueError(f"Unknown suit '{suit_char}' — use h/d/c/s")
    if rank_str not in RANK_MAP:
        raise ValueError(f"Unknown rank '{rank_str}' — use 2-9, 10, J, Q, K, A")

    return Card(RANK_MAP[rank_str], SUIT_MAP[suit_char])


# =============================================================================
# RefereeSession
# =============================================================================

class RefereeSession:
    """
    Manages one or more rounds of a real-life Drinking Blackjack game.
    Receives card/action/result events via text commands and fires
    DrinkingRules hooks in response.
    """

    def __init__(self, players: list, dealer_name: str,
                 wager: int = 1, num_hands: int = 2):
        self.all_players   = players           # list of Player objects (includes dealer-player)
        self.dealer_name   = dealer_name
        self.wager         = wager
        self.num_hands     = num_hands
        self.round_count   = 0
        self._all_names    = [p.name for p in players]
        self._player_map   = {p.name.lower(): p for p in players}

        # Round state
        self._ace_clubs_flag  = {"protected": False}
        self._four_aces_fd    = False
        self._ace_credits     = []    # player names who received A-clubs
        self._initial_dealt   = False # True once all first-deal cards are entered

        # Tracker — resolves recipients and logs drinks
        self.tracker = DrinkTracker(players, self._get_dealer())

    # ---------------------------------------------------------------- helpers

    def _get_dealer(self) -> Player:
        return self._player_map.get(self.dealer_name.lower())

    def _get_player(self, name: str) -> Player:
        return self._player_map.get(name.strip().lower())

    def _get_hand(self, player: Player, hand_label: str) -> Hand:
        """
        hand_label: 'hand1', 'hand2', ... or empty (defaults to hand1).
        For the dealer, returns dealer_hand.
        """
        if player.is_dealer and player.name.lower() == self.dealer_name.lower():
            return player.dealer_hand
        try:
            idx = int(hand_label.lower().replace("hand", "").strip()) - 1
        except (ValueError, AttributeError):
            idx = 0
        while len(player.hands) <= idx:
            player.hands.append(Hand())
        return player.hands[idx]

    # ---------------------------------------------------------------- setup round

    def start_round(self):
        self.round_count += 1
        print(f"\n{'='*52}")
        print(f"  ROUND {self.round_count}  |  Dealer: {self.dealer_name}")
        print("="*52)
        print("  Enter cards as they are dealt. Type 'help' for commands.\n")

        # Reset all player hands and drink logs
        for p in self.all_players:
            if p.is_dealer:
                p.dealer_hand = Hand()
                p.drink_log   = []
                # Also reset player hands for dealer-player
                p.hands = [Hand() for _ in range(self.num_hands)]
            else:
                p.hands     = [Hand() for _ in range(self.num_hands)]
                p.drink_log = []

        self._ace_clubs_flag  = {"protected": False}
        self._four_aces_fd    = False
        self._ace_credits     = []
        self._initial_dealt   = False
        self.tracker = DrinkTracker(self.all_players, self._get_dealer())

    # ---------------------------------------------------------------- command: deal

    def cmd_deal(self, parts: list):
        """deal <player> <card> [hand<n>]"""
        if len(parts) < 3:
            print("  Usage: deal <player> <card> [hand<n>]")
            print("  Example: deal Rob Ah hand1   |   deal dealer 7d")
            return

        player_name = parts[1]
        card_str    = parts[2]
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        # Resolve player
        is_dealer_seat = (player_name.lower() == "dealer"
                          or player_name.lower() == self.dealer_name.lower())
        if is_dealer_seat:
            player = self._get_dealer()
        else:
            player = self._get_player(player_name)

        if not player:
            print(f"  Unknown player '{player_name}'. Known: {', '.join(self._all_names)}")
            return

        # Parse card
        try:
            card = parse_card(card_str)
        except ValueError as e:
            print(f"  {e}")
            return

        # Get hand
        if is_dealer_seat:
            hand = player.dealer_hand
            recipient_name = self.dealer_name
        else:
            hand = self._get_hand(player, hand_label)
            recipient_name = player.name

        # Add card to hand
        card_pos = len(hand.cards) + 1
        hand.cards.append(card)
        print(f"  {recipient_name} {'(dealer) ' if is_dealer_seat else ''}"
              f"{hand_label if not is_dealer_seat else ''}: dealt {card}  "
              f"-> {hand}")

        # Fire ace rules immediately
        msgs = DrinkingRules.on_card_dealt(
            card, recipient_name, card_pos,
            self._all_names, self.dealer_name,
            self._ace_clubs_flag
        )
        for r, s, reason in msgs:
            if s == -1:
                self._ace_credits.append(recipient_name)
                print(f"    (i) {reason}")
            else:
                self.tracker.apply([(r, s, reason)])

        # Check for blackjack on first two cards
        if len(hand.cards) == 2 and hand.is_blackjack() and not is_dealer_seat:
            print(f"  *** {recipient_name} has BLACKJACK! ***")
            print(f"  (Use 'action {recipient_name} insurance {hand_label}' if dealer shows A and they want to insure)")

    # ---------------------------------------------------------------- command: action

    def cmd_action(self, parts: list):
        """action <player> <action> [hand<n>]"""
        if len(parts) < 3:
            print("  Usage: action <player> <action> [hand<n>]")
            print("  Actions: double, split, insurance, blackjack")
            return

        player_name = parts[1]
        action      = parts[2].lower()
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        player = self._get_player(player_name)
        if not player:
            print(f"  Unknown player '{player_name}'.")
            return

        hand = self._get_hand(player, hand_label)

        if action == "double":
            hand.doubled = True
            print(f"  {player.name} {hand_label}: marked as doubled.")

        elif action == "split":
            # Create a new hand for the split
            new_hand = Hand(from_split=True)
            hand.from_split   = True
            hand.split_count += 1
            idx = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
            player.hands.insert(idx + 1, new_hand)
            new_label = f"hand{idx + 2}"
            print(f"  {player.name} splits {hand_label} -> {hand_label} + {new_label}")
            print(f"  Now deal one card each to {hand_label} and {new_label}.")

        elif action == "insurance":
            hand.insured = True
            print(f"  {player.name} {hand_label}: insured — blackjack treated as regular 21.")

        elif action in ("blackjack", "bj"):
            hand.stood = True
            print(f"  {player.name} {hand_label}: BLACKJACK confirmed.")
            self.tracker.apply(
                DrinkingRules.on_blackjack(player.name, hand, self._all_names))

        else:
            print(f"  Unknown action '{action}'. Use: double, split, insurance, blackjack")

    # ---------------------------------------------------------------- command: result

    def cmd_result(self, parts: list):
        """result <player> <win|loss|push|bust> [hand<n>]"""
        if len(parts) < 3:
            print("  Usage: result <player> <win|loss|push|bust> [hand<n>]")
            print("  Special: 'result dealer bust' marks dealer bust (all non-bust players win)")
            return

        player_name = parts[1]
        outcome     = parts[2].lower()
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        # Special case: dealer bust
        if player_name.lower() in ("dealer", self.dealer_name.lower()) and outcome == "bust":
            dealer = self._get_dealer()
            dealer.dealer_hand.bust = True
            print(f"  Dealer busts. Mark each non-busted player hand as 'win'.")
            # Check dealer suited hand
            self.tracker.apply(
                DrinkingRules.on_dealer_hand_revealed(dealer.dealer_hand))
            return

        player = self._get_player(player_name)
        if not player:
            print(f"  Unknown player '{player_name}'.")
            return

        hand = self._get_hand(player, hand_label)

        if outcome in ("win", "loss", "push"):
            hand.result = outcome
            print(f"  {player.name} {hand_label}: {outcome.upper()}")
            self.tracker.apply(
                DrinkingRules.on_hand_resolved(player.name, hand, self._all_names))
        elif outcome == "bust":
            hand.result = "loss"
            hand.bust   = True
            print(f"  {player.name} {hand_label}: BUST => LOSS")
        else:
            print(f"  Unknown outcome '{outcome}'. Use: win, loss, push, bust")

    # ---------------------------------------------------------------- command: dealer reveal

    def cmd_dealer(self, parts: list):
        """dealer <final|suited|bust|blackjack> — mark the dealer's final state"""
        if len(parts) < 2:
            print("  Usage: dealer <final|suited|bust|blackjack>")
            return

        sub = parts[1].lower()
        dealer = self._get_dealer()

        if sub == "final":
            # Trigger dealer-suited-hand check
            self.tracker.apply(
                DrinkingRules.on_dealer_hand_revealed(dealer.dealer_hand))
            print(f"  Dealer final hand checked: {dealer.dealer_hand}")

        elif sub == "bust":
            dealer.dealer_hand.bust = True
            self.tracker.apply(
                DrinkingRules.on_dealer_hand_revealed(dealer.dealer_hand))
            print("  Dealer bust registered.")

        elif sub == "blackjack":
            dealer.dealer_hand.stood = True
            print("  Dealer blackjack registered.")

        else:
            print(f"  Unknown dealer command '{sub}'. Use: final, bust, blackjack")

    # ---------------------------------------------------------------- command: four aces

    def cmd_fouraces(self, parts: list):
        """fouraces <firstdeal|endround> — manually trigger four-aces check"""
        phase_map = {"firstdeal": "first_deal", "endround": "end_of_round"}
        phase = phase_map.get(parts[1].lower() if len(parts) > 1 else "", "")
        if not phase:
            print("  Usage: fouraces <firstdeal|endround>")
            return
        all_cards = [c for p in self.all_players for h in p.hands for c in h.cards]
        if self._get_dealer():
            all_cards += self._get_dealer().dealer_hand.cards
        msgs, self._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, phase, self._four_aces_fd)
        self.tracker.apply(msgs)

    # ---------------------------------------------------------------- command: endround

    def cmd_endround(self):
        """Finalise the round — fire end-of-round rules and print summary."""
        print("\n--- End of Round ---")

        # Hard dealer switch check
        dealer  = self._get_dealer()
        players = [p for p in self.all_players if not p.is_dealer or p.hands]
        winning = []
        dealer_lost_all = True
        for p in players:
            for hand in p.hands:
                if hand.result == "win":
                    winning.append((p.name, hand))
                elif hand.result in ("loss", "push"):
                    dealer_lost_all = False

        if dealer_lost_all and winning:
            self.tracker.apply(
                DrinkingRules.on_hard_dealer_switch(
                    self.dealer_name, winning,
                    self._ace_clubs_flag["protected"]))

        # Round-end rules (net losses, sweeps)
        self.tracker.apply(DrinkingRules.on_round_end(players, self.wager))

        # Ace-of-clubs credits
        for name in self._ace_credits:
            p = self._get_player(name)
            if p: self.tracker.apply_ace_clubs_credit(p)

        # Update cumulative stats
        for p in players:
            p.total_wins   += p.round_wins()
            p.total_losses += p.round_losses()
            p.total_pushes += p.round_pushes()

        # Print
        self._show_results()
        self.tracker.print_round_summary()

    # ---------------------------------------------------------------- command: status

    def cmd_status(self):
        """Show the current state of all hands this round."""
        print("\n--- Current Round State ---")
        rows = []
        for p in self.all_players:
            for i, h in enumerate(p.hands):
                tag = " (dealer)" if p.is_dealer else ""
                rows.append([
                    f"{p.name}{tag} H{i+1}",
                    str(h),
                    h.result.upper() if h.result else "-"
                ])
            if p.is_dealer and p.dealer_hand:
                rows.append([
                    f"{p.name} (dealer hand)",
                    str(p.dealer_hand),
                    "BUST" if p.dealer_hand.bust else "-"
                ])
        print(tabulate(rows, headers=["Seat", "Hand", "Result"], tablefmt="pretty"))

    # ---------------------------------------------------------------- show results

    def _show_results(self):
        print("\n" + "="*52)
        print("  ROUND RESULTS")
        print("="*52)
        rows = []
        for p in self.all_players:
            for i, h in enumerate(p.hands):
                rows.append([f"{p.name} H{i+1}", str(h),
                             h.result.upper() if h.result else "-"])
        dealer = self._get_dealer()
        if dealer and dealer.dealer_hand:
            dh = dealer.dealer_hand
            rows.append([f"Dealer ({self.dealer_name})", str(dh),
                         "BJ" if dh.is_blackjack() else
                         "BUST" if dh.is_bust() else str(dh.score())])
        print(tabulate(rows, headers=["Seat", "Hand", "Result"], tablefmt="pretty"))
        print("="*52)

    # ---------------------------------------------------------------- help

    @staticmethod
    def print_help():
        help_text = """
  REFEREE COMMANDS
  ================
  deal <player> <card> [hand<n>]
      Register a card dealt to a player or the dealer.
      Card format: <rank><suit>  e.g. Ah  10s  Kd  3c
      Suit: h=hearts d=diamonds c=clubs s=spades
      Example: deal Rob Ah hand1
               deal dealer 7d

  action <player> <action> [hand<n>]
      Register a player action.
      Actions: double  split  insurance  blackjack
      Example: action Rob double hand1
               action Markoi split hand2
               action David insurance hand1
               action Rob blackjack hand1

  result <player> <outcome> [hand<n>]
      Set the outcome of a hand.
      Outcomes: win  loss  push  bust
      Special:  result dealer bust
      Example: result Rob win hand1
               result Markoi push hand2
               result dealer bust

  dealer <sub>
      Mark the dealer's final state.
      Sub-commands: final  bust  blackjack
      Example: dealer final
               dealer bust

  fouraces <firstdeal|endround>
      Manually trigger the four-aces check.

  endround
      Finalise the round — fires all end-of-round drink rules
      and prints the full drink summary.

  newround
      Start a new round (resets all hands).

  status
      Show the current state of all hands.

  quit / exit
      Exit the referee session.
"""
        print(help_text)


# =============================================================================
# Setup
# =============================================================================

def _safe_int(prompt: str, default: int, lo: int = 1, hi: int = 999) -> int:
    """Input helper — accepts integers, ignores trailing punctuation, loops on bad input."""
    while True:
        try:
            raw = input(prompt).strip().rstrip(".,:;")
            val = int(raw) if raw else default
            if lo <= val <= hi:
                return val
            print(f"  Please enter a number between {lo} and {hi}.")
        except ValueError:
            print("  Please enter a number.")


def setup_session() -> RefereeSession:
    print("\n" + "="*52)
    print("  DRINKING BLACKJACK — REFEREE MODE")
    print("="*52)
    print("  Real-life session: you deal the cards, we track the drinks.\n")

    n = _safe_int("  Number of players (1-4): ", default=2, lo=1, hi=4)

    names = []
    for i in range(n):
        name = input(f"  Name for player {i+1}: ").strip() or f"Player {i+1}"
        names.append(name.capitalize())

    print("\n  Who is the dealer this round?")
    for i, name in enumerate(names):
        print(f"    {i+1}. {name}")

    dealer_name = names[0]
    while True:
        raw = input("  Enter number or name: ").strip()
        if not raw:
            break
        if raw.isdigit():
            idx = max(0, min(n - 1, int(raw) - 1))
            dealer_name = names[idx]
            break
        match = next((name for name in names if name.lower() == raw.lower()), None)
        if match:
            dealer_name = match
            break
        print(f"  '{raw}' not recognised. Enter a number (1-{n}) or a player name.")

    wager     = _safe_int("  Sips per hand wager (default 1): ", default=1, lo=1, hi=20)
    num_hands = _safe_int("  Hands per player (default 2): ",    default=2, lo=1, hi=10)

    # Build Player objects — dealer-player gets is_dealer=True
    players = []
    for name in names:
        p           = Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    print(f"\n  Session ready.")
    print(f"  Players: {', '.join(names)}")
    print(f"  Dealer:  {dealer_name}")
    print(f"  Wager:   {wager} sip(s)/hand  |  {num_hands} hands/player")
    print(f"  Type 'help' for command reference.\n")

    return RefereeSession(players, dealer_name, wager, num_hands)


# =============================================================================
# Main loop
# =============================================================================

def main():
    session = setup_session()
    session.start_round()

    while True:
        try:
            raw = input("referee> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Exiting referee session.")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd   = parts[0].lower()

        if cmd in ("quit", "exit", "q"):
            print("  Exiting referee session. Thanks for playing!")
            break

        elif cmd == "deal":
            session.cmd_deal(parts)

        elif cmd == "action":
            session.cmd_action(parts)

        elif cmd == "result":
            session.cmd_result(parts)

        elif cmd == "dealer":
            session.cmd_dealer(parts)

        elif cmd == "fouraces":
            session.cmd_fouraces(parts)

        elif cmd == "endround":
            session.cmd_endround()

        elif cmd == "newround":
            cont = input("  Rotate dealer? [y/n]: ").strip().lower()
            if cont == "y":
                all_names   = [p.name for p in session.all_players]
                cur_idx     = all_names.index(session.dealer_name)
                new_idx     = (cur_idx + 1) % len(all_names)
                new_dealer  = all_names[new_idx]
                for p in session.all_players:
                    p.is_dealer   = (p.name == new_dealer)
                    p.dealer_hand = Hand() if p.is_dealer else None
                session.dealer_name = new_dealer
                print(f"  Dealer rotates => {new_dealer} is now dealer.")
            session.start_round()

        elif cmd in ("status", "st"):
            session.cmd_status()

        elif cmd == "help":
            RefereeSession.print_help()

        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for reference.")


if __name__ == "__main__":
    main()
