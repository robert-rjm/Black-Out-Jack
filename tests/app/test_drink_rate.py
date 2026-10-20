"""
Tests for Drink Rate Mode (app/services/drink_rate.py, app/routes/drink_rate.py,
and the rate application in drink_tracker.award_sips).
"""

import time

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player, make_hand
from app import create_app
from app.config import DRINK_RATE_PROTECTION_ROUNDS
from app.models.game_room import GameRoom, GameConfig
from app.services.drink_rate import (
    apply_drink_rate_forfeit, apply_queued_rates, cast_rate_vote, is_protected,
    open_rate_proposal, protection_rounds_left, set_own_rate, sync_drink_rates,
)
from app.services.drink_tracker import award_sips
from app.services.room_manager import reset_round_state
from app.services.serializer import serialize_state
from app.services.session_store import game_sessions, set_session


def _room(dealt=False, bots=()):
    names = ["Alice", "Bob", "Carol", "Dave"]
    players = []
    for n in names:
        hands = [make_hand(("5", "S"), ("6", "H"))] if dealt else []
        players.append(make_player(n, hands=hands, is_dealer=(n == "Alice"),
                                   is_npc=(n in bots)))
    players[0].dealer_hand = make_hand(("K", "S"), ("7", "H"))
    raw = RefereeSession(players, "Alice", wager=1, num_hands=1)
    room = GameRoom(session=raw, config=GameConfig(mode="digital", drinking_mode=True))
    room._room_clients = {
        "admin-cid": {"name": "Alice", "role": "admin", "local_names": ["Alice"]},
        "bob-cid":   {"name": "Bob",   "role": "player"},
        "carol-cid": {"name": "Carol", "role": "player"},
        "dave-cid":  {"name": "Dave",  "role": "player"},
    }
    now = time.monotonic()
    for cid in room._room_clients:
        room._client_last_seen[cid] = now
    return room


def _p(room, name):
    return next(p for p in room.all_players if p.name == name)


# ---------------------------------------------------------------------------
# Bots follow the table
# ---------------------------------------------------------------------------

def test_bots_take_the_rate_only_when_all_humans_share_it():
    room = _room(bots=("Dave",))
    for n in ("Alice", "Bob", "Carol"):
        _p(room, n).drink_rate = 0.6
    sync_drink_rates(room)
    assert _p(room, "Dave").effective_drink_rate == 0.6
    _p(room, "Bob").drink_rate = 1.0
    sync_drink_rates(room)
    assert _p(room, "Dave").effective_drink_rate == 1.0


def test_humans_use_their_own_rate():
    room = _room()
    _p(room, "Bob").drink_rate = 0.4
    sync_drink_rates(room)
    assert _p(room, "Bob").effective_drink_rate == 0.4
    assert _p(room, "Carol").effective_drink_rate == 1.0


# ---------------------------------------------------------------------------
# Own changes
# ---------------------------------------------------------------------------

def test_raising_own_rate_needs_no_vote_and_applies_immediately_pre_deal():
    room = _room()
    assert set_own_rate(room, "bob-cid", "Bob", 1.4) == (True, "")
    assert _p(room, "Bob").drink_rate == 1.4
    assert _p(room, "Bob").effective_drink_rate == 1.4


def test_discount_for_yourself_needs_the_table():
    room = _room()
    ok, err = set_own_rate(room, "bob-cid", "Bob", 0.6)
    assert not ok and "approval" in err
    assert _p(room, "Bob").drink_rate == 1.0


def test_cannot_change_someone_elses_seat():
    room = _room()
    ok, err = set_own_rate(room, "bob-cid", "Carol", 1.2)
    assert not ok and "control" in err


def test_local_seat_holder_can_change_the_seat():
    room = _room()
    room._room_clients["admin-cid"]["local_names"] = ["Alice", "Dave"]
    assert set_own_rate(room, "admin-cid", "Dave", 1.2)[0] is True


def test_invalid_rate_is_rejected():
    room = _room()
    assert set_own_rate(room, "bob-cid", "Bob", 0.5)[0] is False
    assert set_own_rate(room, "bob-cid", "Bob", 2.0)[0] is False


