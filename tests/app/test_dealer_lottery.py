"""
Tests for the Dealer Lottery post-round bonus event (Rules.md §5.9):
  - app/services/dealer_lottery.py
  - /dealer_lottery/enter and /dealer_lottery/give_sip routes (app/routes/polling.py)
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand, make_card
from app import create_app
from app.models.game_room import GameRoom, GameConfig, RoundState
from app.services.session_store import game_sessions, set_session
from app.services.serializer import serialize_state
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

def _make_room(num_players=3, dealer_hand=None, drinking_mode=True, easy_mode=False, num_hands=2):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=num_hands)
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


def test_maybe_start_npc_with_profile_uses_mined_stake():
    """An NPC_Player with a personality profile should submit its mined
    lottery_stakes tendency instead of always auto-opting-out at 0."""
    alice = make_player("Alice", is_dealer=True, dealer_hand=make_hand(("9", "S"), ("9", "H")))
    bob   = make_player("Bob")
    carol = make_player("Carol", is_npc=True)
    carol.personality = "highroller"
    carol._style_profile = {
        "player": "Carol", "deviations": [],
        "lottery_stakes": [{"owed_bucket": "none", "avg_stake": 4, "samples": 5}],
    }

    raw_session = RefereeSession([alice, bob, carol], "Alice", wager=1, num_hands=2)
    room = GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=True))

    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)

    pending = room.round._pending_dealer_lottery
    assert pending["entries"]["Carol"] == 4


def test_maybe_start_logs_npc_entry_decision():
    room = _make_room(num_players=3, dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room._get_player("Carol").is_npc = True
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)

    npc_rows = [r for r in room._dealer_lottery_decision_log if r["player"] == "Carol"]
    assert len(npc_rows) == 1
    assert npc_rows[0]["is_npc"] is True
    assert npc_rows[0]["x_entered"] == 0


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


def test_submit_entry_logs_human_decision():
    room = _make_room()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    submit_dealer_lottery_entry(room, "Alice", 3)

    human_rows = [r for r in room._dealer_lottery_decision_log if r["player"] == "Alice"]
    assert len(human_rows) == 1
    assert human_rows[0]["is_npc"] is False
    assert human_rows[0]["x_entered"] == 3
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


def test_result_seq_keeps_incrementing_across_rounds(monkeypatch):
    """Regression: _dealer_lottery_result_seq must survive a new round's
    RoundState replacement (it lives on DrinkLedger, not RoundState) --
    otherwise it resets to 0 every round, the frontend's already-advanced
    local pointer never sees a "new" value again, and the reveal modal only
    ever fires once per session no matter how many times the lottery
    triggers afterward."""
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 3)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)
    assert room.drinks._dealer_lottery_result_seq == 1

    # Simulate a new round: RoundState is replaced wholesale, same as
    # app/services/room_manager.py's newround handler does.
    room.round = RoundState()
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    submit_dealer_lottery_entry(room, "Alice", 3)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)
    assert room.drinks._dealer_lottery_result_seq == 2  # not reset back to 1


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


def test_resolve_neither_bust_drinks_stake(monkeypatch):
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    # Both hands stand immediately: 9 + King = 19
    _patch_deck(monkeypatch, [make_card("K", "C"), make_card("K", "D")])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert result["busted"] == 0
    # Drink X (no halving, 3 players, easy_mode off) -- was 2X before Proposal A.
    assert room.drinks.last_round_sips["Alice"] == 4
    assert result["drink_amounts"] == {"Alice": 4}


def test_resolve_one_bust_does_nothing(monkeypatch):
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
    # Proposal A: exactly one hand busting is a wash -- no drink, no credit.
    assert "Alice" not in room.drinks.last_round_sips
    assert result["drink_amounts"] == {}
    assert result["credit_amounts"] == {}


def test_resolve_survives_deck_exhaustion_from_long_hit_runs(monkeypatch):
    """Regression for the Dealer Lottery deck-exhaustion crash
    (docs/planning/Code-Audit-2026-07.md #2): a long run of low-card hits
    needed to reach 17 can pop more cards than the isolated one-off Deck()
    originally held. Before the fix, deck.cards.pop() on an empty list
    raised IndexError -- which would 500 the /state poll for the whole room,
    since resolve_dealer_lottery() runs on every tick via
    apply_dealer_lottery_entry_forfeit(). _draw() now replenishes with a
    fresh shuffled deck instead of crashing."""
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 3)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    deck_calls = []

    def _counting_deck():
        deck_calls.append(1)
        return _ScriptedDeck([make_card("6", "H")])  # only 1 card per "deck"

    monkeypatch.setattr("app.services.dealer_lottery.Deck", _counting_deck)
    monkeypatch.setattr("app.services.dealer_lottery.random.shuffle", lambda cards: None)

    resolve_dealer_lottery(room)  # must not raise IndexError

    # Deck() was called more than once -- proves the deck ran dry mid-hand
    # and _draw() replenished it instead of crashing.
    assert len(deck_calls) > 1

    # Both hands: 9 + 6 + 6 = 21 (stand, no bust, no split -- 9 and 6 don't pair).
    result = room.drinks.last_dealer_lottery_result
    assert [h["score"] for h in result["hands"]] == [21, 21]
    assert result["busted"] == 0
    assert result["drink_amounts"] == {"Alice": 3}


# ---------------------------------------------------------------------------
# Re-splitting (a new second card that itself pairs up) and the generalized
# all-bust/none-bust/mixed payout rule that scales to however many hands
# a re-split produces
# ---------------------------------------------------------------------------

def test_resolve_resplits_when_new_card_pairs_again(monkeypatch):
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("9", "D"),  # hand_a's 2nd card forms a new pair -> re-splits
        make_card("8", "C"),  # re-split hand #1: 9+8 = 17, stands
        make_card("8", "D"),  # re-split hand #2: 9+8 = 17, stands
        make_card("K", "C"),  # hand_b: 9+King = 19, stands
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert len(result["hands"]) == 3   # the re-split hand_a plus hand_b
    assert [h["score"] for h in result["hands"]] == [17, 17, 19]
    # hand_a (idx 0) and hand_b (idx 2) are the two original branch roots
    # (parent_index None); the re-split sibling (idx 1) split off hand_a.
    assert [h["parent_index"] for h in result["hands"]] == [None, 0, None]
    assert result["busted"] == 0
    # No hand busted -> drink X * (n_hands - 1) = 4 * (3 - 1) = 8. Scales
    # with hand count so standing through a re-split costs more than
    # standing on the un-split base case (see resolve_dealer_lottery's
    # docstring for why).
    assert room.drinks.last_round_sips["Alice"] == 8
    assert result["drink_amounts"] == {"Alice": 8}


def test_resolve_cascading_resplit_tracks_parent_chain(monkeypatch):
    """A hand whose new 2nd card pairs up TWICE in a row (re-splitting
    twice) must still correctly attribute both split-off siblings to the
    SAME parent hand -- and the flat `hands` list holds 4 entries: the
    twice-continuing root, its two siblings, and the untouched other
    branch. Regression coverage for the parent_index field added to
    support the reveal-modal animation ordering (see admin.js's
    _showDealerLotteryRevealModal)."""
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("9", "D"),   # hand_a's 2nd card pairs again -> re-splits (sibling1 split off)
        make_card("9", "C"),   # continuing hand_a's NEW 2nd card pairs AGAIN -> re-splits (sibling2 split off)
        make_card("8", "H"),   # continuing hand_a's 3rd attempt: 9+8=17, no match, stands
        make_card("8", "S"),   # sibling2: 9+8=17, stands
        make_card("Q", "C"),   # sibling1: 9+Q=19, stands
        make_card("K", "C"),   # hand_b: 9+K=19, stands
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert len(result["hands"]) == 4
    assert [h["score"] for h in result["hands"]] == [17, 17, 19, 19]
    # idx0 = hand_a's final continuation (root, no parent)
    # idx1 = sibling2 (split off hand_a 2nd) -- appears before sibling1 because
    #   the backend fully resolves hand_a's own continuing branch (including
    #   any further splits) before ever touching the FIRST sibling it split off
    # idx2 = sibling1 (split off hand_a 1st)
    # idx3 = hand_b (the other original branch root, no parent)
    assert [h["parent_index"] for h in result["hands"]] == [None, 0, 0, None]


def test_resolve_all_hands_bust_after_resplit_credits_and_opens_handout(monkeypatch):
    room = _nine_pair_room()
    room.drinks.last_round_sips["Alice"] = 10
    submit_dealer_lottery_entry(room, "Alice", 5)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("9", "D"),                          # hand_a re-splits
        make_card("5", "C"), make_card("K", "C"),      # re-split hand #1: 9+5=14, hit K -> 24 bust
        make_card("5", "D"), make_card("Q", "C"),      # re-split hand #2: 9+5=14, hit Q -> 24 bust
        make_card("5", "H"), make_card("J", "C"),      # hand_b: 9+5=14, hit J -> 24 bust
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert len(result["hands"]) == 3
    assert result["busted"] == 3   # every hand busted -> credit + handout
    assert room.drinks.last_round_sips["Alice"] == 5   # 10 - 5 credit
    assert result["pending_handouts"] == {"Alice": 5}


def test_resolve_exactly_one_bust_after_resplit_does_nothing(monkeypatch):
    """Only exactly 1 of 3 hands busting is still a wash under the
    >=2-bust rule -- 2 of 3 busting is covered separately below, since
    that's exactly the case the >=2 threshold (instead of the old
    all-N-bust requirement) changed."""
    room = _nine_pair_room()
    submit_dealer_lottery_entry(room, "Alice", 4)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("9", "D"),                          # hand_a re-splits
        make_card("8", "C"),                           # re-split hand #1: 9+8 = 17, stands
        make_card("8", "D"),                           # re-split hand #2: 9+8 = 17, stands
        make_card("5", "H"), make_card("K", "C"),      # hand_b: 9+5=14, hit K -> 24 bust
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert len(result["hands"]) == 3
    assert result["busted"] == 1   # exactly 1 of 3 busted -> still nothing happens
    assert result["drink_amounts"] == {}
    assert result["credit_amounts"] == {}
    assert "Alice" not in room.drinks.last_round_sips


def test_resolve_two_of_three_bust_after_resplit_credits_and_opens_handout(monkeypatch):
    """The behavior change from the old all-N-bust rule: 2 of 3 hands
    busting (not all 3) now credits + opens a handout, same as if all 3
    had busted -- a re-split only ever makes this easier to reach, never
    harder."""
    room = _nine_pair_room()
    room.drinks.last_round_sips["Alice"] = 10
    submit_dealer_lottery_entry(room, "Alice", 5)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)

    _patch_deck(monkeypatch, [
        make_card("9", "D"),                          # hand_a re-splits
        make_card("5", "C"), make_card("K", "C"),      # re-split hand #1: 9+5=14, hit K -> 24 bust
        make_card("8", "D"),                           # re-split hand #2: 9+8 = 17, stands
        make_card("5", "H"), make_card("J", "C"),      # hand_b: 9+5=14, hit J -> 24 bust
    ])
    resolve_dealer_lottery(room)

    result = room.drinks.last_dealer_lottery_result
    assert len(result["hands"]) == 3
    assert result["busted"] == 2   # 2 of 3, not all 3 -- still credits under the >=2 rule
    assert room.drinks.last_round_sips["Alice"] == 5   # 10 - 5 credit
    assert result["pending_handouts"] == {"Alice": 5}


def test_deal_and_resolve_hand_respects_max_splits_cap():
    """A hand already at the shared split cap must not split again, even
    when the newly dealt card would otherwise form another matching pair --
    the safety property that keeps a hot run of 9s/tens bounded (mirrors
    Hand.MAX_SPLITS, the same cap the main game's own hand-splitting uses)."""
    from app.services.dealer_lottery import _deal_and_resolve_hand
    from engine.blackjack import Hand

    hand = Hand()
    hand.cards.append(make_card("10", "S"))
    hand.split_count = Hand.MAX_SPLITS   # already at the cap

    class _OneCardDeck:
        def __init__(self):
            self.cards = list(reversed([make_card("J", "D")]))  # matches value 10

    result = _deal_and_resolve_hand(hand, _OneCardDeck(), None)
    assert len(result) == 1             # did not split again despite matching
    resolved_hand, parent = result[0]
    assert resolved_hand.score() == 20
    assert parent is None


def test_resolve_halves_handout_at_four_players(monkeypatch):
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


def test_resolve_drink_is_never_halved_even_under_easy_mode(monkeypatch):
    """The drink (no-hand-busts) branch is never halved -- only the handout
    (all-hands-bust branch) is. Easy Mode / 4+ players still governs the
    handout, but has no effect on the drink amount."""
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")), easy_mode=True)
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    submit_dealer_lottery_entry(room, "Alice", 3)
    for name in ("Bob", "Carol"):
        submit_dealer_lottery_entry(room, name, 0)

    # Neither hand busts: drink stays the full X=3, unhalved despite easy_mode
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


def test_give_sip_removes_giver_from_served_pending_handouts(monkeypatch):
    """Regression: serialize_state's pending_handouts/my_pending_handouts
    must stop listing a giver the instant they give -- last_dealer_lottery_
    result["pending_handouts"] is a static snapshot from resolve_dealer_
    lottery() that give_dealer_lottery_sip() never mutates, so without this
    exclusion the give-overlay panel (a full-screen modal) kept showing the
    already-given giver's button for the rest of the 90-second result
    window, appearing to freeze the table for everyone."""
    room = _both_bust_room(monkeypatch)
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice"], "role": "admin", "kicked": False,
    }

    before = serialize_state(room, "client-1")
    assert before["dealer_lottery"]["pending_handouts"] == {"Alice": 5}
    assert before["dealer_lottery"]["my_pending_handouts"] == {"Alice": 5}

    assert give_dealer_lottery_sip(room, "Alice", "Bob") is True

    after = serialize_state(room, "client-1")
    assert after["dealer_lottery"]["pending_handouts"] == {}
    assert after["dealer_lottery"]["my_pending_handouts"] == {}


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
# Milestone safety (confirms a Dealer Lottery credit never lets a player's
# cumulative sip_ticker go backwards, so it can't un-cross a milestone
# boundary already claimed)
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


