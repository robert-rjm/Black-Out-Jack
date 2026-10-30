"""
app/services/recap_deck.py
===========================
The session recap deck: a slide-style story of one session (race, league
table, sip bridge, drivers, tempo, decision quality, the house, side games,
player comparables, awards, definitions, thank-you), built as one HTML page
of 1280×720 slides in the app's colours.

    analyse(rows, decisions, lottery, day)  -> dict of every number the deck uses
    build_html(a, logo_css)                 -> the deck as a self-contained HTML page

Inputs are the same rows the exports carry: session.drinks.csv_rows,
session._decision_log and session._dealer_lottery_decision_log (or those
sheets read back from the xlsx exports). Two consumers:

  - GET /recap_html (app/routes/reports.py): the browser turns each slide into
    a PDF page (static/js/ui/recap-pdf.js, html2canvas + jsPDF).
  - scripts/build_recap_deck.py: prints the same HTML to a vector PDF through
    a local headless Edge/Chrome, from two saved exports.

Each content slide has a full-sentence title (the takeaway), a section
tracker, one chart or table, a "So what" box and a source line. Titles and
takeaways are worded from the data, so they read correctly for any session.
"""

import base64
import collections
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.qr import qr_svg
from app.config import TIP_URL
from engine.rules_registry import GROUPS, RULES

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP_NAME = "Black(Out)Jack"
_TZ = ZoneInfo("Europe/Zurich")

SIPS_PER_BEER = 15          # illustrative: ~15 sips per 0.5 l
# App palette (static/css/main.css :root) — the deck is dark like the app
BG, SURFACE, BORDER, TEXT, MUTED = "#0f1117", "#1a1d27", "#2e3247", "#e8eaf0", "#9095ab"
BLUE, GREEN, RED, YELLOW, PURPLE, ON_FILL = "#4f8ef7", "#3ecf6e", "#e05c5c", "#f5c842", "#a78bfa", "#0f1117"
AMBER = "#f39a1e"           # logo beer
IDLE = "#3a4160"            # unhighlighted bars
PLAYER_COLOURS = [BLUE, AMBER, PURPLE, "#2dd4bf", "#f472b6", YELLOW]

# Rule -> driver category (sips you drink, grouped by *why* you drink them)
CATEGORIES = [
    ("Others' wins",       ("Blackjack bonus", "Doubled win", "Split win", "Suited winning", "5+ card win")),
    ("Own losing hands",   ("Net hand losses", "Lost doubled", "Lost suited")),
    ("Sweeps",             ("Other-player sweep", "All-hands sweep")),
    ("Bust votes",         ("Bust vote wrong", "Bust vote handout")),
    ("Dealer Lottery",     ("Dealer Lottery",)),
    ("Card events",        ("Ace dealt", "Four Aces", "Devil's Hand", "Dealer suited")),
    ("Dealer duty",        ("Hard Dealer Switch",)),
    ("Milestones",         ("Milestone", "Worst average")),
    ("Wild Card & other",  ("",)),
]


def _category(rule: str) -> str:
    for name, keys in CATEGORIES:
        if any(rule.startswith(k) for k in keys):
            return name
    return CATEGORIES[-1][0]


def esc(s) -> str:
    return html.escape(str(s))


def pct(n, d, digits=0) -> str:
    return f"{n / d * 100:.{digits}f}%" if d else "–"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _row_rate(r) -> float:
    """The seat's drink factor on a drink row. Rows from before the rate
    column existed infer it from sips vs sips_raw (1.0 when they match)."""
    if r.get("rate") is not None:
        return float(r["rate"])
    raw = r.get("sips_raw")
    return round(r["sips"] / raw, 1) if raw and raw != r["sips"] else 1.0


def analyse(rows, decisions, lottery, day, setup=None) -> dict:
    """setup (optional, live sessions only): {"rules": RuleSet, "wager",
    "hands", "easy_mode", "rate_rounds"}; the xlsx exports carry none of it."""
    a: dict = {"day": day, "setup": setup or {}}
    rows = [{**r, "round": max(r["round"] or 1, 1)} for r in rows]
    players = list(dict.fromkeys(r["player"] for r in rows))
    n_rounds = max(r["round"] for r in rows)
    rounds = range(1, n_rounds + 1)
    a.update(players=players, n_rounds=n_rounds, colour={p: PLAYER_COLOURS[i % 6] for i, p in enumerate(players)})
    a["session_id"] = decisions[0]["session_id"] if decisions else "–"

    ts = [d["timestamp"] for d in decisions]
    if ts:
        a["start"] = datetime.fromtimestamp(min(ts), _TZ)
        a["end"] = datetime.fromtimestamp(max(ts), _TZ)
        a["minutes"] = (max(ts) - min(ts)) / 60
    else:
        a["start"] = a["end"] = None
        a["minutes"] = 0

    # Totals / per round
    per_rp = collections.defaultdict(lambda: collections.Counter())    # round -> player -> sips
    total = collections.Counter()
    gross = collections.Counter()
    dealer_sips = collections.Counter()
    credits = collections.Counter()
    cat = collections.defaultdict(collections.Counter)                # category -> player -> gross sips
    for r in rows:
        per_rp[r["round"]][r["player"]] += r["sips"]
        total[r["player"]] += r["sips"]
        if r["role"] == "dealer":
            dealer_sips[r["player"]] += r["sips"]
        if r["sips"] > 0:
            gross[r["player"]] += r["sips"]
            cat[_category(r["rule"])][r["player"]] += r["sips"]
        else:
            credits[r["rule"]] += r["sips"]
    a.update(total=total, gross=gross, dealer_sips=dealer_sips, credits=credits, cat=cat)
    a["net"] = sum(total.values())
    a["gross_all"] = sum(gross.values())
    a["round_tot"] = [sum(per_rp[i].values()) for i in rounds]

    # Rounds present (decision log is the attendance record)
    present = {p: {d["round"] for d in decisions if d["player"] == p} for p in players}
    for p in players:                         # fall back to drink rows
        if not present[p]:
            present[p] = {r["round"] for r in rows if r["player"] == p}
    a["present"] = {p: len(present[p]) for p in players}
    a["joined"] = {p: min(present[p]) for p in players}
    a["per_round"] = {p: total[p] / a["present"][p] for p in players}
    a["clean"] = {p: sum(1 for i in present[p] if per_rp[i][p] <= 0) for p in players}
    a["best_round"] = {p: max(((per_rp[i][p], i) for i in rounds), default=(0, 0)) for p in players}

    # Cumulative race + lead changes
    cum = {p: [0] for p in players}
    run, lead_rounds = collections.Counter(), collections.Counter()
    leader, changes = None, []
    for i in rounds:
        for p in players:
            run[p] += per_rp[i][p]
            cum[p].append(run[p])
        top = max(players, key=lambda p: run[p])
        lead_rounds[top] += 1
        if top != leader:
            changes.append((i, top))
            leader = top
    a.update(cum=cum, changes=changes, lead_rounds=lead_rounds)

    # Easy Mode (4-player halving) window
    easy = sorted({r["round"] for r in rows if r["rule"] == "Easy mode halving"})
    a["easy_from"] = easy[0] if easy else None
    # Who brought the table to 4 (halving starts by itself), if anyone
    a["easy_joiners"] = [p for p in players if a["easy_from"] and 1 < a["easy_from"] == a["joined"][p]]
    a["easy_label"] = "4 players · Easy Mode halves sips" if a["easy_joiners"] else "Easy Mode halves sips"

    # Dealers by round
    a["dealer_of"] = {}
    for r in rows:
        a["dealer_of"].setdefault(r["round"], r["dealer"])

    # Hands (one row per hand: last decision of each hand carries the result)
    hands = {}
    for d in decisions:
        hands[(d["round"], d["player"], d["hand_index"])] = d
    hs = collections.defaultdict(collections.Counter)
    house = collections.defaultdict(collections.Counter)
    for (rd, p, _), d in hands.items():
        hs[p][d["hand_result"]] += 1
        house[d["dealer_name"]][d["hand_result"]] += 1
    a["hands"], a["house"] = hs, house

    # Basic strategy adherence (decision level)
    bs = {}
    fol_res, dev_res = collections.Counter(), collections.Counter()
    dev_kinds = collections.Counter()
    bs_res = {}
    for p in players:
        dd = [d for d in decisions if d["player"] == p and not d["is_npc"] and d["basic_strategy_action"]]
        f = sum(d["action_taken"] == d["basic_strategy_action"] for d in dd)
        bs[p] = (f, len(dd))
        bs_res[p] = (collections.Counter(), collections.Counter())
        for d in dd:
            book = d["action_taken"] == d["basic_strategy_action"]
            (fol_res if book else dev_res)[d["hand_result"]] += 1
            bs_res[p][0 if book else 1][d["hand_result"]] += 1
            if not book:
                dev_kinds[(d["action_taken"], d["basic_strategy_action"])] += 1
    a.update(bs=bs, bs_res=bs_res, fol_res=fol_res, dev_res=dev_res, dev_kinds=dev_kinds)

    # Side games
    rule_tot = collections.Counter()
    rule_cnt = collections.Counter()
    for r in rows:
        rule_tot[r["rule"]] += r["sips"]
        rule_cnt[r["rule"]] += 1
    a["rule_tot"], a["rule_cnt"] = rule_tot, rule_cnt
    a["lottery"] = lottery
    a["wild"] = collections.Counter(r["player"] for r in rows if r["rule"] == "Wild Card")

    # Per player: what they drank for, and how they played
    a["rule_by_player"] = {p: collections.Counter() for p in players}
    for r in rows:
        if r["sips"] > 0:
            a["rule_by_player"][r["player"]][r["rule"]] += r["sips"]
    doubled, splits = collections.defaultdict(collections.Counter), collections.Counter()
    acts = collections.defaultdict(set)
    for d in decisions:
        acts[(d["round"], d["player"], d["hand_index"])].add(d["action_taken"])
        if d["action_taken"] == "sp":
            splits[d["player"]] += 1
    for key, d in hands.items():
        if "d" in acts[key]:
            doubled[key[1]]["hands"] += 1
            doubled[key[1]]["won"] += d["hand_result"] == "win"
    a["doubled"], a["splits"] = doubled, splits
    a["decks"] = max((d.get("decks_in_play") or 0 for d in decisions), default=0)

    # Drink Rate (boosters above 1.0×, discounts below): sips before the factor,
    # and how many rounds each seat played at each factor
    a["raw_total"] = collections.Counter()
    raw_gross = collections.Counter()
    seat_rate = collections.defaultdict(dict)                         # player -> round -> factor
    for r in rows:
        raw = r.get("sips_raw", r["sips"])
        a["raw_total"][r["player"]] += raw
        if raw > 0:
            raw_gross[r["player"]] += raw
        f = _row_rate(r)
        prev = seat_rate[r["player"]].get(r["round"], 1.0)
        # Events that skip boosters log 1.0, so the factor furthest from 1.0 is the seat's
        seat_rate[r["player"]][r["round"]] = f if abs(f - 1) > abs(prev - 1) else prev
    live_rr = (setup or {}).get("rate_rounds") or {}
    factor_rounds = {}
    for p in players:
        if live_rr.get(p):
            factor_rounds[p] = collections.Counter({float(f): n for f, n in live_rr[p].items()})
        else:
            factor_rounds[p] = collections.Counter(seat_rate[p].get(i, 1.0) for i in present[p])
    a["factor_rounds"] = factor_rounds
    a["avg_factor"] = {p: (sum(f * c for f, c in fr.items()) / sum(fr.values()) if fr else 1.0)
                       for p, fr in factor_rounds.items()}
    a["rate_used"] = any(f != 1.0 for fr in factor_rounds.values() for f in fr if fr[f])
    a["raw_gross_all"] = sum(raw_gross.values())
    return a


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def _nice_max(v: float) -> tuple[float, float]:
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if v / step <= 6:
            return (int(v / step) + 1) * step, step
    return v, v / 5


