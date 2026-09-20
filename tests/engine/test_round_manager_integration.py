"""
tests/test_round_manager_integration.py
========================================
Integration tests (Test-Plan.md §6): scripted, seeded rounds via
RoundManager that exercise multi-rule interactions end-to-end, plus a
RoundEndEvent + apply_end_of_round integration check for 4+ player halving.
"""

import io
import contextlib

from engine.blackjack import NPC_Player, Shoe, RoundManager
from engine.drinking_rules import DrinkTracker, DrinkingRules
from tests.conftest import make_card, make_player, make_hand


def _load_shoe(shoe, deal_order):
    """Preload a Shoe so deal_card() (pop from end) returns cards in
    `deal_order`, and disable reshuffling."""
    shoe.cards = list(reversed(deal_order))
    shoe.penetration = 1.0
    shoe.total_cards = len(shoe.cards)


def _always_stand(self, hand, dealer_up_card, valid_actions, drinking_mode=False):
    return "s"


def _run_round(rm):
    with contextlib.redirect_stdout(io.StringIO()):
        rm.play_round()


# ---------------------------------------------------------------------------
# 1. Hard Dealer Switch with A-clubs half protection
# ---------------------------------------------------------------------------

def test_hard_dealer_switch_with_ace_clubs_half_protection(monkeypatch):
    monkeypatch.setattr(NPC_Player, "decide", _always_stand)

    p1 = NPC_Player("Player1")
    p2 = NPC_Player("Player2")
    p2.is_dealer = True
    players = [p1, p2]

    shoe = Shoe(1)
    # Deal order: P1.h0[0], P2.h0[0], dealer_hand[0], P1.h0[1], P2.h0[1], dealer_hand[1]
    deal_order = [
        make_card("10", "S"),  # P1 card 1
        make_card("9", "D"),   # P2 card 1
        make_card("A", "C"),   # dealer_hand card 1 -> half protection
        make_card("9", "H"),   # P1 card 2  (P1 hand = 19)
        make_card("10", "C"),  # P2 card 2  (P2 hand = 19)
        make_card("6", "D"),   # dealer_hand card 2 (dealer hand = 17, stands)
    ]
    _load_shoe(shoe, deal_order)

    tracker = DrinkTracker(players, p2)
    rm = RoundManager(players, p2, shoe, tracker, wager=1, num_hands=1, drinking_mode=True)
    _run_round(rm)

    # Dealer (P2) loses to both P1 and P2's own hand -> Hard Dealer Switch,
    # but the A-clubs dealt to the dealer hand halves the total (2 -> 1).
    assert p2.drink_log == [
        (1,
         "Hard Dealer Switch (A♣ half protection): Player2 drinks 1 sip(s) "
         "(halved from 2: Player1 regular win => 1 sip; Player2 regular win => 1 sip)",
         "dealer"),
    ]
    # P1 has no losses and isn't penalized (and the dealer is exempt on a hard switch).
    assert p1.drink_log == []


# ---------------------------------------------------------------------------
# 2. Split hand interactions: split-win immunity break + stacked loss penalties
# ---------------------------------------------------------------------------

