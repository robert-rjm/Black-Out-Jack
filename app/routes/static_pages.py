"""
app/routes/static_pages.py
===========================
Static-asset, doc and link routes.

GET /logo.png       — app icon (PWA)
GET /manifest.json  — PWA manifest
GET /rules          — Rules.md (or Rules-Normal.md with ?mode=normal) as JSON for
                       frontend markdown rendering
GET /beer           — redirect to the PayPal tip link (see static/js/ui/tip.js)
GET /beer_qr        — the tip link plus a QR code of it, as inline SVG
"""

import os

from flask import Blueprint, current_app, jsonify, redirect, request, send_from_directory

from app.services.qr import qr_svg

bp = Blueprint("static_pages", __name__)

# ── Project root (one level above the app/ package) ─────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))   # .../app/routes/
_ROOT = os.path.dirname(os.path.dirname(_HERE))      # .../Black-Out-Jack/

TIP_URL = "https://paypal.me/robertmichels"


@bp.route("/logo.png")
def serve_logo():
    return send_from_directory(current_app.static_folder, "img/logo.png")


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
