"""
scripts/build_pitch_deck.py
============================
Build the Black(Out)Jack pitch deck, linked from the README, in two looks:

  docs/Pitch-Deck.pdf          the app's dark colours, icons and logo
  docs/Pitch-Deck-Finance.pdf  a sober white-and-navy report style, no emojis

Same twelve slides in both: why the game exists, how a round works, the
rules, side games, house rules and Drink Rate, where to play, a modelled
typical night, balance from the simulator, the recap, responsible play, and
how to start.

The numbers are read fresh on every run: the typical night from the logged
rounds in data/decisions/ (average and spread of sips per seat per round),
balance and sip sources from scripts/benchmarks.json, rule counts from the
rules registry. Slides, colours and PDF printing come from the recap deck
(app/services/recap_deck.py, scripts/build_recap_deck.py: headless
Edge/Chrome).

Usage:
    python scripts/build_pitch_deck.py                 # both looks
    python scripts/build_pitch_deck.py --theme finance --html
"""

import argparse
import collections
import glob
import json
import math
import os
import re
import statistics
import sys
import tempfile

import openpyxl

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.config import MILESTONE_HANDOUT_SIPS, MILESTONE_STEP, TIP_URL  # noqa: E402
from app.services.qr import qr_svg  # noqa: E402
from app.services.recap_deck import APP_NAME, CATEGORIES, CSS, _category, hbars, logo_css, slide  # noqa: E402
from engine.rules_registry import PRESETS, RULES  # noqa: E402
from scripts.build_recap_deck import print_pdf  # noqa: E402

PLAY_URL = "https://black-out-jack.onrender.com"
REPO_URL = "https://github.com/robert-rjm/Black-Out-Jack"
DECK = "Pitch deck"
NIGHT_ROUNDS = 40           # length of the modelled night
BAND_Z = 1.28               # 80% of seats fall inside the band

THEMES = {
    "app":     {"out": "Pitch-Deck.pdf", "line": "#4f8ef7", "band": "rgba(79,142,247,.16)", "grid": "#2e3247",
                "muted": "#9095ab", "text": "#e8eaf0", "mark": "#f5c842", "bar": "#4f8ef7", "bar2": "#35548f"},
    "finance": {"out": "Pitch-Deck-Finance.pdf", "line": "#0b2545", "band": "rgba(31,78,121,.14)", "grid": "#d5dae3",
                "muted": "#5b6475", "text": "#0b2545", "mark": "#b8860b", "bar": "#0b2545", "bar2": "#8fa3bf"},
}

# Pictographs and symbols come out of the finance deck; card suits (♠♥♦♣, U+2660–2667) stay
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-♟♨-⛿✀-➿⬀-⯿▶️]")


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def seat_rounds(folder: str) -> dict:
    """Net sips of every seat in every logged round (a seat with no drink in a
    round counts as 0): the mean and spread drive the modelled night."""
    vals, by_size = [], collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(folder, "drinks_summary_*.xlsx"))):
        rows = [r for r in openpyxl.load_workbook(f, read_only=True)["Raw Rows"].iter_rows(min_row=2, values_only=True)
                if r and r[0]]
        if not rows:
            continue
        sips = collections.Counter()
        for r in rows:
            sips[(r[0], r[2])] += r[5]
        players = {r[2] for r in rows}
        for rd in range(1, max(r[0] for r in rows) + 1):
            for p in players:
                vals.append(sips[(rd, p)])
                by_size[len(players)].append(sips[(rd, p)])
    return {"n": len(vals), "mean": statistics.mean(vals) if vals else 0, "sd": statistics.pstdev(vals) if vals else 0,
            "by_size": {k: statistics.mean(v) for k, v in by_size.items()}}


# Side games and milestones: left out of sips per hand, which is about the cards
_NOT_HAND = {"Bust votes", "Dealer Lottery", "Milestones"}


def sips_per_hand(entry: dict) -> float:
    """Simulator sips per hand dealt: sips per round, minus side games and
    milestones, over players × hands per round (splits aren't counted apart)."""
    c = entry["config"]
    side = sum(v for r, v in entry["sips_per_round_by_rule"].items()
               if _category(r) in _NOT_HAND or r.startswith(("Wild Card", "Targeted")))
    return (entry["avg_sips_per_round"] - side) / (c["num_players"] * c["hands_per_round"])


