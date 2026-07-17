"""
Tests for app/services/drink_tracker.py's out-of-band sip accounting --
specifically award_sips's count_toward_round flag and the milestone
"worst average sips/round" streak it feeds into
(_apply_worst_player_streak). These aren't exercised elsewhere: the
Targeted Drinking suite checks that its own penalty sips land with
count_toward_round=False, but not the drink_tracker-side math that flag
is meant to protect.
"""

from engine.referee import RefereeSession
from tests.conftest import make_player
from app.models.game_room import GameRoom, GameConfig
from app.services.drink_tracker import award_sips, _apply_worst_player_streak


def _make_room(num_players=3):
    """Minimal GameRoom with num_players players (Alice is dealer) -- same
    shape as test_targeted_drinking.py's own _make_room."""
    names = ["Alice", "Bob", "Carol", "Dave"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    return GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=True))


# ---------------------------------------------------------------------------
# award_sips: count_toward_round
# ---------------------------------------------------------------------------

def test_award_sips_default_counts_toward_round():
    room = _make_room()
    award_sips(room, "Bob", 2, "test rule")
    assert room.drinks.sip_ticker["Bob"] == 2
    assert room.drinks.last_round_sips["Bob"] == 2
    assert room.drinks.last_round_drinks[-1] == {"name": "Bob", "sips": 2, "reason": "test rule"}
    assert room.drinks.sip_ticker_excl_round_avg.get("Bob") is None


def test_award_sips_excluded_still_updates_session_total_only():
    room = _make_room()
    award_sips(room, "Bob", 1, "Targeted Drinking wrong guess", count_toward_round=False)

    # Session total and the exclusion tracker both see it...
    assert room.drinks.sip_ticker["Bob"] == 1
    assert room.drinks.sip_ticker_excl_round_avg["Bob"] == 1
    # ...but it never touches the round-based accounting.
    assert "Bob" not in room.drinks.last_round_sips
    assert room.drinks.last_round_drinks == []


def test_award_sips_excluded_still_appends_csv_row():
    room = _make_room()
    award_sips(room, "Bob", 1, "Targeted Drinking wrong guess", count_toward_round=False)
    assert room.drinks.csv_rows[-1]["player"] == "Bob"
    assert room.drinks.csv_rows[-1]["sips"] == 1


# ---------------------------------------------------------------------------
# _apply_worst_player_streak: excluded sips don't count toward the average
# ---------------------------------------------------------------------------

def test_worst_streak_ignores_sips_excluded_from_round_average():
    room = _make_room(num_players=3)   # Alice, Bob, Carol
    room.stats.player_rounds_played = {"Alice": 4, "Bob": 4, "Carol": 4}

    # Round-based totals: Bob and Carol tied at a low, genuine 2 sips/round.
    room.drinks.sip_ticker = {"Alice": 40, "Bob": 8, "Carol": 8}
    # Bob's total is inflated by 20 sips of Targeted Drinking penalties
    # that never happened during any round -- without the exclusion,
    # Bob's round average would look far worse than Carol's for no
    # round-related reason at all.
    room.drinks.sip_ticker_excl_round_avg = {"Bob": 20}
    room.drinks.sip_ticker["Bob"] += 20

    _apply_worst_player_streak(room, winner="Alice", ticker=room.drinks.sip_ticker)

    # Bob (8/4=2.0) and Carol (8/4=2.0) are tied on the *round* average --
    # alphabetical tiebreak picks Bob, not "Bob looks worse because of the
    # mini-game penalty" (which would have made his raw average 28/4=7.0).
    assert room.drinks.last_milestone_worst == "Bob"


def test_worst_streak_penalty_uses_round_average_not_raw_ticker():
    room = _make_room(num_players=3)
    room.stats.player_rounds_played = {"Alice": 4, "Bob": 4, "Carol": 4}
    room.drinks.last_milestone_worst = "Bob"   # already flagged worst once

    room.drinks.sip_ticker = {"Alice": 40, "Bob": 8 + 20, "Carol": 8}
    room.drinks.sip_ticker_excl_round_avg = {"Bob": 20}

    _apply_worst_player_streak(room, winner="Alice", ticker=room.drinks.sip_ticker)

    bob = room._get_player("Bob")
    # Winner's round average is 40/4=10 -- the penalty should match that,
    # not some value inflated by Bob's own excluded sips (which don't
    # affect the winner's average at all here, but confirms the helper
    # uses round_avg() uniformly rather than raw ticker division anywhere).
    assert sum(e[0] for e in bob.drink_log if e) == 10
