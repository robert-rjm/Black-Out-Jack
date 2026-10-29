"""
Direct unit tests for the private harvest_drink_log helpers in
app/services/drink_tracker.py (extracted in M1).

Tests call each helper directly with a minimal GameRoom so every helper is
testable in isolation without running a full round.
"""

import pytest

from app.services.drink_tracker import (
    _record_csv_rows,
    _update_sip_tickers,
    _snapshot_round,
    _record_drinks_detail,
    _update_hand_stats,
    _update_max_round_sips,
    _update_dealer_stats,
    _update_streaks,
    _update_l_badges,
    apply_l_handout_forfeit,
    give_l_handout,
    harvest_drink_log,
    l_handout_sips,
)
from app.config import WORST_STREAK_THRESHOLD
from engine.referee import RefereeSession
from app.models.game_room import GameRoom, GameConfig
from tests.conftest import make_hand, make_player


# ---------------------------------------------------------------------------
# Test fixture
# ---------------------------------------------------------------------------

def _make_room(names=None, dealer_idx=0):
    """Minimal GameRoom for harvest-helper tests."""
    if names is None:
        names = ["Alice", "Bob"]
    players = [make_player(n) for n in names]
    players[dealer_idx].is_dealer = True
    players[dealer_idx].dealer_hand = make_hand()   # empty, non-bust
    raw = RefereeSession(players, players[dealer_idx].name, wager=1, num_hands=2)
    return GameRoom(session=raw, config=GameConfig(mode="referee"))


# ---------------------------------------------------------------------------
# _record_csv_rows
# ---------------------------------------------------------------------------

def test_record_csv_rows_positive_sip_recorded():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "net loss", "player")           # classify_rule → "Net hand losses"
    _record_csv_rows(room)
    assert any(r["player"] == "Alice" and r["sips"] == 2 for r in room.drinks.csv_rows)


def test_record_csv_rows_zero_sips_skipped():
    room = _make_room()
    room.all_players[0].add_drink(0, "net loss", "player")
    _record_csv_rows(room)
    assert room.drinks.csv_rows == []


def test_record_csv_rows_null_classified_reason_skipped():
    """Reasons that classify_rule maps to None (e.g. 'exempt') are not recorded."""
    room = _make_room()
    # "exempt" → classify_rule returns None → skip
    room.all_players[0].add_drink(1, "exempt from drinks", "player")
    _record_csv_rows(room)
    assert room.drinks.csv_rows == []


def test_record_csv_rows_negative_sips_always_recorded():
    """Negative (credit) sips are always recorded with their canonical rule name."""
    room = _make_room()
    # "bust vote correct" → classify_rule now returns "Bust vote credit"
    room.all_players[0].add_drink(-1, "bust vote correct: -1 sip credit", "player")
    _record_csv_rows(room)
    assert any(r["player"] == "Alice" and r["sips"] == -1 and r["rule"] == "Bust vote credit"
               for r in room.drinks.csv_rows)


def test_record_csv_rows_includes_round_and_dealer():
    room = _make_room()
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_csv_rows(room)
    row = room.drinks.csv_rows[-1]
    assert "round" in row and "dealer" in row


def test_record_csv_rows_records_correct_dealer():
    room = _make_room()
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_csv_rows(room)
    assert room.drinks.csv_rows[-1]["dealer"] == "Alice"   # Alice is dealer (idx 0)


# ---------------------------------------------------------------------------
# _update_sip_tickers
# ---------------------------------------------------------------------------

def test_update_sip_tickers_net_positive():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(3, "net loss", "player")
    alice.add_drink(-1, "bust vote correct: -1 sip credit", "player")  # net = 2
    _update_sip_tickers(room)
    assert room.drinks.sip_ticker.get("Alice") == 2


def test_update_sip_tickers_zero_net_not_stored():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(1, "net loss", "player")
    alice.add_drink(-1, "bust vote correct: -1 sip credit", "player")  # net = 0
    _update_sip_tickers(room)
    assert room.drinks.sip_ticker.get("Alice", 0) == 0


def test_update_sip_tickers_dealer_role_tracked_separately():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "Hard Dealer Switch", "dealer")
    _update_sip_tickers(room)
    assert room.drinks.dealer_role_ticker.get("Alice") == 2


def test_update_sip_tickers_accumulates_across_calls():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "net loss", "player")
    _update_sip_tickers(room)
    alice.drink_log.clear()
    alice.add_drink(3, "net loss", "player")
    _update_sip_tickers(room)
    assert room.drinks.sip_ticker.get("Alice") == 5


