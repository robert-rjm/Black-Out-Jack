"""
app/services/serializer.py
===========================
Converts live session state into the JSON snapshots the frontend consumes.

All functions are pure reads — nothing here mutates session state.
The only external dependency is validators.get_client_info so that
per-client fields (my_role, is_dealer_client, etc.) can be included.
"""

import time

from engine.blackjack import Hand, NPC_Player
from engine.drinking_rules import _bj_multiplier

from app.models.game_room import GameRoom
from app.models.state_schema import AppState, QueuedSettingsOut
from app.services.validators import get_client_info
from app.config import INSURANCE_VOTE_TIMEOUT, TARGETED_DRINKING_REVEAL_PAUSE_SECONDS


def _serialize_last_milestone(result: dict | None) -> dict | None:
    """Serialize the most recent completed milestone for the frontend.

    Returns None if there is no result or it is older than 90 seconds
    (the frontend dismisses the toast after that window anyway).
    """
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "winner":      result["winner"],
        "boundary":    result["boundary"],
        "allocations": result["allocations"],
        "seconds_ago": max(0, round(time.monotonic() - result["set_at"])),
    }


def _serialize_pending_milestone(milestone: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending milestone awaiting the winner's claim / handout.

    Returns None when there is no pending milestone or its claim window has expired.
    ``client_info`` is the caller's _room_clients entry, used to set ``i_am_winner``.
    """
    if not milestone or time.monotonic() >= milestone["expires_at"]:
        return None
    return {
        "boundary":     milestone["boundary"],
        "winner":       milestone["winner"],
        "handout":      milestone["handout"],
        "seconds_left": max(0, round(milestone["expires_at"] - time.monotonic())),
        "i_am_winner":  bool(
            client_info.get("name") and
            milestone["winner"].lower() == client_info["name"].lower()
        ),
    }


def _serialize_pending_dealer_lottery(pending: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending Dealer Lottery entry window.

    Returns None when there is no pending lottery or its entry window has
    expired. Only reveals this client's own local players' submitted
    values (``my_entries``) plus an answered/total count -- never anyone
    else's individual entry, to avoid metagaming the table's choices.
    """
    if not pending or time.monotonic() >= pending["expires_at"]:
        return None
    entries  = pending["entries"]
    my_names = set(client_info.get("local_names") or
                   ([client_info["name"]] if client_info.get("name") else []))
    return {
        "seconds_left":   max(0, round(pending["expires_at"] - time.monotonic())),
        "answered_count": sum(1 for v in entries.values() if v is not None),
        "total_count":    len(entries),
        "my_entries":     {n: v for n, v in entries.items() if n in my_names},
    }


def _serialize_last_dealer_lottery_result(result: dict | None) -> dict | None:
    """Serialize the most recently resolved Dealer Lottery draw for the
    frontend. Returns None if there is no result or it is older than 90
    seconds (matches _serialize_last_milestone's dismissal window)."""
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "hands":        [dict(h) for h in result["hands"]],
        "busted":       result["busted"],
        "entries":      dict(result["entries"]),
        "drink_amounts":  dict(result.get("drink_amounts", {})),
        "credit_amounts": dict(result.get("credit_amounts", {})),
        "seconds_ago":  max(0, round(time.monotonic() - result["set_at"])),
    }


