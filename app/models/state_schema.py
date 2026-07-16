"""
app/models/state_schema.py
============================
Pydantic schema for the JSON snapshot app.services.serializer.serialize_state
returns to the frontend.

This is a runtime contract, not documentation: every key serialize_state
produces must appear here with the right type, and every key here must
actually be produced (``extra="forbid"`` on every model) — a mismatch in
either direction raises immediately at the call site instead of silently
reaching the frontend as a missing/misshapen field. That's the whole point
of putting this in front of a plain dict return.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class _StrictModel(BaseModel):
    """Base for every model below: unknown keys raise instead of being
    silently dropped, so a schema/serializer drift is always caught."""
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Card / hand
# ---------------------------------------------------------------------------

class CardOut(_StrictModel):
    rank:   str
    suit:   str
    symbol: str


class HandOut(_StrictModel):
    """A player's betting hand (serialize_hand)."""
    cards:      list[CardOut]
    score:      Optional[int]
    stood:      bool
    bust:       bool
    doubled:    bool
    from_split: bool
    insured:    bool
    result:     Optional[Literal["win", "loss", "push"]]
    blackjack:  bool
    bj_mult:    int
    done:       bool
    can_split:  bool
    can_double: bool


class DealerHandOut(_StrictModel):
    """The dealer's hand -- a distinct (smaller) shape from HandOut, and
    ``score`` is the literal "?" while the hole card is hidden."""
    cards:     list[CardOut]
    score:     int | Literal["?"]
    hidden:    bool
    blackjack: bool
    bust:      bool
    done:      bool


# ---------------------------------------------------------------------------
# Table seat
# ---------------------------------------------------------------------------

class TableSeatOut(_StrictModel):
    name:                  str
    is_dealer:             bool
    is_npc:                bool
    personality:           Optional[str]
    hands:                 list[HandOut]
    done:                  bool
    is_turn:               bool
    strategy_hint_enabled: bool
    player_bet:            float


# ---------------------------------------------------------------------------
# KPI stats (compute_kpi_stats)
# ---------------------------------------------------------------------------

class KpiSessionOut(_StrictModel):
    total_sips:         int
    avg_per_round:      Optional[float]
    avg3:               Optional[float]
    avg5:               Optional[float]
    avg10:              Optional[float]
    sipm:               Optional[float]
    total_hands:        int
    total_bj:           int
    total_busts:        int
    total_wins:         int
    total_pushes:       int
    bust_rate_pct:      Optional[float]
    win_rate_pct:       Optional[float]
    push_rate_pct:      Optional[float]
    dealer_bust_pct:    Optional[float]
    dealer_bust_rounds: int
    bj_rate_pct:        Optional[float]
    session_seconds:    int


class KpiPlayerRowOut(_StrictModel):
    name:           str
    hands:          int
    wins:           int
    losses:         int
    pushes:         int
    wr:             Optional[float]
    bj:             int
    busts:          int
    bust_pct:       Optional[float]
    suited:         int
    suited_pct:     Optional[float]
    hit_rate:       Optional[float]
    sub17:          int
    sub17_pct:      Optional[float]
    avg_hv:         Optional[float]
    dbl_pct:        Optional[float]
    sp_pct:         Optional[float]
    avg_sips:       Optional[float]
    max_sips:       int
    total_sips:     int
    longest_win:    int
    longest_loss:   int
    current_streak: int
    sd_pct:         Optional[float]
    sd_total:       int
    balance:        Optional[float]
    net_pl:         Optional[float]
    big_win:        float
    big_loss:       float


class KpiStatsOut(_StrictModel):
    session: KpiSessionOut
    players: list[KpiPlayerRowOut]
    ranked:  list[KpiPlayerRowOut]


# ---------------------------------------------------------------------------
# Connection / room-membership entries
# ---------------------------------------------------------------------------

class ConnectedClientOut(_StrictModel):
    name:        Optional[str]
    role:        Optional[str]
    local_names: list[str]


class KickedClientOut(_StrictModel):
    client_id: str
    name:      str


class DeniedClientOut(_StrictModel):
    client_id: str


class PendingSeatTransferOut(_StrictModel):
    requester_name: str
    target:         str


class PendingRegistrationOut(_StrictModel):
    client_id: str
    name:      str


class RejoinRequestOut(_StrictModel):
    client_id:    str
    display_name: str


# ---------------------------------------------------------------------------
# Event-log entries
# ---------------------------------------------------------------------------