def test_update_sip_tickers_multiple_players_independent():
    room = _make_room()
    alice, bob = room.all_players[0], room.all_players[1]
    alice.add_drink(3, "net loss", "player")
    bob.add_drink(1, "net loss", "player")
    _update_sip_tickers(room)
    assert room.drinks.sip_ticker.get("Alice") == 3
    assert room.drinks.sip_ticker.get("Bob") == 1


# ---------------------------------------------------------------------------
# _snapshot_round
# ---------------------------------------------------------------------------

def test_snapshot_round_shifts_prev_sips():
    room = _make_room()
    room.drinks.last_round_sips = {"Alice": 2}
    room.all_players[0].add_drink(5, "net loss", "player")
    _snapshot_round(room)
    assert room.drinks.prev_round_sips == {"Alice": 2}
    assert room.drinks.last_round_sips.get("Alice") == 5


def test_snapshot_round_zero_sip_player_still_recorded():
    """Players with no drinks must appear in _last_round_sips (crown-badge logic)."""
    room = _make_room()
    _snapshot_round(room)
    assert "Alice" in room.drinks.last_round_sips
    assert room.drinks.last_round_sips["Alice"] == 0


def test_snapshot_round_increments_rounds_played():
    room = _make_room()
    _snapshot_round(room)
    assert room.stats.player_rounds_played.get("Alice") == 1


def test_snapshot_round_appends_to_sip_history():
    room = _make_room()
    room.all_players[0].add_drink(3, "net loss", "player")
    _snapshot_round(room)
    assert len(room.stats.round_sip_history) == 1
    assert room.stats.round_sip_history[0] == 3


def test_snapshot_round_history_clamps_negative():
    room = _make_room()
    room.all_players[0].add_drink(-5, "bust vote correct: -1 sip credit", "player")
    _snapshot_round(room)
    assert room.stats.round_sip_history[0] == 0   # max(0, -5) = 0


# ---------------------------------------------------------------------------
# _update_max_round_sips
# ---------------------------------------------------------------------------

def test_update_max_sips_records_first_round():
    room = _make_room()
    room.drinks.last_round_sips = {"Alice": 5}
    _update_max_round_sips(room)
    assert room.stats.max_round_sips["Alice"] == 5


def test_update_max_sips_keeps_previous_higher():
    room = _make_room()
    room.stats.max_round_sips    = {"Alice": 10}
    room.drinks.last_round_sips   = {"Alice": 3}
    _update_max_round_sips(room)
    assert room.stats.max_round_sips["Alice"] == 10


def test_update_max_sips_replaces_previous_lower():
    room = _make_room()
    room.stats.max_round_sips    = {"Alice": 2}
    room.drinks.last_round_sips   = {"Alice": 7}
    _update_max_round_sips(room)
    assert room.stats.max_round_sips["Alice"] == 7


def test_update_max_sips_clamps_negative():
    room = _make_room()
    room.drinks.last_round_sips = {"Alice": -2}
    _update_max_round_sips(room)
    assert room.stats.max_round_sips.get("Alice", 0) == 0


# ---------------------------------------------------------------------------
# _update_streaks
# ---------------------------------------------------------------------------

def test_streaks_win_round_increments():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_streaks(room)
    assert room.stats.streaks["Alice"]["current"] == 1


def test_streaks_loss_round_decrements():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_streaks(room)
    assert room.stats.streaks["Alice"]["current"] == -1


def test_streaks_neutral_resets_to_zero():
    room = _make_room()
    alice = room.all_players[0]
    alice.hands = [
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("5", "S"), ("6", "H"), result="loss"),
    ]
    room.stats.streaks["Alice"] = {"current": 3, "longest_win": 3, "longest_loss": 0}
    _update_streaks(room)
    assert room.stats.streaks["Alice"]["current"] == 0


def test_streaks_tracks_longest_win():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    room.stats.streaks["Alice"] = {"current": 2, "longest_win": 2, "longest_loss": 0}
    _update_streaks(room)
    assert room.stats.streaks["Alice"]["longest_win"] == 3


def test_streaks_tracks_longest_loss():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    room.stats.streaks["Alice"] = {"current": -2, "longest_win": 0, "longest_loss": 2}
    _update_streaks(room)
    assert room.stats.streaks["Alice"]["longest_loss"] == 3


def test_streaks_unresolved_hands_player_skipped():
    """Player with only unresolved hands (result=None) is not added to _streaks."""
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result=None)]
    _update_streaks(room)
    assert "Alice" not in room.stats.streaks


# ---------------------------------------------------------------------------
# "L" badge and comeback handout (_update_l_badges, give_l_handout)
# ---------------------------------------------------------------------------

def _streaks(room, **current):
    room.stats.streaks = {n: {"current": c, "longest_win": 0, "longest_loss": max(0, -c)}
                          for n, c in current.items()}


