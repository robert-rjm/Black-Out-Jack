"""
app/routes/polling.py
======================
Read-mostly player-interaction routes: state polling, client registration,
pre-selections, dealer suggestions, and insurance votes.

GET  /state                  — Full game-state snapshot (SSE-style polling)
POST /register               — Joining client claims a seat or becomes spectator
POST /preselect               — Player pre-votes their intended action
POST /suggest_action          — Dealer suggests a different action to a player
POST /respond_suggest         — Player accepts or declines a dealer suggestion
POST /vote_insurance          — Player casts their insurance vote
POST /give_bust_sip           — Bust vote winner hands out their 1-sip reward
POST /dealer_lottery/enter    — Player submits their Dealer Lottery entry (0-5)
POST /dealer_lottery/give_sip — Dealer Lottery credit-winner hands out their sip(s)
POST /targeted_drinking/vote        — Targeted player casts their bust/stand vote
POST /targeted_drinking/begin       — Host or dealer kicks off the waiting mini-round
POST /targeted_drinking/vote_target — Any player casts/retracts a vote to target someone
"""

import logging
import time as _time

from flask import Blueprint, jsonify, request

from app.services.session_store import (
    game_sessions, _room_last_access, cleanup_stale_sessions,
    mark_waiting_client, get_waiting_clients,
)
from app.services.validators import sanitize_name, is_dealer_client
from app.routes.admin import _require_admin, _require_host_or_dealer
from app.services.serializer import (
    serialize_state, round_phase, current_turn, hand_done,
    compute_mandatory_split10,
)
from app.services.drink_tracker import award_sips
from app.services.dealer_lottery import (
    submit_dealer_lottery_entry,
    resolve_dealer_lottery,
    give_dealer_lottery_sip,
)
from app.services.targeted_drinking import (
    submit_targeted_drinking_vote,
    request_targeted_drinking_start,
    start_targeted_drinking,
)
from app.services.payout_tracker import init_bankrolls
from app.services.game_engine import auto_play_npc_turns
from app.services.tick import tick, _run_deferred_dealer_play
from app.config import MAX_REG_DENIALS

log = logging.getLogger(__name__)

_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 3600   # run cleanup at most once per hour

bp = Blueprint("polling", __name__)


# ---------------------------------------------------------------------------
# State snapshot
# ---------------------------------------------------------------------------

@bp.route("/state")
def state():
    global _last_cleanup
    room_code = request.args.get("room_code", "")
    client_id = request.args.get("client_id", "")
    session   = game_sessions.get(room_code)
    if session is not None:
        _room_last_access[room_code] = _time.monotonic()
    # Periodically evict sessions idle for more than 24 hours
    now = _time.monotonic()
    if now - _last_cleanup > _CLEANUP_INTERVAL:
        _last_cleanup = now
        cleanup_stale_sessions()
    if session is not None:
        tick(session)

    if session is None:
        if room_code in game_sessions:
            mark_waiting_client(room_code, client_id)
            return jsonify({
                "ok": True,
                "waiting": True,
                "waiting_count": len(get_waiting_clients(room_code)),
            })
        return jsonify({"ok": False})

    return jsonify(serialize_state(session, client_id))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@bp.route("/register", methods=["POST"])