class AceDrinkEventOut(_StrictModel):
    seq:       int
    recipient: str
    sips:      int
    reason:    str


class TableEventOut(_StrictModel):
    seq:     int
    text:    str
    outcome: str
    target:  str


class ReshuffleEventOut(_StrictModel):
    seq:   int
    decks: int


class BustHandoutLogEntryOut(_StrictModel):
    winner:    str
    recipient: Optional[str]
    forfeited: bool


class DrinkEntryOut(_StrictModel):
    """One line-item in the last-/prev-round Drinks pane detail list."""
    name:   str
    sips:   int
    reason: str


class InsuranceResultOut(_StrictModel):
    player:       str
    insured:      bool
    dealer_bj:    bool
    group_won:    bool
    outcome_text: str


class InsuranceVoteOut(_StrictModel):
    bj_player:      str
    hand_idx:       int
    resolved:       bool
    my_vote:        Optional[bool]
    votes_cast:     int
    votes_needed:   int
    votes_cast_by:  dict[str, bool]
    insure_count:   Optional[int]
    decline_count:  Optional[int]
    seconds_left:   int


# ---------------------------------------------------------------------------
# Milestone
# ---------------------------------------------------------------------------

class LastMilestoneResultOut(_StrictModel):
    winner:      str
    boundary:    int
    allocations: dict[str, int]
    seconds_ago: int


class PendingMilestoneOut(_StrictModel):
    boundary:     int
    winner:       str
    handout:      int
    seconds_left: int
    i_am_winner:  bool


# ---------------------------------------------------------------------------
# Dealer Lottery (docs/planning/DealerLottery-Plan.md)
# ---------------------------------------------------------------------------

class DealerLotteryPendingOut(_StrictModel):
    seconds_left:   int
    answered_count: int
    total_count:    int
    my_entries:     dict[str, Optional[int]]


class DealerLotteryHandOut(_StrictModel):
    cards: list[CardOut]
    score: int
    bust:  bool


class DealerLotteryResultOut(_StrictModel):
    hands:        list[DealerLotteryHandOut]
    busted:       int
    entries:      dict[str, int]
    drink_amounts:  dict[str, int]
    credit_amounts: dict[str, int]
    seconds_ago:  int


class DealerLotteryOut(_StrictModel):
    pending:              Optional[DealerLotteryPendingOut]
    last_result:          Optional[DealerLotteryResultOut]
    result_seq:           int
    pending_handouts:     dict[str, int]
    my_pending_handouts:  dict[str, int]
    handout_seconds_left: int


# ---------------------------------------------------------------------------
# Bust vote
# ---------------------------------------------------------------------------

class BustVoteResultOut(_StrictModel):
    dealer_busted:   bool
    winners:         list[str]
    losers:          list[str]
    side_bet_amount: Optional[float]
    outcome_lines:   list[str]
    winner_label:    str
    loser_label:     str


# ---------------------------------------------------------------------------
# Queued settings (admin's "apply next round" buffer)
# ---------------------------------------------------------------------------

class QueuedAddPlayerOut(_StrictModel):
    name:   str
    is_npc: bool


class QueuedSettingsOut(_StrictModel):
    """Validated separately in serialize_state and dumped with
    exclude_none=True -- the frontend (admin-settings.js's
    _renderQueuedBanner) checks presence with ``"wager" in queued`` etc., so
    the API shape must stay sparse (only actually-queued keys present), not
    every key present-with-null the way a plain AppState field would dump."""
    wager:               Optional[int] = None
    num_hands:           Optional[int] = None
    num_decks:           Optional[int] = None
    easy_mode:           Optional[bool] = None
    add_players:         Optional[list[QueuedAddPlayerOut]] = None
    remove_players:      Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Payout data (Normal mode only)
# ---------------------------------------------------------------------------

class BiggestRoundPayoutOut(_StrictModel):
    best:  float
    worst: float


# ---------------------------------------------------------------------------
# Full state snapshot (serialize_state's return value)
# ---------------------------------------------------------------------------