def test_bots_cannot_be_given_a_rate():
    room = _room(bots=("Dave",))
    room._room_clients["dave-cid"] = {"name": "Dave", "role": "player"}
    assert set_own_rate(room, "dave-cid", "Dave", 1.2)[0] is False


def test_booster_can_be_dropped_to_beer_and_starts_protection():
    room = _room()
    set_own_rate(room, "bob-cid", "Bob", 1.5)
    assert not is_protected(room, "Bob")
    assert set_own_rate(room, "bob-cid", "Bob", 1.0)[0] is True
    assert _p(room, "Bob").drink_rate == 1.0
    assert is_protected(room, "Bob")
    assert protection_rounds_left(room, "Bob") == DRINK_RATE_PROTECTION_ROUNDS


def test_dropping_to_a_lower_booster_is_free_and_not_protected():
    room = _room()
    set_own_rate(room, "bob-cid", "Bob", 1.5)
    assert set_own_rate(room, "bob-cid", "Bob", 1.2)[0] is True
    assert not is_protected(room, "Bob")


def test_protection_expires_after_three_rounds():
    room = _room()
    set_own_rate(room, "bob-cid", "Bob", 1.5)
    set_own_rate(room, "bob-cid", "Bob", 1.0)
    through = room._drink_rate_protected_through["bob"]
    assert through == room.round_count + DRINK_RATE_PROTECTION_ROUNDS


def test_change_is_queued_mid_round_and_applied_at_next_round():
    room = _room(dealt=True)
    assert set_own_rate(room, "bob-cid", "Bob", 1.4)[0] is True
    assert _p(room, "Bob").drink_rate == 1.0            # not yet
    assert room._drink_rate_queued == {"bob": 1.4}
    reset_round_state(room)
    assert _p(room, "Bob").drink_rate == 1.4
    assert room._drink_rate_queued == {}
    assert any("Bob now drinks" in e for e in room.round._log_entries)


def test_queued_rate_that_returns_to_current_is_dropped():
    room = _room(dealt=True)
    set_own_rate(room, "bob-cid", "Bob", 1.4)
    set_own_rate(room, "bob-cid", "Bob", 1.0)
    assert room._drink_rate_queued == {}


# ---------------------------------------------------------------------------
# Admin proposal + majority vote
# ---------------------------------------------------------------------------

def test_a_player_cannot_propose_for_everyone_or_for_someone_else():
    room = _room()
    ok, err = open_rate_proposal(room, "bob-cid", "all", 0.6)
    assert not ok and "admin" in err.lower()
    ok, err = open_rate_proposal(room, "bob-cid", ["Carol"], 0.6)
    assert not ok and "seat you control" in err


def test_proposal_passes_on_strict_majority_and_beneficiary_votes():
    room = _room()
    assert open_rate_proposal(room, "admin-cid", ["Bob"], 0.6) == (True, "")
    assert room.round._pending_rate_proposal is not None
    # 4 voters: needs 3 Yes. Admin (pre-filled) + Bob (the beneficiary) is only 2.
    assert cast_rate_vote(room, "bob-cid", True)[0] is True
    assert room.round._pending_rate_proposal is not None
    cast_rate_vote(room, "carol-cid", True)
    assert room.round._pending_rate_proposal is None
    assert room._drink_rate_last_result["passed"] is True
    assert _p(room, "Bob").drink_rate == 0.6          # pre-deal: applied now


def test_proposal_fails_when_majority_is_out_of_reach():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", False)
    cast_rate_vote(room, "dave-cid", False)
    assert room._drink_rate_last_result["passed"] is False
    assert _p(room, "Bob").drink_rate == 1.0


def test_proposal_times_out():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    room.round._pending_rate_proposal["expires_at"] = time.monotonic() - 1
    apply_drink_rate_forfeit(room)
    assert room._drink_rate_last_result["reason"] == "timed out"


def test_proposal_for_all_covers_every_human_and_skips_bots():
    room = _room(bots=("Dave",))
    del room._room_clients["dave-cid"]            # bots have no client
    open_rate_proposal(room, "admin-cid", "all", 0.6)
    cast_rate_vote(room, "bob-cid", True)
    assert room._drink_rate_last_result["passed"] is True
    assert sorted(room._drink_rate_last_result["targets"]) == ["Alice", "Bob", "Carol"]
    assert _p(room, "Dave").drink_rate == 1.0
    sync_drink_rates(room)
    assert _p(room, "Dave").effective_drink_rate == 0.6   # everyone human shares it


