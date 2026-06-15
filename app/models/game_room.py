"""
app/models/game_room.py — typed container for all per-room state.

All RefereeSession attributes used by app/ code are exposed as explicit
properties or method wrappers below — no __getattr__ magic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from engine.referee import RefereeSession


@dataclass
class GameRoom:
    # Core session
    session: RefereeSession

    # Game config
    mode: str = "referee"
    drinking_mode: bool = True

    # Dealer rotation
    rounds_this_dealer: int = 1
    switch_this_round: str | None = None
    _dealer_rotate_every: int = 1

    # Shared log
    _log_entries: list = field(default_factory=list)
    _log_version: int = 0
    _deferred_hole_card_msgs: list = field(default_factory=list)

    # Decision log (Phase C — per-decision board-state capture for
    # per-player bot training; see docs/planning/DecisionLog-Plan.md)
    _decision_log: list = field(default_factory=list)

    # Drink accounting
    _drink_csv_rows: list = field(default_factory=list)
    _sip_ticker: dict = field(default_factory=dict)
    _drink_log_harvested: bool = False
    _last_round_sips: dict = field(default_factory=dict)
    _last_round_drinks: list = field(default_factory=list)
    _round_notices: list = field(default_factory=list)
    _prev_round_sips: dict = field(default_factory=dict)
    _prev_round_drinks: list = field(default_factory=list)
    _dealer_role_ticker: dict = field(default_factory=dict)
    _round_over_seq: int = 0   # increments each harvest so clients never miss the toast

    # Client registry
    _room_clients: dict = field(default_factory=dict)
    _pending_registrations: list = field(default_factory=list)
    _kick_votes: dict = field(default_factory=dict)
    _rejoin_requests: list = field(default_factory=list)
    _anim_default: bool = True

    # Action queues
    _preselections: dict = field(default_factory=dict)
    _suggestions: dict = field(default_factory=dict)
    _insurance_votes: list = field(default_factory=list)
    _queued_settings: dict = field(default_factory=dict)

    # Stats and milestones
    _hand_stats: dict = field(default_factory=dict)
    _dealer_hand_stats: dict = field(default_factory=dict)
    _strategy_decisions: dict = field(default_factory=dict)  # player -> {correct: N, total: N}
    _max_round_sips: dict = field(default_factory=dict)   # player -> highest single-round sip total
    _dealer_bust_rounds: int = 0                          # rounds where dealer hand busted
    _streaks: dict = field(default_factory=dict)          # player -> {current, longest_win, longest_loss}
    _round_sip_history: list = field(default_factory=list)  # total sips (all players) per completed round
    _session_started_at: float = field(default_factory=lambda: __import__("time").monotonic())
    _milestones_claimed: dict = field(default_factory=dict)
    _pending_milestone: dict | None = None
    _last_milestone_result: dict | None = None

    # "Worst player" (lowest avg sips/round) streak tracking across milestones.
    # If the same player is worst for 2 consecutive milestones, they take a
    # one-time penalty equal to the milestone winner's avg sips/round.
    _last_milestone_worst: str | None = None

    # Easy mode (halve drinks every round)
    easy_mode: bool = False

    # Bust vote side bet
    bust_vote_enabled: bool = False

    # Basic-strategy "best play" highlight (blue border) — opt-in, off by default
    strategy_hint_enabled: bool = False
    _god_mode: bool = True
    _bust_votes: dict = field(default_factory=dict)        # player_name -> "bust" | "pass"
    _bust_vote_expires_at: float | None = None             # monotonic timestamp; None = window closed
    _bust_vote_result: dict | None = None                  # set after resolve, cleared on newround
    _bust_handouts_given: set = field(default_factory=set)  # winner names who have given their handout sip
    _bust_handout_expires_at: float | None = None          # monotonic; winners have until this to give their sip
    _bust_handout_log: list = field(default_factory=list)   # [{"winner","recipient","forfeited"}] this round
    _bust_handout_seq: int = 0                              # bumped once all handouts for the round resolve

    # Mid-round state (digital only - reset each newround in game_commands.py)
    _ace_drink_events: list = field(default_factory=list)
    _ace_drink_seq: int = 0

    # Mid-round shoe reshuffle events (shoe ran low and auto-reshuffled
    # while dealing, not the routine between-round reshuffle)
    _reshuffle_events: list = field(default_factory=list)
    _reshuffle_seq: int = 0

    # Tracks (player_name, id(hand)) pairs that have already been resolved
    # for the "mandatory split 10s" house rule this round, so it doesn't
    # re-fire after the player makes a choice (drinking mode only).
    _honor_acked: set = field(default_factory=set)

    # Set when a STAND attempt is blocked by the "mandatory split 10s" house
    # rule and is awaiting the player's choice via /honor_resolve.
    # Shape: {"player": <name>, "hand_id": id(hand)} or None.
    _honor_pending: dict | None = None

    # Misc UI state
    _last_peeked: dict | None = None

    # Cash wager / bankroll system (Normal mode only — drinking_mode = False)
    bet_amount: float = 10
    starting_bankroll: float = 100
    _bankrolls: dict = field(default_factory=dict)        # player_name -> balance
    _last_round_payouts: dict = field(default_factory=dict)  # player_name -> net $ change last round
    _bank_run_players: list = field(default_factory=list)    # players currently at $0 (bank run pending)
    _biggest_round_payouts: dict = field(default_factory=dict)  # player_name -> {"best": float, "worst": float}

    # ------------------------------------------------------------------
    # Explicit properties delegating to RefereeSession
    # ------------------------------------------------------------------

    @property
    def all_players(self):
        return self.session.all_players

    @all_players.setter
    def all_players(self, value):
        self.session.all_players = value

    @property
    def dealer_name(self) -> str:
        return self.session.dealer_name

    @dealer_name.setter
    def dealer_name(self, value: str):
        self.session.dealer_name = value

    @property
    def wager(self) -> int:
        return self.session.wager

    @wager.setter
    def wager(self, value: int):
        self.session.wager = value

    @property
    def num_hands(self) -> int:
        return self.session.num_hands

    @num_hands.setter
    def num_hands(self, value: int):
        self.session.num_hands = value

    @property
    def round_count(self) -> int:
        return self.session.round_count

    @property
    def tracker(self):
        return self.session.tracker

    @tracker.setter
    def tracker(self, value):
        self.session.tracker = value

    @property
    def shoe(self):
        return getattr(self.session, "shoe", None)

    @shoe.setter
    def shoe(self, value):
        self.session.shoe = value

    @property
    def _ace_clubs_flag(self) -> dict:
        return self.session._ace_clubs_flag

    @_ace_clubs_flag.setter
    def _ace_clubs_flag(self, value: dict):
        self.session._ace_clubs_flag = value

    @property
    def _ace_credits(self) -> list:
        return self.session._ace_credits

    @_ace_credits.setter
    def _ace_credits(self, value: list):
        self.session._ace_credits = value

    @property
    def _four_aces_fd(self) -> bool:
        return self.session._four_aces_fd

    @_four_aces_fd.setter
    def _four_aces_fd(self, value: bool):
        self.session._four_aces_fd = value

    @property
    def _pending_resolved(self) -> list:
        return self.session._pending_resolved

    @_pending_resolved.setter
    def _pending_resolved(self, value: list):
        self.session._pending_resolved = value

    @property
    def _all_names(self) -> list:
        return self.session._all_names

    @property
    def _hard_switch_drinking_applied(self) -> bool:
        return getattr(self.session, "_hard_switch_drinking_applied", False)

    @_hard_switch_drinking_applied.setter
    def _hard_switch_drinking_applied(self, value: bool):
        self.session._hard_switch_drinking_applied = value

    @property
    def _insurance_result(self):
        return getattr(self.session, "_insurance_result", None)

    @_insurance_result.setter
    def _insurance_result(self, value):
        self.session._insurance_result = value

    # ------------------------------------------------------------------
    # Method wrappers for RefereeSession methods
    # ------------------------------------------------------------------

    def _get_dealer(self):
        return self.session._get_dealer()

    def _get_player(self, name: str):
        return self.session._get_player(name)

    def start_round(self):
        result = self.session.start_round(digital=(self.mode == "digital"))
        self.session.tracker.verbose = False
        return result

    def cmd_deal(self, parts):
        return self.session.cmd_deal(parts)

    def cmd_action(self, parts):
        return self.session.cmd_action(parts)

    def cmd_result(self, parts):
        return self.session.cmd_result(parts)

    def cmd_dealer(self, parts):
        return self.session.cmd_dealer(parts)

    def cmd_fouraces(self, parts):
        return self.session.cmd_fouraces(parts)

    def cmd_endround(self):
        extra = getattr(self, '_eor_msgs_buffer', [])
        self._eor_msgs_buffer = []
        return self.session.cmd_endround(
            skip_sweep=(self.mode == "digital"),
            extra_eor_msgs=extra,
        )

    def cmd_status(self):
        return self.session.cmd_status()
