"""
app/services/drink_tracker.py
==============================
End-of-round drink accounting: harvesting drink logs, tracking stats,
and checking milestone boundaries.

All functions accept a session object — this module never imports
session_store. The route layer owns the store lookup and passes the
session down.
"""

import time

from app.models.game_room import GameRoom
from app.config import MILESTONE_STEP, MILESTONE_HANDOUT_SIPS, MILESTONE_TTL


# ---------------------------------------------------------------------------
# Rule classification
# ---------------------------------------------------------------------------

def classify_rule(reason: str) -> str | None:
    """
    Normalise a raw drink-reason string to a short canonical rule name.
    Returns None for bookkeeping entries that should not appear in the CSV.
    Mirrors classify_rule() in simulation.py.
    """
    r = reason
    if "A♣" in r and "credit" in r:           return None
    if "protects" in r:                         return None
    if "exempt" in r:                           return None
    if "Hard Dealer Switch" in r:              return "Hard Dealer Switch"
    if "net loss" in r:                        return "Net hand losses"
    if "lost a doubled hand" in r:             return "Lost doubled hand"
    if "lost a suited hand" in r:              return "Lost suited hand"
    if "immunity exception" in r:              return "Doubled win (immunity break)"
    if "won suited hand" in r:                 return "Suited winning hand"
    if "split hand" in r:                      return "Split win (immunity break)"
    if "swept all hands" in r:                return "Other-player sweep"
    if "Blackjack by" in r:                    return "Blackjack bonus"
    if "4 Aces" in r and "first deal" in r:   return "Four Aces (first deal)"
    if "4 Aces" in r and "end of round" in r:  return "Four Aces (end of round)"
    if "Dealer hand is all" in r:              return "Dealer suited hand"
    if "handed" in r and "5-card 21" in r:    return "5-card 21 handout received"
    if "won with" in r and "cards" in r:       return "5+ card win"
    if "A♠" in r and "to dealer" in r:        return "Ace dealt: Ace of Spades (dealer hand)"
    if "A♥" in r and "dealer" in r:           return "Ace dealt: Ace of Hearts (dealer hand)"
    if "A♦" in r and "dealer" in r:           return "Ace dealt: Ace of Diamonds (dealer hand)"
    if "A♠" in r:                             return "Ace dealt: Ace of Spades (player hand)"
    if "A♥" in r:                             return "Ace dealt: Ace of Hearts (player hand)"
    if "A♦" in r:                             return "Ace dealt: Ace of Diamonds (player hand)"
    return "Other"


# ---------------------------------------------------------------------------
# Log harvesting
# ---------------------------------------------------------------------------