def test_cannot_propose_a_no_op():
    room = _room()
    ok, err = open_rate_proposal(room, "admin-cid", ["Bob"], 1.0)
    assert not ok and "change" in err


def test_second_proposal_is_blocked_while_one_is_open():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    assert open_rate_proposal(room, "admin-cid", ["Carol"], 0.6)[0] is False


def test_non_voter_cannot_vote():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    room._room_clients["spec"] = {"name": None, "role": "spectator"}
    assert cast_rate_vote(room, "spec", True)[0] is False


def test_sole_voter_passes_immediately():
    room = _room()
    for cid in ("bob-cid", "carol-cid", "dave-cid"):
        room._room_clients[cid]["role"] = "spectator"
    assert open_rate_proposal(room, "admin-cid", ["Alice"], 0.6)[0] is True
    assert room._drink_rate_last_result["passed"] is True


def test_booster_can_be_voted_onto_an_unprotected_player():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 1.4)
    cast_rate_vote(room, "carol-cid", True)
    cast_rate_vote(room, "dave-cid", True)
    assert _p(room, "Bob").drink_rate == 1.4


# ---------------------------------------------------------------------------
# Protection after normalizing
# ---------------------------------------------------------------------------

def _protected_bob(room):
    set_own_rate(room, "bob-cid", "Bob", 1.5)
    set_own_rate(room, "bob-cid", "Bob", 1.0)
    assert is_protected(room, "Bob")


def test_protected_player_needs_their_own_yes():
    room = _room()
    _protected_bob(room)
    open_rate_proposal(room, "admin-cid", ["Bob"], 1.4)
    cast_rate_vote(room, "carol-cid", True)
    cast_rate_vote(room, "dave-cid", True)       # majority reached, but Bob has not said yes
    assert room.round._pending_rate_proposal is not None
    assert _p(room, "Bob").drink_rate == 1.0
    cast_rate_vote(room, "bob-cid", True)
    assert room._drink_rate_last_result["passed"] is True
    assert _p(room, "Bob").drink_rate == 1.4


def test_protected_player_no_vote_is_a_veto():
    room = _room()
    _protected_bob(room)
    open_rate_proposal(room, "admin-cid", ["Bob"], 1.4)
    cast_rate_vote(room, "bob-cid", False)
    assert room._drink_rate_last_result["passed"] is False
    assert room._drink_rate_last_result["reason"] == "a protected player voted no"


def test_protection_also_covers_discounts():
    room = _room()
    _protected_bob(room)
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", True)
    cast_rate_vote(room, "dave-cid", True)
    assert room.round._pending_rate_proposal is not None   # still waiting on Bob


def test_everyone_protected_cannot_be_proposed():
    room = _room()
    for cid, n in (("bob-cid", "Bob"),):
        set_own_rate(room, cid, n, 1.5)
        set_own_rate(room, cid, n, 1.0)
    room._room_clients["bob-cid"]["role"] = "spectator"   # unreachable -> skipped
    ok, err = open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    assert not ok and "protected" in err


def test_protection_ends_after_the_window():
    room = _room()
    _protected_bob(room)
    room._drink_rate_protected_through["bob"] = room.round_count - 1
    assert not is_protected(room, "Bob")
    assert protection_rounds_left(room, "Bob") == 0


# ---------------------------------------------------------------------------
# Applying rates to sips
# ---------------------------------------------------------------------------

def test_award_sips_scales_by_the_receivers_rate_and_records_raw():
    room = _room()
    _p(room, "Bob").effective_drink_rate = 0.6
    award_sips(room, "Bob", 3, "Net hand losses")
    assert room.drinks.sip_ticker["Bob"] == 2
    row = room.drinks.csv_rows[-1]
    assert row["sips"] == 2 and row["sips_raw"] == 3


def test_award_sips_default_rate_has_equal_raw_and_sips():
    room = _room()
    award_sips(room, "Carol", 3, "Net hand losses")
    row = room.drinks.csv_rows[-1]
    assert row["sips"] == 3 and row["sips_raw"] == 3
    assert room.drinks.sip_ticker["Carol"] == 3


