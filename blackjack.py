"""
blackjack.py
========================
🃏 Drinking BlackJack
========================
Core Blackjack game. Fully playable standalone (normal mode).
When drinking mode is selected at startup, drinking_rules.py is imported
and the DrinkTracker is activated alongside the game.

Run:
    python blackjack.py
"""

from datetime import datetime
import random
from enum import Enum
from tabulate import tabulate

print("Date last modified:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# =============================================================================
# Enums
# =============================================================================

class Suit(Enum):
    HEARTS   = "hearts"
    DIAMONDS = "diamonds"
    CLUBS    = "clubs"
    SPADES   = "spades"

    @property
    def symbol(self):
        return {"hearts": "♥", "diamonds": "♦", "clubs": "♣", "spades": "♠"}[self.value]

    @classmethod
    def from_input(cls, value):
        if isinstance(value, cls): return value
        if isinstance(value, str):
            v = value.strip().upper().removeprefix("SUIT.")
            try: return cls[v]
            except KeyError: raise ValueError(f"Invalid suit: {value}")
        raise TypeError("Input must be a string or Suit enum")


class Rank(Enum):
    TWO=2; THREE=3; FOUR=4; FIVE=5; SIX=6; SEVEN=7; EIGHT=8; NINE=9
    TEN=10; JACK=11; QUEEN=12; KING=13; ACE=14

    @classmethod
    def from_input(cls, value):
        if isinstance(value, cls): return value
        if isinstance(value, str):
            v = value.strip().upper().removeprefix("RANK.")
            try: return cls[v]
            except KeyError: raise ValueError(f"Invalid rank: {value}")
        raise TypeError("Input must be a string or Rank enum")

    @property
    def label(self):
        if self in (Rank.JACK, Rank.QUEEN, Rank.KING): return self.name[0]
        if self == Rank.ACE: return "A"
        return str(self.value)

    @property
    def blackjack_value(self):
        if self in (Rank.JACK, Rank.QUEEN, Rank.KING): return 10
        if self == Rank.ACE: return 11
        return self.value


# =============================================================================
# Card, Deck, Shoe
# =============================================================================

class Card:
    def __init__(self, rank: Rank, suit: Suit):
        if not isinstance(rank, Rank): raise ValueError("Invalid rank")
        if not isinstance(suit, Suit): raise ValueError("Invalid suit")
        self.rank = rank
        self.suit = suit

    def __str__(self):  return f"{self.rank.label}{self.suit.symbol}"
    def __repr__(self): return f"Card({self.rank.label}{self.suit.symbol})"
    def to_tuple(self): return (self.rank.label, self.suit.symbol)


class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for suit in Suit for rank in Rank]

    def __len__(self): return len(self.cards)


class Shoe:
    def __init__(self, num_decks: int = 1):
        self.num_decks   = num_decks
        self.cards       = []
        self.penetration = random.uniform(0.70, 0.85)
        self.total_cards = num_decks * 52
        for _ in range(num_decks):
            self.cards.extend(Deck().cards)

    def __len__(self):  return len(self.cards)
    def __str__(self):  return (f"Shoe({self.num_decks} deck(s), "
                                f"{len(self.cards)} remaining, "
                                f"pen {self.penetration:.0%})")
    def __repr__(self): return (f"Shoe(num_decks={self.num_decks}, "
                                f"cards_remaining={len(self.cards)}, "
                                f"penetration={self.penetration:.2%})")

    def shuffle(self):
        random.shuffle(self.cards)
        print(f"Shoe shuffled - {len(self.cards)} cards ready.")

    def reset(self, num_decks: int = None):
        self.__init__(num_decks or self.num_decks)
        self.shuffle()

    def needs_reshuffle(self) -> bool:
        return len(self.cards) < (1 - self.penetration) * self.total_cards

    def deal_card(self) -> Card:
        if self.needs_reshuffle():
            print("Reshuffling shoe...")
            self.reset()
        return self.cards.pop()


# =============================================================================
# Hand
# =============================================================================

