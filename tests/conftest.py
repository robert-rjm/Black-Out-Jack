"""
tests/conftest.py
==================
Shared fixtures/builders for the drinking-rules test suite.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.blackjack import Card, Hand, Player, NPC_Player, Rank, Suit


# ---------------------------------------------------------------------------
# Rank / Suit shorthand
# ---------------------------------------------------------------------------

_RANK_ALIASES = {
    "A": Rank.ACE, "2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR,
    "5": Rank.FIVE, "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT,
    "9": Rank.NINE, "10": Rank.TEN, "J": Rank.JACK, "Q": Rank.QUEEN,
    "K": Rank.KING,
}

_SUIT_ALIASES = {
    "S": Suit.SPADES, "H": Suit.HEARTS, "D": Suit.DIAMONDS, "C": Suit.CLUBS,
    "SPADES": Suit.SPADES, "HEARTS": Suit.HEARTS,
    "DIAMONDS": Suit.DIAMONDS, "CLUBS": Suit.CLUBS,
}


def _coerce_rank(rank) -> Rank:
    if isinstance(rank, Rank):
        return rank
    return _RANK_ALIASES[str(rank).upper()]


def _coerce_suit(suit) -> Suit:
    if isinstance(suit, Suit):
        return suit
    return _SUIT_ALIASES[str(suit).upper()]


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def make_card(rank, suit) -> Card:
    """make_card('A', 'S') -> Ace of Spades. Accepts Rank/Suit enums too."""
    return Card(_coerce_rank(rank), _coerce_suit(suit))


def make_hand(*cards, doubled: bool = False, from_split: bool = False,
               result=None, stood: bool = False, bust: bool = False,
               insured: bool = False) -> Hand:
    """
    Build a Hand from (rank, suit) tuples or Card objects, with result/flags
    set directly so resolution-stage rules can be tested without running a
    full round.
    """
    h = Hand(doubled=doubled, from_split=from_split)
    for c in cards:
        if isinstance(c, Card):
            h.cards.append(c)
        else:
            r, s = c
            h.cards.append(make_card(r, s))
    h.result  = result
    h.stood   = stood
    h.bust    = bust
    h.insured = insured
    return h


def make_player(name: str, hands=None, is_dealer: bool = False,
                 is_npc: bool = False, dealer_hand=None) -> Player:
    p = NPC_Player(name) if is_npc else Player(name)
    p.is_dealer = is_dealer
    p.hands = list(hands) if hands is not None else []
    if is_dealer:
        p.dealer_hand = dealer_hand if dealer_hand is not None else Hand()
    return p


@pytest.fixture
def ace_clubs_flag():
    """Fresh mutable flag dict per test, mirroring the real shared flag."""
    return {}


# ---------------------------------------------------------------------------
# Canonical hands
# ---------------------------------------------------------------------------

@pytest.fixture
def suited_21():
    """Two-card 21, suited (blackjack, all spades)."""
    return make_hand(("A", "S"), ("K", "S"), result="win")


@pytest.fixture
def blackjack_AJ_suited_black():
    """A♣ + J♣ — suited AND A+J AND both-black => x8 multiplier."""
    return make_hand(("A", "C"), ("J", "C"), result="win")


@pytest.fixture
def blackjack_plain():
    """Plain blackjack, no multipliers (e.g. A♥ + K♦)."""
    return make_hand(("A", "H"), ("K", "D"), result="win")


@pytest.fixture
def bust_hand():
    return make_hand(("K", "S"), ("Q", "H"), ("5", "D"), result="loss", bust=True)


@pytest.fixture
def five_card_21():
    """5-card 21 (not blackjack, since len != 2)."""
    return make_hand(("2", "H"), ("3", "D"), ("4", "C"),
                      ("5", "S"), ("7", "H"), result="win")


@pytest.fixture
def doubled_loss():
    return make_hand(("K", "S"), ("9", "H"), doubled=True, result="loss")