def svg_race(a, w=820, h=430) -> str:
    L, R, T, B = 48, 120, 16, 40
    n = a["n_rounds"]
    ymax, step = _nice_max(max(max(max(c) for c in a["cum"].values()), 1))
    def x(i): return L + (w - L - R) * i / n
    def y(v): return T + (h - T - B) * (1 - v / ymax)
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    if a["easy_from"]:
        x0 = x(a["easy_from"] - 1)
        out.append(f'<rect x="{x0:.1f}" y="{T}" width="{x(n) - x0:.1f}" height="{h - T - B}" fill="{SURFACE}"/>')
        out.append(f'<text x="{x0 + 8:.1f}" y="{T + 16}" class="ax">{a["easy_label"]} →</text>')
    v = 0
    while v <= ymax:
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{BORDER}"/>'
                   f'<text x="{L - 8}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{v:g}</text>')
        v += step
    for i in range(0, n + 1, 5 if n > 20 else 2):
        out.append(f'<text x="{x(i):.1f}" y="{h - B + 18}" class="ax" text-anchor="middle">{i}</text>')
    out.append(f'<text x="{(L + w - R) / 2}" y="{h - 4}" class="ax" text-anchor="middle">Round</text>')
    for p in a["players"]:
        start = a["joined"][p] - 1
        pts = " ".join(f"{x(i):.1f},{y(a['cum'][p][i]):.1f}" for i in range(start, n + 1))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{a["colour"][p]}" stroke-width="2.5" '
                   f'stroke-linejoin="round"/>')
    # Lead-change markers
    for k, (rd, p) in enumerate(a["changes"][1:], 1):
        cx, cy = x(rd), y(a["cum"][p][rd])
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="9" fill="{YELLOW}"/>'
                   f'<text x="{cx:.1f}" y="{cy + 4:.1f}" text-anchor="middle" font-size="11" font-weight="700" '
                   f'fill="{ON_FILL}">{k}</text>')
    # End labels, spread so they don't collide
    ends = sorted(a["players"], key=lambda p: -a["cum"][p][n])
    last_y = -99
    for p in ends:
        ly = max(y(a["cum"][p][n]) + 4, last_y + 17)
        last_y = ly
        out.append(f'<text x="{w - R + 8}" y="{ly:.1f}" font-size="13" font-weight="700" fill="{a["colour"][p]}">'
                   f'{esc(p)} <tspan font-weight="400" fill="{TEXT}">{a["cum"][p][n]}</tspan></text>')
    out.append("</svg>")
    return "".join(out)


def svg_player_race(a, p, w=600, h=220) -> str:
    """One player's running total against a typical seat (each round, the
    average of the players seated that round, added up) and, faintly,
    everyone else."""
    L, R, T, B = 40, 124, 12, 30
    n = a["n_rounds"]
    avg = [0.0]
    for i in range(1, n + 1):
        seated = [q for q in a["players"] if a["joined"][q] <= i]
        avg.append(avg[-1] + sum(a["cum"][q][i] - a["cum"][q][i - 1] for q in seated) / max(len(seated), 1))
    ymax, step = _nice_max(max(max(max(c) for c in a["cum"].values()), 1))
    def x(i): return L + (w - L - R) * i / n
    def y(v): return T + (h - T - B) * (1 - v / ymax)
    def line(vals, start, **attrs):
        pts = " ".join(f"{x(i):.1f},{y(vals[i]):.1f}" for i in range(start, n + 1))
        extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
        return f'<polyline points="{pts}" fill="none" {extra}/>'
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    v = 0
    while v <= ymax:
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{BORDER}"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{v:g}</text>')
        v += step
    for i in range(0, n + 1, 10 if n > 30 else 5 if n > 10 else 2):
        out.append(f'<text x="{x(i):.1f}" y="{h - B + 16}" class="ax" text-anchor="middle">{i}</text>')
    for q in a["players"]:
        if q != p:
            out.append(line(a["cum"][q], a["joined"][q] - 1, stroke=IDLE, stroke_width="1.5"))
    out.append(line(avg, 0, stroke=MUTED, stroke_width="2", stroke_dasharray="5,4"))
    out.append(line(a["cum"][p], a["joined"][p] - 1, stroke=a["colour"][p], stroke_width="3", stroke_linejoin="round"))
    ends = sorted([(a["cum"][p][n], esc(p), a["colour"][p]), (round(avg[n]), "Typical seat", MUTED)],
                  key=lambda e: -e[0])
    last_y = -99
    for val, label, colour in ends:
        ly = max(y(val) + 4, last_y + 16)
        last_y = ly
        out.append(f'<text x="{w - R + 8}" y="{ly:.1f}" font-size="12.5" font-weight="700" fill="{colour}">'
                   f'{label} <tspan font-weight="400" fill="{TEXT}">{val:g}</tspan></text>')
    out.append("</svg>")
    return "".join(out)


def svg_waterfall(steps, w=820, h=420) -> str:
    """steps: [(label, value, kind)] kind in total|delta. A delta that adds
    sips (boosters) is red, one that removes them (credits) green."""
    L, R, T, B = 20, 20, 30, 56
    run, bars = 0, []
    for label, v, kind in steps:
        if kind == "total":
            bars.append((label, 0, v, kind, v))
            run = v
        else:
            bars.append((label, min(run, run + v), max(run, run + v), kind, v))
            run += v
    ymax = max(max(b[2] for b in bars), 1) * 1.08
    bw = (w - L - R) / len(bars)
    def y(v): return T + (h - T - B) * (1 - v / ymax)
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
           f'<line x1="{L}" x2="{w - R}" y1="{y(0)}" y2="{y(0)}" stroke="{MUTED}"/>']
    run = 0
    for i, (label, lo, hi, kind, v) in enumerate(bars):
        x0 = L + i * bw + bw * 0.18
        colour = BLUE if kind == "total" else RED if v > 0 else GREEN
        out.append(f'<rect x="{x0:.1f}" y="{y(hi):.1f}" width="{bw * 0.64:.1f}" height="{y(lo) - y(hi):.1f}" '
                   f'fill="{colour}"/>')
        txt = f"{v:,.0f}" if kind == "total" else f"+{v:,.0f}" if v > 0 else f"–{-v:,.0f}"
        out.append(f'<text x="{x0 + bw * 0.32:.1f}" y="{y(hi) - 7:.1f}" text-anchor="middle" font-size="13" '
                   f'font-weight="700" fill="{TEXT}">{txt}</text>')
        run = v if kind == "total" else run + v
        if i < len(bars) - 1:
            ly = y(run)
            out.append(f'<line x1="{x0 + bw * 0.64:.1f}" x2="{x0 + bw:.1f}" y1="{ly:.1f}" y2="{ly:.1f}" '
                       f'stroke="{MUTED}" stroke-dasharray="3,3"/>')
        words = label.split(" ")
        mid = (len(words) + 1) // 2
        for j, line in enumerate([" ".join(words[:mid]), " ".join(words[mid:])]):
            out.append(f'<text x="{x0 + bw * 0.32:.1f}" y="{h - B + 18 + j * 14}" text-anchor="middle" '
                       f'class="ax">{esc(line)}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_columns(a, w=1180, h=330) -> str:
    L, R, T, B = 40, 10, 24, 36
    vals = a["round_tot"]
    n = len(vals)
    ymax, step = _nice_max(max(max(vals), 1))
    bw = (w - L - R) / n
    def y(v): return T + (h - T - B) * (1 - max(v, 0) / ymax)
    top3 = sorted(range(n), key=lambda i: -vals[i])[:3]
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}">']
    if a["easy_from"]:
        x0 = L + (a["easy_from"] - 1) * bw
        out.append(f'<rect x="{x0:.1f}" y="{T}" width="{w - R - x0:.1f}" height="{h - T - B}" fill="{SURFACE}"/>'
                   f'<text x="{x0 + 6:.1f}" y="{T + 14}" class="ax">{a["easy_label"]}</text>')
    v = 0
    while v <= ymax:
        out.append(f'<line x1="{L}" x2="{w - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{BORDER}"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" class="ax" text-anchor="end">{v:g}</text>')
        v += step
    for i, val in enumerate(vals):
        x0 = L + i * bw + bw * 0.15
        hot = i in top3
        out.append(f'<rect x="{x0:.1f}" y="{y(val):.1f}" width="{bw * 0.7:.1f}" height="{y(0) - y(val):.1f}" '
                   f'fill="{YELLOW if hot else IDLE}"/>')
        if hot:
            out.append(f'<text x="{x0 + bw * 0.35:.1f}" y="{y(val) - 5:.1f}" text-anchor="middle" font-size="12" '
                       f'font-weight="700" fill="{YELLOW}">{val}</text>')
        if (i + 1) % 5 == 0 or i == 0:
            out.append(f'<text x="{x0 + bw * 0.35:.1f}" y="{h - B + 16}" text-anchor="middle" '
                       f'class="ax">{i + 1}</text>')
    # 5-round rolling average
    pts = []
    for i in range(n):
        win = vals[max(0, i - 4): i + 1]
        pts.append(f"{L + i * bw + bw / 2:.1f},{y(sum(win) / len(win)):.1f}")
    out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{BLUE}" stroke-width="2.5"/>')
    out.append("</svg>")
    return "".join(out)


