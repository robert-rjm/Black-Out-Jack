"""
tests/scripts/test_build_recap_deck.py
======================================
scripts/build_recap_deck.py reading a session back from its two xlsx
exports: the Drink Rate columns and the Summary sheet's rounds-per-factor
table must reach the deck, and older exports without them read as 1.0×.
"""

import openpyxl

from scripts.build_recap_deck import load


def _exports(folder, day, *, with_rate: bool):
    wb = openpyxl.Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Drinking Blackjack — Session Summary"])
    if with_rate:
        summary.append(["DRINK RATE"])
        summary.append(["Player", "Rounds", "Avg factor", "Raw sips", "Effective sips", "Effective ÷ raw",
                        "Rounds @ 1×", "Rounds @ 1.4×"])
        summary.append(["Rob", 2, 1.2, 4, 5, 1.25, 1, 1])
        summary.append(["Marko", 2, 1.0, 3, 3, 1.0, 2, 0])
        summary.append(["Avg factor = mean of the seat's drink factor over the rounds played"])
    raw = wb.create_sheet("Raw Rows")
    if with_rate:
        raw.append(["round", "dealer", "player", "role", "rule", "sips", "sips_raw", "rate"])
        raw.append([1, "Rob", "Rob", "player", "Net hand losses", 2, 2, 1.0])
        raw.append([2, "Rob", "Rob", "player", "Net hand losses", 3, 2, 1.4])
        raw.append([1, "Rob", "Marko", "player", "Net hand losses", 3, 3, 1.0])
    else:
        # Older format: sips_raw without rate (here it differs because of halving, not a factor)
        raw.append(["round", "dealer", "player", "role", "rule", "sips", "sips_raw"])
        raw.append([1, "Rob", "Rob", "player", "Net hand losses", 2, 4])
        raw.append([1, "Rob", "Marko", "player", "Net hand losses", 3, 3])
    wb.save(folder / f"drinks_summary_{day}.xlsx")

    dec = openpyxl.Workbook()
    hd = dec.active
    hd.title = "Hand Decisions"
    hd.append(["session_id", "timestamp", "round", "player", "hand_index", "dealer_name", "action_taken",
               "basic_strategy_action", "is_npc", "hand_result"])
    for rnd in (1, 2):
        for p in ("Rob", "Marko"):
            hd.append(["Test1", 1_800_000_000 + rnd * 60, rnd, p, 1, "Rob", "s", "s", False, "loss"])
    lot = dec.create_sheet("Dealer Lottery Entries")
    lot.append(["session_id", "timestamp", "round", "player", "is_npc", "x_entered"])
    dec.save(folder / f"decision_log_{day}.xlsx")


def test_load_reads_drink_rate_columns_and_rounds_per_factor(tmp_path):
    _exports(tmp_path, "2026-10-31", with_rate=True)
    a = load("2026-10-31", str(tmp_path))
    assert a["rate_used"]
    assert a["factor_rounds"]["Rob"] == {1.0: 1, 1.4: 1}       # from the Summary table, not guessed
    assert a["factor_rounds"]["Marko"] == {1.0: 2}
    assert a["raw_total"]["Rob"] == 4 and a["total"]["Rob"] == 5


def test_load_older_export_without_rate_is_one(tmp_path):
    _exports(tmp_path, "2026-07-01", with_rate=False)
    a = load("2026-07-01", str(tmp_path))
    assert not a["rate_used"]
    assert a["raw_total"]["Rob"] == 2                            # sips_raw ignored without a rate column
