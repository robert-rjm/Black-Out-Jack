"""
app/routes/lobby.py
====================
Room lifecycle routes: creating a room, joining, and initial game setup.

POST /create_room — Reserve a new room code
POST /join_room   — Client joins an existing room
POST /setup       — Admin configures and starts the game session
GET  /room_invite — Join link + QR code (SVG) for a room code
"""

import io
import re
import socket
from urllib.parse import urlsplit

import segno
from flask import Blueprint, jsonify, redirect, request

from engine.style_strategy import available_profiles

from app.services.session_store import (
    game_sessions,
    reserve_room, find_room_code,
    is_join_rate_limited,
    mark_waiting_client, get_waiting_clients,
)
from app.services.validators  import sanitize_name, is_offensive_name
from app.services.serializer  import serialize_state
from app.services.room_factory import build_game_room
from app.config import DEFAULT_WAGER, DEFAULT_NUM_HANDS, DEFAULT_MODE

bp = Blueprint("lobby", __name__)

TIP_URL = "https://paypal.me/robertmichels"


@bp.route("/beer_qr")
def beer_qr():
    """QR code for the tip link, so it works even when a popup/ad blocker stops
    the PayPal tab from opening."""
    return jsonify({"ok": True, "url": TIP_URL, "svg": _qr_svg(TIP_URL)})


@bp.route("/beer")
def beer():
    """"Tip us" link target. Redirecting from our own origin keeps ad blockers
    that hide direct PayPal links from swallowing the in-game button."""
    return redirect(TIP_URL, code=302)


# ---------------------------------------------------------------------------
# Player personalities
# ---------------------------------------------------------------------------

@bp.route("/player_personalities", methods=["GET"])
def player_personalities():
    """Return a list of available player personality names (profile files present)."""
    return jsonify({"personalities": available_profiles()})


# ---------------------------------------------------------------------------
# Create room
# ---------------------------------------------------------------------------

@bp.route("/create_room", methods=["POST"])
def create_room():
    code = reserve_room()
    return jsonify({"ok": True, "code": code})


# ---------------------------------------------------------------------------
# Delete room (cancel before game starts)
# ---------------------------------------------------------------------------

@bp.route("/delete_room", methods=["POST"])
def delete_room():
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    if room_code not in game_sessions:
        return jsonify({"ok": True})  # already gone, that's fine

    session = game_sessions[room_code]

    # Slot is None before /setup is called — safe to delete immediately
    if session is None:
        del game_sessions[room_code]
        return jsonify({"ok": True})

    # Only allow deletion if the game hasn't started yet
    if session.round_count > 0:
        return jsonify({"ok": False, "error": "Game already in progress."})

    # Verify requester is the admin
    info = session._room_clients.get(client_id, {})
    if info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Only the room creator can delete it."})

    del game_sessions[room_code]
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Join room
# ---------------------------------------------------------------------------