def _serialize_pending_targeted_drinking(pending: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending Targeted Drinking Mode vote window (Rules.md §5.10).

    Returns None when there is no pending mini-round or its vote window has
    expired. ``my_vote`` reveals only this client's own primary-name vote
    (mirrors cast_bust_vote's single-seat convention) -- local multiplayer
    with more than one targeted seat reads each target's vote from
    ``votes_cast`` instead, same as Dealer Lottery's own ``my_entries`` vs.
    the plain entry count.
    """
    if not pending or time.monotonic() >= pending["expires_at"]:
        return None
    votes   = pending["votes"]
    my_name = (client_info.get("name") or "").capitalize()
    return {
        "seconds_left": max(0, round(pending["expires_at"] - time.monotonic())),
        "my_vote":      votes.get(my_name),
        "votes_cast":   {n: v for n, v in votes.items() if v is not None},
    }


def _serialize_last_targeted_drinking_result(result: dict | None) -> dict | None:
    """Serialize the most recently resolved Targeted Drinking mini-round
    for the frontend. Returns None if there is no result or it is older
    than 90 seconds (matches _serialize_last_dealer_lottery_result's
    dismissal window)."""
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "hand":        dict(result["hand"]),
        "votes":       dict(result["votes"]),
        "correct":     dict(result["correct"]),
        "streaks":     dict(result["streaks"]),
        "graduated":   list(result["graduated"]),
        "sips":        dict(result["sips"]),
        "seconds_ago": max(0, round(time.monotonic() - result["set_at"])),
    }


def _targeted_drinking_awaiting_start(session: GameRoom) -> bool:
    """True when the *first* mini-round after a normal round's end could
    open right now but is waiting on someone to tap "Start Targeting Now".
    Mirrors app/services/targeted_drinking.py's own
    ``_targeted_drinking_ready_to_open`` + ``targeted_drinking_awaiting_start``
    gates -- duplicated here rather than imported, since that module
    imports *this* one for ``serialize_card``; importing back would be
    circular."""
    r = session.round
    if not r._targeted_drinking_eligible:
        return False
    if r._pending_targeted_drinking is not None:
        return False
    if r._targeted_drinking_start_requested:
        return False
    if r._pending_milestone is not None:
        return False
    if r._dealer_lottery_eligible or r._pending_dealer_lottery is not None:
        return False
    last_result = session.drinks.last_targeted_drinking_result
    if last_result and time.monotonic() - last_result["set_at"] < TARGETED_DRINKING_REVEAL_PAUSE_SECONDS:
        return False
    return True


def _serialize_targeted_drinking_summary(summary: dict | None) -> dict | None:
    """Serialize the most recent Targeted Drinking Mode subgame-ending
    recap (reason + total sips per target, plus the run's final
    statistics table). Returns None if there is no summary yet or it's
    older than 90 seconds (same dismissal window as the per-mini-round
    result)."""
    if not summary or time.monotonic() - summary["set_at"] >= 90:
        return None
    return {
        "reason": summary["reason"],
        "totals": dict(summary["totals"]),
        "stats": {
            "correct":      dict(summary.get("correct", {})),
            "wrong":        dict(summary.get("wrong", {})),
            "dealer_hands": summary.get("dealer_hands", 0),
            "dealer_busts": summary.get("dealer_busts", 0),
        },
    }



# ---------------------------------------------------------------------------
# Turn / phase helpers
# ---------------------------------------------------------------------------

_UNSET = object()   # sentinel — None is a valid current_turn() value, so it can't mean "not provided"


def play_order(session: GameRoom) -> list[str]:
    """
    Turn order: dealer's left clockwise, dealer-player goes last.
    Returns list of player names.
    """
    all_names = [p.name for p in session.all_players]
    if session.dealer_name not in all_names:
        return all_names
    d_idx = all_names.index(session.dealer_name)
    order = []
    for i in range(1, len(all_names)):
        order.append(all_names[(d_idx + i) % len(all_names)])
    order.append(session.dealer_name)   # dealer plays their player hands last
    return order


def hand_done(hand: Hand) -> bool:
    """True if hand cannot/should not act anymore."""
    # Split hand with only 1 card is waiting for its second card — not playable yet
    if hand.from_split and len(hand.cards) < 2:
        return True
    return hand.stood or hand.bust or hand.is_bust() or hand.is_blackjack()


def player_done(player) -> bool:
    """True if every betting hand for this player is finished."""
    if not player.hands:
        return True
    return all(hand_done(h) for h in player.hands)


def current_turn(session: GameRoom, order: list[str] | None = None) -> str | None:
    """
    Whose turn is it right now?
    Returns the player name, or None if no one is up (pre-deal or dealer phase).
    Only meaningful when the initial deal has happened.

    `order` may be a pre-computed play_order(session) value, for callers
    that need both and would otherwise trigger a redundant recompute.
    """
    has_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_cards:
        return None
    if order is None:
        order = play_order(session)
    for name in order:
        p = session._get_player(name)
        if p and not player_done(p):
            return name
    return None   # all player hands done → dealer phase


def round_phase(session: GameRoom, turn=_UNSET) -> str:
    """
    'pre-deal'     → waiting for initial deal
    'playing'      → at least one player still has an active hand
    'dealer-ready' → all player hands done, results not yet assigned
    'round-over'   → every hand has a result (dealer has resolved the round)

    `turn` may be a pre-computed current_turn(session) value, for callers
    (e.g. serialize_state) that need both and would otherwise trigger two
    full play_order() scans back to back. Leave unset to compute it here.
    """
    has_player_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_player_cards:
        return "pre-deal"

    if turn is _UNSET:
        turn = current_turn(session)
    if turn is not None:
        return "playing"

    # `result` is only ever set by the resolution step (after the dealer
    # plays/reveals), so it's the definitive round-over signal — unlike
    # inferring "dealer is done" from dealer_hand score/stood/bust, which
    # can be true from the initial deal alone (e.g. a 17+ up-card total)
    # before the dealer has actually played, and breaks entirely if
    # dealer_hand is ever None/missing.
    all_resolved = all(
        h.result is not None for p in session.all_players for h in p.hands
    )
    if all_resolved:
        return "round-over"
    return "dealer-ready"


# ---------------------------------------------------------------------------
# Card / hand serialisation
# ---------------------------------------------------------------------------

def serialize_card(card) -> dict:
    """Compact JSON for a single card."""
    return {
        "rank":   card.rank.label,
        "suit":   card.suit.value,    # 'hearts' | 'diamonds' | 'clubs' | 'spades'
        "symbol": card.suit.symbol,
    }


def serialize_hand(hand: Hand, hide_double: bool = False) -> dict:
    cards = [serialize_card(c) for c in hand.cards]
    # Doubled card is dealt face-down until dealer plays
    is_hidden_double = hide_double and hand.doubled
    if is_hidden_double and len(cards) > 0:
        cards[-1] = {"rank": "?", "suit": "hidden", "symbol": "?"}
    return {
        "cards":      cards,
        "score":      None if is_hidden_double else (hand.score() if hand.cards else 0),
        "stood":      hand.stood,
        "bust":       False if is_hidden_double else (hand.bust or bool(hand.cards and hand.is_bust())),
        "doubled":    hand.doubled,
        "from_split": hand.from_split,
        "insured":    hand.insured,
        "result":     None if is_hidden_double else hand.result,
        "blackjack":  bool(hand.cards) and hand.is_blackjack(),
        "bj_mult":    _bj_multiplier(hand),
        "done":       hand_done(hand),
        "can_split":  hand.can_split(),
        "can_double": len(hand.cards) == 2 and not hand.doubled,
    }


# ---------------------------------------------------------------------------
# Bust-vote window helper
# ---------------------------------------------------------------------------

def _bust_vote_window(session: GameRoom) -> dict:
    """Return bust_vote_window_open and bust_vote_seconds_left for the frontend."""
    if not session.bust_vote_enabled or not session.round._bust_vote_expires_at:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    now        = time.monotonic()
    secs_left  = session.round._bust_vote_expires_at - now
    if secs_left <= 0:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    # Early close: all non-NPC players have voted or passed
    human_players = [p for p in session.all_players
                     if not getattr(p, "is_npc", False)]
    all_decided = bool(human_players) and all(
        session.round._bust_votes.get(p.name) is not None for p in human_players
    )
    if all_decided:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    return {
        "bust_vote_window_open":   True,
        "bust_vote_seconds_left":  max(1, int(secs_left)),
    }


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
    return {
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
    if len(active_hand.cards) == 2 and not active_hand.doubled:
        valid.append("d")
    if active_hand.can_split():
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
    session_secs       = max(0, int(time.monotonic() - session.stats.session_started_at))
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


# ---------------------------------------------------------------------------
# Insurance vote serializer helper
# ---------------------------------------------------------------------------

def _insurance_outcome_text(r: dict) -> str:
    """Return the canonical human-readable outcome string for one insurance result entry.

    Centralised here so both the toast (admin.js) and the banner
    (table-modals.js) display identical wording without duplicating logic.
    """
    insured   = r.get("insured")
    dealer_bj = r.get("dealer_bj")
    if insured and dealer_bj:
        return "dealer had BJ — BJ holder drinks own bonus, group safe"
    if insured and not dealer_bj:
        return "no dealer BJ — group drinks double"
    if not insured and not dealer_bj:
        return "no dealer BJ — normal BJ bonus"
    return "dealer had BJ — auto-insurance applies"


def _serialize_insurance_vote(v: dict, session: GameRoom, client_info: dict) -> dict:
    """Serialize one insurance vote entry.

    insure_count / decline_count are exposed as soon as every eligible player
    has cast a vote — not gated on `resolved` (which only flips after the 60s
    timeout). This means the banner can show the correct result immediately
    when the last vote comes in rather than always defaulting to "DECLINE".
    """
    bj_player    = v["player"]
    # NPCs never cast insurance votes, so exclude them from the required
    # count — otherwise votes_cast can never reach votes_needed when NPCs
    # are seated, and the vote sits "unresolved" for the full 60s timeout,
    # stalling the dealer's turn even though every human has already voted.
    votes_needed = sum(1 for p in session.all_players
                       if p.name.lower() != bj_player.lower()
                       and not getattr(p, "is_npc", False))
    votes_cast   = len(v["votes"])
    counts_ready = v["resolved"] or votes_cast >= votes_needed
    # Bots abstain — only humans with drinking stake count toward the
    # majority. Any human who hasn't voted (or voted decline) counts toward
    # decline_count, so non-voters default to decline. Ties (incl. 0-0 when
    # everyone is a bot) default to decline via `insured = insure > decline`.
    insure_count  = sum(1 for x in v["votes"].values() if x)
    decline_count = votes_needed - insure_count
    return {
        "bj_player":      bj_player,
        "hand_idx":       v["hand_idx"],
        "resolved":       v["resolved"],
        "my_vote":        v["votes"].get(client_info.get("name") or "", None),
        "votes_cast":     votes_cast,
        "votes_needed":   votes_needed,
        "votes_cast_by":  dict(v["votes"]),   # {voter_name: bool} — local multiplayer uses this to advance seats
        "insure_count":  insure_count  if counts_ready else None,
        "decline_count": decline_count if counts_ready else None,
        "seconds_left":  max(0, int(INSURANCE_VOTE_TIMEOUT -
                                    (time.monotonic() - v.get("started_at", time.monotonic())))),
    }


# ---------------------------------------------------------------------------
# Full state snapshot
# ---------------------------------------------------------------------------

def serialize_state(session: GameRoom | None, client_id: str = "") -> dict:
    """Full snapshot for the UI."""
    if not session:
        return {"ok": False}

    _ci = get_client_info(session, client_id) if client_id else {}

    dealer      = session._get_dealer()
    order       = play_order(session)
    turn        = current_turn(session, order=order)
    phase       = round_phase(session, turn=turn)
    hide_double = (phase != "round-over")   # reveal doubled card once round is over

    # Build a name→hint lookup from the session-level hint set
    # (stored on session._hint_seats to survive client reconnections)
    _hint_names = getattr(session, "_hint_seats", set())

    table = []
    for p in session.all_players:
        table.append({
            "name":                   p.name,
            "is_dealer":              p.is_dealer,
            "is_npc":                 getattr(p, "is_npc", False),
            "personality":            getattr(p, "personality", "basic") if getattr(p, "is_npc", False) else None,
            "hands":                  [serialize_hand(h, hide_double=hide_double) for h in p.hands],
            "done":                   player_done(p),
            "is_turn":                (p.name == turn),
            "strategy_hint_enabled":  p.name.lower() in _hint_names,
            "player_bet":             getattr(session, "_player_bets", {}).get(p.name, session.bet_amount),
        })

    # Dealer hand — hide hole card while players are still acting (digital only)
    mode         = session.mode
    d_hand_state = None
    if dealer and dealer.dealer_hand:
        d_cards = dealer.dealer_hand.cards
        if mode == "digital" and phase in ("playing", "pre-deal") and len(d_cards) >= 2:
            d_hand_state = {
                "cards":     [serialize_card(d_cards[0]),
                              {"rank": "?", "suit": "hidden", "symbol": "?"}]
                              + [serialize_card(c) for c in d_cards[2:]],
                "score":     "?",
                "hidden":    True,
                "blackjack": False,
                "bust":      False,
                "done":      False,
            }
        else:
            d_hand_state = {
                "cards":     [serialize_card(c) for c in d_cards],
                "score":     dealer.dealer_hand.score() if d_cards else 0,
                "hidden":    False,
                "blackjack": bool(d_cards) and dealer.dealer_hand.is_blackjack(),
                "bust":      bool(d_cards) and dealer.dealer_hand.is_bust(),
                "done":      bool(d_cards) and (
                    dealer.dealer_hand.stood
                    or dealer.dealer_hand.is_bust()
                    or dealer.dealer_hand.score() >= 17
                ),
            }

    # Dealer-rotation suggestion (drinking mode only — Normal mode has a fixed
    # house dealer that never rotates, so all rotation state is suppressed)
    if session.drinking_mode:
        switch         = session.round.switch_this_round
        rounds_td      = session.rounds_this_dealer
        num_p          = len(session.all_players)
        suggest_rotate = bool(switch in ("hard", "soft") or rounds_td >= num_p)
        if switch == "hard":
            rotate_reason = "Hard switch — dealer lost all hands"
        elif switch == "soft":
            rotate_reason = "Soft switch — dealer won all hands"
        elif suggest_rotate:
            rotate_reason = f"Round {rounds_td} of {num_p} — every player has been dealer"
        else:
            rotate_reason = f"Round {rounds_td} of {num_p} as dealer"
    else:
        switch         = None
        rounds_td      = 0
        suggest_rotate = False
        rotate_reason  = ""

    sip_totals, _dealer_role_sips = (
        _compute_live_drink_totals(session) if session.drinking_mode else ({}, {})
    )

    _payout_data = compute_payout_data(session)

    # ---- This-round / last-round drink summaries ----
    _drink_summary_data = {
        "sip_totals":             sip_totals,
        "sip_grand_total":        sum(sip_totals.values()),
        "round_over_seq":         session.drinks.round_over_seq,
        "last_round_sips":        {k: max(0, v) for k, v in session.drinks.last_round_sips.items()},
        "clean_streaks":          dict(session.stats.clean_streak),
        "total_clean_rounds":     dict(session.stats.total_clean_rounds),
        "trophy_holder":          compute_trophy_holder(session),
        "last_round_drinks":      session.drinks.last_round_drinks,
        "round_notices":          session.drinks.round_notices,
        "prev_round_sips":        {k: max(0, v) for k, v in session.drinks.prev_round_sips.items()},
        "prev_round_drinks":      session.drinks.prev_round_drinks,
        "dealer_role_sips":       _dealer_role_sips,
        "ace_drink_events":       session.round._ace_drink_events,
        "ace_drink_seq":          session.round._ace_drink_seq,
        "reshuffle_events":       session.round._reshuffle_events,
        "reshuffle_seq":          session.round._reshuffle_seq,
        # Wild Card Easter egg
        "wild_card_enabled":      session.wild_card_enabled,
        "wild_card_seq":          session.round._wild_card_seq,
        "wild_card_text":         (session.round._wild_card_result or {}).get("text"),
        "wild_card_outcome":      (session.round._wild_card_result or {}).get("outcome"),
        # Devil's Hand (666) / Lucky Sevens (777)
        "table_events":           session.round._table_events,
        "table_event_seq":        session.round._table_event_seq,
    }

    # ---- Bust-vote data ----
    _bust_vote_data = {
        "bust_vote_enabled":      session.bust_vote_enabled,
        "bust_votes":             dict(session.round._bust_votes),
        "my_bust_vote":           session.round._bust_votes.get((_ci.get("name") or "").capitalize()),
        "my_bust_votes":          {
            n: session.round._bust_votes.get(n)
            for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
        },
        "bust_vote_result":       session.round._bust_vote_result,
        "bust_handout_seconds_left": (
            max(0, round(session.round._bust_handout_expires_at - time.monotonic()))
            if session.round._bust_handout_expires_at else 0
        ),
        "my_bust_handout_pending": [
            n for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
            if (session.round._bust_vote_result or {}).get("dealer_busted")
            and n in (session.round._bust_vote_result or {}).get("winners", [])
            and n not in session.round._bust_handouts_given
        ],
        # max_round_sips kept here (not inside kpi_stats) because table-render.js
        # reads it directly for the "worst rond" badge on the score panel.
        "max_round_sips":         dict(session.stats.max_round_sips),
        "bust_handout_seq":       session._bust_handout_seq,
        "bust_handout_results":   list(session.round._bust_handout_log),
        **_bust_vote_window(session),
    }

    # ---- Insurance data ----
    _insurance_data = {
        "insurance_result":       [
            {**r, "outcome_text": _insurance_outcome_text(r)}
            for r in (session._insurance_result or [])
        ],
        "insurance_votes":        [
            _serialize_insurance_vote(v, session, _ci)
            for v in session.round._insurance_votes
        ],
    }

    # ---- Milestone data ----
    _milestone_data = {
        "last_milestone_result": _serialize_last_milestone(session.drinks.last_milestone_result),
        "pending_milestone":     _serialize_pending_milestone(session.round._pending_milestone, _ci),
        "last_milestone_worst":  session.drinks.last_milestone_worst,
    }

    # ---- Dealer Lottery data ----
    # Exclude givers who already gave (mirrors my_bust_handout_pending's
    # "n not in _bust_handouts_given" filter) -- last_dealer_lottery_result's
    # pending_handouts is a static snapshot from resolve_dealer_lottery() and
    # is never mutated by give_dealer_lottery_sip(), so without this filter
    # the give-overlay panel keeps showing an already-given giver's button
    # for the rest of the 90-second result window, blocking the table.
    _dl_pending_handouts = {
        n: a for n, a in (session.drinks.last_dealer_lottery_result or {}).get(
            "pending_handouts", {}).items()
        if n not in session.round._dealer_lottery_handouts_given
    }
    _dl_my_names = set(_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
    _dealer_lottery_data = {
        "dealer_lottery": {
            "pending":              _serialize_pending_dealer_lottery(
                                        session.round._pending_dealer_lottery, _ci),
            "last_result":          _serialize_last_dealer_lottery_result(
                                        session.drinks.last_dealer_lottery_result),
            "result_seq":           session.drinks._dealer_lottery_result_seq,
            "pending_handouts":     dict(_dl_pending_handouts),
            "my_pending_handouts":  {n: a for n, a in _dl_pending_handouts.items()
                                     if n in _dl_my_names},
            "handout_seconds_left": (
                max(0, round(session.round._dealer_lottery_handout_expires_at - time.monotonic()))
                if session.round._dealer_lottery_handout_expires_at else 0
            ),
        },
    }

    # ---- Targeted Drinking Mode data (Rules.md §5.10) ----
    _targeted_drinking_data = {
        "targeted_drinking": {
            "active":               session._targeted_drinking_active,
            "targets":              list(session._targeted_drinking_targets),
            "streaks":              dict(session._targeted_drinking_streaks),
            "cooldown_until_round": session._targeted_drinking_cooldown_until_round,
            "pending":              _serialize_pending_targeted_drinking(
                                        session.round._pending_targeted_drinking, _ci),
            "last_result":          _serialize_last_targeted_drinking_result(
                                        session.drinks.last_targeted_drinking_result),
            "result_seq":           session.drinks._targeted_drinking_result_seq,
            "last_summary":         _serialize_targeted_drinking_summary(
                                        session.drinks.last_targeted_drinking_summary),
            "summary_seq":          session.drinks._targeted_drinking_summary_seq,
            "awaiting_start":       _targeted_drinking_awaiting_start(session),
            # Raw eligibility flag -- true whenever a mini-round could be
            # queued up right now (whether it's actually open yet, waiting
            # on Start Targeting Now, or blocked by the reveal-pause/
            # milestone/Dealer Lottery gates). The frontend uses this to
            # tell "something's genuinely about to happen" apart from
            # "nothing is queued at all" (e.g. the subgame was started
            # while already between rounds, so nothing will arm it until
            # a new round ends) -- see targeted_drinking.py's own
            # start_targeted_drinking docstring for the failure mode this
            # guards against.
            "eligible":             session.round._targeted_drinking_eligible,
            # Live run-wide statistics table (Rules.md §5.10) -- unlike
            # last_result/last_summary this isn't seq-gated one-shot data,
            # it's just the current running tally, always present so
            # targeted players can see it update while deciding their
            # next call.
            "stats": {
                "correct":      dict(session._targeted_drinking_correct_counts),
                "wrong":        dict(session._targeted_drinking_wrong_counts),
                "dealer_hands": session._targeted_drinking_dealer_hands,
                "dealer_busts": session._targeted_drinking_dealer_busts,
            },
        },
    }

    # ---- Connection / room-membership data (admin-only fields gated below) ----
    _connection_data = {
        "kick_votes":             {k: len(v) for k, v in session.round._kick_votes.items()},
        "kick_votes_mine":        [k for k, v in session.round._kick_votes.items()
                                   if (_ci.get("name") or "").lower() in v],
        "kick_votes_detail":      {k: sorted(v) for k, v in session.round._kick_votes.items()},
        "rejoin_requests":        [r for r in session._rejoin_requests
                                   if _ci.get("role") == "admin"],
        "my_rejoin_pending":      any(r["client_id"] == client_id
                                      for r in session._rejoin_requests),
        "pending_registrations":  [{"client_id": r["client_id"], "name": r["name"]}
                                   for r in session._pending_registrations
                                   if _ci.get("role") == "admin"],
        "my_registration_pending": any(r["client_id"] == client_id
                                       for r in session._pending_registrations),
        "my_registration_rejected": _ci.get("role") == "denied",
        "my_registration_denied":   (
            _ci.get("role") == "denied" and
            _ci.get("reg_denials", 0) >= 2
        ),
        "connected_clients":      [
            {"name": info.get("name"), "role": info.get("role"),
             "local_names": info.get("local_names") or []}
            for info in session._room_clients.values()
            if not info.get("kicked")
        ],
        "pending_seat_transfers": [
            {"requester_name": t["requester_name"], "target": t["target"]}
            for t in session._pending_seat_transfers
            if t["controller_cid"] == client_id
        ],
        "kicked_clients":         [
            {"client_id": cid, "name": info.get("name") or ""}
            for cid, info in session._room_clients.items()
            if info.get("kicked") and info.get("name")
        ] if _ci.get("role") == "admin" else [],
        "denied_clients":         [
            {"client_id": cid}
            for cid, info in session._room_clients.items()
            if info.get("role") == "denied" and info.get("reg_denials", 0) >= 2
        ] if _ci.get("role") == "admin" else [],
    }

    # ---- This client's identity / permissions ----
    _client_identity_data = {
        "my_role":                _ci.get("role"),
        "my_name":                _ci.get("name"),
        "my_names":               _ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []),
        "can_add_local_seat":     (
            _ci.get("role") in ("admin", "player") and
            any(
                # Not already one of this client's own seats
                p.name.lower() not in {(n or "").lower()
                               for n in (_ci.get("local_names") or []) + (
                                   [_ci.get("name")] if _ci.get("name") else [])}
                # Not claimed as another client's primary (remote) registration
                and p.name.lower() not in {(info.get("name") or "").lower()
                               for cid, info in session._room_clients.items()
                               if cid != client_id and not info.get("kicked")
                               and info.get("name")}
                # Not an NPC
                and not getattr(p, "is_npc", False)
                for p in session.all_players
            )
        ),
        "is_dealer_client":       (
            (_ci.get("role") == "admin" and session._god_mode) or
            session.dealer_name.lower() in {
                (n or "").lower()
                for n in ([_ci.get("name")] + list(_ci.get("local_names") or []))
            }
        ),
    }

    state = {
        "ok":              True,
        "round":           session.round_count,
        "dealer":          session.dealer_name,
        "players":         [p.name for p in session.all_players],
        "num_hands":       session.num_hands,
        "wager":           session.wager,
        "mode":            session.mode,
        "table":           table,
        "dealer_hand":     d_hand_state,
        "current_turn":    turn,
        "play_order":      order,
        "phase":           phase,
        "drinking_mode":          session.drinking_mode,
        "best_play":              compute_best_play(session, turn, phase),
        "honor_pending":          bool(session.drinking_mode and session.round._honor_pending),
        "honor_pending_action":   (session.round._honor_pending or {}).get("action") if session.drinking_mode else None,
        "honor_pending_reason":   (session.round._honor_pending or {}).get("reason") if session.drinking_mode else None,
        "suggest_rotate":         suggest_rotate,
        "rotate_reason":          rotate_reason,
        "rounds_this_dealer":     rounds_td,
        "dealer_rotate_every":    session._dealer_rotate_every,
        "switch_this_round":      switch,
        "log_entries":            session.round._log_entries,
        "log_count":              len(session.round._log_entries),
        "log_version":            session._log_version,
        "peeked_card":            session.round._last_peeked,
        "preselections":          session.round._preselections,
        "suggestions":            session.round._suggestions,
        "anim_default":           session._anim_default,
        "easy_mode":              session.easy_mode,
        "god_mode_enabled":       session._god_mode,
        # Validated against the real shape, then dumped back to a sparse
        # dict (only actually-queued keys) -- the frontend's
        # _renderQueuedBanner checks presence with `"wager" in queued`, so
        # every-key-with-null (a plain AppState field would dump that way)
        # would break it. See QueuedSettingsOut's docstring.
        "queued_settings": QueuedSettingsOut(**session._queued_settings).model_dump(exclude_none=True),
        "num_decks":              session.shoe.num_decks if session.shoe else 1,
        "kpi_stats":              compute_kpi_stats(session, sip_ticker=sip_totals, order=order),
        **_payout_data,
        **_drink_summary_data,
        **_bust_vote_data,
        **_insurance_data,
        **_milestone_data,
        **_dealer_lottery_data,
        **_targeted_drinking_data,
        **_connection_data,
        **_client_identity_data,
        "state_seq":            int(time.monotonic() * 1_000_000),
    }

    # Validate against the AppState schema -- raises immediately (rather than
    # reaching the frontend as a missing/misshapen field) if a bug ever makes
    # this dict drift from the documented contract in state_schema.py.
    return AppState(**state).model_dump()