def test_award_sips_booster_increases_the_ticker():
    room = _room()
    _p(room, "Bob").effective_drink_rate = 1.5
    award_sips(room, "Bob", 2, "Net hand losses")
    assert room.drinks.sip_ticker["Bob"] == 3


def test_giving_sips_is_not_scaled_for_the_giver():
    """A wine drinker handing out 1 sip to a beer drinker gives exactly 1."""
    room = _room()
    _p(room, "Bob").effective_drink_rate = 0.4
    award_sips(room, "Carol", 1, "Handout")
    assert room.drinks.sip_ticker["Carol"] == 1


def test_last_round_drinks_shows_raw_only_when_it_differs():
    room = _room()
    _p(room, "Bob").effective_drink_rate = 0.6
    award_sips(room, "Bob", 3, "Net hand losses")
    award_sips(room, "Carol", 3, "Net hand losses")
    by_name = {d["name"]: d for d in room.drinks.last_round_drinks}
    assert by_name["Bob"]["raw"] == 3 and by_name["Bob"]["sips"] == 2
    assert "raw" not in by_name["Carol"]


# ---------------------------------------------------------------------------
# Routes + serialization
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return create_app().test_client()


@pytest.fixture
def route_room():
    code = "RateRoom1"
    room = _room()
    set_session(code, room)
    yield code, room
    game_sessions.pop(code, None)


def _post(client, path, code, cid, **extra):
    return client.post(path, json={"room_code": code, "client_id": cid, **extra}).get_json()


def test_set_route_raises_own_rate(client, route_room):
    code, room = route_room
    data = _post(client, "/drink_rate/set", code, "bob-cid", seat="Bob", rate=1.2)
    assert data["ok"] and _p(room, "Bob").drink_rate == 1.2


def test_set_route_rejects_a_discount(client, route_room):
    code, _ = route_room
    data = _post(client, "/drink_rate/set", code, "bob-cid", seat="Bob", rate=0.6)
    assert data["ok"] is False


def test_propose_and_vote_routes(client, route_room):
    code, room = route_room
    assert _post(client, "/drink_rate/propose", code, "admin-cid", seats=["Bob"], rate=0.6)["ok"]
    _post(client, "/drink_rate/vote", code, "bob-cid", vote=True)
    data = _post(client, "/drink_rate/vote", code, "carol-cid", vote=True)
    assert data["ok"]
    assert _p(room, "Bob").drink_rate == 0.6


def test_propose_route_validates_seats(client, route_room):
    code, _ = route_room
    assert _post(client, "/drink_rate/propose", code, "admin-cid", seats="nope", rate=0.6)["ok"] is False


def test_state_exposes_drink_rates(client, route_room):
    code, room = route_room
    set_own_rate(room, "bob-cid", "Bob", 1.4)
    st = serialize_state(room, "bob-cid")["drink_rates"]
    bob = next(s for s in st["seats"] if s["name"] == "Bob")
    assert bob["rate"] == 1.4 and bob["effective_rate"] == 1.4
    assert st["allowed_rates"] == [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.5]
    assert st["presets"]["wine"] == 0.6 and st["presets"]["cocktail"] == 0.4
    open_rate_proposal(room, "admin-cid", ["Carol"], 0.6)
    st = serialize_state(room, "carol-cid")["drink_rates"]
    assert st["pending"]["eligible"] is True and st["pending"]["targets"] == ["Carol"]


def test_tick_syncs_bot_rates():
    from app.services.tick import tick
    room = _room(bots=("Dave",))
    for n in ("Alice", "Bob", "Carol"):
        _p(room, n).drink_rate = 0.4
    tick(room)
    assert _p(room, "Dave").effective_drink_rate == 0.4


# ---------------------------------------------------------------------------
# Late-joiner boost offer (human takes over a bot seat)
# ---------------------------------------------------------------------------

from app.services.drink_rate import (
    dismiss_late_join_offer, offer_late_join_boost, recommend_late_join_rate,
)


def _late_room(rounds=3, ticker=None):
    room = _room(bots=("Dave",))
    del room._room_clients["dave-cid"]
    room.session.round_count = rounds
    room.drinks.sip_ticker = ticker if ticker is not None else {"Alice": 8, "Bob": 6, "Carol": 7}
    return room