def hbars(items, maxv=None, fmt=str, label_w=120, bar_w=360, ref=None) -> str:
    """items: [(label, value, colour)] → HTML horizontal bars."""
    maxv = maxv or max((v for _, v, _ in items), default=0) or 1
    out = ['<div class="hbars">']
    for label, v, colour in items:
        out.append(f'<div class="hb"><span class="hbl" style="width:{label_w}px">{esc(label)}</span>'
                   f'<span class="hbt" style="width:{bar_w}px">'
                   f'<span class="hbf" style="width:{max(v, 0) / maxv * 100:.1f}%;background:{colour}"></span>'
                   + (f'<span class="hbref" style="left:{ref / maxv * 100:.1f}%"></span>' if ref is not None else "")
                   + f'</span><span class="hbv">{fmt(v)}</span></div>')
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------

def slide(tracker, title, body, source, page) -> str:
    return (f'<section class="slide"><div class="brand"><div class="logo"></div>{APP_NAME}</div>'
            f'<div class="tracker">{esc(tracker)}</div>'
            f'<h1>{title}</h1><div class="body">{body}</div>'
            f'<footer><span>{source}</span><span>{APP_NAME} · Session recap · {page}</span></footer></section>')


_SUITS = {"Spades": "♠", "Hearts": "♥", "Diamonds": "♦", "Clubs": "♣"}


def _short_rule(rule: str) -> str:
    """Rule label short enough for a bar label: "Ace dealt: Ace of Spades
    (dealer hand)" -> "A♠ dealt (dealer hand)", "(immunity break)" dropped."""
    if rule.startswith("Ace dealt: Ace of "):
        suit, _, rest = rule.removeprefix("Ace dealt: Ace of ").partition(" ")
        return f"A{_SUITS.get(suit, suit)} dealt {rest}".strip()
    rule = rule.replace(" (immunity break)", "")
    return rule if len(rule) <= 27 else rule[:26].rstrip() + "…"


def _ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def _player_slide(a, p, rank, n_players, table_pr, table_mix, table_adh, adh, house, factor, awards, src, page):
    """One player's page: running total vs the table, where their sips came
    from, headline numbers, how they played, their awards and a takeaway."""
    name, colour = esc(p), a["colour"][p]
    pr, gross = a["per_round"][p], a["gross"][p]
    diff = pr - table_pr
    title = (f"{name} finished {_ordinal(rank)} of {n_players} with {a['total'][p]} net sips: {pr:.2f} per round, "
             f"{abs(diff):.2f} {'above' if diff >= 0 else 'below'} the table average")
    top = a["rule_by_player"][p].most_common(6)
    bars = hbars([(_short_rule(r), v, colour if i == 0 else "#35548f") for i, (r, v) in enumerate(top)],
                 None, lambda v: f"{v} · {pct(v, gross)}", 170, 190)
    worst, worst_r = a["best_round"][p]
    kpis = [(f"{_ordinal(rank)}", f"of {n_players} by net sips"), (a["total"][p], "net sips"),
            (f"{pr:.2f}", "sips per round played"),
            (a["present"][p], "rounds played" + (f" (joined R{a['joined'][p]})" if a["joined"][p] > 1 else "")),
            (a["clean"][p], "clean rounds"), (worst, f"sips in round {worst_r}, the worst")]
    hs = a["hands"][p]
    n_hands = sum(hs.values())
    stats = []
    if n_hands:
        stats.append(("Hands won–lost–push", f"{hs['win']}–{hs['loss']}–{hs['push']} ({hs['win'] / n_hands:.0%} won)"))
        dh = a["doubled"][p]
        stats.append(("Doubles won", f"{dh['won']} of {dh['hands']}" if dh["hands"] else "none doubled"))
        stats.append(("Splits", a["splits"][p] or "none"))
    if p in adh:
        stats.append(("Basic-strategy match", f"{adh[p]:.0%} (table {table_adh:.0%})"))
    if p in house:
        c = house[p]
        stats.append(("As dealer", f"house won {c['loss'] / sum(c.values()):.0%} of {sum(c.values())} hands · "
                                   f"{a['dealer_sips'][p]} sips"))
    if a["rate_used"]:
        delta = a["total"][p] - a["raw_total"][p]
        stats.append(("Drink Rate", (f"{factor} ({delta:+} sips)" if delta else factor) if factor
                      else "1.0× all night"))

    cat_p = max((c for c, _ in CATEGORIES), key=lambda c: a["cat"][c][p])
    notes = [f"{esc(cat_p)} drove {pct(a['cat'][cat_p][p], gross)} of {name}'s sips "
             f"(table {table_mix[cat_p]:.0%})."]
    if p in adh:
        notes.append(f"Matched basic strategy {adh[p]:.0%} of the time, "
                     f"{'above' if adh[p] >= table_adh else 'below'} the table's {table_adh:.0%}.")
    if factor:
        delta = a["total"][p] - a["raw_total"][p]
        notes.append(f"Played at {factor}" + (f", {delta:+} sips against 1.0×." if delta else "."))
    chips = ("".join(f'<span class="chip">{esc(w)}</span>' for w in awards)
             or '<span class="chip muted">No award this time</span>')
    body = (f'<div class="pl-top"><div><h3>Running total vs the table</h3>{svg_player_race(a, p)}</div>'
            f'<div><h3>Where {name}\'s sips came from <small>(gross)</small></h3>{bars}</div></div>'
            '<div class="row6">'
            + "".join(f'<div class="kpi" style="border-color:{colour}"><b>{v}</b><span>{t}</span></div>'
                                          for v, t in kpis) + '</div>'
            '<div class="pl-bottom"><div><h3>At the table</h3><div class="kv">'
            + "".join(f"<div><span>{k}</span><b>{esc(v)}</b></div>" for k, v in stats) + '</div></div>'
            f'<div><h3>Awards</h3><div class="chips">{chips}</div>'
            f'<div class="sowhat"><b>So what</b>{" ".join(notes)}</div></div></div>')
    return slide(f"Player recap · {p}", title, body,
                 src + " · Table average = all players' net sips per round played; typical seat = each round's "
                 "average across seated players, added up", page)


def _setup_slide(a, rules, rated, factor_txt, src, page):
    """How the table was set up: settings, Drink Rate factors, and which house rules were off."""
    st, P = a["setup"], a["players"]
    easy = ("on" if st.get("easy_mode") else
            f"halving from round {a['easy_from']} (4+ players)" if a["easy_from"] else "off")
    rows = [("Players", ", ".join(map(esc, P))), ("Rounds", a["n_rounds"]),
            ("Sips per hand", st.get("wager", "–")), ("Hands per player", st.get("hands", "–")),
            ("Decks in the shoe", a["decks"] or "–"), ("Easy Mode", easy),
            ("Drink Rate", " · ".join(f"{esc(p)} {factor_txt(p)}" for p in rated) or "everyone at 1.0×")]
    left = '<table class="t defs">' + "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows) + "</table>"
    if rules is None:
        right = ('<h3>House rules</h3><p class="note">Not part of this export: the in-app recap lists which rules '
                 'were on.</p>')
        title = f"Table setup: {len(P)} players over {a['n_rounds']} rounds"
    else:
        eff = rules.effective()
        off = [r for r in RULES if r.id not in eff]
        preset = f"{rules.preset.title()} preset" if rules.preset else "Custom rule set"
        lines = []
        for gid, glabel in GROUPS:
            names = [esc(r.name) for r in off if r.group == gid]
            if names:
                lines.append(f"<li><b>{glabel}</b> {', '.join(names)}</li>")
        right = (f'<h3>House rules: {preset} · {len(RULES) - len(off)} of {len(RULES)} on</h3>'
                 + (f'<ul class="rules-off">{"".join(lines)}</ul>' if lines
                    else '<p class="note">Every rule was on.</p>')
                 + '<p class="note">Rules as set when the recap was made; changes during the session aren\'t '
                   'recorded.</p>')
        title = ((f"Played on the {rules.preset.title()} preset" if rules.preset else "Played on a custom rule set")
                 + (f" with {len(off)} of {len(RULES)} rules off" if off else " with every rule on"))
    if rated:
        title += f"; {len(rated)} player{'s' if len(rated) != 1 else ''} on a Drink Rate factor"
    body = f'<div class="setup"><div><h3>Settings</h3>{left}</div><div>{right}</div></div>'
    return slide("Appendix · Table setup", title, body, src, page)


