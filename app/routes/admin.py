"""
app/routes/admin.py
====================
Admin settings routes. Kick / rejoin / leave live in moderation.py, admin-role
handover in admin_transfer.py, player management in players.py, and the
Targeted Drinking start / cancel / continue routes in targeted_drinking.py.

POST /set_anim_pref    — Admin pushes animation preference to joiners
POST /set_hint         — Player toggles their own strategy-hint flag
POST /update_settings  — Admin queues game settings for next round
POST /claim_milestone  — Winner distributes their milestone-handout sips
POST /toggle_god_mode  — Admin toggles god mode
POST /set_paused       — Admin pauses / resumes the table (freezes all timers)
"""

import time

from flask import Blueprint, jsonify, request
from markupsafe import escape

from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.drink_tracker import award_sips, check_and_set_milestone, note_milestone_assigned
from app.services.validators import sanitize_name, is_offensive_name
from app.services.pause import pause_game, resume_game

from app.routes._auth import _require_admin

bp = Blueprint("admin", __name__)


# ---------------------------------------------------------------------------
# Animation preference
# ---------------------------------------------------------------------------

@bp.route("/set_anim_pref", methods=["POST"])
def set_anim_pref():
    """Admin pushes their animation preference so new joiners inherit it.
    Body: { room_code, client_id, enabled: bool }"""
    data    = request.json or {}
    enabled = bool(data.get("enabled", True))
    session, _, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    session._anim_default = enabled
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Per-player strategy hint flag (any player, no admin required)
# ---------------------------------------------------------------------------

