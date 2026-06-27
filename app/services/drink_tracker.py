"""
app/services/drink_tracker.py
==============================
End-of-round drink accounting: harvesting drink logs, tracking stats,
and checking milestone boundaries.

All functions accept a session object — this module never imports
session_store. The route layer owns the store lookup and passes the
session down.
"""

import logging
import time

from app.models.game_room import GameRoom
from app.services.utils import classify_rule
from app.config import (
    MILESTONE_STEP,
    MILESTONE_TTL,
    MILESTONE_HANDOUT_SIPS,
    BUST_HANDOUT_WINDOW_SECONDS,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule classification
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Central sip-award helper
# ---------------------------------------------------------------------------

def award_sips(
    session: GameRoom,
    player_name: str,
    sips: int,
    rule: str,
    *,
    role: str = "player",
    reason: str | None = None,
) -> None:
    """Write a post-harvest sip event to all four session-level accumulators.

    Use this for every out-of-band drink award that happens after
    ``harvest_drink_log`` has already run (bust-vote forfeits, milestone
    handouts/forfeits, give-sip routes).  Callers that also need to update the
    player's own ``drink_log`` (pre-harvest) should call ``player.add_drink()``
    separately before or after.

    Updates:
      • ``_drink_csv_rows``    — CSV export row
      • ``_sip_ticker``        — cumulative session sip count per player
      • ``_last_round_sips``   — per-player sip count for the current round
      • ``_last_round_drinks`` — ordered list shown in the Drinks panel

    If *sips* > 0, calls ``check_and_set_milestone`` so a freshly crossed
    milestone boundary is detected immediately.
    """
    session.drinks.csv_rows.append({
        "round":  session.round_count,
        "dealer": session.dealer_name,
        "player": player_name,
        "role":   role,
        "rule":   rule,
        "sips":   sips,
    })
    if sips != 0:
        session.drinks.sip_ticker[player_name] = (
            session.drinks.sip_ticker.get(player_name, 0) + sips
        )
        session.drinks.last_round_sips[player_name] = (
            session.drinks.last_round_sips.get(player_name, 0) + sips
        )
        session.drinks.last_round_drinks.append({
            "name":   player_name,
            "sips":   sips,
            "reason": reason if reason is not None else rule,
        })
    if sips > 0:
        check_and_set_milestone(session)


# ---------------------------------------------------------------------------
# Bust vote penalties
# ---------------------------------------------------------------------------

def apply_bust_vote_penalties(session: GameRoom) -> None:
    """Resolve dealer-bust confidence votes (web path).

    Only players who voted 'bust' are affected:
      - dealer busted  → correct: -1 sip credit + 1 sip to hand out (via /give_bust_sip)
      - dealer stood   → wrong:   +1 sip penalty
    Players who abstained are unaffected.
    Builds session.round._bust_vote_result for the toast.

    NOTE: There is a parallel implementation for the interactive CLI path:
    ``RefereeSession._resolve_bust_votes()`` in ``engine/referee.py``.
    The two functions must stay in sync whenever bust-vote rules change.
    The CLI version uses interactive handout prompts; this web version opens
    a timed /give_bust_sip window instead.  In web sessions bust_vote_enabled
    is always False on RefereeSession, so _resolve_bust_votes() is dead code
    for web play — but it is kept for the standalone CLI referee mode.
    """
    if not session.bust_vote_enabled:
        session.round._bust_vote_result = None
        return

    voters = {name: v for name, v in session.round._bust_votes.items() if v == "bust"}
    if not voters:
        session.round._bust_vote_result = None
        return

    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand:
        session.round._bust_vote_result = None
        return

    dealer_busted = dealer.dealer_hand.is_bust()
    winners, losers = [], []
    session.round._bust_handouts_given = set()   # reset handout tracking for this round
    session.round._bust_handout_log    = []      # reset handout reveal log for this round

    for p in session.all_players:
        if p.name not in voters:
            continue
        if dealer_busted:
            winners.append(p.name)
            # Sip credit and handout only apply in drinking mode
            if session.drinking_mode:
                p.add_drink(-1, "bust vote correct: -1 sip credit", "player")
                log.debug(f"  [bust vote] {p.name} called it — -1 sip + 1 to give out")
            else:
                log.debug(f"  [bust vote] {p.name} called it (normal mode — no sip reward)")
        else:
            losers.append(p.name)
            if session.drinking_mode:
                p.add_drink(1, "Bust vote wrong — dealer didn't bust: +1 sip", "player")
                log.debug(f"  [bust vote] {p.name} wrong — +1 sip")
            else:
                log.debug(f"  [bust vote] {p.name} wrong (normal mode — no sip penalty)")

    # In normal mode, attach the side-bet stake so the frontend and
    # payout_tracker can display / settle the correct dollar amount.
    side_bet_amount = (session.bet_amount / 2) if not session.drinking_mode else None
    normal = side_bet_amount is not None

    # Pre-build outcome strings so the frontend is a pure renderer.
    def _fmt(v):
        return f"${float(v):.2f}"

    each = " each" if len(losers) > 1 else ""
    outcome_lines = []
    if dealer_busted:
        if winners:
            reward = f" (+{_fmt(side_bet_amount * 2)} @ 2:1)" if normal else " (-1 sip + give 1)"
            outcome_lines.append(f"✅ {', '.join(winners)} called it{reward}")
        if losers:
            penalty = f" (-{_fmt(side_bet_amount)}{each})" if normal else f" (+1 sip{each})"
            outcome_lines.append(f"❌ {', '.join(losers)} wrong{penalty}")
    else:
        if losers:
            penalty = f" (-{_fmt(side_bet_amount)}{each})" if normal else f" (+1 sip{each})"
            outcome_lines.append(f"❌ {', '.join(losers)} bet bust — wrong{penalty}")

    if normal:
        winner_label = f"called it (+{_fmt(side_bet_amount * 2)} @ 2:1)"
        loser_label  = f"wrong (−{_fmt(side_bet_amount)})"
    else:
        winner_label = "called it — -1 sip + give 1!"
        loser_label  = "wrong — +1 sip each"

    session.round._bust_vote_result = {
        "dealer_busted":   dealer_busted,
        "winners":         winners,
        "losers":          losers,
        "side_bet_amount": side_bet_amount,   # None in drinking mode
        "outcome_lines":   outcome_lines,
        "winner_label":    winner_label,
        "loser_label":     loser_label,
    } if (winners or losers) else None

    # Handout window only opens in drinking mode — in normal mode there are no sips to give
    if winners and session.drinking_mode:
        session.round._bust_handout_expires_at = time.monotonic() + BUST_HANDOUT_WINDOW_SECONDS
    else:
        session.round._bust_handout_expires_at = None


# ---------------------------------------------------------------------------
# Bust vote handout forfeit
# ---------------------------------------------------------------------------

def apply_bust_handout_forfeit(session: GameRoom) -> None:
    """
    If the bust-vote handout window has expired, penalise any winner who
    hasn't yet given away their 1-sip reward with the same +1 sip they would
    have given out (mirrors apply_milestone_forfeit).

    Safe to call on every /state tick — exits immediately if no handout
    window is pending or it hasn't closed yet.
    """
    expires = session.round._bust_handout_expires_at
    if expires is None or time.monotonic() < expires:
        return

    result  = session.round._bust_vote_result or {}
    winners = result.get("winners", [])

    for winner_name in winners:
        if winner_name in session.round._bust_handouts_given:
            continue

        winner_p = session._get_player(winner_name)
        if winner_p:
            reason = f"Bust vote forfeited — {winner_name} didn't assign in time: +1 sip"
            winner_p.add_drink(1, reason, "player")
            award_sips(session, winner_name, 1, "Bust vote handout", reason=reason)
            log_line = (
                f"  ⏱ {winner_name} didn't assign their bust-vote sip in time — "
                f"drinks 1 sip\n"
            )
            session.round._log_entries.append(log_line)
            session._log_version += 1
            log.debug(f"  [bust vote] {winner_name} forfeited handout — drinks 1 sip")

        session.round._bust_handout_log.append({
            "winner":    winner_name,
            "recipient": None,
            "forfeited": True,
        })
        session.round._bust_handouts_given.add(winner_name)

    if all(w in session.round._bust_handouts_given for w in winners):
        session.round._bust_handout_expires_at = None
        if winners:
            session._bust_handout_seq += 1


# ---------------------------------------------------------------------------
# Log harvesting — private helpers
# ---------------------------------------------------------------------------

def _record_csv_rows(session: GameRoom) -> None:
    """Append this round's drink-log entries to the session CSV accumulator."""
    rows      = session.drinks.csv_rows
    round_num = session.round_count
    dealer    = session.dealer_name
    for p in session.all_players:
        for entry in p.drink_log:
            sips   = entry[0]
            reason = entry[1]
            role   = entry[2] if len(entry) > 2 else "player"
            if sips == 0:
                continue
            if sips < 0:
                credit_rule = classify_rule(reason) or "Sip credit"
                rows.append({"round": round_num, "dealer": dealer,
                             "player": p.name, "role": role,
                             "rule": credit_rule, "sips": sips})
                continue
            rule = classify_rule(reason)
            if rule is None:
                continue
            rows.append({"round": round_num, "dealer": dealer,
                         "player": p.name, "role": role,
                         "rule": rule, "sips": sips})
    session.drinks.csv_rows = rows


def _update_sip_tickers(session: GameRoom) -> None:
    """Update cumulative sip ticker and dealer-role ticker from this round's drink log."""
    ticker = session.drinks.sip_ticker
    for p in session.all_players:
        net = max(0, sum((e[0] or 0) for e in p.drink_log if e))
        if net > 0:
            ticker[p.name] = ticker.get(p.name, 0) + net
    session.drinks.sip_ticker = ticker

    d_ticker = session.drinks.dealer_role_ticker
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            role = entry[2] if len(entry) > 2 else "player"
            if sips > 0 and role == "dealer":
                d_ticker[p.name] = d_ticker.get(p.name, 0) + sips
    session.drinks.dealer_role_ticker = d_ticker


def _snapshot_round(session: GameRoom) -> None:
    """Shift prev-round snapshots, record last-round sips, rolling history, and rounds-played."""
    session.drinks.prev_round_sips   = session.drinks.last_round_sips
    session.drinks.prev_round_drinks = session.drinks.last_round_drinks

    last = {}
    for p in session.all_players:
        # Store raw (unclamped) net so that bust-sip handouts added later via
        # /give_bust_sip are offset correctly against any existing -1 credits.
        # Always record an entry even at 0 — the frontend uses
        # `name in last_round_sips` to detect a clean round for the crown badge.
        raw = sum((e[0] or 0) for e in p.drink_log if e)
        last[p.name] = raw
    session.drinks.last_round_sips = last

    round_total = max(0, sum(last.values()))
    session._round_sip_history = session._round_sip_history + [round_total]

    rounds_played = session._player_rounds_played
    for p in session.all_players:
        rounds_played[p.name] = rounds_played.get(p.name, 0) + 1
    session._player_rounds_played = rounds_played


def _record_drinks_detail(session: GameRoom) -> None:
    """Build the Drinks-pane detail list and round notices from this round's drink log."""
    drinks_detail = []
    notices       = []
    for p in session.all_players:
        for entry in p.drink_log:
            if not entry or len(entry) < 2:
                continue
            sips   = entry[0]
            reason = entry[1]

            rule = classify_rule(reason) if reason else None

            if rule is None:
                continue  # skip entirely (exempt / protects / no reason)

            if rule == "Hard Switch notice":
                notices.append(reason)
                continue

            if sips and sips > 0:
                if rule == "A♣ waived":
                    drinks_detail.append({"name": p.name, "sips": sips,
                                          "reason": f"Hard Dealer Switch — A♣ protected ({sips} sip(s) waived)"})
                else:
                    drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})

            elif sips and sips < 0:
                if rule == "Bust vote credit":
                    drinks_detail.append({"name": p.name, "sips": sips,
                                          "reason": "-1 sip credit from dealer bust"})
                elif rule == "Sweep credit":
                    drinks_detail.append({"name": p.name, "sips": sips,
                                          "reason": "-1 sip: doubled-hand drink waived (covered by sweep)"})
                else:
                    drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})

    session.drinks.last_round_drinks = drinks_detail
    session.drinks.round_notices     = notices


