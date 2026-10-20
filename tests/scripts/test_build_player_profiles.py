"""
tests/scripts/test_build_player_profiles.py
=============================================
Covers scripts/build_player_profiles.py's build_lottery_stakes: mining a
per-player Dealer Lottery staking tendency from "Dealer Lottery Entries"
sheet rows (written by app.services.decision_log.record_dealer_lottery_entry,
exported via GET /export_decisions) into the lottery_stakes list consumed by
engine/style_strategy.py's decide_dealer_lottery_stake.
"""

from scripts.build_player_profiles import build_lottery_stakes, select_targets


def _row(player="Rob", is_npc="False", x_entered="3", current_owed="0"):
    return {
        "player": player, "is_npc": is_npc,
        "x_entered": x_entered, "current_owed": current_owed,
    }


def test_build_lottery_stakes_averages_per_owed_bucket():
    rows = [
        _row(current_owed="0", x_entered="0"),
        _row(current_owed="0", x_entered="2"),
        _row(current_owed="0", x_entered="1"),
    ]
    stakes = build_lottery_stakes(rows, "Rob", min_samples=3)
    assert stakes == [{"owed_bucket": "none", "avg_stake": 1.0, "samples": 3}]


def test_build_lottery_stakes_skips_bucket_below_min_samples():
    rows = [_row(current_owed="0", x_entered="5"), _row(current_owed="0", x_entered="5")]
    assert build_lottery_stakes(rows, "Rob", min_samples=3) == []


def test_build_lottery_stakes_excludes_npc_rows():
    rows = [_row(is_npc="True", x_entered="5")] * 5
    assert build_lottery_stakes(rows, "Rob", min_samples=3) == []


def test_build_lottery_stakes_excludes_other_players():
    rows = [_row(player="Marko", x_entered="5")] * 5
    assert build_lottery_stakes(rows, "Rob", min_samples=3) == []


def test_build_lottery_stakes_separates_buckets():
    rows = (
        [_row(current_owed="0", x_entered="1")] * 3 +
        [_row(current_owed="4", x_entered="5")] * 3
    )
    stakes = build_lottery_stakes(rows, "Rob", min_samples=3)
    by_bucket = {s["owed_bucket"]: s for s in stakes}
    assert by_bucket["none"]["avg_stake"] == 1.0
    assert by_bucket["high"]["avg_stake"] == 5.0


# ---------------------------------------------------------------------------
# select_targets: profiles are opt-in
# ---------------------------------------------------------------------------

def _never(name):
    raise AssertionError(f"must not ask about {name}")


def test_no_player_flag_only_rebuilds_existing_profiles():
    targets, skipped, unknown = select_targets(
        ["Andrej", "Rob", "Marko"], {"rob", "marko"}, None, _never)
    assert targets == ["Rob", "Marko"]
    assert skipped == ["Andrej"] and unknown == []


def test_new_player_is_only_created_when_confirmed():
    asked = []
    def decline(name):
        asked.append(name)
        return False
    assert select_targets(["Andrej"], set(), "andrej", decline) == ([], ["Andrej"], [])
    assert asked == ["Andrej"]
    assert select_targets(["Andrej"], set(), "ANDREJ", lambda n: True) == (["Andrej"], [], [])


def test_existing_profile_with_player_flag_does_not_ask():
    assert select_targets(["Rob"], {"rob"}, "rob", _never) == (["Rob"], [], [])


def test_player_flag_for_name_not_in_logs_builds_nothing():
    assert select_targets(["Rob"], {"rob"}, "Ghost", _never) == ([], [], ["Ghost"])
