"""
app/models/game_room.py — typed container for all per-room state.

All RefereeSession attributes used by app/ code are exposed as explicit
properties or method wrappers below — no __getattr__ magic.

State is divided into five layers:

  RoundState   — per-round transient fields. Replaced wholesale by
                 reset_round_state() so it's impossible to forget
                 to clear a field on newround.

  DrinkLedger  — session-lifetime drink accounting: all four sip
                 accumulators, milestone tracking, and wild-card stats.
                 Accessed via ``session.drinks.*``.

  SessionStats — session-lifetime statistics: hand outcomes, streaks,
                 sip history, strategy tracking, dealer bust counter.
                 Accessed via ``session.stats.*``.

  GameConfig   — game configuration: mode, feature flags, and bankroll
                 settings.  Accessed via ``session.config.*``.

  GameRoom     — session-lifetime fields that survive across rounds,
                 plus ``round``, ``drinks``, ``stats``, and ``config``
                 slots, and delegation properties that proxy into
                 RefereeSession.
"""
from __future__ import annotations
import threading
from dataclasses import dataclass, field
from engine.referee import RefereeSession


@dataclass
class RoundState:
    """All per-round transient state for a GameRoom.

    Replaced wholesale by ``reset_round_state()`` — adding a new per-round
    field here automatically gets it cleared on every newround without
    touching reset logic.
    """
    # Game flow
    switch_this_round: str | None = None
    _drink_log_harvested: bool = False

    # Snapshot of DrinkLedger.clean_streak as it stood *before* this round's
    # own harvest update (see drink_tracker._snapshot_round) -- lets a later
    # post-harvest event (Dealer Lottery, Milestone, bust-vote handout) that
    # retroactively turns a dirty round clean reconstruct what the streak
    # should become, since harvest already overwrote it to 0 believing the
    # round was dirty at the time.
    _pre_round_clean_streak: dict = field(default_factory=dict)

    # Log
    _log_entries: list = field(default_factory=list)
    _last_peeked: dict | None = None
    _deferred_hole_card_msgs: list = field(default_factory=list)  # digital only

    # Action queues
    _preselections: dict = field(default_factory=dict)
    _suggestions: dict = field(default_factory=dict)
    _insurance_votes: list = field(default_factory=list)
    _kick_votes: dict = field(default_factory=dict)

    # Bust vote side bet
    _bust_votes: dict = field(default_factory=dict)
    _bust_vote_expires_at: float | None = None
    _bust_vote_result: dict | None = None
    _bust_handout_expires_at: float | None = None
    _bust_handouts_given: set = field(default_factory=set)
    _bust_handout_log: list = field(default_factory=list)

    # Targeted Drinking Mode (Rules.md §5.10) — a standalone mini-game
    # played between normal rounds (mirrors the Dealer Lottery fields right
    # below): _targeted_drinking_eligible is set once (right after
    # milestone check) whenever the subgame is active;
    # _pending_targeted_drinking (vote window + votes) is only opened once
    # any pending milestone AND Dealer Lottery draw have cleared, so at
    # most one of the three post-round modals is ever open at once. The
    # subgame's persistent state (active flag, target list, graduation
    # streaks, cooldown) lives on GameRoom below, since it must survive
    # across rounds.
    _targeted_drinking_eligible: bool = False
    _pending_targeted_drinking: dict | None = None
    # True once someone has tapped "Start Targeting Now" for the mini-round
    # that _targeted_drinking_eligible above is waiting on -- lets the table
    # finish drinking for the round that just ended before the mini-game
    # takes over. Only gates the *first* mini-round after a normal round
    # ends; back-to-back continuations re-set this for themselves (see
    # resolve_targeted_drinking_round), so the chain never needs a repeat tap.
    _targeted_drinking_start_requested: bool = False
    # Perfect-graduation handout (mirrors the Dealer Lottery handout fields
    # just below) -- pending_handouts itself is a snapshot on
    # session.drinks.last_targeted_drinking_result, these three just track
    # the claim window and who's already given.
    _targeted_drinking_handout_expires_at: float | None = None
    _targeted_drinking_handouts_given: set = field(default_factory=set)
    _targeted_drinking_handout_log: list = field(default_factory=list)

    # Ace drink events (digital only).
    # _ace_drink_seq resets to 0 each round (RoundState is replaced wholesale).
    # The frontend resets its local pointer when it detects a new round via
    # round_count, so seq=1 in round N+1 is always treated as a new event.
    _ace_drink_events: list = field(default_factory=list)
    _ace_drink_seq: int = 0

    # Shoe reshuffle events (mid-round, digital only)
    _reshuffle_events: list = field(default_factory=list)
    _reshuffle_seq: int = 0

    # Mandatory split-10s house rule tracking
    _honor_acked: set = field(default_factory=set)
    _honor_pending: dict | None = None

    # Milestone
    _pending_milestone: dict | None = None

    # Dealer Lottery (post-round bonus event on a paired 18/20 dealer hand)
    # _dealer_lottery_eligible is set once (right after milestone check) when
    # this round's dealer hand qualifies; _pending_dealer_lottery is only
    # opened (with a real countdown) once any pending milestone has cleared,
    # so the entry window's clock never ticks down while the milestone
    # modal is still blocking the player's attention.
    _dealer_lottery_eligible: bool = False
    _pending_dealer_lottery: dict | None = None
    _dealer_lottery_handout_expires_at: float | None = None
    _dealer_lottery_handouts_given: set = field(default_factory=set)
    _dealer_lottery_handout_log: list = field(default_factory=list)

    # Wild Card Easter egg (per-round transient)
    _wild_card_seq: int = 0
    _wild_card_result: dict | None = None

    # Devil's Hand (666) / Lucky Sevens (777) — digital mode (per-round transient)
    _six_count: int = 0
    _seven_count: int = 0
    _six_curse_fired: bool = False
    _seven_lucky_fired: bool = False
    _table_events: list = field(default_factory=list)
    _table_event_seq: int = 0

    # End-of-round message buffer (populated by dealer_turn, drained by cmd_endround)
    _eor_msgs_buffer: list = field(default_factory=list)


