"""
Tests for the 🏆 trophy (compute_trophy_holder, serializer.py) and the
👑/💎 crown badge, plus the total_clean_rounds/clean_streak bookkeeping
both are built on (drink_tracker.py).
"""

from engine.referee import RefereeSession
from tests.conftest import make_player
from app.models.game_room import GameRoom, GameConfig
from app.services.drink_tracker import award_sips, _snapshot_round
from app.services.serializer import compute_trophy_holder


def _make_room(names=None):
    names = names or ["Alice", "Bob", "Carol"]
    players = [make_player(n) for n in names]
    players[0].is_dealer = True
    raw = RefereeSession(players, players[0].name, wager=1, num_hands=1)
    return GameRoom(session=raw, config=GameConfig(mode="digital", drinking_mode=True))


# ---------------------------------------------------------------------------
# compute_trophy_holder
# ---------------------------------------------------------------------------

def test_trophy_holder_none_below_threshold():
    room = _make_room()
    room.stats.total_clean_rounds = {"Alice": 2}
    assert compute_trophy_holder(room) is None


def test_trophy_holder_unique_leader_at_threshold():
    room = _make_room()
    room.stats.total_clean_rounds = {"Alice": 3, "Bob": 1}
    assert compute_trophy_holder(room) == "Alice"


def test_trophy_holder_none_when_tied_at_threshold():
    room = _make_room()
    room.stats.total_clean_rounds = {"Alice": 3, "Bob": 3}
    assert compute_trophy_holder(room) is None


def test_trophy_holder_escalates_past_a_tie():
    room = _make_room()
    room.stats.total_clean_rounds = {"Alice": 5, "Bob": 3}
    # Tied at 3 -> threshold escalates to 5 -> Alice uniquely clears it
    assert compute_trophy_holder(room) == "Alice"


# ---------------------------------------------------------------------------
# award_sips: retroactive clean-round reconciliation
# ---------------------------------------------------------------------------
#
# harvest_drink_log's _snapshot_round only knows about sips recorded by
# round-end. Milestone handouts, Dealer Lottery, and bust-vote handouts all
# resolve afterward on later ticks and call award_sips -- which can flip
# whether the round counts as "clean" after total_clean_rounds has already
# been incremented (or not) for it. Without reconciling here, the trophy can
# keep crediting (or miss) a round based on stale information.

def test_post_harvest_drink_retroactively_uncounts_clean_round():
    room = _make_room()
    room.round._drink_log_harvested = True
    room.drinks.last_round_sips = {"Alice": 0}
    room.stats.total_clean_rounds = {"Alice": 3}   # already counted this round as clean

    award_sips(room, "Alice", 4, "Dealer Lottery drink", reason="test")

    assert room.drinks.last_round_sips["Alice"] == 4
    assert room.stats.total_clean_rounds["Alice"] == 2   # corrected back down


def test_post_harvest_credit_retroactively_counts_clean_round():
    room = _make_room()
    room.round._drink_log_harvested = True
    room.drinks.last_round_sips = {"Alice": 4}
    room.stats.total_clean_rounds = {"Alice": 2}   # this round wasn't counted as clean

    award_sips(room, "Alice", -4, "Dealer Lottery credit", reason="test")

    assert room.drinks.last_round_sips["Alice"] == 0
    assert room.stats.total_clean_rounds["Alice"] == 3   # now retroactively counted


def test_post_harvest_extra_drink_while_already_dirty_does_not_double_count():
    room = _make_room()
    room.round._drink_log_harvested = True
    room.drinks.last_round_sips = {"Alice": 2}
    room.stats.total_clean_rounds = {"Alice": 2}

    award_sips(room, "Alice", 3, "Dealer Lottery drink", reason="test")

    assert room.drinks.last_round_sips["Alice"] == 5
    assert room.stats.total_clean_rounds["Alice"] == 2   # unchanged, was already dirty


def test_pre_harvest_award_does_not_touch_clean_round_tally():
    """award_sips is documented as always post-harvest -- this just confirms
    the reconciliation is defensively gated on that, not a live code path."""
    room = _make_room()
    room.round._drink_log_harvested = False
    room.drinks.last_round_sips = {}
    room.stats.total_clean_rounds = {}

    award_sips(room, "Alice", 3, "test", reason="test")

    assert room.stats.total_clean_rounds.get("Alice") is None


