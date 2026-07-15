"""
Tests for the Dealer Lottery post-round bonus event
(docs/planning/DealerLottery-Plan.md):
  - app/services/dealer_lottery.py
"""

import time

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand, make_card
from app.models.game_room import GameRoom, GameConfig
from app.services.dealer_lottery import (
    _dealer_pair_trigger,
    check_dealer_lottery_trigger,
    maybe_start_dealer_lottery,
    submit_dealer_lottery_entry,
    apply_dealer_lottery_entry_forfeit,
    resolve_dealer_lottery,
    give_dealer_lottery_sip,
    apply_dealer_lottery_handout_forfeit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(num_players=3, dealer_hand=None, drinking_mode=True, easy_mode=False):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=2)
    room = GameRoom(
        session=raw_session,
        config=GameConfig(mode="digital", drinking_mode=drinking_mode, easy_mode=easy_mode),
    )
    return room


class _ScriptedDeck:
    """A fake deck whose .cards.pop() yields `pop_order` in that exact
    sequence (first element popped first) -- lets tests script an exact
    hit sequence for the lottery's split hands without fighting a real
    shuffle."""
    def __init__(self, pop_order):
        self.cards = list(reversed(pop_order))


def _patch_deck(monkeypatch, pop_order):
    monkeypatch.setattr(
        "app.services.dealer_lottery.Deck",
        lambda: _ScriptedDeck(pop_order),
    )
    monkeypatch.setattr("app.services.dealer_lottery.random.shuffle", lambda cards: None)


# ---------------------------------------------------------------------------
# _dealer_pair_trigger
# ---------------------------------------------------------------------------

def test_trigger_true_for_nine_pair():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    assert _dealer_pair_trigger(room) is True


def test_trigger_true_for_mixed_ten_value_pair():
    room = _make_room(dealer_hand=make_hand(("K", "S"), ("10", "H")))
    assert _dealer_pair_trigger(room) is True


def test_trigger_false_for_nonpaired_nineteen():
    room = _make_room(dealer_hand=make_hand(("K", "S"), ("9", "H")))
    assert _dealer_pair_trigger(room) is False


def test_trigger_false_for_three_card_hand():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H"), ("2", "D")))
    assert _dealer_pair_trigger(room) is False


def test_trigger_false_when_no_dealer_hand():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room._get_dealer().dealer_hand = None
    assert _dealer_pair_trigger(room) is False


# ---------------------------------------------------------------------------
# check_dealer_lottery_trigger / maybe_start_dealer_lottery
# ---------------------------------------------------------------------------

def test_check_trigger_sets_eligible_flag():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    check_dealer_lottery_trigger(room)
    assert room.round._dealer_lottery_eligible is True


def test_check_trigger_noop_outside_drinking_mode():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")), drinking_mode=False)
    check_dealer_lottery_trigger(room)
    assert room.round._dealer_lottery_eligible is False


def test_maybe_start_waits_for_milestone_to_clear():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room.round._dealer_lottery_eligible = True
    room.round._pending_milestone = {"boundary": 50, "winner": "Alice",
                                      "handout": 5, "expires_at": time.monotonic() + 60}
    maybe_start_dealer_lottery(room)
    assert room.round._pending_dealer_lottery is None


