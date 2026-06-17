"""
Direct unit tests for the private harvest_drink_log helpers in
app/services/drink_tracker.py (extracted in M1).

Tests call each helper directly with a minimal GameRoom so every helper is
testable in isolation without running a full round.
"""

from app.services.drink_tracker import (
    _record_csv_rows,
    _update_sip_tickers,
    _snapshot_round,
    _record_drinks_detail,
    _update_hand_stats,
    _update_max_round_sips,
    _update_dealer_stats,
    _update_streaks,
)
from engine.referee import RefereeSession
from app.models.game_room import GameRoom
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
    return GameRoom(session=raw, mode="referee")


# ---------------------------------------------------------------------------
# _record_csv_rows
# ---------------------------------------------------------------------------

def test_record_csv_rows_positive_sip_recorded():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "net loss", "player")           # classify_rule → "Net hand losses"
    _record_csv_rows(room)
    assert any(r["player"] == "Alice" and r["sips"] == 2 for r in room._drink_csv_rows)


def test_record_csv_rows_zero_sips_skipped():
    room = _make_room()
    room.all_players[0].add_drink(0, "net loss", "player")
    _record_csv_rows(room)
    assert room._drink_csv_rows == []


def test_record_csv_rows_null_classified_reason_skipped():
    """Reasons that classify_rule maps to None (e.g. 'exempt') are not recorded."""
    room = _make_room()
    # "exempt" → classify_rule returns None → skip
    room.all_players[0].add_drink(1, "exempt from drinks", "player")
    _record_csv_rows(room)
    assert room._drink_csv_rows == []


def test_record_csv_rows_negative_sips_always_recorded():
    """Negative (credit) sips are always recorded; fallback rule is 'Sip credit'."""
    room = _make_room()
    # "bust vote correct" → classify_rule returns None → fallback to "Sip credit"
    room.all_players[0].add_drink(-1, "bust vote correct: -1 sip credit", "player")
    _record_csv_rows(room)
    assert any(r["player"] == "Alice" and r["sips"] == -1 and r["rule"] == "Sip credit"
               for r in room._drink_csv_rows)


def test_record_csv_rows_includes_round_and_dealer():
    room = _make_room()
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_csv_rows(room)
    row = room._drink_csv_rows[-1]
    assert "round" in row and "dealer" in row


def test_record_csv_rows_records_correct_dealer():
    room = _make_room()
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_csv_rows(room)
    assert room._drink_csv_rows[-1]["dealer"] == "Alice"   # Alice is dealer (idx 0)


# ---------------------------------------------------------------------------
# _update_sip_tickers
# ---------------------------------------------------------------------------

def test_update_sip_tickers_net_positive():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(3, "net loss", "player")
    alice.add_drink(-1, "bust vote correct: -1 sip credit", "player")  # net = 2
    _update_sip_tickers(room)
    assert room._sip_ticker.get("Alice") == 2


def test_update_sip_tickers_zero_net_not_stored():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(1, "net loss", "player")
    alice.add_drink(-1, "bust vote correct: -1 sip credit", "player")  # net = 0
    _update_sip_tickers(room)
    assert room._sip_ticker.get("Alice", 0) == 0


def test_update_sip_tickers_dealer_role_tracked_separately():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "Hard Dealer Switch", "dealer")
    _update_sip_tickers(room)
    assert room._dealer_role_ticker.get("Alice") == 2


def test_update_sip_tickers_accumulates_across_calls():
    room = _make_room()
    alice = room.all_players[0]
    alice.add_drink(2, "net loss", "player")
    _update_sip_tickers(room)
    alice.drink_log.clear()
    alice.add_drink(3, "net loss", "player")
    _update_sip_tickers(room)
    assert room._sip_ticker.get("Alice") == 5


def test_update_sip_tickers_multiple_players_independent():
    room = _make_room()
    alice, bob = room.all_players[0], room.all_players[1]
    alice.add_drink(3, "net loss", "player")
    bob.add_drink(1, "net loss", "player")
    _update_sip_tickers(room)
    assert room._sip_ticker.get("Alice") == 3
    assert room._sip_ticker.get("Bob") == 1


