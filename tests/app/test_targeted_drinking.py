"""
Tests for Targeted Drinking Mode (docs/planning/TargetedDrinkingMode.md,
MVP scope): app/services/targeted_drinking.py; the
/targeted_drinking/start + /targeted_drinking/cancel admin routes
(app/routes/admin.py); the /targeted_drinking/vote player route
(app/routes/polling.py); and the serializer's "targeted_drinking" block
(app/services/serializer.py).
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand
from app import create_app
from app.models.game_room import GameRoom, GameConfig
from app.services.session_store import game_sessions, set_session
from app.services.serializer import serialize_state
from app.services.targeted_drinking import (
    start_targeted_drinking,
    maybe_open_targeted_drinking_vote,
    submit_targeted_drinking_vote,
    apply_targeted_drinking_vote_forfeit,
    resolve_targeted_drinking_round,
    end_targeted_drinking,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_room(num_players=3, dealer_hand=None):
    """Build a minimal GameRoom with `num_players` players (Alice is dealer)."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    players[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()

    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    room = GameRoom(session=raw_session, config=GameConfig(mode="digital"))
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
    # Original subgame untouched
    assert room._targeted_drinking_targets == ["Bob"]


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


# ---------------------------------------------------------------------------
# maybe_open_targeted_drinking_vote
# ---------------------------------------------------------------------------

def test_maybe_open_vote_noop_when_inactive():
    room = _make_room()
    maybe_open_targeted_drinking_vote(room)
    assert room.round._targeted_drinking_expires_at is None


def test_maybe_open_vote_sets_expiry_once():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    maybe_open_targeted_drinking_vote(room)
    first_expiry = room.round._targeted_drinking_expires_at
    assert first_expiry is not None and first_expiry > time.monotonic()

    # Calling again before the window closes must not reset the countdown
    maybe_open_targeted_drinking_vote(room)
    assert room.round._targeted_drinking_expires_at == first_expiry


# ---------------------------------------------------------------------------
# submit_targeted_drinking_vote
# ---------------------------------------------------------------------------

def test_submit_vote_rejects_non_target():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Carol", "bust") is False
    assert "Carol" not in room.round._targeted_drinking_votes


def test_submit_vote_rejects_invalid_value():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "maybe") is False


def test_submit_vote_records_valid_vote():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    assert submit_targeted_drinking_vote(room, "Bob", "bust") is True
    assert room.round._targeted_drinking_votes["Bob"] == "bust"


# ---------------------------------------------------------------------------
# resolve_targeted_drinking_round
# ---------------------------------------------------------------------------

def test_resolve_noop_if_not_active():
    room = _make_room()
    resolve_targeted_drinking_round(room)  # must not raise
    assert room._targeted_drinking_streaks == {}


def test_resolve_noop_if_no_dealer_hand():
    room = _make_room(dealer_hand=make_hand())
    room._get_dealer().dealer_hand = None
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")
    resolve_targeted_drinking_round(room)
    # No crash, and nothing resolved (streak untouched)
    assert room._targeted_drinking_streaks == {"Bob": 0}


def test_resolve_correct_guess_increments_streak_without_graduating():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # 25 -> bust
    room = _make_room(dealer_hand=busted_hand)
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # correct: dealer busted
    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert "Bob" in room._targeted_drinking_targets   # not graduated yet (needs 3)
    assert room._targeted_drinking_active is True
    bob = room._get_player("Bob")
    assert bob.drink_log == []   # no sip awarded on a correct guess


def test_resolve_wrong_guess_resets_streak_and_awards_sip():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    room._targeted_drinking_streaks["Bob"] = 2   # pretend they were on a streak
    submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong: dealer stood

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 0
    assert "Bob" in room._targeted_drinking_targets   # still targeted
    assert room.drinks.last_round_sips["Bob"] == 1
    assert room.drinks.last_round_drinks[-1]["reason"].startswith(
        "Targeted Drinking: guessed bust, dealer stood"
    )