@pytest.mark.parametrize("rounds, expected", [(1, 1.2), (2, 1.4), (3, 1.5), (9, 1.5)])
def test_recommended_rate_grows_with_rounds_played(rounds, expected):
    assert recommend_late_join_rate(rounds) == expected


def test_offer_is_made_when_the_table_has_drunk_enough():
    room = _late_room(rounds=2)
    assert offer_late_join_boost(room, "new-cid", "Dave") is True
    offer = room._late_join_offers["new-cid"]
    assert offer["seat"] == "Dave" and offer["avg_others"] == 7.0
    assert offer["rounds"] == 2 and offer["recommended"] == 1.4


def test_no_offer_when_nobody_has_drunk_much():
    room = _late_room(ticker={"Alice": 1, "Bob": 2, "Carol": 0})
    assert offer_late_join_boost(room, "new-cid", "Dave") is False
    assert room._late_join_offers == {}


def test_no_offer_in_normal_mode_or_without_other_humans():
    room = _late_room()
    room.config.drinking_mode = False
    assert offer_late_join_boost(room, "new-cid", "Dave") is False
    room = _late_room()
    for n in ("Alice", "Bob", "Carol"):
        _p(room, n).is_npc = True
    assert offer_late_join_boost(room, "new-cid", "Dave") is False


def test_taking_a_booster_clears_the_offer():
    room = _late_room()
    _p(room, "Dave").is_npc = False
    room._room_clients["new-cid"] = {"name": "Dave", "role": "player"}
    offer_late_join_boost(room, "new-cid", "Dave")
    assert set_own_rate(room, "new-cid", "Dave", 1.4)[0] is True
    assert "new-cid" not in room._late_join_offers
    assert _p(room, "Dave").drink_rate == 1.4


def test_dismissing_clears_the_offer_without_changing_the_rate():
    room = _late_room()
    offer_late_join_boost(room, "new-cid", "Dave")
    dismiss_late_join_offer(room, "new-cid")
    assert room._late_join_offers == {}


def test_offer_is_serialized_only_for_that_client(client):
    code = "RateRoom2"
    room = _late_room()
    room._room_clients["new-cid"] = {"name": "Dave", "role": "player"}
    room._client_last_seen["new-cid"] = time.monotonic()
    set_session(code, room)
    try:
        offer_late_join_boost(room, "new-cid", "Dave")
        mine = serialize_state(room, "new-cid")["drink_rates"]["late_join_offer"]
        assert mine["seat"] == "Dave" and mine["recommended"] in (1.2, 1.4, 1.5)
        assert serialize_state(room, "bob-cid")["drink_rates"]["late_join_offer"] is None
        data = _post(client, "/drink_rate/dismiss_offer", code, "new-cid")
        assert data["ok"] and data["drink_rates"]["late_join_offer"] is None
    finally:
        game_sessions.pop(code, None)


def test_approving_a_bot_seat_takeover_creates_the_offer(client):
    code = "RateRoom3"
    room = _late_room()
    room._room_clients["new-cid"] = {"name": None, "role": "pending", "kicked": False}
    room._pending_registrations = [{"client_id": "new-cid", "name": "Dave"}]
    set_session(code, room)
    try:
        data = _post(client, "/handle_registration", code, "admin-cid",
                     target_client_id="new-cid", approve=True)
        assert data["ok"]
        assert _p(room, "Dave").is_npc is False
        assert room._late_join_offers["new-cid"]["seat"] == "Dave"
    finally:
        game_sessions.pop(code, None)


# ---------------------------------------------------------------------------
# Bots never vote or count toward the majority
# ---------------------------------------------------------------------------

def test_client_holding_only_a_bot_seat_is_not_a_voter():
    from app.services.drink_rate import _voter_cids
    room = _room(bots=("Dave",))
    assert "dave-cid" not in _voter_cids(room)
    assert sorted(_voter_cids(room)) == ["admin-cid", "bob-cid", "carol-cid"]


