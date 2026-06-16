"""
app/services/game_engine.py
============================
Digital-mode game logic: dealing, player actions, dealer turn, NPC auto-play.

All public functions accept a session object as their first argument.
This module never imports session_store — the route layer owns the store
lookup and passes the session down. This keeps the dependency graph clean
and makes these functions unit-testable without a Flask context.
"""

import logging
import time as _time

from engine.blackjack import Hand, HandEvaluator, NPC_Player, get_player_hand
from app.services.decision_log import record_decision
from engine.drinking_rules import DrinkingRules
from engine.events import (
    CardDealtEvent,
    BlackjackEvent,
    InsuranceResolvedEvent,
    HandResolvedEvent,
    AllHandsSweepEvent,
    DealerHandRevealedEvent,
    HardDealerSwitchEvent,
)

from app.models.game_room import GameRoom
from app.services.serializer import hand_done, round_phase, current_turn

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ace drink event helper

def _push_ace_drink_event(session: GameRoom, msg: tuple) -> None:
    """Push a single ace drink message to the mid-round toast queue."""
    recipient, sips, reason = msg[0], msg[1], msg[2]
    session.round._ace_drink_seq += 1
    session.round._ace_drink_events.append({
        "seq":       session.round._ace_drink_seq,
        "recipient": recipient or "all",
        "sips":      sips,
        "reason":    reason,
    })


def _push_reshuffle_event(session: GameRoom) -> None:
    """Push a mid-round shoe-reshuffle event to the toast queue."""
    session.round._reshuffle_seq += 1
    session.round._reshuffle_events.append({
        "seq":       session.round._reshuffle_seq,
        "decks":     session.shoe.num_decks,
    })


# ---------------------------------------------------------------------------
# Hand / player helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Card dealing
# ---------------------------------------------------------------------------

def deal_card(session: GameRoom, hand: Hand, recipient_name: str):
    """Deal one card from the shoe into hand and fire ace drinking rules.

    Defers hole-card and face-down doubled-card drink messages so they are
    not revealed in the log before the dealer turn.
    """
    card     = session.shoe.deal_card(quiet=True)
    if session.shoe.just_reshuffled:
        session.shoe.just_reshuffled = False
        _push_reshuffle_event(session)
    card_pos = len(hand.cards) + 1
    hand.cards.append(card)

    if session.drinking_mode:
        all_names      = [p.name for p in session.all_players]
        dealer         = session._get_dealer()
        is_dealer_hand = (dealer is not None and hand is dealer.dealer_hand)
        is_hole_card   = is_dealer_hand and card_pos == 2
        is_double_card = (not is_dealer_hand) and hand.doubled   # face-down doubled card

        msgs = DrinkingRules.handle(CardDealtEvent(
            card=card, recipient=recipient_name, card_pos=card_pos,
            all_names=all_names, dealer_name=session.dealer_name,
            ace_clubs_flag=session._ace_clubs_flag,
            is_dealer_hand=is_dealer_hand,
        ))
        for msg in msgs:
            _, s, reason = msg[0], msg[1], msg[2]
            if s == -1:
                # Ace-clubs credit — track immediately but suppress the print if
                # the card is face-down (doubled hand) to avoid revealing it early.
                session._ace_credits.append(recipient_name)
                if not is_double_card:
                    log.debug(f"    (i) {reason}")
            elif is_hole_card or is_double_card:
                # Defer until the card is face-up
                session.round._deferred_hole_card_msgs.append(msg)
            else:
                session.tracker.apply([msg])
                if s and s > 0:
                    _push_ace_drink_event(session, msg)

    return card


def deal_pending_split_cards(session: GameRoom) -> None:
    """
    After any player action, deal the second card to any split hand whose
    predecessor has finished (stood / bust / BJ).

    Loops until stable — handles chain splits automatically.
    """
    changed = True
    while changed:
        changed = False
        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if not (hand.from_split and len(hand.cards) == 1):
                    continue
                # Bypass the 1-card guard in hand_done for the predecessor check
                if i == 0:
                    prev_done = True
                else:
                    prev = p.hands[i - 1]
                    prev_done = (len(prev.cards) >= 2 and
                                 (prev.stood or prev.bust or
                                  prev.is_bust() or prev.is_blackjack()))
                if not prev_done:
                    continue

                deal_card(session, hand, p.name)
                log.debug(f"  {p.name} hand{i+1}: second card dealt — {hand}")

                if hand.is_blackjack():
                    hand.stood = True
                    log.debug(f"  {p.name} hand{i+1}: BLACKJACK! auto-stands.")
                    # Register insurance vote if dealer shows Ace
                    dealer = session._get_dealer()
                    if (dealer and dealer.dealer_hand and dealer.dealer_hand.cards
                            and dealer.dealer_hand.cards[0].rank.label == "A"
                            and session.drinking_mode):
                        existing = next(
                            (v for v in session.round._insurance_votes
                             if v["player"] == p.name and v["hand_idx"] == i),
                            None,
                        )
                        if not existing:
                            session.round._insurance_votes.append({
                                "player":    p.name,
                                "hand_idx":  i,
                                "votes":     {},
                                "resolved":  False,
                                "started_at": _time.monotonic(),
                            })
                elif hand.score() == 21:
                    hand.stood = True
                    log.debug(f"  {p.name} hand{i+1}: auto-stands at 21.")
                elif hand.is_bust():
                    hand.bust = hand.stood = True
                    hand.result = "loss"
                    log.debug(f"  {p.name} hand{i+1}: BUST on second card!")

                changed = True
                break   # restart scan after each deal
            if changed:
                break