def _update_hand_stats(session: GameRoom) -> None:
    """Accumulate per-player hand outcome statistics."""
    hand_stats = session._hand_stats
    for p in session.all_players:
        if p.name not in hand_stats:
            hand_stats[p.name] = {
                "hands": 0, "wins": 0, "losses": 0, "pushes": 0,
                "split_hands": 0, "split_wins": 0,
                "double_hands": 0, "double_wins": 0,
                "blackjacks": 0, "busts": 0,
                "suited_hands": 0, "hit_hands": 0,
                "stand_sub17": 0, "total_score": 0, "scored_hands": 0,
            }
        hs = hand_stats[p.name]
        for key, default in (
            ("blackjacks", 0), ("busts", 0), ("suited_hands", 0),
            ("hit_hands", 0), ("stand_sub17", 0),
            ("total_score", 0), ("scored_hands", 0),
        ):
            hs.setdefault(key, default)
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
            if hand.is_suited():
                hs["suited_hands"] += 1
            if len(hand.cards) > 2:
                hs["hit_hands"] += 1
            if (getattr(hand, "stood", False) and not getattr(hand, "bust", False)
                    and not hand.is_blackjack() and hand.score() < 17):
                hs["stand_sub17"] += 1
            if not getattr(hand, "bust", False) and not hand.is_bust():
                hs["total_score"]  += hand.score()
                hs["scored_hands"] += 1
    session._hand_stats = hand_stats