def test_every_player_on_a_long_losing_streak_wears_the_l():
    room = _make_room(names=["Alice", "Bob", "Carol"])
    _streaks(room, Alice=-5, Bob=-9, Carol=-(WORST_STREAK_THRESHOLD - 1))
    _update_l_badges(room, {"Alice": -4, "Bob": -8, "Carol": -3})
    assert room.stats.l_badge_holders == ["Alice", "Bob"]   # several at once, seat order
    assert room.round._l_handout_pending == {}             # nobody broke a streak
    assert room.drinks.sip_ticker == {}                     # and nobody drinks for it


def test_handout_size_steps_up_every_two_rounds():
    assert [l_handout_sips(n) for n in (5, 6, 7, 8, 9, 10, 11)] == [1, 1, 2, 2, 3, 3, 4]
    assert l_handout_sips(7, wager=3) == 6   # sips are wagers


@pytest.mark.parametrize("before, sips", [(-5, 1), (-6, 1), (-7, 2), (-9, 3)])
def test_breaking_a_streak_earns_a_handout(before, sips):
    room = _make_room()
    _streaks(room, Alice=1, Bob=0)
    _update_l_badges(room, {"Alice": before, "Bob": 0})
    assert room.round._l_handout_pending == {"Alice": sips}
    assert room.stats.l_badge_holders == []
    assert room.round._l_handout_expires_at is not None


def test_handout_is_counted_in_wagers():
    room = _make_room()
    room.session.wager = 2
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -7})
    assert room.round._l_handout_pending == {"Alice": 4}


def test_a_push_or_even_round_breaks_the_streak_too():
    room = _make_room()
    _streaks(room, Alice=0)      # _update_streaks resets an even round to 0
    _update_l_badges(room, {"Alice": -6})
    assert room.round._l_handout_pending == {"Alice": 1}


def test_a_streak_of_four_earns_nothing():
    room = _make_room()
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -(WORST_STREAK_THRESHOLD - 1)})
    assert room.round._l_handout_pending == {}


def test_a_player_with_no_resolved_hands_keeps_the_streak_and_earns_nothing():
    room = _make_room()
    _streaks(room, Alice=-6)     # untouched by _update_streaks this round
    _update_l_badges(room, {"Alice": -6})
    assert room.stats.l_badge_holders == ["Alice"]
    assert room.round._l_handout_pending == {}


def test_harvest_reads_the_streak_from_before_the_round():
    room = _make_room(names=["Alice", "Bob"], dealer_idx=0)
    _streaks(room, Bob=-7)
    room._get_player("Bob").hands = [make_hand(("10", "H"), ("9", "D"), result="win"),
                                     make_hand(("10", "S"), ("8", "D"), result="push")]
    harvest_drink_log(room)
    assert room.stats.streaks["Bob"]["current"] == 1
    assert room.round._l_handout_pending == {"Bob": 2}


def test_giving_credits_the_recipients_sips_for_real():
    room = _make_room(names=["Alice", "Bob"])
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -7})
    assert give_l_handout(room, "Alice", "Bob") is True
    assert room.drinks.sip_ticker["Bob"] == 2
    assert room.drinks.last_round_sips["Bob"] == 2
    assert room.drinks.csv_rows[-1]["rule"] == "Comeback handout"
    assert len(room._get_player("Bob").drink_log) == 1
    assert any("Bob drinks 2 sips" in e for e in room.round._log_entries)
    assert room.round._l_handout_expires_at is None       # nothing left to wait for
    assert give_l_handout(room, "Alice", "Bob") is False  # only once


def test_cannot_give_to_yourself_or_a_stranger():
    room = _make_room()
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -5})
    assert give_l_handout(room, "Alice", "Alice") is False
    assert give_l_handout(room, "Alice", "Nobody") is False
    assert room.drinks.sip_ticker == {}


def test_keeping_the_handout_means_drinking_it():
    room = _make_room()
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -5})
    assert give_l_handout(room, "Alice", None) is True
    assert room.drinks.sip_ticker["Alice"] == 1


def test_an_unassigned_handout_is_drunk_by_the_giver_when_time_runs_out():
    room = _make_room()
    _streaks(room, Alice=1)
    _update_l_badges(room, {"Alice": -9})
    apply_l_handout_forfeit(room)                 # window still open: nothing
    assert room.drinks.sip_ticker == {}
    room.round._l_handout_expires_at = 0
    apply_l_handout_forfeit(room)
    assert room.drinks.sip_ticker["Alice"] == 3
    assert "Alice" in room.round._l_handout_given


