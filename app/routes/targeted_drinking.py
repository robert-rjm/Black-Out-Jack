"""
app/routes/targeted_drinking.py
===============================
Targeted Drinking routes (player + admin).

POST /targeted_drinking/vote, /begin, /propose_target, /vote_proposal, /give_sip
POST /targeted_drinking/start    — Admin picks target(s) and force-starts the mode
POST /targeted_drinking/cancel   — Host or dealer ends the mode immediately
POST /targeted_drinking/continue — Host or dealer skips the reveal pause
"""

import time
import time as _time
from flask import Blueprint, jsonify, request
from markupsafe import escape
from app.services.session_store import game_sessions
from app.services.serializer import serialize_state
from app.services.validators import sanitize_name
from app.services.targeted_drinking import (
    start_targeted_drinking,
    end_targeted_drinking,
    submit_targeted_drinking_vote,
    request_targeted_drinking_start,
    give_targeted_drinking_sip,
    propose_targeted_drinking_target,
    submit_target_proposal_vote,
)
from app.config import TARGETED_DRINKING_REVEAL_PAUSE_SECONDS
from app.routes._auth import _require_admin, _require_host_or_dealer

bp = Blueprint("targeted_drinking", __name__)


@bp.route("/targeted_drinking/give_sip", methods=["POST"])
def targeted_drinking_give_sip():
    """Perfect-graduation winner hands their bonus sip(s) to a chosen
    player. Body: { room_code, client_id, giver_name, recipient_name }
    giver_name must be one of the client's local_names and have a pending
    handout. Mirrors /dealer_lottery/give_sip exactly.
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

    result = session.drinks.last_targeted_drinking_result or {}
    if giver_name not in result.get("pending_handouts", {}):
        return jsonify({"ok": False, "error": "No pending handout for this player."})
    if giver_name in session.round._targeted_drinking_handouts_given:
        return jsonify({"ok": False, "error": "Already given."})

    if not give_targeted_drinking_sip(session, giver_name, recipient_name):
        return jsonify({"ok": False, "error": "Could not give sip — check the recipient."})

    log_line = f"  🏆 Targeted Drinking: {giver_name} gives their sip(s) to {recipient_name}\n"
    session.round._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})


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


@bp.route("/targeted_drinking/propose_target", methods=["POST"])
def targeted_drinking_propose_target():
    """A registered non-spectator player taps another player's name to
    propose them as a Targeted Drinking target -- one of three ways a
    subgame can start (alongside the host's direct override and the Wild
    Card easter egg). Opens a table-wide Yes/No vote (see
    propose_targeted_drinking_target); fails if the proposer is currently
    frozen from a prior failed proposal, the subgame is already running or
    on cooldown, a proposal is already open, or the target is invalid.
    Body: { room_code, client_id, target_name }
    """
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = sanitize_name(data.get("target_name") or "")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    proposer_name = info.get("name") or ""
    if not proposer_name:
        return jsonify({"ok": False, "error": "Spectators cannot propose a target."})

    ok, error = propose_targeted_drinking_target(session, proposer_name, target_name)
    if not ok:
        return jsonify({"ok": False, "error": error})

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/vote_proposal", methods=["POST"])
def targeted_drinking_vote_proposal():
    """Any eligible voter casts their Yes/No vote on the pending target
    proposal -- resolves immediately (starting the subgame) the instant
    strict majority says Yes; otherwise resolves on timeout via the tick's
    apply_target_proposal_vote_forfeit.
    Body: { room_code, client_id, vote: bool }
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    vote      = bool(data.get("vote"))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    voter_name = info.get("name") or ""
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})

    if not submit_target_proposal_vote(session, voter_name, vote):
        return jsonify({"ok": False, "error": "No proposal is currently open for you to vote on."})

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/start", methods=["POST"])
def targeted_drinking_start():
    """Admin starts Targeted Drinking Mode against one or more players.
    Body: { room_code, client_id, target_names: [str, ...] }"""
    data        = request.json or {}
    raw_names   = data.get("target_names") or []
    session, client_id, _, err = _require_admin(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    if not isinstance(raw_names, list) or not raw_names:
        return jsonify({"ok": False, "error": "No target players provided."})
    target_names = [sanitize_name(n) for n in raw_names if isinstance(n, str) and n.strip()]
    if not target_names:
        return jsonify({"ok": False, "error": "No target players provided."})

    if not start_targeted_drinking(session, target_names):
        return jsonify({"ok": False, "error": "Could not start Targeted Drinking Mode (already active, on cooldown, or invalid target)."})

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/cancel", methods=["POST"])
def targeted_drinking_cancel():
    """Host or current dealer ends Targeted Drinking Mode immediately.
    Body: { room_code, client_id }"""
    data = request.json or {}
    session, client_id, _, err = _require_host_or_dealer(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    end_targeted_drinking(session, reason="admin_cancelled")
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/targeted_drinking/continue", methods=["POST"])
def targeted_drinking_continue():
    """Host or current dealer skips the remaining reveal-pause breather so
    the next mini-round can open immediately instead of waiting out the
    flat safety-net timeout (TARGETED_DRINKING_REVEAL_PAUSE_SECONDS) --
    fixes laggy clients getting swept into the next mini-round before
    they've actually seen the current one's hand play out, by letting
    whoever's watching the table for everyone drive the pace explicitly.
    No-op (still ok) if there's no in-flight reveal to advance past, or if
    the breather has already elapsed naturally.
    Body: { room_code, client_id }"""
    data = request.json or {}
    session, client_id, _, err = _require_host_or_dealer(data)
    if err:
        return jsonify({"ok": False, "error": escape(err)})

    result = session.drinks.last_targeted_drinking_result
    if result:
        earliest = time.monotonic() - TARGETED_DRINKING_REVEAL_PAUSE_SECONDS
        result["set_at"] = min(result["set_at"], earliest)

    return jsonify({**serialize_state(session, client_id), "ok": True})
