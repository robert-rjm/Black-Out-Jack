"""
app/services/player_actions.py
==============================
Shared player-action helpers (strategy logging, honor house rule, unsplit-ace
penalty, post-action follow-up). Not HTTP logic; used by the /command handlers
and /honor_resolve.
"""

import logging
import time
from engine.strategy import best_play as _best_play
from app.services.stats import compute_mandatory_split10, compute_mandatory_split_aces
from app.services.round_state import round_phase, current_turn
from app.services.game_engine import (
    deal_card,
    deal_pending_split_cards,
    dealer_turn,
    auto_play_npc_turns,
    _push_ace_drink_event,
    resolve_endround,
)
from app.services.decision_log import record_decision

log = logging.getLogger(__name__)


def record_strategy_decision(session, player, hand, chosen_action: str) -> None:
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
                         drinking_mode=session.drinking_mode,
                         split_tens=session.rules.on("table.split_tens"))

    sd = session.stats.strategy_decisions
    if player.name not in sd:
        sd[player.name] = {"correct": 0, "total": 0}
    sd[player.name]["total"]   += 1
    sd[player.name]["correct"] += 1 if chosen_action == optimal else 0


def check_honor_house_rule(game_session, player, hand, action) -> bool:
    """Drinking-mode "mandatory split 10s" house rule.

    If `hand` is an unsuited 10-value pair, split is still legal, and this
    hand hasn't been resolved yet, block the attempted action (hit, stand,
    or double) by recording it in session.round._honor_pending and return
    True. The frontend shows the "Play with honor / <action> (1× wager)" prompt
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


def penalize_unsplit_aces(game_session, player, hand) -> None:
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


def perform_action_without_honor(game_session, player, hand, action) -> None:
    """Carry out the originally-attempted action (hit/double/stand) after the
    player declines the mandatory-split-10s house rule, then apply the 1-sip
    "without honor" penalty via the existing ace-drink toast pipeline.
    """
    hand_label = f"hand{player.hands.index(hand) + 1}"

    if action == "hit":
        record_strategy_decision(game_session, player, hand, "h")
        record_decision(game_session, player, hand, "h")
        card = deal_card(game_session, hand, player.name)
        log.debug(f"  {player.name} {hand_label} hits without honor {card}: {hand}")
        if hand.is_bust():
            hand.bust = hand.stood = True
            hand.result = "loss"
        elif hand.score() == 21:
            hand.stood = True
    elif action == "double":
        record_strategy_decision(game_session, player, hand, "d")
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
        record_strategy_decision(game_session, player, hand, "s")
        record_decision(game_session, player, hand, "s")
        hand.stood = True
        log.debug(f"  {player.name} {hand_label}: stands without honor at {hand.score()}.")

    reason     = (game_session.round._honor_pending or {}).get("reason", "tens")
    rule_label = "mandatory ace-split" if reason == "aces" else "mandatory 10-split"
    log.debug(f"  {player.name}: {action} without honor "
              f"(declined {rule_label}, +{game_session.wager} sip{'' if game_session.wager == 1 else 's'} penalty).")

    # 1x wager "without honor" penalty via the existing ace-drink toast pipeline.
    game_session.tracker.apply([
        (player.name, game_session.wager,
         f"{player.name} played without honor ({action}, declined {rule_label})"),
    ])
    _push_ace_drink_event(game_session, (player.name, game_session.wager,
        f"Played without honor ({action}) => {player.name} drinks {game_session.wager} sip{'' if game_session.wager == 1 else 's'}"))


def after_player_action(game_session):
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
            resolve_endround(game_session)