# ---------------------------------------------------------------------------
# _snapshot_round
# ---------------------------------------------------------------------------

def test_snapshot_round_shifts_prev_sips():
    room = _make_room()
    room._last_round_sips = {"Alice": 2}
    room.all_players[0].add_drink(5, "net loss", "player")
    _snapshot_round(room)
    assert room._prev_round_sips == {"Alice": 2}
    assert room._last_round_sips.get("Alice") == 5


def test_snapshot_round_zero_sip_player_still_recorded():
    """Players with no drinks must appear in _last_round_sips (crown-badge logic)."""
    room = _make_room()
    _snapshot_round(room)
    assert "Alice" in room._last_round_sips
    assert room._last_round_sips["Alice"] == 0


def test_snapshot_round_increments_rounds_played():
    room = _make_room()
    _snapshot_round(room)
    assert room._player_rounds_played.get("Alice") == 1


def test_snapshot_round_appends_to_sip_history():
    room = _make_room()
    room.all_players[0].add_drink(3, "net loss", "player")
    _snapshot_round(room)
    assert len(room._round_sip_history) == 1
    assert room._round_sip_history[0] == 3


def test_snapshot_round_history_clamps_negative():
    room = _make_room()
    room.all_players[0].add_drink(-5, "bust vote correct: -1 sip credit", "player")
    _snapshot_round(room)
    assert room._round_sip_history[0] == 0   # max(0, -5) = 0


# ---------------------------------------------------------------------------
# _update_max_round_sips
# ---------------------------------------------------------------------------

def test_update_max_sips_records_first_round():
    room = _make_room()
    room._last_round_sips = {"Alice": 5}
    _update_max_round_sips(room)
    assert room._max_round_sips["Alice"] == 5


def test_update_max_sips_keeps_previous_higher():
    room = _make_room()
    room._max_round_sips    = {"Alice": 10}
    room._last_round_sips   = {"Alice": 3}
    _update_max_round_sips(room)
    assert room._max_round_sips["Alice"] == 10


def test_update_max_sips_replaces_previous_lower():
    room = _make_room()
    room._max_round_sips    = {"Alice": 2}
    room._last_round_sips   = {"Alice": 7}
    _update_max_round_sips(room)
    assert room._max_round_sips["Alice"] == 7


def test_update_max_sips_clamps_negative():
    room = _make_room()
    room._last_round_sips = {"Alice": -2}
    _update_max_round_sips(room)
    assert room._max_round_sips.get("Alice", 0) == 0


# ---------------------------------------------------------------------------
# _update_streaks
# ---------------------------------------------------------------------------

def test_streaks_win_round_increments():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_streaks(room)
    assert room._streaks["Alice"]["current"] == 1


def test_streaks_loss_round_decrements():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_streaks(room)
    assert room._streaks["Alice"]["current"] == -1


def test_streaks_neutral_resets_to_zero():
    room = _make_room()
    alice = room.all_players[0]
    alice.hands = [
        make_hand(("A", "H"), ("K", "D"), result="win"),
        make_hand(("5", "S"), ("6", "H"), result="loss"),
    ]
    room._streaks["Alice"] = {"current": 3, "longest_win": 3, "longest_loss": 0}
    _update_streaks(room)
    assert room._streaks["Alice"]["current"] == 0


def test_streaks_tracks_longest_win():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    room._streaks["Alice"] = {"current": 2, "longest_win": 2, "longest_loss": 0}
    _update_streaks(room)
    assert room._streaks["Alice"]["longest_win"] == 3


def test_streaks_tracks_longest_loss():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    room._streaks["Alice"] = {"current": -2, "longest_win": 0, "longest_loss": 2}
    _update_streaks(room)
    assert room._streaks["Alice"]["longest_loss"] == 3


def test_streaks_unresolved_hands_player_skipped():
    """Player with only unresolved hands (result=None) is not added to _streaks."""
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result=None)]
    _update_streaks(room)
    assert "Alice" not in room._streaks


# ---------------------------------------------------------------------------
# _update_hand_stats
# ---------------------------------------------------------------------------