class AppState(_StrictModel):
    ok:     bool
    round:  int
    dealer: str
    players: list[str]
    num_hands: int
    wager:  int
    mode:   str
    table:  list[TableSeatOut]
    dealer_hand: Optional[DealerHandOut]
    current_turn: Optional[str]
    play_order:   list[str]
    phase: Literal["pre-deal", "playing", "dealer-ready", "round-over"]
    drinking_mode: bool
    best_play: Optional[Literal["h", "s", "d", "sp"]]
    honor_pending:        bool
    honor_pending_action: Optional[str]
    honor_pending_reason: Optional[str]
    suggest_rotate:       bool
    rotate_reason:        str
    rounds_this_dealer:   int
    dealer_rotate_every:  int
    switch_this_round:    Optional[Literal["hard", "soft"]]
    log_entries: list[str]
    log_count:   int
    log_version: int
    peeked_card: Optional[CardOut]
    preselections: dict[str, str]
    suggestions:   dict[str, str]
    anim_default:     bool
    easy_mode:        bool
    god_mode_enabled: bool
    # Already validated + sparsely dumped in serialize_state (see
    # QueuedSettingsOut's docstring) -- typed loosely here since it arrives
    # pre-shaped, not as a fresh dict to expand against the sub-model.
    queued_settings:  dict[str, Any]
    num_decks:        int
    kpi_stats:        KpiStatsOut
    state_seq:        int

    # ---- Payout data (Normal mode only -- absent entirely otherwise) ----
    bet_amount:            Optional[float] = None
    starting_bankroll:     Optional[float] = None
    balances:              Optional[dict[str, float]] = None
    round_payouts:         Optional[dict[str, float]] = None
    bank_run_players:      Optional[list[str]] = None
    biggest_round_payouts: Optional[dict[str, BiggestRoundPayoutOut]] = None

    # ---- Drink summary (always present) ----
    sip_totals:         dict[str, int]
    sip_grand_total:    int
    round_over_seq:     int
    last_round_sips:    dict[str, int]
    clean_streaks:      dict[str, int]
    total_clean_rounds: dict[str, int]
    trophy_holder:      Optional[str]
    last_round_drinks:  list[DrinkEntryOut]
    round_notices:      list[str]
    prev_round_sips:    dict[str, int]
    prev_round_drinks:  list[DrinkEntryOut]
    dealer_role_sips:   dict[str, int]
    ace_drink_events:   list[AceDrinkEventOut]
    ace_drink_seq:      int
    reshuffle_events:   list[ReshuffleEventOut]
    reshuffle_seq:      int
    wild_card_enabled:  bool
    wild_card_seq:      int
    wild_card_text:     Optional[str]
    wild_card_outcome:  Optional[str]
    table_events:       list[TableEventOut]
    table_event_seq:    int

    # ---- Bust-vote data (always present) ----
    bust_vote_enabled:        bool
    bust_votes:               dict[str, Literal["bust", "pass"]]
    my_bust_vote:             Optional[Literal["bust", "pass"]]
    my_bust_votes:            dict[str, Optional[Literal["bust", "pass"]]]
    bust_vote_result:         Optional[BustVoteResultOut]
    bust_handout_seconds_left: int
    my_bust_handout_pending:  list[str]
    max_round_sips:           dict[str, int]
    bust_handout_seq:         int
    bust_handout_results:     list[BustHandoutLogEntryOut]
    bust_vote_window_open:    bool
    bust_vote_seconds_left:   int

    # ---- Insurance data (always present) ----
    insurance_result: list[InsuranceResultOut]
    insurance_votes:  list[InsuranceVoteOut]

    # ---- Milestone data (always present) ----
    last_milestone_result: Optional[LastMilestoneResultOut]
    pending_milestone:     Optional[PendingMilestoneOut]
    last_milestone_worst:  Optional[str]

    # ---- Dealer Lottery data (always present) ----
    dealer_lottery: DealerLotteryOut

    # ---- Connection / room-membership data (always present) ----
    kick_votes:                 dict[str, int]
    kick_votes_mine:            list[str]
    kick_votes_detail:          dict[str, list[str]]
    rejoin_requests:            list[RejoinRequestOut]
    my_rejoin_pending:          bool
    pending_registrations:      list[PendingRegistrationOut]
    my_registration_pending:    bool
    my_registration_rejected:   bool
    my_registration_denied:     bool
    connected_clients:          list[ConnectedClientOut]
    pending_seat_transfers:     list[PendingSeatTransferOut]
    kicked_clients:             list[KickedClientOut]
    denied_clients:             list[DeniedClientOut]

    # ---- Client identity / permissions (always present) ----
    my_role:            Optional[str]
    my_name:            Optional[str]
    my_names:           list[str]
    can_add_local_seat: bool
    is_dealer_client:   bool