def _update_max_round_sips(session: GameRoom) -> None:
    """Track the highest single-round sip total per player."""
    mx = session._max_round_sips
    for name, raw in session.drinks.last_round_sips.items():
        net = max(0, raw)
        if net > mx.get(name, 0):
            mx[name] = net
    session._max_round_sips = mx


def _update_dealer_stats(session: GameRoom) -> None:
    """Update dealer bust counter and per-dealer win/loss/push stats."""
    dealer_player = next((p for p in session.all_players if p.is_dealer), None)
    if dealer_player and getattr(dealer_player, "dealer_hand", None):
        if dealer_player.dealer_hand.is_bust():
            session._dealer_bust_rounds += 1

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


def _update_streaks(session: GameRoom) -> None:
    """Update win/loss streaks per player.

    Win round  = net wins  > 0 (won more hands than lost).
    Loss round = net losses > 0 (lost more hands than won).
    Neutral    = equal -> resets current streak to 0.
    """
    streaks = session._streaks
    for p in session.all_players:
        round_wins   = sum(1 for h in p.hands if getattr(h, "result", None) == "win")
        round_losses = sum(1 for h in p.hands if getattr(h, "result", None) == "loss")
        net = round_wins - round_losses
        if not any(getattr(h, "result", None) in ("win", "loss", "push") for h in p.hands):
            continue  # no resolved hands this round
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
            s["current"] = 0
    session._streaks = streaks


