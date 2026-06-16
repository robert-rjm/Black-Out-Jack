"""
Tests for the Bust Vote side bet (Test-Plan §9):
  - app/services/drink_tracker.apply_bust_vote_penalties
  - app/services/drink_tracker.apply_bust_handout_forfeit
  - /cast_bust_vote and /give_bust_sip routes (app/routes/polling.py)
"""

import time

import pytest

from app import create_app
from app.models.game_room import GameRoom
from app.services.session_store import game_sessions, set_session
from app.services.drink_tracker import (
    apply_bust_vote_penalties,
    apply_bust_handout_forfeit,
)
from engine.referee import RefereeSession
from engine.drinking_rules import classify_rule
from tests.conftest import make_player, make_hand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(num_players=3, bust_vote_enabled=True, dealer_hand=None):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=2)
    room = GameRoom(
        session=raw_session,
        mode="referee",
        bust_vote_enabled=bust_vote_enabled,
    )
    return room


# ---------------------------------------------------------------------------
# apply_bust_vote_penalties
# ---------------------------------------------------------------------------

def test_disabled_is_noop():
    room = _make_room(bust_vote_enabled=False)
    room.round._bust_votes = {"Bob": "bust"}
    apply_bust_vote_penalties(room)
    assert room.round._bust_vote_result is None


def test_no_votes_cast_is_noop():
    room = _make_room()
    room.round._bust_votes = {}
    apply_bust_vote_penalties(room)
    assert room.round._bust_vote_result is None


def test_all_votes_pass_is_noop():
    room = _make_room()
    room.round._bust_votes = {"Bob": "pass", "Carol": "pass"}
    apply_bust_vote_penalties(room)
    assert room.round._bust_vote_result is None


def test_dealer_no_dealer_hand_is_noop():
    room = _make_room(dealer_hand=make_hand())
    room._get_dealer().dealer_hand = None
    room.round._bust_votes = {"Bob": "bust"}
    apply_bust_vote_penalties(room)
    assert room.round._bust_vote_result is None


def test_dealer_busts_credits_winners():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # 25 -> bust
    room = _make_room(dealer_hand=busted_hand)
    room.round._bust_votes = {"Bob": "bust", "Carol": "bust"}
    apply_bust_vote_penalties(room)

    bob = room._get_player("Bob")
    carol = room._get_player("Carol")
    assert bob.drink_log == [(-1, "bust vote correct: -1 sip credit", "player")]
    assert carol.drink_log == [(-1, "bust vote correct: -1 sip credit", "player")]
    assert room.round._bust_vote_result == {
        "dealer_busted": True,
        "winners": ["Bob", "Carol"],
        "losers": [],
    }
    assert room.round._bust_handouts_given == set()
    assert room.round._bust_handout_expires_at is not None
    assert room.round._bust_handout_expires_at > time.monotonic()


def test_dealer_does_not_bust_penalizes_voters():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    room.round._bust_votes = {"Bob": "bust", "Carol": "bust"}
    apply_bust_vote_penalties(room)

    bob = room._get_player("Bob")
    carol = room._get_player("Carol")
    assert bob.drink_log == [(1, "Bust vote wrong — dealer didn't bust: +1 sip", "player")]
    assert carol.drink_log == [(1, "Bust vote wrong — dealer didn't bust: +1 sip", "player")]
    assert room.round._bust_vote_result == {
        "dealer_busted": False,
        "winners": [],
        "losers": ["Bob", "Carol"],
    }
    assert room.round._bust_handout_expires_at is None


def test_mixed_votes_dealer_busts():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # bust
    room = _make_room(num_players=4, dealer_hand=busted_hand)
    room.round._bust_votes = {"Bob": "bust", "Carol": "pass"}
    apply_bust_vote_penalties(room)

    bob = room._get_player("Bob")
    carol = room._get_player("Carol")
    dave = room._get_player("Dave")
    assert bob.drink_log == [(-1, "bust vote correct: -1 sip credit", "player")]
    assert carol.drink_log == []
    assert dave.drink_log == []
    assert room.round._bust_vote_result["winners"] == ["Bob"]
    assert room.round._bust_vote_result["losers"] == []


def test_classify_rule_round_trip():
    assert classify_rule("bust vote correct: -1 sip credit") is None
    assert classify_rule("Bust vote wrong — dealer didn't bust: +1 sip") == "Bust vote wrong call"


