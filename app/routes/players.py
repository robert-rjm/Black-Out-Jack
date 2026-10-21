"""
app/routes/players.py
=====================
Player-management routes.

POST /make_bot, /make_human, /set_bot_personality, /take_back_seat, /rotate_dealer
"""

from flask import Blueprint, jsonify, request
from markupsafe import escape
from app.services.serializer import serialize_state
from app.services.round_state import round_phase
from app.services.game_engine import auto_play_npc_turns
from app.services.room_manager import rotate_dealer as _rotate_dealer
from app.services.validators import sanitize_name
from app.routes._auth import _require_admin

bp = Blueprint("players", __name__)


@bp.route("/make_bot", methods=["POST"])
def make_bot():
    """Admin converts a seated player to an NPC bot.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    target_name = sanitize_name(data.get("player_name") or "")
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    player = next(
        (p for p in session.all_players
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{escape(target_name)}' not found."})
    if getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{escape(target_name)}' is already a bot."})

    player.is_npc = True

    # Disconnect the player's client connection if present
    for cid, info in list(clients.items()):
        if cid != client_id and (info.get("name") or "").lower() == target_name.lower():
            info["kicked"] = True  # marks as disconnected so poll loop drops them

    # Clear any pending preselections / suggestions for this player
    key_prefix = f"{target_name.lower()}:"
    for d in (session.round._preselections, session.round._suggestions):
        for k in [k for k in d if k.startswith(key_prefix)]:
            d.pop(k, None)

    # If it's the new bot's turn, auto-play immediately
    if round_phase(session) == "playing":
        auto_play_npc_turns(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/make_human", methods=["POST"])
def make_human():
    """Admin converts an NPC bot back to a human-controlled player.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    target_name = sanitize_name(data.get("player_name") or "")
    session, client_id, admin_info, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    player = next(
        (p for p in session.all_players
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{escape(target_name)}' not found."})
    if not getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{escape(target_name)}' is not a bot."})

    player.is_npc = False

    # Add the newly-human player to the admin's local_names so they can
    # control that seat (vote, act on their hand, etc.).
    current_locals = admin_info.get("local_names") or []
    if player.name not in current_locals:
        admin_info["local_names"] = current_locals + [player.name]

    # Clear any lingering auto-voted "pass" so they can cast a real vote
    # if a bust-vote window happens to be open right now.
    if session.round._bust_votes.get(player.name) == "pass":
        session.round._bust_votes.pop(player.name, None)

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/set_bot_personality", methods=["POST"])
def set_bot_personality():
    """Admin changes the personality of an NPC bot mid-round.
    Body: { room_code, client_id, player_name, personality }"""
    data        = request.json or {}
    target_name = sanitize_name(data.get("player_name") or "")
    personality = (data.get("personality") or "basic").strip().lower()
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    player = next(
        (p for p in session.all_players
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{escape(target_name)}' not found."})
    if not getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{escape(target_name)}' is not a bot."})

    player.personality    = personality
    player._style_profile = None   # clear cached profile so next decide() reloads it

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/take_back_seat", methods=["POST"])
def take_back_seat():
    """Admin reclaims a seat from a remote player, moving them to spectator.
    The seat is added back to the admin's local_names.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    player_name = (data.get("player_name") or "").strip()
    session, client_id, admin_info, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    if not player_name:
        return jsonify({"ok": False, "error": "No player name provided."})

    # Capitalise to match stored names
    player_name = sanitize_name(player_name)
    valid = {p.name for p in session.all_players}
    if player_name not in valid:
        return jsonify({"ok": False, "error": "Player not found."})

    # Demote whichever remote client currently holds this seat → spectator
    for cid, info in clients.items():
        if cid != client_id and not info.get("kicked") and \
                (info.get("name") or "").lower() == player_name.lower():
            info["name"] = None
            info["role"] = "spectator"
            break

    # Add back to admin's local_names (preserving player order)
    current_locals = admin_info.get("local_names") or []
    if not any(n.lower() == player_name.lower() for n in current_locals):
        player_order = [p.name for p in session.all_players]
        insert_at    = len(current_locals)
        try:
            target_idx = player_order.index(player_name)
            for i, n in enumerate(current_locals):
                try:
                    if player_order.index(n) > target_idx:
                        insert_at = i
                        break
                except ValueError:
                    continue  # n no longer in all_players — skip it
        except ValueError:
            pass
        current_locals = current_locals[:insert_at] + [player_name] + current_locals[insert_at:]
    admin_info["local_names"] = current_locals

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/rotate_dealer", methods=["POST"])
def rotate_dealer():
    """Admin immediately rotates the dealer to the next player (lobby/name order).
    Resets rounds_this_dealer to 1. Does not start a new round.
    Body: { room_code, client_id }"""
    data = request.json or {}
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    _rotate_dealer(session)
    session.rounds_this_dealer = 1
    return jsonify({**serialize_state(session, client_id), "ok": True})