def register():
    """A joining client claims a seat or becomes spectator.
    Body: { room_code, client_id, name }  — name="" means spectator."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    name      = sanitize_name((data.get("name") or "").strip())

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    # Guards the whole check-then-mutate sequence below (seat-claimed check,
    # pending-slot cap, then the writes) against a concurrent /register call
    # for the same seat -- see docs/planning/Code-Audit-2026-07.md #4.
    with session._registry_lock:
        existing = session._room_clients.get(client_id, {})
        if existing.get("kicked"):
            if not name:
                # Kicked player wants to spectate — allow it, clear kicked flag
                session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
                # Remove any pending rejoin request for this client
                session._rejoin_requests = [r for r in session._rejoin_requests
                                            if r["client_id"] != client_id]
                return jsonify({**serialize_state(session, client_id), "ok": True})
            return jsonify({"ok": False, "error": "You have been removed from this session."})

        if not name:
            # Spectating — no approval needed
            session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
            return jsonify({**serialize_state(session, client_id), "ok": True})

        valid_names = [p.name for p in session.all_players]
        if name not in valid_names:
            return jsonify({"ok": False,
                            "error": f"'{name}' is not a seat. Available: {', '.join(valid_names)}"})

        # Check seat is not already claimed
        for cid, info in session._room_clients.items():
            if (cid != client_id and not info.get("kicked")
                    and (info.get("name") or "").lower() == name.lower()):
                return jsonify({"ok": False, "error": f"'{name}' is already taken."})

        # Admin registering their own seat — immediate, no approval needed
        if existing.get("role") == "admin":
            # Preserve existing local_names; ensure the newly claimed name is in it
            local_names = existing.get("local_names") or []
            if name not in local_names:
                local_names = [name] + [n for n in local_names if n != name]
            session._room_clients[client_id] = {
                **existing, "name": name, "role": "admin", "kicked": False,
                "local_names": local_names,
            }
            return jsonify({**serialize_state(session, client_id), "ok": True})

        # Block clients who have been denied too many times
        if existing.get("reg_denials", 0) >= MAX_REG_DENIALS:
            return jsonify({"ok": False,
                            "error": "You have been denied too many times and cannot request to join."})

        # Cancel any previous pending request from this client (counts as one slot)
        prev_pending = [r for r in session._pending_registrations if r["client_id"] != client_id]

        # Cap: no more pending requests than there are unclaimed seats
        total_seats   = len(session.all_players)
        claimed_seats = sum(
            1 for info in session._room_clients.values()
            if info.get("name") and not info.get("kicked")
        )
        available_seats = total_seats - claimed_seats
        if len(prev_pending) >= available_seats:
            return jsonify({"ok": False,
                            "error": "Too many pending requests — wait for the host to review."})

        session._pending_registrations = prev_pending
        session._pending_registrations.append({"client_id": client_id, "name": name})
        session._room_clients[client_id] = {**existing, "name": None, "role": "pending", "kicked": False}
        return jsonify({**serialize_state(session, client_id), "ok": True, "pending": True})


# ---------------------------------------------------------------------------
# Registration approval
# ---------------------------------------------------------------------------


@bp.route("/request_local_seat", methods=["POST"])
def request_local_seat():
    """Registered player requests to add another seat as a local player.
    Body: { room_code, client_id, name }
    Goes through the same admin-approval flow as /register, but on approval
    the name is appended to the requester's local_names rather than replacing
    their primary registration.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    name      = sanitize_name((data.get("name") or "").strip())

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    existing = session._room_clients.get(client_id, {})
    role = existing.get("role")
    if role not in ("player", "admin"):
        return jsonify({"ok": False, "error": "Must be registered to add a local seat."})

    if not name:
        return jsonify({"ok": False, "error": "Name required."})

    valid_names = [p.name for p in session.all_players]
    if name not in valid_names:
        return jsonify({"ok": False, "error": f"'{name}' is not a seat in this game."})

    # Guards the whole check-then-mutate sequence below (seat-claimed check,
    # then queueing a transfer/registration or auto-approving) against a
    # concurrent request for the same seat -- see
    # docs/planning/Code-Audit-2026-07.md #4.
    with session._registry_lock:
        # Check if seat is claimed by another client's primary registration or local_names
        name_lower = name.lower()
        for cid, info in session._room_clients.items():
            if cid == client_id or info.get("kicked"):
                continue
            if (info.get("name") or "").lower() == name_lower:
                return jsonify({"ok": False, "error": f"'{name}' is already taken."})
            if any(n.lower() == name_lower for n in (info.get("local_names") or [])):
                # Seat is locally controlled by someone else — queue a transfer request
                # (remove any previous request for this same seat first)
                session._pending_seat_transfers = [
                    t for t in session._pending_seat_transfers if t["target"].lower() != name_lower
                ]
                requester_display = existing.get("name") or "Someone"
                session._pending_seat_transfers.append({
                    "requester_cid":  client_id,
                    "requester_name": requester_display,
                    "target":         name,
                    "controller_cid": cid,
                })
                return jsonify({**serialize_state(session, client_id), "ok": True, "transfer_pending": True})

        # Already a local name for this client
        local_names = existing.get("local_names") or []
        if name.lower() in {(n or "").lower() for n in local_names}:
            return jsonify({"ok": False, "error": f"'{name}' is already a local seat."})

        # Admin requesting an unclaimed seat: auto-approve immediately (no popup needed —
        # the admin IS the approver, so routing their own request through the queue just
        # blocks the game with the register overlay).
        if existing.get("role") == "admin":
            local_names = list(existing.get("local_names") or [])
            if not any(n.lower() == name.lower() for n in local_names):
                local_names.append(name)
            existing["local_names"] = local_names
            session._room_clients[client_id] = existing
            # If the seat was NPC, convert to human
            claimed = next((p for p in session.all_players if p.name.lower() == name.lower()), None)
            if claimed and getattr(claimed, "is_npc", False):
                claimed.is_npc = False
            return jsonify({**serialize_state(session, client_id), "ok": True})

        # Non-admin: queue as pending with add_to_local flag, await admin approval
        session._pending_registrations = [
            r for r in session._pending_registrations if r["client_id"] != client_id
        ]
        session._pending_registrations.append({
            "client_id":    client_id,
            "name":         name,
            "add_to_local": True,
        })
        return jsonify({**serialize_state(session, client_id), "ok": True, "pending": True})