def test_winner_net_drinks_owed_floor():
    """A bust-vote winner with no other drinks this round shouldn't go negative."""
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))
    room = _make_room(dealer_hand=busted_hand)
    room.round._bust_votes = {"Bob": "bust"}
    apply_bust_vote_penalties(room)

    bob = room._get_player("Bob")
    assert bob.drinks_owed() == 0  # positive-only sum, the -1 entry is excluded
    net = sum(e[0] for e in bob.drink_log)
    assert net == -1
    assert max(0, net) == 0


# ---------------------------------------------------------------------------
# apply_bust_handout_forfeit
# ---------------------------------------------------------------------------

def test_forfeit_noop_when_no_expiry_set():
    room = _make_room()
    room.round._bust_handout_expires_at = None
    apply_bust_handout_forfeit(room)
    assert room._get_player("Bob").drink_log == []


def test_forfeit_noop_when_window_not_expired():
    room = _make_room()
    room.round._bust_vote_result = {"dealer_busted": True, "winners": ["Bob"], "losers": []}
    room.round._bust_handouts_given = set()
    room.round._bust_handout_expires_at = time.monotonic() + 100
    apply_bust_handout_forfeit(room)
    assert room._get_player("Bob").drink_log == []


def test_forfeit_applies_penalty_when_expired(monkeypatch):
    room = _make_room()
    room.round._bust_vote_result = {"dealer_busted": True, "winners": ["Bob"], "losers": []}
    room.round._bust_handouts_given = set()
    room.round._bust_handout_expires_at = time.monotonic() - 1  # already expired

    apply_bust_handout_forfeit(room)

    bob = room._get_player("Bob")
    assert bob.drink_log[-1][0] == 1
    assert "didn't assign in time" in bob.drink_log[-1][1]
    assert "Bob" in room.round._bust_handouts_given
    assert room.round._bust_handout_expires_at is None  # all winners resolved -> cleared


def test_forfeit_already_given_no_double_penalty():
    room = _make_room()
    room.round._bust_vote_result = {"dealer_busted": True, "winners": ["Bob"], "losers": []}
    room.round._bust_handouts_given = {"Bob"}
    room.round._bust_handout_expires_at = time.monotonic() - 1

    apply_bust_handout_forfeit(room)

    bob = room._get_player("Bob")
    assert bob.drink_log == []  # no penalty applied
    assert room.round._bust_handout_expires_at is None


def test_forfeit_partial_resolution_keeps_expiry():
    room = _make_room(num_players=4)
    room.round._bust_vote_result = {"dealer_busted": True, "winners": ["Bob", "Carol"], "losers": []}
    room.round._bust_handouts_given = {"Bob"}  # Bob already gave; Carol hasn't
    room.round._bust_handout_expires_at = time.monotonic() - 1

    apply_bust_handout_forfeit(room)

    carol = room._get_player("Carol")
    assert carol.drink_log[-1][0] == 1
    assert room.round._bust_handouts_given == {"Bob", "Carol"}
    assert room.round._bust_handout_expires_at is None  # all resolved now


def test_forfeit_no_result_or_winners_is_noop():
    room = _make_room()
    room.round._bust_vote_result = None
    room.round._bust_handout_expires_at = time.monotonic() - 1
    # Should not raise
    apply_bust_handout_forfeit(room)


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
    """Register a 3-player room with a client registered as Bob (and Carol as a
    local player on the same client), with a vote window open."""
    room_code = "TestRoom1"
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # dealer busts
    room = _make_room(num_players=3, dealer_hand=busted_hand)
    room.start_round()
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob", "Carol"], "role": "admin", "kicked": False,
    }
    room.round._bust_vote_expires_at = time.monotonic() + 60
    set_session(room_code, room)
    yield room_code, room
    game_sessions.pop(room_code, None)


# ---------------------------------------------------------------------------
# /cast_bust_vote
# ---------------------------------------------------------------------------

def test_cast_vote_not_enabled(client):
    room_code = "TestRoomDisabled"
    room = _make_room(bust_vote_enabled=False)
    room.start_round()
    room._room_clients["client-1"] = {"name": "Bob", "local_names": ["Bob"], "role": "admin"}
    set_session(room_code, room)
    try:
        resp = client.post("/cast_bust_vote", json={
            "room_code": room_code, "client_id": "client-1", "vote": "bust",
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "not enabled" in data["error"].lower()
    finally:
        game_sessions.pop(room_code, None)


def test_cast_vote_window_expired(client, room_setup):
    room_code, room = room_setup
    room.round._bust_vote_expires_at = time.monotonic() - 1  # expired

    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "closed" in data["error"].lower()


def test_cast_vote_invalid_vote_value(client, room_setup):
    room_code, room = room_setup
    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "maybe",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "vote must be" in data["error"].lower()


def test_cast_vote_records_and_recast_overwrites(client, room_setup):
    room_code, room = room_setup

    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    assert resp.get_json()["ok"] is True
    assert room.round._bust_votes["Bob"] == "bust"

    # Re-cast — last vote wins
    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "pass",
    })
    assert resp.get_json()["ok"] is True
    assert room.round._bust_votes["Bob"] == "pass"


