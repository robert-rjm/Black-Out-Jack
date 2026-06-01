"""
app/models/game_room.py — typed container for all per-room state.

__getattr__ forwards unknown reads to the inner RefereeSession.
__setattr__ forwards unknown writes to the inner RefereeSession so that
e.g. session.dealer_name = "Bob" updates RefereeSession, not a GameRoom
shadow attr that would cause _get_dealer() to return a stale player.
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
    _bust_votes: dict = field(default_factory=dict)        # player_name → "bust" | "pass"
    _bust_vote_expires_at: float | None = None             # monotonic timestamp; None = window closed
    _bust_vote_result: dict | None = None                  # set after resolve, cleared on newround

    # Misc UI state
    _last_peeked: dict | None = None

    def __getattr__(self, name):
        session = object.__getattribute__(self, "session")
        return getattr(session, name)

    def __setattr__(self, name, value):
        if name in type(self).__dataclass_fields__:
            object.__setattr__(self, name, value)
        else:
            try:
                session = object.__getattribute__(self, "session")
                setattr(session, name, value)
            except AttributeError:
                object.__setattr__(self, name, value)