class Hand:
    """
    One blackjack hand. Players hold a list of Hands
    (2 initial hands per the drinking rules; splits add more).
    """
    MAX_SPLITS = 5  # max splits per hand (aces unlimited)

    def __init__(self, doubled: bool = False, from_split: bool = False):
        self.cards:     list = []
        self.doubled    = doubled
        self.from_split = from_split
        self.split_count = 0
        self.stood      = False
        self.bust       = False
        self.insured    = False
        self.result     = None   # "win" | "loss" | "push"

    # --- scoring ---
    def score(self) -> int:
        total = sum(c.rank.blackjack_value for c in self.cards)
        aces  = sum(1 for c in self.cards if c.rank == Rank.ACE)
        while total > 21 and aces:
            total -= 10; aces -= 1
        return total

    def is_blackjack(self) -> bool: return len(self.cards) == 2 and self.score() == 21
    def is_bust(self)      -> bool: return self.score() > 21
    def is_suited(self)    -> bool: return len(self.cards) >= 2 and len({c.suit for c in self.cards}) == 1

    def can_split(self) -> bool:
        if len(self.cards) != 2: return False
        if self.cards[0].rank == Rank.ACE: return True          # aces: unlimited splits
        return (self.cards[0].rank.blackjack_value == self.cards[1].rank.blackjack_value
                and self.split_count < self.MAX_SPLITS)

    def split(self, shoe) -> "Hand":
        """Remove second card into a new Hand, deal one card to each."""
        new_hand = Hand(from_split=True)
        new_hand.cards.append(self.cards.pop())
        self.from_split   = True
        self.split_count += 1
        self.cards.append(shoe.deal_card())
        new_hand.cards.append(shoe.deal_card())
        return new_hand

    # --- display ---
    def __str__(self):
        tags = [t for flag, t in [(self.doubled, "DBL"),
                                   (self.from_split, "SPL"),
                                   (self.insured, "INS")] if flag]
        tag = f'  [{", ".join(tags)}]' if tags else ""
        return f'{", ".join(str(c) for c in self.cards)}  [{self.score()}]{tag}'

    def __repr__(self): return f"Hand({self})"


# =============================================================================
# Player & NPC
# =============================================================================

class Player:
    """
    One seat at the table.
    When is_dealer=True, also runs a separate dealer_hand.
    In single-player mode 'House' holds is_dealer=True but plays no player hands.
    """
    def __init__(self, name: str):
        self.name         = name.strip().capitalize()
        self.hands:  list = []
        self.is_dealer    = False
        self.is_npc       = False
        self.dealer_hand  = None
        self.drink_log:  list = []   # (sips, reason) — used in drinking mode
        self.total_wins   = 0
        self.total_losses = 0
        self.total_pushes = 0
        self.total_drinks = 0

    def reset_round(self, num_hands: int = 2):
        self.hands       = [Hand() for _ in range(num_hands)]
        self.dealer_hand = Hand() if self.is_dealer else None
        self.drink_log   = []

    def round_wins(self)   -> int: return sum(1 for h in self.hands if h.result == "win")
    def round_losses(self) -> int: return sum(1 for h in self.hands if h.result == "loss")
    def round_pushes(self) -> int: return sum(1 for h in self.hands if h.result == "push")
    def net_losses(self)   -> int: return max(0, self.round_losses() - self.round_wins())
    def drinks_owed(self)  -> int: return sum(s for s, _ in self.drink_log if s > 0)

    def add_drink(self, sips: int, reason: str):
        if sips != 0:
            self.drink_log.append((sips, reason))

    def __str__(self):  return self.name
    def __repr__(self): return f"Player({self.name})"