# ---------------------------------------------------------------------------
# Flask routes: /dealer_lottery/enter, /dealer_lottery/give_sip
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def lottery_room_setup():
    """Register a 3-player room (Alice dealer, on a 9-9 hand) with a client
    registered as Alice and Bob as a local player on the same client, with
    a Dealer Lottery entry window already open."""
    room_code = "TestLottery1"
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice", "Bob"], "role": "admin", "kicked": False,
    }
    set_session(room_code, room)
    yield room_code, room
    game_sessions.pop(room_code, None)


def test_enter_route_records_entry(client, lottery_room_setup):
    room_code, room = lottery_room_setup
    resp = client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 3,
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room.round._pending_dealer_lottery["entries"]["Alice"] == 3


def test_enter_route_rejects_out_of_range_x(client, lottery_room_setup):
    room_code, room = lottery_room_setup
    resp = client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 9,
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "between 0 and 5" in data["error"]


def test_enter_route_rejects_when_no_pending(client):
    room_code = "TestLotteryNone"
    room = _make_room(dealer_hand=make_hand(("K", "S"), ("9", "H")))  # non-paired 19
    room._room_clients["client-1"] = {"name": "Alice", "local_names": ["Alice"], "role": "admin"}
    set_session(room_code, room)
    try:
        resp = client.post("/dealer_lottery/enter", json={
            "room_code": room_code, "client_id": "client-1", "x": 3,
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "No dealer lottery" in data["error"]
    finally:
        game_sessions.pop(room_code, None)


def test_enter_route_local_player_override(client, lottery_room_setup):
    room_code, room = lottery_room_setup
    resp = client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 2, "player_name": "Bob",
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room.round._pending_dealer_lottery["entries"]["Bob"] == 2
    assert room.round._pending_dealer_lottery["entries"]["Alice"] is None  # unaffected


def test_enter_route_rejects_player_not_local(client, lottery_room_setup):
    room_code, room = lottery_room_setup
    resp = client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 2, "player_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "not one of your local players" in data["error"].lower()


def test_enter_route_resolves_early_when_all_entries_in(client, lottery_room_setup):
    room_code, room = lottery_room_setup
    # Carol is an NPC in this room? No -- make her submit too, plus Bob (local to
    # client-1) and Alice, so every entrant (Alice, Bob, Carol) has answered.
    client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 0,
    })
    client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-1", "x": 0, "player_name": "Bob",
    })
    assert room.round._pending_dealer_lottery is not None  # Carol hasn't answered yet
    room._room_clients["client-2"] = {"name": "Carol", "local_names": ["Carol"], "role": "player"}
    resp = client.post("/dealer_lottery/enter", json={
        "room_code": room_code, "client_id": "client-2", "x": 0,
    })
    assert resp.get_json()["ok"] is True
    # All zero -> resolves immediately to a no-op (pending cleared, no result)
    assert room.round._pending_dealer_lottery is None
    assert room.drinks.last_dealer_lottery_result is None