@dataclass
class SessionStats:
    """Session-lifetime statistics.

    Hand outcomes, streaks, sip history, strategy tracking, and dealer
    bust counter.  Accessed via ``session.stats.*``.
    """
    hand_stats: dict          = field(default_factory=dict)   # player -> outcome counters
    dealer_hand_stats: dict   = field(default_factory=dict)   # dealer_name -> outcome counters
    strategy_decisions: dict  = field(default_factory=dict)   # player -> {correct: N, total: N}
    max_round_sips: dict      = field(default_factory=dict)   # player -> highest single-round total
    dealer_bust_rounds: int   = 0                             # rounds where dealer busted
    streaks: dict             = field(default_factory=dict)   # player -> {current, longest_win, longest_loss}
    round_sip_history: list   = field(default_factory=list)   # total sips (all players) per round
    player_rounds_played: dict = field(default_factory=dict)  # player -> rounds participated
    session_started_at: float = field(default_factory=lambda: __import__("time").monotonic())
    clean_streak: dict       = field(default_factory=dict)   # player -> current consecutive clean rounds
    total_clean_rounds: dict = field(default_factory=dict)   # player -> total clean rounds this session


@dataclass
class GameConfig:
    """Game configuration — mode, feature flags, and bankroll settings.

    Accessed via ``session.config.*``.  Passed as a single object at
    ``GameRoom`` construction time so all config is in one place.
    """
    mode: str              = "referee"  # "referee" | "digital"
    drinking_mode: bool    = True
    easy_mode: bool        = False
    bust_vote_enabled: bool     = False
    strategy_hint_enabled: bool = False
    god_mode: bool         = True
    dealer_rotate_every: int    = 1
    bet_amount: float      = 10
    starting_bankroll: float    = 100
    wild_card_enabled: bool     = True


