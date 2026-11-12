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


def test_load_reads_settings_and_milestones(tmp_path):
    _exports(tmp_path, "2026-10-31", with_rate=True)
    path = tmp_path / "drinks_summary_2026-10-31.xlsx"
    wb = openpyxl.load_workbook(path)
    wb["Summary"].append([])
    wb["Summary"].append(["MILESTONES"])
    wb["Summary"].append(["Threshold", "First to reach"])
    wb["Summary"].append(["50 sips", "Rob"])
    st = wb.create_sheet("Settings")
    for row in (["Setting", "Value"], ["Sips per hand", 2], ["Hands per player", 2], ["Decks", 1],
                ["Easy Mode", "off"], [], ["Rule ID", "Rule", "On"], ["core.net_loss", "Net hand losses", "on"],
                ["side.bust_vote", "Side bet: dealer bust vote", "off"]):
        st.append(row)
    wb.save(path)
    a = load("2026-10-31", str(tmp_path))
    assert a["setup"]["wager"] == 2 and a["setup"]["decks"] == 1 and a["setup"]["easy_mode"] is False
    assert not a["setup"]["rules"].on("side.bust_vote")
    assert a["setup"]["rules"].on("core.net_loss")
    assert a["milestones"][0][:2] == (50, "Rob")


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


def _merge(folder, day):
    """Fold the legacy pair into one session_data_<day>.xlsx, as /export_session writes it."""
    wb = openpyxl.load_workbook(folder / f"drinks_summary_{day}.xlsx")
    dec = openpyxl.load_workbook(folder / f"decision_log_{day}.xlsx")
    for ws in dec.worksheets:
        new = wb.create_sheet(ws.title)
        for row in ws.iter_rows(values_only=True):
            new.append(list(row))
    wb.save(folder / f"session_data_{day}.xlsx")


def test_load_reads_the_merged_session_file(tmp_path):
    _exports(tmp_path, "2026-10-31", with_rate=True)
    legacy = load("2026-10-31", str(tmp_path))
    _merge(tmp_path, "2026-10-31")
    (tmp_path / "drinks_summary_2026-10-31.xlsx").unlink()
    (tmp_path / "decision_log_2026-10-31.xlsx").unlink()
    merged = load("2026-10-31", str(tmp_path))
    assert merged["total"] == legacy["total"] and merged["players"] == legacy["players"]
    assert merged["bs"] == legacy["bs"]


def test_merged_file_wins_over_legacy_pair_for_the_same_day(tmp_path):
    from scripts.session_files import decision_files, drinks_files, session_paths
    _exports(tmp_path, "2026-10-31", with_rate=True)
    _exports(tmp_path, "2026-07-01", with_rate=False)
    _merge(tmp_path, "2026-10-31")
    assert [p.name for p in drinks_files(tmp_path)] == ["drinks_summary_2026-07-01.xlsx", "session_data_2026-10-31.xlsx"]
    assert [p.name for p in decision_files(tmp_path)] == ["decision_log_2026-07-01.xlsx", "session_data_2026-10-31.xlsx"]
    assert session_paths(tmp_path, "2026-10-31")[0] == session_paths(tmp_path, "2026-10-31")[1]
    assert session_paths(tmp_path, "2026-07-01")[0].name == "drinks_summary_2026-07-01.xlsx"
