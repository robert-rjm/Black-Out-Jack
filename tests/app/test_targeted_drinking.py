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
    tests."""
    room = _make_room(num_players=num_players)
    start_targeted_drinking(room, list(targets))
    check_targeted_drinking_trigger(room)
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
    maybe_start_targeted_drinking_round(room)
    pending_before = room.round._pending_targeted_drinking
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


def test_maybe_start_opens_window_with_all_targets_unanswered():
    room = _make_room()
    start_targeted_drinking(room, ["Bob", "Carol"])
    check_targeted_drinking_trigger(room)
    maybe_start_targeted_drinking_round(room)
    pending = room.round._pending_targeted_drinking
    assert pending is not None
    assert pending["votes"] == {"Bob": None, "Carol": None}
    assert pending["expires_at"] > time.monotonic()


def test_maybe_start_does_not_reopen_an_already_open_window():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    maybe_start_targeted_drinking_round(room)
    first = room.round._pending_targeted_drinking
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is first


def test_maybe_start_waits_for_pending_milestone():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    room.round._pending_milestone = {"boundary": 50, "winner": "Alice", "handout": 5,
                                      "expires_at": time.monotonic() + 60}
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


def test_maybe_start_waits_for_dealer_lottery_eligible():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
    room.round._dealer_lottery_eligible = True
    maybe_start_targeted_drinking_round(room)
    assert room.round._pending_targeted_drinking is None


def test_maybe_start_waits_for_pending_dealer_lottery():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)
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
    assert room.drinks.last_round_sips["Bob"] == 1
    assert room.drinks.last_round_drinks[-1]["reason"].startswith(
        "Targeted Drinking: guessed bust, dealer stood"
    )
    result = room.drinks.last_targeted_drinking_result
    assert result["sips"]["Bob"] == 1
    assert result["hand"]["score"] == 19
    assert result["hand"]["bust"] is False


def test_resolve_graduates_after_streak_threshold_and_ends_subgame(monkeypatch):
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    check_targeted_drinking_trigger(room)

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
    assert room.drinks.last_round_sips.get("Bob") is None
    assert room.drinks.last_round_sips["Carol"] == 1


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
    assert room._targeted_drinking_cooldown_until_round == 13


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
    room = _active_room_with_pending(monkeypatch, targets=["Bob"])
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

        # Round just ended -- the mini-round should now be eligible, and a
        # /state poll (tick) opens its vote window.
        assert room.round._targeted_drinking_eligible is True
        _patch_deck(monkeypatch, [make_card("K", "S"), make_card("9", "H")])  # stands (19)
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["ok"] is True
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