def test_cast_vote_local_player_override(client, room_setup):
    room_code, room = room_setup

    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1",
        "vote": "bust", "player_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room.round._bust_votes["Carol"] == "bust"
    assert "Bob" not in room.round._bust_votes


def test_cast_vote_local_player_not_in_local_names_rejected(client, room_setup):
    room_code, room = room_setup

    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1",
        "vote": "bust", "player_name": "Alice",  # not in client-1's local_names
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "not one of your local players" in data["error"].lower()


def test_cast_vote_all_humans_voted_triggers_deferred_play(client, room_setup, monkeypatch):
    room_code, room = room_setup

    called = {"npc": False, "deferred": False}
    monkeypatch.setattr(
        "app.routes.polling.auto_play_npc_turns",
        lambda session: called.__setitem__("npc", True),
    )
    monkeypatch.setattr(
        "app.routes.polling._run_deferred_dealer_play",
        lambda session: called.__setitem__("deferred", True),
    )
    # Force phase to "playing" so auto_play_npc_turns would normally be invoked
    monkeypatch.setattr("app.routes.polling.round_phase", lambda session: "playing")

    # Bob votes for himself and Carol (both non-dealer humans) -> all humans voted
    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1",
        "vote": "bust", "player_name": "Carol",
    })
    assert resp.get_json()["ok"] is True

    # Dealer (Alice) also counts as a human player in the all-voted check;
    # simulate her vote having already been recorded.
    room.round._bust_votes["Alice"] = "pass"

    resp = client.post("/cast_bust_vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    assert resp.get_json()["ok"] is True

    assert called["npc"] is True
    assert called["deferred"] is True


# ---------------------------------------------------------------------------
# /give_bust_sip
# ---------------------------------------------------------------------------

def _set_winner(room, winner="Bob", dealer_busted=True, winners=None):
    room.round._bust_vote_result = {
        "dealer_busted": dealer_busted,
        "winners": winners if winners is not None else [winner],
        "losers": [],
    }
    room.round._bust_handouts_given = set()


def test_give_sip_not_a_winner(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winners=[])  # Bob is not in winners

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "no pending handout" in data["error"].lower()


def test_give_sip_dealer_did_not_bust(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winner="Bob", dealer_busted=False)

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "no pending handout" in data["error"].lower()


def test_give_sip_already_given(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winner="Bob")
    room.round._bust_handouts_given = {"Bob"}

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "already given" in data["error"].lower()


def test_give_sip_invalid_recipient(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winner="Bob")

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Zach",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "recipient not found" in data["error"].lower()


def test_give_sip_self_assignment_rejected(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winner="Bob")

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Bob",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "cannot give to yourself" in data["error"].lower()


def test_give_sip_valid_handout(client, room_setup):
    room_code, room = room_setup
    _set_winner(room, winner="Bob")

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is True

    carol = room._get_player("Carol")
    assert carol.drink_log[-1] == (1, "Bust vote handout from Bob: +1 sip", "player")
    assert "Bob" in room.round._bust_handouts_given
    assert room._last_round_sips["Carol"] >= 1
    assert room._sip_ticker["Carol"] >= 1
    assert any(
        row["player"] == "Carol" and row["rule"] == "Bust vote handout"
        for row in room._drink_csv_rows
    )


def test_give_sip_idempotent_after_forfeit(client, room_setup):
    """After apply_bust_handout_forfeit marks a winner as given, /give_bust_sip
    for that winner is rejected."""
    room_code, room = room_setup
    _set_winner(room, winner="Bob")
    room.round._bust_handout_expires_at = time.monotonic() - 1
    apply_bust_handout_forfeit(room)
    assert "Bob" in room.round._bust_handouts_given

    resp = client.post("/give_bust_sip", json={
        "room_code": room_code, "client_id": "client-1",
        "winner_name": "Bob", "recipient_name": "Carol",
    })
    data = resp.get_json()
    assert data["ok"] is False
    assert "already given" in data["error"].lower()
