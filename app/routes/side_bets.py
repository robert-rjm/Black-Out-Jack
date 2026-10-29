"""
app/routes/side_bets.py
=======================
Insurance, bust-vote, buy-in handout and stake routes.

POST /vote_insurance, /cast_bust_vote, /give_bust_sip, /buyin_handout/give, /l_handout/give,
     /set_player_bet, /confirm_stake
"""

import logging
import time as _time
from flask import Blueprint, jsonify, request
from app.services.session_store import game_sessions
from app.services.validators import sanitize_name
from app.services.serializer import serialize_state
from app.services.round_state import round_phase
from app.services.drink_tracker import award_sips
from app.services.buyin_handout import give_buyin_sip
from app.services.drink_tracker import give_l_handout
from app.services.payout_tracker import (
    init_bankrolls,
    human_names,
    stake_window_open,
    confirm_stake,
)
from app.services.game_engine import auto_play_npc_turns
from app.services.tick import _run_deferred_dealer_play

log = logging.getLogger(__name__)

bp = Blueprint("side_bets", __name__)


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
        if (vote == "bust" and prev_vote != "bust"
                and session._bankrolls.get(voter_name, session.starting_bankroll) < side_bet):
            # Can't cover the side bet -- reject without recording the vote.
            if prev_vote is None:
                session.round._bust_votes.pop(voter_name, None)
            else:
                session.round._bust_votes[voter_name] = prev_vote
            return jsonify({"ok": False, "error": "Not enough bankroll for the side bet."})
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
        recipient.add_drink(session.wager, f"Bust vote handout from {winner_name}: +{session.wager} sip{'' if session.wager == 1 else 's'}", "player", scale=False)
        log.debug(f"  [bust vote] {winner_name} gives {session.wager} sip{'' if session.wager == 1 else 's'} to {recipient_name}")

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
    award_sips(session, recipient_name, session.wager, "Bust vote handout",
               reason=f"Bust bet handout (from {winner_name}): +{session.wager} sip{'' if session.wager == 1 else 's'}",
               scale=False)

    # Log entry visible to all players
    log_line = f"  💥 Bust bet: {winner_name} called it — {recipient_name} drinks {session.wager} sip{'' if session.wager == 1 else 's'}\n"
    session.round._log_entries.append(log_line)
    session._log_version = session._log_version + 1

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/buyin_handout/give", methods=["POST"])
def buyin_handout_give():
    """Normal mode: a player above the buy-in hands out their sip, or passes.
    Body: { room_code, client_id, giver_name, recipient_name? }
    An empty recipient_name passes the handout. giver_name must be one of the
    client's local_names and have a pending handout.
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

    if not give_buyin_sip(session, giver_name, recipient_name or None):
        return jsonify({"ok": False, "error": "Could not hand out the sip."})

    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/l_handout/give", methods=["POST"])
def l_handout_give():
    """Comeback handout (L badge broken): give the sips to another player,
    or keep them (drink them yourself).
    Body: { room_code, client_id, giver_name, recipient_name? }
    An empty recipient_name keeps the handout. giver_name must be one of the
    client's local_names and have a pending handout.
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

    if not give_l_handout(session, giver_name, recipient_name or None):
        return jsonify({"ok": False, "error": "Could not hand out the sips."})

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

    if round_phase(session) != "pre-deal":
        return jsonify({"ok": False, "error": "betting phase is over"})

    info = session._room_clients.get(client_id, {})
    my_names = {
        n.lower() for n in
        (info.get("local_names") or []) + ([info.get("name")] if info.get("name") else [])
        if n
    }
    if player_name.lower() not in my_names:
        return jsonify({"ok": False, "error": "not your seat"})

    # A bot plays on at its current stake (lowered only if it can't afford it).
    seat = session._get_player(player_name)
    if seat is not None and getattr(seat, "is_npc", False):
        return jsonify({"ok": False, "error": "a bot's stake can't be changed"})

    # Validate and clamp: multiples of 2.5, min 2.5, max 10× default
    try:
        bet = float(raw_bet)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid bet"})

    step = 2.5
    bet  = round(round(bet / step) * step, 2)   # snap to nearest step
    bet  = max(2.5, min(bet, session.bet_amount * 20))

    # Normal mode: a bet can never exceed what the player can cover.
    if (not session.drinking_mode) and session.mode == "digital":
        from app.services.payout_tracker import max_affordable_bet
        cap = max_affordable_bet(session, player_name)
        if cap < step:
            return jsonify({"ok": False, "error": "Not enough bankroll to bet — re-buy first."})
        bet = min(bet, cap)

    if not hasattr(session, "_player_bets"):
        session._player_bets = {}
    session._player_bets[player_name] = bet
    return jsonify({**serialize_state(session, client_id), "ok": True, "bet": bet})


@bp.route("/confirm_stake", methods=["POST"])
def confirm_stake_route():
    """Accept the current stake for the seats this client controls while the
    Normal-mode stake window is open. The cards are dealt on the next /state
    tick once every human seat has accepted (or the window runs out).
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = data.get("client_id")

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "room not found"})
    if not stake_window_open(session):
        return jsonify({"ok": False, "error": "no stake window is open"})

    info = session._room_clients.get(client_id, {})
    my_names = {
        n.lower() for n in
        (info.get("local_names") or []) + ([info.get("name")] if info.get("name") else [])
        if n
    }
    for name in human_names(session):
        if name.lower() in my_names:
            confirm_stake(session, name)
    return jsonify({**serialize_state(session, client_id), "ok": True})