# ---------------------------------------------------------------------------
# Split helper
# ---------------------------------------------------------------------------

def perform_split(session: GameRoom, player, hand: Hand, hand_idx: int) -> tuple[Hand, str]:
    """Mechanical digital split: move the second card to a new hand, share the
    split-chain counter, insert the new hand into the player's hand list, and
    deal a replacement second card to the original hand.

    Returns ``(new_hand, new_label)`` so callers can log or react to the
    post-deal state (21, bust, etc.).

    Note: referee.py has its own split path that does *not* move card data
    (physical cards are moved by the player), so this helper is digital-only.
    """
    new_hand = hand.split(session.shoe)          # card pop + chain counter + from_split flags
    player.hands.insert(hand_idx + 1, new_hand)
    deal_card(session, hand, player.name)
    new_label = f"hand{hand_idx + 2}"
    return new_hand, new_label


# ---------------------------------------------------------------------------
# Round flow
# ---------------------------------------------------------------------------

def initial_deal(session: GameRoom) -> None:
    """Deal 2 cards to every player hand and the dealer hand from the shoe."""
    session.round._deferred_hole_card_msgs = []
    dealer = session._get_dealer()

    log.debug("\n--- Dealing ---")
    for _ in range(2):
        for p in session.all_players:
            for hand in p.hands:
                deal_card(session, hand, p.name)
        deal_card(session, dealer.dealer_hand, dealer.name)

    log.debug(f"\n  Dealer ({dealer.name}) shows: {dealer.dealer_hand.cards[0]}, ?")
    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            tag = " (also dealer)" if p.is_dealer else ""
            log.debug(f"  {p.name}{tag} Hand {i+1}: {hand}")
            if hand.is_blackjack():
                log.debug(f"  *** {p.name} Hand {i+1} — BLACKJACK! ***")

    # Four-aces check after first deal (drinking mode only)
    if session.drinking_mode:
        all_cards = [c for p in session.all_players for h in p.hands for c in h.cards]
        all_cards += dealer.dealer_hand.cards
        msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, "first_deal", session._four_aces_fd)
        session.tracker.apply(msgs)

    # Set up insurance vote slots if dealer shows Ace
    session.round._insurance_votes = []
    if dealer.dealer_hand.cards[0].rank.label == "A" and session.drinking_mode:
        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if hand.is_blackjack():
                    session.round._insurance_votes.append({
                        "player":    p.name,
                        "hand_idx":  i,
                        "votes":     {},
                        "resolved":  False,
                        "started_at": _time.monotonic(),
                    })