def _lottery_room_with_handout(monkeypatch, room_code="TestLotteryHandout"):
    room = _make_room(dealer_hand=make_hand(("9", "S"), ("9", "H")))
    room.round._dealer_lottery_eligible = True
    maybe_start_dealer_lottery(room)
    room.drinks.last_round_sips["Alice"] = 10
    submit_dealer_lottery_entry(room, "Alice", 5)
    submit_dealer_lottery_entry(room, "Bob", 0)
    submit_dealer_lottery_entry(room, "Carol", 0)
    _patch_deck(monkeypatch, [
        make_card("5", "C"), make_card("9", "D"),
        make_card("5", "D"), make_card("9", "C"),
    ])
    resolve_dealer_lottery(room)
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice"], "role": "admin", "kicked": False,
    }
    set_session(room_code, room)
    return room_code, room


def test_give_sip_route_assigns(client, monkeypatch):
    room_code, room = _lottery_room_with_handout(monkeypatch)
    try:
        resp = client.post("/dealer_lottery/give_sip", json={
            "room_code": room_code, "client_id": "client-1",
            "giver_name": "Alice", "recipient_name": "Bob",
        })
        data = resp.get_json()
        assert data["ok"] is True
        assert room.drinks.last_round_sips["Bob"] == 5
    finally:
        game_sessions.pop(room_code, None)