@dataclass
class DrinkLedger:
    """Session-lifetime drink accounting.

    All four sip accumulators, milestone tracking, and wild-card stats.
    Accessed via ``session.drinks.*``.
    """
    csv_rows: list             = field(default_factory=list)
    sip_ticker: dict           = field(default_factory=dict)
    # Mirrors sip_ticker but only for sips awarded with count_toward_round=False
    # (currently just Targeted Drinking penalties) -- subtracted back out of
    # sip_ticker when computing "average sips/round" for the milestone
    # worst-player streak, so a between-round mini-game penalty can't make
    # someone look artificially bad at blackjack itself. Never subtracted
    # from sip_ticker directly -- session totals, the leaderboard, and
    # milestone boundary crossing all still count these sips normally.
    sip_ticker_excl_round_avg: dict = field(default_factory=dict)
    last_round_sips: dict      = field(default_factory=dict)
    last_round_drinks: list    = field(default_factory=list)
    round_notices: list        = field(default_factory=list)
    prev_round_sips: dict      = field(default_factory=dict)
    prev_round_drinks: list    = field(default_factory=list)
    dealer_role_ticker: dict   = field(default_factory=dict)
    round_over_seq: int        = 0
    milestones_claimed: dict   = field(default_factory=dict)
    last_milestone_result: dict | None = None
    last_milestone_worst: str | None   = None
    wild_card_presses: dict    = field(default_factory=dict)
    last_dealer_lottery_result: dict | None = None
    # Bumped each time resolve_dealer_lottery() sets a new result, so the
    # frontend can detect a fresh draw (vs. re-polling the same one) --
    # lives here (session-lifetime), not on RoundState, because RoundState
    # is replaced wholesale every round: a per-round seq would reset to 0
    # on the very next round and the frontend's already-advanced local
    # pointer (which never resets) would then never see a "new" value again,
    # silently suppressing the reveal modal on every round after the first.
    _dealer_lottery_result_seq: int = 0
    last_targeted_drinking_result: dict | None = None
    # Same reasoning as _dealer_lottery_result_seq above.
    _targeted_drinking_result_seq: int = 0
    # Fires once per subgame *run* (not per mini-round) -- set when
    # end_targeted_drinking() closes out a run, holding each original
    # target's total sips across every mini-round they played. Same
    # session-lifetime placement/seq reasoning as _targeted_drinking_result_seq.
    last_targeted_drinking_summary: dict | None = None
    _targeted_drinking_summary_seq: int = 0


