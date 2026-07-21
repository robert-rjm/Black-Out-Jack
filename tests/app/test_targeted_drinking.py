"""
Tests for Targeted Drinking Mode (Rules.md §5.10, MVP scope) -- a
standalone mini-game played between normal rounds, dealing its own
isolated dealer-only hand (mirrors Dealer Lottery's trigger/pending/
resolve shape):
  app/services/targeted_drinking.py; the
  /targeted_drinking/start + /targeted_drinking/cancel admin routes
  (app/routes/admin.py); the /targeted_drinking/vote player route
  (app/routes/polling.py); and the serializer's "targeted_drinking" block
  (app/services/serializer.py).
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand, make_card
from app import create_app
from app.models.game_room import GameRoom, GameConfig
from app.services.session_store import game_sessions, set_session
from app.services.serializer import serialize_state
from app.services.targeted_drinking import (
    start_targeted_drinking,
    check_targeted_drinking_trigger,
    targeted_drinking_awaiting_start,
    request_targeted_drinking_start,
    maybe_start_targeted_drinking_round,
    submit_targeted_drinking_vote,
    apply_targeted_drinking_vote_forfeit,
    resolve_targeted_drinking_round,
    end_targeted_drinking,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(num_players=3, drinking_mode=True):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    room = GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=drinking_mode))
    return room


class _ScriptedDeck:
    """A fake deck whose .cards.pop() yields `pop_order` in that exact
    sequence (first element popped first) -- lets tests script the
    isolated dealer hand's exact cards without fighting a real shuffle."""
    def __init__(self, pop_order):
        self.cards = list(reversed(pop_order))


def _patch_deck(monkeypatch, pop_order):
    monkeypatch.setattr(
        "app.services.targeted_drinking.Deck",
        lambda: _ScriptedDeck(pop_order),
    )
    monkeypatch.setattr("app.services.targeted_drinking.random.shuffle", lambda cards: None)


def _active_room_with_pending(monkeypatch, targets=("Bob",), hand_cards=None, num_players=3):
    """A room with the subgame active and a mini-round's vote window
    already open -- the common starting point for vote/forfeit/resolve
    tests. Requests the start itself (as if someone had tapped "Start
    Targeting Now") since that's a separate concern from whatever the
    calling test actually wants to exercise."""
    room = _make_room(num_players=num_players)
    start_targeted_drinking(room, list(targets))
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    if hand_cards is not None:
        _patch_deck(monkeypatch, hand_cards)
    return room


# ---------------------------------------------------------------------------
# start_targeted_drinking
# ---------------------------------------------------------------------------

def test_start_fails_with_no_targets():
    room = _make_room()
    assert start_targeted_drinking(room, []) is False
    assert room._targeted_drinking_active is False


def test_start_fails_for_unknown_player():
    room = _make_room()
    assert start_targeted_drinking(room, ["Nobody"]) is False
    assert room._targeted_drinking_active is False


def test_start_succeeds_and_zeroes_streaks():
    room = _make_room()
    assert start_targeted_drinking(room, ["Bob", "Carol"]) is True
    assert room._targeted_drinking_active is True
    assert room._targeted_drinking_targets == ["Bob", "Carol"]
    assert room._targeted_drinking_streaks == {"Bob": 0, "Carol": 0}
    # No cards dealt yet (pre-deal, not round-over) -- must NOT arm
    # eligibility itself; the first mini-round still waits for the
    # current round to actually finish (check_targeted_drinking_trigger).
    assert room.round._targeted_drinking_eligible is False


def test_start_is_case_insensitive_on_names():
    room = _make_room()
    assert start_targeted_drinking(room, ["bob"]) is True


def test_start_fails_if_already_active():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert start_targeted_drinking(room, ["Carol"]) is False
    assert room._targeted_drinking_targets == ["Bob"]   # untouched


def test_start_fails_during_cooldown():
    room = _make_room()
    room._targeted_drinking_cooldown_until_round = 5
    room.session.round_count = 2
    assert start_targeted_drinking(room, ["Bob"]) is False


def test_start_succeeds_once_cooldown_elapsed():
    room = _make_room()
    room._targeted_drinking_cooldown_until_round = 5
    room.session.round_count = 5
    assert start_targeted_drinking(room, ["Bob"]) is True


def test_start_does_not_interrupt_a_mini_round_already_in_progress():
    """Starting mid-round never opens a vote window immediately -- the
    first mini-round only opens once check_targeted_drinking_trigger runs
    (i.e. the current normal round ends)."""
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    maybe_start_targeted_drinking_round(room)   # no eligible flag set yet
    assert room.round._pending_targeted_drinking is None


# ---------------------------------------------------------------------------
# check_targeted_drinking_trigger
# ---------------------------------------------------------------------------

def test_check_trigger_noop_when_inactive():
    room = _make_room()
    check_targeted_drinking_trigger(room)
    assert room.round._targeted_drinking_eligible is False


def test_check_trigger_noop_outside_drinking_mode():
    room = _make_room(drinking_mode=False)
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    assert room.round._targeted_drinking_eligible is False


def test_check_trigger_sets_eligible_when_active():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    assert room.round._targeted_drinking_eligible is True


def test_check_trigger_idempotent_if_already_pending():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    pending_before = room.round._pending_targeted_drinking
    assert pending_before is not None
    check_targeted_drinking_trigger(room)   # must not disturb the open window
    assert room.round._pending_targeted_drinking is pending_before


# ---------------------------------------------------------------------------
# maybe_start_targeted_drinking_round
# ---------------------------------------------------------------------------

def test_maybe_start_noop_when_not_eligible():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


