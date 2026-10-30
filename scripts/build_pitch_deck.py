"""
scripts/build_pitch_deck.py
============================
Build the Black(Out)Jack pitch deck (docs/Pitch-Deck.pdf, linked from the
README): what the game is, how a round works, the rules and side games,
house rules and Drink Rate, where to play, proof from real game nights and
the simulator, the recap, responsible play, and how to start.

Uses the recap deck's slides, colours and logo (app/services/recap_deck.py)
and its PDF printing (scripts/build_recap_deck.py, headless Edge/Chrome).
The numbers are read fresh on every run: game nights from data/decisions/,
balance from scripts/benchmarks.json, rule counts from the rules registry.

Usage:
    python scripts/build_pitch_deck.py
    python scripts/build_pitch_deck.py --out docs/Pitch-Deck.pdf --html
"""

import argparse
import csv
import glob
import json
import os
import sys
import tempfile
from datetime import date

import openpyxl

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.config import MILESTONE_HANDOUT_SIPS, MILESTONE_STEP, TIP_URL  # noqa: E402
from app.services.qr import qr_svg  # noqa: E402
from app.services.recap_deck import APP_NAME, CSS, esc, logo_css, slide, svg_race  # noqa: E402
from engine.rules_registry import PRESETS, RULES  # noqa: E402
from scripts.build_recap_deck import load, print_pdf  # noqa: E402