def test_bot_seat_does_not_inflate_the_majority_needed():
    room = _room(bots=("Dave",))
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    assert len(room.round._pending_rate_proposal["votes"]) == 3      # not 4
    cast_rate_vote(room, "carol-cid", True)                          # admin + carol = 2 of 3
    assert room._drink_rate_last_result["passed"] is True


def test_admin_with_only_local_players_decides_alone():
    """Only the admin is connected and controls every seat: the vote is just them."""
    room = _room()
    room._room_clients = {"admin-cid": {"name": "Alice", "role": "admin",
                                        "local_names": ["Alice", "Bob", "Carol", "Dave"]}}
    assert open_rate_proposal(room, "admin-cid", ["Bob"], 0.4) == (True, "")
    assert room._drink_rate_last_result["passed"] is True
    assert _p(room, "Bob").drink_rate == 0.4


def test_afk_vote_pool_also_excludes_bot_only_clients():
    from app.services.afk import eligible_voter_cids
    room = _room(bots=("Dave",))
    assert "dave-cid" not in eligible_voter_cids(room)


# ---------------------------------------------------------------------------
# A player's request for a lower rate opens the same vote an admin proposal would
# ---------------------------------------------------------------------------

from app.config import DRINK_RATE_REQUEST_FREEZE_ROUNDS


def test_player_request_opens_a_vote_with_the_player_as_proposer():
    room = _room()
    assert open_rate_proposal(room, "bob-cid", ["Bob"], 0.6) == (True, "")
    pending = room.round._pending_rate_proposal
    assert pending["proposer"] == "Bob" and pending["targets"] == ["Bob"]
    assert pending["votes"]["bob-cid"] is True                    # their own vote is pre-filled Yes
    assert len(pending["votes"]) == 4                             # everyone votes, admin included
    assert _p(room, "Bob").drink_rate == 1.0                      # nothing changes until it passes


def test_player_request_passes_on_a_majority_like_any_proposal():
    room = _room()
    open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", True)
    assert room.round._pending_rate_proposal is not None          # 2 of 4 is not a majority
    cast_rate_vote(room, "admin-cid", True)
    assert room._drink_rate_last_result["passed"] is True
    assert _p(room, "Bob").drink_rate == 0.6


def test_player_request_must_be_a_lower_rate():
    room = _room()
    assert open_rate_proposal(room, "bob-cid", ["Bob"], 1.2)[0] is False    # higher: just set it
    assert open_rate_proposal(room, "bob-cid", ["Bob"], 1.0)[0] is False    # no change


def test_request_below_beer_is_the_only_kind_a_player_can_open():
    room = _room()
    set_own_rate(room, "bob-cid", "Bob", 1.4)
    ok, err = open_rate_proposal(room, "bob-cid", ["Bob"], 1.2)
    assert not ok and "lower rate" in err


def test_spectators_cannot_open_a_vote():
    room = _room()
    room._room_clients["spec"] = {"name": None, "role": "spectator"}
    assert open_rate_proposal(room, "spec", ["Bob"], 0.6)[0] is False


def test_a_voted_down_request_freezes_that_seat_for_three_rounds():
    room = _room()
    open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", False)
    cast_rate_vote(room, "dave-cid", False)
    assert room._drink_rate_last_result["passed"] is False
    ok, err = open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)
    assert not ok and "voted down" in err
    room._drink_rate_request_frozen_through["bob"] = room.round_count - 1   # window over
    assert open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)[0] is True


def test_a_timed_out_request_also_freezes_the_seat():
    room = _room()
    open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)
    room.round._pending_rate_proposal["expires_at"] = time.monotonic() - 1
    apply_drink_rate_forfeit(room)
    assert room._drink_rate_request_frozen_through["bob"] == room.round_count + DRINK_RATE_REQUEST_FREEZE_ROUNDS


def test_a_failed_admin_proposal_does_not_freeze_anyone():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", False)
    cast_rate_vote(room, "dave-cid", False)
    assert room._drink_rate_request_frozen_through == {}
    assert open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)[0] is True


def test_player_request_route(client, route_room):
    code, room = route_room
    data = _post(client, "/drink_rate/propose", code, "bob-cid", seats=["Bob"], rate=0.6)
    assert data["ok"] and data["drink_rates"]["pending"]["proposer"] == "Bob"
    assert _post(client, "/drink_rate/propose", code, "bob-cid", seats=["Carol"], rate=0.6)["ok"] is False


