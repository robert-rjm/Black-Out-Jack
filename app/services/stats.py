"""
app/services/stats.py
=====================
Derived numbers computed from a live session: sip totals, payout data,
best-play hint, mandatory-split flags, trophy holder and the KPI block.
Pure reads; split out of serializer.py, which only assembles the snapshot.
"""

import time

from engine.blackjack import NPC_Player

from app.models.game_room import GameRoom
from app.services.round_state import hand_done, play_order


# ---------------------------------------------------------------------------
# Sip / drink aggregation helpers
# ---------------------------------------------------------------------------

def _compute_live_drink_totals(session: GameRoom) -> tuple[dict, dict]:
    """Single pass over drink_log → (sip_totals, dealer_role_sips).

    Called by serialize_state() so the live drink_log is only walked once per
    poll instead of twice (once for sip totals, once for dealer-role sips).
    Only meaningful when drinking_mode is on and the log has not yet been
    harvested; callers should short-circuit on !drinking_mode themselves.
    """
    sip_ticker    = dict(session.drinks.sip_ticker)
    dealer_ticker = dict(session.drinks.dealer_role_ticker)
    if not session.round._drink_log_harvested:
        for p in session.all_players:
            net = 0
            for entry in p.drink_log:
                if not entry:
                    continue
                sips = entry[0] or 0
                net += sips
                if sips > 0:
                    role = entry[2] if len(entry) > 2 else "player"
                    if role == "dealer":
                        dealer_ticker[p.name] = dealer_ticker.get(p.name, 0) + sips
            if net > 0:
                sip_ticker[p.name] = sip_ticker.get(p.name, 0) + net
    return sip_ticker, dealer_ticker


def compute_sip_totals(session: GameRoom) -> dict:
    """Return cumulative sip counts per player: past rounds + current round.

    Delegates to _compute_live_drink_totals so the drink_log is only walked
    once even when both sip_totals and dealer_role_sips are needed.
    """
    if not session.drinking_mode:
        return {}
    return _compute_live_drink_totals(session)[0]


def compute_payout_data(session: GameRoom) -> dict:
    """Cash wager / bankroll fields for Normal mode (drinking_mode = False,
    digital only). Empty in Drinking/Referee mode."""
    if session.drinking_mode or session.mode != "digital":
        return {}
    expires = session.round._stake_window_expires_at
    secs_left = max(0.0, expires - time.monotonic()) if expires is not None else 0.0
    return {
        "stake_window_open":         expires is not None,
        "stake_window_seconds_left": int(secs_left) if expires is not None else 0,
        "stake_confirmed":           sorted(session.round._stake_confirmed),
        "bet_amount":         session.bet_amount,
        "starting_bankroll":  session.starting_bankroll,
        "balances":           dict(session._bankrolls),
        "round_payouts":      dict(session._last_round_payouts),
        "bank_run_players":   list(session._bank_run_players),
        "biggest_round_payouts": {k: dict(v) for k, v in session._biggest_round_payouts.items()},
    }


def compute_best_play(session: GameRoom, turn: str | None, phase: str) -> str | None:
    """
    Return the basic-strategy best action ('h'|'s'|'d'|'sp') for the
    current active hand, or None when it's not applicable.
    Uses drinking-mode overrides (mandatory 10-split, etc.) only when the
    session itself is in drinking mode; Normal mode gets pure basic strategy.
    """
    if phase != "playing" or not turn:
        return None
    player = session._get_player(turn)
    if not player:
        return None
    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand or not dealer.dealer_hand.cards:
        return None
    active_hand = next((h for h in player.hands if not hand_done(h)), None)
    if not active_hand or not active_hand.cards:
        return None
    dealer_up = dealer.dealer_hand.cards[0]
    valid = ["h", "s"]
    from app.services.payout_tracker import can_afford_extra
    affordable = can_afford_extra(session, player.name)
    if len(active_hand.cards) == 2 and not active_hand.doubled and affordable:
        valid.append("d")
    if active_hand.can_split() and affordable:
        valid.append("sp")
    # drinking_mode=False in Normal mode → pure basic strategy (no mandatory 10-split).
    # This is intentional: the hint matches the rules the players are actually playing.
    return NPC_Player.best_play(active_hand, dealer_up, valid, drinking_mode=session.drinking_mode)