def harvest_drink_log(session: GameRoom) -> None:
    """
    Copy the current round's drink_log entries from every player into the
    session-wide accumulators. Call this right after cmd_endround() and
    before start_round() resets drink_log to [].

    Delegates each concern to a private helper; see each helper's docstring
    for details.  Idempotent: returns immediately if already harvested.
    """
    if session.round._drink_log_harvested:
        return  # already harvested this round -- do not double-count

    _record_csv_rows(session)
    _update_sip_tickers(session)
    _snapshot_round(session)
    _record_drinks_detail(session)
    _update_hand_stats(session)
    _update_max_round_sips(session)
    _update_dealer_stats(session)
    _update_streaks(session)

    session.round._drink_log_harvested = True
    session.drinks.round_over_seq += 1   # seq-based trigger so clients never miss the toast


# ---------------------------------------------------------------------------
# Milestone checking
# ---------------------------------------------------------------------------

def _apply_worst_player_streak(session: GameRoom, winner: str, ticker: dict) -> None:
    """
    House rule: track the player with the lowest average sips/round (overall)
    at each milestone, excluding the milestone winner. If the SAME player is
    "worst" for two consecutive milestones, they take a one-time penalty —
    drinking a number of sips equal to the milestone winner's avg sips/round
    (rounded to the nearest whole sip, minimum 1).
    """
    rounds_played = session._player_rounds_played

    candidates = [
        (ticker.get(p.name, 0) / max(1, rounds_played.get(p.name, 0)), p.name.lower(), p.name)
        for p in session.all_players
        if p.name.lower() != winner.lower()
    ]
    if not candidates:
        return

    candidates.sort(key=lambda t: (t[0], t[1]))
    worst_name = candidates[0][2]

    if session.drinks.last_milestone_worst and session.drinks.last_milestone_worst.lower() == worst_name.lower():
        # Second consecutive milestone as "worst" — apply the one-time penalty.
        winner_rounds = max(1, rounds_played.get(winner, 0))
        winner_avg    = ticker.get(winner, 0) / winner_rounds
        penalty       = max(1, round(winner_avg))

        worst_p = session._get_player(worst_name)
        if worst_p:
            reason = (
                f"Worst average sips/round for 2 milestones in a row — "
                f"drinks {penalty} sip{'s' if penalty != 1 else ''} "
                f"(matching {winner}'s avg)"
            )
            worst_p.add_drink(penalty, reason, "player")
            award_sips(session, worst_name, penalty,
                       "Worst average for 2 milestones", reason=reason)
            session.round._log_entries.append(
                f"  📉 {worst_name} was the worst average for 2 milestones running — "
                f"drinks {penalty} sip{'s' if penalty != 1 else ''}\n"
            )
            session._log_version += 1
            log.debug(f"  [milestone] {worst_name} worst avg 2x in a row — drinks {penalty} sips")

    session.drinks.last_milestone_worst = worst_name


