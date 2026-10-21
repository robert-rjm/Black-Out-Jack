"""
app/routes/game_commands.py
============================
The /command dispatcher — the heart of in-game interaction.

POST /command — All game actions for both digital and referee modes.

Digital commands: deal, hit, stand, double, split, insurance, blackjack,
                  peek, dealer, endround, newround, status, help
Referee commands: deal, action, result, dealer, fouraces, endround,
                  newround, status, help
"""

import contextlib
import io
import logging

from flask import Blueprint, jsonify, request


from app.services.session_store import game_sessions
from app.services.validators import is_dealer_client
from app.services.serializer import serialize_state
from app.services.round_state import round_phase, current_turn
from app.services.game_engine import bust_vote_pending
from app.services.payout_tracker import cmd_rebuy

from app.services.player_actions import perform_action_without_honor, after_player_action
from app.routes.commands.common import PLAYER_ACTION_CMDS
from app.routes.commands.digital import DIGITAL_COMMANDS, cmd_split
from app.routes.commands.referee import REFEREE_COMMANDS

log = logging.getLogger(__name__)

bp = Blueprint("game_commands", __name__)


# ---------------------------------------------------------------------------
# Digital help text
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Strategy deviation helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Digital-mode command handlers
# ---------------------------------------------------------------------------