@bp.route("/set_hint", methods=["POST"])
def set_hint():
    """Store strategy-hint preference for the calling client. Body: { room_code, client_id, enabled }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    enabled   = bool(data.get("enabled", False))
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    info = session._room_clients.get(client_id)
    if not info:
        return jsonify({"ok": False, "error": "Client not found."})
    # Collect all seat names controlled by this client (primary + all local seats)
    primary     = (info.get("name") or "").lower()
    local_names = [n.lower() for n in (info.get("local_names") or []) if n]
    all_names   = list({primary} | set(local_names)) if primary else local_names
    if not all_names:
        return jsonify({"ok": False, "error": "No seat claimed."})
    # Store on the session object so it's shared across all clients' polls
    if not hasattr(session, "_hint_seats"):
        session._hint_seats = set()
    for name in all_names:
        if enabled:
            session._hint_seats.add(name)
        else:
            session._hint_seats.discard(name)
    return jsonify({**serialize_state(session, client_id), "ok": True})


# Update settings
# ---------------------------------------------------------------------------

@bp.route("/update_settings", methods=["POST"])
def update_settings():
    """Queue game settings to apply at the start of the next round (admin only)."""
    data = request.json or {}
    session, client_id, admin_info, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})
    clients = session._room_clients

    admin_name_lc = (admin_info.get("name") or "").lower()
    queued = session._queued_settings

    # Validate and queue each provided setting
    try:
        if "wager" in data:
            v = int(data["wager"])
            if v >= 1:
                queued["wager"] = v

        if "num_hands" in data:
            v = int(data["num_hands"])
            if v >= 1:
                queued["num_hands"] = v

        if "num_decks" in data:
            v = int(data["num_decks"])
            if 1 <= v <= 8:
                queued["num_decks"] = v
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid numeric setting."})

    if "add_player" in data:
        name   = sanitize_name(str(data.get("add_player") or ""))
        is_npc = bool(data.get("add_player_npc", False))
        if name and is_offensive_name(name):
            return jsonify({"ok": False, "error": f"Name not allowed: {name}. Please choose something else."})
        if name:
            adds = queued.get("add_players", [])
            if not any(a["name"] == name for a in adds):
                adds.append({"name": name, "is_npc": is_npc})
            queued["add_players"] = adds

    if "remove_player" in data:
        name = sanitize_name(str(data.get("remove_player") or ""))
        if name:
            if name.lower() == admin_name_lc:
                return jsonify({"ok": False, "error": "Cannot remove your own seat."})
            target = next(
                (p for p in session.all_players if p.name.lower() == name.lower()),
                None,
            )
            if target and getattr(target, "is_dealer", False):
                return jsonify({"ok": False, "error": "Cannot remove the current dealer's seat."})
            removes = queued.get("remove_players", [])
            if name not in removes:
                removes.append(name)
            queued["remove_players"] = removes

    if "clear_queued" in data and data["clear_queued"]:
        queued = {}

    # dealer_rotate_every is a live setting — applied immediately, not queued
    if "dealer_rotate_every" in data:
        try:
            v = int(data["dealer_rotate_every"])
            if v >= 1:
                session._dealer_rotate_every = v
        except (ValueError, TypeError):
            pass   # silently ignore a malformed value; non-critical setting

    # easy_mode — queued, takes effect next round
    if "easy_mode" in data:
        queued["easy_mode"] = bool(data["easy_mode"])

    # drinking_mode — queued, takes effect next round (same table, same seats).
    # One-way: a Normal table can graduate to Drinking, never the reverse.
    # Asking for the mode the table is already in cancels a pending switch.
    if "drinking_mode" in data:
        want = bool(data["drinking_mode"])
        if session.drinking_mode and not want:
            return jsonify({"ok": False,
                            "error": "A Drinking table can't switch back to Normal mode."})
        if want == session.drinking_mode:
            queued.pop("drinking_mode", None)
        else:
            queued["drinking_mode"] = want

    # bust_vote_enabled is a live setting — toggled immediately
    if "bust_vote_enabled" in data:
        session.bust_vote_enabled = bool(data["bust_vote_enabled"])
        session.round._bust_votes = {}   # clear any stale votes when toggling

    # strategy_hint_enabled (basic-strategy "best play" blue border) — live setting
    if "strategy_hint_enabled" in data:
        session.strategy_hint_enabled = bool(data["strategy_hint_enabled"])

    # buyin_handouts — Normal-mode perk, live setting
    if "buyin_handouts" in data:
        session.buyin_handouts = bool(data["buyin_handouts"])

    # wild_card_enabled — admin can disable the logo Easter egg (live setting)
    if "wild_card_enabled" in data:
        session.wild_card_enabled = bool(data["wild_card_enabled"])

    # local_names — update which seats this admin client controls directly (live)
    if "local_names" in data:
        raw_names = data["local_names"]
        if isinstance(raw_names, list):
            valid_names = {p.name for p in session.all_players}
            cleaned = [sanitize_name(n) for n in raw_names if isinstance(n, str)]
            cleaned = [n for n in cleaned if n in valid_names]
            clients[client_id]["local_names"] = cleaned

    session._queued_settings = queued
    state = serialize_state(session, client_id)
    state["output"] = ""
    return jsonify(state)


# ---------------------------------------------------------------------------
# Milestone claim
# ---------------------------------------------------------------------------

@bp.route("/claim_milestone", methods=["POST"])
def claim_milestone():
    """
    Winner submits their sip-handout allocation.
    Body: { room_code, client_id, allocations: {player_name: sips, ...} }

    Rules enforced server-side:
      - Only the milestone winner may submit.
      - Cannot allocate to self.
      - Total must not exceed the milestone's handout value (boundary-scaled).
      - Each allocation must be a non-negative integer.
      - Must be submitted before the TTL expires.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    milestone = session.round._pending_milestone
    if not milestone:
        return jsonify({"ok": False, "error": "No active milestone."})
    if time.monotonic() >= milestone["expires_at"]:
        session.round._pending_milestone = None
        return jsonify({"ok": False, "error": "Milestone claim window has expired."})

    # Verify caller is the winner
    clients     = session._room_clients
    caller_info = clients.get(client_id, {})
    caller_name = caller_info.get("name", "")
    if caller_name.lower() != milestone["winner"].lower():
        return jsonify({"ok": False, "error": "Only the milestone winner can submit the handout."})

    raw_alloc = data.get("allocations", {})
    if not isinstance(raw_alloc, dict):
        return jsonify({"ok": False, "error": "allocations must be an object."})

    # Validate: non-negative ints, no self-allocation, real players, sum = handout total
    # Build a lowercase→canonical map so allocation keys are always the server-side
    # canonical name regardless of how the client cased them.
    canonical_names = {p.name.lower(): p.name for p in session.all_players}
    alloc: dict[str, int] = {}
    for name, sips in raw_alloc.items():
        try:
            s = int(sips)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": f"Invalid sip count for {name}."})
        if s < 0:
            return jsonify({"ok": False, "error": "Sip counts must be non-negative."})
        if name.lower() == caller_name.lower():
            return jsonify({"ok": False, "error": "Cannot assign sips to yourself."})
        canonical = canonical_names.get(name.lower())
        if canonical is None:
            return jsonify({"ok": False, "error": f"Unknown player '{escape(name)}'."})
        if s > 0:
            alloc[canonical] = s

    handout_cap  = milestone["handout"]
    total = sum(alloc.values())
    if total > handout_cap:
        return jsonify({"ok": False,
                        "error": f"Cannot assign more than {handout_cap} sips (got {total})."})

    residual     = handout_cap - total
    winner_name  = milestone["winner"]
    boundary_val = milestone["boundary"]

    # Award sips to each recipient and the winner's residual. award_sips()
    # calls check_and_set_milestone() internally, but it's a guaranteed
    # no-op for all of these — _pending_milestone is still set to *this*
    # milestone until we clear it below, so the re-check has to happen
    # explicitly afterward (see the call after _pending_milestone = None).
    winner   = milestone["winner"]
    boundary = milestone["boundary"]
    for name, s in alloc.items():
        award_sips(session, name, s, "Milestone handout",
                   reason=f"Milestone handout from {winner_name} ({boundary_val} sip milestone)")
    if residual > 0:
        award_sips(session, winner_name, residual, "Milestone residual",
                   reason=(f"Milestone residual — {winner_name} kept {residual} "
                           f"sip(s) ({boundary_val} sip milestone)"))

    # Log the handout
    log_lines = [f"🎉 {winner} reached {boundary} sips — milestone handout!"]
    for name, s in alloc.items():
        sip_word = "sip" if s == 1 else "sips"
        log_lines.append(f"  → {name} drinks {s} {sip_word}")
    if residual > 0:
        sip_word = "sip" if residual == 1 else "sips"
        log_lines.append(f"  → {winner} keeps {residual} {sip_word} (drinks them)")
    session.round._log_entries = session.round._log_entries + ["\n".join(log_lines)]
    session._log_version = session._log_version + 1

    session.round._pending_milestone     = None
    session.drinks.last_milestone_result = {
        "winner":      winner,
        "boundary":    boundary,
        "allocations": alloc,         # {name: sips} — only non-zero entries
        "set_at":      time.monotonic(),
    }

    # Winning *and* handing out two milestones in a row earns a log callout.
    # Must run before the re-check below: that can claim the next boundary
    # and resolve it on the spot for an NPC winner, which would otherwise
    # record its own handout first and make this one look non-consecutive.
    note_milestone_assigned(session, winner)

    # A handout allocation can itself push a recipient past the next
    # boundary. _pending_milestone is clear now, so this can fire.
    check_and_set_milestone(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Take back seat (local multiplayer)
# ---------------------------------------------------------------------------

@bp.route("/toggle_god_mode", methods=["POST"])
def toggle_god_mode():
    """Admin toggles God Mode on/off.
    God Mode grants admin full dealer bypass (execute any turn, deal, endround).
    Without it, admin is subject to the same turn-gate as regular players.
    """
    data = request.json or {}
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    enabled = bool(data.get("enabled", False))
    session._god_mode = enabled
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/set_paused", methods=["POST"])
def set_paused():
    """Host pauses / resumes the table. Body: { room_code, client_id, paused }"""
    data = request.json or {}
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    if bool(data.get("paused", False)):
        pause_game(session)
    else:
        resume_game(session)
    return jsonify({**serialize_state(session, client_id), "ok": True})