# Basic strategy lookup tables
_BS_HARD = {
    **{(s, d): "h" for s in range(4, 9)  for d in range(2, 12)},
    **{(9,  d): ("d" if 3 <= d <= 6 else "h") for d in range(2, 12)},
    **{(10, d): ("d" if 2 <= d <= 9 else "h") for d in range(2, 12)},
    **{(11, d): "d" for d in range(2, 12)},
    **{(12, d): ("h" if d in (2, 3) or d >= 7 else "s") for d in range(2, 12)},
    **{(s,  d): ("h" if d >= 7 else "s") for s in range(13, 17) for d in range(2, 12)},
    **{(s,  d): "s" for s in range(17, 22) for d in range(2, 12)},
}
_BS_SOFT = {
    **{(13, d): ("d" if 5 <= d <= 6 else "h") for d in range(2, 12)},
    **{(14, d): ("d" if 5 <= d <= 6 else "h") for d in range(2, 12)},
    **{(15, d): ("d" if 4 <= d <= 6 else "h") for d in range(2, 12)},
    **{(16, d): ("d" if 4 <= d <= 6 else "h") for d in range(2, 12)},
    **{(17, d): ("d" if 3 <= d <= 6 else "h") for d in range(2, 12)},
    **{(18, d): ("d" if 3 <= d <= 6 else "s" if d in (2, 7, 8) else "h") for d in range(2, 12)},
    **{(s,  d): "s" for s in range(19, 22) for d in range(2, 12)},
}


class NPC_Player(Player):
    """
    Computer-controlled seat using standard basic strategy.
    Participates fully in drinking rules when drinking mode is active.
    Can hold the dealer role like any human seat.
    """
    def __init__(self, name: str = "Bot"):
        super().__init__(name)
        self.is_npc = True

    def __repr__(self): return f"NPC_Player({self.name})"

    def _is_soft(self, hand) -> bool:
        total = sum(c.rank.blackjack_value for c in hand.cards)
        aces  = sum(1 for c in hand.cards if c.rank == Rank.ACE)
        return aces > 0 and total <= 21

    def decide(self, hand, dealer_up_card, valid_actions: list, drinking_mode: bool = False) -> str:
        score   = hand.score()
        d_val   = min(dealer_up_card.rank.blackjack_value, 10)
        is_soft = self._is_soft(hand)

        if "sp" in valid_actions and hand.can_split():
            rv = hand.cards[0].rank.blackjack_value
            if rv == 11: return "sp"
            if rv == 8:  return "sp"
            if rv == 10: return "sp" if (drinking_mode and d_val != 10) else "s"
            if rv == 5:  return "d" if "d" in valid_actions else "h"
            if rv == 4:  return "sp" if 5 <= d_val <= 6 else "h"
            if rv == 9:  return "sp" if d_val not in (7, 10, 11) else "s"
            if rv == 7:  return "sp" if d_val <= 7 else "h"
            if rv == 6:  return "sp" if 2 <= d_val <= 6 else "h"
            if rv in (2, 3): return "sp" if 2 <= d_val <= 7 else "h"

        table = _BS_SOFT if is_soft else _BS_HARD
        ideal = table.get((score, d_val), "s")
        if ideal == "d" and "d" not in valid_actions:
            ideal = "h"
        return ideal if ideal in valid_actions else "s"


# =============================================================================
# HandEvaluator
# =============================================================================

class HandEvaluator:
    @staticmethod
    def compare(player_hand: Hand, dealer_hand: Hand) -> str:
        """Returns 'win' | 'loss' | 'push' from the player's perspective."""
        p_bj = player_hand.is_blackjack()
        d_bj = dealer_hand.is_blackjack()
        if player_hand.is_bust():   return "loss"
        if dealer_hand.is_bust():   return "win"
        if p_bj and d_bj:           return "push"
        if p_bj:                    return "win"
        if d_bj:                    return "loss"
        p, d = player_hand.score(), dealer_hand.score()
        return "win" if p > d else "loss" if p < d else "push"


# =============================================================================
# RoundManager
# =============================================================================