@bp.route("/rebuy", methods=["POST"])
def rebuy():
    """Re-buy a busted player's bankroll back to the starting amount
    (Normal mode "Bank Run" modal). Body: { room_code, client_id, player }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    player_name = (data.get("player") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    if session.drinking_mode or session.mode != "digital":
        return jsonify({**serialize_state(session, client_id), "ok": True})

    # Only the seat itself may re-buy (admin/dealer exempt, matching the
    # dealer-gate model on /command and the same check on /honor_resolve).
    if info.get("role") != "admin":
        my_names = {
            n.lower() for n in
            (info.get("local_names") or []) + ([info.get("name")] if info.get("name") else [])
            if n
        }
        if player_name.lower() not in my_names:
            return jsonify({"ok": False, "error": "Not your seat to re-buy."})

    cmd_rebuy(session, player_name)
    return jsonify({**serialize_state(session, client_id), "ok": True})


@bp.route("/honor_resolve", methods=["POST"])
def honor_resolve():
    """Resolve a pending "mandatory split 10s" house-rule prompt
    (state.honor_pending == true), drinking mode only.
    Body: { room_code, client_id, choice }  choice: "split" | "no"

    choice == "split": comply with the house rule -- splits the hand
        (equivalent to pressing SPLIT), no penalty.
    choice == "no": "play without honor" -- carries out whichever action
        the player originally attempted (hit, double, or stand —
        recorded in session.round._honor_pending["action"]) and applies a
        1-sip penalty, delivered via the existing ace-drink toast pipeline.

    Either way this is the single follow-up action -- no further button
    press is needed to complete the hand's action.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    choice    = (data.get("choice") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    info = session._room_clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    if (info.get("role") or "spectator") not in ("admin", "player"):
        return jsonify({"ok": False, "error": "Spectators cannot resolve this prompt."})

    if not session.drinking_mode or not session.round._honor_pending:
        # Nothing pending (stale request / already resolved elsewhere) -- no-op.
        return jsonify({**serialize_state(session, client_id), "ok": True})

    # Only the seat this prompt belongs to may resolve it (admin/dealer is
    # exempt, matching the dealer-gate on /command -- the dealer client is
    # allowed to act on behalf of any seat).
    if info.get("role") != "admin":
        my_names = {
            n.lower() for n in
            (info.get("local_names") or []) + ([info.get("name")] if info.get("name") else [])
            if n
        }
        if session.round._honor_pending["player"].lower() not in my_names:
            return jsonify({"ok": False, "error": "Not your prompt to resolve."})

    if choice not in ("split", "no"):
        return jsonify({"ok": False, "error": f"Invalid choice '{choice}'."})

    pending = session.round._honor_pending
    player  = session._get_player(pending["player"])
    hand    = next((h for h in player.hands if id(h) == pending["hand_id"]), None)
    if not player or not hand:
        # Hand no longer exists (shouldn't happen) -- clear and bail safely.
        session.round._honor_pending = None
        return jsonify({**serialize_state(session, client_id), "ok": True})

    session.round._honor_acked.add((player.name, id(hand)))
    session.round._honor_pending = None
    hand_label = f"hand{player.hands.index(hand) + 1}"
    session.round._preselections.pop(f"{player.name.lower()}:{hand_label}", None)

    if choice == "split":
        cmd_split(session, ["split", player.name, hand_label])
    else:
        action = pending.get("action") or "stand"
        perform_action_without_honor(session, player, hand, action)

    after_player_action(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


# ---------------------------------------------------------------------------
# Referee-mode command handlers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Command registries
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------

@bp.route("/command", methods=["POST"])
def command():
    _req         = request.json or {}
    room_code    = _req.get("room_code", "")
    game_session = game_sessions.get(room_code)
    if not game_session:
        return jsonify({"ok": False, "output": "No active session — set up a game first."})

    if game_session._paused_at is not None:
        return jsonify({**serialize_state(game_session), "rejected": True,
                        "output": "  Game is paused.\n"})

    cmd_str   = _req.get("cmd", "").strip()[:200]
    client_id = _req.get("client_id", "")
    if not cmd_str:
        return jsonify({"ok": False, "output": "Empty command."})

    parts = cmd_str.split()
    cmd   = parts[0].lower()
    mode  = game_session.mode

    # Turn-order gate: in digital mode, per-player actions must come from the
    # player whose turn it currently is. (deal/dealer/endround/newround/status/help
    # are session-wide and bypass the gate.)
    TURN_GATED = {"hit", "stand", "double", "split", "insurance", "blackjack"}
    if mode == "digital" and cmd in TURN_GATED and len(parts) >= 2:
        current = current_turn(game_session)
        target  = parts[1].strip().capitalize()
        if current is None:
            return jsonify({
                **serialize_state(game_session),
                "rejected": True,
                "output": "  Not in play phase — deal cards or run dealer turn.\n",
            })
        if target.lower() != current.lower():
            return jsonify({
                **serialize_state(game_session),
                "rejected": True,
                "output": f"  Out of order — it's {current}'s turn (not {target}).\n",
            })

    # Gate the dealer-reveal command too: only allow when all players are done
    if mode == "digital" and cmd == "dealer":
        phase = round_phase(game_session)
        if phase == "pre-deal":
            return jsonify({
                **serialize_state(game_session),
                "rejected": True,
                "output": "  Deal cards first.\n",
            })
        if phase == "playing":
            current = current_turn(game_session) or "a player"
            return jsonify({
                **serialize_state(game_session),
                "rejected": True,
                "output": f"  Cannot reveal dealer — {current} still has hands to play.\n",
            })

    # Round-ended gate (all modes): once the round has been settled, the only
    # valid moves are newround/status/help. Re-running dealer/endround/deal (or
    # entering more cards/results) would re-pay bankrolls or re-fire drinks.
    ROUND_ENDED_BLOCKED = {
        "deal", "hit", "stand", "double", "split", "insurance", "blackjack",
        "dealer", "endround", "action", "result", "fouraces",
    }   # "peek" is deliberately absent: read-only, and its button lives on the round-over panel
    if game_session.round._round_ended and cmd in ROUND_ENDED_BLOCKED:
        return jsonify({
            **serialize_state(game_session, client_id),
            "rejected": True,
            "output": "  Round already ended — start a new round.\n",
        })

    # Deal only from a clean table (digital): re-dealing mid-round would stack
    # cards onto live hands and double-charge stakes.
    if mode == "digital" and cmd == "deal" and round_phase(game_session) != "pre-deal":
        return jsonify({
            **serialize_state(game_session, client_id),
            "rejected": True,
            "output": "  Cards are already dealt this round.\n",
        })

    # Dealer-gate: only dealer or admin may execute game-changing commands
    DEALER_GATED_CMDS = {
        "deal", "hit", "stand", "double", "split", "insurance",
        "dealer", "endround", "newround", "peek", "action", "result", "fouraces",
    }
    if (cmd in DEALER_GATED_CMDS
            and game_session._room_clients
            and not is_dealer_client(game_session, client_id)):
        state = serialize_state(game_session, client_id)
        state["output"] = "  Not authorised — only the dealer can do that.\n"
        state["rejected"] = True   # client shows output as a toast
        return jsonify(state)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):

        # ── Digital-only commands ────────────────────────────────────────────
        if mode == "digital":

            if cmd in PLAYER_ACTION_CMDS and bust_vote_pending(game_session):
                log.debug("  Waiting for all players to vote on dealer bust before play begins.")
            else:
                handler = DIGITAL_COMMANDS.get(cmd)
                if handler:
                    try:
                        handler(game_session, parts)
                    except ValueError as e:
                        log.debug(f"  {e}")
                else:
                    log.debug(f"  Unknown command '{cmd}'. Type 'help' for reference.")

            # Clear the pre-selection for the player whose action just executed
            if cmd in PLAYER_ACTION_CMDS and len(parts) >= 2:
                _p = parts[1].strip().capitalize()
                _h = (parts[2] if len(parts) > 2 else "hand1").strip().lower()
                game_session.round._preselections.pop(f"{_p.lower()}:{_h}", None)

            # After any player action: deal pending second cards to split hands
            # whose predecessor just finished, then check if dealer should auto-play
            if cmd in PLAYER_ACTION_CMDS:
                after_player_action(game_session)

        # ── Referee mode (original behaviour, unchanged) ───────────────────────
        else:
            handler = REFEREE_COMMANDS.get(cmd)
            if handler:
                try:
                    handler(game_session, parts)
                except ValueError as e:
                    log.debug(f"  {e}")
            else:
                log.debug(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    output = buf.getvalue()
    # Append to the shared log so polling clients see this output too.
    # newround already cleared _log_entries above; appending here adds the
    # new-round start text to the fresh log.
    if output.strip():
        game_session.round._log_entries.append(output)
    state = serialize_state(game_session, client_id)
    state["output"] = output   # kept for immediate display on the sender's side
    # peeked_card is included in serialize_state and persists until cleared
    # by newround/deal so all polling clients can see it.
    return jsonify(state)