def test_hand_stats_win_and_blackjack_counted():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_hand_stats(room)
    hs = room._hand_stats["Alice"]
    assert hs["hands"] == 1
    assert hs["wins"] == 1
    assert hs["blackjacks"] == 1


def test_hand_stats_loss_counted():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_hand_stats(room)
    assert room._hand_stats["Alice"]["losses"] == 1


def test_hand_stats_bust_counted():
    room = _make_room()
    room.all_players[0].hands = [
        make_hand(("K", "S"), ("Q", "H"), ("5", "D"), result="loss", bust=True)
    ]
    _update_hand_stats(room)
    assert room._hand_stats["Alice"]["busts"] == 1


def test_hand_stats_unresolved_hand_skipped():
    room = _make_room()
    room.all_players[0].hands = [make_hand(("A", "H"), ("K", "D"), result=None)]
    _update_hand_stats(room)
    assert room._hand_stats.get("Alice", {}).get("hands", 0) == 0


def test_hand_stats_split_hand_tracked():
    room = _make_room()
    room.all_players[0].hands = [
        make_hand(("7", "H"), ("8", "D"), result="win", from_split=True)
    ]
    _update_hand_stats(room)
    hs = room._hand_stats["Alice"]
    assert hs["split_hands"] == 1
    assert hs["split_wins"] == 1


def test_hand_stats_accumulates_across_rounds():
    room = _make_room()
    alice = room.all_players[0]
    alice.hands = [make_hand(("A", "H"), ("K", "D"), result="win")]
    _update_hand_stats(room)
    alice.hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_hand_stats(room)
    hs = room._hand_stats["Alice"]
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
    ds = room._dealer_hand_stats["Alice"]
    assert ds["losses"] == 1


def test_dealer_stats_player_loss_is_dealer_win():
    room = _make_room(["Alice", "Bob"])
    room.all_players[1].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_dealer_stats(room)
    assert room._dealer_hand_stats["Alice"]["wins"] == 1


def test_dealer_stats_bust_hand_counted():
    room = _make_room(["Alice", "Bob"])
    # Give the dealer player a bust hand
    room.all_players[0].dealer_hand = make_hand(("K", "S"), ("Q", "H"), ("5", "D"))
    _update_dealer_stats(room)
    assert room._dealer_bust_rounds == 1


def test_dealer_stats_dealer_own_hands_excluded():
    """The dealer player's non-dealer hands are not counted in dealer stats."""
    room = _make_room(["Alice", "Bob"])
    # Give the dealer (Alice) a player hand — shouldn't be counted
    room.all_players[0].hands = [make_hand(("5", "S"), ("6", "H"), result="loss")]
    _update_dealer_stats(room)
    assert room._dealer_hand_stats.get("Alice", {}).get("wins", 0) == 0


# ---------------------------------------------------------------------------
# _record_drinks_detail
# ---------------------------------------------------------------------------

def test_record_drinks_detail_positive_sip_in_last_round_drinks():
    room = _make_room()
    room.all_players[0].add_drink(2, "net loss", "player")
    _record_drinks_detail(room)
    assert any(d["name"] == "Alice" and d["sips"] == 2 for d in room._last_round_drinks)


def test_record_drinks_detail_credit_in_last_round_drinks():
    room = _make_room()
    room.all_players[0].add_drink(-1, "bust vote correct: -1 sip credit", "player")
    _record_drinks_detail(room)
    assert any(d["name"] == "Alice" and d["sips"] == -1 for d in room._last_round_drinks)


def test_record_drinks_detail_replaces_previous_detail():
    """Each call to _record_drinks_detail overwrites _last_round_drinks."""
    room = _make_room()
    room._last_round_drinks = [{"name": "Bob", "sips": 9, "reason": "stale"}]
    room.all_players[0].add_drink(1, "net loss", "player")
    _record_drinks_detail(room)
    # stale entry replaced; only Alice's drink remains
    names = [d["name"] for d in room._last_round_drinks]
    assert "Bob" not in names or all(d["sips"] != 9 for d in room._last_round_drinks)