def test_maybe_start_waits_for_start_request():
    """The 'Start Targeting Now' gate: eligible + nothing else blocking is
    not enough on its own -- the first mini-round after a normal round
    ends also waits for someone to tap the button (see
    targeted_drinking_awaiting_start / request_targeted_drinking_start)."""
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    assert targeted_drinking_awaiting_start(room) is True
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None   # still waiting on the tap

    assert request_targeted_drinking_start(room) is True
    assert targeted_drinking_awaiting_start(room) is False   # requested -- no longer "awaiting"
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is not None


def test_request_start_noop_when_nothing_waiting():
    room = _make_room()
    assert request_targeted_drinking_start(room) is False   # subgame isn't even active

    start_targeted_drinking(room, ["Bob"])
    assert request_targeted_drinking_start(room) is False   # round hasn't ended yet either


def test_maybe_start_opens_window_with_all_targets_unanswered():
    room = _make_room()
    start_targeted_drinking(room, ["Bob", "Carol"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    pending = room.round._pending_targeted_drinking
    assert pending is not None
    assert pending["votes"] == {"Bob": None, "Carol": None}
    assert pending["expires_at"] > time.monotonic()


def test_maybe_start_does_not_reopen_an_already_open_window():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    first = room.round._pending_targeted_drinking
    assert first is not None
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is first


def test_maybe_start_waits_for_pending_milestone():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    room.round._pending_milestone = {"boundary": 50, "winner": "Alice", "handout": 5,
                                      "expires_at": time.monotonic() + 60}
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


def test_maybe_start_waits_for_dealer_lottery_eligible():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    room.round._dealer_lottery_eligible = True
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


def test_maybe_start_waits_for_pending_dealer_lottery():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    room.round._pending_dealer_lottery = {"expires_at": time.monotonic() + 20, "entries": {}}
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


# ---------------------------------------------------------------------------
# submit_targeted_drinking_vote
# ---------------------------------------------------------------------------

def test_submit_vote_rejects_when_no_pending():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "bust") is False


def test_submit_vote_rejects_non_target(monkeypatch):
    room = _active_room_with_pending(monkeypatch, targets=["Bob"])
    assert submit_targeted_drinking_vote(room, "Carol", "bust") is False
    assert "Carol" not in room.round._pending_targeted_drinking["votes"]


def test_submit_vote_rejects_invalid_value(monkeypatch):
    room = _active_room_with_pending(monkeypatch, targets=["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "maybe") is False


def test_submit_vote_records_valid_vote(monkeypatch):
    # Two targets so Bob's vote alone doesn't immediately resolve the
    # mini-round (submit_targeted_drinking_vote only auto-resolves once
    # *every* target has voted) -- this test is checking the vote gets
    # recorded, not the resolution path.
    room = _active_room_with_pending(monkeypatch, targets=["Bob", "Carol"])
    assert submit_targeted_drinking_vote(room, "Bob", "bust") is True
    assert room.round._pending_targeted_drinking["votes"]["Bob"] == "bust"
    assert room.round._pending_targeted_drinking["votes"]["Carol"] is None


# ---------------------------------------------------------------------------
# apply_targeted_drinking_vote_forfeit / resolve_targeted_drinking_round
# ---------------------------------------------------------------------------

def test_forfeit_noop_before_expiry(monkeypatch):
    room = _active_room_with_pending(monkeypatch, targets=["Bob"])
    apply_targeted_drinking_vote_forfeit(room)
    assert room.round._pending_targeted_drinking is not None   # unresolved, unchanged
    assert room._targeted_drinking_streaks["Bob"] == 0


def test_forfeit_noop_when_no_pending():
    room = _make_room()
    apply_targeted_drinking_vote_forfeit(room)  # must not raise with no window at all


def test_forfeit_defaults_unanswered_votes_and_resolves(monkeypatch):
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    room.round._pending_targeted_drinking["expires_at"] = time.monotonic() - 1   # already expired

    apply_targeted_drinking_vote_forfeit(room)

    assert room.round._pending_targeted_drinking is None   # resolved and cleared
    assert room._targeted_drinking_streaks["Bob"] == 1     # defaulted "stand" was correct
    result = room.drinks.last_targeted_drinking_result
    assert result["votes"]["Bob"] == "stand"
    assert result["correct"]["Bob"] is True


def test_forfeit_does_not_override_an_explicit_vote(monkeypatch):
    # Two targets: Bob votes explicitly (and correctly) but Carol never
    # answers -- the round can't auto-resolve on Bob's vote alone (Carol
    # is still pending), so it stays open until the forfeit sweep defaults
    # Carol to "stand". That sweep must not clobber Bob's explicit vote.
    # dealer busts: K + 5 = 15 (hit) + K = 25
    room = _active_room_with_pending(
        monkeypatch, targets=["Bob", "Carol"],
        hand_cards=[make_card("K", "S"), make_card("5", "H"), make_card("K", "D")],
    )
    submit_targeted_drinking_vote(room, "Bob", "bust")   # explicit, correct
    room.round._pending_targeted_drinking["expires_at"] = time.monotonic() - 1

    apply_targeted_drinking_vote_forfeit(room)

    result = room.drinks.last_targeted_drinking_result
    assert result["votes"]["Bob"] == "bust"
    assert result["correct"]["Bob"] is True
    assert room._targeted_drinking_streaks["Bob"] == 1
    assert result["votes"]["Carol"] == "stand"   # defaulted, and wrong (dealer busted)
    assert result["correct"]["Carol"] is False


def test_resolve_noop_if_no_pending():
    room = _make_room()
    resolve_targeted_drinking_round(room)  # must not raise
    assert room._targeted_drinking_streaks == {}


def test_resolve_correct_guess_increments_streak_without_graduating(monkeypatch):
    # dealer busts: K + 5 = 15 (hit) + K = 25
    room = _active_room_with_pending(
        monkeypatch, targets=["Bob"],
        hand_cards=[make_card("K", "S"), make_card("5", "H"), make_card("K", "D")],
    )
    submit_targeted_drinking_vote(room, "Bob", "bust")   # correct: dealer busted
    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert "Bob" in room._targeted_drinking_targets   # not graduated yet (needs 3)
    assert room._targeted_drinking_active is True
    bob = room._get_player("Bob")
    assert bob.drink_log == []   # no sip awarded on a correct guess


def test_resolve_wrong_guess_resets_streak_and_awards_sip(monkeypatch):
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    room._targeted_drinking_streaks["Bob"] = 2   # pretend they were on a streak
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong: dealer stood

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 0
    assert "Bob" in room._targeted_drinking_targets   # still targeted
    # Counts toward the session total (and milestone progress)...
    assert room.drinks.sip_ticker["Bob"] == 1
    assert room.drinks.sip_ticker_excl_round_avg["Bob"] == 1
    # ...but not toward this (or any) round's own sip tally -- it happened
    # between rounds, not as part of any round's blackjack outcome, so it
    # can't skew "worst average sips/round" or the Last Round summary.
    assert "Bob" not in room.drinks.last_round_sips
    assert room.drinks.last_round_drinks == []
    result = room.drinks.last_targeted_drinking_result
    assert result["sips"]["Bob"] == 1
    assert result["hand"]["score"] == 19
    assert result["hand"]["bust"] is False
    # Statistics table: this mini-round counted as a wrong guess for Bob,
    # and the dealer stood (not a bust) on its one resolved hand this run.
    assert room._targeted_drinking_wrong_counts["Bob"] == 1
    assert room._targeted_drinking_correct_counts.get("Bob", 0) == 0
    assert room._targeted_drinking_dealer_hands == 1
    assert room._targeted_drinking_dealer_busts == 0


def test_resolve_graduates_after_streak_threshold_and_ends_subgame(monkeypatch):
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)   # only the first mini-round needs this -- resolve re-requests itself

    for _ in range(3):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "stand")  # correct each time
        resolve_targeted_drinking_round(room)
        # Mini-rounds chain back-to-back (no need to re-trigger from a fresh
        # normal round each time) -- just bypass the reveal-pause breather
        # between iterations so the loop doesn't need to sleep for real.
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is False   # subgame ended: everyone graduated
    assert room._targeted_drinking_targets == []
    assert room._targeted_drinking_cooldown_until_round == room.session.round_count + 3
    assert room.drinks.last_targeted_drinking_result["graduated"] == ["Bob"]


# ---------------------------------------------------------------------------
# Easter egg (Wild Card) launch: 5-sip cap + graduation-backfire payback
# ---------------------------------------------------------------------------

def test_easter_egg_cap_ends_run_as_loss_with_penalty(monkeypatch):
    """A target who never graduates and racks up 5 wrong-guess sips is
    force-ended right at the cap with one extra +1 penalty sip (6 total),
    and removed from the target list without graduating."""
    room = _make_room(num_players=3)   # Alice (dealer), Bob, Carol
    start_targeted_drinking(room, ["Bob"], presser_name="Carol")
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)

    for _ in range(5):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong every time
        resolve_targeted_drinking_round(room)
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is False
    assert room.drinks.last_targeted_drinking_summary["reason"] == "capped_out"
    assert room.drinks.sip_ticker["Bob"] == 6   # 5-sip cap + 1 penalty for not managing
    assert room.drinks.sip_ticker.get("Carol", 0) == 0   # presser untouched on a loss


