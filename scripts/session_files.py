"""
scripts/session_files.py
=========================
Find the saved session exports in data/decisions/. A session is now one
workbook, session_data_<day>.xlsx (GET /export_session: Summary, Raw Rows,
Settings, Hand Decisions and Dealer Lottery Entries sheets). Sessions saved
before the merge are two files, drinks_summary_<day>.xlsx and
decision_log_<day>.xlsx; both layouts keep working, and when a day has the
merged file the legacy ones for that day are ignored.
"""

from pathlib import Path

MERGED = "session_data"
_DRINKS, _DECISIONS = "drinks_summary", "decision_log"


def _day(path: Path, prefix: str) -> str:
    return path.stem[len(prefix) + 1:]


def session_files(directory, legacy_prefix: str) -> list[Path]:
    """Every export holding the legacy file's sheets: all merged files plus
    the legacy_prefix ("drinks_summary" or "decision_log") ones whose day has
    no merged file."""
    d = Path(directory)
    merged = sorted(d.glob(f"{MERGED}_*.xlsx"))
    taken = {_day(p, MERGED) for p in merged}
    legacy = [p for p in sorted(d.glob(f"{legacy_prefix}_*.xlsx")) if _day(p, legacy_prefix) not in taken]
    return sorted(merged + legacy)


def decision_files(directory) -> list[Path]:
    return session_files(directory, _DECISIONS)


def drinks_files(directory) -> list[Path]:
    return session_files(directory, _DRINKS)


def session_paths(directory, day: str) -> tuple[Path, Path]:
    """(drinks workbook, decisions workbook) for one day: the same merged
    file twice, or the legacy pair."""
    d = Path(directory)
    merged = d / f"{MERGED}_{day}.xlsx"
    if merged.exists():
        return merged, merged
    return d / f"{_DRINKS}_{day}.xlsx", d / f"{_DECISIONS}_{day}.xlsx"
