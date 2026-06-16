"""
app/routes/admin.py
====================
Admin and player-management routes.

POST /kick             — Admin removes a client
POST /undo_kick        — Admin reinstates a kicked client as spectator
POST /make_bot         — Admin converts a player to an NPC bot
POST /transfer_admin   — Admin hands admin role to another connected player
POST /leave_room       — Client leaves; admin role auto-transferred if needed
POST /set_anim_pref    — Admin pushes animation preference to joiners
POST /vote_kick        — Player casts/retracts a vote-kick
POST /request_rejoin   — Spectator asks admin to re-seat them
POST /handle_rejoin    — Admin approves or denies a rejoin request
POST /update_settings  — Admin queues game settings for next round
POST /claim_milestone  — Winner distributes their milestone-handout sips
POST /rotate_dealer    — Admin immediately rotates the dealer seat
POST /take_back_seat   — Admin reclaims a remote seat, moving them to spectator
"""

import time

from flask import Blueprint, jsonify, request

from app.services.session_store import game_sessions
from app.services.serializer    import serialize_state, round_phase
from app.services.drink_tracker import check_and_set_milestone
from app.services.game_engine   import auto_play_npc_turns
from app.services.room_manager  import rotate_dealer as _rotate_dealer

bp = Blueprint("admin", __name__)


# ---------------------------------------------------------------------------
# Kick / undo-kick
# ---------------------------------------------------------------------------

@bp.route("/kick", methods=["POST"])
def kick():
    """Admin removes a client. Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    admin_name_lc = (admin_info.get("name") or "").lower()
    if target_name.lower() == admin_name_lc:
        return jsonify({"ok": False, "error": "Cannot kick yourself."})

    for cid, info in clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == target_name.lower()):
            info["kicked"] = True
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})


@bp.route("/undo_kick", methods=["POST"])
def undo_kick():
    """Admin reinstates a previously kicked client as a spectator.
    Body: { room_code, client_id, target_client_id }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    target_info = clients.get(target_client_id)
    if not target_info:
        return jsonify({"ok": False, "error": "Client not found."})
    if not target_info.get("kicked"):
        return jsonify({"ok": False, "error": "Player is not kicked."})

    # Reinstate as spectator — they can then request to rejoin as a player
    target_info["kicked"] = False
    target_info["role"]   = "spectator"

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Bot conversion
# ---------------------------------------------------------------------------

