"""
strategy.py
========================
Basic Strategy Lookup
========================
Standalone module containing the basic strategy tables and best_play()
resolver. Used by NPC_Player (blackjack.py), the web game engine, and
strategy deviation tracking.

Action codes:  "h" = hit   "s" = stand   "d" = double   "sp" = split
"""


# =============================================================================
# Lookup tables
# =============================================================================

# Hard totals: (player_total, dealer_up_value) -> action
_BS_HARD = {
    **{(s, d): "h" for s in range(4, 9)  for d in range(2, 12)},
    **{(9,  d): ("d" if 3 <= d <= 6 else "h") for d in range(2, 12)},
    **{(10, d): ("d" if 2 <= d <= 9 else "h") for d in range(2, 12)},
    **{(11, d): "d" for d in range(2, 12)},
    **{(12, d): ("h" if d in (2, 3) or d >= 7 else "s") for d in range(2, 12)},
    **{(s,  d): ("h" if d >= 7 else "s") for s in range(13, 17) for d in range(2, 12)},
    **{(s,  d): "s" for s in range(17, 22) for d in range(2, 12)},
}

# Soft totals: (player_total, dealer_up_value) -> action
_BS_SOFT = {
    **{(13, d): ("d" if 5 <= d <= 6 else "h") for d in range(2, 12)},
    **{(14, d): ("d" if 5 <= d <= 6 else "h") for d in range(2, 12)},
    **{(15, d): ("d" if 4 <= d <= 6 else "h") for d in range(2, 12)},
    **{(16, d): ("d" if 4 <= d <= 6 else "h") for d in range(2, 12)},
    **{(17, d): ("d" if 3 <= d <= 6 else "h") for d in range(2, 12)},
    **{(18, d): ("d" if 3 <= d <= 6 else "s" if d in (2, 7, 8) else "h") for d in range(2, 12)},
    **{(s,  d): "s" for s in range(19, 22) for d in range(2, 12)},
}

# Pair split: (pair_rank_value, dealer_up_value) -> action
# Drinking-mode 10-split override is applied in best_play(), not here.
_BS_PAIR = {
    **{(11, d): "sp"                                        for d in range(2, 12)},  # A-A always split
    **{(10, d): "s"                                         for d in range(2, 12)},  # 10s stand (drinking overrides)
    **{(9,  d): ("sp" if d not in (7, 10, 11) else "s")    for d in range(2, 12)},  # 9-9
    **{(8,  d): "sp"                                        for d in range(2, 12)},  # 8-8 always split
    **{(7,  d): ("sp" if d <= 7 else "h")                  for d in range(2, 12)},  # 7-7
    **{(6,  d): ("sp" if 2 <= d <= 6 else "h")             for d in range(2, 12)},  # 6-6
    **{(5,  d): ("d" if 2 <= d <= 9 else "h")              for d in range(2, 12)},  # 5-5 never split → treat as 10
    **{(4,  d): ("sp" if 5 <= d <= 6 else "h")             for d in range(2, 12)},  # 4-4
    **{(3,  d): ("sp" if 2 <= d <= 7 else "h")             for d in range(2, 12)},  # 3-3
    **{(2,  d): ("sp" if 2 <= d <= 7 else "h")             for d in range(2, 12)},  # 2-2
}


# =============================================================================
# Helpers
# =============================================================================

def is_soft_hand(hand) -> bool:
    """True when the hand contains a live Ace counted as 11."""
    total = sum(c.rank.blackjack_value for c in hand.cards)
    # An ace is soft when it's still counted as 11 (blackjack_value == 11)
    aces  = sum(1 for c in hand.cards if c.rank.blackjack_value == 11)
    return aces > 0 and total <= 21


# =============================================================================
# Resolver
# =============================================================================

def best_play(hand, dealer_up_card, valid_actions: list,
              drinking_mode: bool = False) -> str:
    """
    Return the basic-strategy optimal action for any hand.

    Args:
        hand:            Hand object (cards, score(), can_split(), is_suited())
        dealer_up_card:  Card object (the dealer's visible card)
        valid_actions:   List of currently legal actions, e.g. ["h","s","d","sp"]
        drinking_mode:   When True applies drinking-rule overrides (mandatory
                         10-split, aggressive doubling on 9/10/11)

    Returns:
        One of "h", "s", "d", "sp"
    """
    score   = hand.score()
    d_val   = min(dealer_up_card.rank.blackjack_value, 10)
    soft    = is_soft_hand(hand)

    # --- Drinking mode overrides ---
    if drinking_mode:
        if "sp" in valid_actions and hand.can_split():
            rv = hand.cards[0].rank.blackjack_value
            if rv == 10 and not hand.is_suited():
                return "sp"
            if rv == 9 and d_val != 10:
                return "sp"
            if rv == 5 and "d" in valid_actions:
                return "d"
        if score in (9, 10, 11) and "d" in valid_actions:
            return "d"

    # --- Pair split ---
    if "sp" in valid_actions and hand.can_split():
        rv  = hand.cards[0].rank.blackjack_value
        raw = _BS_PAIR.get((rv, d_val), "h")
        if raw in valid_actions:
            return raw
        return "h" if raw == "d" else "s"

    # --- Hard / soft table ---
    table = _BS_SOFT if soft else _BS_HARD
    ideal = table.get((score, d_val), "s")
    if ideal == "d" and "d" not in valid_actions:
        ideal = "h"
    return ideal if ideal in valid_actions else "s"
