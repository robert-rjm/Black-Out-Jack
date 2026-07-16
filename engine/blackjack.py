"""
engine/blackjack.py
========================
🃏 Drinking BlackJack
========================
Core Blackjack game. Fully playable standalone (normal mode).
When drinking mode is selected at startup, drinking_rules.py is imported
and the DrinkTracker is activated alongside the game.

Run:
    python blackjack.py
"""

import random
from enum import Enum
from tabulate import tabulate

# NOTE: DrinkingRules and all engine.events imports are intentionally deferred
# to the call sites (lazy imports inside methods) to avoid a circular import:
#   blackjack.py → drinking_rules.py → blackjack.py (Rank, Suit, Hand, Player)
# Python caches modules after the first import so the per-call overhead is
# just a dict lookup — there is no re-execution penalty.


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
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

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
        # Set by deal_card() when a reshuffle happened *because the shoe ran
        # low mid-deal* (as opposed to a routine reshuffle the caller
        # triggers explicitly between rounds). Callers can check + clear
        # this to surface a toast to players.
        self.just_reshuffled = False
        for _ in range(num_decks):
            self.cards.extend(Deck().cards)


    def __len__(self):  return len(self.cards)

    def __str__(self):  return (f"Shoe({self.num_decks} deck(s), "
                                f"{len(self.cards)} remaining, "
                                f"pen {self.penetration:.0%})")
    def __repr__(self): return (f"Shoe(num_decks={self.num_decks}, "
                                f"cards_remaining={len(self.cards)}, "
                                f"penetration={self.penetration:.2%})")

    def shuffle(self, quiet: bool = False):
        random.shuffle(self.cards)
        if not quiet:
            print(f"Shoe shuffled - {len(self.cards)} cards ready.")

    def reset(self, num_decks: int = None, quiet: bool = False):
        self.__init__(num_decks or self.num_decks)
        self.shuffle(quiet=quiet)

    def needs_reshuffle(self) -> bool:
        return len(self.cards) < (1 - self.penetration) * self.total_cards

    def deal_card(self, quiet: bool = False) -> Card:
        if self.needs_reshuffle():
            if not quiet:
                print("Reshuffling shoe...")
            self.reset(quiet=quiet)
            self.just_reshuffled = True
        return self.cards.pop()


# =============================================================================
# Hand
# =============================================================================

class Hand:
    """
    One blackjack hand. Players hold a list of Hands
    (2 initial hands per the drinking rules; splits add more).
    """
    MAX_SPLITS = 4  # 4 splits per original starting hand = 5 hands total (aces included)

    def __init__(self, doubled: bool = False, from_split: bool = False):
        self.cards:     list = []
        self.doubled    = doubled
        self.from_split = from_split
        # Shared mutable counter so the split limit applies to the WHOLE
        # split tree descended from one starting hand, not just one branch's
        # depth. New hands created by split() share this same list with
        # their sibling/parent hands (see split() below).
        self._split_chain = [0]
        self.stood      = False
        self.bust       = False
        self.insured    = False
        self.result     = None   # "win" | "loss" | "push"

    @property
    def split_count(self) -> int:
        return self._split_chain[0]

    @split_count.setter
    def split_count(self, value: int) -> None:
        self._split_chain[0] = value

    # --- scoring ---
    def score(self) -> int:
        total = sum(c.rank.blackjack_value for c in self.cards)
        aces  = sum(1 for c in self.cards if c.rank == Rank.ACE)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def is_blackjack(self) -> bool: return len(self.cards) == 2 and self.score() == 21
    def is_bust(self)      -> bool: return self.score() > 21
    def is_suited(self)    -> bool: return len(self.cards) >= 2 and len({c.suit for c in self.cards}) == 1

    def can_split(self) -> bool:
        if len(self.cards) != 2: return False
        return (self.cards[0].rank.blackjack_value == self.cards[1].rank.blackjack_value
                and self.split_count < self.MAX_SPLITS)

    def split(self) -> "Hand":
        """
        Remove second card into a new Hand.  Second cards are NOT dealt here —
        _play_hand deals each hand's second card just before that hand is played,
        so H1 is fully played before H2 ever receives its second card.
        """
        new_hand = Hand(from_split=True)
        new_hand.cards.append(self.cards.pop())
        self.from_split   = True
        new_hand._split_chain = self._split_chain  # share counter across the whole chain
        self.split_count += 1   # increments the shared counter for both hands
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

    def reset_round(self, num_hands: int = 2):
        self.hands       = [Hand() for _ in range(num_hands)]
        self.dealer_hand = Hand() if self.is_dealer else None
        self.drink_log   = []

    def round_wins(self)   -> int: return sum(1 for h in self.hands if h.result == "win")
    def round_losses(self) -> int: return sum(1 for h in self.hands if h.result == "loss")
    def round_pushes(self) -> int: return sum(1 for h in self.hands if h.result == "push")

    def net_losses(self)   -> int:
        """Raw net hand losses: losses minus wins, clamped to zero."""
        return max(0, self.round_losses() - self.round_wins())

    def drinks_owed(self)  -> int: return sum(e[0] for e in self.drink_log if e[0] > 0)

    def add_drink(self, sips: int, reason: str, role: str = "player"):
        """role: 'player' (betting-hand drink) or 'dealer' (dealer-seat drink)."""
        if sips != 0:
            self.drink_log.append((sips, reason, role))

    def __str__(self):  return self.name
    def __repr__(self): return f"Player({self.name})"