PLAY_URL = "https://black-out-jack.onrender.com"
REPO_URL = "https://github.com/robert-rjm/Black-Out-Jack"
DECK = "Pitch deck"


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def pilot(folder: str) -> dict:
    """Totals over every saved game night: drink logs give rounds, decision
    logs (xlsx, or the older csv) give decisions and time at the table."""
    nights, rounds, minutes, decisions, players = set(), 0, 0.0, 0, set()
    longest, latest = 0.0, None
    rounds_by_day, minutes_by_day = {}, {}
    for f in sorted(glob.glob(os.path.join(folder, "drinks_summary_*.xlsx"))):
        day = os.path.basename(f)[15:25]
        rows = [r for r in openpyxl.load_workbook(f, read_only=True)["Raw Rows"].iter_rows(min_row=2, values_only=True)
                if r and r[0]]
        if rows:
            nights.add(day)
            rounds_by_day[day] = max(r[0] for r in rows)
            rounds += rounds_by_day[day]
            players |= {r[2] for r in rows}
            latest = day
    for f in sorted(glob.glob(os.path.join(folder, "decision_log_*.*"))):
        day = os.path.basename(f)[13:23]
        if f.endswith(".xlsx"):
            it = openpyxl.load_workbook(f, read_only=True)["Hand Decisions"].iter_rows(values_only=True)
            hdr = next(it)
            rows = [dict(zip(hdr, r)) for r in it if r[0]]
        elif f.endswith(".csv"):
            with open(f, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        else:
            continue
        nights.add(day)
        decisions += len(rows)
        ts = [float(r["timestamp"]) for r in rows if r.get("timestamp")]
        if ts:
            span = (max(ts) - min(ts)) / 60
            minutes += span
            minutes_by_day[day] = span
            longest = max(longest, span)
    first = min(nights) if nights else None
    both = [d for d in rounds_by_day if d in minutes_by_day]
    timed_rounds = sum(rounds_by_day[d] for d in both)
    return {"nights": len(nights), "rounds": rounds, "round_nights": len(rounds_by_day), "hours": minutes / 60,
            "decisions": decisions, "players": len(players), "longest": longest, "first": first,
            "latest": latest,
            "min_per_round": sum(minutes_by_day[d] for d in both) / timed_rounds if timed_rounds else 0}


def balance() -> list[tuple]:
    """(label, sips per player per round, dealer bust %, blackjack %) for a few table sizes."""
    with open(os.path.join(_ROOT, "scripts", "benchmarks.json"), encoding="utf-8") as f:
        b = json.load(f)
    out = []
    for key in ("2p_1d", "3p_1d", "4p_2d"):
        if key in b:
            c = b[key]["config"]
            out.append((f"{c['num_players']} players · {c['num_decks']} deck{'s' if c['num_decks'] > 1 else ''}",
                        b[key]["avg_sips_per_round"] / c["num_players"], b[key]["dealer_bust_pct"],
                        b[key]["blackjack_rate_pct"], c["num_rounds"]))
    return out


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def cards(items, cols=3, cls="card") -> str:
    return (f'<div class="cards c{cols}">' + "".join(
        f'<div class="{cls}"><div class="em">{e}</div><div class="ct">{t}</div><div class="cb">{b}</div></div>'
        for e, t, b in items) + "</div>")


def build(p: dict, bal: list, recap_a: dict | None) -> str:
    n_rules = len(RULES)
    preset_n = {k: len(v) for k, v in PRESETS.items()}
    src = f"Source: {APP_NAME} rules, game logs and simulator"
    when = date.fromisoformat(p["first"]).strftime("%B %Y") if p["first"] else ""
    pages = []

    def add(tracker, title, body, source=src):
        pages.append(slide(tracker, title, body, source, len(pages) + 1, deck=DECK))

    # 1 — Cover
    pages.append(f'''<section class="slide cover">
      <div class="cv-band"></div>
      <div class="logo cv-logo"></div>
      <div class="cv-kicker">The blackjack drinking game for your phone</div>
      <div class="cv-title">{APP_NAME}</div>
      <div class="cv-sub">Blackjack where splitting 10s is mandatory and good decisions are optional.</div>
      <div class="cv-kpis">
        <div><b>Free</b><span>in your browser</span></div>
        <div><b>{n_rules}</b><span>house rules</span></div>
        <div><b>2–12</b><span>seats, bots included</span></div>
        <div><b>{p["nights"]}</b><span>nights play-tested</span></div>
      </div>
      <div class="cv-foot">{PLAY_URL.removeprefix("https://")} · 18+ only · drink responsibly</div>
    </section>''')

    # 2 — The pitch
    add("Why Black(Out)Jack",
        "Blackjack night without the bookkeeping: the app deals, keeps the score and settles every argument",
        cards([
            ("🃏", "It deals", "A shuffled shoe on every phone. The dealer seat rotates by itself, and bots fill "
                              "empty seats."),
            ("🧮", "It keeps score", "Every sip, credit and handout is counted live, per player, and milestones "
                                    "are called out as they happen."),
            ("⚖️", "It settles arguments", "Rules fire automatically. Votes and side bets run on everyone's "
                                          "phone, with a timer."),
        ])
        + '<div class="sowhat wide"><b>So what</b>Everyone plays; nobody has to be the referee, the banker or the '
          'one who remembers what an Ace of Spades does.</div>')

    # 3 — A round
    steps = [
        ("1", "Call it", "Before the deal, bet whether the dealer busts. Right earns a credit and a handout; wrong "
                         "costs a sip."),
        ("2", "Play two hands", "Hit, stand, double or split. Unsuited 10s must be split: playing it safe is "
                                "not the point."),
        ("3", "Rules fire live", "Aces, suited hands, a third 6 or 7 on the table: sips move the moment the "
                                 "card lands."),
        ("4", "Settle up", "Wins offset losses, so you only drink your net loss. Then the dealer seat moves on."),
    ]
    body = ('<div class="steps">' + "".join(f'<div class="step"><i>{k}</i><b>{t}</b><span>{d}</span></div>'
                                            for k, t, d in steps) + '</div>'
            + f'<div class="sowhat wide"><b>So what</b>A round takes about {p["min_per_round"]:.1f} minutes at a '
              'real table, quick enough that nobody waits long for their turn.</div>')
    add("How it plays", "Four steps a round, and the app runs all of them", body,
        src + " · Round time: average over the play-test nights")

    # 4 — Rules
    add("The rules",
        "The drinking rules reward bold play: the table drinks when you win big",
        cards([
            ("📉", "Net losses only", "Wins offset losses. You only drink for the hands you lose more than you "
                                      "win."),
            ("🎉", "Your Blackjack, their sips", "Blackjacks, doubled and split wins and suited hands hand sips "
                                                "to everyone else."),
            ("🂡", "Aces have powers", "♣ a credit · ♠ the next player drinks · ♥ treat yourself · ♦ the "
                                     "dealer drinks."),
            ("🔟", "Split 10s with honor", "Unsuited 10s must be split. The cautious 20 is off the menu."),
            ("😈", "Devil's Hand · Lucky Sevens", "A third 6 on the table makes someone drink; a third 7 "
                                                 "hands out a credit."),
            ("🏁", "Milestones", f"First to every {MILESTONE_STEP} sips hands out {MILESTONE_HANDOUT_SIPS}. Back-"
                                "to-back winners get called out."),
        ]), src + " · Full rules: docs/Rules.md")

    # 5 — Side games
    add("Side games",
        "Between hands, four side games keep the whole table in it, dealer included",
        cards([
            ("🎯", "Dealer bust vote", "Bet the dealer busts. Right: a credit plus a handout. Wrong: a sip."),
            ("🎰", "Dealer Lottery", "Dealer lands a paired 18 or 20? Stake 0–5 on a split redeal: busts pay out, "
                                    "a clean redeal costs you."),
            ("👉", "Targeted Drinking", "The table votes someone onto the spot: call bust or stand on a mini-hand "
                                       "until three in a row."),
            ("🃏", "Wild Card", "Tap the logo for a surprise: a sip for you, for someone random, or a Targeted "
                               "round."),
        ], cols=4)
        + '<div class="sowhat wide"><b>So what</b>Every side game is a switch in 📜 House rules: keep the ones '
          'your table loves, drop the rest, even mid-game.</div>')

    # 6 — Your rules
    ladder = "".join(
        f'<div class="rung"><b>{name.title()}</b><span>{preset_n[name]} rules · {blurb}</span></div>'
        for name, blurb in (("starter", "the essentials"), ("standard", "the classic night"),
                            ("full", "everything on")))
    body = (f'<div class="row2"><div><h3>House rules your way</h3><div class="ladder">{ladder}</div>'
            '<ul class="ticks"><li>Start on a preset, then add rules one at a time</li>'
            '<li>Switch any rule off, even mid-game</li>'
            '<li>Players suggest changes; the table can vote them in</li></ul></div>'
            '<div><h3>Fair for every drink</h3><ul class="ticks">'
            '<li><b>Drink Rate</b>: each seat picks its factor, from wine at 0.6× or a cocktail at 0.4× up to a '
            '1.5× booster</li>'
            '<li><b>Easy Mode</b>: halve everyone\'s sips with one switch</li>'
            '<li><b>Big tables</b>: sips halve by themselves at 4+ players</li>'
            '<li><b>Normal mode</b>: the same game with chips, no drinking at all</li></ul></div></div>')
    add("Your table", f"Every table sets its own game: {n_rules} rules, three presets, and a drink rate for each seat",
        body)

    # 7 — Play anywhere
    add("Play anywhere",
        "One room code gets everyone in, around one table or across the country",
        cards([
            ("📱", "Digital", "Phones and laptops, no install: add it to your home screen for an app feel. Bots "
                             "fill empty seats."),
            ("🂠", "Referee", "Play with a real deck; the app is the scorekeeper and rule book."),
            ("⌨️", "Terminal", "Solo or local multiplayer from the command line, for the nerds."),
        ])
        + '<div class="sowhat wide"><b>So what</b>Share the room code or its QR code, and anyone can join from '
          'their own phone. Spectators can watch without a seat.</div>')

    # 8 — Proof
    kpis = [(p["nights"], f"game nights since {when}"),
            (f"{p['rounds']:,}", f"rounds dealt on the {p['round_nights']} nights with drink logs"),
            (f"{p['decisions']:,}", "player decisions logged"), (f"{p['hours']:.0f} h", "at the table"),
            (f"{int(p['longest'] // 60)}h {int(p['longest'] % 60):02d}m", "longest night")]
    rows = "".join(f"<tr><td>{esc(lbl)}</td><td>{s:.1f}</td><td>{bust:.0f}%</td><td>{bj:.1f}%</td></tr>"
                   for lbl, s, bust, bj, _ in bal)
    sims = bal[0][4] if bal else 0
    body = ('<div class="row5">' + "".join(f'<div class="kpi"><b>{v}</b><span>{t}</span></div>' for v, t in kpis)
            + '</div><div class="row2"><div><h3>Balanced by the simulator</h3><table class="t"><tr><th>Table</th>'
              '<th>Sips per player per round</th><th>Dealer busts</th><th>Blackjacks</th></tr>'
            + rows + '</table></div><div class="sowhat"><b>So what</b>Every rule is tuned at real tables and '
              f'checked over {sims:,} simulated rounds per table size, so a night stays a steady, social pace '
              'instead of a race to the floor. The play-test nights are the developers\' own group of friends, '
              'not a public user count.</div></div>')
    add("Proof", f"Play-tested over {p['nights']} real game nights and balanced over {sims:,} simulated rounds",
        body, src + " · Game nights: data/decisions · Simulator: scripts/simulation.py, basic-strategy bots")

    # 9 — Recap
    if recap_a:
        chart = svg_race(recap_a, w=640, h=330)
        body = (f'<div class="row-recap"><div><h3>A real night: the race to the top</h3>{chart}</div>'
                '<div><h3>Every recap includes</h3><ul class="ticks">'
                '<li>An executive summary and a race chart with every lead change</li>'
                '<li>Where the sips came from, round by round</li>'
                '<li>Who played by the book, and who ran the toughest house</li>'
                '<li>A page for every player, awards included</li></ul>'
                '<div class="sowhat"><b>So what</b>One tap on “📊 Download Recap (PDF)” in the summary, and '
                'the group chat has something to argue about until the next game.</div></div></div>')
        add("After the game", "Every night ends with a recap deck: who won, why, and who should never split again",
            body, src + f" · Chart: game night of {recap_a['day']}")

    # 10 — Responsible
    add("Play responsibly", "Built for good nights, not regrets",
        cards([
            ("🔞", "18+ only", "An age gate on every device, and a link to the Terms & Disclaimer."),
            ("🍷", "Drink less, still play", "Drink Rate discounts and Easy Mode cut the sips without leaving the "
                                            "game."),
            ("🥤", "Or don't drink at all", "Normal mode plays the same blackjack with chips instead of sips."),
            ("💧", "Know your limits", "Water counts. Taxis count. Never drink and drive."),
        ], cols=4)
        + '<div class="sowhat wide"><b>So what</b>The game is about the cards and the company; the sips are just '
          'how you keep score.</div>')

    # 11 — Call to action
    pages.append(f'''<section class="slide thanks">
      <div class="cv-band"></div>
      <div class="logo cv-logo"></div>
      <div class="ty-title">Deal yourself in</div>
      <div class="ty-sub">Free, in your browser, no sign-up. Grab some friends and a drink of your choice.</div>
      <div class="cta">
        <div class="cta-box"><div class="qr">{qr_svg(PLAY_URL)}</div><div><b>▶ Play now</b>
          <span><a href="{PLAY_URL}">{PLAY_URL.removeprefix("https://")}</a></span>
          <span>Rules: <a href="{REPO_URL}/blob/main/docs/Rules.md">docs/Rules.md</a></span>
          <span>Code: <a href="{REPO_URL}">github.com/robert-rjm/Black-Out-Jack</a></span></div></div>
        <div class="cta-box small"><div class="qr">{qr_svg(TIP_URL)}</div><div><b>🍺 Buy us a beer</b>
          <span>A free hobby project. Tips keep the cards coming:
          <a href="{TIP_URL}">{TIP_URL.removeprefix("https://")}</a></span></div></div>
      </div>
      <div class="cv-foot">18+ only · know your limits · never drink and drive · CC BY-NC-SA 4.0</div>
    </section>''')

    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{APP_NAME} pitch deck</title>"
            f"<style>{logo_css(inline=True)}{CSS}{PITCH_CSS}</style></head><body>{''.join(pages)}</body></html>")


