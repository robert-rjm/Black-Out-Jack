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
from drinking_rules import DrinkingRules, classify_rule
from app.config import MILESTONE_STEP, MILESTONE_HANDOUT_SIPS, MILESTONE_TTL


# ---------------------------------------------------------------------------
# Rule classification
# ---------------------------------------------------------------------------

# classify_rule imported from drinking_rules


# ---------------------------------------------------------------------------
# Bust vote penalties
# ---------------------------------------------------------------------------

def apply_bust_vote_penalties(session: GameRoom) -> None:
    """Resolve dealer-bust confidence votes.

    Only players who voted 'bust' are affected:
      - dealer busted  → correct: -1 sip credit + 1 sip to hand out (via /give_bust_sip)
      - dealer stood   → wrong:   +1 sip penalty
    Players who abstained are unaffected.
    Builds session._bust_vote_result for the toast.
    """
    if not session.bust_vote_enabled:
        session._bust_vote_result = None
        return

    voters = {name: v for name, v in session._bust_votes.items() if v == "bust"}
    if not voters:
        session._bust_vote_result = None
        return

    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand:
        session._bust_vote_result = None
        return

    dealer_busted = dealer.dealer_hand.is_bust()
    winners, losers = [], []
    session._bust_handouts_given = set()   # reset handout tracking for this round

    for p in session.all_players:
        if p.name not in voters:
            continue
        if dealer_busted:
            p.add_drink(-1, "bust vote correct: -1 sip credit", "player")
            winners.append(p.name)
            print(f"  [bust vote] {p.name} called it — -1 sip + 1 to give out")
        else:
            p.add_drink(1, "Bust vote wrong — dealer didn't bust: +1 sip", "player")
            losers.append(p.name)
            print(f"  [bust vote] {p.name} wrong — +1 sip")

    session._bust_vote_result = {
        "dealer_busted": dealer_busted,
        "winners":       winners,
        "losers":        losers,
    } if (winners or losers) else None


# ---------------------------------------------------------------------------
# Display-reason helper — strip verbose detail from panel labels
# ---------------------------------------------------------------------------

def _display_reason(rule: str, raw: str) -> str:
    """Return a human-readable label for the drinks detail panel."""
    return raw


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

    # Live sip ticker — cumulative net totals across all rounds (credits reduce total)
    ticker = session._sip_ticker
    for p in session.all_players:
        net = max(0, sum((e[0] or 0) for e in p.drink_log if e))
        if net > 0:
            ticker[p.name] = ticker.get(p.name, 0) + net
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
        # Store raw (unclamped) net so that bust-sip handouts added later via
        # /give_bust_sip are offset correctly against any existing -1 credits.
        # e.g. -1 credit + 1 assigned = 0 net, not 1.
        # Callers that display or accumulate sips clamp to 0 themselves.
        raw = sum((e[0] or 0) for e in p.drink_log if e)
        if raw != 0:
            last[p.name] = raw
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
                rule = classify_rule(reason)
                if rule is None:
                    # Display-only waived entry (A♣ protected hard switch) — show but skip CSV
                    if reason and "A♣ protected" in reason:
                        drinks_detail.append({"name": p.name, "sips": sips,
                                              "reason": f"Hard Dealer Switch — A♣ protected ({sips} sip(s) waived)"})
                    continue
                drinks_detail.append({"name": p.name, "sips": sips,
                                      "reason": _display_reason(rule, reason)})
            elif sips and sips < 0 and reason:
                # Credit entries — show green in drinks detail, skip CSV
                if "bust vote correct" in reason:
                    drinks_detail.append({"name": p.name, "sips": sips,
                                          "reason": "-1 sip credit from dealer bust"})
                elif "A♣ protection credit" in reason or ("A♣" in reason and "credit" in reason):
                    drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})
                elif "Sweep cancels doubled-hand drink" in reason:
                    drinks_detail.append({"name": p.name, "sips": sips,
                                          "reason": "-1 sip: doubled-hand drink waived (covered by sweep)"})
            elif reason and "Hard Switch triggered" in reason:
                notices.append(reason)
    session._last_round_drinks  = drinks_detail
    session._round_notices      = notices

    # Hand outcome stats per player (win/loss/push, splits, doubles, BJs, busts).
    # Includes the dealer-player's p.hands — they play as a regular player too.
    hand_stats = session._hand_stats
    for p in session.all_players:
        if p.name not in hand_stats:
            hand_stats[p.name] = {
                "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
                "split_hands": 0, "split_wins": 0,
                "double_hands": 0, "double_wins": 0,
                "blackjacks": 0,  "busts": 0,
            }
        hs = hand_stats[p.name]
        # Back-fill missing keys for sessions started before this field was added
        hs.setdefault("blackjacks", 0)
        hs.setdefault("busts", 0)
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
            if hand.is_blackjack() and result == "win":
                hs["blackjacks"] += 1
            if getattr(hand, "bust", False) or hand.is_bust():
                hs["busts"] += 1
    session._hand_stats = hand_stats

    # Max single-round sip hit per player
    mx = session._max_round_sips
    for name, raw in session._last_round_sips.items():
        net = max(0, raw)
        if net > mx.get(name, 0):
            mx[name] = net
    session._max_round_sips = mx

    # Dealer bust counter
    dealer_player = next((p for p in session.all_players if p.is_dealer), None)
    if dealer_player and getattr(dealer_player, "dealer_hand", None):
        if dealer_player.dealer_hand.is_bust():
            session._dealer_bust_rounds += 1

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

    # Win/loss streaks per player.
    # Win round  = net wins  > 0 (won more hands than lost)
    # Loss round = net losses > 0 (lost more hands than won)
    # Neutral    = equal → resets current streak to 0
    streaks = session._streaks
    for p in session.all_players:
        round_wins   = sum(1 for h in p.hands if getattr(h, "result", None) == "win")
        round_losses = sum(1 for h in p.hands if getattr(h, "result", None) == "loss")
        net = round_wins - round_losses
        if not any(getattr(h, "result", None) in ("win", "loss", "push") for h in p.hands):
            continue  # no resolved hands this round — skip
        if p.name not in streaks:
            streaks[p.name] = {"current": 0, "longest_win": 0, "longest_loss": 0}
        s = streaks[p.name]
        if net > 0:
            s["current"] = s["current"] + 1 if s["current"] > 0 else 1
            s["longest_win"] = max(s["longest_win"], s["current"])
        elif net < 0:
            s["current"] = s["current"] - 1 if s["current"] < 0 else -1
            s["longest_loss"] = max(s["longest_loss"], abs(s["current"]))
        else:
            s["current"] = 0   # neutral round breaks streak
    session._streaks = streaks


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
        this_round    = max(0, last.get(name, 0))  # clamp: credits don't inflate prev total
        prev_total    = total - this_round
        prev_boundary = (prev_total // MILESTONE_STEP) * MILESTONE_STEP
        for boundary in range(prev_boundary + MILESTONE_STEP, highest + 1, MILESTONE_STEP):
            if claimed.get(boundary):
                continue
            newly_hit.setdefault(boundary, []).append((this_round, name))

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