def test_trophy_no_longer_sticks_after_dealer_lottery_drink_breaks_clean_round():
    """End-to-end regression for the reported bug: a player becomes the sole
    trophy holder immediately after round-end (harvest_drink_log saw 0 sips
    for them), but Dealer Lottery -- an async event that resolves seconds
    later -- then makes them drink. Before the fix, total_clean_rounds was
    never corrected, so the trophy kept showing for a round that, once
    everything settled, wasn't actually clean."""
    room = _make_room()
    room.round._drink_log_harvested = True
    room.drinks.last_round_sips = {"Alice": 0, "Bob": 1, "Carol": 1}
    room.stats.total_clean_rounds = {"Alice": 3, "Bob": 0, "Carol": 0}

    assert compute_trophy_holder(room) == "Alice"   # trophy shows immediately

    # Dealer Lottery resolves moments later: Alice's split hands didn't
    # bust, so she drinks -- her round is no longer clean.
    award_sips(room, "Alice", 4, "Dealer Lottery drink", reason="no bust")

    assert compute_trophy_holder(room) is None   # trophy correctly revoked


# ---------------------------------------------------------------------------
# award_sips: retroactive clean_streak reconciliation (crown/diamond badge)
# ---------------------------------------------------------------------------
#
# Same root cause as total_clean_rounds above, but trickier to correct: a
# round retroactively turning dirty must fully reset the streak (streak-
# breaking isn't a decrement-by-one), while a round retroactively turning
# clean needs to know what the streak was *before* this round -- which
# harvest already zeroed out, believing the round dirty at the time. See
# RoundState._pre_round_clean_streak, snapshotted by _snapshot_round.

def test_snapshot_round_captures_pre_round_streak_before_updating():
    room = _make_room()
    room.stats.clean_streak = {"Alice": 2}   # Alice already had a 2-round streak
    for p in room.all_players:
        p.drink_log = []   # everyone clean this round -> streak becomes 3

    _snapshot_round(room)

    assert room.round._pre_round_clean_streak == {"Alice": 2}   # snapshot taken BEFORE the update
    assert room.stats.clean_streak["Alice"] == 3                # then correctly updated


def test_post_harvest_drink_resets_streak_to_zero_not_decrement():
    room = _make_room()
    room.round._drink_log_harvested = True
    room.drinks.last_round_sips = {"Alice": 0}
    room.stats.clean_streak = {"Alice": 5}   # harvest saw this round as clean, streak now 5

    award_sips(room, "Alice", 2, "Dealer Lottery drink", reason="test")

    assert room.stats.clean_streak["Alice"] == 0   # full reset, not 4 (decrement would be wrong)


def test_post_harvest_credit_reconstructs_streak_from_pre_round_snapshot():
    room = _make_room()
    room.round._drink_log_harvested = True
    room.round._pre_round_clean_streak = {"Alice": 4}   # streak coming into this round
    room.drinks.last_round_sips = {"Alice": 3}
    room.stats.clean_streak = {"Alice": 0}   # harvest saw this round as dirty, streak reset to 0

    award_sips(room, "Alice", -3, "Dealer Lottery credit", reason="test")

    assert room.drinks.last_round_sips["Alice"] == 0
    assert room.stats.clean_streak["Alice"] == 5   # pre-round streak (4) + 1 for this now-clean round


def test_crown_streak_no_longer_stuck_after_dealer_lottery_drink_breaks_clean_round():
    """End-to-end regression mirroring the trophy test above, but for the
    crown/diamond badge's clean_streak."""
    room = _make_room()
    room.round._drink_log_harvested = True
    room.round._pre_round_clean_streak = {"Alice": 1}
    room.drinks.last_round_sips = {"Alice": 0}
    room.stats.clean_streak = {"Alice": 2}   # harvest incremented it believing the round clean

    award_sips(room, "Alice", 4, "Dealer Lottery drink", reason="no bust")

    assert room.stats.clean_streak["Alice"] == 0   # streak correctly broken, not left at 2