def compute_mandatory_split10(session: GameRoom, turn: str | None, phase: str) -> bool:
    """
    Drinking-mode "house rule": an unsuited 10-value pair must be split.
    Returns True when the current human turn's active hand is exactly such
    a pair, splitting is still a valid action, and the player hasn't yet
    been prompted/acknowledged this hand. Always False in Normal mode.
    """
    if not session.drinking_mode or phase != "playing" or not turn:
        return False
    player = session._get_player(turn)
    if not player or getattr(player, "is_npc", False):
        return False
    active_hand = next((h for h in player.hands if not hand_done(h)), None)
    if not active_hand or len(active_hand.cards) != 2:
        return False
    if not active_hand.can_split():
        return False
    if active_hand.cards[0].rank.blackjack_value != 10:
        return False
    if active_hand.is_suited():
        return False
    if (player.name, id(active_hand)) in session.round._honor_acked:
        return False
    return True



def compute_mandatory_split_aces(session: GameRoom, turn: str | None, phase: str) -> bool:
    """Drinking-mode house rule: a pair of Aces must be split.

    Returns True when the current human turn's active hand is exactly an
    Ace pair, splitting is still valid, and the player hasn't yet been
    prompted/acknowledged this hand. Always False in Normal mode.
    """
    if not session.drinking_mode or phase != "playing" or not turn:
        return False
    player = session._get_player(turn)
    if not player or getattr(player, "is_npc", False):
        return False
    active_hand = next((h for h in player.hands if not hand_done(h)), None)
    if not active_hand or len(active_hand.cards) != 2:
        return False
    if not active_hand.can_split():
        return False
    if not all(c.rank.blackjack_value == 11 for c in active_hand.cards):
        return False
    if (player.name, id(active_hand)) in session.round._honor_acked:
        return False
    return True



def compute_trophy_holder(session: GameRoom) -> str | None:
    """Return the name of the sole player who uniquely leads in total clean
    rounds, subject to a dynamic threshold that starts at 3 and escalates
    by 2 whenever two or more players are tied at or above it.

    Returns None if no player meets the threshold, or if the leader is tied.
    """
    totals = session.stats.total_clean_rounds
    if not totals:
        return None
    threshold = 3
    while True:
        qualifiers = [name for name, n in totals.items() if n >= threshold]
        if len(qualifiers) < 2:
            break          # 0 or 1 player at this level — stop escalating
        threshold += 2     # tie at current level — raise the bar
    leaders = [name for name, n in totals.items() if n >= threshold]
    return leaders[0] if len(leaders) == 1 else None


# ---------------------------------------------------------------------------
# KPI stats — pre-computed server-side so kpi.js is a pure renderer
# ---------------------------------------------------------------------------

def _rolling_avg(history: list, n: int):
    """Rolling average of last n items, or None if fewer than n items exist."""
    if not history or len(history) < n:
        return None
    return round(sum(history[-n:]) / n, 1)


