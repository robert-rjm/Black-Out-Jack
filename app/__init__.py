"""
app/__init__.py
================
Flask application factory.

Usage:
    from app import create_app
    app = create_app()
"""

import os

from flask import Flask, render_template

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

    # -- Global after_request ------------------------------------------
    @app.after_request
    def no_cache(response):
        """Prevent Safari from caching JSON polling responses."""
        if response.content_type and "json" in response.content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"]        = "no-cache"
            response.headers["Expires"]       = "0"
        return response

    # -- Index ---------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    # -- Blueprints ----------------------------------------------------
    from app.routes.reports       import bp as reports_bp
    from app.routes.polling       import bp as polling_bp
    from app.routes.lobby         import bp as lobby_bp
    from app.routes.admin         import bp as admin_bp
    from app.routes.game_commands import bp as game_commands_bp

    app.register_blueprint(reports_bp)
    app.register_blueprint(polling_bp)
    app.register_blueprint(lobby_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(game_commands_bp)

    return app