def test_easter_egg_graduation_backfires_on_presser(monkeypatch):
    """A target who graduates before hitting the cap makes the easter egg
    backfire: the presser drinks whatever the target drank over the run."""
    room = _make_room(num_players=3)
    start_targeted_drinking(room, ["Bob"], presser_name="Carol")
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)

    # One wrong guess first (1 sip), then 3 correct in a row to graduate.
    maybe_start_targeted_drinking_round(room)
    _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong
    resolve_targeted_drinking_round(room)
    room.drinks.last_targeted_drinking_result["set_at"] = 0

    for _ in range(3):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "stand")   # correct
        resolve_targeted_drinking_round(room)
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is False
    assert room.drinks.last_targeted_drinking_summary["reason"] == "all_graduated"
    assert room.drinks.sip_ticker["Bob"] == 1     # only the one wrong guess before graduating
    assert room.drinks.sip_ticker["Carol"] == 1   # backfire: presser drinks what Bob drank


def test_easter_egg_graduation_with_no_misses_awards_presser_nothing(monkeypatch):
    """A target who graduates without ever missing owes the presser 0 --
    award_sips is never called for a zero payback."""
    room = _make_room(num_players=3)
    start_targeted_drinking(room, ["Bob"], presser_name="Carol")
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)

    for _ in range(3):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "stand")
        resolve_targeted_drinking_round(room)
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is False
    assert room.drinks.sip_ticker.get("Bob", 0) == 0
    assert room.drinks.sip_ticker.get("Carol", 0) == 0


