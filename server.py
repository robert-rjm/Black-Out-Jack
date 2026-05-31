"""
server.py
=========
Entry point — creates the Flask app and starts the development server.

The application factory (create_app) and all route blueprints live under
the app/ package:

    app/__init__.py          Flask factory + blueprint registration
    app/config.py            Constants and feature flags
    app/routes/
        lobby.py             /create_room  /join_room  /setup
        game_commands.py     /command  (digital + referee dispatcher)
        admin.py             /kick  /rotate_dealer  /update_settings  …
        polling.py           /state  /register  /preselect  …
        reports.py           /export_csv  /summary_json  /rules  …
    app/services/
        session_store.py     In-memory room/session registry
        validators.py        Input sanitisation, client-auth helpers
        serializer.py        Session state → frontend JSON
        game_engine.py       Digital dealing, NPC auto-play, dealer turn
        drink_tracker.py     End-of-round drink accounting and milestones
        room_manager.py      Room lifecycle, queued settings, dealer rotation

Run:
    python server.py

Then open http://<your-PC-IP>:5000 on any phone on the same WiFi.
"""

import socket

from app import create_app

app = create_app()

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"

    print("\n  Drinking Blackjack Referee -- Web Mode")
    print("  Local:   http://localhost:5000")
    print(f"  iPhone:  http://{local_ip}:5000  (same WiFi)")
    print("  (Ctrl+C to stop)\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