def test_give_sip_route_rejects_not_local_player(client, monkeypatch):
    room_code, room = _lottery_room_with_handout(monkeypatch)
    try:
        resp = client.post("/dealer_lottery/give_sip", json={
            "room_code": room_code, "client_id": "client-1",
            "giver_name": "Bob", "recipient_name": "Carol",
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "not one of your local players" in data["error"].lower()
    finally:
        game_sessions.pop(room_code, None)


def test_give_sip_route_rejects_no_pending_handout(client, monkeypatch):
    room_code, room = _lottery_room_with_handout(monkeypatch)
    try:
        client.post("/dealer_lottery/give_sip", json={
            "room_code": room_code, "client_id": "client-1",
            "giver_name": "Alice", "recipient_name": "Bob",
        })
        resp = client.post("/dealer_lottery/give_sip", json={
            "room_code": room_code, "client_id": "client-1",
            "giver_name": "Alice", "recipient_name": "Carol",
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "already given" in data["error"].lower()
    finally:
        game_sessions.pop(room_code, None)


# ---------------------------------------------------------------------------
# Full-stack integration: a real digital round, dealt from a rigged shoe,
# driven entirely through /command and /state -- the same code path
# production traffic uses (initial_deal -> stand -> _after_player_action ->
# dealer_turn -> _resolve_endround -> apply_endround_pipeline -> tick()).
# Closes the one gap in the coverage above: every piece was unit/route-
# tested, but not through a genuinely dealt trigger.
# ---------------------------------------------------------------------------

def test_dealer_lottery_triggers_through_a_real_dealt_round(client):
    from engine.blackjack import Shoe

    room_code = "TestLotteryRealRound"
    room = _make_room(num_players=2, num_hands=1)
    room.start_round()

    # Rig the shoe so initial_deal() hands the dealer a real 20 (K, Q) --
    # a genuine two-card ten-value pair, dealt through the actual shoe.
    # initial_deal() order per pass: every player's hand(s), then the
    # dealer's own dealer_hand -- see app/services/game_engine.py.
    deal_order = [
        make_card("2", "S"),   # Alice (dealer-as-player) hand1 card 1
        make_card("2", "H"),   # Bob hand1 card 1
        make_card("K", "D"),   # dealer_hand card 1
        make_card("3", "S"),   # Alice hand1 card 2
        make_card("3", "H"),   # Bob hand1 card 2
        make_card("Q", "C"),   # dealer_hand card 2 -> dealer stands on K,Q = 20
    ]
    shoe = Shoe(1)
    shoe.cards = list(reversed(deal_order))
    shoe.penetration = 1.0
    shoe.total_cards = len(shoe.cards)
    room.shoe = shoe

    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice", "Bob"], "role": "admin", "kicked": False,
    }
    set_session(room_code, room)
    try:
        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "deal",
        })
        assert resp.get_json()["ok"] is not False  # /command has no explicit "ok" on success

        # Play order: dealer (Alice) plays last, so Bob's hand goes first.
        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Bob hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")

        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Alice hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")

        # dealer_turn() + _resolve_endround() ran synchronously inside that
        # last /command response (all hands were done) -- confirm the
        # dealer really did land on the rigged 20 and the trigger fired.
        dealer = room._get_dealer()
        assert [c.rank.label for c in dealer.dealer_hand.cards] == ["K", "Q"]
        assert dealer.dealer_hand.score() == 20
        assert room.round._dealer_lottery_eligible is True

        # A /state poll runs tick(), which promotes eligible -> pending
        # (no milestone in the way on round 1) with a real countdown.
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["dealer_lottery"]["pending"] is not None
        assert data["dealer_lottery"]["pending"]["total_count"] == 2
        assert room.round._pending_dealer_lottery is not None
    finally:
        game_sessions.pop(room_code, None)