@bp.route("/handle_seat_transfer", methods=["POST"])
def handle_seat_transfer():
    """Current local-seat controller approves or denies a seat transfer request.
    Body: { room_code, client_id (controller), target, approve: bool }
    On approval: removes seat from controller's local_names, adds to requester's.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    target    = sanitize_name((data.get("target") or "").strip())
    approve   = bool(data.get("approve"))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    existing = session._room_clients.get(client_id, {})
    if existing.get("role") not in ("player", "admin"):
        return jsonify({"ok": False, "error": "Not authorised."})

    target_lower = target.lower()

    # Guards the whole check-then-mutate sequence below (transfer lookup,
    # then removing it and applying local_names) against a concurrent
    # approval for the same transfer -- see
    # docs/planning/Code-Audit-2026-07.md #4.
    with session._registry_lock:
        # Find the matching pending transfer (this client must be the controller)
        transfer = next(
            (t for t in session._pending_seat_transfers
             if t["target"].lower() == target_lower and t["controller_cid"] == client_id),
            None,
        )
        if not transfer:
            return jsonify({"ok": False, "error": "No pending transfer found."})

        # Remove the request regardless of outcome
        session._pending_seat_transfers = [
            t for t in session._pending_seat_transfers
            if not (t["target"].lower() == target_lower and t["controller_cid"] == client_id)
        ]

        if approve:
            # Remove seat from controller's local_names
            ctrl_locals = existing.get("local_names") or []
            existing["local_names"] = [n for n in ctrl_locals if n.lower() != target_lower]
            session._room_clients[client_id] = existing

            # Add seat to requester's local_names.
            # Seed list with their primary name first so my_names always includes
            # their own seat (serializer uses local_names when non-empty).
            req_cid  = transfer["requester_cid"]
            req_info = session._room_clients.get(req_cid, {})
            req_locals = list(req_info.get("local_names") or [])
            if not req_locals and req_info.get("name"):
                req_locals = [req_info["name"]]
            if not any(n.lower() == target_lower for n in req_locals):
                req_locals.append(target)
            req_info["local_names"] = req_locals
            session._room_clients[req_cid] = req_info

        return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/handle_registration", methods=["POST"])
def handle_registration():
    """Admin approves or denies a pending player registration.
    Body: { room_code, client_id (admin), target_client_id, approve: bool }"""
    data             = request.json or {}
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": err})

    # Guards the whole check-then-mutate sequence below (pending lookup,
    # seat-still-unclaimed check, then the writes) against a concurrent
    # approval/denial for the same request -- see
    # docs/planning/Code-Audit-2026-07.md #4.
    with session._registry_lock:
        pending = next(
            (r for r in session._pending_registrations if r["client_id"] == target_client_id),
            None,
        )
        if not pending:
            return jsonify({"ok": False, "error": "No pending request found."})

        session._pending_registrations = [
            r for r in session._pending_registrations if r["client_id"] != target_client_id
        ]

        target_existing = session._room_clients.get(target_client_id, {})

        if approve:
            name = pending["name"]
            # Ensure seat is still unclaimed before approving
            for cid, info in session._room_clients.items():
                if (cid != target_client_id and not info.get("kicked")
                        and (info.get("name") or "").lower() == name.lower()):
                    # Seat taken while pending — count as a denial
                    denials = target_existing.get("reg_denials", 0) + 1
                    session._room_clients[target_client_id] = {
                        **target_existing, "name": None, "role": "denied",
                        "kicked": False, "reg_denials": denials,
                    }
                    return jsonify({**serialize_state(session, client_id), "ok": True})
            if pending.get("add_to_local"):
                # Append to requester local_names without changing primary name/role.
                # Seed with primary name first so my_names always includes own seat.
                existing_local = list(target_existing.get("local_names") or [])
                if not existing_local and target_existing.get("name"):
                    existing_local = [target_existing["name"]]
                if not any(n.lower() == name.lower() for n in existing_local):
                    existing_local.append(name)
                session._room_clients[target_client_id] = {
                    **target_existing, "local_names": existing_local, "kicked": False
                }
            else:
                session._room_clients[target_client_id] = {
                    **target_existing, "name": name, "role": "player", "kicked": False
                }
            # If the claimed seat was an NPC, convert them to human so auto-play stops
            claimed_player = next(
                (p for p in session.all_players if p.name.lower() == name.lower()), None
            )
            if claimed_player and getattr(claimed_player, "is_npc", False):
                claimed_player.is_npc = False
                # Clear the bot's auto-voted "pass" so the new human can vote
                # if the bust-vote window is still open.
                if session.round._bust_votes.get(claimed_player.name) == "pass":
                    session.round._bust_votes.pop(claimed_player.name, None)
            # Seat is now claimed — remove from admin's local_names
            for info in session._room_clients.values():
                if info.get("role") == "admin":
                    local_names = info.get("local_names") or []
                    info["local_names"] = [n for n in local_names if n.lower() != name.lower()]
                    break
        else:
            denials = target_existing.get("reg_denials", 0) + 1
            session._room_clients[target_client_id] = {
                **target_existing, "name": None, "role": "denied",
                "kicked": False, "reg_denials": denials,
            }

        return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/reset_registration", methods=["POST"])
def reset_registration():
    """Admin clears a client's denial count, allowing them to request again.
    Body: { room_code, client_id (admin), target_client_id }"""
    data             = request.json or {}
    target_client_id = (data.get("target_client_id") or "").strip()
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": err})

    target = session._room_clients.get(target_client_id)
    if not target:
        return jsonify({"ok": False, "error": "Client not found."})

    session._room_clients[target_client_id] = {
        **target, "role": "spectator", "reg_denials": 0
    }
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Pre-selections and suggestions
# ---------------------------------------------------------------------------

@bp.route("/preselect", methods=["POST"])
def preselect():
    """Player pre-votes their intended action. Dealer sees this in the UI.
    Body: { room_code, client_id, hand, action }  action: h|s|d|sp"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    action    = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    name = info.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Spectators cannot pre-select actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    # House rule: pre-selecting HIT, STAND, or DOUBLE on a hand the
    # "mandatory split 10s" rule applies to opens the "Play with honor /
    # <action> without honor (1 sip)" prompt (state.honor_pending) instead
    # of recording a plain action vote.
    _ACTION_NAMES = {"h": "hit", "s": "stand", "d": "double"}
    if (action in _ACTION_NAMES and session.drinking_mode
            and current_turn(session)
            and current_turn(session).lower() == name.lower()
            and compute_mandatory_split10(session, current_turn(session), round_phase(session))):
        player      = session._get_player(name)
        active_hand = next((h for h in player.hands if not hand_done(h)), None)
        if player and active_hand:
            session.round._honor_pending = {
                "player":  player.name,
                "hand_id": id(active_hand),
                "action":  _ACTION_NAMES[action],
                "reason":  "tens",
            }
            return jsonify({**serialize_state(session, client_id), "ok": True})

    session.round._preselections[f"{name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/suggest_action", methods=["POST"])