def test_resolve_graduates_after_streak_threshold_and_ends_subgame():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])

    for _ in range(3):
        submit_targeted_drinking_vote(room, "Bob", "stand")  # correct each time
        resolve_targeted_drinking_round(room)
        room.round._targeted_drinking_votes.clear()   # simulate a fresh round's votes

    assert room._targeted_drinking_active is False   # subgame ended: everyone graduated
    assert room._targeted_drinking_targets == []
    assert room._targeted_drinking_cooldown_until_round == room.session.round_count + 3


def test_resolve_unanswered_vote_defaults_to_stand():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    # No vote submitted at all -- resolve_targeted_drinking_round itself
    # treats a missing vote as "stand" (apply_targeted_drinking_vote_forfeit
    # additionally writes this into the votes dict before resolving).
    resolve_targeted_drinking_round(room)
    assert room._targeted_drinking_streaks["Bob"] == 1   # "stand" was correct


def test_resolve_only_targets_still_in_subgame_are_scored():
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(num_players=3, dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob", "Carol"])
    submit_targeted_drinking_vote(room, "Bob", "stand")   # correct
    submit_targeted_drinking_vote(room, "Carol", "bust")  # wrong

    resolve_targeted_drinking_round(room)

    assert room._targeted_drinking_streaks["Bob"] == 1
    assert room._targeted_drinking_streaks["Carol"] == 0
    assert "Bob" in room._targeted_drinking_targets
    assert "Carol" in room._targeted_drinking_targets
    assert room.drinks.last_round_sips.get("Bob") is None
    assert room.drinks.last_round_sips["Carol"] == 1


# ---------------------------------------------------------------------------
# apply_targeted_drinking_vote_forfeit
# ---------------------------------------------------------------------------

def test_forfeit_noop_before_expiry():
    room = _make_room()
    start_targeted_drinking(room, ["Bob"])
    room.round._targeted_drinking_expires_at = time.monotonic() + 100
    apply_targeted_drinking_vote_forfeit(room)
    assert room._targeted_drinking_streaks["Bob"] == 0   # unresolved, unchanged
    assert room.round._targeted_drinking_votes == {}


def test_forfeit_noop_when_no_window_open():
    room = _make_room()
    apply_targeted_drinking_vote_forfeit(room)  # must not raise with no window at all


def test_forfeit_defaults_unanswered_votes_but_does_not_resolve():
    # Regression guard: an expired window must NOT score the round itself --
    # only apply_endround_pipeline's call to resolve_targeted_drinking_round
    # (once the round has genuinely ended) may do that. Verified in-browser
    # that without this, every subsequent tick after expiry re-ran
    # resolve_targeted_drinking_round against a still-in-progress round's
    # placeholder dealer_hand, graduating a target within seconds.
    good_hand = make_hand(("K", "S"), ("9", "H"))  # 19 -> no bust
    room = _make_room(dealer_hand=good_hand)
    start_targeted_drinking(room, ["Bob"])
    room.round._targeted_drinking_expires_at = time.monotonic() - 1   # already expired

    apply_targeted_drinking_vote_forfeit(room)

    assert room.round._targeted_drinking_votes["Bob"] == "stand"
    assert room._targeted_drinking_streaks["Bob"] == 0   # not resolved yet

    # A second tick (window still expired) must not re-run it either.
    apply_targeted_drinking_vote_forfeit(room)
    assert room._targeted_drinking_streaks["Bob"] == 0


def test_forfeit_does_not_override_an_explicit_vote():
    busted_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))  # bust
    room = _make_room(dealer_hand=busted_hand)
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")   # explicit
    room.round._targeted_drinking_expires_at = time.monotonic() - 1

    apply_targeted_drinking_vote_forfeit(room)

    assert room.round._targeted_drinking_votes["Bob"] == "bust"


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
def td_vote_setup():
    """Register a 3-player room with Targeted Drinking active against Carol,
    a client registered as Carol (with Dave as a local player), and an open
    vote window."""
    room_code = "TDVoteRoom1"
    room = _make_room(num_players=3)
    room.start_round()
    start_targeted_drinking(room, ["Carol"])
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }
    room.round._targeted_drinking_expires_at = time.monotonic() + 60
    set_session(room_code, room)
    yield room_code, room
    game_sessions.pop(room_code, None)