def test_admin_started_subgame_has_no_cap_or_backfire(monkeypatch):
    """Without a presser (admin-started via the admin panel), wrong
    guesses never cap out or force-end the run early -- flat 1 sip each,
    same as before this mechanic existed."""
    room = _make_room(num_players=3)
    start_targeted_drinking(room, ["Bob"])   # no presser_name -> admin-started
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)

    for _ in range(6):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong every time
        resolve_targeted_drinking_round(room)
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is True   # never capped, still running
    assert room.drinks.sip_ticker["Bob"] == 6        # flat 1 sip per wrong guess, no cap penalty


def test_stats_table_accumulates_across_mini_rounds(monkeypatch):
    """The statistics table (correct/wrong per target, dealer bust rate)
    is a running tally across the whole subgame run, not reset each
    mini-round -- unlike last_targeted_drinking_result, which only ever
    reflects the most recent one."""
    room = _make_room(num_players=3)   # Alice, Bob, Carol
    start_targeted_drinking(room, ["Bob", "Carol"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)

    def _resolve(hand_cards, bob_vote, carol_vote):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, hand_cards)
        submit_targeted_drinking_vote(room, "Bob", bob_vote)
        submit_targeted_drinking_vote(room, "Carol", carol_vote)
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0   # skip the reveal-pause breather

    # Round 1: dealer stands (K+9=19). Bob calls stand (correct), Carol calls bust (wrong).
    _resolve([make_card("K", "S"), make_card("9", "H")], "stand", "bust")
    # Round 2: dealer busts (K+5=15, hit, +K=25). Bob calls bust (correct), Carol calls stand (wrong).
    _resolve([make_card("K", "S"), make_card("5", "H"), make_card("K", "D")], "bust", "stand")

    assert room._targeted_drinking_correct_counts == {"Bob": 2, "Carol": 0}
    assert room._targeted_drinking_wrong_counts == {"Bob": 0, "Carol": 2}
    assert room._targeted_drinking_dealer_hands == 2
    assert room._targeted_drinking_dealer_busts == 1
    # Streaks are per-mini-round-outcome (reset on a wrong guess), distinct
    # from the run-wide correct/wrong counters above.
    assert room._targeted_drinking_streaks == {"Bob": 2, "Carol": 0}


def test_resolve_rearms_eligible_for_back_to_back_mini_rounds(monkeypatch):
    """Regression guard: the subgame must not need a whole normal round to
    play out between mini-rounds -- as long as it's still running, the next
    one queues up immediately (only gated by the reveal-pause breather)."""
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong -- doesn't graduate
    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_active is True
    assert room.round._targeted_drinking_eligible is True   # re-armed, not waiting for a new round
    assert room.round._pending_targeted_drinking is None     # not yet -- reveal-pause still gating


def test_resolve_does_not_rearm_eligible_when_subgame_ends(monkeypatch):
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    room._targeted_drinking_streaks["Bob"] = 2   # one more correct call graduates
    submit_targeted_drinking_vote(room, "Bob", "stand")   # correct
    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_active is False
    assert room.round._targeted_drinking_eligible is False


def test_maybe_start_waits_out_the_reveal_pause_before_the_next_mini_round(monkeypatch):
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong -- doesn't graduate
    resolve_targeted_drinking_round(room)

    # Immediately after resolving, the breather is still in effect.
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None

    # Once the breather has elapsed, the next mini-round opens.
    room.drinks.last_targeted_drinking_result["set_at"] = 0
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is not None


def test_resolve_unanswered_vote_defaults_to_stand(monkeypatch):
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Bob"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    # No vote submitted at all -- resolve treats a missing vote as "stand".
    resolve_targeted_drinking_round(room)
    assert room._targeted_drinking_streaks["Bob"] == 1   # "stand" was correct


def test_resolve_only_targets_still_in_subgame_are_scored(monkeypatch):
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Bob", "Carol"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    submit_targeted_drinking_vote(room, "Bob", "stand")   # correct
    submit_targeted_drinking_vote(room, "Carol", "bust")  # wrong

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert room._targeted_drinking_streaks["Carol"] == 0
    assert "Bob" in room._targeted_drinking_targets
    assert "Carol" in room._targeted_drinking_targets
    assert room.drinks.sip_ticker.get("Bob") is None
    assert room.drinks.sip_ticker["Carol"] == 1
    # Neither shows up in the round-based tally -- Bob was correct (no
    # sip), and Carol's wrong-guess sip is deliberately excluded from it.
    assert "Bob" not in room.drinks.last_round_sips
    assert "Carol" not in room.drinks.last_round_sips
    # Statistics table tracks both outcomes for this one dealer hand.
    assert room._targeted_drinking_correct_counts["Bob"] == 1
    assert room._targeted_drinking_wrong_counts.get("Bob", 0) == 0
    assert room._targeted_drinking_wrong_counts["Carol"] == 1
    assert room._targeted_drinking_correct_counts.get("Carol", 0) == 0
    assert room._targeted_drinking_dealer_hands == 1
    assert room._targeted_drinking_dealer_busts == 0


def test_resolve_survives_deck_exhaustion_from_long_hit_runs(monkeypatch):
    """Regression for the same deck-exhaustion crash Dealer Lottery guards
    against (Code-Audit-2026-07.md #2): a long run of low-card hits needed
    to reach 17 can pop more cards than one isolated Deck() holds."""
    room = _active_room_with_pending(monkeypatch, targets=["Bob"])

    deck_calls = []

    def _counting_deck():
        deck_calls.append(1)
        return _ScriptedDeck([make_card("6", "H")])  # only 1 card per "deck"

    monkeypatch.setattr("app.services.targeted_drinking.Deck", _counting_deck)
    monkeypatch.setattr("app.services.targeted_drinking.random.shuffle", lambda cards: None)

    resolve_targeted_drinking_round(room)  # must not raise IndexError
    assert len(deck_calls) > 1