def dealer_turn(session: GameRoom) -> None:
    """
    Reveal the dealer hole card, hit until 17+, evaluate all player hands,
    and fire all relevant drinking rules.
    """
    dealer = session._get_dealer()
    d_hand = dealer.dealer_hand

    # Apply deferred ace messages now that hidden cards are revealed
    deferred = session.round._deferred_hole_card_msgs
    if deferred:
        session.tracker.apply(deferred)
        for msg in deferred:
            if len(msg) >= 2 and msg[1] and msg[1] > 0:
                _push_ace_drink_event(session, msg)
        session.round._deferred_hole_card_msgs = []

    log.debug(f"\n--- Dealer ({dealer.name}) reveals ---")
    log.debug(f"  Full hand: {d_hand}")

    if d_hand.is_blackjack():
        log.debug("  Dealer BLACKJACK!")
    else:
        while d_hand.score() < 17:
            card = deal_card(session, d_hand, dealer.name)
            log.debug(f"  Dealer hits: {card}  -> {d_hand}")
        if d_hand.is_bust():
            log.debug("  Dealer BUSTS!")
        else:
            log.debug(f"  Dealer stands at {d_hand.score()}.")

    drinking = session.drinking_mode
    if drinking:
        session.tracker.apply(DrinkingRules.handle(DealerHandRevealedEvent(dealer_hand=d_hand)))
        if DrinkingRules.dealer_21_five_cards(d_hand):
            log.debug(f"\n  ★ Dealer 21 with {len(d_hand.cards)} cards — wager DOUBLED this round!")

    log.debug("\n--- Results ---")
    dealer_bj = d_hand.is_blackjack()
    all_names = [p.name for p in session.all_players]

    if dealer_bj and drinking:
        log.debug("  ★ Dealer blackjack — auto-insurance: only net-loss sips will apply.")

    # Pass 1 — resolve all hand results
    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            if not hand.result:
                hand.result = HandEvaluator.compare(hand, d_hand)
            icon = {"win": "WIN", "loss": "LOSS", "push": "PUSH"}[hand.result]
            log.debug(f"  {p.name} Hand {i+1}: {hand}  => {icon}")

    # Detect hard / soft dealer switch
    all_results = [h.result for p in session.all_players for h in p.hands]
    hard_switch = bool(all_results) and all(r == "win"  for r in all_results)
    soft_switch = bool(all_results) and all(r == "loss" for r in all_results)
    if soft_switch:
        insured_bj = any(
            h.insured and h.is_blackjack()
            for p in session.all_players for h in p.hands
        )
        if insured_bj:
            soft_switch = False
            log.debug("  Soft Switch suppressed — insurance on blackjack.")
    if hard_switch:
        session.round.switch_this_round = "hard"
        log.debug("  >>> HARD DEALER SWITCH <<<")
    elif soft_switch:
        session.round.switch_this_round = "soft"
        log.debug("  >>> SOFT DEALER SWITCH — dealer wins all, role passes <<<")
    else:
        session.round.switch_this_round = None

    # Pass 2 — fire drinking events
    if drinking:
        exempt_dealer   = session.dealer_name if hard_switch else ""
        insurance_votes = session.round._insurance_votes
        voted_keys      = {(v["player"], v["hand_idx"]) for v in insurance_votes}

        if session._insurance_result is None:
            session._insurance_result = []

        # Collect all end-of-round drink messages; apply together so 4-player
        # halving operates on each player's total for the round, not per event.
        eor_msgs = []

        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if hand.is_blackjack() and (p.name, i) in voted_keys:
                    vote          = next(v for v in insurance_votes
                                         if v["player"] == p.name and v["hand_idx"] == i)
                    # Bots abstain — only humans with drinking stake count
                    # toward the majority. Non-voting humans default to
                    # decline; ties (incl. 0-0 when everyone is a bot)
                    # default to decline.
                    voters        = [x for x in session.all_players
                                      if x.name != p.name and not getattr(x, "is_npc", False)]
                    insure_count  = sum(1 for v in vote["votes"].values() if v)
                    decline_count = len(voters) - insure_count
                    insured       = insure_count > decline_count   # tie -> decline
                    vote["resolved"] = True
                    eor_msgs.extend(DrinkingRules.handle(InsuranceResolvedEvent(
                        player_name=p.name, hand=hand, all_names=all_names,
                        insured=insured, dealer_bj=dealer_bj,
                        hard_switch_dealer=exempt_dealer,
                    )))
                    # group_won: insure+BJ or decline+no BJ
                    group_won = (insured and dealer_bj) or (not insured and not dealer_bj)
                    session._insurance_result.append({
                        "player":    p.name,
                        "insured":   insured,
                        "dealer_bj": dealer_bj,
                        "group_won": group_won,
                    })
                elif hand.is_blackjack() and hand.result == "win":
                    eor_msgs.extend(DrinkingRules.handle(BlackjackEvent(
                        player_name=p.name, hand=hand, all_names=all_names,
                        hard_switch_dealer=exempt_dealer,
                    )))
                eor_msgs.extend(DrinkingRules.handle(HandResolvedEvent(
                    player_name=p.name, hand=hand, all_names=all_names,
                    dealer_bj=dealer_bj, dealer_name=exempt_dealer,
                )))

        # Hard dealer switch -- dealer drinks per each winning hand
        if hard_switch:
            winning_hds = [
                (p.name, hand)
                for p in session.all_players
                for hand in p.hands
                if hand.result == "win"
            ]
            partial_protected = session._ace_clubs_flag.get("partial_protected", False)
            half_protected    = session._ace_clubs_flag.get("half_protected", False)
            hs_for_penalty = (
                [h for h in winning_hds if h[0].lower() != session.dealer_name.lower()]
                if partial_protected else winning_hds
            )
            eor_msgs.extend(DrinkingRules.handle(HardDealerSwitchEvent(
                dealer_name=session.dealer_name, winning_hands=hs_for_penalty,
                half_protected=half_protected,
            )))
            session._hard_switch_drinking_applied = True

        # All-hands sweep
        for p in session.all_players:
            if p.is_dealer:
                continue
            eor_msgs.extend(DrinkingRules.handle(AllHandsSweepEvent(
                player_name=p.name, player_hands=p.hands, all_names=all_names,
                wager=session.wager, dealer_name=exempt_dealer, dealer_bj=dealer_bj,
            )))

        # Four-aces end-of-round check
        all_cards  = [c for p in session.all_players for h in p.hands for c in h.cards]
        all_cards += d_hand.cards
        four_aces_msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, "end_of_round", session._four_aces_fd)
        eor_msgs.extend(four_aces_msgs)

        # Buffer msgs — cmd_endround will combine with RoundEndEvent (net losses)
        # and flush through apply_end_of_round once, so halving operates on the
        # full-round total per player, not on each batch independently.
        session.round._eor_msgs_buffer = eor_msgs