def test_split_hand_immunity_break_and_stacked_loss_penalties(monkeypatch):
    actions = {
        "Player1": iter(["sp", "h", "s", "d"]),
        "Player2": iter(["s"]),
    }

    def decide(self, hand, dealer_up_card, valid_actions, drinking_mode=False):
        return next(actions[self.name])

    monkeypatch.setattr(NPC_Player, "decide", decide)

    p1 = NPC_Player("Player1")
    p2 = NPC_Player("Player2")
    p2.is_dealer = True
    players = [p1, p2]

    shoe = Shoe(1)
    deal_order = [
        make_card("8", "S"),   # P1 h0 card1 -> pair, will split
        make_card("9", "C"),   # P2 h0 card1
        make_card("10", "D"),  # dealer_hand card1
        make_card("8", "H"),   # P1 h0 card2 -> pair, will split
        make_card("10", "H"),  # P2 h0 card2 (P2 hand = 19)
        make_card("7", "S"),   # dealer_hand card2 (dealer hand = 17, stands)
        make_card("10", "C"),  # P1 split-hand0: hit -> 8+10=18, stand
        make_card("9", "H"),   # P1 split-hand1: auto second card -> 8H+9H
        make_card("K", "H"),   # P1 split-hand1: double -> 8H+9H+KH = 27 bust, suited
    ]
    _load_shoe(shoe, deal_order)

    tracker = DrinkTracker(players, p2)
    rm = RoundManager(players, p2, shoe, tracker, wager=1, num_hands=1, drinking_mode=True)
    _run_round(rm)

    # Split-hand 0 wins at 18 (vs dealer 17); split-hand 1 doubled+bust+suited loses.
    assert p1.hands[0].result == "win"
    assert p1.hands[1].result == "loss"
    assert p1.hands[1].doubled is True
    assert p1.hands[1].is_suited() is True
    assert p2.hands[0].result == "win"

    reasons = [e[1] for e in p1.drink_log]
    sips = {e[0] for e in p1.drink_log}
    assert "Player1 lost a doubled hand => +1 sip(s)" in reasons
    assert "Player1 lost a suited hand => +1 sip(s)" in reasons
    assert any("swept all hands => Player1" in r for r in reasons)
    assert sips == {1}
    assert len(p1.drink_log) == 3

    # P2 swept (no losses/pushes) and isn't charged anything itself.
    assert p2.drink_log == []


# ---------------------------------------------------------------------------
# 3. All 4 aces dealt on the first deal
# ---------------------------------------------------------------------------

def test_all_four_aces_on_first_deal(monkeypatch):
    monkeypatch.setattr(NPC_Player, "decide", _always_stand)

    p1 = NPC_Player("Player1")
    p2 = NPC_Player("Player2")
    p2.is_dealer = True
    players = [p1, p2]

    shoe = Shoe(1)
    # Deal order: P1.h0[0], P2.h0[0], dealer_hand[0], P1.h0[1], P2.h0[1], dealer_hand[1]
    deal_order = [
        make_card("A", "S"),  # P1 card1
        make_card("A", "H"),  # P2 card1
        make_card("A", "D"),  # dealer_hand card1 (dealer shows Ace)
        make_card("A", "C"),  # P1 card2 -> all 4 aces visible after first deal
        make_card("5", "C"),  # P2 card2 (P2 hand = A+5 = 16)
        make_card("6", "S"),  # dealer_hand card2 (dealer hand = A+6 = 17, stands)
    ]
    _load_shoe(shoe, deal_order)

    tracker = DrinkTracker(players, p2)
    rm = RoundManager(players, p2, shoe, tracker, wager=1, num_hands=1, drinking_mode=True)
    _run_round(rm)

    assert rm._four_aces_fd is True

    four_aces_msg = "All 4 Aces on table after first deal => everyone drinks 2 sips"
    for p in players:
        entries = [(e[0], e[1]) for e in p.drink_log]
        assert (2, four_aces_msg) in entries


# ---------------------------------------------------------------------------
# 4. 4-player round-end halving (RoundEndEvent -> apply_end_of_round)
# ---------------------------------------------------------------------------

def test_round_end_event_halving_with_four_players():
    names = ["Alice", "Bob", "Carol", "Dave"]
    players = [make_player(n) for n in names]

    # Alice lost all 3 of her starting hands; everyone else pushed (so no
    # one else qualifies as a sweep "winner" and no extra messages fire).
    players[0].hands = [make_hand(("2", "H"), ("3", "D"), result="loss") for _ in range(3)]
    for p in players[1:]:
        p.hands = [make_hand(("8", "S"), ("8", "D"), result="push")]

    tracker = DrinkTracker(players, players[0])

    msgs = DrinkingRules.on_round_end(
        players, wager=1, dealer_bj=False, hard_switch_dealer="", num_hands=3,
    )
    assert msgs == [
        ("Alice", 3, "Alice net -3 hand(s) => drinks 3 sip(s) (net loss)"),
    ]

    tracker.apply_end_of_round(msgs)

    alice = players[0]
    # Raw entry unchanged...
    assert alice.drinks_owed() == 3
    # ...but a halving credit brings the net total down (4-player halving).
    net = sum(e[0] for e in alice.drink_log)
    assert net == 2
    assert any("halving" in e[1] for e in alice.drink_log)

    for p in players[1:]:
        assert p.drink_log == []