class RoundManager:
    """
    Manages one full round.

    Multi-player: ALL players (including dealer-player) play their own hands,
                  then the dealer-player reveals and plays the dealer hand.
                  3 players x 2 hands + 1 dealer hand = 7 hands total.

    Single-player: Only the human plays; House runs the dealer hand.

    drinking_mode: if True, fires DrinkTracker hooks at each game event.
    """

    def __init__(self, players, dealer_player, shoe, tracker,
                 wager=1, num_hands=2, drinking_mode=False):
        self.players        = players
        self.dealer_player  = dealer_player
        self.shoe           = shoe
        self.tracker        = tracker
        self.wager          = wager
        self.num_hands      = num_hands
        self.drinking_mode  = drinking_mode
        self._all_names     = [p.name for p in players]
        self._ace_credits   = []
        self._ace_clubs_flag = {"protected": False}
        self._four_aces_fd  = False

    # ---------------------------------------------------------------- helpers

    def _drink(self, msgs):
        """Fire drinking rule messages only when drinking mode is active."""
        if self.drinking_mode and self.tracker:
            self.tracker.apply(msgs)

    # ---------------------------------------------------------------- flow

    def play_round(self):
        self._reset()
        self._deal_initial()
        if self.drinking_mode:
            self._check_four_aces("first_deal")
        ordered = sorted(self.players, key=lambda p: p.is_dealer)
        self._player_turns(ordered)
        self._dealer_turn()
        if self.drinking_mode:
            self._check_four_aces("end_of_round")
        self._evaluate()
        if self.drinking_mode:
            self._round_end_drinks()
        self._show_results()
        if self.drinking_mode and self.tracker:
            self.tracker.print_round_summary()

    # ---------------------------------------------------------------- reset

    def _reset(self):
        for p in self.players:
            p.reset_round(self.num_hands)
        if self.dealer_player not in self.players:
            self.dealer_player.reset_round(0)
            self.dealer_player.dealer_hand = Hand()
        self._ace_credits    = []
        self._ace_clubs_flag = {"protected": False}
        self._four_aces_fd   = False

    # ---------------------------------------------------------------- dealing

    def _deal_card_to(self, hand, recipient_name):
        card     = self.shoe.deal_card()
        card_pos = len(hand.cards) + 1
        hand.cards.append(card)

        if self.drinking_mode:
            from drinking_rules import DrinkingRules
            msgs = DrinkingRules.on_card_dealt(
                card, recipient_name, card_pos,
                self._all_names, self.dealer_player.name,
                self._ace_clubs_flag
            )
            for r, s, reason in msgs:
                if s == -1:
                    self._ace_credits.append(recipient_name)
                    print(f"    (i) {reason}")
                else:
                    self.tracker.apply([(r, s, reason)])
        return card

    def _deal_initial(self):
        print("\n--- Dealing ---")
        dp = self.dealer_player
        for _ in range(2):
            for p in self.players:
                for hand in p.hands:
                    self._deal_card_to(hand, p.name)
            self._deal_card_to(dp.dealer_hand, dp.name)

        print(f"  Dealer ({dp.name}) shows: {dp.dealer_hand.cards[0]}, ?")
        for p in self.players:
            for i, h in enumerate(p.hands):
                tag = " (also dealer)" if p.is_dealer else ""
                print(f"  {p.name}{tag} Hand {i+1}: {h}")

    # ---------------------------------------------------------------- four aces

    def _check_four_aces(self, phase):
        from drinking_rules import DrinkingRules
        all_cards = ([c for p in self.players for h in p.hands for c in h.cards]
                     + self.dealer_player.dealer_hand.cards)
        msgs, self._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, phase, self._four_aces_fd)
        self.tracker.apply(msgs)

    # ---------------------------------------------------------------- player turns

    def _player_turns(self, ordered):
        for p in ordered:
            idx = 0
            while idx < len(p.hands):
                print(f"\n--- {p.name} Hand {idx+1} ---")
                self._play_hand(p, p.hands[idx], idx)
                idx += 1

    def _play_hand(self, player, hand, hand_idx):
        if hand.stood or hand.bust:
            return
        dealer_up = self.dealer_player.dealer_hand.cards[0]

        # Insurance
        if dealer_up.rank == Rank.ACE and not hand.from_split and len(hand.cards) == 2:
            if player.is_npc:
                print(f"  {player.name} (NPC) declines insurance.")
            else:
                raw = input(f"  Dealer shows A. {player.name}: take insurance? [y/n]: ").strip().lower()
                if raw == "y":
                    hand.insured = True
                    print(f"  {player.name} insures.")

        # Natural blackjack
        if hand.is_blackjack():
            hand.stood = True
            print(f"  BLACKJACK! {hand}")
            if self.drinking_mode:
                from drinking_rules import DrinkingRules
                self._drink(DrinkingRules.on_blackjack(player.name, hand, self._all_names))
            return

        # Normal loop
        while not hand.stood and not hand.bust:
            print(f"  Hand: {hand}  |  Dealer shows: {dealer_up}")
            valid = ["h", "s"]
            if len(hand.cards) == 2 and not hand.doubled: valid.append("d")
            if hand.can_split():                          valid.append("sp")

            if player.is_npc:
                action = player.decide(hand, dealer_up, valid, self.drinking_mode)
                print(f"  {player.name} (NPC) => {action}")
            else:
                # Mandatory 10-split warning (drinking mode only)
                if (self.drinking_mode
                        and "sp" in valid
                        and hand.cards[0].rank.blackjack_value == 10
                        and not hand.is_suited()):
                    print(f"  WARNING: rules require splitting {hand.cards[0]}, {hand.cards[1]} (mandatory unless suited)")
                    confirm = input("  Split? [y/n]: ").strip().lower()
                    if confirm == "y":
                        action = "sp"
                    else:
                        print(f"  {player.name} overrides mandatory split. Play with honor!")
                        action = self._get_input(valid)
                else:
                    action = self._get_input(valid)

            if action == "s":
                hand.stood = True
                print(f"  {player.name} stands.")

            elif action == "h":
                self._deal_card_to(hand, player.name)
                print(f"  Hit: {hand.cards[-1]}  -> {hand}")
                if hand.is_bust():
                    hand.bust = hand.stood = True
                    print("  BUST!")

            elif action == "d":
                hand.doubled = True
                self._deal_card_to(hand, player.name)
                hand.stood = True
                print(f"  Double down: {hand.cards[-1]}  -> {hand}")
                if hand.is_bust():
                    hand.bust = True
                    print("  BUST on double!")

            elif action == "sp":
                new_hand = hand.split(self.shoe)
                player.hands.insert(hand_idx + 1, new_hand)
                print(f"  Split! This hand: {hand}  |  New hand: {new_hand}")
                is_ace_split = (hand.cards[0].rank == Rank.ACE)
                if is_ace_split and not self.drinking_mode:
                    # Standard: 1 card per ace hand, auto-stand both, no further play
                    hand.stood = new_hand.stood = True
                    for h in (hand, new_hand):
                        if h.is_blackjack():
                            print(f"  Split-ace BLACKJACK! {h}")
                elif hand.is_blackjack():
                    # Immediate BJ after any split (drinking ace split or non-ace split)
                    hand.stood = True
                    print(f"  BLACKJACK! {hand}")
                    if self.drinking_mode:
                        from drinking_rules import DrinkingRules
                        self._drink(DrinkingRules.on_blackjack(player.name, hand, self._all_names))
                # No return: while loop exits if hand.stood, or continues for hit/stand/double
                # new_hand is played when _player_turns increments to the next idx

    @staticmethod
    def _get_input(valid):
        labels = {"h": "hit", "s": "stand", "d": "double", "sp": "split"}
        opts   = ", ".join(f"{k}={labels[k]}" for k in valid)
        while True:
            raw = input(f"  Action [{opts}]: ").strip().lower()
            if raw in valid: return raw
            print(f"  Invalid. Choose: {', '.join(valid)}")

    # ---------------------------------------------------------------- dealer turn

    def _dealer_turn(self):
        dp     = self.dealer_player
        d_hand = dp.dealer_hand
        print(f"\n--- Dealer ({dp.name}) ---")
        print(f"  Reveals: {d_hand}")

        if d_hand.is_blackjack():
            print("  Dealer BLACKJACK!")
        else:
            while d_hand.score() < 17:
                self._deal_card_to(d_hand, dp.name)
                print(f"  Dealer hits: {d_hand.cards[-1]}  -> {d_hand}")
            if d_hand.is_bust():
                print("  Dealer BUSTS!")
            else:
                print(f"  Dealer stands at {d_hand.score()}.")

        if self.drinking_mode:
            from drinking_rules import DrinkingRules
            self._drink(DrinkingRules.on_dealer_hand_revealed(d_hand))

    # ---------------------------------------------------------------- evaluation

    def _evaluate(self):
        print("\n--- Results ---")
        d_hand          = self.dealer_player.dealer_hand
        winning_hds     = []
        dealer_lost_all = True

        for p in self.players:
            for i, hand in enumerate(p.hands):
                result      = HandEvaluator.compare(hand, d_hand)
                hand.result = result
                icon = {"win": "WIN", "loss": "LOSS", "push": "PUSH"}[result]
                print(f"  {p.name} H{i+1}: {hand}  => {icon}")
                if result == "win":
                    winning_hds.append((p.name, hand))
                else:
                    dealer_lost_all = False
                if self.drinking_mode:
                    from drinking_rules import DrinkingRules
                    self._drink(DrinkingRules.on_hand_resolved(p.name, hand, self._all_names))

            p.total_wins   += p.round_wins()
            p.total_losses += p.round_losses()
            p.total_pushes += p.round_pushes()

        if self.drinking_mode and dealer_lost_all and winning_hds:
            from drinking_rules import DrinkingRules
            self._drink(DrinkingRules.on_hard_dealer_switch(
                self.dealer_player.name, winning_hds,
                self._ace_clubs_flag["protected"]))

    def _round_end_drinks(self):
        from drinking_rules import DrinkingRules
        self.tracker.apply(DrinkingRules.on_round_end(self.players, self.wager))
        for name in self._ace_credits:
            p = next((x for x in self.players if x.name.lower() == name.lower()), None)
            if p: self.tracker.apply_ace_clubs_credit(p)

    # ---------------------------------------------------------------- display

    def _show_results(self):
        print("\n" + "="*52)
        rows = []
        for p in self.players:
            for i, h in enumerate(p.hands):
                rows.append([f"{p.name} H{i+1}", str(h),
                             h.result.upper() if h.result else "-"])
        dh = self.dealer_player.dealer_hand
        rows.append([f"Dealer ({self.dealer_player.name})", str(dh),
                     "BJ" if dh.is_blackjack() else "BUST" if dh.is_bust() else str(dh.score())])
        print(tabulate(rows, headers=["Seat", "Hand", "Result"], tablefmt="pretty"))
        print("="*52)