def check_and_set_milestone(session: GameRoom) -> None:
    """
    After harvesting a round's drink log, check whether any player has newly
    crossed a MILESTONE_STEP boundary. If so, record the winner in
    session.round._pending_milestone so the frontend can display the handout UI.

    Tiebreak: fewest sips THIS round wins (prevents gaming). Alphabetical
    name order breaks any remaining tie.

    Each boundary fires only once (tracked in session.drinks.milestones_claimed).
    """
    # Never overwrite an active unresolved milestone — the winner gets to hand
    # out their sips before we fire the next one.
    if session.round._pending_milestone:
        return

    ticker  = session.drinks.sip_ticker
    last    = session.drinks.last_round_sips
    claimed = session.drinks.milestones_claimed

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

    # Handout scales: MILESTONE_HANDOUT_SIPS at the first boundary, +1 sip
    # for each additional MILESTONE_STEP boundary crossed (e.g. with the
    # defaults of STEP=50 / HANDOUT=5: 5 sips at 50, 6 at 100, 7 at 150...).
    handout_sips = MILESTONE_HANDOUT_SIPS - 1 + boundary // MILESTONE_STEP

    claimed[boundary] = winner
    session.drinks.milestones_claimed = claimed

    # "Worst player" streak check — lowest avg sips/round overall, excluding
    # the milestone winner. If the same player is worst for 2 consecutive
    # milestones, they take a one-time penalty equal to the winner's avg
    # sips/round (rounded, min 1).
    _apply_worst_player_streak(session, winner, ticker)

    # NPC winners can't drive the handout-allocation UI, so resolve their
    # milestone immediately via round-robin distribution to the other
    # players rather than leaving it pending (and eventually self-forfeiting).
    winner_p = session._get_player(winner)
    if winner_p and getattr(winner_p, "is_npc", False):
        _distribute_milestone_round_robin(session, winner, boundary, handout_sips)
        return

    session.round._pending_milestone  = {
        "boundary":   boundary,
        "winner":     winner,
        "handout":    handout_sips,
        "expires_at": time.monotonic() + MILESTONE_TTL,
    }