def suggest_action():
    """Dealer suggests a different action to a player, or any player suggests
    a move for an NPC bot's turn (the bot will play it automatically).
    Body: { room_code, client_id, player_name, hand, action }  action: h|s|d|sp"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()
    hand        = (data.get("hand") or "hand1").strip().lower()
    action      = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    target_player = session._get_player(target_name)
    target_is_npc = bool(target_player and getattr(target_player, "is_npc", False))

    info = session._room_clients.get(client_id, {})
    if info.get("kicked") or (info.get("role") or "spectator") == "spectator":
        return jsonify({"ok": False, "error": "Spectators can't suggest actions."})

    if not target_is_npc and not is_dealer_client(session, client_id):
        return jsonify({"ok": False, "error": "Only the dealer can suggest actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    session.round._suggestions[f"{target_name.lower()}:{hand}"] = action
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/respond_suggest", methods=["POST"])
def respond_suggest():
    """Player accepts or declines a dealer suggestion.
    Body: { room_code, client_id, hand, accept: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    accept    = bool(data.get("accept", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    name = info.get("name", "")
    key  = f"{name.lower()}:{hand}"

    suggestion  = session.round._suggestions.get(key)
    if not suggestion:
        return jsonify({"ok": False, "error": "No pending suggestion."})

    if accept:
        session.round._preselections[key] = suggestion

    session.round._suggestions.pop(key, None)
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Insurance voting
# ---------------------------------------------------------------------------

@bp.route("/vote_insurance", methods=["POST"])
def vote_insurance():
    """
    Player casts their insurance vote for a specific blackjack hand.
    Body: { room_code, client_id, bj_player, hand_idx, vote: true=insure/false=decline }
    Can be called multiple times — last vote wins.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    bj_player = sanitize_name(data.get("bj_player") or "")
    try:
        hand_idx = int(data.get("hand_idx", 0))
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "Invalid hand index."})
    vote = bool(data.get("vote", False))   # True = insure, False = decline

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    # Local multiplayer: client may specify which local seat is voting
    requested_voter = (data.get("voter_name") or "").strip().capitalize()
    local_names     = [n for n in (info.get("local_names") or []) if n]
    if requested_voter and requested_voter in local_names:
        voter_name = requested_voter
    else:
        voter_name = (info.get("name") or "").strip()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if voter_name.lower() == bj_player.lower():
        return jsonify({"ok": False, "error": "You cannot vote on your own blackjack."})

    vote_entry = next(
        (v for v in session.round._insurance_votes
         if v["player"].lower() == bj_player.lower() and v["hand_idx"] == hand_idx),
        None,
    )
    if not vote_entry:
        return jsonify({"ok": False, "error": "No insurance vote open for that hand."})
    if vote_entry.get("resolved"):
        return jsonify({"ok": False, "error": "This vote has already been resolved."})

    vote_entry["votes"][voter_name] = vote
    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Bust vote side bet
# ---------------------------------------------------------------------------

@bp.route("/cast_bust_vote", methods=["POST"])
def cast_bust_vote():
    """Player casts or updates their dealer-bust confidence vote.
    Body: { room_code, client_id, vote: "bust" | "win" }
    Can be re-cast any time before round-over — last vote wins.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    vote      = (data.get("vote") or "").strip()

    if vote not in ("bust", "pass"):
        return jsonify({"ok": False, "error": "vote must be 'bust' or 'pass'."})

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if not session.bust_vote_enabled:
        return jsonify({"ok": False, "error": "Bust vote not enabled."})

    # Reject if window is expired (simple timestamp check — avoids double-calling serializer helper)
    expires = session.round._bust_vote_expires_at
    if not expires or _time.monotonic() >= expires:
        return jsonify({"ok": False, "error": "Vote window is closed."})

    client_info = session._room_clients.get(client_id, {})
    voter_name  = client_info.get("name")
    if not voter_name:
        return jsonify({"ok": False, "error": "Not registered."})

    # Optional: vote on behalf of a specific local player (local multiplayer)
    player_name = sanitize_name((data.get("player_name") or "").strip())
    if player_name:
        local_names = client_info.get("local_names") or [voter_name]
        if player_name not in local_names:
            return jsonify({"ok": False, "error": "Not one of your local players."})
        # Validate that the named player actually exists in the game
        valid_names = {p.name for p in session.all_players}
        if player_name not in valid_names:
            return jsonify({"ok": False, "error": "Player not found."})
        voter_name = player_name

    prev_vote = session.round._bust_votes.get(voter_name)
    session.round._bust_votes[voter_name] = vote

    # Normal mode: side bet is opt-in via the "bust" vote.
    # Deduct half the main bet when a player commits to the bet, refund it
    # immediately if they switch back to "pass".  Drinking mode uses sips only.
    if not session.drinking_mode and session.mode == "digital":
        _pbets   = getattr(session, "_player_bets", {})
        side_bet = _pbets.get(voter_name, session.bet_amount) / 2
        init_bankrolls(session)   # safe no-op for players already seeded
        if vote == "bust" and prev_vote != "bust":
            # Player is placing the side bet — deduct now
            session._bankrolls[voter_name] = (
                session._bankrolls.get(voter_name, session.starting_bankroll) - side_bet
            )
        elif vote == "pass" and prev_vote == "bust":
            # Player withdrew their bet — refund
            session._bankrolls[voter_name] = (
                session._bankrolls.get(voter_name, session.starting_bankroll) + side_bet
            )

    # If every human non-dealer player has now voted, unblock NPC auto-play
    # (NPCs were holding off waiting for humans) then let the dealer run if ready.
    _human_players = [
        p for p in session.all_players
        if not getattr(p, "is_npc", False)
    ]
    if _human_players and all(session.round._bust_votes.get(p.name) is not None for p in _human_players):
        if round_phase(session) == "playing":
            auto_play_npc_turns(session)
        _run_deferred_dealer_play(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Bust vote sip handout
# ---------------------------------------------------------------------------

@bp.route("/give_bust_sip", methods=["POST"])
def give_bust_sip():
    """Bust-vote winner gives their 1-sip reward to a chosen player.
    Body: { room_code, client_id, winner_name, recipient_name, forfeit?: bool }
    If forfeit=true the winner takes the sip themselves (timer expired penalty).
    winner_name must be one of the client's local_names and a confirmed winner.
    """
    data           = request.json or {}
    room_code      = (data.get("room_code")      or "").strip()
    client_id      = (data.get("client_id")      or "").strip()
    winner_name    = sanitize_name(data.get("winner_name")    or "")
    recipient_name = sanitize_name(data.get("recipient_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    client_info = session._room_clients.get(client_id, {})
    if not client_info.get("name"):
        return jsonify({"ok": False, "error": "Not registered."})

    # winner_name must be one of this client's local players
    local_names = client_info.get("local_names") or [client_info["name"]]
    if winner_name not in local_names:
        return jsonify({"ok": False, "error": "Not one of your local players."})

    result = session.round._bust_vote_result or {}
    if not result.get("dealer_busted") or winner_name not in result.get("winners", []):
        return jsonify({"ok": False, "error": "No pending handout for this player."})

    if winner_name in session.round._bust_handouts_given:
        return jsonify({"ok": False, "error": "Already given."})

    # Recipient must be a player in the game (no self-assignment).
    valid_names = {p.name for p in session.all_players}
    if recipient_name not in valid_names:
        return jsonify({"ok": False, "error": "Recipient not found."})
    if recipient_name.lower() == winner_name.lower():
        return jsonify({"ok": False, "error": "Cannot give to yourself."})

    recipient = session._get_player(recipient_name)
    if recipient:
        recipient.add_drink(1, f"Bust vote handout from {winner_name}: +1 sip", "player")
        log.debug(f"  [bust vote] {winner_name} gives 1 sip to {recipient_name}")

    session.round._bust_handouts_given.add(winner_name)
    session.round._bust_handout_log.append({
        "winner":    winner_name,
        "recipient": recipient_name,
        "forfeited": False,
    })
    if all(w in session.round._bust_handouts_given for w in result.get("winners", [])):
        session.round._bust_handout_expires_at = None
        session._bust_handout_seq += 1

    # harvest_drink_log already ran — patch the round snapshots directly so
    # the sip shows up in the drinks panel and cumulative ticker without waiting
    # for the next round.
    award_sips(session, recipient_name, 1, "Bust vote handout",
               reason=f"Bust bet handout (from {winner_name}): +1 sip")

    # Log entry visible to all players
    log_line = f"  💥 Bust bet: {winner_name} called it — {recipient_name} drinks 1 sip\n"
    session.round._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Dealer Lottery (Rules.md §5.9)
# ---------------------------------------------------------------------------

@bp.route("/dealer_lottery/enter", methods=["POST"])
def dealer_lottery_enter():
    """Player submits their Dealer Lottery entry (0-5 sips).
    Body: { room_code, client_id, x, player_name? }
    Can be re-submitted any time before the entry window closes — last
    value wins. `player_name` optionally submits on behalf of one of this
    client's local players (shared-device seats), mirroring /cast_bust_vote.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    try:
        x = int(data.get("x"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "x must be a number."})
    if not (0 <= x <= 5):
        return jsonify({"ok": False, "error": "x must be between 0 and 5."})

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})
    if not session.round._pending_dealer_lottery:
        return jsonify({"ok": False, "error": "No dealer lottery is open."})
    if _time.monotonic() >= session.round._pending_dealer_lottery["expires_at"]:
        return jsonify({"ok": False, "error": "Entry window is closed."})

    client_info = session._room_clients.get(client_id, {})
    entrant_name = client_info.get("name")
    if not entrant_name:
        return jsonify({"ok": False, "error": "Not registered."})

    player_name = sanitize_name((data.get("player_name") or "").strip())
    if player_name:
        local_names = client_info.get("local_names") or [entrant_name]
        if player_name not in local_names:
            return jsonify({"ok": False, "error": "Not one of your local players."})
        entrant_name = player_name

    if not submit_dealer_lottery_entry(session, entrant_name, x):
        return jsonify({"ok": False, "error": "Not an entrant in this lottery."})

    # If every entry is in (no one still awaiting a submission), resolve
    # immediately rather than making the table wait out the full window.
    pending = session.round._pending_dealer_lottery
    if pending and all(v is not None for v in pending["entries"].values()):
        resolve_dealer_lottery(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/dealer_lottery/give_sip", methods=["POST"])
def dealer_lottery_give_sip():
    """Dealer Lottery credit-winner hands their sip(s) to a chosen player.
    Body: { room_code, client_id, giver_name, recipient_name }
    giver_name must be one of the client's local_names and have a pending
    handout. Mirrors /give_bust_sip exactly.
    """
    data           = request.json or {}
    room_code      = (data.get("room_code")      or "").strip()
    client_id      = (data.get("client_id")      or "").strip()
    giver_name     = sanitize_name(data.get("giver_name")     or "")
    recipient_name = sanitize_name(data.get("recipient_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    client_info = session._room_clients.get(client_id, {})
    if not client_info.get("name"):
        return jsonify({"ok": False, "error": "Not registered."})

    local_names = client_info.get("local_names") or [client_info["name"]]
    if giver_name not in local_names:
        return jsonify({"ok": False, "error": "Not one of your local players."})

    result = session.drinks.last_dealer_lottery_result or {}
    if giver_name not in result.get("pending_handouts", {}):
        return jsonify({"ok": False, "error": "No pending handout for this player."})
    if giver_name in session.round._dealer_lottery_handouts_given:
        return jsonify({"ok": False, "error": "Already given."})

    if not give_dealer_lottery_sip(session, giver_name, recipient_name):
        return jsonify({"ok": False, "error": "Could not give sip — check the recipient."})

    log_line = f"  🎰 Dealer Lottery: {giver_name} gives their sip(s) to {recipient_name}\n"
    session.round._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/set_player_bet", methods=["POST"])
def set_player_bet():
    """Let a player change their own bet before the round is dealt.

    Only allowed during the pre-deal phase.  Each client may only set bets
    for seats they own (primary or local names).  The amount is stored in
    session._player_bets[player_name] and read by deduct_bets() at deal time.
    """
    data       = request.json or {}
    room_code  = (data.get("room_code")   or "").strip()
    client_id  = data.get("client_id")
    player_name = (data.get("player_name") or "").strip()
    raw_bet    = data.get("bet")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "room not found"})

    if round_phase(session) not in ("pre-deal", "round-over"):
        return jsonify({"ok": False, "error": "betting phase is over"})

    info = session._room_clients.get(client_id, {})
    my_names = {
        n.lower() for n in
        (info.get("local_names") or []) + ([info.get("name")] if info.get("name") else [])
        if n
    }
    if player_name.lower() not in my_names:
        return jsonify({"ok": False, "error": "not your seat"})

    # Validate and clamp: multiples of 2.5, min 2.5, max 10× default
    try:
        bet = float(raw_bet)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid bet"})

    step = 2.5
    bet  = round(round(bet / step) * step, 2)   # snap to nearest step
    bet  = max(2.5, min(bet, session.bet_amount * 20))

    if not hasattr(session, "_player_bets"):
        session._player_bets = {}
    session._player_bets[player_name] = bet


# ---------------------------------------------------------------------------
# Targeted Drinking Mode (Rules.md §5.10, MVP scope)
# ---------------------------------------------------------------------------

@bp.route("/targeted_drinking/vote", methods=["POST"])
def targeted_drinking_vote():
    """Targeted player casts or updates their mandatory bust/stand vote for
    the current mini-round. Body: { room_code, client_id, vote: "bust" | "stand", player_name? }
    Can be re-cast any time before the mini-round's vote window closes --
    last vote wins. `player_name` optionally votes on behalf of one of this
    client's local players (shared-device seats), mirroring /cast_bust_vote.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    vote      = (data.get("vote") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    pending = session.round._pending_targeted_drinking
    if not pending or _time.monotonic() >= pending["expires_at"]:
        return jsonify({"ok": False, "error": "Vote window is closed."})

    client_info = session._room_clients.get(client_id, {})
    voter_name  = client_info.get("name")
    if not voter_name:
        return jsonify({"ok": False, "error": "Not registered."})

    player_name = sanitize_name((data.get("player_name") or "").strip())
    if player_name:
        local_names = client_info.get("local_names") or [voter_name]
        if player_name not in local_names:
            return jsonify({"ok": False, "error": "Not one of your local players."})
        voter_name = player_name

    if not submit_targeted_drinking_vote(session, voter_name, vote):
        return jsonify({"ok": False, "error": "Invalid vote, or not a current target."})

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/begin", methods=["POST"])
def targeted_drinking_begin():
    """Host or current dealer kicks off the mini-round that's waiting on
    "Start Targeting Now" -- lets the table finish drinking for the round
    that just ended before the mini-game's modal takes over.
    Body: { room_code, client_id }. No-op (still returns ok) if nothing is
    actually waiting to start, e.g. a race with another tap.
    """
    data = request.json or {}
    session, client_id, _, err = _require_host_or_dealer(data)
    if err:
        return jsonify({"ok": False, "error": err})

    request_targeted_drinking_start(session)
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/vote_target", methods=["POST"])
def targeted_drinking_vote_target():
    """Any registered non-spectator player casts or retracts a vote to
    target a player for Targeted Drinking Mode -- one of three ways a
    subgame can start (alongside the host's direct override and the Wild
    Card easter egg). Toggles; auto-starts at strict majority, mirroring
    vote_kick's exact math (app/routes/admin.py).
    Body: { room_code, client_id, target_name }
    """
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = sanitize_name(data.get("target_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = session._room_clients
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    voter_name = (info.get("name") or "").lower()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if voter_name == target_name.lower():
        return jsonify({"ok": False, "error": "Cannot vote to target yourself."})

    if session._targeted_drinking_active:
        return jsonify({"ok": False, "error": "Targeted Drinking Mode is already running."})
    if session.round_count < session._targeted_drinking_cooldown_until_round:
        return jsonify({"ok": False, "error": "Targeted Drinking Mode is on cooldown."})

    # Verify target is a real player in this game (bots included in
    # all_players but excluded below) -- mirrors start_targeted_drinking's
    # own validation, not vote_kick's _room_clients connectivity check:
    # unlike a kick target, a Targeted Drinking target doesn't need an
    # active browser session of their own to be voted for.
    target_player = session._get_player(target_name)
    if target_player is None:
        return jsonify({"ok": False, "error": f"'{target_name}' is not in the session."})
    if getattr(target_player, "is_npc", False):
        return jsonify({"ok": False, "error": "Cannot vote to target a bot."})

    key   = target_name.lower()
    votes = session._targeted_drinking_start_votes.setdefault(key, set())

    # Toggle
    if voter_name in votes:
        votes.discard(voter_name)
    else:
        votes.add(voter_name)

    # Count eligible voters: connected, named, non-spectator, non-bot, excluding the target
    all_players_lc = {
        (v.get("name") or "").lower()
        for v in clients.values()
        if not v.get("kicked") and v.get("name") and v.get("role") != "spectator"
    }
    npc_names_lc = {p.name.lower() for p in session.all_players if getattr(p, "is_npc", False)}
    eligible = all_players_lc - npc_names_lc - {key}

    started = False
    if len(eligible) > 0 and len(votes) > len(eligible) / 2:
        started = start_targeted_drinking(session, [target_name])
        # start_targeted_drinking clears _targeted_drinking_start_votes on
        # success; if it somehow failed (race with another start path
        # between the checks above and here), leave the vote in place.

    state = serialize_state(session, client_id)
    state["ok"]      = True
    state["started"] = started
    return jsonify(state)