# =============================================================================
# BlackJackGame — top-level controller
# =============================================================================

class BlackJackGame:
    """
    Supports 1-4 human/NPC players.
    Mode 1: Normal Blackjack  (drinking_rules.py not needed)
    Mode 2: Drinking Blackjack (drinking_rules.py activated)

    Multi-player: dealer role rotates every n rounds (n = seat count).
    Single-player: House is always dealer.
    """

    def __init__(self):
        self.all_seats     = []
        self.players       = []
        self.dealer_player = None
        self.shoe          = None
        self.wager         = 1
        self.num_hands     = 2
        self.round_count   = 0
        self._dealer_idx   = 0
        self._house_mode   = False
        self._drinking     = False
        self._npc_seats    = set()

    # ---------------------------------------------------------------- setup

    def setup(self):
        print("\n" + "="*52)
        print("  BLACKJACK")
        print("="*52)

        mode = self._ask_int("Game mode — 1: Normal  2: Drinking: ", 1, 2)
        self._drinking = (mode == 2)

        n = self._ask_int("Number of players (1-4): ", 1, 4)
        names = []
        self._npc_seats = set()
        for i in range(n):
            name = input(f"  Name for player {i+1} (Enter = NPC Bot {i+1}): ").strip()
            if name == "":
                name = f"Bot {i+1}"
                self._npc_seats.add(name)
                print(f"  -> NPC: {name}")
            else:
                if input(f"  Is {name} an NPC? [y/n]: ").strip().lower() == "y":
                    self._npc_seats.add(name)
                    print(f"  -> {name} set as NPC")
            names.append(name)

        if self._drinking:
            self.wager = self._ask_int("  Wager sips per hand (default 1): ", 1, 20, default=1)
        num_decks = self._ask_int("  Number of decks 1-8 (default 1): ", 1, 8, default=1)

        self.all_seats   = names
        self._house_mode = (n == 1)
        self._dealer_idx = 0
        self._assign_dealer()

        self.shoe = Shoe(num_decks)
        self.shoe.shuffle()

        mode_label = "Drinking Blackjack" if self._drinking else "Normal Blackjack"
        print(f"\n  Mode: {mode_label}")
        if self._house_mode:
            print("  Single-player vs House")
        else:
            total_hands = n * self.num_hands + 1
            print(f"  {n} players | dealer rotates every {n} round(s)")
            print(f"  First dealer: {self.dealer_player.name}")
            print(f"  Hands per round: {n} x {self.num_hands} + 1 dealer = {total_hands}")

    def _make_player(self, name):
        return NPC_Player(name) if name in self._npc_seats else Player(name)

    def _assign_dealer(self):
        prev = {p.name: (p.total_wins, p.total_losses, p.total_pushes, p.total_drinks)
                for p in self.players}

        if self._house_mode:
            human        = self._make_player(self.all_seats[0])
            house        = Player("House")
            house.is_dealer  = True
            house.dealer_hand = Hand()
            self.players      = [human]
            self.dealer_player = house
        else:
            dealer_name  = self.all_seats[self._dealer_idx]
            self.players = [self._make_player(n) for n in self.all_seats]
            for p in self.players:
                if p.name in prev:
                    p.total_wins, p.total_losses, p.total_pushes, p.total_drinks = prev[p.name]
                if p.name.lower() == dealer_name.lower():
                    p.is_dealer        = True
                    self.dealer_player = p

    def _rotate_dealer(self):
        if self._house_mode: return
        self._dealer_idx = (self._dealer_idx + 1) % len(self.all_seats)
        self._assign_dealer()
        print(f"  Dealer rotates => {self.dealer_player.name} is now dealer.")

    # ---------------------------------------------------------------- main loop

    def play(self):
        self.setup()

        while True:
            self.round_count += 1
            dealer_label = "House" if self._house_mode else self.dealer_player.name
            print(f"\n{'='*52}")
            print(f"  ROUND {self.round_count}  |  Dealer: {dealer_label}")
            print("="*52)

            tracker = None
            if self._drinking:
                from drinking_rules import DrinkTracker
                all_for_tracker = self.players + ([self.dealer_player] if self._house_mode else [])
                tracker = DrinkTracker(all_for_tracker, self.dealer_player)

            rm = RoundManager(
                self.players, self.dealer_player,
                self.shoe, tracker, self.wager, self.num_hands,
                drinking_mode=self._drinking
            )
            rm.play_round()

            if not self._house_mode and self.round_count % len(self.all_seats) == 0:
                self._rotate_dealer()

            if input("\nPlay another round? [y/n]: ").strip().lower() != "y":
                self._final_summary()
                break

    # ---------------------------------------------------------------- summary

    def _final_summary(self):
        print("\n" + "="*52)
        print("  FINAL SUMMARY")
        print("="*52)
        headers = ["Player", "Wins", "Losses", "Pushes"]
        if self._drinking:
            headers.append("Total Drinks")
        rows = []
        for p in self.players:
            row = [p.name, p.total_wins, p.total_losses, p.total_pushes]
            if self._drinking:
                row.append(p.total_drinks)
            rows.append(row)
        print(tabulate(rows, headers=headers, tablefmt="pretty"))
        print("\nThanks for playing!")

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _ask_int(prompt, lo, hi, default=None):
        while True:
            try:
                raw = input(f"  {prompt}").strip()
                if raw == "" and default is not None: return default
                val = int(raw)
                if lo <= val <= hi: return val
                print(f"  Enter a number between {lo} and {hi}.")
            except ValueError:
                print("  Invalid input.")


# =============================================================================
# Entry point
# =============================================================================

if __name__ == "__main__":
    game = BlackJackGame()
    game.play()