def compute_kpi_stats(session: GameRoom, sip_ticker: dict | None = None,
                       order: list[str] | None = None) -> dict:
    """Pre-compute all KPI panel metrics server-side.

    All arithmetic lives here; kpi.js becomes a pure renderer that only does
    HTML generation and benchmark z-score coloring (which depends on the static
    BENCHMARKS_BY_CONFIG JS file that has no backend equivalent).

    `sip_ticker` and `order` may be passed in by a caller that already
    computed them (e.g. serialize_state, which needs both for its own
    fields) to avoid walking the drink log / recomputing play_order() a
    second time. Both fall back to computing here for any other caller.
    """
    hand_stats         = session.stats.hand_stats
    if sip_ticker is None:
        sip_ticker = compute_sip_totals(session)
    if order is None:
        order = play_order(session)
    max_round_sips     = session.stats.max_round_sips
    streaks            = session.stats.streaks
    strategy_decisions = session.stats.strategy_decisions
    dealer_bust_rounds = session.stats.dealer_bust_rounds
    n_rounds           = session.round_count
    history            = session.stats.round_sip_history
    session_secs       = max(0, int((session._paused_at or time.monotonic()) - session.stats.session_started_at))
    drinking           = session.drinking_mode

    # ── Session-wide aggregates ──────────────────────────────────────────────
    total_sips   = sum(sip_ticker.values())
    total_hands  = sum(h.get("hands",      0) for h in hand_stats.values())
    total_bj     = sum(h.get("blackjacks", 0) for h in hand_stats.values())
    total_busts  = sum(h.get("busts",      0) for h in hand_stats.values())
    total_wins   = sum(h.get("wins",       0) for h in hand_stats.values())
    total_pushes = sum(h.get("pushes",     0) for h in hand_stats.values())

    def _pct(num, den, decimals=0):
        if den <= 0:
            return None
        v = (num / den) * 100
        return round(v, decimals) if decimals else round(v)

    session_stats = {
        "total_sips":         total_sips,
        "avg_per_round":      round(total_sips / n_rounds, 1) if (drinking and n_rounds > 0) else None,
        "avg3":               _rolling_avg(history, 3)  if drinking else None,
        "avg5":               _rolling_avg(history, 5)  if drinking else None,
        "avg10":              _rolling_avg(history, 10) if drinking else None,
        "sipm":               round(total_sips / (session_secs / 60), 2) if (drinking and session_secs > 0) else None,
        "total_hands":        total_hands,
        "total_bj":           total_bj,
        "total_busts":        total_busts,
        "total_wins":         total_wins,
        "total_pushes":       total_pushes,
        "bust_rate_pct":      _pct(total_busts,  total_hands),
        "win_rate_pct":       _pct(total_wins,   total_hands),
        "push_rate_pct":      _pct(total_pushes, total_hands),
        "dealer_bust_pct":    _pct(dealer_bust_rounds, n_rounds),
        "dealer_bust_rounds": dealer_bust_rounds,
        "bj_rate_pct":        _pct(total_bj, total_hands, decimals=1),
        "session_seconds":    session_secs,
    }

    # ── Per-player rows (in play order) ─────────────────────────────────────
    player_rows = []
    for name in order:
        hs  = hand_stats.get(name, {})
        sk  = streaks.get(name, {})
        sd  = strategy_decisions.get(name, {})
        big = session._biggest_round_payouts.get(name, {})

        hands    = hs.get("hands",        0)
        wins     = hs.get("wins",         0)
        losses   = hs.get("losses",       0)
        pushes_p = hs.get("pushes",       0)
        bj_p     = hs.get("blackjacks",   0)
        busts    = hs.get("busts",        0)
        suited   = hs.get("suited_hands", 0)
        hit_h    = hs.get("hit_hands",    0)
        sub17    = hs.get("stand_sub17",  0)
        dh       = hs.get("double_hands", 0)
        dw       = hs.get("double_wins",  0)
        sh       = hs.get("split_hands",  0)
        sw       = hs.get("split_wins",   0)
        tot_score = hs.get("total_score", 0)
        scored_h  = hs.get("scored_hands",0)

        sips_p   = sip_ticker.get(name, 0)
        rounds_p = session.stats.player_rounds_played.get(name, 0)
        balance  = None if drinking else session._bankrolls.get(name)

        sd_total   = sd.get("total",   0)
        sd_correct = sd.get("correct", 0)

        player_rows.append({
            "name":           name,
            "hands":          hands,
            "wins":           wins,
            "losses":         losses,
            "pushes":         pushes_p,
            "wr":             _pct(wins,   hands),
            "bj":             bj_p,
            "busts":          busts,
            "bust_pct":       _pct(busts,  hands),
            "suited":         suited,
            "suited_pct":     _pct(suited, hands),
            "hit_rate":       _pct(hit_h,  hands),
            "sub17":          sub17,
            "sub17_pct":      _pct(sub17,  hands),
            "avg_hv":         round(tot_score / scored_h, 1) if scored_h > 0 else None,
            "dbl_pct":        _pct(dw, dh),
            "sp_pct":         _pct(sw, sh),
            "avg_sips":       round(sips_p / rounds_p, 1) if (drinking and rounds_p > 0) else None,
            "max_sips":       max_round_sips.get(name, 0),
            "total_sips":     sips_p,
            "longest_win":    sk.get("longest_win",  0),
            "longest_loss":   sk.get("longest_loss", 0),
            "current_streak": sk.get("current",      0),
            "sd_pct":         _pct(sd_correct, sd_total) if sd_total >= 3 else None,
            "sd_total":       sd_total,
            "balance":        balance,
            "net_pl":         None if (balance is None) else balance - session.starting_bankroll,
            "big_win":        big.get("best",  0),
            "big_loss":       big.get("worst", 0),
        })

    # ── Leaderboard ranking ──────────────────────────────────────────────────
    # Descending win rate (None last), then ascending total sips as tie-breaker
    # in drinking mode — matches the sort the frontend previously applied.
    ranked = sorted(
        [p for p in player_rows if p["hands"] > 0],
        key=lambda p: (
            -(p["wr"] if p["wr"] is not None else -1),
            p["total_sips"] if drinking else 0,
        ),
    )

    return {"session": session_stats, "players": player_rows, "ranked": ranked}