def harvest_drink_log(session: GameRoom) -> None:
    """
    Copy the current round's drink_log entries from every player into the
    session-wide CSV accumulator. Call this right after cmd_endround() and
    before start_round() resets drink_log to [].
    """
    rows      = session._drink_csv_rows
    round_num = session.round_count
    dealer    = session.dealer_name

    for p in session.all_players:
        for entry in p.drink_log:
            sips   = entry[0]
            reason = entry[1]
            role   = entry[2] if len(entry) > 2 else "player"
            if sips <= 0:
                continue
            rule = classify_rule(reason)
            if rule is None:
                continue
            rows.append({
                "round":  round_num,
                "dealer": dealer,
                "player": p.name,
                "role":   role,
                "rule":   rule,
                "sips":   sips,
            })
    session._drink_csv_rows = rows

    # Live sip ticker — cumulative raw totals across all rounds
    ticker = session._sip_ticker
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            if sips > 0:
                ticker[p.name] = ticker.get(p.name, 0) + sips
    session._sip_ticker          = ticker
    session._drink_log_harvested = True

    # Cumulative dealer-role sips (shown in dealer panel)
    d_ticker = session._dealer_role_ticker
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            role = entry[2] if len(entry) > 2 else "player"
            if sips > 0 and role == "dealer":
                d_ticker[p.name] = d_ticker.get(p.name, 0) + sips
    session._dealer_role_ticker = d_ticker

    # Shift snapshots before overwriting (enables round-over comparison)
    session._prev_round_sips   = session._last_round_sips
    session._prev_round_drinks = session._last_round_drinks

    # Per-player sip totals for the "Last Round" panel
    last = {}
    for p in session.all_players:
        total = sum(e[0] for e in p.drink_log if e and e[0] > 0)
        if total > 0:
            last[p.name] = total
    session._last_round_sips = last

    # Detailed drink entries for the Drinks pane
    drinks_detail = []
    notices       = []
    for p in session.all_players:
        for entry in p.drink_log:
            if not entry or len(entry) < 2:
                continue
            sips   = entry[0]
            reason = entry[1]
            if sips and sips > 0:
                if classify_rule(reason) is None:
                    continue
                drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})
            elif reason and "Hard Switch triggered" in reason:
                notices.append(reason)
    session._last_round_drinks  = drinks_detail
    session._round_notices      = notices

    # Hand outcome stats per player (win/loss/push, splits, doubles)
    hand_stats = session._hand_stats
    for p in session.all_players:
        if p.is_dealer:
            continue
        if p.name not in hand_stats:
            hand_stats[p.name] = {
                "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
                "split_hands": 0, "split_wins": 0,
                "double_hands": 0, "double_wins": 0,
            }
        hs = hand_stats[p.name]
        for hand in p.hands:
            result = getattr(hand, "result", None)
            if result not in ("win", "loss", "push"):
                continue
            hs["hands"] += 1
            if result == "win":    hs["wins"]   += 1
            elif result == "loss": hs["losses"] += 1
            elif result == "push": hs["pushes"] += 1
            if getattr(hand, "from_split", False):
                hs["split_hands"] += 1
                if result == "win": hs["split_wins"] += 1
            if getattr(hand, "doubled", False):
                hs["double_hands"] += 1
                if result == "win": hs["double_wins"] += 1
    session._hand_stats = hand_stats

    # Dealer hand stats — wins/losses/pushes from the dealer's POV
    # (player "win" = dealer lost that hand, and vice versa)
    dealer_stats = session._dealer_hand_stats
    dname = session.dealer_name
    if dname not in dealer_stats:
        dealer_stats[dname] = {"hands": 0, "wins": 0, "losses": 0, "pushes": 0}
    ds = dealer_stats[dname]
    for p in session.all_players:
        if p.is_dealer:
            continue
        for hand in p.hands:
            result = getattr(hand, "result", None)
            if result not in ("win", "loss", "push"):
                continue
            ds["hands"] += 1
            if result == "win":    ds["losses"] += 1   # player wins = dealer lost
            elif result == "loss": ds["wins"]   += 1   # player loses = dealer won
            elif result == "push": ds["pushes"] += 1
    session._dealer_hand_stats = dealer_stats


# ---------------------------------------------------------------------------
# Milestone checking
# ---------------------------------------------------------------------------

def check_and_set_milestone(session: GameRoom) -> None:
    """
    After harvesting a round's drink log, check whether any player has newly
    crossed a MILESTONE_STEP boundary. If so, record the winner in
    session._pending_milestone so the frontend can display the handout UI.

    Tiebreak: fewest sips THIS round wins (prevents gaming). Alphabetical
    name order breaks any remaining tie.

    Each boundary fires only once (tracked in session._milestones_claimed).
    """
    ticker  = session._sip_ticker
    last    = session._last_round_sips
    claimed = session._milestones_claimed

    newly_hit: dict[int, list[tuple[int, str]]] = {}
    for name, total in ticker.items():
        highest      = (total // MILESTONE_STEP) * MILESTONE_STEP
        if highest <= 0:
            continue
        prev_total    = total - last.get(name, 0)
        prev_boundary = (prev_total // MILESTONE_STEP) * MILESTONE_STEP
        for boundary in range(prev_boundary + MILESTONE_STEP, highest + 1, MILESTONE_STEP):
            if claimed.get(boundary):
                continue
            newly_hit.setdefault(boundary, []).append((last.get(name, 0), name))

    if not newly_hit:
        return

    boundary   = min(newly_hit.keys())
    candidates = newly_hit[boundary]
    candidates.sort(key=lambda t: (t[0], t[1].lower()))
    _round_sips, winner = candidates[0]

    claimed[boundary] = winner
    session._milestones_claimed = claimed
    session._pending_milestone  = {
        "boundary":   boundary,
        "winner":     winner,
        "handout":    MILESTONE_HANDOUT_SIPS,
        "expires_at": time.monotonic() + MILESTONE_TTL,
    }