@bp.route("/join_room", methods=["POST"])
def join_room():
    data      = request.json or {}
    raw       = (data.get("code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    # Generic error — same message whether code is malformed or absent,
    # so the response cannot be used as a room-existence oracle.
    _bad = {"ok": False, "error": "Invalid room code. Check the code and try again."}

    # Rate-limit failed join attempts per source IP to slow enumeration.
    ip   = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if is_join_rate_limited(ip):
        return jsonify({"ok": False, "error": "Too many attempts. Please wait a moment."}), 429

    # Case-insensitive lookup (codes are stored as "Ace427" etc.)
    code = find_room_code(raw)
    if code is None:
        return jsonify(_bad)

    session  = game_sessions[code]
    has_game = session is not None
    if not has_game:
        mark_waiting_client(code, client_id)
    state    = serialize_state(session, client_id)
    state["ok"]        = True
    state["has_game"]  = has_game
    state["room_code"] = code   # return canonical casing
    if not has_game:
        state["waiting_count"] = len(get_waiting_clients(code))
    return jsonify(state)


# ---------------------------------------------------------------------------
# Setup (game configuration)
# ---------------------------------------------------------------------------

@bp.route("/setup", methods=["POST"])
def setup():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "Invalid request body."})

    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    if room_code not in game_sessions:
        return jsonify({"ok": False, "error": "Room not found."})

    # Prevent any client from overwriting an active game.
    # The admin (session creator) may reconfigure; everyone else is blocked.
    existing = game_sessions[room_code]
    if existing is not None:
        if existing._room_clients.get(client_id, {}).get("role") != "admin":
            return jsonify({"ok": False, "error": "Game already in progress."})

    raw_players = data.get("players")
    if not isinstance(raw_players, list):
        return jsonify({"ok": False, "error": "Invalid players list."})
    names = [sanitize_name(n) for n in raw_players if isinstance(n, str) and n.strip()]
    names = [n for n in names if n]   # drop any that became empty after sanitization
    if not names:
        return jsonify({"ok": False, "error": "No player names provided."})
    offensive = [n for n in names if is_offensive_name(n)]
    if offensive:
        return jsonify({"ok": False,
                        "error": f"Name not allowed: {', '.join(offensive)}. Please choose something else."})

    try:
        mode       = data.get("mode", DEFAULT_MODE)
        dealer_idx = int(data.get("dealer_index", 0))
        wager      = max(1, int(data.get("wager", DEFAULT_WAGER)))
        num_hands  = max(1, int(data.get("num_hands", DEFAULT_NUM_HANDS)))
        bet_amount = max(2.5, float(data.get("bet_amount", 5)))
        starting_bankroll = max(0, float(data.get("starting_bankroll", 100)))
        # Same 1-8 clamp as /update_settings — an unbounded value can crash
        # the shoe (0 decks: deal_card() pops from an empty list) or exhaust
        # memory (a huge value allocates that many Deck() objects).
        default_decks = 2 if len(names) >= 4 else 1
        num_decks     = max(1, min(8, int(data.get("num_decks", default_decks))))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid numeric field."})
    if not (0 <= dealer_idx < len(names)):
        return jsonify({"ok": False, "error": "Invalid dealer index."})
    dealer_name = names[dealer_idx]

    npc_names = {sanitize_name(n) for n in data.get("npcs", []) if n.strip()}
    # personalities: {"BotName": "rob"} — optional, defaults to "basic"
    raw_personalities = data.get("personalities", {})
    npc_personalities = {sanitize_name(k): v.strip().lower()
                         for k, v in raw_personalities.items() if v}

    drinking = bool(data.get("drinking", True))

    room, output = build_game_room(
        room_code, client_id, names, npc_names, npc_personalities, dealer_name,
        mode=mode, drinking=drinking, wager=wager, num_hands=num_hands,
        bet_amount=bet_amount, starting_bankroll=starting_bankroll,
        num_decks=num_decks,
        bust_vote_enabled=bool(data.get("bust_vote_enabled", False)),
        easy_mode=bool(data.get("easy_mode", False)),
    )
    state  = serialize_state(room, client_id)
    state["output"] = output   # kept for host's immediate display
    return jsonify(state)


# ---------------------------------------------------------------------------
# Invite link + QR code
# ---------------------------------------------------------------------------

_CODE_RE      = re.compile(r"^[A-Za-z0-9]{1,24}$")
_LOCAL_HOSTS  = {"localhost", "127.0.0.1", "::1"}


def _lan_ip() -> str | None:
    """This machine's address on the local network, or None. Opens no
    connection: a UDP "connect" only selects the outgoing interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def _invite_base_url() -> str:
    """Public base URL of this server as the client reached it (honours the
    proxy headers hosts like Render set). When the host opened the page via
    localhost, phones cannot use that, so it is swapped for the LAN address."""
    scheme = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    host   = (request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip()
    parts  = urlsplit(f"//{host}")
    name   = parts.hostname or host
    if name in _LOCAL_HOSTS:
        name = _lan_ip() or name
    port   = f":{parts.port}" if parts.port else ""
    return f"{scheme}://{name}{port}"


def _qr_svg(text: str) -> str:
    buf = io.BytesIO()
    segno.make(text, error="m").save(
        buf, kind="svg", scale=8, border=4, xmldecl=False, nl=False,
        dark="#000000", light="#ffffff",
    )
    svg = buf.getvalue().decode("utf-8")
    # segno emits width/height but no viewBox, so CSS-resizing the SVG crops it
    # instead of scaling it. Add one so it scales to its container.
    m = re.search(r'<svg[^>]*?width="(\d+)"[^>]*?height="(\d+)"', svg)
    if m and "viewBox" not in svg:
        svg = svg.replace("<svg ", f'<svg viewBox="0 0 {m.group(1)} {m.group(2)}" ', 1)
    return svg


@bp.route("/room_invite", methods=["GET"])
def room_invite():
    """The link that joins a room and a QR code for it, as inline SVG.
    Body-less: ?code=<room code>. This encodes the code it is given and says
    nothing about whether the room exists, so it is not a room-existence oracle."""
    code = (request.args.get("code") or "").strip()
    if not _CODE_RE.match(code):
        return jsonify({"ok": False, "error": "Invalid room code."}), 400
    url = f"{_invite_base_url()}/?room={code}"
    return jsonify({"ok": True, "code": code, "url": url, "svg": _qr_svg(url)})