# Strategy tables and resolver live in strategy.py
from engine.strategy import best_play as _strategy_best_play  # noqa: E402


def get_player_hand(player: Player, hand_label: str) -> "Hand":
    """Resolve a player's betting hand by label ('hand1', 'hand2', …).

    Extends ``player.hands`` with empty Hand objects if the requested index
    doesn't exist yet. Always targets ``player.hands`` directly — never
    redirects to a dealer hand — so the dealer-player can still act on their
    own betting hands via this helper.
    """
    try:
        idx = int(hand_label.lower().replace("hand", "").strip()) - 1
    except (ValueError, AttributeError):
        idx = 0
    while len(player.hands) <= idx:
        player.hands.append(Hand())
    return player.hands[idx]


class NPC_Player(Player):
    """
    Computer-controlled seat using standard basic strategy, or a player-style
    profile when ``personality`` is set.

    personality: "basic" (default) | any name with a profile in
                 engine/player_profiles/<name>.json (e.g. "rob", "marko", "david").
    """
    def __init__(self, name: str = "Bot", personality: str = "basic"):
        super().__init__(name)
        self.is_npc      = True
        self.personality = personality.lower()
        self._style_profile: dict | None = None  # loaded lazily on first decide()

    def _get_profile(self) -> dict | None:
        if self.personality == "basic":
            return None
        if self._style_profile is None:
            from engine.style_strategy import load_profile
            self._style_profile = load_profile(self.personality)
        return self._style_profile

    def __repr__(self): return f"NPC_Player({self.name}, personality={self.personality!r})"

    @staticmethod
    def best_play(hand, dealer_up_card, valid_actions: list,
                  drinking_mode: bool = False) -> str:
        """Delegate to strategy.best_play — kept for backwards compatibility."""
        return _strategy_best_play(hand, dealer_up_card, valid_actions, drinking_mode)

    def decide(self, hand, dealer_up_card, valid_actions: list,
               drinking_mode: bool = False, visible_cards: list | None = None,
               sibling_hands: list | None = None) -> str:
        profile = self._get_profile()
        if profile is not None:
            from engine.style_strategy import best_play_for
            return best_play_for(profile, hand, dealer_up_card,
                                 valid_actions, drinking_mode,
                                 visible_cards=visible_cards,
                                 sibling_hands=sibling_hands)
        return _strategy_best_play(hand, dealer_up_card, valid_actions, drinking_mode)

    def decide_dealer_lottery_stake(self, current_owed: int) -> int:
        """Choose this NPC's Dealer Lottery entry (0-5), per its profile's
        mined lottery_stakes tendency. "basic" personality (or a profile with
        no mined lottery data) always opts out (0) -- same as before this
        was a real decision."""
        profile = self._get_profile()
        if profile is None:
            return 0
        from engine.style_strategy import decide_dealer_lottery_stake
        return decide_dealer_lottery_stake(profile, current_owed)


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
        self._ace_clubs_flag = {"partial_protected": False, "half_protected": False}
        self._four_aces_fd  = False
        # List of (player, hand, insured:bool) — populated after deal, resolved in _evaluate
        self._insurance_votes: list = []

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
            self._collect_insurance_votes()
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
        self._ace_clubs_flag = {"partial_protected": False, "half_protected": False}
        self._four_aces_fd   = False
        self._insurance_votes = []

    # ---------------------------------------------------------------- dealing

    def _deal_card_to(self, hand, recipient_name):
        card     = self.shoe.deal_card()
        card_pos = len(hand.cards) + 1
        hand.cards.append(card)

        if self.drinking_mode:
            from engine.drinking_rules import DrinkingRules
            from engine.events import CardDealtEvent
            is_dealer_hand = (hand is self.dealer_player.dealer_hand)
            msgs = DrinkingRules.handle(CardDealtEvent(
                card=card, recipient=recipient_name, card_pos=card_pos,
                all_names=self._all_names, dealer_name=self.dealer_player.name,
                ace_clubs_flag=self._ace_clubs_flag,
                is_dealer_hand=is_dealer_hand,
            ))
            for msg in msgs:
                _, s, reason = msg[0], msg[1], msg[2]
                if s == -1:
                    self._ace_credits.append(recipient_name)
                    print(f"    (i) {reason}")
                else:
                    self.tracker.apply([msg])   # pass full tuple; apply() extracts optional role
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
        from engine.drinking_rules import DrinkingRules
        all_cards = ([c for p in self.players for h in p.hands for c in h.cards]
                     + self.dealer_player.dealer_hand.cards)
        msgs, self._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, phase, self._four_aces_fd)
        self.tracker.apply(msgs)

    # ---------------------------------------------------------------- insurance vote

    def _collect_insurance_votes(self):
        """
        After the initial deal, scan all hands in deal order for blackjacks.
        When the dealer shows an Ace and a player has a blackjack, run a group
        vote (everyone except that player). Majority insures; tie = decline.
        Result stored in self._insurance_votes for resolution at round end.
        """
        dealer_up = self.dealer_player.dealer_hand.cards[0]
        if dealer_up.rank != Rank.ACE:
            return

        for p in self.players:
            for i, hand in enumerate(p.hands):
                if not hand.is_blackjack():
                    continue

                voters = [v for v in self.players if v is not p]
                if not voters:
                    continue

                print(f"\n--- Insurance vote: {p.name} Hand {i+1} has Blackjack ---")
                print(f"  Dealer shows Ace. Vote to insure {p.name}'s blackjack?")
                print(f"  (If insured + dealer BJ: {p.name} drinks own bonus, group safe)")
                print("  (If insured + no dealer BJ: group drinks double bonus)")

                insure_count  = 0
                decline_count = 0
                for voter in voters:
                    if voter.is_npc:
                        # NPCs always decline insurance
                        print(f"  {voter.name} (NPC): decline")
                        decline_count += 1
                    else:
                        raw = input(f"  {voter.name}: insure or decline? [i/d]: ").strip().lower()
                        if raw == "i":
                            insure_count += 1
                            print(f"  {voter.name}: insure")
                        else:
                            decline_count += 1
                            print(f"  {voter.name}: decline")

                insured = insure_count > decline_count  # tie goes to decline
                result  = "INSURE" if insured else "DECLINE"
                print(f"  Vote result: {insure_count} insure / {decline_count} decline => {result}")
                if insured:
                    hand.insured = True

                self._insurance_votes.append((p, hand, insured))

    # ---------------------------------------------------------------- player turns

    def _player_turns(self, ordered):
        for p in ordered:
            idx = 0
            while idx < len(p.hands):
                print(f"\n--- {p.name} Hand {idx+1} ---")
                self._play_hand(p, p.hands[idx], idx)
                idx += 1

    def _play_hand(self, player, hand, hand_idx):
        _BLUE  = "\033[94m"   # terminal-only colour helpers
        _RESET = "\033[0m"
        # Split hands start with 1 card; deal their second card now (after H1 is fully played)
        if hand.from_split and len(hand.cards) == 1:
            card = self._deal_card_to(hand, player.name)
            print(f"  {player.name} H{hand_idx+1}: second card dealt — {card}  -> {hand}")

        if hand.stood or hand.bust:
            return
        dealer_up = self.dealer_player.dealer_hand.cards[0]

        # Insurance — only offered in normal mode (drinking mode uses _collect_insurance_votes group vote)
        if not self.drinking_mode and dealer_up.rank == Rank.ACE and hand.is_blackjack():
            if player.is_npc:
                print(f"  {player.name} (NPC) declines insurance.")
            else:
                raw = input(
                    f"  Dealer shows A and you have Blackjack. "
                    f"{player.name}: take insurance? [y/n]: "
                    ).strip().lower()
                if raw == "y":
                    hand.insured = True
                    print(f"  {player.name} insures — Blackjack plays as regular 21.")

        # Natural blackjack
        if hand.is_blackjack():
            hand.stood = True
            print(f"  BLACKJACK! {hand}")
            if self.drinking_mode:
                from engine.drinking_rules import DrinkingRules
                from engine.events import BlackjackEvent
                self._drink(DrinkingRules.handle(BlackjackEvent(
                    player_name=player.name, hand=hand, all_names=self._all_names,
                )))
            return

        # Normal loop
        while not hand.stood and not hand.bust:
            print(f"  Hand: {hand}  |  Dealer shows: {dealer_up}")
            valid = ["h", "s"]
            if len(hand.cards) == 2 and not hand.doubled: valid.append("d")
            if hand.can_split():                          valid.append("sp")

            if player.is_npc:
                action = player.decide(hand, dealer_up, valid, self.drinking_mode)
                print(f"  {player.name} (NPC) => {_BLUE}{action}{_RESET}")
            else:
                # Show basic-strategy hint in blue before asking human
                hint = NPC_Player.best_play(hand, dealer_up, valid, self.drinking_mode)
                print(f"  {_BLUE}Best play: {hint}{_RESET}")
                # Mandatory 10-split warning (drinking mode only)
                if (self.drinking_mode
                        and "sp" in valid
                        and hand.cards[0].rank.blackjack_value == 10
                        and not hand.is_suited()):
                    print(f"  WARNING: rules require splitting "
                          f"{hand.cards[0]}, {hand.cards[1]} (mandatory unless suited)"
                          )
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
                new_hand = hand.split()
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
                        from engine.drinking_rules import DrinkingRules
                        from engine.events import BlackjackEvent
                        self._drink(DrinkingRules.handle(BlackjackEvent(
                            player_name=player.name, hand=hand, all_names=self._all_names,
                        )))
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
            from engine.drinking_rules import DrinkingRules
            from engine.events import DealerHandRevealedEvent
            self._drink(DrinkingRules.handle(DealerHandRevealedEvent(dealer_hand=d_hand)))

    # ---------------------------------------------------------------- evaluation

    def _evaluate(self):
        print("\n--- Results ---")
        d_hand          = self.dealer_player.dealer_hand
        dealer_bj       = d_hand.is_blackjack()
        winning_hds     = []
        dealer_lost_all = True

        # Pass 1 — evaluate results only (no drinking events yet)
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

            p.total_wins   += p.round_wins()
            p.total_losses += p.round_losses()
            p.total_pushes += p.round_pushes()

        # Determine hard switch now so drinking events can use it
        hard_switch        = dealer_lost_all and bool(winning_hds)
        self._hard_switch  = hard_switch   # shared with _round_end_drinks
        exempt_dealer      = self.dealer_player.name if hard_switch else ""

        # Pass 2 — fire drinking events with conditional dealer exemption
        if self.drinking_mode:
            from engine.drinking_rules import DrinkingRules
            from engine.events import (
                BlackjackEvent, HandResolvedEvent,
                InsuranceResolvedEvent, HardDealerSwitchEvent,
            )

            # Hands that went through a group insurance vote — resolved separately
            voted_hands = {id(entry[1]) for entry in self._insurance_votes}

            for p in self.players:
                for hand in p.hands:
                    if hand.is_blackjack() and hand.result == "win":
                        if id(hand) not in voted_hands:
                            # No vote was held (dealer didn't show Ace) — normal BJ bonus
                            self._drink(DrinkingRules.handle(BlackjackEvent(
                                player_name=p.name, hand=hand, all_names=self._all_names,
                                hard_switch_dealer=exempt_dealer,
                            )))
                    self._drink(DrinkingRules.handle(HandResolvedEvent(
                        player_name=p.name, hand=hand, all_names=self._all_names,
                        dealer_bj=dealer_bj, dealer_name=exempt_dealer,
                    )))

            # Resolve insurance votes now that dealer BJ is known
            for (p, hand, insured) in self._insurance_votes:
                self._drink(DrinkingRules.handle(InsuranceResolvedEvent(
                    player_name=p.name, hand=hand, all_names=self._all_names,
                    insured=insured, dealer_bj=dealer_bj,
                    hard_switch_dealer=exempt_dealer,
                )))

            if hard_switch:
                partial_protected = self._ace_clubs_flag.get("partial_protected", False)
                half_protected    = self._ace_clubs_flag.get("half_protected", False)
                # Partial protection (player-hand A♣): exclude dealer's own player
                # hands from the penalty — they still drink for everyone else's hands.
                hs_for_penalty = (
                    [h for h in winning_hds if h[0].lower() != self.dealer_player.name.lower()]
                    if partial_protected else winning_hds
                )
                # Insurance Case 2, sub-case B: dealer-player IS the BJ holder,
                # group voted insure, no dealer BJ → their BJ hand is covered by the
                # insurance rule (they drink nothing from insurance; group drinks double).
                # Exclude dealer's BJ hand from the Hard Switch penalty to avoid
                # double-counting.
                dealer_bj_insured = any(
                    p.name.lower() == self.dealer_player.name.lower()
                    and h.is_blackjack() and vote_insured and not dealer_bj
                    for (p, h, vote_insured) in self._insurance_votes
                )
                if dealer_bj_insured:
                    hs_for_penalty = [
                        (pn, h) for (pn, h) in hs_for_penalty
                        if not (pn.lower() == self.dealer_player.name.lower()
                                and h.is_blackjack())
                    ]
                self._drink(DrinkingRules.handle(HardDealerSwitchEvent(
                    dealer_name=self.dealer_player.name, winning_hands=hs_for_penalty,
                    half_protected=half_protected,
                )))

    def _round_end_drinks(self):
        from engine.drinking_rules import DrinkingRules
        from engine.events import RoundEndEvent
        d_hand    = self.dealer_player.dealer_hand
        dealer_bj = d_hand.is_blackjack()
        w         = self.wager
        if DrinkingRules.dealer_21_five_cards(d_hand):
            w *= 2
            print(f"  ★ Dealer 21 with {len(d_hand.cards)} cards — wager doubled to {w} sip(s) this round!")
        if dealer_bj:
            print("  ★ Dealer blackjack — auto-insurance: only net-loss sips apply.")
        hard_switch = getattr(self, "_hard_switch", False)
        self.tracker.apply(DrinkingRules.handle(RoundEndEvent(
            players=self.players, wager=w, dealer_bj=dealer_bj,
            hard_switch_dealer=self.dealer_player.name if hard_switch else "",
            num_hands=self.num_hands,
        )))
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
