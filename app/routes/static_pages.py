"""
app/routes/static_pages.py
===========================
Static-asset, doc and link routes.

GET /logo.png       — app icon (PWA)
GET /favicon.ico   — the same icon, for pages without a <link rel="icon"> (PDF tabs, bare requests)
GET /manifest.json  — PWA manifest
GET /rules          — Rules.md (or Rules-Normal.md with ?mode=normal) as JSON for
                       frontend markdown rendering
GET /rules_registry — every toggleable house rule (names, groups, presets) as
                       cacheable JSON for the settings view
GET /how-it-works   — the "How it works" PDF (docs/Pitch-Deck.pdf, shown in the lobby popup);
                       /how-it-works/finance is the report-style version (docs/Pitch-Deck-Finance.pdf)
GET /beer           — redirect to the PayPal tip link (see static/js/ui/tip.js)
GET /beer_qr        — the tip link plus a QR code of it, as inline SVG
"""

import os

from flask import Blueprint, current_app, jsonify, redirect, request, send_from_directory

from app.services.house_rules import registry_payload
from app.config import TIP_URL
from app.services.qr import qr_svg

bp = Blueprint("static_pages", __name__)

# ── Project root (one level above the app/ package) ─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))   # .../app/routes/
_ROOT = os.path.dirname(os.path.dirname(_HERE))      # .../Black-Out-Jack/

@bp.route("/logo.png")
def serve_logo():
    return send_from_directory(current_app.static_folder, "img/logo.png")


@bp.route("/favicon.ico")
def favicon():
    return send_from_directory(current_app.static_folder, "img/logo.png", mimetype="image/png", max_age=86400)


@bp.route("/manifest.json")
def serve_manifest():
    return jsonify({
        "name":             "Black(Out)Jack",
        "short_name":       "Black(Out)Jack",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#0f1117",
        "theme_color":      "#0f1117",
        "icons": [
            {"src": "/logo.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@bp.route("/rules")
def rules():
    """Serve the Rules.md content as plain text for frontend markdown rendering."""
    name = "Rules-Normal.md" if request.args.get("mode") == "normal" else "Rules.md"
    rules_path = os.path.join(_ROOT, "docs", name)
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except FileNotFoundError:
        return jsonify({"ok": False, "content": "# Rules\n\nRules file not found."})


def _tour_pdf(filename: str):
    """Show a "How it works" PDF in the browser; 404 if the file isn't deployed."""
    return send_from_directory(os.path.join(_ROOT, "docs"), filename, mimetype="application/pdf",
                               as_attachment=False, max_age=300)


@bp.route("/how-it-works")
def tour():
    """Short, shareable link to the "How it works" deck (also what a QR code can point at)."""
    return _tour_pdf("Pitch-Deck.pdf")


@bp.route("/how-it-works/finance")
def tour_finance():
    """The same deck as a sober report: no emojis, square corners."""
    return _tour_pdf("Pitch-Deck-Finance.pdf")


@bp.route("/rules_registry")
def rules_registry():
    """Static rule data. /state only carries ID lists; the frontend fetches
    this once for names, summaries, groups and dependencies."""
    resp = jsonify(registry_payload())
    resp.headers["Cache-Control"] = "public, max-age=300"
    return resp


@bp.route("/beer_qr")
def beer_qr():
    """QR code for the tip link, so it works even when a popup/ad blocker stops
    the PayPal tab from opening."""
    return jsonify({"ok": True, "url": TIP_URL, "svg": qr_svg(TIP_URL)})


@bp.route("/beer")
def beer():
    """"Tip us" link target. Redirecting from our own origin keeps ad blockers
    that hide direct PayPal links from swallowing the in-game button."""
    return redirect(TIP_URL, code=302)
