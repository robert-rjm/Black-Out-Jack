"""
Tests for app/services/serializer.py's compute_kpi_stats().
"""

from engine.referee import RefereeSession
from tests.conftest import make_player
from app.models.game_room import GameRoom, GameConfig
from app.services.serializer import compute_kpi_stats


def _make_room(num_players=3):
    names = ["Alice", "Bob", "Carol"][:num_players]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    raw_session = RefereeSession(players, "Alice", wager=1, num_hands=1)
    return GameRoom(session=raw_session, config=GameConfig(mode="digital", drinking_mode=True))


def test_avg_sips_uses_player_rounds_played_not_session_round_count():
    """Regression: a player who joins mid-session must have avg_sips
    divided by the rounds *they* actually played, not by session.round_count
    (which includes rounds before they were seated). Before this fix,
    avg_sips used n_rounds (session.round_count) uniformly for every
    player, silently deflating a late joiner's average -- inconsistent
    with the milestone system's own round_avg(), which already used
    player_rounds_played correctly (see drink_tracker.py's
    _apply_worst_player_streak)."""
    room = _make_room(num_players=2)          # Alice, Bob
    room.session.round_count = 10             # session has run 10 rounds total
    room.stats.player_rounds_played = {"Alice": 10, "Bob": 4}   # Bob joined late

    sip_ticker = {"Alice": 20, "Bob": 8}
    stats = compute_kpi_stats(room, sip_ticker=sip_ticker, order=["Alice", "Bob"])

    rows = {r["name"]: r for r in stats["players"]}
    assert rows["Alice"]["avg_sips"] == 2.0   # 20 / 10 rounds played
    assert rows["Bob"]["avg_sips"]   == 2.0   # 8 / 4 rounds played -- NOT 8 / 10 = 0.8


def test_avg_sips_none_for_player_with_zero_rounds_played():
    room = _make_room(num_players=2)
    room.session.round_count = 5
    room.stats.player_rounds_played = {"Alice": 5, "Bob": 0}   # Bob just registered

    sip_ticker = {"Alice": 10, "Bob": 0}
    stats = compute_kpi_stats(room, sip_ticker=sip_ticker, order=["Alice", "Bob"])

    rows = {r["name"]: r for r in stats["players"]}
    assert rows["Bob"]["avg_sips"] is None
