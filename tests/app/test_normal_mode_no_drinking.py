"""
tests/test_normal_mode_no_drinking.py
======================================
Phase A (Normal Mode rebuild) regression test: when drinking_mode=False,
a full round must produce zero drink/sip activity anywhere — no entries
in any player's drink_log, no tracker side effects, and the serialized
state must report empty/zero sip-related fields.
"""

import io
import contextlib

from engine.blackjack import NPC_Player, Shoe, RoundManager
from engine.drinking_rules import DrinkTracker
from tests.conftest import make_card


def _always_stand(self, hand, dealer_up_card, valid_actions, drinking_mode=False):
    return "s"


def _load_shoe(shoe, deal_order):
    shoe.cards = list(reversed(deal_order))
    shoe.penetration = 1.0
    shoe.total_cards = len(shoe.cards)


def _run_round(rm):
    with contextlib.redirect_stdout(io.StringIO()):
        rm.play_round()


def test_no_drink_log_entries_when_drinking_mode_false(monkeypatch):
    monkeypatch.setattr(NPC_Player, "decide", _always_stand)

    p1 = NPC_Player("Player1")
    p2 = NPC_Player("Player2")
    p2.is_dealer = True
    players = [p1, p2]

    shoe = Shoe(1)
    # Same deal as the drinking-mode hard-switch test, which normally
    # produces a Hard Dealer Switch drink penalty for the dealer.
    deal_order = [
        make_card("10", "S"),  # P1 card 1
        make_card("9", "D"),   # P2 card 1
        make_card("A", "C"),   # dealer_hand card 1
        make_card("9", "H"),   # P1 card 2 (P1 hand = 19)
        make_card("10", "C"),  # P2 card 2 (P2 hand = 19)
        make_card("6", "D"),   # dealer_hand card 2 (dealer hand = 17, stands)
    ]
    _load_shoe(shoe, deal_order)

    tracker = DrinkTracker(players, p2)
    rm = RoundManager(players, p2, shoe, tracker, wager=1, num_hands=1,
                       drinking_mode=False)
    _run_round(rm)

    # Despite a Hard Dealer Switch occurring, no drink messages are produced.
    assert p1.drink_log == []
    assert p2.drink_log == []


def test_four_aces_no_drink_events_when_drinking_mode_false(monkeypatch):
    monkeypatch.setattr(NPC_Player, "decide", _always_stand)

    p1 = NPC_Player("Player1")
    p2 = NPC_Player("Player2")
    p2.is_dealer = True
    players = [p1, p2]

    shoe = Shoe(1)
    # All four aces dealt on the first round of cards.
    deal_order = [
        make_card("A", "S"),  # P1 card 1
        make_card("A", "D"),  # P2 card 1
        make_card("A", "C"),  # dealer card 1
        make_card("A", "H"),  # P1 card 2
        make_card("2", "C"),  # P2 card 2
        make_card("6", "D"),  # dealer card 2
    ]
    _load_shoe(shoe, deal_order)

    tracker = DrinkTracker(players, p2)
    rm = RoundManager(players, p2, shoe, tracker, wager=1, num_hands=1,
                       drinking_mode=False)
    _run_round(rm)

    assert p1.drink_log == []
    assert p2.drink_log == []


def test_serializer_reports_empty_sip_fields_when_drinking_mode_false():
    """compute_sip_totals short-circuits to {} so the frontend never receives
    stale or leaked sip data in Normal mode."""
    from app.services.serializer import compute_sip_totals

    class _FakeDrinks:
        sip_ticker = {"Player1": 5}
        dealer_role_ticker = {"Player1": 3}

    class _FakeSession:
        drinking_mode = False
        drinks = _FakeDrinks()
        all_players = []

        class round:
            _drink_log_harvested = False

    session = _FakeSession()
    assert compute_sip_totals(session) == {}
