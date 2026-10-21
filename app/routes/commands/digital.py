"""
app/routes/commands/digital.py
==============================
Digital-mode command handlers and the DIGITAL_COMMANDS registry.
"""

import logging
from engine.blackjack import Hand
from engine.drinking_rules import DrinkingRules
from engine.events import BlackjackEvent
from app.services.round_state import serialize_card
from app.services.game_engine import (
    deal_card,
    perform_split,
    get_player_hand,
    dealer_turn,
    _push_ace_drink_event,
    deal_now,
    resolve_endround,
)
from app.services.decision_log import record_decision
from app.services.payout_tracker import (
    deduct_split_bet,
    deduct_double_bet,
    can_afford_extra,
    is_cash_mode,
    stake_per_hand,
    human_names,
    stake_window_open,
    open_stake_window,
    close_stake_window,
)
from app.services.player_actions import (
    record_strategy_decision,
    check_honor_house_rule,
    penalize_unsplit_aces,
)
from app.routes.commands.common import cmd_newround, cmd_status

log = logging.getLogger(__name__)


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


def _cmd_deal_digital(game_session, parts):
    # Normal mode: the first Deal opens the stake window (players change or
    # accept their stake); the cards go out when /state ticks it closed (see
    # tick.apply_stake_window). Deal again during the window to skip the wait.
    if is_cash_mode(game_session):
        if not stake_window_open(game_session) and human_names(game_session):
            open_stake_window(game_session)
            print("  Stake window open — change or accept your stake.")
            return
        close_stake_window(game_session)
    deal_now(game_session)


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
    if check_honor_house_rule(game_session, player, hand, "hit"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    penalize_unsplit_aces(game_session, player, hand)
    record_strategy_decision(game_session, player, hand, "h")
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
    if check_honor_house_rule(game_session, player, hand, "stand"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    penalize_unsplit_aces(game_session, player, hand)
    record_strategy_decision(game_session, player, hand, "s")
    record_decision(game_session, player, hand, "s")
    hand.stood = True
    log.debug(f"  {player.name} {hand_label}: stands at {hand.score()}.")


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
    if check_honor_house_rule(game_session, player, hand, "double"):
        log.debug(f"  {player.name} {hand_label}: house rule requires splitting "
                  f"this unsuited 10-pair — awaiting choice.")
        return
    if not can_afford_extra(game_session, player.name):
        log.debug(f"  {player.name} can't afford to double "
                  f"(needs ${stake_per_hand(game_session, player.name):.2f} more).")
        return
    penalize_unsplit_aces(game_session, player, hand)
    record_strategy_decision(game_session, player, hand, "d")
    record_decision(game_session, player, hand, "d")
    hand.doubled = True
    deduct_double_bet(game_session, player.name)
    deal_card(game_session, hand, player.name)
    hand.stood   = True
    log.debug(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
    if hand.is_bust():
        hand.bust = True
        hand.result = "loss"


def cmd_split(game_session, parts):
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
    if not can_afford_extra(game_session, player.name):
        log.debug(f"  {player.name} can't afford to split "
                  f"(needs ${stake_per_hand(game_session, player.name):.2f} more).")
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

    record_strategy_decision(game_session, player, hand, "sp")
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
        DrinkingRules.handle(BlackjackEvent(
            player_name=player.name, hand=hand, all_names=all_names,
            wager=game_session.wager)))
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
    resolve_endround(game_session)


def _cmd_help_digital(game_session, parts):
    _print_digital_help()


DIGITAL_COMMANDS = {
    "deal":      _cmd_deal_digital,
    "hit":       _cmd_hit,
    "stand":     _cmd_stand,
    "double":    _cmd_double,
    "split":     cmd_split,
    "insurance": _cmd_insurance,
    "peek":      _cmd_peek,
    "dealer":    _cmd_dealer_digital,
    "endround":  lambda gs, parts: resolve_endround(gs),
    "newround":  lambda gs, parts: cmd_newround(gs, parts, digital=True),
    "status":    cmd_status,
    "st":        cmd_status,
    "help":      _cmd_help_digital,
}
