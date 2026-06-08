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

import logging
log = logging.getLogger(__name__)

import contextlib
import io
import time

from flask import Blueprint, jsonify, request

from blackjack  import Hand
from engine.drinking_rules import DrinkingRules
from referee    import RefereeSession
from strategy   import best_play as _best_play

from app.services.session_store  import game_sessions
from app.services.validators     import is_dealer_client
from app.services.serializer     import (
    serialize_state, serialize_card,
    round_phase, current_turn,
)
from app.services.game_engine    import (
    deal_card, deal_pending_split_cards,
    get_player_hand, initial_deal, dealer_turn, auto_play_npc_turns,
)
from app.services.drink_tracker  import harvest_drink_log, check_and_set_milestone, apply_bust_vote_penalties
from app.services.room_manager   import apply_queued_settings, rotate_dealer, patch_tracker

bp = Blueprint("game_commands", __name__)


# ---------------------------------------------------------------------------
# Digital help text
# ---------------------------------------------------------------------------

def _print_digital_help():
    log.debug("""
  DIGITAL MODE COMMANDS
  =====================
  deal
      Deal initial 2 cards to all hands from the shoe.

  hit <player> [hand<n>]
      Deal one card from the shoe to that hand.
      Example: hit Rob hand1

  stand <player> [hand<n>]
      Mark the hand as stood.
      Example: stand Alice hand2

  double <player> [hand<n>]
      Double down -- deal one card then stand. Must be on first two cards.
      Example: double Rob hand1

  split <player> [hand<n>]
      Split the hand and deal one card to each resulting hand.
      Example: split Rob hand1

  insurance <player> [hand<n>]
      Mark the hand as insured (when dealer shows Ace).

  blackjack <player> [hand<n>]
      Confirm a natural blackjack and fire drinking rules.

  dealer
      Reveal the hole card, hit until 17+, then auto-evaluate all hands.

  endround
      Finalise the round -- fire end-of-round drinking rules and print summary.

  newround [rotate]
      Start a new round. Add 'rotate' to pass the dealer role clockwise.

  status
      Show current state of all hands.
""")


# ---------------------------------------------------------------------------
# Strategy deviation helper
# ---------------------------------------------------------------------------