PITCH_CSS = """
.cards { display: grid; gap: 20px; }
.cards.c3 { grid-template-columns: repeat(3, 1fr); }
.cards.c4 { grid-template-columns: repeat(4, 1fr); }
.body { padding-top: 30px; }
.card { background: #1a1d27; border: 1px solid #2e3247; border-radius: 12px; padding: 28px 28px; min-height: 290px; }
.cards.c3 .card { min-height: 220px; }
.cards.c3 + .sowhat, .cards.c4 + .sowhat { margin-top: 30px; }
.card .em { font-size: 46px; }
.card .ct { font-size: 23px; font-weight: 700; margin-top: 16px; }
.card .cb { font-size: 16.5px; color: #9095ab; margin-top: 10px; line-height: 1.55; }
.sowhat { font-size: 16.5px; padding: 18px 22px; }
.steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
.step { background: #1a1d27; border: 1px solid #2e3247; border-radius: 12px; padding: 28px; min-height: 360px; }
.step i { display: block; font-style: normal; width: 52px; height: 52px; border-radius: 12px; background: #4f8ef7;
  color: #0f1117; font-weight: 800; font-size: 26px; text-align: center; line-height: 52px; }
.step b { display: block; font-size: 24px; margin-top: 22px; }
.step span { display: block; font-size: 17px; color: #9095ab; margin-top: 12px; line-height: 1.55; }
.ladder { display: flex; gap: 14px; margin-bottom: 28px; }
.rung { flex: 1; background: #1a1d27; border: 1px solid #2e3247; border-radius: 12px; padding: 22px 20px;
  min-height: 130px; }
.rung:nth-child(2) { border-color: #4f8ef7; }
.rung:nth-child(3) { border-color: #f5c842; }
.rung b { display: block; font-size: 26px; }
.rung span { display: block; font-size: 15px; color: #9095ab; margin-top: 8px; line-height: 1.4; }
.ticks { list-style: none; margin: 0; padding: 0; }
.ticks li { position: relative; padding: 0 0 18px 30px; font-size: 18px; line-height: 1.5; }
.ticks li::before { content: "✓"; position: absolute; left: 0; color: #3ecf6e; font-weight: 800; }
.row5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 18px; margin-bottom: 40px; }
.row5 .kpi b { font-size: 40px; }
.row5 .kpi span { font-size: 14px; }
.row5 + .row2 .t td, .row5 + .row2 .t th { padding: 12px 10px; font-size: 16px; }
.row5 + .row2 .t th { font-size: 12px; }
.row-recap { display: grid; grid-template-columns: 640px 1fr; gap: 40px; }
.cta { position: absolute; left: 90px; top: 360px; display: flex; flex-direction: column; gap: 18px; width: 640px; }
.cta-box { display: flex; gap: 22px; align-items: center; background: #1a1d27; border: 1px solid #2e3247;
  border-radius: 12px; padding: 16px 20px; }
.cta-box .qr { width: 118px; height: 118px; flex: none; background: #fff; border-radius: 8px; padding: 4px; }
.cta-box.small .qr { width: 84px; height: 84px; }
.cta-box .qr svg { width: 100%; height: 100%; display: block; }
.cta-box b { display: block; font-size: 22px; color: #f5c842; margin-bottom: 4px; }
.cta-box span { display: block; font-size: 14px; color: #9095ab; line-height: 1.55; }
.cta-box a { color: #4f8ef7; text-decoration: none; font-weight: 700; }
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=os.path.join(_ROOT, "data", "decisions"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "docs", "Pitch-Deck.pdf"))
    ap.add_argument("--html", action="store_true", help="also keep the HTML next to the PDF")
    args = ap.parse_args()

    p = pilot(args.dir)
    recap_a = load(p["latest"], args.dir) if p["latest"] else None
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    html_path = (os.path.splitext(args.out)[0] + ".html" if args.html
                 else os.path.join(tempfile.mkdtemp(), "pitch.html"))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build(p, balance(), recap_a))
    print_pdf(html_path, args.out)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