@dataclass
class GameRoom:
    # Core session
    session: RefereeSession

    # Game configuration (mode, flags, bankroll settings)
    config: GameConfig = field(default_factory=GameConfig)

    # Room code this session is stored under in app.services.session_store
    # (set at creation time in app/routes/lobby.py:setup). Used for
    # tagging exported logs (e.g. decision_log.py's "session_id" column).
    room_code: str = ""

    # Per-round transient state — replaced wholesale on each newround
    round: RoundState = field(default_factory=RoundState)

    # Drink accounting + milestone tracking (session-lifetime)
    drinks: DrinkLedger = field(default_factory=DrinkLedger)

    # Session-lifetime statistics
    stats: SessionStats = field(default_factory=SessionStats)

    # Dealer rotation
    rounds_this_dealer: int = 1

    # Log version — increments each round so clients detect log changes
    _log_version: int = 0

    # Decision log (Phase C — per-decision board-state capture for
    # per-player bot training; see docs/planning/DecisionLog-Plan.md)
    _decision_log: list = field(default_factory=list)

    # Dealer Lottery entry log — one row per stake (0-5) decision, human or
    # NPC, so per-player lottery-staking tendency can be mined the same way
    # hand decisions are (see scripts/build_player_profiles.py).
    _dealer_lottery_decision_log: list = field(default_factory=list)

    # Client registry
    _room_clients: dict = field(default_factory=dict)
    _pending_registrations: list = field(default_factory=list)
    _pending_seat_transfers: list = field(default_factory=list)
    _rejoin_requests: list = field(default_factory=list)
    _anim_default: bool = True

    # Guards check-then-mutate sequences on _room_clients / _pending_registrations /
    # _pending_seat_transfers (seat claims, registration approval, seat-transfer
    # approval) against concurrent requests for the same room -- see
    # docs/planning/Code-Audit-2026-07.md #4. Not used for other GameRoom fields.
    _registry_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # Queued settings (applied at newround)
    _queued_settings: dict = field(default_factory=dict)

    # Bust handout sequence counter (session-lifetime; bumped when all
    # handouts for a round resolve — never reset between rounds)
    _bust_handout_seq: int = 0

    # Wild Card Easter egg — cooldown tracker (session-lifetime so it
    # persists across rounds).  Maps player_name → round_count when last used.
    _wild_card_last_used: dict = field(default_factory=dict)

    # Targeted Drinking Mode (Rules.md §5.10) — persistent subgame state
    # (survives across rounds). Per-round vote state lives on RoundState
    # above instead.
    _targeted_drinking_active: bool = False
    _targeted_drinking_targets: list = field(default_factory=list)   # names, fixed for the subgame's lifetime
    _targeted_drinking_streaks: dict = field(default_factory=dict)   # name -> consecutive correct guesses (graduation streak)
    # name -> consecutive WRONG guesses (distinct from the graduation streak
    # above, which it doesn't affect). Drives the streak-scaled wrong-guess
    # penalty in resolve_targeted_drinking_round -- resets to 0 on any
    # correct guess, same as the graduation streak resets on any wrong one.
    _targeted_drinking_losing_streaks: dict = field(default_factory=dict)
    _targeted_drinking_cooldown_until_round: int = 0   # round_count below which a new subgame can't start
    # Majority-vote-to-target: target_name_lower -> set of voter_name_lower.
    # Session-lifetime (not RoundState) like the rest of this block, since
    # a proposal should survive across rounds until it hits majority or the
    # subgame starts/ends -- unlike _kick_votes, which resets every round.
    _targeted_drinking_start_votes: dict = field(default_factory=dict)
    # Set only when this subgame was launched by the Wild Card easter egg
    # (name of the player who pressed it) -- None for admin-started subgames.
    # Gates the easter-egg-only 5-sip cap/graduation-payback mechanic below.
    _targeted_drinking_presser: str | None = None
    # name -> total sips drunk across every mini-round of this subgame run
    # (unlike _targeted_drinking_streaks, never loses a name when someone
    # graduates -- this is the running tally end_targeted_drinking snapshots
    # into last_targeted_drinking_summary for the end-of-subgame recap).
    _targeted_drinking_total_sips: dict = field(default_factory=dict)
    # Live run-wide statistics (Rules.md §5.10, "statistics table"):
    # correct/wrong guess counts per target (never lose a name on
    # graduation, same reasoning as _targeted_drinking_total_sips above),
    # plus how many of this run's isolated dealer hands busted vs. stood --
    # exposed live (not just in the end-of-run summary) so targeted players
    # can factor "the dealer's busted 40% of hands so far" into their next
    # call. Reset in start_targeted_drinking, snapshotted into
    # last_targeted_drinking_summary and cleared in end_targeted_drinking.
    _targeted_drinking_correct_counts: dict = field(default_factory=dict)
    _targeted_drinking_wrong_counts: dict = field(default_factory=dict)
    _targeted_drinking_dealer_hands: int = 0
    _targeted_drinking_dealer_busts: int = 0

    # Cash wager / bankroll system (Normal mode only — drinking_mode = False)
    _bankrolls: dict = field(default_factory=dict)
    _player_bets: dict = field(default_factory=dict)   # name -> per-round bet override
    _last_round_payouts: dict = field(default_factory=dict)
    _bank_run_players: list = field(default_factory=list)
    _biggest_round_payouts: dict = field(default_factory=dict)

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
        return self.session._hard_switch_drinking_applied

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
        extra = self.round._eor_msgs_buffer
        self.round._eor_msgs_buffer = []
        return self.session.cmd_endround(
            skip_sweep=(self.mode == "digital"),
            extra_eor_msgs=extra,
        )

    def cmd_status(self):
        return self.session.cmd_status()

    # ------------------------------------------------------------------
    # GameConfig shims — backward-compat aliases for session.config.*
    # These cover all app call sites that use session.mode,
    # session.drinking_mode, etc. directly.  Remove each shim once its
    # call sites are migrated to session.config.*.
    # ------------------------------------------------------------------

    @property
    def mode(self): return self.config.mode
    @mode.setter
    def mode(self, v): self.config.mode = v

    @property
    def drinking_mode(self): return self.config.drinking_mode
    @drinking_mode.setter
    def drinking_mode(self, v): self.config.drinking_mode = v

    @property
    def easy_mode(self): return self.config.easy_mode
    @easy_mode.setter
    def easy_mode(self, v): self.config.easy_mode = v

    @property
    def bust_vote_enabled(self): return self.config.bust_vote_enabled
    @bust_vote_enabled.setter
    def bust_vote_enabled(self, v): self.config.bust_vote_enabled = v

    @property
    def strategy_hint_enabled(self): return self.config.strategy_hint_enabled
    @strategy_hint_enabled.setter
    def strategy_hint_enabled(self, v): self.config.strategy_hint_enabled = v

    @property
    def _god_mode(self): return self.config.god_mode
    @_god_mode.setter
    def _god_mode(self, v): self.config.god_mode = v

    @property
    def _dealer_rotate_every(self): return self.config.dealer_rotate_every
    @_dealer_rotate_every.setter
    def _dealer_rotate_every(self, v): self.config.dealer_rotate_every = v

    @property
    def bet_amount(self): return self.config.bet_amount
    @bet_amount.setter
    def bet_amount(self, v): self.config.bet_amount = v

    @property
    def starting_bankroll(self): return self.config.starting_bankroll
    @starting_bankroll.setter
    def starting_bankroll(self, v): self.config.starting_bankroll = v

    @property
    def wild_card_enabled(self): return self.config.wild_card_enabled
    @wild_card_enabled.setter
    def wild_card_enabled(self, v): self.config.wild_card_enabled = v