def benchmarks() -> dict:
    with open(os.path.join(_ROOT, "scripts", "benchmarks.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def svg_typical_night(m: float, sd: float, t: dict, w=660, h=330) -> str:
    """Expected running total for one seat over a NIGHT_ROUNDS night, with the
    range 80% of seats end up in (mean ± BAND_Z·sd·√rounds) and milestone lines."""
    L, R, T, B = 46, 110, 14, 40
    n = NIGHT_ROUNDS
    hi_end = m * n + BAND_Z * sd * math.sqrt(n)
    step = 50
    ymax = (int(hi_end / step) + 1) * step
    def x(i): return L + (w - L - R) * i / n
    def y(v): return T + (h - T - B) * (1 - max(v, 0) / ymax)
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="inherit">']
    v = 0
    while v <= ymax:
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{t["grid"]}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" font-size="11" fill="{t["muted"]}" '
                   f'text-anchor="end">{v}</text>')
        v += step
    for i in range(0, n + 1, 10):
        out.append(f'<text x="{x(i):.1f}" y="{h - B + 18}" font-size="11" fill="{t["muted"]}" '
                   f'text-anchor="middle">{i}</text>')
    out.append(f'<text x="{(L + w - R) / 2}" y="{h - 4}" font-size="11" fill="{t["muted"]}" '
               f'text-anchor="middle">Round</text>')
    upper = " ".join(f"{x(i):.1f},{y(m * i + BAND_Z * sd * math.sqrt(i)):.1f}" for i in range(n + 1))
    lower = " ".join(f"{x(i):.1f},{y(m * i - BAND_Z * sd * math.sqrt(i)):.1f}" for i in range(n, -1, -1))
    out.append(f'<polygon points="{upper} {lower}" fill="{t["band"]}"/>')
    out.append(f'<polyline points="{" ".join(f"{x(i):.1f},{y(m * i):.1f}" for i in range(n + 1))}" fill="none" '
               f'stroke="{t["line"]}" stroke-width="3"/>')
    # Milestones: where the expected seat crosses each MILESTONE_STEP
    k = MILESTONE_STEP
    while k < m * n:
        rd = k / m
        out.append(f'<circle cx="{x(rd):.1f}" cy="{y(k):.1f}" r="5" fill="{t["mark"]}"/>'
                   f'<text x="{x(rd) - 8:.1f}" y="{y(k) - 9:.1f}" font-size="11" fill="{t["mark"]}" '
                   f'text-anchor="end" font-weight="700">{k} by R{rd:.0f}</text>')
        k += MILESTONE_STEP
    end, spread = m * n, BAND_Z * sd * math.sqrt(n)
    for val, label, colour, weight in ((end + spread, f"{end + spread:.0f} heavy seat", t["muted"], 400),
                                       (end, f"{end:.0f} typical seat", t["line"], 700),
                                       (end - spread, f"{end - spread:.0f} light seat", t["muted"], 400)):
        out.append(f'<text x="{w - R + 8}" y="{y(val) + 4:.1f}" font-size="12" font-weight="{weight}" '
                   f'fill="{colour}">{label}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def build(theme: str, sr: dict, bench: dict) -> str:
    t = THEMES[theme]
    fin = theme == "finance"

    def txt(s: str) -> str:
        """The finance deck drops pictographs (card suits stay)."""
        return re.sub(r"“\s+", "“", re.sub(r"\s{2,}", " ", _EMOJI.sub("", s))).strip() if fin else s

    def cards(items, cols=3) -> str:
        return (f'<div class="cards c{cols}">' + "".join(
            f'<div class="card"><div class="em">{f"{i:02d}" if fin else e}</div><div class="ct">{txt(ti)}</div>'
            f'<div class="cb">{txt(b)}</div></div>' for i, (e, ti, b) in enumerate(items, 1)) + "</div>")

    def sowhat(text, wide=True) -> str:
        return f'<div class="sowhat{" wide" if wide else ""}"><b>So what</b>{txt(text)}</div>'

    pages = []
    src = f"Source: {APP_NAME} rules, logged rounds and simulator"

    def add(tracker, title, body, source=src):
        pages.append(slide(txt(tracker), txt(title), body, txt(source), len(pages) + 1, deck=DECK))

    n_rules = len(RULES)
    preset_n = {k: len(v) for k, v in PRESETS.items()}
    m, sd = sr["mean"], sr["sd"]

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
        <div><b>3</b><span>ways to play</span></div>
      </div>
      <div class="cv-foot">{PLAY_URL.removeprefix("https://")} · 18+ only · drink responsibly</div>
    </section>''')

    # 2 — Why
    add("Why Black(Out)Jack",
        "Blackjack night without the bookkeeping: the app deals, keeps the score and settles every argument",
        cards([
            ("🃏", "It deals", "A shuffled shoe on every phone. The dealer seat rotates by itself, and bots fill "
                              "empty seats."),
            ("🧮", "It keeps score", "Every sip, credit and handout is counted live, per player, and milestones "
                                    "are called out as they happen."),
            ("⚖️", "It settles arguments", "Rules fire automatically. Votes and side bets run on everyone's "
                                          "phone, with a timer."),
        ]) + sowhat("Everyone plays; nobody has to be the referee, the banker or the one who remembers what an "
                    "Ace of Spades does."))

    # 3 — A round
    steps = [
        ("Call it", "Before the deal, bet whether the dealer busts. Right earns a credit and a handout; wrong "
                    "costs a sip."),
        ("Play any hand", "Hit, stand, double or split, on as many hands as the table sets. Unsuited 10s must "
                          "be split."),
        ("Rules fire live", "Aces, suited hands, a third 6 or 7 on the table: sips move the moment the card "
                            "lands."),
        ("Settle up", "Wins offset losses, so you only drink your net loss. Then the dealer seat moves on."),
    ]
    add("How it plays", "Four steps a round, and the app runs all of them",
        '<div class="steps">' + "".join(f'<div class="step"><i>{k}</i><b>{s}</b><span>{d}</span></div>'
                                        for k, (s, d) in enumerate(steps, 1)) + '</div>'
        + sowhat("Nobody sits out: the dealer seat rotates, so over a night everyone deals and everyone plays."))

    # 4 — Rules
    add("The rules", "The drinking rules reward bold play: the table drinks when you win big",
        cards([
            ("📉", "Net losses only", "Wins offset losses. You only drink for the hands you lose more than you "
                                      "win."),
            ("🎉", "Your Blackjack, their sips", "Blackjacks, doubled and split wins and suited hands hand sips "
                                                "to everyone else."),
            ("🂡", "Aces have powers", "♣ a credit · ♠ the next player drinks · ♥ treat yourself · ♦ the dealer "
                                     "drinks."),
            ("🔟", "Split 10s with honor", "Unsuited 10s must be split. The cautious 20 is off the menu."),
            ("😈", "Devil's Hand · Lucky Sevens", "A third 6 on the table makes someone drink; a third 7 hands "
                                                 "out a credit."),
            ("🏁", "Milestones", f"First to every {MILESTONE_STEP} sips hands out {MILESTONE_HANDOUT_SIPS}. Back-"
                                "to-back winners get called out."),
        ]), src + " · Full rules: docs/Rules.md")

    # 5 — Side games
    add("Side games", "Between hands, four side games keep the whole table in it, dealer included",
        cards([
            ("🎯", "Dealer bust vote", "Bet the dealer busts. Right: a credit plus a handout. Wrong: a sip."),
            ("🎰", "Dealer Lottery", "Dealer lands a paired 18 or 20? Stake 0–5 on a split redeal: busts pay out, "
                                    "a clean redeal costs you."),
            ("👉", "Targeted Drinking", "The table votes someone onto the spot: call bust or stand on a mini-hand "
                                       "until three in a row."),
            ("🃏", "Wild Card", "Tap the logo for a surprise: a sip for you, for someone random, or a Targeted "
                               "round."),
        ], cols=4) + sowhat("Every side game is a switch in 📜 House rules: keep the ones your table loves, drop the "
                            "rest, even mid-game."))

    # 6 — Your table
    ladder = "".join(f'<div class="rung"><b>{name.title()}</b><span>{preset_n[name]} rules · {blurb}</span></div>'
                     for name, blurb in (("starter", "the essentials"), ("standard", "the classic night"),
                                         ("full", "everything on")))
    add("Your table", f"Every table sets its own game: {n_rules} rules, three presets, and a drink rate for each "
                      "seat",
        f'<div class="row2"><div><h3>House rules your way</h3><div class="ladder">{ladder}</div>'
        '<ul class="ticks"><li>Start on a preset, then add rules one at a time</li>'
        '<li>Switch any rule off, even mid-game</li>'
        '<li>Players suggest changes; the table can vote them in</li></ul></div>'
        '<div><h3>Fair for every drink</h3><ul class="ticks">'
        '<li><b>Drink Rate</b>: each seat picks its factor, from wine at 0.6× or a cocktail at 0.4× up to a 1.5× '
        'booster</li>'
        '<li><b>Easy Mode</b>: halve everyone\'s sips with one switch</li>'
        '<li><b>Big tables</b>: sips halve by themselves at 4+ players</li>'
        '<li><b>Normal mode</b>: the same game with chips, no drinking at all</li></ul></div></div>')

    # 7 — Play anywhere
    add("Play anywhere", "One room code gets everyone in, around one table or across the country",
        cards([
            ("📱", "Digital", "Phones and laptops, no install: add it to your home screen for an app feel. Bots "
                             "fill empty seats and can play in the style of real players."),
            ("🂠", "Referee", "Play with a real deck; the app is the scorekeeper and rule book."),
            ("⌨️", "Terminal", "Solo or local multiplayer from the command line, for the nerds."),
        ]) + sowhat("Share the room code or its QR code, and anyone can join from their own phone. Spectators can "
                    "watch without a seat."))

    # 8 — A typical night (model)
    end, spread = m * NIGHT_ROUNDS, BAND_Z * sd * math.sqrt(NIGHT_ROUNDS)
    first = MILESTONE_STEP / m if m else 0
    kpis = [(f"{m:.1f}", "sips per seat per round, on average"),
            (f"~{end:.0f}", f"sips for a typical seat over {NIGHT_ROUNDS} rounds"),
            (f"{end - spread:.0f}–{end + spread:.0f}", "where 80% of seats finish"),
            (f"R{first:.0f}", f"when a typical seat reaches the first {MILESTONE_STEP}-sip milestone")]
    add("A typical night",
        f"A typical {NIGHT_ROUNDS}-round night: about {m:.1f} sips per seat per round, and the first milestone "
        f"lands around round {first:.0f}",
        f'<div class="row-model"><div><h3>Modelled running total for one seat</h3>'
        f'{svg_typical_night(m, sd, t)}</div><div class="kpi-stack">'
        + "".join(f'<div class="kpi"><b>{v}</b><span>{s}</span></div>' for v, s in kpis)
        + "</div></div>"
        + sowhat("Steady, not a sprint: the gap between the heaviest and lightest seat grows with the square root of "
                 "the rounds played, not with the rounds themselves. Easy Mode, Drink Rate and 4+ player tables all "
                 "bring the line down.", wide=True),
        src + f" · Model: average and spread of {sr['n']:,} logged seat-rounds (net sips, as played); band = average "
              f"± {BAND_Z} × spread × √rounds")

    # 9 — Balance
    rows = ""
    for key in ("2p_1d", "3p_1d", "3p_2d", "4p_2d", "4p_3d"):
        if key in bench:
            c = bench[key]["config"]
            rows += (f"<tr><td>{c['num_players']} players · {c['num_decks']} deck{'s' if c['num_decks'] > 1 else ''}"
                     f"</td><td>{bench[key]['avg_sips_per_round'] / c['num_players']:.1f}</td>"
                     f"<td>{sips_per_hand(bench[key]):.1f}</td>"
                     f"<td>{bench[key]['dealer_bust_pct']:.0f}%</td><td>{bench[key]['blackjack_rate_pct']:.1f}%</td>"
                     f"<td>{bench[key]['win_rate_pct']:.0f}%</td></tr>")
    ref = bench.get("3p_1d")
    body = ""
    if ref:
        cats = collections.Counter()
        for rule, v in ref["sips_per_round_by_rule"].items():
            if v > 0:
                cats[_category(rule)] += v
        tot = sum(cats.values()) or 1
        order = [c for c, _ in CATEGORIES if cats[c] > 0]
        order.sort(key=lambda c: -cats[c])
        bars = hbars([(c, cats[c] / tot * 100, t["bar"] if i == 0 else t["bar2"]) for i, c in enumerate(order[:7])],
                     None, lambda v: f"{v:.0f}%", 140, 220)
        sims = ref["config"]["num_rounds"]
        real3 = sr["by_size"].get(3)
        body = (f'<div class="row2"><div><h3>Simulator, per table size</h3><table class="t bal"><tr><th>Table</th>'
                '<th>Sips / seat / round</th><th>Sips / hand</th><th>Dealer busts</th><th>Blackjacks</th>'
                f'<th>Hands won</th></tr>{rows}'
                f'</table></div><div><h3>Where the sips come from <small>(3 players, 1 deck)</small></h3>{bars}</div>'
                '</div>'
                + sowhat(f"Every table size is checked over {sims:,} simulated rounds, and the simulator matches real "
                         f"tables: {ref['avg_sips_per_round'] / 3:.1f} sips per seat per round for 3 players, against "
                         f"{real3:.1f} in the logged 3-player rounds. Other players' wins, not your own losses, "
                         "drive most of the drinking." if real3 else
                         f"Every table size is checked over {sims:,} simulated rounds."))
        add("Balance", f"Balanced over {sims:,} simulated rounds per table size: more players, more sips each, but "
                       "never a race to the floor",
            body, src + " · Simulator: scripts/simulation.py, basic-strategy bots, 2 hands per player · Sips / "
                        "hand: per hand dealt, without side games and milestones")

    # 10 — The recap
    contents = [("Executive summary", "the night's six takeaways"), ("The race", "every lead change, round by round"),
                ("League table and sip bridge", "who drank what, and what credits saved"),
                ("Drivers and tempo", "which rules drove the bill, and when it peaked"),
                ("Decision quality and the house", "who played by the book, who dealt the toughest"),
                ("Player pages and awards", "a page for every player, with their awards"),
                ("Table setup", "house rules and Drink Rate, for the record")]
    add("After the game", "Every night ends with a recap deck: who won, why, and who should never split again",
        '<div class="row2"><div><h3>What the recap covers</h3><table class="t recap">'
        + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in contents) + '</table></div><div>'
        + sowhat("One tap on “📊 Download Recap (PDF)” in the session summary, and the group chat has something to "
                 "argue about until the next game.", wide=False)
        + '<p class="note">About 15 pages plus one per player, in the same look as the app.</p></div></div>')

    # 11 — Responsible
    add("Play responsibly", "Built for good nights, not regrets",
        cards([
            ("🔞", "18+ only", "An age gate on every device, and a link to the Terms & Disclaimer."),
            ("🍷", "Drink less, still play", "Drink Rate discounts and Easy Mode cut the sips without leaving the "
                                            "game."),
            ("🥤", "Or don't drink at all", "Normal mode plays the same blackjack with chips instead of sips."),
            ("💧", "Know your limits", "Water counts. Taxis count. Never drink and drive."),
        ], cols=4) + sowhat("The game is about the cards and the company; the sips are just how you keep score."))

    # 12 — Call to action
    pages.append(f'''<section class="slide thanks">
      <div class="cv-band"></div>
      <div class="logo cv-logo"></div>
      <div class="ty-title">Deal yourself in</div>
      <div class="ty-sub">Free, in your browser, no sign-up. Grab some friends and a drink of your choice.</div>
      <div class="cta">
        <div class="cta-box"><div class="qr">{qr_svg(PLAY_URL)}</div><div><b>{txt("▶ Play now")}</b>
          <span><a href="{PLAY_URL}">{PLAY_URL.removeprefix("https://")}</a></span>
          <span>Rules: <a href="{REPO_URL}/blob/main/docs/Rules.md">docs/Rules.md</a></span>
          <span>Code: <a href="{REPO_URL}">github.com/robert-rjm/Black-Out-Jack</a></span></div></div>
        <div class="cta-box small"><div class="qr">{qr_svg(TIP_URL)}</div><div><b>{txt("🍺 Buy us a beer")}</b>
          <span>A free hobby project. Tips keep the cards coming:
          <a href="{TIP_URL}">{TIP_URL.removeprefix("https://")}</a></span></div></div>
      </div>
      <div class="cv-foot">18+ only · know your limits · never drink and drive · CC BY-NC-SA 4.0</div>
    </section>''')

    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{APP_NAME} pitch deck</title>"
            f"<style>{logo_css(inline=True)}{CSS}{PITCH_CSS}{FINANCE_CSS if fin else ''}</style></head>"
            f"<body>{''.join(pages)}</body></html>")


PITCH_CSS = """
.body { padding-top: 30px; }
.cards { display: grid; gap: 20px; }
.cards.c3 { grid-template-columns: repeat(3, 1fr); }
.cards.c4 { grid-template-columns: repeat(4, 1fr); }
.card { background: #1a1d27; border: 1px solid #2e3247; border-radius: 12px; padding: 28px; min-height: 290px; }
.cards.c3 .card { min-height: 220px; }
.cards + .sowhat { margin-top: 30px; }
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
.row-model { display: grid; grid-template-columns: 660px 1fr; gap: 50px; margin-bottom: 18px; }
.kpi-stack { display: flex; flex-direction: column; gap: 18px; padding-top: 6px; }
.kpi-stack .kpi b { font-size: 34px; }
.kpi-stack .kpi span { font-size: 14px; }
.t.bal td, .t.bal th, .t.recap td { padding: 11px 10px; font-size: 15.5px; }
.t.bal th { font-size: 11.5px; }
.t.recap td:first-child { font-weight: 700; width: 280px; }
.hbars { font-size: 14.5px; }
.hb { margin-bottom: 12px; }
.hbt { height: 24px; }
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

# Report style: white pages, navy ink, hairlines, square corners, numbered blocks, Arial
FINANCE_CSS = """
body, .slide { background: #ffffff; color: #0b2545; font-family: Arial, Helvetica, sans-serif; }
.tracker { color: #1f4e79; }
h1 { border-bottom: 2px solid #0b2545; color: #0b2545; max-width: 1040px; }
h3 { color: #1f4e79; }
footer { color: #5b6475; border-top-color: #d5dae3; }
.brand { color: #0b2545; }
.cover::after, .thanks::after { content: ""; position: absolute; right: 0; top: 0; bottom: 0; width: 470px;
  background: #0b2545; }
.card, .step, .rung, .cta-box { background: #ffffff; border: 1px solid #d5dae3; border-top: 3px solid #0b2545;
  border-radius: 0; }
.card .em { font-size: 15px; font-weight: 700; color: #1f4e79; letter-spacing: .08em; }
.card .ct { font-size: 21px; margin-top: 10px; }
.card .cb, .step span, .rung span, .cta-box span, .kpi span, .note { color: #4a5568; }
.step i { background: #0b2545; color: #ffffff; border-radius: 0; }
.rung:nth-child(2), .rung:nth-child(3) { border-color: #d5dae3; border-top-color: #0b2545; }
.rung:nth-child(3) { background: #f2f4f7; }
.ticks li::before { content: "■"; color: #1f4e79; font-size: 11px; top: 5px; }
.sowhat { background: #f2f4f7; border: 0; border-left: 4px solid #0b2545; border-radius: 0; color: #0b2545; }
.sowhat b { color: #1f4e79; }
.kpi { border-top-color: #0b2545; }
.t th { color: #0b2545; border-bottom-color: #0b2545; }
.t td { border-bottom-color: #d5dae3; }
.hbt { background: #eef1f5; border-radius: 0; }
.hbf { border-radius: 0; }
.cover, .thanks { background: #ffffff; color: #0b2545; }
.cv-band { background: #0b2545; width: 14px; }
.cv-kicker { color: #1f4e79; }
.cv-sub, .cv-kpis span, .cv-foot, .ty-sub { color: #4a5568; }
.cv-logo { width: 330px; height: 330px; right: 70px; top: 195px; z-index: 1; }
.cta-box b { color: #0b2545; }
.cta-box a { color: #1f4e79; }
.cta-box .qr { border: 1px solid #d5dae3; border-radius: 0; }
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=os.path.join(_ROOT, "data", "decisions"))
    ap.add_argument("--theme", choices=("app", "finance", "both"), default="both")
    ap.add_argument("--out-dir", default=os.path.join(_ROOT, "docs"))
    ap.add_argument("--html", action="store_true", help="also keep the HTML next to each PDF")
    args = ap.parse_args()

    sr, bench = seat_rounds(args.dir), benchmarks()
    os.makedirs(args.out_dir, exist_ok=True)
    for theme in (("app", "finance") if args.theme == "both" else (args.theme,)):
        pdf = os.path.join(args.out_dir, THEMES[theme]["out"])
        html_path = (os.path.splitext(pdf)[0] + ".html" if args.html
                     else os.path.join(tempfile.mkdtemp(), f"pitch_{theme}.html"))
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build(theme, sr, bench))
        print_pdf(html_path, pdf)
        print(f"Wrote {pdf}")


if __name__ == "__main__":
    main()
