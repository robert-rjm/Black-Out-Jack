"""
Tests for classify_rule — engine/drinking_rules.py

Covers every branch in source order, including ordering-sensitive overlaps.
"""

import pytest

from engine.drinking_rules import classify_rule


# ---------------------------------------------------------------------------
# None-returning (excluded from CSV) branches
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reason", [
    "A♣ dealt to Alice => -1 sip credit at round end",
    "A♣ protected this round",
    "A♣ protection credit applied",
    "Alice won the bust vote correct call",
    "Alice's A♣ protects them this round",
    "Alice is exempt from this round's charges",
])
def test_none_returning_reasons(reason):
    assert classify_rule(reason) is None


# ---------------------------------------------------------------------------
# Bust vote / insurance
# ---------------------------------------------------------------------------

def test_bust_vote_wrong_call():
    assert classify_rule("Bust vote wrong — dealer didn't bust: +1 sip") == "Bust vote wrong call"


def test_insurance_bj_holder_own_bonus():
    reason = ("Insurance (group voted insure) + dealer BJ: "
              "Alice drinks own bonus 2 sip(s), group protected")
    assert classify_rule(reason) == "Insurance: BJ holder drinks own bonus"


def test_insurance_group_double_bonus():
    reason = ("Insurance (group voted insure) + no dealer BJ: "
              "Bob drinks double BJ bonus 2 sip(s)")
    assert classify_rule(reason) == "Insurance: group drinks double BJ bonus"


# ---------------------------------------------------------------------------
# Hard Dealer Switch — half protection matched before generic
# ---------------------------------------------------------------------------

def test_hard_dealer_switch_half_protection_matched_first():
    reason = ("Hard Dealer Switch (A♣ half protection): Dealer drinks 2 sip(s) "
              "(halved from 3: ...)")
    assert classify_rule(reason) == "Hard Dealer Switch (half, A♣)"


def test_hard_dealer_switch_plain():
    reason = "Hard Dealer Switch: Dealer drinks 3 sip(s) (...)"
    assert classify_rule(reason) == "Hard Dealer Switch"


# ---------------------------------------------------------------------------
# Round-end / hand-resolution rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reason,expected", [
    ("Alice net -2 hand(s) => drinks 2 sip(s) (net loss)", "Net hand losses"),
    ("Alice lost a doubled hand => +1 sip(s)", "Lost doubled hand"),
    ("Alice lost a suited hand => +1 sip(s)", "Lost suited hand"),
    ("Bob won a doubled hand => Carol drinks 1 sip (immunity exception)", "Doubled win (immunity break)"),
    ("Alice won suited hand (all ♠) => Bob drinks 1 sip(s)", "Suited winning hand"),
    ("Alice won 2 split hand(s) => Bob drinks 1 sip(s)", "Split win (immunity break)"),
    ("Alice swept all hands => Bob drinks 2 sip(s)", "Other-player sweep"),
    ("Alice all-hands sweep (all ♠ suited across all hands) => Bob drinks 2 sip(s)", "All-hands sweep"),
    ("Alice blackjack: group declined insurance, dealer has BJ => auto-insurance applies, normal max sips only", "Dealer BJ (auto-insurance)"),
    ("Blackjack by Alice => Bob drinks 1 sip(s)", "Blackjack bonus"),
    ("All 4 Aces on table after first deal => everyone drinks 2 sips", "Four Aces (first deal)"),
    ("All 4 Aces visible at end of round => everyone drinks 1 sip", "Four Aces (end of round)"),
    ("Dealer hand is all ♥ => everyone drinks 2 sips", "Dealer suited hand"),
    ("Alice handed 1 sip to Bob (5-card 21)", "5-card 21 handout received"),
    ("Alice won with 5 cards => Bob drinks 1 sip", "5+ card win"),
])
def test_misc_canonical_mappings(reason, expected):
    assert classify_rule(reason) == expected


# ---------------------------------------------------------------------------
# Ace dealt — dealer-hand vs player-hand, dealer matched first
# ---------------------------------------------------------------------------

def test_ace_spades_dealer_hand():
    reason = "A♠ to dealer (card #1, odd) => Bob drinks 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Spades (dealer hand)"


def test_ace_hearts_dealer_hand():
    reason = "A♥ dealt to dealer => everyone drinks 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Hearts (dealer hand)"


def test_ace_diamonds_dealer_hand():
    reason = "A♦ dealt to dealer => all non-dealer players drink 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Diamonds (dealer hand)"


def test_ace_spades_player_hand():
    reason = "A♠ dealt to Alice (card #1) => Bob drinks 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Spades (player hand)"


def test_ace_hearts_player_hand():
    reason = "A♥ dealt to Alice => Alice drinks 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Hearts (player hand)"


def test_ace_diamonds_player_hand_when_no_dealer_word():
    """Branch only reachable with a constructed string lacking 'dealer'."""
    reason = "A♦ dealt to Alice => Bob drinks 1 sip"
    assert classify_rule(reason) == "Ace dealt: Ace of Diamonds (player hand)"


def test_ace_spades_string_with_both_markers_maps_to_dealer_variant():
    """A string containing both 'A♠' and 'dealer' maps to the dealer variant,
    not the player variant — dealer checks are matched first."""
    reason = "A♠ dealt to Alice, who is also dealer => Bob drinks 1 sip (to dealer)"
    assert classify_rule(reason) == "Ace dealt: Ace of Spades (dealer hand)"


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def test_unmatched_reason_returns_other():
    assert classify_rule("Some completely unrelated reason string") == "Other"
