"""
scripts/build_recap_deck.py
============================
Build the session recap deck (app/services/recap_deck.py) as a vector PDF
from a session's two saved exports (drinks_summary_<day>.xlsx +
decision_log_<day>.xlsx in data/decisions/), printed by a local headless
Edge/Chrome. The in-app button (GET /recap_html) renders the same deck in
the browser instead.

Usage:
    python scripts/build_recap_deck.py 2026-10-19
    python scripts/build_recap_deck.py 2026-10-19 --out data/recaps --html
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

import openpyxl

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.services.recap_deck import analyse, build_html, logo_css  # noqa: E402
from engine.rules_registry import RULES_BY_ID, RuleSet  # noqa: E402


def _rate_rounds(summary) -> dict:
    """Rounds each seat played at each Drink Rate factor, from the Summary
    sheet's DRINK RATE table ("Rounds @ 1.4×" columns); {} when the export
    has none (everyone at 1.0×, or an export from before Drink Rate)."""
    rows = list(summary.iter_rows(values_only=True))
    out = {}
    for i, r in enumerate(rows):
        if r and r[0] == "DRINK RATE":
            hdr = rows[i + 1]
            cols = {j: float(str(h).removeprefix("Rounds @ ").rstrip("×"))
                    for j, h in enumerate(hdr) if isinstance(h, str) and h.startswith("Rounds @ ")}
            for r2 in rows[i + 2:]:
                if not r2 or not r2[0] or str(r2[0]).startswith("Avg factor"):
                    break
                out[r2[0]] = {f: r2[j] for j, f in cols.items() if r2[j]}
            break
    return out


def _milestones(summary) -> dict:
    """{boundary: first player to reach it} from the Summary sheet's MILESTONES table."""
    rows = list(summary.iter_rows(values_only=True))
    out = {}
    for i, r in enumerate(rows):
        if r and r[0] == "MILESTONES":
            for r2 in rows[i + 2:]:                    # skip the "Threshold | First to reach" header
                if not r2 or not r2[0]:
                    break
                out[int(str(r2[0]).split()[0])] = r2[1]
            break
    return out


def _settings(wb) -> dict:
    """Table setup and house rules from the Settings sheet (exports from
    before it existed have none: the recap then says so)."""
    if "Settings" not in wb.sheetnames:
        return {}
    rows = [r for r in wb["Settings"].iter_rows(values_only=True)]
    vals = {r[0]: r[1] for r in rows if r and r[0] and len(r) > 1 and r[0] not in ("Setting", "Rule ID")}
    on = {r[0] for r in rows if r and len(r) > 2 and r[2] == "on"}
    out = {"wager": vals.get("Sips per hand"), "hands": vals.get("Hands per player"),
           "decks": vals.get("Decks"), "easy_mode": vals.get("Easy Mode") == "on"}
    if on:
        known = on & RULES_BY_ID.keys()                # rule IDs from a newer build are skipped
        out["rules"] = RuleSet(frozenset(known))
    return {k: v for k, v in out.items() if v is not None}


def load(day: str, folder: str) -> dict:
    drinks = openpyxl.load_workbook(os.path.join(folder, f"drinks_summary_{day}.xlsx"), read_only=True)
    it = drinks["Raw Rows"].iter_rows(values_only=True)
    hdr = next(it)
    rows = []
    for r in it:
        if not r[0]:
            continue
        row = dict(zip(hdr, r))
        # Drink Rate columns only count with the rate column: older exports'
        # sips_raw meant something else, and analyse() treats no rate as 1.0×
        keys = ["round", "dealer", "player", "role", "rule", "sips"] + (["sips_raw", "rate"] if "rate" in hdr else [])
        rows.append({k: row[k] for k in keys if row.get(k) is not None})
    setup = {"rate_rounds": _rate_rounds(drinks["Summary"]), "milestones": _milestones(drinks["Summary"]),
             **_settings(drinks)}

    dec_wb = openpyxl.load_workbook(os.path.join(folder, f"decision_log_{day}.xlsx"), read_only=True)
    ws = dec_wb["Hand Decisions"]
    it = ws.iter_rows(values_only=True)
    hdr = next(it)
    decisions = [dict(zip(hdr, r)) for r in it if r[0]]
    ws = dec_wb["Dealer Lottery Entries"]
    it = ws.iter_rows(values_only=True)
    hdr = next(it)
    lottery = [dict(zip(hdr, r)) for r in it if r[0]]
    return analyse(rows, decisions, lottery, day, setup)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def _browser() -> str | None:
    for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(path):
            return path
    return shutil.which("chromium") or shutil.which("google-chrome") or shutil.which("msedge")


def print_pdf(html_path: str, pdf_path: str) -> None:
    """Print an HTML file to PDF with a local headless Edge/Chrome; exits on failure.
    Also used by scripts/build_pitch_deck.py."""
    exe = _browser()
    if not exe:
        sys.exit(f"No Edge/Chrome found; HTML written to {html_path}")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    # A throwaway profile, or an already-open Edge/Chrome swallows the call;
    # the launcher can exit before the PDF lands, so wait for the file
    profile = tempfile.mkdtemp()
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
                    "file:///" + html_path.replace("\\", "/")],
                   capture_output=True, timeout=120)
    for _ in range(60):
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            break
        time.sleep(0.5)
    shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(pdf_path):
        sys.exit(f"PDF printing failed; HTML written to {html_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("day", help="session date as in the export file names, e.g. 2026-10-19")
    ap.add_argument("--dir", default=os.path.join(_ROOT, "data", "decisions"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "data", "recaps"))
    ap.add_argument("--html", action="store_true", help="also keep the HTML next to the PDF")
    args = ap.parse_args()

    a = load(args.day, args.dir)
    os.makedirs(args.out, exist_ok=True)
    html_path = os.path.join(args.out if args.html else tempfile.mkdtemp(), f"recap_{args.day}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(a, logo_css(inline=True)))
    pdf_path = os.path.join(args.out, f"recap_{args.day}.pdf")
    print_pdf(html_path, pdf_path)
    print(f"Wrote {pdf_path}")


if __name__ == "__main__":
    main()
