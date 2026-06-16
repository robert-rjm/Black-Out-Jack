"""
engine/events.py
================
Typed game-event dataclasses that form the explicit contract between the
game engine (blackjack.py / game_engine.py / referee.py) and the drinking
rules layer (drinking_rules.py).

Every event that drinking_rules reacts to is declared here.  Adding a new
rule requires adding a dataclass here AND a matching case in
DrinkingRules.handle() — the `case _: raise NotImplementedError` guard in
handle() makes it impossible to silently miss a new event type.

NOTE — two DrinkingRules helpers are NOT events and are called directly:
  - check_four_aces(all_cards, phase, triggered_first_deal) → (msgs, bool)
      Stateful: returns the updated flag alongside drink messages.
  - dealer_21_five_cards(dealer_hand) → bool
      Query only: returns a boolean, fires no drink messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from engine.blackjack import Card, Hand, Player


# ---------------------------------------------------------------------------
# Event dataclasses — one per handled event type.
# ---------------------------------------------------------------------------

@dataclass
class CardDealtEvent:
    """Fired immediately after every card is physically dealt."""
    card:           Card
    recipient:      str
    card_pos:       int          # 1-indexed position in the recipient's current hand
    all_names:      list[str]
    dealer_name:    str
    ace_clubs_flag: dict         # mutable flag shared for the whole round
    is_dealer_hand: bool = False  # True only for the dealer's own dealer hand


@dataclass
class BlackjackEvent:
    """Fired for each uninsured winning blackjack after hand evaluation."""
    player_name:        str
    hand:               Hand
    all_names:          list[str]
    hard_switch_dealer: str = ""  # dealer-player name when a Hard Switch is in play


@dataclass
class InsuranceResolvedEvent:
    """Fired once per insurance-voted hand when dealer results are known."""
    player_name:        str
    hand:               Hand
    all_names:          list[str]
    insured:            bool       # True if majority voted to insure
    dealer_bj:          bool
    hard_switch_dealer: str = ""


@dataclass
class HandResolvedEvent:
    """Fired for every player hand after evaluation (win/loss/push known)."""
    player_name: str
    hand:        Hand
    all_names:   list[str]
    dealer_bj:   bool = False
    dealer_name: str  = ""  # exempt from bonus-win drinks on a Hard Switch


@dataclass
class AllHandsSweepEvent:
    """Fired for each non-dealer player to check a cross-hand sweep bonus."""
    player_name:  str
    player_hands: list[Hand]
    all_names:    list[str]
    wager:        int
    dealer_name:  str  = ""
    dealer_bj:    bool = False


@dataclass
class DealerHandRevealedEvent:
    """Fired once the dealer's full hand is visible (after dealer plays out)."""
    dealer_hand: Hand


@dataclass
class RoundEndEvent:
    """Fired once all hands are resolved — net losses, splits, sweeps."""
    players:            list[Player]
    wager:              int
    dealer_bj:          bool = False
    hard_switch_dealer: str  = ""
    num_hands:          int  = 0   # configured starting hands per player


@dataclass
class HardDealerSwitchEvent:
    """Fired when the dealer loses every hand at the table."""
    dealer_name:    str
    winning_hands:  list[tuple[str, Hand]]  # (player_name, hand) for each winning hand
    half_protected: bool = False            # True = dealer-hand A♣ half protection


# ---------------------------------------------------------------------------
# Union alias — use as the type annotation in handle() and callers.
# ---------------------------------------------------------------------------

GameEvent = Union[
    CardDealtEvent,
    BlackjackEvent,
    InsuranceResolvedEvent,
    HandResolvedEvent,
    AllHandsSweepEvent,
    DealerHandRevealedEvent,
    RoundEndEvent,
    HardDealerSwitchEvent,
]
