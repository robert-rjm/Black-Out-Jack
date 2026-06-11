"""
app/routes/reports.py
======================
Static-asset and reporting routes.

GET /logo.png       — app icon (PWA)
GET /manifest.json  — PWA manifest
GET /rules          — Rules.md as JSON for frontend markdown rendering
GET /export_csv     — Full drink-log CSV download for the session
GET /summary_json   — Drink summary as JSON for on-screen display
"""

import csv
import io
import os
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request, Response, send_from_directory

from app.services.session_store import game_sessions

bp = Blueprint("reports", __name__)

# ── Project root (one level above the app/ package) ─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))   # .../app/routes/
_ROOT = os.path.dirname(os.path.dirname(_HERE))      # .../Black-Out-Jack/


# ---------------------------------------------------------------------------
# Static assets
# ---------------------------------------------------------------------------

@bp.route("/logo.png")
def serve_logo():
    return send_from_directory(current_app.static_folder, "img/logo.png")


@bp.route("/manifest.json")
def serve_manifest():
    return jsonify({
        "name":             "Black-Out Jack",
        "short_name":       "Black-Out Jack",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#0f1117",
        "theme_color":      "#0f1117",
        "icons": [
            {"src": "/logo.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@bp.route("/rules")
def rules():
    """Serve the Rules.md content as plain text for frontend markdown rendering."""
    rules_path = os.path.join(_ROOT, "docs", "Rules.md")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except FileNotFoundError:
        return jsonify({"ok": False, "content": "# Rules\n\nRules file not found."})


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@bp.route("/export_csv")
def export_csv():
    """
    Return a CSV file of all drinks recorded so far in this session.
    Columns: round, dealer, player, role, rule, sips
    Usage: GET /export_csv?room_code=Jack-21
    """
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return Response("No active session.", status=404, mimetype="text/plain")

    rows = session._drink_csv_rows

    # Aggregate: player_sips[player][rule] and dealer_sips[player][rule]
    player_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    dealer_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    num_rounds = max((r["round"] for r in rows), default=1)
    players_seen: list[str] = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        bucket = dealer_sips if row["role"] == "dealer" else player_sips
        bucket[name][row["rule"]] += row["sips"]

    all_rules = sorted({row["rule"] for row in rows})

    # Build summary CSV
    buf = io.StringIO()
    w   = csv.writer(buf)

    hand_stats  = session._hand_stats
    milestones  = session._milestones_claimed

    def _pct(n, d):
        return f"{n/d*100:.1f}%" if d else "—"

    # Header metadata
    w.writerow(["Drinking Blackjack — Session Summary"])
    w.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    w.writerow(["Rounds completed", num_rounds])
    w.writerow(["Players"] + players_seen)
    w.writerow([])

    # Milestone winners — who crossed each 50-sip threshold first
    if milestones:
        w.writerow(["MILESTONES"])
        w.writerow(["Threshold", "First to reach"])
        for boundary in sorted(milestones):
            w.writerow([f"{boundary} sips", milestones[boundary]])
        w.writerow([])

    # Per-player tables
    for name in players_seen:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        gt = pt + dt
        # Hand outcome stats
        w.writerow([name])
        hs = hand_stats.get(name)
        h  = hs["hands"] if hs else 0
        w.writerow([f"Total sips: {gt}",    f"Won: {hs['wins']} ({_pct(hs['wins'], h)})" if h else ""])
        w.writerow([f"As player: {pt}",     f"Lost: {hs['losses']} ({_pct(hs['losses'], h)})" if h else ""])
        w.writerow([f"As dealer: {dt}",     f"Push: {hs['pushes']} ({_pct(hs['pushes'], h)})" if h else ""])
        w.writerow([
            f"Sips/round: {gt/num_rounds:.2f}",
            (f"Splits won: {hs['split_wins']} of {hs['split_hands']}"
             f" ({_pct(hs['split_wins'], hs['split_hands'])})" if h and hs["split_hands"] else "")
        ])
        w.writerow([
            f"Hands: {h}" if h else "Hands: 0",
            (f"Doubles won: {hs['double_wins']} of {hs['double_hands']}"
             f" ({_pct(hs['double_wins'], hs['double_hands'])})" if h and hs["double_hands"] else "")
        ])
        w.writerow(["Rule", "Player sips", "Dealer sips", "Total", "Sips/round", "% of own"])
        player_rules = [(rule, player_sips[name].get(rule, 0) + dealer_sips[name].get(rule, 0)) for rule in all_rules]
        for rule, total in sorted(player_rules, key=lambda x: -x[1]):
            if total == 0:
                continue
            ps  = player_sips[name].get(rule, 0)
            ds  = dealer_sips[name].get(rule, 0)
            pct = f"{total/gt*100:.1f}%" if gt else "—"
            w.writerow([rule, ps, ds, total, f"{total/num_rounds:.2f}", pct])
        w.writerow(["TOTAL", pt, dt, gt, f"{gt/num_rounds:.2f}", "100%"])
        w.writerow([])

    # Grand totals table
    rule_totals: dict[str, int] = defaultdict(int)
    for name in players_seen:
        for rule, s in player_sips[name].items():
            rule_totals[rule] += s
        for rule, s in dealer_sips[name].items():
            rule_totals[rule] += s
    grand_total = sum(rule_totals.values())

    w.writerow(["ALL PLAYERS COMBINED"])
    w.writerow(["Rule", "Total sips", "Sips/round", "% of total"])
    for rule in sorted(rule_totals, key=lambda r: -rule_totals[r]):
        total = rule_totals[rule]
        pct   = f"{total/grand_total*100:.1f}%" if grand_total else "—"
        w.writerow([rule, total, f"{total/num_rounds:.2f}", pct])
    w.writerow([])
    w.writerow(["Grand total", grand_total, f"{grand_total/num_rounds:.2f} sips/round"])

    # Hand stats summary table (all players)
    w.writerow([])
    w.writerow(["HAND OUTCOMES"])
    w.writerow(["Player", "Hands", "Won", "Win%", "Lost", "Loss%", "Push", "Push%",
                "Splits won", "Split win%", "Doubles won", "Double win%"])
    for name in players_seen:
        hs = hand_stats.get(name, {
            "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
            "split_hands": 0, "split_wins": 0, "double_hands": 0, "double_wins": 0,
        })
        h = hs["hands"]
        w.writerow([
            name, h if h else "-",
            hs["wins"]   if h else "-", _pct(hs["wins"],   h),
            hs["losses"] if h else "-", _pct(hs["losses"],  h),
            hs["pushes"] if h else "-", _pct(hs["pushes"],  h),
            f"{hs['split_wins']} of {hs['split_hands']}" if hs["split_hands"]  else "-",
            _pct(hs["split_wins"],  hs["split_hands"]),
            f"{hs['double_wins']} of {hs['double_hands']}" if hs["double_hands"] else "-",
            _pct(hs["double_wins"], hs["double_hands"]),
        ])

    # Dealer stats
    dealer_stats = session._dealer_hand_stats
    if dealer_stats:
        w.writerow([])
        w.writerow(["DEALER STATS (per dealing stint)"])
        w.writerow(["Dealer", "Hands dealt", "Won", "Win%", "Lost", "Loss%", "Push", "Push%"])
        for dname, ds in sorted(dealer_stats.items()):
            dh = ds["hands"]
            w.writerow([
                dname, dh,
                ds["wins"],   _pct(ds["wins"],   dh),
                ds["losses"], _pct(ds["losses"],  dh),
                ds["pushes"], _pct(ds["pushes"],  dh),
            ])

    return Response(
        b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"),  # UTF-8 BOM for Excel
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="drinks_summary.csv"'},
    )


# ---------------------------------------------------------------------------
# JSON summary
# ---------------------------------------------------------------------------

@bp.route("/summary_json")
def summary_json():
    """Return session drink summary as JSON for on-screen display."""
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    rows       = session._drink_csv_rows
    num_rounds = max((r["round"] for r in rows), default=0)

    player_sips: dict[str, int] = defaultdict(int)
    dealer_sips: dict[str, int] = defaultdict(int)
    players_seen: list[str]     = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        if row["role"] == "dealer":
            dealer_sips[name] += row["sips"]
        else:
            player_sips[name] += row["sips"]

    summary = []
    for name in players_seen:
        ps = player_sips[name]
        ds = dealer_sips[name]
        summary.append({"name": name, "player_sips": ps,
                         "dealer_sips": ds, "total_sips": ps + ds})
    summary.sort(key=lambda x: -x["total_sips"])

    return jsonify({"ok": True, "rounds": num_rounds, "players": summary})