def logo_css(inline: bool = True) -> str:
    """The app logo as CSS variables: --logo (round, as in the lobby) and
    --logo-big (transparent, for the cover and thank-you slides). inline=True
    embeds both as data URIs (a standalone file); False points at /static."""
    urls = {}
    for var, name in (("--logo", "logo.png"), ("--logo-big", "logo-transparent.png")):
        if inline:
            with open(os.path.join(_ROOT, "static", "img", name), "rb") as f:
                urls[var] = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        else:
            urls[var] = f"/static/img/{name}"
    return ":root { " + " ".join(f"{v}: url({u});" for v, u in urls.items()) + " }"


def build_html(a, logo: str) -> str:
    """logo: the CSS from logo_css()."""
    P, n = a["players"], a["n_rounds"]
    by_total = sorted(P, key=lambda p: -a["total"][p])
    champ, last = by_total[0], by_total[-1]
    second = by_total[1] if len(by_total) > 1 else champ
    margin = a["total"][champ] - a["total"][second]
    src = f"Source: {APP_NAME} drink log and decision log, session {esc(a['session_id'])}, {n} rounds"
    mins = a["minutes"]
    dur = f"{int(mins // 60)}h {int(mins % 60):02d}m" if mins else "–"
    long_leader = max(a["lead_rounds"], key=a["lead_rounds"].get)
    late = a["changes"][-1]
    pr_lo, pr_hi = min(a["per_round"].values()), max(a["per_round"].values())
    saved = -sum(a["credits"].values())
    easy = -a["credits"].get("Easy mode halving", 0)
    cat_tot = {c: sum(a["cat"][c].values()) for c, _ in CATEGORIES}
    cat_order = sorted(cat_tot, key=lambda c: -cat_tot[c])
    others, own = cat_tot["Others' wins"], cat_tot["Own losing hands"]
    fol_w = a["fol_res"]["win"] / max(sum(a["fol_res"].values()), 1)
    dev_w = a["dev_res"]["win"] / max(sum(a["dev_res"].values()), 1)
    # Dealers with a meaningful sample; early in a session, anyone who dealt
    house = ({d: c for d, c in a["house"].items() if sum(c.values()) >= 10}
             or {d: c for d, c in a["house"].items() if sum(c.values())})
    # House win = player hand lost
    all_house = sum(c["loss"] for c in a["house"].values()) / max(sum(sum(c.values()) for c in a["house"].values()), 1)
    house_rate = {d: c["loss"] / sum(c.values()) for d, c in house.items()}
    toughest = max(house_rate, key=house_rate.get) if house_rate else None
    softest = min(house_rate, key=house_rate.get) if house_rate else None
    adh = {p: a["bs"][p][0] / a["bs"][p][1] for p in P if a["bs"][p][1]}
    best_bs = max(adh, key=adh.get) if adh else None
    peak_i = max(range(n), key=lambda i: a["round_tot"][i])
    avg_round = a["net"] / n
    beers = a["net"] / SIPS_PER_BEER
    wire = champ == long_leader                     # winner also led most of the night
    top_credit = min(a["credits"], key=a["credits"].get) if a["credits"] else None
    headline = ", ".join([
        "A tight finish at the top" if margin <= 0.05 * a["total"][champ] else f"A clear win for {esc(champ)}",
        "a level table underneath" if pr_hi <= 1.2 * pr_lo else "a wide spread underneath",
    ]) + (", and other players' wins, not your own losses, drove the bill" if others > own
          else ", and losing hands drove the bill")
    rules = a["setup"].get("rules")
    level = pr_hi <= 1.2 * pr_lo
    raw_pr = {p: a["raw_total"][p] / a["present"][p] for p in P}
    raw_lo, raw_hi = min(raw_pr.values()), max(raw_pr.values())
    rate_explains = a["rate_used"] and not level and raw_hi <= 1.2 * raw_lo

    def feature_on(rule_id, label_prefix):
        """On in the room's rules, or (no rules, e.g. an xlsx export) left any sips."""
        played = any(r.startswith(label_prefix) for r in a["rule_tot"])
        return played or (rules.on(rule_id) if rules is not None else False)
    bust_on = feature_on("side.bust_vote", "Bust vote")
    lottery_on = feature_on("event.dealer_lottery", "Dealer Lottery") or bool(a["lottery"])
    wild_on = feature_on("event.wild_card", "Wild Card")
    top_cat = cat_order[0]
    rate_delta = a["gross_all"] - a["raw_gross_all"]    # + boosters added sips, − discounts took some off

    def factor_txt(p):
        fr = a["factor_rounds"][p]
        return ", ".join(f"{f:g}× for {c} round{'s' if c != 1 else ''}"
                         for f, c in sorted(fr.items()) if f != 1.0 and c)
    rated = [p for p in P if factor_txt(p)]
    pages = []

    # 1 — Cover
    when = a["start"].strftime("%A, %d %B %Y") if a["start"] else a["day"]
    span = f'{a["start"]:%H:%M}–{a["end"]:%H:%M}' if a["start"] else ""
    pages.append(f'''<section class="slide cover">
      <div class="cv-band"></div>
      <div class="logo cv-logo"></div>
      <div class="cv-kicker">Session recap · {esc(a["session_id"])}</div>
      <div class="cv-title">The night in numbers</div>
      <div class="cv-sub">{when} · {span} · {", ".join(map(esc, P))}</div>
      <div class="cv-kpis">
        <div><b>{a["net"]:,}</b><span>net sips</span></div>
        <div><b>{n}</b><span>rounds</span></div>
        <div><b>{dur}</b><span>at the table</span></div>
        <div><b>{esc(champ)}</b><span>top of the table</span></div>
      </div>
      <div class="cv-foot">Strictly confidential · prepared for the table only · not investment advice
        · drink responsibly</div>
    </section>''')

    # 2 — Executive summary
    msgs = [
        (f"{esc(champ)} finished top with {a['total'][champ]} sips, {margin} ahead of {esc(second)}",
         f"{esc(long_leader)} led for {a['lead_rounds'][long_leader]} of {n} rounds; the lead changed hands "
         f"{len(a['changes']) - 1}× and was settled in round {late[0]}"),
        (f"Per round played, the table was level at {pr_lo:.1f}–{pr_hi:.1f} sips" if level else
         f"Drink Rate explains the spread: at 1.0× the table was level at {raw_lo:.1f}–{raw_hi:.1f} sips per round"
         if rate_explains else
         f"Per round played the spread was wide: {pr_lo:.1f}–{pr_hi:.1f} sips",
         " · ".join(f"{esc(p)} {a['per_round'][p]:.1f}" for p in sorted(P, key=lambda p: -a['per_round'][p]))
         + (f" — {esc(last)}'s lower total reflects joining in round {a['joined'][last]}"
            if a["joined"][last] > 1 else "")),
        (f"Credits cut the bill by {pct(saved, a['gross_all'])}: {a['gross_all']:,} sips owed, {a['net']:,} drunk",
         f"Easy Mode alone saved {easy} sips" if easy
         else f"Biggest credit: {esc(top_credit)} ({-a['credits'][top_credit]} sips)" if top_credit else "No credits "
              "this session"),
    ] + ([
        (f"Drink Rate {'added' if rate_delta > 0 else 'took off'} {abs(rate_delta)} "
         f"sip{'s' if abs(rate_delta) != 1 else ''}: {a['raw_gross_all']:,} owed at 1.0× became {a['gross_all']:,}"
         if rate_delta else "Drink Rate factors were in play but netted out: the bill matches 1.0×",
         " · ".join(f"{esc(p)} {factor_txt(p)}" for p in rated)),
    ] if a["rate_used"] else []) + [
        (f"You mostly drink because others win: {pct(others, a['gross_all'])} of sips vs {pct(own, a['gross_all'])} "
         f"from your own losing hands",
         "Blackjacks, doubled and split wins and suited hands all hand sips to everyone else")
        if top_cat == "Others' wins" else
        (f"{esc(top_cat)} drove the most sips: {pct(cat_tot[top_cat], a['gross_all'])} of the gross bill",
         f"Others' wins {pct(others, a['gross_all'])} · own losing hands {pct(own, a['gross_all'])}"),
    ] + ([
        (f"Following basic strategy paid: {fol_w:.0%} of book decisions won vs {dev_w:.0%} when deviating",
         f"Most common deviation: standing when the book says hit ({a['dev_kinds'][('s', 'h')]}×)"),
    ] if adh else []) + ([
        (f"{esc(toughest)} ran the toughest house, winning {house_rate[toughest]:.0%} of hands as dealer",
         f"{esc(softest)}'s table was the most generous at {house_rate[softest]:.0%} (table average {all_house:.0%})"),
    ] if house_rate else [])
    body = '<div class="exec"><div class="exec-kpis">' + "".join(
        f'<div class="kpi"><b>{v}</b><span>{label}</span></div>' for v, label in [
            (f"{a['net']:,}", "net sips"), (f"{avg_round:.1f}", "sips per round"),
            (dur, "session length"), (f"≈{beers:.0f}", "beers' worth¹")]) + '</div><ol class="msgs">' + "".join(
        f"<li><b>{h}</b><span>{s}</span></li>" for h, s in msgs) + "</ol></div>"
    pages.append(slide("Executive summary",
                       headline,
                       body, src + f" · ¹ Illustrative, assumes {SIPS_PER_BEER} sips ≈ 0.5 l", len(pages) + 1))

    # 3 — The race
    events = [(rd, f'<li><i>{k}</i><b>Round {rd}</b> {esc(p)} takes the lead</li>')
              for k, (rd, p) in enumerate(a["changes"][1:], 1)]
    if a["easy_from"] and a["easy_from"] > 1:
        who = (", ".join(map(esc, a["easy_joiners"])) + " joins; " if a["easy_joiners"] else "")
        events.append((a["easy_from"] - 0.5, f'<li><i>+</i><b>Round {a["easy_from"]}</b> '
                       f'{who}Easy Mode halves the rate</li>'))
    moments = "".join(li for _, li in sorted(events))
    body = (f'<div class="row"><div>{svg_race(a)}</div><div class="side"><h3>Key moments</h3><ol '
            f'class="moments">{moments}</ol>'
            f'<div class="sowhat"><b>So what</b>'
            + (f"{esc(champ)} took control in round {late[0]} and never gave it back; the chasers closed the gap "
               f"to {margin} sips but never got ahead." if wire else
               f"{esc(long_leader)} built the early lead, but the title was settled in the final {n - late[0] + 1} "
               f"rounds.")
            + '</div></div></div>')
    pages.append(slide("Results · The race",
                       f"{esc(champ)} led for {a['lead_rounds'][champ]} of {n} rounds and finished {margin} sips "
                       f"clear of {esc(second)}"
                       if wire else
                       f"{esc(champ)} took the lead in round {late[0]} and held on to win by {margin} sips; "
                       f"{esc(long_leader)} had led for {a['lead_rounds'][long_leader]} rounds",
                       body, src + " · Cumulative net sips after credits", len(pages) + 1))

    # 4 — League table, raw vs normalised
    mx = max(a["total"].values())
    left = hbars([(p, a["total"][p], a["colour"][p]) for p in by_total], mx, lambda v: f"{v}", 90, 300)
    by_pr = sorted(P, key=lambda p: -a["per_round"][p])
    right = hbars([(p, a["per_round"][p], a["colour"][p]) for p in by_pr], max(a["per_round"].values()),
                  lambda v: f"{v:.2f}", 90, 300, ref=a["net"] / sum(a["present"].values()))
    tbl = "".join(
        f"<tr><td><span class='dot' style='background:{a['colour'][p]}'></span>{esc(p)}</td><td>{a['present'][p]}</td>"
        f"<td>{a['dealer_sips'][p]}</td><td>{a['clean'][p]}</td><td>{a['best_round'][p][0]} "
        f"(R{a['best_round'][p][1]})</td>"
        + (f"<td>{a['avg_factor'][p]:.2f}×</td><td>{a['raw_total'][p]}</td>" if a["rate_used"] else "")
        + "</tr>"
        for p in by_total)
    body = (f'<div class="row2"><div><h3>Total net sips</h3>{left}</div>'
            f'<div><h3>Sips per round played <small>(line = table average)</small></h3>{right}</div></div>'
            f'<table class="t"><tr><th>Player</th><th>Rounds played</th><th>Sips as dealer</th><th>Clean rounds</th>'
            f'<th>Worst single round</th>'
            + ('<th>Avg drink factor</th><th>Sips at 1.0×</th>' if a["rate_used"] else "")
            + f'</tr>{tbl}</table>')
    if rate_explains:
        title = (f"Drink Rate explains the spread ({pr_lo:.1f}–{pr_hi:.1f} sips per round): at 1.0× the field is "
                 f"level at {raw_lo:.1f}–{raw_hi:.1f}")
    elif level:
        title = (f"On a per-round basis the field is level ({pr_lo:.1f}–{pr_hi:.1f} sips); "
                 + (f"{esc(last)}'s low total is a late-arrival effect, not tolerance" if a["joined"][last] > 1
                    else f"{esc(champ)} drank {a['per_round'][champ] / a['per_round'][last]:.1f}× {esc(last)}'s rate"))
    else:
        hi_p, lo_p = max(P, key=lambda p: a["per_round"][p]), min(P, key=lambda p: a["per_round"][p])
        title = (f"Per round played the field was spread out: {esc(hi_p)} drank "
                 f"{a['per_round'][hi_p] / max(a['per_round'][lo_p], 0.01):.1f}× {esc(lo_p)}'s rate")
    pages.append(slide("Results · League table", title, body,
                       src + " · Rounds played from the decision log · Clean round = no net sips", len(pages) + 1))

    # 5 — Bridge
    steps = ([("Sips owed at 1.0×", a["raw_gross_all"], "total"), ("Drink Rate factors", rate_delta, "delta")]
             if a["rate_used"] else [("Gross sips owed", a["gross_all"], "total")])
    for rule, v in sorted(a["credits"].items(), key=lambda kv: kv[1]):
        steps.append((rule.replace("Easy mode halving", "Easy Mode (halving)"), v, "delta"))
    steps.append(("Net sips drunk", a["net"], "total"))
    body = (f'<div class="row"><div>{svg_waterfall(steps)}</div><div class="side">'
            f'<div class="big">{pct(saved, a["gross_all"])}</div><div class="bigl">of the gross bill was cancelled '
            f'by credits</div>'
            '<div class="sowhat"><b>So what</b>'
            + (f"Easy Mode is the single biggest lever: it alone removed {pct(easy, a['gross_all'])} of everything owed"
            + (" once the 4th player joined." if a["easy_joiners"] else ".") if easy else
            f"{esc(top_credit)} was the biggest lever ({-a['credits'][top_credit]} sips). Without a 4th player there "
            f"is no "
            f"Easy Mode halving, so the gross bill is mostly what gets drunk." if top_credit else "Nothing was "
            "credited back.")
            + '</div></div></div>')
    pages.append(slide("Results · Sip bridge",
                       f"Credits removed {saved:,} sips from a gross bill of {a['gross_all']:,}"
                       + (f"; Easy Mode alone accounts for {pct(easy, saved)} of the savings" if easy else "")
                       + (f"; Drink Rate factors {'added' if rate_delta > 0 else 'removed'} {abs(rate_delta)} sip"
                          f"{'s' if abs(rate_delta) != 1 else ''}"
                          if a["rate_used"] and rate_delta else ""),
                       body, src + " · Gross = all positive sip events before credits"
                       + (" · Drink Rate: boosters above 1.0× add sips, discounts below take them off"
                          if a["rate_used"] else ""), len(pages) + 1))

    # 6 — Drivers
    bars = hbars([(c, cat_tot[c], BLUE if c == cat_order[0] else "#35548f") for c in cat_order if cat_tot[c] > 0],
                 None, lambda v: f"{v} · {pct(v, a['gross_all'])}", 140, 250)
    head = "".join(f"<th>{esc(p)}</th>" for p in P)
    trs = ""
    for c in cat_order:
        if not cat_tot[c]:
            continue
        cells = ""
        for p in P:
            share = a["cat"][c][p] / a["gross"][p] if a["gross"][p] else 0
            cells += (f'<td style="background:rgba(79,142,247,{min(share * 2.2, 0.9):.2f});'
                      f'color:{ON_FILL if share > 0.3 else TEXT}">{share:.0%}</td>')
        trs += f"<tr><td>{esc(c)}</td>{cells}</tr>"
    body = (f'<div class="row2"><div><h3>Gross sips by driver</h3>{bars}</div>'
            f'<div><h3>Mix by player <small>(% of each player\'s gross sips)</small></h3>'
            f'<table class="t heat"><tr><th></th>{head}</tr>{trs}</table></div></div>'
            '<div class="sowhat wide"><b>So what</b>'
            + ("The fastest way to drink less is not to lose less but to sit next to fewer winners: other players' "
               f"wins and sweeps make up {pct(others + cat_tot['Sweeps'], a['gross_all'])} of the gross bill."
               if top_cat == "Others' wins" else
               f"{esc(top_cat)} is the biggest lever on the bill at {pct(cat_tot[top_cat], a['gross_all'])} of gross "
               "sips; drivers missing here belong to rules the table didn't play.")
            + '</div>')
    pages.append(slide("Drivers · Where the sips came from",
                       f"Other players' wins drove {pct(others, a['gross_all'])} of all sips, "
                       f"{others / max(own, 1):.1f}× more than your own losing hands"
                       if top_cat == "Others' wins" else
                       f"{esc(top_cat)} drove {pct(cat_tot[top_cat], a['gross_all'])} of all sips, the biggest "
                       "single driver",
                       body, src + " · Drivers group the rule that triggered each sip; gross before credits",
                       len(pages) + 1))

    # 7 — Tempo
    first_half = sum(a["round_tot"][: n // 2]) / max(n // 2, 1)
    second_half = sum(a["round_tot"][n // 2:]) / (n - n // 2)
    body = (f'{svg_columns(a)}<div class="row3">'
            f'<div class="kpi"><b>{a["round_tot"][peak_i]}</b><span>sips in round {peak_i + 1}, the peak '
            f'({a["round_tot"][peak_i] / avg_round:.1f}× average)</span></div>'
            f'<div class="kpi"><b>{first_half:.1f} → {second_half:.1f}</b><span>avg sips per round, first vs second '
            f'half</span></div>'
            f'<div class="kpi"><b>{n / (mins / 60):.0f}</b><span>rounds per hour · {mins / n:.1f} min per '
            f'round</span></div>'
            f'<div class="kpi"><b>{a["net"] / (mins / 60) / len(P):.0f}</b><span>sips per player per '
            f'hour</span></div></div>'
            if mins else svg_columns(a))
    pages.append(slide("Drivers · Tempo",
                       f"The pace built through the night: round {peak_i + 1} was the peak at "
                       f"{a['round_tot'][peak_i]} sips, "
                       f"{a['round_tot'][peak_i] / avg_round:.1f}× the session average",
                       body, src + " · Net sips per round, all players; line = 5-round rolling average; top 3 rounds "
                                   "highlighted", len(pages) + 1))

    # 8 — Decision quality
    if adh:
        left = hbars([(p, adh[p] * 100, a["colour"][p]) for p in sorted(adh, key=lambda p: -adh[p])], 100,
                     lambda v: f"{v:.0f}%", 90, 300)
        kinds = {("s", "h"): "Stood, book said hit", ("h", "s"): "Hit, book said stand", ("d", "h"): "Doubled, book "
                  "said hit",
                 ("sp", "h"): "Split, book said hit", ("d", "s"): "Doubled, book said stand", ("sp", "s"): "Split, "
                  "book said stand"}
        dev_list = "".join(f"<tr><td>{kinds.get(k, '/'.join(k))}</td><td>{c}</td></tr>"
                           for k, c in a["dev_kinds"].most_common(4))
        split = ""
        for p in sorted(adh, key=lambda p: -adh[p]):
            f, d = a["bs_res"][p]
            fw, dw = f["win"] / max(sum(f.values()), 1), d["win"] / max(sum(d.values()), 1)
            split += (f"<tr><td><span class='dot' style='background:{a['colour'][p]}'></span>{esc(p)}</td>"
                      f"<td>{fw:.0%}</td><td>{dw:.0%}</td><td "
                      f"style='color:{GREEN if fw >= dw else RED};font-weight:700'>"
                      f"{(fw - dw) * 100:+.0f} pp</td></tr>")
        body = (f'<div class="row2"><div><h3>Decisions matching basic strategy</h3>{left}'
                f'<h3 style="margin-top:22px">Most common deviations</h3><table class="t">{dev_list}</table></div>'
                f'<div><h3>Hand win rate by decision type</h3><div class="vs">'
                f'<div><b style="color:{GREEN}">{fol_w:.0%}</b><span>By the book<br>{sum(a["fol_res"].values())} '
                f'decisions</span></div>'
                f'<div><b style="color:{RED}">{dev_w:.0%}</b><span>Against the book<br>{sum(a["dev_res"].values())} '
                f'decisions</span></div></div>'
                f'<div class="sowhat"><b>So what</b>Every deviation lowered the odds of winning that hand by '
                f'~{(fol_w - dev_w) * 100:.0f} pp, '
                f'and in this game a lost hand costs sips. {esc(best_bs)} played closest to the book '
                f'({adh[best_bs]:.0%}).</div>'
                f'<h3 style="margin-top:22px">Win rate by player</h3><table class="t"><tr><th>Player</th><th>By the '
                f'book</th>'
                f'<th>Against</th><th>Book premium</th></tr>{split}</table></div></div>')
        pages.append(slide("Behaviour · Decision quality",
                           f"Playing by the book paid off: decisions in line with basic strategy won {fol_w:.0%} of "
                           f"the time vs {dev_w:.0%} against it",
                           body, src + " · Decision level; a hand with several decisions counts each one; result = "
                                       "final result of that hand", len(pages) + 1))

    # 9 — Dealers
    if house_rate:
        order = sorted(house_rate, key=lambda d: -house_rate[d])
        house_note = "dealers with fewer than 10 hands excluded" if all(sum(c.values()) >= 10 for c in house.values()) \
            else "small samples early in the session"
        bars = hbars([(f"{d} ({sum(house[d].values())} hands)", house_rate[d] * 100,
                       RED if d == toughest else a["colour"].get(d, BLUE)) for d in order],
                     100, lambda v: f"{v:.0f}%", 150, 360, ref=all_house * 100)
        deal_rows = "".join(
            f"<tr><td><span class='dot' style='background:{a['colour'].get(d, BLUE)}'></span>{esc(d)}</td>"
            f"<td>{sum(1 for r in a['dealer_of'].values() if r == d)}</td><td>{sum(house[d].values())}</td>"
            f"<td>{house[d]['loss']}</td><td>{house[d]['win']}</td><td>{house[d]['push']}</td><td>{a['dealer_sips'][d]}</td></tr>"
            for d in order)
        bars += (f'<h3 style="margin-top:26px">Dealer detail</h3><table class="t"><tr><th>Dealer</th><th>Rounds '
                 f'dealt</th>'
                 f'<th>Hands</th><th>House won</th><th>House lost</th><th>Push</th><th>Sips as '
                 f'dealer</th></tr>{deal_rows}</table>')
        body = (f'<div class="row2"><div><h3>House win rate by dealer <small>(line = table '
                f'average)</small></h3>{bars}</div>'
                f'<div class="side"><div class="big">{(house_rate[toughest] - house_rate[softest]) * 100:.0f} pp</div>'
                f'<div class="bigl">points between the toughest and the most generous dealer</div>'
                f'<div class="sowhat"><b>So what</b>When {esc(toughest)} deals, expect to lose more hands'
                + (", so bank the Dealer Lottery credits early. " if lottery_on else ". ")
                + f'{esc(softest)}\'s deals are the time to double down.</div></div></div>')
        pages.append(slide("Behaviour · The house",
                           f"{esc(toughest)} ran the toughest house, winning {house_rate[toughest]:.0%} of hands vs "
                           f"a table average of {all_house:.0%}",
                           body, src + " · House win = player hand lost; pushes count as hands; " + house_note,
                           len(pages) + 1))

    # 10 — Side games (only the ones in play)
    bv_right, bv_wrong = a["rule_cnt"]["Bust vote credit"], a["rule_cnt"]["Bust vote wrong call"]
    bv_net = sum(v for r, v in a["rule_tot"].items() if r.startswith("Bust vote"))
    dl_net = sum(v for r, v in a["rule_tot"].items() if r.startswith("Dealer Lottery"))
    wc_net = a["rule_tot"]["Wild Card"]
    side_net = bv_net * bust_on + dl_net * lottery_on + wc_net * wild_on
    lot_by = collections.defaultdict(list)
    for e in a["lottery"]:
        lot_by[e["player"]].append(e["x_entered"])
    if bust_on or lottery_on or wild_on:
        kpis, cols, notes, off = [], [], [], []
        if bust_on:
            kpis.append((pct(bv_right, bv_right + bv_wrong),
                         f"bust-vote calls right ({bv_right} of {bv_right + bv_wrong}) · net {bv_net:+} sips"))
            notes.append(f"At {pct(bv_right, bv_right + bv_wrong)} accuracy the bust vote "
                         + ("is worse than a coin flip" if bv_right < bv_wrong else "beats a coin flip")
                         + f", and it moved the table's bill by {bv_net:+} sips.")
        else:
            off.append("bust vote")
        if lottery_on:
            kpis.append((f"{dl_net:+}", f"net sips from the Dealer Lottery ({len(a['lottery'])} stakes placed)"))
            cols.append(("Avg lottery stake (0–5)",
                         lambda p: f"{sum(lot_by[p]) / len(lot_by[p]):.1f}" if lot_by.get(p) else "–"))
            cols.append(("Stakes placed", lambda p: len(lot_by.get(p, []))))
            notes.append("The Dealer Lottery " + ("roughly paid for itself." if abs(dl_net) <= 0.05 * a["net"]
                                                  else f"cost the table {dl_net:+} sips." if dl_net > 0
                                                  else f"saved the table {-dl_net} sips."))
        else:
            off.append("Dealer Lottery")
        if wild_on:
            kpis.append((f"{wc_net:+}", "net sips from the Wild Card"))
            cols.insert(0, ("Wild Card sips", lambda p: a["wild"][p]))
            notes.append("The Wild Card is pure entertainment.")
        else:
            off.append("Wild Card")
        kpis.append((f"{side_net:+}", f"net sips from side games, {pct(side_net, a['net'])} of the bill"))
        trs = "".join(f"<tr><td><span class='dot' style='background:{a['colour'][p]}'></span>{esc(p)}</td>"
                      + "".join(f"<td>{fn(p)}</td>" for _, fn in cols) + "</tr>" for p in P)
        table = ('<div><h3>Appetite for risk</h3><table class="t"><tr><th>Player</th>'
                 + "".join(f"<th>{h}</th>" for h, _ in cols) + f'</tr>{trs}</table></div>' if cols else "<div></div>")
        body = ('<div class="row3">' + "".join(f'<div class="kpi"><b>{v}</b><span>{t}</span></div>' for v, t in kpis)
                + f'</div><div class="row2">{table}<div class="sowhat"><b>So what</b>{" ".join(notes)}'
                + (f" Not played this session: {', '.join(off)}." if off else "") + '</div></div>')
        pages.append(slide("Behaviour · Side games",
                           f"Side games added a net {side_net:+} sips"
                           + (f"; bust-vote calls were right only {pct(bv_right, bv_right + bv_wrong)} of the time"
                              if bust_on and bv_right < bv_wrong else ""),
                           body, src + (" · Bust-vote accuracy counts credit vs wrong-call events" if bust_on else ""),
                           len(pages) + 1))

    # 11 — Player comps
    def rank_cells(vals: dict, fmt, good_high: bool):
        best = max(vals, key=vals.get) if good_high else min(vals, key=vals.get)
        worst = min(vals, key=vals.get) if good_high else max(vals, key=vals.get)
        return {p: f'<td class="{"g" if p == best else "b" if p == worst else ""}">{fmt(vals[p])}</td>' for p in vals}
    hw = {p: a["hands"][p]["win"] / max(sum(a["hands"][p].values()), 1) for p in P}
    drv = {p: max((c for c, _ in CATEGORIES), key=lambda c: a["cat"][c][p]) for p in P}
    metrics = [
        ("Net sips", {p: f"<td>{a['total'][p]}</td>" for p in P}),
        ("Sips / round played", rank_cells(a["per_round"], lambda v: f"{v:.2f}", False)),
        ("Hand win rate", rank_cells(hw, lambda v: f"{v:.0%}", True)),
        ("Basic-strategy match", rank_cells(adh, lambda v: f"{v:.0%}", True) if adh else None),
        ("House win rate as dealer",
         rank_cells({p: house_rate.get(p, 0) for p in P}, lambda v: f"{v:.0%}" if v else "–", True)
         if house_rate else None),
        ("Clean rounds", rank_cells(a["clean"], str, True)),
        ("Wild Card sips", {p: f"<td>{a['wild'][p]}</td>" for p in P}) if wild_on else ("", None),
        ("Avg drink factor", {p: f"<td>{a['avg_factor'][p]:.2f}×</td>" for p in P}) if a["rate_used"] else ("", None),
        ("#1 sip driver", {p: f"<td>{esc(drv[p])}</td>" for p in P}),
    ]
    head = "".join(f"<th><span class='dot' style='background:{a['colour'][p]}'></span>{esc(p)}</th>" for p in P)
    trs = "".join(f"<tr><td>{m}</td>{''.join(cells.get(p, '<td>–</td>') for p in P)}</tr>"
                  for m, cells in metrics if cells)
    body = f'<table class="t comps"><tr><th></th>{head}</tr>{trs}</table>'
    pages.append(slide("Recognition · Player comparables",
                       (f"Side by side: {esc(best_bs)} was both the most efficient drinker per round and the most "
                        "disciplined player" if best_bs == by_pr[-1] else
                        f"Side by side: {esc(by_pr[-1])} was the most efficient drinker per round"
                        + (f", {esc(best_bs)} the most disciplined player" if best_bs else "")),
                       body, src + " · Green = best in row, red = worst", len(pages) + 1))

    # 12 — Awards
    lot_avg = {p: sum(v) / len(v) for p, v in lot_by.items() if v}
    awards = [
        ("🏆", "Top of the table", champ, f"{a['total'][champ]} net sips"),
        ("🧊", "Most efficient", by_pr[-1], f"{a['per_round'][by_pr[-1]]:.2f} sips per round played"),
        ("💥", "Worst single round", max(P, key=lambda p: a["best_round"][p][0]),
         "{} sips in round {}".format(*a["best_round"][max(P, key=lambda p: a["best_round"][p][0])])),
    ]
    if adh:
        maverick = min(adh, key=adh.get)
        awards[2:2] = [("📘", "By the book", best_bs, f"{adh[best_bs]:.0%} of decisions matched basic strategy"),
                       ("🎲", "Maverick", maverick, f"{a['bs'][maverick][1] - a['bs'][maverick][0]} deviations from "
                        "the book")]
    if house_rate:
        awards.insert(-1, ("🏦", "The House", toughest, f"won {house_rate[toughest]:.0%} of hands as dealer"))
    if lot_avg:
        bold = max(lot_avg, key=lot_avg.get)
        awards.append(("🎰", "Risk appetite", bold, f"average Dealer Lottery stake {lot_avg[bold]:.1f} of 5"))
    boost = {p: sum(c for f, c in a["factor_rounds"][p].items() if f > 1) for p in P}
    if any(boost.values()):
        bp = max(boost, key=boost.get)
        awards.append(("🚀", "Booster", bp, factor_txt(bp)))
    disc = {p: sum(c for f, c in a["factor_rounds"][p].items() if f < 1) for p in P}
    if any(disc.values()):
        dp = max(disc, key=disc.get)
        awards.append(("🍷", "Sipping smart", dp, factor_txt(dp)))
    if a["wild"] and wild_on:
        wc = a["wild"].most_common(1)[0]
        awards.append(("🃏", "Wild Card magnet", wc[0], f"{wc[1]} sips handed out by Wild Cards"))
    cards = "".join(f'<div class="award"><div class="em">{e}</div><div class="an">{esc(t)}</div>'
                    f'<div class="aw" style="color:{a["colour"].get(p, BLUE)}">{esc(p)}</div><div '
                    f'class="as">{esc(s)}</div></div>'
                    for e, t, p, s in awards)
    pages.append(slide("Recognition · Awards", "Awards: one for every kind of night",
                       f'<div class="awards{" many" if len(awards) > 8 else ""}">{cards}</div>', src,
                       len(pages) + 1))
    won = collections.defaultdict(list)
    for e, t, p, _ in awards:
        won[p].append(f"{e} {t}")

    # Player recaps — one page each, in finishing order
    table_pr = a["net"] / max(sum(a["present"].values()), 1)
    table_mix = {c: cat_tot[c] / max(a["gross_all"], 1) for c in cat_tot}
    table_adh = (sum(f for f, _ in a["bs"].values()) / max(sum(t for _, t in a["bs"].values()), 1)) if adh else None
    for rank, p in enumerate(by_total, 1):
        pages.append(_player_slide(a, p, rank, len(P), table_pr, table_mix, table_adh, adh, house,
                                   factor_txt(p), won[p], src, len(pages) + 1))

    # Appendix — table setup and house rules
    pages.append(_setup_slide(a, rules, rated, factor_txt, src, len(pages) + 1))

    # 13 — Appendix
    defs = [
        ("Net sips", "Every sip event after credits (Easy Mode halving, Dealer Lottery, bust-vote, Lucky Sevens, A♣ "
         "protection)."),
        ("Gross sips", "All positive sip events before credits; used for driver mix."),
        ("Round played", "A round in which the player made at least one decision (decision log)."),
        ("Clean round", "A round played with zero or negative net sips."),
        ("Basic-strategy match", "Share of hit/stand/double/split decisions equal to the engine's basic-strategy "
         "action."),
        ("House win rate", "Share of player hands lost while that player dealt; pushes count as hands."),
        ("Drink Rate factor", "A seat's multiplier on the sips it owes: boosters (1.2–1.5×) drink more, discounts "
         "(0.2–0.8×, e.g. wine 0.6×) drink less. Aces, the bust vote, 666/777 and the Wild Card skip boosters. "
         "Avg factor = mean over the rounds the seat played."),
        ("Driver categories", "; ".join(f"{c}: {', '.join(k for k in keys if k)}" for c, keys in CATEGORIES[:-1])
         + "; everything else: Wild Card & other."),
    ]
    body = ('<table class="t defs">' + "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in defs)
            + "</table>")
    pages.append(slide("Appendix · Definitions", "Methodology and definitions", body,
                       src + f" · Full data: drinks_summary_{a['day']}.xlsx", len(pages) + 1))

    # 14 — Thank you
    pages.append(f'''<section class="slide thanks">
      <div class="cv-band"></div>
      <div class="logo cv-logo"></div>
      <div class="ty-title">Thanks for playing!</div>
      <div class="ty-sub">Hope you enjoyed the night. Same table, next deal?</div>
      <div class="ty-recap">{n} rounds · {a["net"]:,} sips · {dur} ·
        congrats {esc(champ)}, the next round is on you</div>
      <div class="ty-beer"><div class="qr">{qr_svg(TIP_URL)}</div><div>
        <b>🍺 Enjoyed it? Buy us a beer</b>
        <span>{APP_NAME} is a hobby project. If it made your night, a tip keeps the cards coming.<br>
        Scan the code or visit <a href="{esc(TIP_URL)}">{esc(TIP_URL.removeprefix("https://"))}</a></span></div></div>
      <div class="cv-foot">Know your limits · drink responsibly · never drink and drive</div>
    </section>''')

    return (f"<!doctype html><html><head><meta charset='utf-8'><title>Session recap {esc(a['day'])}</title>"
            f"<style>{logo}{CSS}</style></head><body>{''.join(pages)}</body></html>")


CSS = f"""
@page {{ size: 13.333in 7.5in; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: {BG}; font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  color: {TEXT}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.slide {{ width: 1280px; height: 720px; padding: 34px 50px 0; position: relative; page-break-after: always;
  overflow: hidden; background: {BG}; }}
.slide:last-child {{ page-break-after: auto; }}
.brand {{ position: absolute; top: 26px; right: 50px; display: flex; align-items: center; gap: 10px; font-size: 12px;
  font-weight: 800; letter-spacing: .06em; color: {MUTED}; }}
.brand .logo {{ width: 38px; height: 38px; }}
.logo {{ background: var(--logo) center / cover no-repeat; border-radius: 50%; }}
.tracker {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: {BLUE}; font-weight: 700; }}
h1 {{ font-size: 25px; line-height: 1.22; margin: 8px 0 0; padding-bottom: 14px; border-bottom: 1px solid {BORDER};
  max-width: 1080px; font-weight: 700; }}
h3 {{ font-size: 13.5px; margin: 0 0 12px; text-transform: uppercase; letter-spacing: .05em; color: {MUTED}; }}
h3 small {{ text-transform: none; font-weight: 400; letter-spacing: 0; }}
.body {{ padding-top: 22px; }}
footer {{ position: absolute; left: 50px; right: 50px; bottom: 18px; display: flex; justify-content: space-between;
  font-size: 10.5px; color: {MUTED}; border-top: 1px solid {BORDER}; padding-top: 7px; }}
.ax {{ font-size: 11px; fill: {MUTED}; }}
.row {{ display: grid; grid-template-columns: 820px 1fr; gap: 30px; }}
.row2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 50px; margin-bottom: 22px; }}
.row3 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 16px 0 22px; }}
.side h3 {{ margin-top: 4px; }}
.sowhat {{ background: {SURFACE}; border: 1px solid {BORDER}; border-left: 4px solid {YELLOW}; border-radius: 12px;
  padding: 12px 16px; font-size: 14px; line-height: 1.45; margin-top: 18px; }}
.sowhat b {{ display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: {YELLOW};
  margin-bottom: 4px; }}
.sowhat.wide {{ margin-top: 4px; }}
.moments {{ list-style: none; padding: 0; margin: 0; font-size: 14px; }}
.moments li {{ margin-bottom: 10px; display: flex; gap: 10px; align-items: baseline; }}
.moments i {{ font-style: normal; background: {YELLOW}; color: {ON_FILL}; border-radius: 50%; width: 20px;
  height: 20px; flex: none; text-align: center; font-size: 11px; line-height: 20px; font-weight: 700; }}
.moments b {{ white-space: nowrap; }}
.hbars {{ font-size: 13px; }}
.hb {{ display: flex; align-items: center; margin-bottom: 9px; }}
.hbl {{ flex: none; }}
.hbt {{ position: relative; height: 22px; background: {SURFACE}; border-radius: 6px; flex: none; }}
.hbf {{ position: absolute; left: 0; top: 0; bottom: 0; border-radius: 6px; }}
.hbref {{ position: absolute; top: -4px; bottom: -4px; border-left: 2px dashed {TEXT}; }}
.hbv {{ padding-left: 10px; font-weight: 700; white-space: nowrap; }}
.t {{ border-collapse: collapse; font-size: 13.5px; width: 100%; }}
.t th {{ text-align: left; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; color: {MUTED};
  border-bottom: 1.5px solid {BORDER}; padding: 6px 10px; }}
.t td {{ border-bottom: 1px solid {BORDER}; padding: 7px 10px; }}
.t td:first-child {{ white-space: nowrap; }}
.t.heat td {{ text-align: center; font-weight: 700; }}
.t.heat td:first-child {{ text-align: left; font-weight: 400; color: {TEXT}; background: none !important; }}
.t.comps td, .t.comps th {{ text-align: center; padding: 10px; font-size: 15px; }}
.t.comps th {{ color: {TEXT}; }}
.t.comps td:first-child {{ text-align: left; font-weight: 700; }}
.t.comps td.g {{ background: rgba(62,207,110,.14); color: {GREEN}; font-weight: 700; }}
.t.comps td.b {{ background: rgba(224,92,92,.14); color: {RED}; font-weight: 700; }}
.t.defs td:first-child {{ font-weight: 700; width: 220px; vertical-align: top; }}
.t.defs td {{ font-size: 13px; line-height: 1.4; }}
.dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }}
.kpi {{ border-top: 3px solid {BLUE}; padding-top: 8px; }}
.kpi b {{ display: block; font-size: 30px; }}
.kpi span {{ font-size: 12.5px; color: {MUTED}; line-height: 1.35; display: block; margin-top: 3px; }}
.big {{ font-size: 64px; font-weight: 700; color: {YELLOW}; line-height: 1; margin-top: 30px; }}
.bigl {{ font-size: 15px; margin-top: 6px; }}
.vs {{ display: flex; gap: 40px; margin: 10px 0 6px; }}
.vs b {{ font-size: 58px; display: block; }}
.vs span {{ font-size: 13px; color: {MUTED}; }}
.exec {{ display: grid; grid-template-columns: 220px 1fr; gap: 44px; }}
.exec-kpis .kpi {{ margin-bottom: 20px; }}
.msgs {{ margin: 0; padding: 0; list-style: none; counter-reset: m; }}
.msgs li {{ counter-increment: m; position: relative; padding: 0 0 13px 44px; margin-bottom: 13px;
  border-bottom: 1px solid {BORDER}; }}
.msgs li::before {{ content: counter(m); position: absolute; left: 0; top: 0; width: 28px; height: 28px;
  border-radius: 8px; background: {BLUE}; color: {ON_FILL}; font-weight: 700; text-align: center; line-height: 28px;
  font-size: 14px; }}
.msgs b {{ display: block; font-size: 16px; }}
.msgs span {{ display: block; font-size: 13px; color: {MUTED}; margin-top: 3px; }}
.awards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}
.award {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 16px 18px; height: 230px; }}
.award .em {{ font-size: 34px; }}
.award .an {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: {YELLOW}; font-weight: 700;
  margin-top: 10px; }}
.award .aw {{ font-size: 26px; font-weight: 700; margin-top: 6px; }}
.award .as {{ font-size: 13.5px; color: {MUTED}; margin-top: 8px; line-height: 1.4; }}
.cover, .thanks {{ padding: 0;
  background: radial-gradient(circle at 76% 50%, rgba(243,154,30,.18), rgba(243,154,30,0) 32%), {BG}; }}
.cv-band {{ position: absolute; left: 0; top: 0; bottom: 0; width: 10px;
  background: linear-gradient({YELLOW}, {AMBER}); }}
.cv-logo {{ position: absolute; right: 90px; top: 110px; width: 500px; height: 500px; border-radius: 0;
  background-image: var(--logo-big); }}
.cv-kicker {{ position: absolute; left: 90px; top: 180px; font-size: 15px; letter-spacing: .14em;
  text-transform: uppercase; color: {AMBER}; font-weight: 700; }}
.cv-title {{ position: absolute; left: 90px; top: 210px; font-size: 64px; font-weight: 800; }}
.cv-sub {{ position: absolute; left: 90px; top: 300px; font-size: 18px; color: {MUTED}; }}
.cv-kpis {{ position: absolute; left: 90px; top: 420px; display: flex; gap: 52px; }}
.cv-kpis b {{ display: block; font-size: 40px; }}
.cv-kpis span {{ font-size: 13px; color: {MUTED}; text-transform: uppercase; letter-spacing: .08em; }}
.cv-foot {{ position: absolute; left: 90px; bottom: 36px; font-size: 11px; color: {MUTED}; letter-spacing: .06em;
  text-transform: uppercase; }}
.ty-title {{ position: absolute; left: 90px; top: 150px; font-size: 64px; font-weight: 800; }}
.ty-sub {{ position: absolute; left: 90px; top: 242px; width: 560px; font-size: 20px; line-height: 1.45;
  color: {MUTED}; }}
.ty-recap {{ position: absolute; left: 90px; top: 345px; font-size: 15px; color: {TEXT}; }}
.ty-beer {{ position: absolute; left: 90px; top: 400px; width: 600px; display: flex; gap: 24px; align-items: center;
  background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 18px 22px; }}
.ty-beer .qr {{ width: 124px; height: 124px; flex: none; background: #fff; border-radius: 8px; padding: 4px; }}
.ty-beer .qr svg {{ width: 100%; height: 100%; display: block; }}
.ty-beer b {{ display: block; font-size: 22px; color: {YELLOW}; }}
.ty-beer span {{ display: block; font-size: 14px; color: {MUTED}; margin-top: 6px; line-height: 1.45; }}
.ty-beer a {{ color: {BLUE}; text-decoration: none; font-weight: 700; }}
.awards.many {{ gap: 12px; }}
.awards.many .award {{ height: 150px; padding: 10px 16px; }}
.awards.many .award .em {{ font-size: 24px; }}
.awards.many .award .an {{ margin-top: 4px; }}
.awards.many .award .aw {{ font-size: 21px; margin-top: 2px; }}
.awards.many .award .as {{ margin-top: 4px; }}
.pl-top {{ display: grid; grid-template-columns: 600px 1fr; gap: 40px; }}
.row6 {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin: 8px 0 14px; }}
.row6 .kpi b {{ font-size: 24px; }}
.row6 .kpi span {{ font-size: 11.5px; }}
.pl-bottom {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }}
.pl-bottom h3 {{ margin-bottom: 8px; }}
.kv {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px 24px; }}
.kv span {{ display: block; font-size: 11px; color: {MUTED}; text-transform: uppercase; letter-spacing: .04em; }}
.kv b {{ font-size: 14.5px; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.chip {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 999px; padding: 5px 12px; font-size: 13px;
  font-weight: 700; }}
.chip.muted {{ color: {MUTED}; font-weight: 400; }}
.pl-bottom .sowhat {{ margin-top: 12px; }}
.setup {{ display: grid; grid-template-columns: 480px 1fr; gap: 50px; }}
.rules-off {{ columns: 2; column-gap: 32px; margin: 0; padding: 0; list-style: none; font-size: 13px;
  line-height: 1.4; }}
.rules-off li {{ break-inside: avoid; margin-bottom: 9px; }}
.rules-off b {{ display: block; color: {YELLOW}; font-size: 11.5px; text-transform: uppercase; letter-spacing: .04em; }}
.note {{ color: {MUTED}; font-size: 13px; line-height: 1.45; margin: 12px 0 0; }}
"""