def test_vote_route_rejects_when_inactive(client):
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
        assert "not active" in data["error"].lower()
    finally:
        game_sessions.pop(room_code, None)


def test_vote_route_rejects_when_window_closed(client, td_vote_setup):
    room_code, room = td_vote_setup
    room.round._targeted_drinking_expires_at = time.monotonic() - 1   # expired

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
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob"], "role": "player", "kicked": False,
    }
    room.round._targeted_drinking_expires_at = time.monotonic() + 60
    set_session(room_code, room)
    try:
        resp = client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1", "vote": "bust",
        })
        data = resp.get_json()
        assert data["ok"] is False
        assert "Bob" not in room.round._targeted_drinking_votes
    finally:
        game_sessions.pop(room_code, None)


def test_vote_route_records_valid_vote(client, td_vote_setup):
    room_code, room = td_vote_setup
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "bust",
    })
    data = resp.get_json()
    assert data["ok"] is True
    assert room.round._targeted_drinking_votes["Carol"] == "bust"

    # Re-cast -- last vote wins
    resp = client.post("/targeted_drinking/vote", json={
        "room_code": room_code, "client_id": "client-1", "vote": "stand",
    })
    assert resp.get_json()["ok"] is True
    assert room.round._targeted_drinking_votes["Carol"] == "stand"


def test_vote_route_local_player_override(client):
    room_code = "TDVoteRoomLocal"
    room = _make_room(num_players=3)
    room.start_round()
    start_targeted_drinking(room, ["Carol"])
    room._room_clients["client-1"] = {
        "name": "Bob", "local_names": ["Bob", "Carol"], "role": "player", "kicked": False,
    }
    room.round._targeted_drinking_expires_at = time.monotonic() + 60
    set_session(room_code, room)
    try:
        resp = client.post("/targeted_drinking/vote", json={
            "room_code": room_code, "client_id": "client-1",
            "vote": "bust", "player_name": "Carol",
        })
        data = resp.get_json()
        assert data["ok"] is True
        assert room.round._targeted_drinking_votes["Carol"] == "bust"
        assert "Bob" not in room.round._targeted_drinking_votes
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

def test_serialize_state_includes_targeted_drinking_block():
    room = _make_room(num_players=3)
    room.start_round()
    start_targeted_drinking(room, ["Carol"])
    room.round._targeted_drinking_expires_at = time.monotonic() + 12
    submit_targeted_drinking_vote(room, "Carol", "stand")
    room._room_clients["client-1"] = {
        "name": "Carol", "local_names": ["Carol"], "role": "player", "kicked": False,
    }

    data = serialize_state(room, "client-1")
    td = data["targeted_drinking"]
    assert td["active"] is True
    assert td["targets"] == ["Carol"]
    assert td["streaks"] == {"Carol": 0}
    assert td["my_vote"] == "stand"
    assert td["votes_cast"] == {"Carol": "stand"}
    assert 0 < td["seconds_left"] <= 12
    assert td["cooldown_until_round"] == 0


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
    assert td["my_vote"] is None
    assert td["votes_cast"] == {}
    assert td["seconds_left"] == 0


# ---------------------------------------------------------------------------
# Full-stack integration: a real digital round, dealt from a rigged shoe,
# driven entirely through /command and /state -- the same code path
# production traffic uses (deal -> stand -> stand -> dealer_turn ->
# _resolve_endround -> apply_endround_pipeline -> tick()). This locks in the
# apply_endround_pipeline ordering: resolve_targeted_drinking_round() must
# run *after* harvest_drink_log(), since harvest_drink_log's own snapshot
# step (_snapshot_round / _record_drinks_detail) overwrites
# last_round_sips/last_round_drinks wholesale from each player's drink_log,
# which would silently wipe out award_sips()'s contribution if the ordering
# were reversed.
# ---------------------------------------------------------------------------