def test_bots_give_their_handout_straight_away():
    from engine.blackjack import NPC_Player
    room = _make_room(names=["Alice", "Bob"])
    bot = NPC_Player("Robo")
    room.all_players.append(bot)
    _streaks(room, Robo=1)
    _update_l_badges(room, {"Robo": -5})
    assert "Robo" in room.round._l_handout_given
    assert sum(room.drinks.sip_ticker.values()) == 1
    assert "Robo" not in room.drinks.sip_ticker

# ---------------------------------------------------------------------------
# _update_hand_stats
# ---------------------------------------------------------------------------

def test_hand_stats_win_and_blackjack_counted():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_hand_stats(room)
    hs = room.stats.hand_stats["Alice"]
    assert hs["hands"] == 1
    assert hs["wins"] == 1
    assert hs["blackjacks"] == 1


def test_hand_stats_loss_counted():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_hand_stats(room)
    assert room.stats.hand_stats["Alice"]["losses"] == 1


def test_hand_stats_bust_counted():
    room = _make_room()
    room.all_players[0].hands = [
        make_hand(("K", "S"), ("Q", "H"), ("5", "D"), result="loss", bust=True)
    ]
    _update_hand_stats(room)
    assert room.stats.hand_stats["Alice"]["busts"] == 1


def test_hand_stats_unresolved_hand_skipped():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result=None)]
    _update_hand_stats(room)
    assert room.stats.hand_stats.get("Alice", {}).get("hands", 0) == 0


def test_hand_stats_split_hand_tracked():
    room = _make_room()
    room.all_players[0].hands = [
        make_hand(("7", "H"), ("8", "D"), result="win", from_split=True)
    ]
    _update_hand_stats(room)
    hs = room.stats.hand_stats["Alice"]
    assert hs["split_hands"] == 1
    assert hs["split_wins"] == 1


def test_hand_stats_accumulates_across_rounds():
    room = _make_room()
    alice = room.all_players[0]
    alice.hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_hand_stats(room)
    alice.hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_hand_stats(room)
    hs = room.stats.hand_stats["Alice"]
    assert hs["hands"] == 2
    assert hs["wins"] == 1
    assert hs["losses"] == 1


# ---------------------------------------------------------------------------
# _update_dealer_stats
# ---------------------------------------------------------------------------

def test_dealer_stats_player_win_is_dealer_loss():
    """A player win increments the dealer's loss counter."""
    room = _make_room(["Alice", "Bob"])
    room.all_players[1].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_dealer_stats(room)
    ds = room.stats.dealer_hand_stats["Alice"]
    assert ds["losses"] == 1


def test_dealer_stats_player_loss_is_dealer_win():
    room = _make_room(["Alice", "Bob"])
    room.all_players[1].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_dealer_stats(room)
    assert room.stats.dealer_hand_stats["Alice"]["wins"] == 1


def test_dealer_stats_bust_hand_counted():
    room = _make_room(["Alice", "Bob"])
    # Give the dealer player a bust hand
    room.all_players[0].dealer_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))
    _update_dealer_stats(room)
    assert room.stats.dealer_bust_rounds == 1


def test_dealer_stats_dealer_own_hands_excluded():
    """The dealer player's non-dealer hands are not counted in dealer stats."""
    room = _make_room(["Alice", "Bob"])
    # Give the dealer (Alice) a player hand — shouldn't be counted
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_dealer_stats(room)
    assert room.stats.dealer_hand_stats.get("Alice", {}).get("wins", 0) == 0


# ---------------------------------------------------------------------------
# _record_drinks_detail
# ---------------------------------------------------------------------------

def test_record_drinks_detail_positive_sip_in_last_round_drinks():
    room = _make_room()
    room.all_players[0].add_drink(2, "net loss", "player")
    _record_drinks_detail(room)
    assert any(d["name"] == "Alice" and d["sips"] == 2 for d in room.drinks.last_round_drinks)


def test_record_drinks_detail_credit_in_last_round_drinks():
    room = _make_room()
    room.all_players[0].add_drink(-1, "bust vote correct: -1 sip credit", "player")
    _record_drinks_detail(room)
    assert any(d["name"] == "Alice" and d["sips"] == -1 for d in room.drinks.last_round_drinks)


def test_record_drinks_detail_replaces_previous_detail():
    """Each call to _record_drinks_detail overwrites _last_round_drinks."""
    room = _make_room()
    room.drinks.last_round_drinks = [{"name": "Bob", "sips": 9, "reason": "stale"}]
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_drinks_detail(room)
    # stale entry replaced; only Alice's drink remains
    names = [d["name"] for d in room.drinks.last_round_drinks]
    assert "Bob" not in names or all(d["sips"] != 9 for d in room.drinks.last_round_drinks)