# ---------------------------------------------------------------------------
# NPC auto-play
# ---------------------------------------------------------------------------

def bust_vote_pending(session: GameRoom) -> bool:
    """Return True while the bust-vote window is open and at least one human
    non-dealer player hasn't cast a vote yet.

    Used to block play actions (hit/stand/double/split and NPC auto-play) until
    all human players have had a chance to vote on the dealer-bust side bet.
    Returns False once the window expires so the timeout always unblocks play.
    """
    if not session.bust_vote_enabled:
        return False
    if session.round._bust_vote_expires_at is None:
        return False
    if _time.monotonic() >= session.round._bust_vote_expires_at:
        return False
    return any(
        session.round._bust_votes.get(p.name) is None
        for p in session.all_players
        if not getattr(p, "is_npc", False)
    )


def auto_play_npc_turns(session: GameRoom) -> None:
    """
    Auto-play all consecutive NPC turns using basic strategy.
    Stops when it reaches a human player's turn, no one is up,
    or the phase leaves 'playing'. Safety-capped at 100 steps.
    """
    # Don't play NPC hands until all human players have voted on the bust side
    # bet — NPCs auto-vote "pass" at deal time, so only human votes can block.
    if bust_vote_pending(session):
        return

    for _ in range(100):
        deal_pending_split_cards(session)
        if round_phase(session) != "playing":
            break
        turn = current_turn(session)
        if not turn:
            break
        player = session._get_player(turn)
        if not player or not getattr(player, "is_npc", False):
            break   # human's turn — stop

        hand = next((h for h in player.hands if not hand_done(h)), None)
        if not hand:
            break

        hand_idx   = player.hands.index(hand)
        hand_label = f"hand{hand_idx + 1}"
        dealer     = session._get_dealer()
        dealer_up  = dealer.dealer_hand.cards[0]

        valid = ["h", "s"]
        if len(hand.cards) == 2 and not hand.doubled:
            valid.append("d")
        if hand.can_split():
            valid.append("sp")

        suggestion_key = f"{player.name.lower()}:{hand_label}"
        suggested      = session.round._suggestions.pop(suggestion_key, None)
        if suggested in valid:
            action = suggested
        else:
            action = NPC_Player.best_play(
                hand, dealer_up, valid,
                drinking_mode=session.drinking_mode)
        log.debug(f"  {player.name} (NPC) {hand_label}: {action.upper()}")

        record_decision(session, player, hand, action, is_npc=True)

        if action == "h":
            card = deal_card(session, hand, player.name)
            log.debug(f"  {player.name} {hand_label} hits {card}: {hand}")
            if hand.is_bust():
                hand.bust = hand.stood = True
                hand.result = "loss"
                log.debug("  BUST!")
            elif hand.score() == 21:
                hand.stood = True
                log.debug(f"  {player.name} {hand_label}: auto-stands at 21.")

        elif action == "s":
            hand.stood = True
            log.debug(f"  {player.name} {hand_label}: stands at {hand.score()}.")

        elif action == "d":
            hand.doubled = True
            deal_card(session, hand, player.name)
            hand.stood = True
            log.debug(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
            if hand.is_bust():
                hand.bust = True
                hand.result = "loss"

        elif action == "sp":
            perform_split(session, player, hand, hand_idx)
            log.debug(f"  {player.name} splits {hand_label}")
