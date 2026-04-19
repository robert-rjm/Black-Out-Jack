"""
app.py
======
Flask web server wrapping referee.py so the game can be played from an iPhone.

Run:
    python app.py

Then open http://<your-PC-IP>:5000 on any phone on the same WiFi.
"""

import io
import contextlib
import socket

from flask import Flask, request, jsonify, render_template

from referee import RefereeSession
from blackjack import Player, Hand

app = Flask(__name__)
game_session: RefereeSession | None = None   # single-table, no auth needed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_tracker(session: RefereeSession):
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web version never blocks waiting for terminal input.
    """
    tracker = session.tracker

    def web_handout(giver: str, total: int, reason: str):
        print(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        print(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21, auto)")
            print(f"    -> {t.name} +1 sip")

    tracker._handle_handout = web_handout


def _capture(fn, *args):
    """Call fn(*args) and return everything it printed as a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/setup", methods=["POST"])
def setup():
    global game_session
    data = request.json

    names = [n.strip().capitalize() for n in data["players"] if n.strip()]
    if not names:
        return jsonify({"ok": False, "output": "No player names provided."})

    dealer_idx  = int(data.get("dealer_index", 0))
    dealer_name = names[min(dealer_idx, len(names) - 1)]
    wager       = int(data.get("wager", 1))
    num_hands   = int(data.get("num_hands", 2))

    players = []
    for name in names:
        p           = Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    game_session = RefereeSession(players, dealer_name, wager, num_hands)
    _patch_tracker(game_session)

    output = _capture(game_session.start_round)
    return jsonify({
        "ok":      True,
        "output":  output,
        "players": names,
        "dealer":  dealer_name,
        "round":   game_session.round_count,
    })


@app.route("/command", methods=["POST"])
def command():
    global game_session
    if not game_session:
        return jsonify({"ok": False, "output": "No active session — set up a game first."})

    cmd_str = (request.json or {}).get("cmd", "").strip()
    if not cmd_str:
        return jsonify({"ok": False, "output": "Empty command."})

    parts = cmd_str.split()
    cmd   = parts[0].lower()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        if cmd == "deal":
            game_session.cmd_deal(parts)

        elif cmd == "action":
            game_session.cmd_action(parts)

        elif cmd == "result":
            game_session.cmd_result(parts)

        elif cmd == "dealer":
            game_session.cmd_dealer(parts)

        elif cmd == "fouraces":
            game_session.cmd_fouraces(parts)

        elif cmd == "endround":
            game_session.cmd_endround()

        elif cmd == "newround":
            # Optional second token: "rotate" | "keep"  (default: keep)
            rotate = len(parts) > 1 and parts[1].lower() == "rotate"
            if rotate:
                all_names = [p.name for p in game_session.all_players]
                cur_idx   = all_names.index(game_session.dealer_name)
                new_idx   = (cur_idx + 1) % len(all_names)
                new_dealer = all_names[new_idx]
                for p in game_session.all_players:
                    p.is_dealer   = (p.name == new_dealer)
                    p.dealer_hand = Hand() if p.is_dealer else None
                game_session.dealer_name = new_dealer
                print(f"  Dealer rotates => {new_dealer} is now dealer.")
            game_session.start_round()
            _patch_tracker(game_session)

        elif cmd in ("status", "st"):
            game_session.cmd_status()

        elif cmd == "help":
            RefereeSession.print_help()

        else:
            print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    # Extra state so the UI can update the header without a second request
    extra = {}
    if game_session:
        extra = {
            "dealer": game_session.dealer_name,
            "round":  game_session.round_count,
            "players": [p.name for p in game_session.all_players],
        }

    return jsonify({"ok": True, "output": buf.getvalue(), **extra})


@app.route("/state")
def state():
    if not game_session:
        return jsonify({"ok": False})
    return jsonify({
        "ok":     True,
        "round":  game_session.round_count,
        "dealer": game_session.dealer_name,
        "players": [p.name for p in game_session.all_players],
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"

    print("\n  Drinking Blackjack Referee — Web Mode")
    print(f"  Local:   http://localhost:5000")
    print(f"  iPhone:  http://{local_ip}:5000  (same WiFi)")
    print("  (Ctrl+C to stop)\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