# ---------------------------------------------------------------------------
# end_targeted_drinking
# ---------------------------------------------------------------------------

def test_end_clears_state_and_sets_cooldown():
    room = _make_room()
    start_targeted_drinking(room, ["Bob", "Carol"])
    room.session.round_count = 10

    end_targeted_drinking(room, reason="admin_cancelled")

    assert room._targeted_drinking_active is False
    assert room._targeted_drinking_targets == []
    assert room._targeted_drinking_streaks == {}
    assert room._targeted_drinking_total_sips == {}
    assert room._targeted_drinking_cooldown_until_round == 13


def test_end_snapshots_summary_with_totals_and_bumps_seq(monkeypatch):
    # dealer busts: K + 5 = 15 (hit) + K = 25 -- Bob calls it wrong twice,
    # Carol never plays a mini-round at all (still gets a 0 in the recap).
    room = _active_room_with_pending(
        monkeypatch, targets=["Bob", "Carol"],
        hand_cards=[make_card("K", "S"), make_card("5", "H"), make_card("K", "D")],
    )
    submit_targeted_drinking_vote(room, "Bob", "stand")   # wrong -- dealer busted
    room.round._pending_targeted_drinking["expires_at"] = time.monotonic() - 1
    apply_targeted_drinking_vote_forfeit(room)   # Carol defaults to stand too, also wrong
    assert room._targeted_drinking_active is True   # neither graduated yet

    end_targeted_drinking(room, reason="admin_cancelled")

    summary = room.drinks.last_targeted_drinking_summary
    assert summary["reason"] == "admin_cancelled"
    assert summary["totals"] == {"Bob": 1, "Carol": 1}
    assert summary["correct"] == {"Bob": 0, "Carol": 0}
    assert summary["wrong"] == {"Bob": 1, "Carol": 1}
    assert summary["dealer_hands"] == 1
    assert summary["dealer_busts"] == 1
    assert room.drinks._targeted_drinking_summary_seq == 1
    assert room._targeted_drinking_total_sips == {}   # cleared after snapshotting
    assert room._targeted_drinking_correct_counts == {}
    assert room._targeted_drinking_wrong_counts == {}
    assert room._targeted_drinking_dealer_hands == 0
    assert room._targeted_drinking_dealer_busts == 0


def test_end_summary_reflects_reason_when_graduation_ends_it(monkeypatch):
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)   # only the first mini-round needs this -- resolve re-requests itself

    for _ in range(3):
        maybe_start_targeted_drinking_round(room)
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        submit_targeted_drinking_vote(room, "Bob", "stand")  # correct each time -- resolves and re-arms itself
        if room.drinks.last_targeted_drinking_result:
            room.drinks.last_targeted_drinking_result["set_at"] = 0

    assert room._targeted_drinking_active is False   # graduated out on its own
    summary = room.drinks.last_targeted_drinking_summary
    assert summary["reason"] == "all_graduated"
    assert summary["totals"] == {"Bob": 0}   # called it right every time -- never drank
    assert summary["correct"] == {"Bob": 3}
    assert summary["wrong"] == {"Bob": 0}
    assert summary["dealer_hands"] == 3
    assert summary["dealer_busts"] == 0


def test_end_is_idempotent():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    room.session.round_count = 10
    end_targeted_drinking(room, reason="admin_cancelled")
    cooldown_after_first_end = room._targeted_drinking_cooldown_until_round

    room.session.round_count = 999   # would produce a different cooldown if re-applied
    end_targeted_drinking(room, reason="admin_cancelled")
    assert room._targeted_drinking_cooldown_until_round == cooldown_after_first_end


def test_end_discards_an_in_flight_mini_round_without_scoring(monkeypatch):
    # Two targets so Bob's vote alone doesn't auto-resolve the round (Carol
    # never answers) -- it's still genuinely pending, with a real
    # (unresolved, undealt) hand, when the admin cancels mid-vote.
    room = _active_room_with_pending(monkeypatch, targets=["Bob", "Carol"])
    submit_targeted_drinking_vote(room, "Bob", "bust")

    end_targeted_drinking(room, reason="admin_cancelled")

    assert room.round._pending_targeted_drinking is None
    assert room.round._targeted_drinking_eligible is False
    bob_drink_log = room._get_player("Bob").drink_log
    assert bob_drink_log == []   # nobody's vote got scored


# ---------------------------------------------------------------------------
# Flask app + route fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def room_setup():
    """Register a 3-player room with a client registered as Bob, admin role."""
    room_code = "TDRoom1"
    room = _make_room(num_players=3)
    room.start_round()
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob"], "role": "admin", "kicked": False,
    }
    room._room_clients["client-2"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }
    set_session(room_code, room)
    yield room_code, room
    game_sessions.pop(room_code, None)


# ---------------------------------------------------------------------------
# /targeted_drinking/start
# ---------------------------------------------------------------------------

