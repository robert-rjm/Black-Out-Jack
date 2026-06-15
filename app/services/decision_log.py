"""
app/services/decision_log.py
=============================
Phase C of docs/planning/DecisionLog-Plan.md — captures one row per player
decision (hit/stand/double/split/insurance) with enough board-state context
to later train per-player "mimicry" bots.

This module never imports session_store — the route layer owns the store
lookup and passes the session (GameRoom) down, mirroring drink_tracker.py.
"""

from __future__ import annotations

import time

from app.models.game_room import GameRoom
from engine.strategy import best_play as _best_play, is_soft_hand


# ---------------------------------------------------------------------------
# Visible-card snapshot
# ---------------------------------------------------------------------------

def _snapshot_visible_cards(session: GameRoom) -> list[str]:
    """
    Every card visible table-wide at this instant: all players' in-play
    hands + the dealer's revealed upcard. The dealer's hole card is NEVER
    included here (it's hidden from players during play).
    """
    visible: list[str] = []
    for p in session.all_players:
        for hand in p.hands:
            for card in hand.cards:
                visible.append(str(card))

    dealer = session._get_dealer()
    if dealer and dealer.dealer_hand and dealer.dealer_hand.cards:
        visible.append(str(dealer.dealer_hand.cards[0]))  # upcard only

    return visible


# ---------------------------------------------------------------------------
# Decision capture
# ---------------------------------------------------------------------------

def record_decision(session: GameRoom, player, hand, action: str, *,
                     is_npc: bool = False) -> None:
    """
    Append one row to session._decision_log for the decision `player` is
    about to make on `hand` (must be called BEFORE the action mutates the
    hand, so hand_cards_before/hand_total_before reflect the pre-action
    state).

    `action` is one of "h", "s", "d", "sp", "insurance".
    """
    dealer = session._get_dealer()
    dealer_upcard = None
    if dealer and dealer.dealer_hand and dealer.dealer_hand.cards:
        dealer_upcard = dealer.dealer_hand.cards[0]

    # Valid actions available at decision time (mirrors the call sites'
    # own validity checks — recomputed here so the row is self-describing).
    if action == "insurance":
        valid_actions = ["insurance", "decline"]
    else:
        valid_actions = ["h", "s"]
        if len(hand.cards) == 2 and not hand.doubled:
            valid_actions.append("d")
        if hand.can_split():
            valid_actions.append("sp")

    basic_strategy_action = None
    if action != "insurance" and dealer_upcard is not None and len(hand.cards) >= 1:
        try:
            basic_strategy_action = _best_play(
                hand, dealer_upcard, valid_actions,
                drinking_mode=session.drinking_mode)
        except Exception:
            basic_strategy_action = None

    shoe = session.shoe
    row = {
        "session_id":              session.room_code,
        "timestamp":               time.time(),
        "round":                   session.round_count,
        "player":                  player.name,
        "hand_index":              player.hands.index(hand) + 1 if hand in player.hands else None,
        "dealer_name":             session.dealer_name,
        "hand_cards_before":       " ".join(str(c) for c in hand.cards),
        "hand_total_before":       hand.score(),
        "is_soft":                 is_soft_hand(hand),
        "dealer_upcard":           str(dealer_upcard) if dealer_upcard else "",
        "visible_cards":           " ".join(_snapshot_visible_cards(session)),
        "cards_remaining":         len(shoe.cards) if shoe else None,
        "decks_in_play":           shoe.num_decks if shoe else None,
        "valid_actions":           ",".join(valid_actions),
        "action_taken":            action,
        "basic_strategy_action":   basic_strategy_action,
        "drinking_mode":           session.drinking_mode,
        "mode":                    session.mode,
        "bet_amount":              getattr(session, "bet_amount", None) if not session.drinking_mode else None,
        "wager":                   session.wager if session.drinking_mode else None,
        "is_npc":                  is_npc or getattr(player, "is_npc", False),
        "hand_result":             None,  # backfilled in backfill_hand_results()
        # Internal-only field, used to match this row up after the round
        # resolves — stripped before export.
        "_hand_id":                id(hand),
    }
    session._decision_log.append(row)


# ---------------------------------------------------------------------------
# Result backfill
# ---------------------------------------------------------------------------

def backfill_hand_results(session: GameRoom) -> None:
    """
    After the round resolves (hand.result is set to "win"/"loss"/"push" for
    every hand), walk this round's decision-log rows and fill in
    `hand_result` for any row still missing it.

    Safe to call multiple times — only fills rows that are still None.
    """
    round_num = session.round_count

    # Build a lookup from id(hand) -> result for this round's hands.
    hand_results: dict[int, str] = {}
    for p in session.all_players:
        for hand in p.hands:
            result = getattr(hand, "result", None)
            if result in ("win", "loss", "push"):
                hand_results[id(hand)] = result

    for row in session._decision_log:
        if row["round"] != round_num or row["hand_result"] is not None:
            continue
        result = hand_results.get(row["_hand_id"])
        if result is not None:
            row["hand_result"] = result