def _distribute_milestone_round_robin(session: GameRoom, winner: str, boundary: int, handout: int) -> None:
    """
    Distribute an NPC milestone winner's handout to the other players,
    round-robin, one sip at a time (mirrors the auto-handout used for
    5-card-21 bonuses). Falls back to a self-penalty if no other players
    exist.
    """
    others = [p for p in session.all_players if p.name.lower() != winner.lower()]
    if not others:
        winner_p = session._get_player(winner)
        if winner_p:
            _solo_reason = (
                f"Milestone ({boundary} sips) — no other players to give to: "
                f"you drink {handout} sips"
            )
            winner_p.add_drink(handout, _solo_reason, "player")
            award_sips(session, winner, handout,
                       "Milestone handout (no other players)", reason=_solo_reason)
        log.debug(f"  [milestone] {winner} hit {boundary} sips — no other players, drinks {handout} sips")
        return

    log.debug(f"  [milestone] {winner} hit {boundary} sips — auto-distributes {handout} sip(s) round-robin")
    for i in range(handout):
        t = others[i % len(others)]
        _rr_reason = f"{winner} hit the {boundary}-sip milestone — you drink 1 sip (auto)"
        t.add_drink(1, _rr_reason, "player")
        award_sips(session, t.name, 1, "Milestone handout (round-robin)", reason=_rr_reason)
        log.debug(f"    -> {t.name} +1 sip")

    session.round._log_entries.append(
        f"  🎯 {winner} (bot) hit the {boundary}-sip milestone — auto-distributes "
        f"{handout} sip(s) round-robin\n"
    )
    session._log_version += 1


# ---------------------------------------------------------------------------
# Milestone forfeit
# ---------------------------------------------------------------------------

def apply_milestone_forfeit(session: GameRoom) -> None:
    """
    If the milestone handout window has expired without the winner assigning
    their sips, penalise the winner with the full handout amount and clear
    the pending milestone.

    Safe to call on every /state tick — exits immediately if no milestone is
    pending or the window has not yet closed.
    """
    ms = session.round._pending_milestone
    if not ms or time.monotonic() < ms["expires_at"]:
        return

    winner_name = ms["winner"]
    handout     = ms["handout"]
    winner_p    = session._get_player(winner_name)
    if winner_p:
        winner_p.add_drink(
            handout,
            f"Milestone handout forfeited — {winner_name} didn't assign in time: +{handout} sips",
            "player",
        )
        award_sips(
            session, winner_name, handout, "Milestone handout forfeit",
            reason=f"Milestone forfeited ({ms['boundary']} sip milestone) — you drink {handout} sips",
        )
        log_line = (
            f"  ⏱ {winner_name} didn't assign the {ms['boundary']}-sip milestone handout "
            f"in time — drinks {handout} sips\n"
        )
        session.round._log_entries.append(log_line)
        session._log_version += 1
        log.debug(f"  [milestone] {winner_name} forfeited handout — drinks {handout} sips")

    session.round._pending_milestone = None