def _record_strategy_decision(session, player, hand, chosen_action: str) -> None:
    """
    Compare the player's chosen action against basic strategy and record the
    result in session._strategy_decisions.

    Skipped for:
      - NPC players (always optimal by definition)
      - Hands with fewer than 2 cards (split hand waiting for second card)
      - No dealer upcard available yet
    """
    if getattr(player, "is_npc", False):
        return

    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand or not dealer.dealer_hand.cards:
        return
    if len(hand.cards) < 2:
        return

    dealer_up   = dealer.dealer_hand.cards[0]
    valid       = ["h", "s"]
    if len(hand.cards) == 2 and not hand.doubled:
        valid.append("d")
    if hand.can_split():
        valid.append("sp")

    optimal = _best_play(hand, dealer_up, valid,
                         drinking_mode=session.drinking_mode)

    sd = session._strategy_decisions
    if player.name not in sd:
        sd[player.name] = {"correct": 0, "total": 0}
    sd[player.name]["total"]   += 1
    sd[player.name]["correct"] += 1 if chosen_action == optimal else 0


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

    cmd_str   = _req.get("cmd", "").strip()
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
                "output": "  Not in play phase — deal cards or run dealer turn.\n",
            })
        if target.lower() != current.lower():
            return jsonify({
                **serialize_state(game_session),
                "output": f"  Out of order — it's {current}'s turn (not {target}).\n",
            })

    # Gate the dealer-reveal command too: only allow when all players are done
    if mode == "digital" and cmd == "dealer":
        phase = round_phase(game_session)
        if phase == "pre-deal":
            return jsonify({
                **serialize_state(game_session),
                "output": "  Deal cards first.\n",
            })
        if phase == "playing":
            current = current_turn(game_session) or "a player"
            return jsonify({
                **serialize_state(game_session),
                "output": f"  Cannot reveal dealer — {current} still has hands to play.\n",
            })

    # Dealer-gate: only dealer or admin may execute game-changing commands
    DEALER_GATED_CMDS = {
        "deal", "hit", "stand", "double", "split", "insurance", "blackjack",
        "dealer", "endround", "newround", "peek", "action", "result", "fouraces",
    }
    if (cmd in DEALER_GATED_CMDS
            and game_session._room_clients
            and not is_dealer_client(game_session, client_id)):
        state = serialize_state(game_session, client_id)
        state["output"] = "  Not authorised — only the dealer can do that.\n"
        return jsonify(state)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):

        # ── Digital-only commands ────────────────────────────────────────────
        if mode == "digital":

            if cmd == "deal":
                # Initial deal — no card args; shoe deals automatically
                game_session._last_peeked   = None   # peeked card is now stale
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._bust_votes    = {}     # fresh votes each deal
                # Open bust-vote window for 17 seconds (countdown displays from 15)
                game_session._bust_vote_expires_at = (
                    time.monotonic() + 17 if game_session.bust_vote_enabled else None
                )
                game_session._bust_handouts_given  = set()   # clear any stale handouts
                game_session._bust_handout_expires_at = None
                initial_deal(game_session)
                auto_play_npc_turns(game_session)

            elif cmd == "hit":
                # hit <player> [hand<n>]
                if len(parts) < 2:
                    log.debug("  Usage: hit <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            log.debug(f"  {player.name} {hand_label} is already done.")
                        else:
                            _record_strategy_decision(game_session, player, hand, "h")
                            card = deal_card(game_session, hand, player.name)
                            log.debug(f"  {player.name} {hand_label} hits {card}: {hand}")
                            if hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                log.debug("  BUST!")
                            elif hand.score() == 21:
                                hand.stood = True
                                log.debug(f"  {player.name} {hand_label}: auto-stands at 21.")

            elif cmd == "stand":
                # stand <player> [hand<n>]
                if len(parts) < 2:
                    log.debug("  Usage: stand <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            log.debug(f"  {player.name} {hand_label} is already done.")
                        else:
                            _record_strategy_decision(game_session, player, hand, "s")
                            hand.stood = True
                            log.debug(f"  {player.name} {hand_label}: stands at {hand.score()}.")

            elif cmd == "double":
                # double <player> [hand<n>]
                if len(parts) < 2:
                    log.debug("  Usage: double <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if len(hand.cards) != 2:
                            log.debug("  Can only double on first two cards.")
                        elif hand.stood or hand.bust:
                            log.debug(f"  {player.name} {hand_label} is already done.")
                        else:
                            _record_strategy_decision(game_session, player, hand, "d")
                            hand.doubled = True
                            deal_card(game_session, hand, player.name)
                            hand.stood   = True
                            log.debug(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
                            if hand.is_bust():
                                hand.bust = True
                                hand.result = "loss"

            elif cmd == "split":
                # split <player> [hand<n>]
                if len(parts) < 2:
                    log.debug("  Usage: split <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if not hand.can_split():
                            # Give a specific message when the split limit is the reason
                            # (record nothing — invalid action, not a strategy decision)
                            if (len(hand.cards) == 2
                                    and hand.cards[0].rank.blackjack_value == hand.cards[1].rank.blackjack_value
                                    and hand.split_count >= Hand.MAX_SPLITS):
                                log.debug(f"  Max splits reached ({Hand.MAX_SPLITS} splits per hand).")
                            else:
                                log.debug("  Cannot split this hand.")
                        else:
                            _record_strategy_decision(game_session, player, hand, "sp")
                            # Move second card to new hand (no second cards dealt yet)
                            new_hand = Hand(from_split=True)
                            new_hand.cards.append(hand.cards.pop())
                            hand.from_split    = True
                            hand.split_count  += 1
                            new_hand.split_count = hand.split_count  # child inherits so chain limit holds
                            idx       = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
                            new_label = f"hand{idx + 2}"
                            player.hands.insert(idx + 1, new_hand)
                            # Deal second card to H1; check for instant 21/bust
                            deal_card(game_session, hand, player.name)
                            if hand.score() == 21:
                                hand.stood = True
                                log.debug(f"  {player.name} splits:")
                                log.debug(f"    {hand_label}: {hand}  (21 — auto-stands)")
                                log.debug(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            elif hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                log.debug(f"  {player.name} splits:")
                                log.debug(f"    {hand_label}: {hand}  BUST!")
                                log.debug(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            else:
                                log.debug(f"  {player.name} splits:")
                                log.debug(f"    {hand_label}: {hand}  ← play this hand first")
                                log.debug(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")

            elif cmd == "insurance":
                # insurance <player> [hand<n>]
                if len(parts) < 2:
                    log.debug("  Usage: insurance <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        if not hand.is_blackjack():
                            log.debug("  Insurance only applies when the player has a Blackjack (dealer shows Ace).")
                        else:
                            hand.insured = True
                            # Sync with the vote system: force all voters' votes to True so
                            # dealer_turn resolves this hand as insured via voted_keys.
                            hand_idx   = player.hands.index(hand)
                            vote_entry = next(
                                (v for v in game_session._insurance_votes
                                 if v["player"] == player.name and v["hand_idx"] == hand_idx
                                 and not v.get("resolved")),
                                None,
                            )
                            if vote_entry:
                                voters = [x for x in game_session.all_players if x.name != player.name]
                                for x in voters:
                                    vote_entry["votes"][x.name] = True
                            log.debug(f"  {player.name} {hand_label}: insured.")

            elif cmd == "blackjack":
                # blackjack <player> [hand<n>] — confirm natural BJ, fire drink rules
                if len(parts) < 2:
                    log.debug("  Usage: blackjack <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        log.debug(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = get_player_hand(player, hand_label)
                        hand.stood = True
                        all_names  = [p.name for p in game_session.all_players]
                        game_session.tracker.apply(
                            DrinkingRules.on_blackjack(player.name, hand, all_names))
                        log.debug(f"  {player.name} BLACKJACK confirmed.")

            elif cmd == "peek":
                # Toggle: hide peeked card if already shown, otherwise reveal it
                shoe = getattr(game_session, "shoe", None)
                if game_session._last_peeked:
                    # Already showing — toggle off
                    game_session._last_peeked = None
                    log.debug("  Next card hidden.")
                elif shoe and shoe.cards:
                    card = shoe.cards[-1]   # pop() takes from the end
                    log.debug(f"  Next card in shoe: {card}")
                    log.debug(f"  ({len(shoe.cards)} cards remaining)")
                    game_session._last_peeked = serialize_card(card)
                else:
                    log.debug("  Shoe is empty or not available.")
                    game_session._last_peeked = None

            elif cmd == "dealer":
                # Auto-run dealer turn + evaluate all hands + assign drinks
                dealer_turn(game_session)
                game_session.cmd_endround()
                apply_bust_vote_penalties(game_session)
                harvest_drink_log(game_session)
                check_and_set_milestone(game_session)

            elif cmd == "endround":
                game_session.cmd_endround()
                apply_bust_vote_penalties(game_session)
                harvest_drink_log(game_session)
                check_and_set_milestone(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = apply_queued_settings(game_session)
                for msg in setting_changes:
                    log.debug(f"  ⚙️  {msg}")
                if rotate:
                    rotate_dealer(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = game_session.rounds_this_dealer + 1
                game_session.switch_this_round = None
                game_session._hard_switch_drinking_applied = False
                # Clear shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = game_session._log_version + 1
                game_session._deferred_hole_card_msgs = []
                game_session._last_peeked   = None
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._bust_votes             = {}    # clear bust votes each round
                game_session._bust_vote_expires_at   = None
                game_session._bust_vote_result        = None
                game_session._bust_handout_expires_at = None
                game_session._insurance_result        = None
                game_session._ace_drink_events        = []
                game_session._ace_drink_seq           = 0
                game_session._bust_handouts_given     = set()
                game_session._drink_log_harvested     = False
                game_session._kick_votes    = {}  # reset vote-kick tally each round
                game_session._pending_milestone = None  # clear between rounds
                if game_session.drinking_mode or game_session.shoe.needs_reshuffle():
                    game_session.shoe.reset()
                    log.debug("  Shoe reshuffled.")
                game_session.start_round()
                patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                _print_digital_help()

            else:
                log.debug(f"  Unknown command '{cmd}'. Type 'help' for reference.")

            # Clear the pre-selection for the player whose action just executed
            if cmd in {"hit", "stand", "double", "split"} and len(parts) >= 2:
                _p = parts[1].strip().capitalize()
                _h = (parts[2] if len(parts) > 2 else "hand1").strip().lower()
                game_session._preselections.pop(f"{_p.lower()}:{_h}", None)

            # After any player action: deal pending second cards to split hands
            # whose predecessor just finished, then check if dealer should auto-play
            if cmd in {"hit", "stand", "double", "split"}:
                deal_pending_split_cards(game_session)
                auto_play_npc_turns(game_session)
                if round_phase(game_session) == "dealer-ready":
                    _bust_open = (
                        game_session.bust_vote_enabled
                        and game_session._bust_vote_expires_at is not None
                        and time.monotonic() < game_session._bust_vote_expires_at
                    )
                    if _bust_open:
                        log.debug("\n  (All players done — waiting for bust vote to close before dealer plays)")
                    else:
                        log.debug("\n  (All players done — dealer plays automatically)")
                        dealer_turn(game_session)
                        game_session.cmd_endround()
                        apply_bust_vote_penalties(game_session)
                        harvest_drink_log(game_session)
                        check_and_set_milestone(game_session)

        # ── Referee mode (original behaviour, unchanged) ─────────────────────
        else:

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
                apply_bust_vote_penalties(game_session)
                harvest_drink_log(game_session)
                check_and_set_milestone(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = apply_queued_settings(game_session)
                for msg in setting_changes:
                    log.debug(f"  ⚙️  {msg}")
                if rotate:
                    rotate_dealer(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = game_session.rounds_this_dealer + 1
                game_session.switch_this_round = None
                game_session._hard_switch_drinking_applied = False
                # Clear the shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = game_session._log_version + 1
                game_session._last_peeked            = None
                game_session._preselections          = {}
                game_session._suggestions            = {}
                game_session._bust_votes              = {}
                game_session._bust_vote_expires_at    = None
                game_session._bust_vote_result        = None
                game_session._bust_handout_expires_at = None
                game_session._insurance_result        = None
                game_session._ace_drink_events        = []
                game_session._ace_drink_seq           = 0
                game_session._bust_handouts_given     = set()
                game_session._drink_log_harvested     = False
                game_session._kick_votes              = {}
                game_session._pending_milestone      = None
                game_session.start_round()
                patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                RefereeSession.print_help()

            else:
                log.debug(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    output = buf.getvalue()
    # Append to the shared log so polling clients see this output too.
    # newround already cleared _log_entries above; appending here adds the
    # new-round start text to the fresh log.
    if output.strip():
        game_session._log_entries.append(output)
    state = serialize_state(game_session, client_id)
    state["output"] = output   # kept for immediate display on the sender's side
    # peeked_card is included in serialize_state and persists until cleared
    # by newround/deal so all polling clients can see it.
    return jsonify(state)