@bp.route("/make_bot", methods=["POST"])
def make_bot():
    """Admin converts a seated player to an NPC bot.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    player = next(
        (p for p in session.all_players
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{target_name}' not found."})
    if getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{target_name}' is already a bot."})

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
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    player = next(
        (p for p in session.all_players
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{target_name}' not found."})
    if not getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{target_name}' is not a bot."})

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


# ---------------------------------------------------------------------------
# Admin transfer
# ---------------------------------------------------------------------------

def _transfer_local_names(old_local_names: list[str], new_info: dict) -> None:
    """Merge `old_local_names` (the departing admin's controlled seats) into
    `new_info["local_names"]`, excluding the new admin's own name (which they
    already own) and de-duplicating against any seats they already control.
    If the new admin had no local_names, fall back to their single-seat name
    so the merge still has a base list to extend.
    """
    new_name = (new_info.get("name") or "").lower()
    transferred = [n for n in old_local_names if n.lower() != new_name]
    if not transferred:
        return
    existing = new_info.get("local_names") or (
        [new_info["name"]] if new_info.get("name") else []
    )
    new_info["local_names"] = existing + [n for n in transferred if n not in existing]


@bp.route("/transfer_admin", methods=["POST"])
def transfer_admin():
    """Admin hands admin role to another connected player.
    Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Find the target client
    target_cid = next(
        (cid for cid, info in clients.items()
         if cid != client_id
         and not info.get("kicked")
         and (info.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if not target_cid:
        return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})

    # Transfer: demote old admin, promote new one.
    # Move local_names to the new admin so they retain control of any local
    # multiplayer seats.  The old admin only keeps their own single seat name.
    old_local_names = admin_info.get("local_names") or []
    admin_info["role"]          = "player"
    admin_info["local_names"]   = []   # old admin loses multi-seat control
    new_admin_info              = clients[target_cid]
    new_admin_info["role"]      = "admin"
    _transfer_local_names(old_local_names, new_admin_info)

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Leave room (with auto admin transfer)
# ---------------------------------------------------------------------------

def _auto_transfer_admin(session, leaving_client_id: str) -> None:
    """Promote the first eligible player to admin when the current admin leaves."""
    clients = session._room_clients
    # Prefer players with a seat, then spectators; skip kicked/pending/denied
    ELIGIBLE = ("player", "spectator")
    candidate = next(
        (cid for cid, info in clients.items()
         if cid != leaving_client_id
         and info.get("role") in ELIGIBLE
         and not info.get("kicked")),
        None,
    )
    if not candidate:
        return
    leaving_info   = clients[leaving_client_id]
    old_local      = leaving_info.get("local_names") or []
    new_info       = clients[candidate]
    new_info["role"] = "admin"
    _transfer_local_names(old_local, new_info)


@bp.route("/leave_room", methods=["POST"])
def leave_room():
    """Client cleanly leaves the room.
    If they were admin, the role is auto-transferred to another player.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": True})   # room already gone, nothing to do

    clients = session._room_clients
    info    = clients.get(client_id, {})

    if info.get("role") == "admin":
        _auto_transfer_admin(session, client_id)

    # Remove the leaving client entirely
    clients.pop(client_id, None)
    # Clean up any pending registration requests from this client
    session._pending_registrations = [
        r for r in session._pending_registrations if r["client_id"] != client_id
    ]
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Animation preference
# ---------------------------------------------------------------------------

@bp.route("/set_anim_pref", methods=["POST"])
def set_anim_pref():
    """Admin pushes their animation preference so new joiners inherit it.
    Body: { room_code, client_id, enabled: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    enabled   = bool(data.get("enabled", True))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    if clients.get(client_id, {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    session._anim_default = enabled
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Vote-kick
# ---------------------------------------------------------------------------

@bp.route("/vote_kick", methods=["POST"])
def vote_kick():
    """Player casts or retracts a kick vote for a target player.
    Body: { room_code, client_id, target_name }
    Toggles the vote — calling again retracts it.
    Auto-kicks when strict majority of eligible voters agree."""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    voter_name = (info.get("name") or "").lower()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote to kick."})
    if voter_name == target_name.lower():
        return jsonify({"ok": False, "error": "Cannot vote to kick yourself."})

    # Verify target exists as a connected, non-bot, non-admin player
    target_info = next(
        (v for v in clients.values()
         if not v.get("kicked") and (v.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if target_info and target_info.get("role") == "admin":
        return jsonify({"ok": False, "error": "Cannot vote to kick the admin."})
    target_connected = target_info is not None
    if not target_connected:
        return jsonify({"ok": False, "error": f"'{target_name}' is not in the session."})

    key   = target_name.lower()
    votes = session.round._kick_votes.setdefault(key, set())

    # Toggle
    if voter_name in votes:
        votes.discard(voter_name)
    else:
        votes.add(voter_name)

    # Count eligible voters: all non-kicked, named, non-spectator players except the target
    all_players_lc = {
        (v.get("name") or "").lower()
        for v in clients.values()
        if not v.get("kicked") and v.get("name") and v.get("role") != "spectator"
    }
    eligible = all_players_lc - {key}  # exclude target

    # Auto-kick at strict majority
    kicked = False
    if len(eligible) > 0 and len(votes) > len(eligible) / 2:
        for cid, v in list(clients.items()):
            if (v.get("name") or "").lower() == key:
                v["kicked"] = True
        session.round._kick_votes.pop(key, None)
        kicked = True

    state = serialize_state(session, client_id)
    state["ok"]     = True
    state["kicked"] = kicked
    return jsonify(state)


# ---------------------------------------------------------------------------
# Rejoin workflow
# ---------------------------------------------------------------------------

@bp.route("/request_rejoin", methods=["POST"])
def request_rejoin():
    """Spectator (formerly kicked) asks admin to let them rejoin.
    Body: { room_code, client_id, display_name }"""
    from app.services.validators import sanitize_name
    data         = request.json or {}
    room_code    = (data.get("room_code") or "").strip()
    client_id    = (data.get("client_id") or "").strip()
    display_name = sanitize_name((data.get("display_name") or "").strip()) or "Unknown"

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not in session."})

    requests_list = session._rejoin_requests
    # Avoid duplicate requests
    if any(r["client_id"] == client_id for r in requests_list):
        return jsonify({**serialize_state(session, client_id), "ok": True})

    requests_list.append({"client_id": client_id, "display_name": display_name or "Unknown"})
    session._rejoin_requests = requests_list
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/handle_rejoin", methods=["POST"])
def handle_rejoin():
    """Admin approves or denies a rejoin request.
    Body: { room_code, client_id, target_client_id, approve: bool }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Remove from rejoin requests regardless of decision
    session._rejoin_requests = [r for r in session._rejoin_requests
                                 if r["client_id"] != target_client_id]

    if approve:
        # Remove the client entry so they get the register overlay on next poll
        clients.pop(target_client_id, None)

    state = serialize_state(session, client_id)
    state["ok"] = True
    return jsonify(state)


# ---------------------------------------------------------------------------
# Update settings
# ---------------------------------------------------------------------------

@bp.route("/update_settings", methods=["POST"])
def update_settings():
    """Queue game settings to apply at the start of the next round (admin only)."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

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
        name   = str(data["add_player"]).strip().capitalize()
        is_npc = bool(data.get("add_player_npc", False))
        if name:
            adds = queued.get("add_players", [])
            if not any(a["name"] == name for a in adds):
                adds.append({"name": name, "is_npc": is_npc})
            queued["add_players"] = adds

    if "remove_player" in data:
        name = str(data["remove_player"]).strip().capitalize()
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

    # bust_vote_enabled is a live setting — toggled immediately
    if "bust_vote_enabled" in data:
        session.bust_vote_enabled = bool(data["bust_vote_enabled"])
        session.round._bust_votes = {}   # clear any stale votes when toggling

    # strategy_hint_enabled (basic-strategy "best play" blue border) — live setting
    if "strategy_hint_enabled" in data:
        session.strategy_hint_enabled = bool(data["strategy_hint_enabled"])

    # local_names — update which seats this admin client controls directly (live)
    if "local_names" in data:
        raw_names = data["local_names"]
        if isinstance(raw_names, list):
            from app.services.validators import sanitize_name
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
    valid_names = {p.name.lower() for p in session.all_players}
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
        if name.lower() not in valid_names:
            return jsonify({"ok": False, "error": f"Unknown player '{name}'."})
        if s > 0:
            alloc[name] = s

    handout_cap  = milestone["handout"]
    total = sum(alloc.values())
    if total > handout_cap:
        return jsonify({"ok": False,
                        "error": f"Cannot assign more than {handout_cap} sips (got {total})."})

    residual     = handout_cap - total
    winner_name  = milestone["winner"]
    boundary_val = milestone["boundary"]

    # Apply to sip ticker — distributed sips go to recipients; residual goes to winner
    ticker = session._sip_ticker
    for name, s in alloc.items():
        ticker[name] = ticker.get(name, 0) + s
    if residual > 0:
        ticker[winner_name] = ticker.get(winner_name, 0) + residual
    session._sip_ticker = ticker

    # Mirror into last_round_sips and last_round_drinks so the Drinks pane
    # shows the milestone handout alongside other round drinks.
    last_sips   = dict(session._last_round_sips)
    last_drinks = list(session._last_round_drinks)
    for name, s in alloc.items():
        last_sips[name] = last_sips.get(name, 0) + s
        last_drinks.append({
            "name":   name,
            "sips":   s,
            "reason": f"Milestone handout from {winner_name} ({boundary_val} sip milestone)",
        })
    if residual > 0:
        last_sips[winner_name] = last_sips.get(winner_name, 0) + residual
        last_drinks.append({
            "name":   winner_name,
            "sips":   residual,
            "reason": f"Milestone residual — {winner_name} kept {residual} sip(s) ({boundary_val} sip milestone)",
        })
    session._last_round_sips   = last_sips
    session._last_round_drinks = last_drinks

    # Write milestone handout into the CSV accumulator so it appears in exports
    winner   = milestone["winner"]
    boundary = milestone["boundary"]
    csv_rows = session._drink_csv_rows
    for name, s in alloc.items():
        csv_rows.append({
            "round":  session.round_count,
            "dealer": session.dealer_name,
            "player": name,
            "role":   "player",
            "rule":   "Milestone handout",
            "sips":   s,
        })
    if residual > 0:
        csv_rows.append({
            "round":  session.round_count,
            "dealer": session.dealer_name,
            "player": winner,
            "role":   "player",
            "rule":   "Milestone residual",
            "sips":   residual,
        })
    session._drink_csv_rows = csv_rows

    # Check if recipients (or winner via residual) crossed a new milestone
    check_and_set_milestone(session)

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
    session._last_milestone_result = {
        "winner":      winner,
        "boundary":    boundary,
        "allocations": alloc,         # {name: sips} — only non-zero entries
        "set_at":      time.monotonic(),
    }
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Dealer rotation
# ---------------------------------------------------------------------------

@bp.route("/rotate_dealer", methods=["POST"])
def rotate_dealer():
    """Admin immediately rotates the dealer to the next player (lobby/name order).
    Resets rounds_this_dealer to 1. Does not start a new round.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    _rotate_dealer(session)
    session.rounds_this_dealer = 1
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
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    info = session._room_clients.get(client_id, {})
    if info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    enabled = bool(data.get("enabled", False))
    session._god_mode = enabled
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/take_back_seat", methods=["POST"])
def take_back_seat():
    """Admin reclaims a seat from a remote player, moving them to spectator.
    The seat is added back to the admin's local_names.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    player_name = (data.get("player_name") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = session._room_clients
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    if not player_name:
        return jsonify({"ok": False, "error": "No player name provided."})

    # Capitalise to match stored names
    from app.services.validators import sanitize_name
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
