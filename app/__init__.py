"""
app/__init__.py
================
Flask application factory.

Usage:
    from app import create_app
    app = create_app()
"""

import os

from flask import Flask, render_template, jsonify
from werkzeug.exceptions import HTTPException

# Project root — one level above this file (app/__init__.py -> Black-Out-Jack/)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        root_path=_ROOT,            # serve templates/static from project root
        template_folder="templates",
        static_folder="static",
    )

    # Regenerate the JS/CSS bundles from source on every startup (this app's
    # only "deploy" step is a process restart, so there's no separate build
    # phase to run this from -- see app/services/asset_bundler.py). Skipped
    # under pytest: the test suite calls create_app() hundreds of times (once
    # per test's `app` fixture) and never reads bundle.js/bundle.css, so
    # rebuilding it every time is both wasted work and, in a OneDrive-synced
    # project folder, a real source of transient PermissionError/OSError
    # flakiness from repeatedly rewriting the same file out from under sync.
    if "PYTEST_CURRENT_TEST" not in os.environ:
        from app.services.asset_bundler import build_bundles
        build_bundles(_ROOT)

    # -- Global after_request ------------------------------------------
    @app.after_request
    def no_cache(response):
        """Prevent Safari from caching JSON polling responses."""
        if response.content_type and "json" in response.content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"]        = "no-cache"
            response.headers["Expires"]       = "0"
        return response

    # -- Centralized error handling -------------------------------------
    # The frontend talks to this app almost entirely via fetch/long-poll and
    # expects JSON back. Without this, an unhandled exception (or a 404 on a
    # bad route) returns Flask's default HTML error page, which breaks
    # response.json() on the client and surfaces as a generic stuck state.
    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        response = jsonify({"ok": False, "output": e.description or e.name})
        response.status_code = e.code or 500
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_exception(e):
        app.logger.exception("Unhandled exception")
        return jsonify({"ok": False, "output": "Internal server error — please try again."}), 500

    # -- Index ---------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/terms")
    def terms():
        return render_template("terms.html")

    # -- Blueprints ----------------------------------------------------
    from app.routes.reports       import bp as reports_bp
    from app.routes.polling       import bp as polling_bp
    from app.routes.lobby         import bp as lobby_bp
    from app.routes.admin         import bp as admin_bp
    from app.routes.game_commands import bp as game_commands_bp
    from app.routes.wild_card     import bp as wild_card_bp

    app.register_blueprint(reports_bp)
    app.register_blueprint(polling_bp)
    app.register_blueprint(lobby_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(game_commands_bp)
    app.register_blueprint(wild_card_bp)

    return app