def test_start_route_requires_admin(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/targeted_drinking/start", json={
        "room_code": room_code, "client_id": "client-2",  # Carol is not admin
        "target_names": ["Carol"],
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "admin" in data["error"].lower()
    assert room._targeted_drinking_active is False


def test_start_route_rejects_empty_target_list(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/targeted_drinking/start", json={
        "room_code": room_code, "client_id": "client-1", "target_names": [],
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert room._targeted_drinking_active is False


def test_start_route_rejects_unknown_target(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/targeted_drinking/start", json={
        "room_code": room_code, "client_id": "client-1", "target_names": ["Nobody"],
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert room._targeted_drinking_active is False


def test_start_route_succeeds(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/targeted_drinking/start", json={
        "room_code": room_code, "client_id": "client-1", "target_names": ["carol"],
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room._targeted_drinking_active is True
    # sanitize_name capitalises to match the stored player casing
    assert room._targeted_drinking_targets == ["Carol"]


def test_start_route_rejects_while_already_active(client, room_setup):
    room_code, room = room_setup
    start_targeted_drinking(room, ["Carol"])

    resp = client.post("/targeted_drinking/start", json={
        "room_code": room_code, "client_id": "client-1", "target_names": ["Bob"],
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert room._targeted_drinking_targets == ["Carol"]   # untouched


# ---------------------------------------------------------------------------
# /targeted_drinking/cancel
# ---------------------------------------------------------------------------

def test_cancel_route_requires_admin(client, room_setup):
    room_code, room = room_setup
    start_targeted_drinking(room, ["Carol"])

    resp = client.post("/targeted_drinking/cancel", json={
        "room_code": room_code, "client_id": "client-2",  # Carol is not admin
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert room._targeted_drinking_active is True


def test_cancel_route_ends_active_subgame(client, room_setup):
    room_code, room = room_setup
    start_targeted_drinking(room, ["Carol"])

    resp = client.post("/targeted_drinking/cancel", json={
        "room_code": room_code, "client_id": "client-1",
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room._targeted_drinking_active is False
    assert room._targeted_drinking_targets == []


def test_cancel_route_is_noop_when_inactive(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/targeted_drinking/cancel", json={
        "room_code": room_code, "client_id": "client-1",
    })
    data = resp.get_json()
    assert data["ok"] is True   # idempotent, still succeeds
    assert room._targeted_drinking_active is False


# ---------------------------------------------------------------------------
# /targeted_drinking/begin
# ---------------------------------------------------------------------------

def test_begin_route_rejects_unregistered_client(client, room_setup):
    room_code, room = room_setup
    start_targeted_drinking(room, ["Carol"])
    check_targeted_drinking_trigger(room)

    resp = client.post("/targeted_drinking/begin", json={
        "room_code": room_code, "client_id": "not-a-real-client",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert targeted_drinking_awaiting_start(room) is True   # unaffected by the rejected attempt


def test_begin_route_any_registered_player_can_start(client, room_setup):
    """Not admin-only -- Carol (a plain player, not Bob the admin) can tap
    "Start Targeting Now" for herself."""
    room_code, room = room_setup
    start_targeted_drinking(room, ["Carol"])
    check_targeted_drinking_trigger(room)

    resp = client.post("/targeted_drinking/begin", json={
        "room_code": room_code, "client_id": "client-2",   # Carol, not admin
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert data["targeted_drinking"]["awaiting_start"] is False
    assert room.round._targeted_drinking_start_requested is True


def test_begin_route_noop_when_nothing_waiting(client, room_setup):
    room_code, room = room_setup   # subgame not even started
    resp = client.post("/targeted_drinking/begin", json={
        "room_code": room_code, "client_id": "client-1",
    })
    data = resp.get_json()
    assert data["ok"] is True   # still succeeds -- just a no-op
    assert room.round._targeted_drinking_start_requested is False


# ---------------------------------------------------------------------------
# /targeted_drinking/vote
# ---------------------------------------------------------------------------

@pytest.fixture
def td_vote_setup(monkeypatch):
    """Register a 4-player room with Targeted Drinking active against Carol
    and Dave and a mini-round's vote window already open, client registered
    as Carol. Two targets (rather than just Carol) so that Carol voting
    alone never auto-resolves the mini-round -- Dave is left unvoted so the
    window stays open for tests that re-cast or otherwise expect it to
    still be pending after Carol's vote."""
    room_code = "TDVoteRoom1"
    room = _make_room(num_players=4)
    room.start_round()
    start_targeted_drinking(room, ["Carol", "Dave"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }
    set_session(room_code, room)
    yield room_code, room
    game_sessions.pop(room_code, None)


def test_vote_route_rejects_when_no_pending(client):
    room_code = "TDVoteRoomInactive"
    room = _make_room(num_players=3)
    room.start_round()
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }
    set_session(room_code, room)
    try:
        resp = client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1", "vote": "bust",
        })
        data = resp.get_json()
        assert data["ok"] is False
    finally:
        game_sessions.pop(room_code, None)


def test_vote_route_rejects_when_window_closed(client, td_vote_setup):
    room_code, room = td_vote_setup
    room.round._pending_targeted_drinking["expires_at"] = time.monotonic() - 1   # expired

    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "closed" in data["error"].lower()


def test_vote_route_rejects_invalid_vote_value(client, td_vote_setup):
    room_code, room = td_vote_setup
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "maybe",
    })
    data = resp.get_json()
    assert data["ok"] is False


def test_vote_route_rejects_non_target(client):
    room_code = "TDVoteRoomNonTarget"
    room = _make_room(num_players=3)
    room.start_round()
    start_targeted_drinking(room, ["Carol"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob"], "role": "player", "kicked": False,
    }
    set_session(room_code, room)
    try:
        resp = client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1", "vote": "bust",
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "Bob" not in room.round._pending_targeted_drinking["votes"]
    finally:
        game_sessions.pop(room_code, None)


def test_vote_route_records_valid_vote(client, td_vote_setup):
    room_code, room = td_vote_setup
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room.round._pending_targeted_drinking["votes"]["Carol"] == "bust"

    # Re-cast -- last vote wins
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "stand",
    })
    assert resp.get_json()["ok"] is True
    assert room.round._pending_targeted_drinking["votes"]["Carol"] == "stand"


def test_vote_route_local_player_override(client):
    room_code = "TDVoteRoomLocal"
    # Two targets (Carol, Dave) so Carol's vote alone doesn't immediately
    # resolve the mini-round -- Dave is left unvoted.
    room = _make_room(num_players=4)
    room.start_round()
    start_targeted_drinking(room, ["Carol", "Dave"])
    check_targeted_drinking_trigger(room)
    request_targeted_drinking_start(room)
    maybe_start_targeted_drinking_round(room)
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob", "Carol"], "role": "player", "kicked": False,
    }
    set_session(room_code, room)
    try:
        resp = client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1",
            "vote": "bust", "player_name": "Carol",
        })
        data = resp.get_json()
        assert data["ok"] is True
        assert room.round._pending_targeted_drinking["votes"]["Carol"] == "bust"
        assert "Bob" not in room.round._pending_targeted_drinking["votes"]
    finally:
        game_sessions.pop(room_code, None)


def test_vote_route_local_player_not_in_local_names_rejected(client, td_vote_setup):
    room_code, room = td_vote_setup
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1",
        "vote": "bust", "player_name": "Alice",  # not in client-1's local_names
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "not one of your local players" in data["error"].lower()


# ---------------------------------------------------------------------------
# Serializer: "targeted_drinking" block
# ---------------------------------------------------------------------------

def test_serialize_state_pending_mini_round(monkeypatch):
    # Two targets so Carol voting alone leaves the mini-round (and its
    # streaks, all still at 0) unresolved and pending.
    room = _active_room_with_pending(monkeypatch, targets=["Carol", "Dave"], num_players=4)
    submit_targeted_drinking_vote(room, "Carol", "stand")
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    td = data["targeted_drinking"]
    assert td["active"] is True
    assert td["targets"] == ["Carol", "Dave"]
    assert td["streaks"] == {"Carol": 0, "Dave": 0}
    assert td["cooldown_until_round"] == 0
    assert td["pending"]["my_vote"] == "stand"
    assert td["pending"]["votes_cast"] == {"Carol": "stand"}
    assert 0 < td["pending"]["seconds_left"] <= 15
    assert td["last_result"] is None
    assert td["result_seq"] == 0
    assert td["last_summary"] is None
    assert td["summary_seq"] == 0
    # Live stats: zeroed for every target, nothing resolved yet this run.
    assert td["stats"] == {
        "correct": {"Carol": 0, "Dave": 0}, "wrong": {"Carol": 0, "Dave": 0},
        "dealer_hands": 0, "dealer_busts": 0,
    }


def test_serialize_state_last_result_after_resolve(monkeypatch):
    # dealer stands: K + 9 = 19
    room = _active_room_with_pending(monkeypatch, targets=["Carol"],
                                      hand_cards=[make_card("K", "S"), make_card("9", "H")])
    submit_targeted_drinking_vote(room, "Carol", "stand")   # correct
    resolve_targeted_drinking_round(room)
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    td = data["targeted_drinking"]
    assert td["pending"] is None
    assert td["result_seq"] == 1
    result = td["last_result"]
    assert result["hand"]["score"] == 19
    assert result["hand"]["bust"] is False
    assert result["votes"] == {"Carol": "stand"}
    assert result["correct"] == {"Carol": True}
    assert result["streaks"] == {"Carol": 1}
    assert td["last_summary"] is None   # subgame still running -- no recap yet
    assert td["summary_seq"] == 0
    # Live stats reflect this one resolved (non-bust) hand and Carol's correct call.
    assert td["stats"] == {"correct": {"Carol": 1}, "wrong": {"Carol": 0}, "dealer_hands": 1, "dealer_busts": 0}


def test_serialize_state_last_summary_after_end(monkeypatch):
    # dealer busts: K + 5 = 15 (hit) + K = 25
    room = _active_room_with_pending(
        monkeypatch, targets=["Carol"],
        hand_cards=[make_card("K", "S"), make_card("5", "H"), make_card("K", "D")],
    )
    submit_targeted_drinking_vote(room, "Carol", "stand")   # wrong -- auto-resolves (sole target)
    end_targeted_drinking(room, reason="admin_cancelled")
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    td = data["targeted_drinking"]
    assert td["active"] is False
    assert td["summary_seq"] == 1
    summary = td["last_summary"]
    assert summary["reason"] == "admin_cancelled"
    assert summary["totals"] == {"Carol": 1}
    assert summary["stats"] == {"correct": {"Carol": 0}, "wrong": {"Carol": 1}, "dealer_hands": 1, "dealer_busts": 1}
    # Live stats reset back to zero once the run's ended and been snapshotted.
    assert td["stats"] == {"correct": {}, "wrong": {}, "dealer_hands": 0, "dealer_busts": 0}


def test_serialize_state_targeted_drinking_inactive_defaults():
    room = _make_room(num_players=3)
    room.start_round()
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob"], "role": "player", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    td = data["targeted_drinking"]
    assert td["active"] is False
    assert td["targets"] == []
    assert td["streaks"] == {}
    assert td["pending"] is None
    assert td["last_result"] is None
    assert td["result_seq"] == 0
    assert td["last_summary"] is None
    assert td["summary_seq"] == 0
    assert td["awaiting_start"] is False
    assert td["stats"] == {"correct": {}, "wrong": {}, "dealer_hands": 0, "dealer_busts": 0}


def test_serialize_state_awaiting_start_before_and_after_request():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice"], "role": "admin", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    assert data["targeted_drinking"]["awaiting_start"] is True
    assert data["targeted_drinking"]["pending"] is None

    request_targeted_drinking_start(room)
    data = serialize_state(room, "client-1")
    assert data["targeted_drinking"]["awaiting_start"] is False


def test_serialize_state_awaiting_start_false_while_milestone_pending():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    room.round._pending_milestone = {"boundary": 50, "winner": "Alice", "handout": 5,
                                      "expires_at": time.monotonic() + 60}
    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice"], "role": "admin", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    # Not "awaiting start" -- it isn't even this mini-round's turn to open yet.
    assert data["targeted_drinking"]["awaiting_start"] is False


# ---------------------------------------------------------------------------
# Full-stack integration: a real round driven entirely through /command and
# /state, confirming the mini-game triggers automatically once the round
# ends and never interrupts play in progress -- the same code path
# production traffic uses.
# ---------------------------------------------------------------------------

def test_targeted_drinking_triggers_and_resolves_between_rounds(client, monkeypatch):
    from engine.blackjack import Shoe

    room_code = "TDBetweenRounds"
    room = _make_room(num_players=2)
    room.start_round()
    start_targeted_drinking(room, ["Bob"])

    # Deal order per pass: every player's hand(s) card N, then the dealer's
    # own dealer_hand card N. Dealer gets K,9 = 19 so it stands immediately
    # with no extra hits needed from this small rigged shoe.
    cards = [
        make_card("2", "S"),   # Alice (dealer-as-player) hand1 card 1
        make_card("2", "H"),   # Bob hand1 card 1
        make_card("K", "D"),   # dealer_hand card 1
        make_card("3", "S"),   # Alice hand1 card 2
        make_card("3", "H"),   # Bob hand1 card 2
        make_card("9", "C"),   # dealer_hand card 2 -> dealer stands on K,9 = 19
    ]
    shoe = Shoe(1)
    shoe.cards = list(reversed(cards))
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
        assert resp.get_json()["ok"] is not False

        # Mid-round: starting the subgame already happened above, before the
        # deal -- confirm no mini-round vote window opened during play.
        assert room.round._pending_targeted_drinking is None

        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Bob hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")
        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Alice hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")

        # Round just ended -- the mini-round is now eligible but waiting on
        # "Start Targeting Now" (nobody's tapped it yet), so a /state poll
        # (tick) must NOT open its vote window on its own.
        assert room.round._targeted_drinking_eligible is True
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["targeted_drinking"]["awaiting_start"] is True
        assert data["targeted_drinking"]["pending"] is None
        assert room.round._pending_targeted_drinking is None

        # Someone taps "Start Targeting Now" -- now the next poll opens it.
        resp = client.post("/targeted_drinking/begin", json={
            "room_code": room_code, "client_id": "client-1",
        })
        assert resp.get_json()["ok"] is True
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["targeted_drinking"]["awaiting_start"] is False
        assert data["targeted_drinking"]["pending"] is not None
        assert room.round._pending_targeted_drinking is not None

        # Vote, then force the window to expire and poll again to resolve.
        client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1", "vote": "stand",
        })
        room.round._pending_targeted_drinking["expires_at"] = time.monotonic() - 1
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["targeted_drinking"]["pending"] is None
        assert data["targeted_drinking"]["result_seq"] == 1
        assert data["targeted_drinking"]["last_result"]["correct"]["Bob"] is True
        assert room._targeted_drinking_streaks["Bob"] == 1
    finally:
        game_sessions.pop(room_code, None)


def test_start_while_already_between_rounds_arms_eligibility_immediately(client, monkeypatch):
    """Regression test: starting the subgame *after* a round has already
    ended (rather than before dealing it, like the test above) used to
    strand it -- check_targeted_drinking_trigger only ever fires once, at
    the moment a round *transitions into* round-over, so it would never
    fire again until an entire extra round played out. start_targeted_drinking
    must arm eligibility itself when the room's already sitting between
    rounds."""
    from engine.blackjack import Shoe

    room_code = "TDStartBetweenRounds"
    room = _make_room(num_players=2)
    room.start_round()

    cards = [
        make_card("2", "S"), make_card("2", "H"), make_card("K", "D"),
        make_card("3", "S"), make_card("3", "H"), make_card("9", "C"),
    ]
    shoe = Shoe(1)
    shoe.cards = list(reversed(cards))
    shoe.penetration = 1.0
    shoe.total_cards = len(shoe.cards)
    room.shoe = shoe

    room._room_clients["client-1"] = {
        "name": "Alice", "local_names": ["Alice", "Bob"], "role": "admin", "kicked": False,
    }
    set_session(room_code, room)
    try:
        client.post("/command", json={"room_code": room_code, "client_id": "client-1", "cmd": "deal"})
        client.post("/command", json={"room_code": room_code, "client_id": "client-1", "cmd": "stand Bob hand1"})
        client.post("/command", json={"room_code": room_code, "client_id": "client-1", "cmd": "stand Alice hand1"})

        # Round is over now, but Targeted Drinking was never started, so
        # check_targeted_drinking_trigger never ran for this round-over
        # period at all.
        assert room.round._targeted_drinking_eligible is False

        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        resp = client.post("/targeted_drinking/start", json={
            "room_code": room_code, "client_id": "client-1", "target_names": ["Bob"],
        })
        assert resp.get_json()["ok"] is True
        assert room.round._targeted_drinking_eligible is True   # armed immediately, not stranded

        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["targeted_drinking"]["eligible"] is True
        assert data["targeted_drinking"]["awaiting_start"] is True
        assert data["targeted_drinking"]["pending"] is None
    finally:
        game_sessions.pop(room_code, None)
