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
import time

from flask import Blueprint, jsonify, request

from engine.blackjack import Hand
from engine.drinking_rules import DrinkingRules
from engine.events import BlackjackEvent
from engine.referee import RefereeSession
from engine.strategy import best_play as _best_play

from app.services.session_store import game_sessions
from app.services.validators import is_dealer_client
from app.services.serializer import (
    serialize_state, serialize_card,
    round_phase, current_turn, compute_mandatory_split10, compute_mandatory_split_aces,
)
from app.services.game_engine import (
    deal_card, deal_pending_split_cards, perform_split,
    get_player_hand, initial_deal, dealer_turn, auto_play_npc_turns,
    bust_vote_pending, _push_ace_drink_event,
)
from app.services.decision_log import record_decision
from app.services.payout_tracker import cmd_rebuy, deduct_bets, deduct_split_bet
from app.services.round_pipeline import apply_endround_pipeline
from app.services.room_manager import apply_queued_settings, rotate_dealer, patch_tracker, reset_round_state
from app.config import BUST_VOTE_WINDOW_SECONDS

log = logging.getLogger(__name__)

bp = Blueprint("game_commands", __name__)


# ---------------------------------------------------------------------------
# Digital help text
# ---------------------------------------------------------------------------

def _print_digital_help():
    print("""
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
    result in session.stats.strategy_decisions.

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

    sd = session.stats.strategy_decisions
    if player.name not in sd:
        sd[player.name] = {"correct": 0, "total": 0}
    sd[player.name]["total"]   += 1
    sd[player.name]["correct"] += 1 if chosen_action == optimal else 0


def _check_honor_house_rule(game_session, player, hand, action) -> bool:
    """Drinking-mode "mandatory split 10s" house rule.

    If `hand` is an unsuited 10-value pair, split is still legal, and this
    hand hasn't been resolved yet, block the attempted action (hit, stand,
    or double) by recording it in session.round._honor_pending and return
    True. The frontend shows the "Play with honor / <action> (1 sip)" prompt
    via state.honor_pending; the choice is applied via /honor_resolve.
    Always returns False (no-op) in Normal mode.
    """
    if not game_session.drinking_mode:
        return False
    turn  = current_turn(game_session)
    phase = round_phase(game_session)
    if not compute_mandatory_split10(game_session, turn, phase):
        return False
    if not turn or turn.lower() != player.name.lower():
        return False
    game_session.round._honor_pending = {
        "player":  player.name,
        "hand_id": id(hand),
        "action":  action,
        "reason":  "tens",
    }
    return True


def _penalize_unsplit_aces(game_session, player, hand) -> None:
    """Drinking-mode auto-penalty: player takes any action other than split
    on a pair of Aces.  1 sip fires immediately — no modal, no choice.
    Only triggers when the hand is still the original 2-card A-A (before
    the action modifies it) and hasn't been acked yet.
    """
    if not game_session.drinking_mode:
        return
    turn  = current_turn(game_session)
    phase = round_phase(game_session)
    if not compute_mandatory_split_aces(game_session, turn, phase):
        return
    if not turn or turn.lower() != player.name.lower():
        return
    # Mark acked so the penalty fires at most once per hand
    game_session.round._honor_acked.add((player.name, id(hand)))
    game_session.tracker.apply([
        (player.name, 1, f"{player.name} didn't split Aces — drinks 1 sip"),
    ])
    _push_ace_drink_event(game_session, (player.name, 1,
        f"⚠️ Didn't split Aces => {player.name} drinks 1 sip"))


def _perform_action_without_honor(game_session, player, hand, action) -> None:
    """Carry out the originally-attempted action (hit/double/stand) after the
    player declines the mandatory-split-10s house rule, then apply the 1-sip
    "without honor" penalty via the existing ace-drink toast pipeline.
    """
    hand_label = f"hand{player.hands.index(hand) + 1}"

    if action == "hit":
        _record_strategy_decision(game_session, player, hand, "h")
        record_decision(game_session, player, hand, "h")
        card = deal_card(game_session, hand, player.name)
        log.debug(f"  {player.name} {hand_label} hits without honor {card}: {hand}")
        if hand.is_bust():
            hand.bust = hand.stood = True
            hand.result = "loss"
        elif hand.score() == 21:
            hand.stood = True
    elif action == "double":
        _record_strategy_decision(game_session, player, hand, "d")
        record_decision(game_session, player, hand, "d")
        hand.doubled = True
        deal_card(game_session, hand, player.name)
        hand.stood = True
        log.debug(f"  {player.name} {hand_label}: doubles without honor — card dealt face-down.")
        if hand.is_bust():
            hand.bust   = True
            hand.result = "loss"
    else:  # "stand" (default / fallback)
        action = "stand"
        _record_strategy_decision(game_session, player, hand, "s")
        record_decision(game_session, player, hand, "s")
        hand.stood = True
        log.debug(f"  {player.name} {hand_label}: stands without honor at {hand.score()}.")

    reason     = (game_session.round._honor_pending or {}).get("reason", "tens")
    rule_label = "mandatory ace-split" if reason == "aces" else "mandatory 10-split"
    log.debug(f"  {player.name}: {action} without honor "
              f"(declined {rule_label}, +1 sip penalty).")

    # 1-sip "without honor" penalty via the existing ace-drink toast pipeline.
    game_session.tracker.apply([
        (player.name, 1, f"{player.name} played without honor ({action}, declined {rule_label})"),
    ])
    _push_ace_drink_event(game_session, (player.name, 1,
        f"Played without honor ({action}) => {player.name} drinks 1 sip"))


def _resolve_endround(game_session):
    """Shared end-of-round bookkeeping: settle the round, apply any bust-vote
    penalties, harvest the drink log, and check for a new milestone.

    Used after dealer_turn() (deal/dealer/_after_player_action) and directly
    by the endround command in both digital and referee mode — all five call
    sites previously repeated this same four-line sequence.
    """
    game_session.cmd_endround()
    apply_endround_pipeline(game_session)


def _after_player_action(game_session):
    """Shared follow-up after any digital hit/stand/double/split.

    Deals pending second cards to split hands whose predecessor hand just
    finished, lets any NPCs play out their turns, and — if every hand is
    now resolved — advances to the dealer (mirroring the "all done" handling
    in deal/dealer/endround).

    The bust-vote window gets special treatment: if it's still open when the
    last hand finishes, expire it immediately so the next /state poll runs
    the dealer right away instead of waiting out the remaining countdown.
    """
    deal_pending_split_cards(game_session)
    auto_play_npc_turns(game_session)
    if round_phase(game_session) == "dealer-ready":
        _bust_open = (
            game_session.bust_vote_enabled
            and game_session.round._bust_vote_expires_at is not None
            and time.monotonic() < game_session.round._bust_vote_expires_at
        )
        if _bust_open:
            # All hands are done — no point holding the dealer for the
            # remaining bust-vote window. Expire it now so the next
            # /state poll triggers the dealer immediately instead of
            # waiting up to 17s (common when player2 is a bot and
            # the NPC plays out instantly after the human's last action).
            game_session.round._bust_vote_expires_at = time.monotonic()
            log.debug("\n  (All players done — bust vote window closed, dealer plays on next poll)")
        else:
            log.debug("\n  (All players done — dealer plays automatically)")
            dealer_turn(game_session)
            _resolve_endround(game_session)


# ---------------------------------------------------------------------------
# Digital-mode command handlers
# ---------------------------------------------------------------------------

def _cmd_deal_digital(game_session, parts):
    # Initial deal — no card args; shoe deals automatically
    game_session.round._last_peeked   = None   # peeked card is now stale
    game_session.round._preselections = {}
    game_session.round._suggestions   = {}
    game_session.round._bust_votes    = {}     # fresh votes each deal
    # Open the bust-vote window (countdown displays from 15)
    game_session.round._bust_vote_expires_at = (
        time.monotonic() + BUST_VOTE_WINDOW_SECONDS
        if game_session.bust_vote_enabled else None
    )
    game_session.round._bust_handouts_given  = set()   # clear any stale handouts
    game_session.round._bust_handout_expires_at = None
    # Targeted Drinking Mode: fresh vote window each deal, same as bust vote
    # above -- RoundState isn't replaced wholesale between rounds (see
    # targeted_drinking.py's module docstring), so without this reset a new
    # round would inherit last round's already-expired window and votes,
    # and maybe_open_targeted_drinking_vote() would never re-open one.
    game_session.round._targeted_drinking_votes = {}
    game_session.round._targeted_drinking_expires_at = None
    # Clear the previous round's payout badge so the seat doesn't show a
    # stale "+$10" delta while the new round's hands are in progress.
    game_session._last_round_payouts = {}
    initial_deal(game_session)
    # Deduct each player's stake upfront — bankroll drops immediately so
    # players can see their money is at risk during the round.
    deduct_bets(game_session)
    # NPCs always decline the bust side bet — cast their votes immediately
    # so only human players can hold up the start of play.
    if game_session.bust_vote_enabled and game_session.round._bust_vote_expires_at is not None:
        for _p in game_session.all_players:
            if getattr(_p, "is_npc", False):
                game_session.round._bust_votes[_p.name] = "pass"
    auto_play_npc_turns(game_session)  # no-op if bust vote still pending
    # If all hands are already done after the deal (e.g. all players
    # have a natural BJ), the hit/stand block below never fires so we
    # must check here too — otherwise the round stalls at "dealer-ready".
    if (not bust_vote_pending(game_session)
            and round_phase(game_session) == "dealer-ready"):
        log.debug("\n  (All hands done after deal — dealer plays automatically)")
        dealer_turn(game_session)
        _resolve_endround(game_session)


def _cmd_hit(game_session, parts):
    # hit <player> [hand<n>]
    if len(parts) < 2:
        log.debug("  Usage: hit <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
    hand_label = parts[2] if len(parts) > 2 else "hand1"
    hand       = get_player_hand(player, hand_label)
    if hand.stood or hand.bust:
        log.debug(f"  {player.name} {hand_label} is already done.")
        return
    if _check_honor_house_rule(game_session, player, hand, "hit"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    _penalize_unsplit_aces(game_session, player, hand)
    _record_strategy_decision(game_session, player, hand, "h")
    record_decision(game_session, player, hand, "h")
    card = deal_card(game_session, hand, player.name)
    log.debug(f"  {player.name} {hand_label} hits {card}: {hand}")
    if hand.is_bust():
        hand.bust = hand.stood = True
        hand.result = "loss"
        log.debug("  BUST!")
    elif hand.score() == 21:
        hand.stood = True
        log.debug(f"  {player.name} {hand_label}: auto-stands at 21.")


def _cmd_stand(game_session, parts):
    # stand <player> [hand<n>]
    if len(parts) < 2:
        log.debug("  Usage: stand <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
    hand_label = parts[2] if len(parts) > 2 else "hand1"
    hand       = get_player_hand(player, hand_label)
    if hand.stood or hand.bust:
        log.debug(f"  {player.name} {hand_label} is already done.")
        return
    if _check_honor_house_rule(game_session, player, hand, "stand"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    _penalize_unsplit_aces(game_session, player, hand)
    _record_strategy_decision(game_session, player, hand, "s")
    record_decision(game_session, player, hand, "s")
    hand.stood = True
    log.debug(f"  {player.name} {hand_label}: stands at {hand.score()}.")


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
        _cmd_split(session, ["split", player.name, hand_label])
    else:
        action = pending.get("action") or "stand"
        _perform_action_without_honor(session, player, hand, action)

    _after_player_action(session)

    return jsonify({**serialize_state(session, client_id), "ok": True})


def _cmd_double(game_session, parts):
    # double <player> [hand<n>]
    if len(parts) < 2:
        log.debug("  Usage: double <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
    hand_label = parts[2] if len(parts) > 2 else "hand1"
    hand       = get_player_hand(player, hand_label)
    if len(hand.cards) != 2:
        log.debug("  Can only double on first two cards.")
        return
    if hand.stood or hand.bust:
        log.debug(f"  {player.name} {hand_label} is already done.")
        return
    if _check_honor_house_rule(game_session, player, hand, "double"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    _penalize_unsplit_aces(game_session, player, hand)
    _record_strategy_decision(game_session, player, hand, "d")
    record_decision(game_session, player, hand, "d")
    hand.doubled = True
    deal_card(game_session, hand, player.name)
    hand.stood   = True
    log.debug(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
    if hand.is_bust():
        hand.bust = True
        hand.result = "loss"


def _cmd_split(game_session, parts):
    # split <player> [hand<n>]
    if len(parts) < 2:
        log.debug("  Usage: split <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
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
        return
    # House rule: splitting an unsuited 10-pair is mandatory (free) and
    # complying carries no penalty — but suited 10-pairs are EXEMPT from
    # the mandatory rule, meaning a 20 is voluntarily being broken up.
    # Warn the player and charge 1 sip for choosing to split anyway.
    _was_suited_10_split = (
        game_session.drinking_mode
        and len(hand.cards) == 2
        and hand.cards[0].rank.blackjack_value == 10
        and hand.cards[1].rank.blackjack_value == 10
        and hand.is_suited()
    )

    _record_strategy_decision(game_session, player, hand, "sp")
    record_decision(game_session, player, hand, "sp")
    # `hand` keeps its identity (id(hand)) across the split — only its second
    # card is moved out to `new_hand`. If this hand was previously acked for
    # the "mandatory split 10s" house rule (split OR stood-without-honor),
    # that ack must not carry over: once it's dealt a new second card it's a
    # brand-new 2-card hand and may need the house-rule prompt again (e.g.
    # re-splitting into another unsuited 10-10).
    game_session.round._honor_acked.discard((player.name, id(hand)))
    try:
        idx = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
    except (ValueError, AttributeError):
        idx = 0
    new_hand, new_label = perform_split(game_session, player, hand, idx)
    # Splitting requires placing an equal bet on the new hand — deduct it now
    # so the bankroll badge stays accurate during the round.
    deduct_split_bet(game_session, player.name)
    # Check for instant 21/bust on H1 after the second card is dealt
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

    if _was_suited_10_split:
        log.debug(f"  {player.name}: mandatory split-10s doesn't apply to suited "
                  f"20s — splits anyway, drinks 1 sip.")
        game_session.tracker.apply([
            (player.name, 1, f"{player.name} split a suited 20 (mandatory split 10s "
                              f"does not apply if suited)"),
        ])
        _push_ace_drink_event(game_session, (player.name, 1,
            f"⚠️ Mandatory split 10s does not apply if suited — "
            f"{player.name} split anyway => drinks 1 sip"))


def _cmd_insurance(game_session, parts):
    # insurance <player> [hand<n>]
    if len(parts) < 2:
        log.debug("  Usage: insurance <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
    hand_label = parts[2] if len(parts) > 2 else "hand1"
    hand       = get_player_hand(player, hand_label)
    if not hand.is_blackjack():
        log.debug("  Insurance only applies when the player has a Blackjack (dealer shows Ace).")
        return
    record_decision(game_session, player, hand, "insurance")
    hand.insured = True
    # Sync with the vote system: force all voters' votes to True so
    # dealer_turn resolves this hand as insured via voted_keys.
    hand_idx   = player.hands.index(hand)
    vote_entry = next(
        (v for v in game_session.round._insurance_votes
         if v["player"] == player.name and v["hand_idx"] == hand_idx
         and not v.get("resolved")),
        None,
    )
    if vote_entry:
        voters = [x for x in game_session.all_players if x.name != player.name]
        for x in voters:
            vote_entry["votes"][x.name] = True
    log.debug(f"  {player.name} {hand_label}: insured.")


def _cmd_blackjack(game_session, parts):
    # blackjack <player> [hand<n>] — confirm natural BJ, fire drink rules
    if len(parts) < 2:
        log.debug("  Usage: blackjack <player> [hand<n>]")
        return
    player = game_session._get_player(parts[1])
    if not player:
        log.debug(f"  Unknown player '{parts[1]}'.")
        return
    hand_label = parts[2] if len(parts) > 2 else "hand1"
    hand       = get_player_hand(player, hand_label)
    hand.stood = True
    all_names  = [p.name for p in game_session.all_players]
    game_session.tracker.apply(
        DrinkingRules.handle(BlackjackEvent(player_name=player.name, hand=hand, all_names=all_names)))
    log.debug(f"  {player.name} BLACKJACK confirmed.")


def _cmd_peek(game_session, parts):
    # Toggle: hide peeked card if already shown, otherwise reveal it
    shoe = getattr(game_session, "shoe", None)
    if game_session.round._last_peeked:
        # Already showing — toggle off
        game_session.round._last_peeked = None
        log.debug("  Next card hidden.")
    elif shoe and shoe.cards:
        card = shoe.cards[-1]   # pop() takes from the end
        log.debug(f"  Next card in shoe: {card}")
        log.debug(f"  ({len(shoe.cards)} cards remaining)")
        game_session.round._last_peeked = serialize_card(card)
    else:
        log.debug("  Shoe is empty or not available.")
        game_session.round._last_peeked = None


def _cmd_dealer_digital(game_session, parts):
    # Auto-run dealer turn + evaluate all hands + assign drinks
    dealer_turn(game_session)
    _resolve_endround(game_session)


def _cmd_newround(game_session, parts, *, digital):
    # newround [rotate]
    # Explicit "rotate" arg is still accepted for manual override.
    # In drinking mode the backend auto-decides: rotate when a hard/soft switch
    # fired this round, or when the rotation interval is reached — so the
    # frontend just sends bare "newround" and never makes this call itself.
    explicit_rotate = len(parts) > 1 and parts[1].lower() == "rotate"
    auto_rotate = (
        game_session.drinking_mode and bool(
            game_session.round.switch_this_round in ("hard", "soft") or
            game_session.rounds_this_dealer >= game_session._dealer_rotate_every
        )
    )
    rotate = explicit_rotate or auto_rotate
    # Apply queued settings before the round starts.
    # Capture shoe reference first — if apply_queued_settings creates a fresh
    # Shoe (num_decks change), we must not reshuffle it immediately after.
    shoe_before = game_session.shoe
    setting_changes = apply_queued_settings(game_session)
    for msg in setting_changes:
        log.debug(f"  ⚙️  {msg}")
    if rotate:
        rotate_dealer(game_session)
        game_session.rounds_this_dealer = 1
    else:
        game_session.rounds_this_dealer = game_session.rounds_this_dealer + 1
    reset_round_state(game_session, digital=digital)
    if digital and (game_session.drinking_mode or game_session.shoe.needs_reshuffle()):
        if game_session.shoe is not shoe_before:
            log.debug("  Shoe already fresh from settings change — skipping reshuffle.")
        else:
            game_session.shoe.reset(quiet=True)
            log.debug("  Shoe reshuffled.")
    game_session.start_round()
    patch_tracker(game_session)
    game_session.session.tracker.easy_mode = game_session.easy_mode


def _cmd_status(game_session, parts):
    game_session.cmd_status()


def _cmd_help_digital(game_session, parts):
    _print_digital_help()


# ---------------------------------------------------------------------------
# Referee-mode command handlers
# ---------------------------------------------------------------------------

def _cmd_referee_deal(game_session, parts):
    game_session.cmd_deal(parts)


def _cmd_referee_action(game_session, parts):
    game_session.cmd_action(parts)


def _cmd_referee_result(game_session, parts):
    game_session.cmd_result(parts)


def _cmd_referee_dealer(game_session, parts):
    game_session.cmd_dealer(parts)


def _cmd_referee_fouraces(game_session, parts):
    game_session.cmd_fouraces(parts)


def _cmd_help_referee(game_session, parts):
    RefereeSession.print_help()


# ---------------------------------------------------------------------------
# Command registries
# ---------------------------------------------------------------------------

# Player-action commands: gated by turn order and bust-vote-pending, and
# trigger the shared _after_player_action() follow-up once executed.
PLAYER_ACTION_CMDS = {"hit", "stand", "double", "split"}

DIGITAL_COMMANDS = {
    "deal":      _cmd_deal_digital,
    "hit":       _cmd_hit,
    "stand":     _cmd_stand,
    "double":    _cmd_double,
    "split":     _cmd_split,
    "insurance": _cmd_insurance,
    "peek":      _cmd_peek,
    "dealer":    _cmd_dealer_digital,
    "endround":  lambda gs, parts: _resolve_endround(gs),
    "newround":  lambda gs, parts: _cmd_newround(gs, parts, digital=True),
    "status":    _cmd_status,
    "st":        _cmd_status,
    "help":      _cmd_help_digital,
}

REFEREE_COMMANDS = {
    "deal":     _cmd_referee_deal,
    "action":   _cmd_referee_action,
    "result":   _cmd_referee_result,
    "dealer":   _cmd_referee_dealer,
    "fouraces": _cmd_referee_fouraces,
    "endround": lambda gs, parts: _resolve_endround(gs),
    "newround": lambda gs, parts: _cmd_newround(gs, parts, digital=False),
    "status":   _cmd_status,
    "st":       _cmd_status,
    "help":     _cmd_help_referee,
}


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
        "deal", "hit", "stand", "double", "split", "insurance",
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

            if cmd in PLAYER_ACTION_CMDS and bust_vote_pending(game_session):
                log.debug("  Waiting for all players to vote on dealer bust before play begins.")
            else:
                handler = DIGITAL_COMMANDS.get(cmd)
                if handler:
                    handler(game_session, parts)
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
                _after_player_action(game_session)

        # ── Referee mode (original behaviour, unchanged) ───────────────────────
        else:
            handler = REFEREE_COMMANDS.get(cmd)
            if handler:
                handler(game_session, parts)
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
