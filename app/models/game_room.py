"""
app/models/game_room.py — typed container for all per-room state.

All RefereeSession attributes used by app/ code are exposed as explicit
properties or method wrappers below — no __getattr__ magic.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from referee import RefereeSession


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
    _milestones_claimed: dict = field(default_factory=dict)
    _pending_milestone: dict | None = None
    _last_milestone_result: dict | None = None

    # Bust vote side bet
    bust_vote_enabled: bool = False
    _god_mode: bool = True
    _bust_votes: dict = field(default_factory=dict)        # player_name -> "bust" | "pass"
    _bust_vote_expires_at: float | None = None             # monotonic timestamp; None = window closed
    _bust_vote_result: dict | None = None                  # set after resolve, cleared on newround
    _bust_handouts_given: set = field(default_factory=set) # winner names who have given their handout sip

    # Mid-round state (digital only - reset each newround in game_commands.py)
    _ace_drink_events: list = field(default_factory=list)
    _ace_drink_seq: int = 0

    # Misc UI state
    _last_peeked: dict | None = None

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
        return self.session.start_round()

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
        return self.session.cmd_endround()

    def cmd_status(self):
        return self.session.cmd_status()