def test_targeted_drinking_resolves_through_a_real_dealt_round(client):
    from engine.blackjack import Shoe
    from tests.conftest import make_card

    room_code = "TDRealRound"
    room = _make_room(num_players=2)
    room.start_round()
    start_targeted_drinking(room, ["Bob"])
    room._targeted_drinking_streaks["Bob"] = 2   # pretend a streak — must reset on a wrong guess

    # Deal order per pass: every player's hand(s) card N, then the dealer's
    # own dealer_hand card N (see app/services/game_engine.py).
    deal_order = [
        make_card("2", "S"),   # Alice (dealer-as-player) hand1 card 1
        make_card("2", "H"),   # Bob hand1 card 1
        make_card("K", "D"),   # dealer_hand card 1
        make_card("3", "S"),   # Alice hand1 card 2
        make_card("3", "H"),   # Bob hand1 card 2
        make_card("9", "C"),   # dealer_hand card 2 -> dealer stands on K,9 = 19 (no bust)
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
        assert resp.get_json()["ok"] is not False

        # Vote after the deal -- _cmd_deal_digital resets the vote window
        # each round (mirroring its own bust-vote reset), so a vote cast
        # before "deal" would be wiped out by it.
        assert submit_targeted_drinking_vote(room, "Bob", "bust")   # wrong: dealer will stand on 19

        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Bob hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")

        resp = client.post("/command", json={
            "room_code": room_code, "client_id": "client-1", "cmd": "stand Alice hand1",
        })
        assert "Out of order" not in (resp.get_json().get("output") or "")

        dealer = room._get_dealer()
        assert dealer.dealer_hand.score() == 19
        assert dealer.dealer_hand.is_bust() is False

        # resolve_targeted_drinking_round already ran synchronously inside
        # that last /command response's apply_endround_pipeline call. Bob
        # also owes normal drinking-mode sips for losing his hand to the
        # dealer's 19 -- check the Targeted Drinking entry specifically
        # (rather than the total) to confirm award_sips()'s contribution
        # survived harvest_drink_log's snapshot overwrite instead of being
        # silently dropped by it.
        assert room._targeted_drinking_streaks["Bob"] == 0
        td_entries = [
            d for d in room.drinks.last_round_drinks
            if d["name"] == "Bob" and d["reason"].startswith("Targeted Drinking:")
        ]
        assert len(td_entries) == 1
        assert td_entries[0]["sips"] == 1

        # A /state poll must still reflect it through the serializer.
        resp = client.get(f"/state?room_code={room_code}&client_id=client-1")
        data = resp.get_json()
        assert data["ok"] is True
        assert data["targeted_drinking"]["streaks"]["Bob"] == 0
    finally:
        game_sessions.pop(room_code, None)


# ---------------------------------------------------------------------------
# Per-round reset: /command deal must clear last round's vote + window
# (app/routes/game_commands.py's _cmd_deal_digital, mirroring its own
# `_bust_votes = {}` reset). Without this, a new round would inherit the
# previous round's already-expired window and stale votes, and
# maybe_open_targeted_drinking_vote() would never open a fresh one.
# ---------------------------------------------------------------------------

def test_deal_resets_targeted_drinking_votes_and_window(client):
    from engine.blackjack import Shoe
    from tests.conftest import make_card

    room_code = "TDDealReset"
    room = _make_room(num_players=2)
    room.start_round()
    start_targeted_drinking(room, ["Bob"])
    submit_targeted_drinking_vote(room, "Bob", "bust")
    room.round._targeted_drinking_expires_at = time.monotonic() - 1   # stale, expired

    shoe = Shoe(1)
    shoe.cards = list(reversed([make_card(r, s) for r in ("2", "3", "4", "5", "6", "7") for s in ("S",)]))
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

        assert room.round._targeted_drinking_votes == {}
        assert room.round._targeted_drinking_expires_at is None
    finally:
        game_sessions.pop(room_code, None)