def test_maybe_start_opens_window_with_npc_auto_zero():
    room = _make_room(num_players=3, dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room._get_player("Carol").is_npc = True
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    pending = room.round._pending_dealer_lottery
    assert pending is not None
    assert pending["entries"]["Carol"] == 0     # NPC auto-submits
    assert pending["entries"]["Alice"] is None  # human awaiting entry
    assert pending["entries"]["Bob"] is None


def test_maybe_start_noop_when_not_eligible():
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    maybe_start_dealer_lottery(room)
    assert room.round._pending_dealer_lottery is None


# ---------------------------------------------------------------------------
# submit_dealer_lottery_entry
# ---------------------------------------------------------------------------

def test_submit_entry_records_and_clamps():
    room = _make_room()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    assert submit_dealer_lottery_entry(room, "Alice", 3) is True
    assert room.round._pending_dealer_lottery["entries"]["Alice"] == 3
    submit_dealer_lottery_entry(room, "Bob", 99)
    assert room.round._pending_dealer_lottery["entries"]["Bob"] == 5
    submit_dealer_lottery_entry(room, "Bob", -3)
    assert room.round._pending_dealer_lottery["entries"]["Bob"] == 0


def test_submit_entry_false_when_no_pending():
    room = _make_room()
    assert submit_dealer_lottery_entry(room, "Alice", 3) is False


def test_submit_entry_false_for_unknown_player():
    room = _make_room()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    assert submit_dealer_lottery_entry(room, "Zach", 3) is False


# ---------------------------------------------------------------------------
# apply_dealer_lottery_entry_forfeit
# ---------------------------------------------------------------------------

def test_entry_forfeit_noop_before_expiry():
    room = _make_room()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    apply_dealer_lottery_entry_forfeit(room)
    assert room.round._pending_dealer_lottery is not None  # untouched


def test_entry_forfeit_defaults_unset_to_zero_and_resolves(monkeypatch):
    room = _make_room()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    room.round._pending_dealer_lottery["expires_at"] = time.monotonic() - 1
    _patch_deck(monkeypatch, [])  # never reached since all entries default to 0
    apply_dealer_lottery_entry_forfeit(room)
    assert room.round._pending_dealer_lottery is None
    assert room.drinks.last_dealer_lottery_result is None  # all-zero -> skipped


# ---------------------------------------------------------------------------
# resolve_dealer_lottery -- payout branches
# ---------------------------------------------------------------------------

def _nine_pair_room(**kwargs):
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")), **kwargs)
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    return room


def test_resolve_all_zero_skips_draw(monkeypatch):
    room = _nine_pair_room()
    for name in room.round._pending_dealer_lottery["entries"]:
        submit_dealer_lottery_entry(room, name, 0)
    resolve_dealer_lottery(room)
    assert room.round._pending_dealer_lottery is None
    assert room.drinks.last_dealer_lottery_result is None


def test_resolve_both_bust_credits_and_opens_handout(monkeypatch):
    room = _nine_pair_room()
    room.drinks.last_round_sips["Alice"] = 3   # Alice owes 3 this round already
    submit_dealer_lottery_entry(room, "Alice", 5)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    # hand_a: 9 + 5 = 14 (hit) + 9 = 23 (bust)
    # hand_b: 9 + 5 = 14 (hit) + 9 = 23 (bust)
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert result["busted"] == 2
    # Credit floored at current owed (3), even though X=5
    assert room.drinks.last_round_sips["Alice"] == 0
    # Handout amount (not halved, only 3 players) is the full X=5, pending a recipient
    assert result["pending_handouts"] == {"Alice": 5}
    assert room.round._dealer_lottery_handout_expires_at is not None


def test_resolve_neither_bust_drinks_full_penalty(monkeypatch):
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    # Both hands stand immediately: 9 + King = 19
    _patch_deck(monkeypatch, [make_card("K", "C"), make_card("K", "D")])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert result["busted"] == 0
    # (2 - 0) * 4 = 8, no halving (3 players, easy_mode off)
    assert room.drinks.last_round_sips["Alice"] == 8


def test_resolve_one_bust_drinks_half_penalty(monkeypatch):
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    # hand_a stands: 9 + King = 19
    # hand_b busts: 9 + 5 = 14 (hit) + 9 = 23
    _patch_deck(monkeypatch, [
        make_card("K", "C"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert result["busted"] == 1
    # (2 - 1) * 4 = 4
    assert room.drinks.last_round_sips["Alice"] == 4


def test_resolve_halves_drink_and_handout_at_four_players(monkeypatch):
    room = _make_room(num_players=4, dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    submit_dealer_lottery_entry(room, "Alice", 5)
    for name in ("Bob", "Carol", "Dave"):
        submit_dealer_lottery_entry(room, name, 0)

    # Both bust -> handout should be ceil(5/2) = 3, halved
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    room.drinks.last_round_sips["Alice"] = 10  # plenty of room, no floor clamp in play
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert result["pending_handouts"] == {"Alice": 3}   # ceil(5/2)
    assert room.drinks.last_round_sips["Alice"] == 5    # 10 - 5 credit (not halved)


def test_resolve_halves_drink_penalty_with_easy_mode(monkeypatch):
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")), easy_mode=True)
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    submit_dealer_lottery_entry(room, "Alice", 3)
    for name in ("Bob", "Carol"):
        submit_dealer_lottery_entry(room, name, 0)

    # Neither hand busts: (2-0)*3 = 6 -> ceil(6/2) = 3
    _patch_deck(monkeypatch, [make_card("K", "C"), make_card("K", "D")])
    resolve_dealer_lottery(room)

    assert room.drinks.last_round_sips["Alice"] == 3


# ---------------------------------------------------------------------------
# give_dealer_lottery_sip / apply_dealer_lottery_handout_forfeit
# ---------------------------------------------------------------------------

def _both_bust_room(monkeypatch, x=5):
    room = _nine_pair_room()
    room.drinks.last_round_sips["Alice"] = 10
    submit_dealer_lottery_entry(room, "Alice", x)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)
    return room


def test_give_sip_assigns_and_closes_window(monkeypatch):
    room = _both_bust_room(monkeypatch)
    assert give_dealer_lottery_sip(room, "Alice", "Bob") is True
    assert room.drinks.last_round_sips["Bob"] == 5
    assert "Alice" in room.round._dealer_lottery_handouts_given
    assert room.round._dealer_lottery_handout_expires_at is None  # all givers done


def test_give_sip_rejects_self_assignment(monkeypatch):
    room = _both_bust_room(monkeypatch)
    assert give_dealer_lottery_sip(room, "Alice", "Alice") is False


def test_give_sip_rejects_double_give(monkeypatch):
    room = _both_bust_room(monkeypatch)
    give_dealer_lottery_sip(room, "Alice", "Bob")
    assert give_dealer_lottery_sip(room, "Alice", "Carol") is False


def test_give_sip_rejects_unknown_recipient(monkeypatch):
    room = _both_bust_room(monkeypatch)
    assert give_dealer_lottery_sip(room, "Alice", "Zach") is False


def test_handout_forfeit_noop_before_expiry(monkeypatch):
    room = _both_bust_room(monkeypatch)
    apply_dealer_lottery_handout_forfeit(room)
    assert "Alice" not in room.round._dealer_lottery_handouts_given


def test_handout_forfeit_gives_sips_to_self_after_expiry(monkeypatch):
    room = _both_bust_room(monkeypatch)  # starts owing 10, credited down to 5 (10 - X=5)
    room.round._dealer_lottery_handout_expires_at = time.monotonic() - 1
    apply_dealer_lottery_handout_forfeit(room)
    assert room.drinks.last_round_sips["Alice"] == 10  # 5 (post-credit) + 5 forfeited back
    assert "Alice" in room.round._dealer_lottery_handouts_given
    assert room.round._dealer_lottery_handout_expires_at is None


# ---------------------------------------------------------------------------
# Milestone safety (confirms docs/planning/DealerLottery-Plan.md §2/§3's claim)
# ---------------------------------------------------------------------------

def test_credit_never_reduces_cumulative_sip_ticker(monkeypatch):
    """A both-bust credit must only touch last_round_sips, never sip_ticker
    -- the number check_and_set_milestone actually checks against."""
    room = _nine_pair_room()
    room.drinks.sip_ticker["Alice"] = 105        # already crossed + claimed the 100 boundary
    room.drinks.last_round_sips["Alice"] = 5
    room.drinks.milestones_claimed[100] = "Alice"
    submit_dealer_lottery_entry(room, "Alice", 5)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)

    assert room.drinks.last_round_sips["Alice"] == 0     # credited down to the floor
    assert room.drinks.sip_ticker["Alice"] == 105        # cumulative total untouched
    assert room.drinks.milestones_claimed[100] == "Alice"  # claim still stands