# ---------------------------------------------------------------------------
# The vote counts the votes cast, not every human at the table
# ---------------------------------------------------------------------------

def _expire(room):
    room.round._pending_rate_proposal["expires_at"] = time.monotonic() - 1
    apply_drink_rate_forfeit(room)


def test_silent_players_do_not_block_a_vote_at_the_deadline():
    room = _room()                                   # 4 voters: admin, bob, carol, dave
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "bob-cid", True)            # 2 yes, 0 no, 2 silent -> not decided yet
    assert room.round._pending_rate_proposal is not None
    _expire(room)
    assert room._drink_rate_last_result["passed"] is True
    assert room._drink_rate_last_result["reason"] == "majority of the votes cast"
    assert _p(room, "Bob").drink_rate == 0.6


def test_a_lone_proposer_vote_does_not_carry_it():
    room = _room()
    open_rate_proposal(room, "bob-cid", ["Bob"], 0.6)
    _expire(room)                                    # nobody else voted
    assert room._drink_rate_last_result["passed"] is False
    assert _p(room, "Bob").drink_rate == 1.0


def test_a_tie_among_the_votes_cast_fails():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "carol-cid", False)         # 1 yes, 1 no, 2 silent
    assert room.round._pending_rate_proposal is not None
    _expire(room)
    assert room._drink_rate_last_result["passed"] is False


def test_yes_beating_no_among_those_who_voted_passes_even_with_silent_players():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "bob-cid", True)
    cast_rate_vote(room, "carol-cid", False)         # 2 yes, 1 no, dave silent: not decided early
    assert room.round._pending_rate_proposal is not None
    _expire(room)
    assert room._drink_rate_last_result["passed"] is True


def test_it_ends_early_once_silent_players_could_not_change_the_result():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "bob-cid", True)
    cast_rate_vote(room, "carol-cid", True)          # 3 yes vs at most 1 more no
    assert room._drink_rate_last_result["passed"] is True
    assert room.round._pending_rate_proposal is None


def test_it_fails_early_when_yes_can_no_longer_win():
    room = _room()
    open_rate_proposal(room, "admin-cid", ["Bob"], 0.6)
    cast_rate_vote(room, "bob-cid", False)
    cast_rate_vote(room, "carol-cid", False)         # 1 yes + 1 remaining <= 2 no
    assert room._drink_rate_last_result["passed"] is False


def test_a_protected_player_still_must_vote_yes_at_the_deadline():
    room = _room()
    _protected_bob(room)
    open_rate_proposal(room, "admin-cid", ["Bob"], 1.4)
    cast_rate_vote(room, "carol-cid", True)
    cast_rate_vote(room, "dave-cid", True)           # majority of votes cast, but Bob is silent
    _expire(room)
    assert room._drink_rate_last_result["passed"] is False
    assert _p(room, "Bob").drink_rate == 1.0


def test_rows_record_the_factor_applied_and_exempt_rows_skip_boosters():
    room = _room()
    _p(room, "Bob").effective_drink_rate = 0.6
    award_sips(room, "Bob", 3, "Net hand losses")
    award_sips(room, "Bob", 3, "Bust vote handout", scale=False)
    assert room.drinks.csv_rows[-2]["rate"] == 0.6
    last = room.drinks.csv_rows[-1]
    assert last["rate"] == 0.6 and last["sips"] == 2 and last["sips_raw"] == 3
    _p(room, "Bob").effective_drink_rate = 1.5
    award_sips(room, "Bob", 3, "Bust vote handout", scale=False)
    last = room.drinks.csv_rows[-1]
    assert last["rate"] == 1.0 and last["sips"] == last["sips_raw"] == 3


def test_harvest_counts_rounds_at_each_factor():
    from app.services.drink_tracker import _record_rate_rounds
    room = _room()
    _p(room, "Bob").effective_drink_rate = 0.6
    _record_rate_rounds(room)
    _p(room, "Bob").effective_drink_rate = 1.0
    _record_rate_rounds(room)
    _record_rate_rounds(room)
    assert room.stats.rate_rounds["Bob"] == {0.6: 1, 1.0: 2}
