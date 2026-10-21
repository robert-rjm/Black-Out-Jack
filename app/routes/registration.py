"""
app/routes/registration.py
===========================
Registration and seat routes.

POST /register, /request_local_seat, /handle_seat_transfer,
     /handle_registration, /reset_registration
"""

from flask import Blueprint, jsonify, request
from app.services.session_store import game_sessions
from app.services.validators import sanitize_name
from app.routes._auth import _require_admin
from app.services.serializer import serialize_state
from app.services.drink_rate import offer_late_join_boost
from app.config import MAX_REG_DENIALS

bp = Blueprint("registration", __name__)


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
                # A human replacing a bot mid-game is a late joiner: offer a
                # recommended catch-up booster (Drink Rate Mode).
                offer_late_join_boost(session, target_client_id, claimed_player.name)
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
