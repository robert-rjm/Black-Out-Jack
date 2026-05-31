"""
app/models/game_room.py
========================
Typed container for all per-room state.

Before this existed, RefereeSession (a third-party class) was monkey-patched
with 30+ attrs in setup() — meaning every reader had to guard with
getattr(session, "_xyz", default) because nothing guaranteed the attr was
set.  GameRoom fixes that: every field has a declared type and a safe
default, so callers can just write room._xyz.

Delegation
----------
GameRoom wraps a RefereeSession rather than inheriting from it.
__getattr__ transparently forwards any attribute lookup that isn't a
GameRoom field (e.g. room.all_players, room.dealer_name, room.tracker)
to the inner session, so existing service code that doesn't know about
GameRoom still works without mass-renaming.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from referee import RefereeSession


@dataclass
class GameRoom:
    # ------------------------------------------------------------------ #
    # Core session — owns all blackjack / referee logic                   #
    # ------------------------------------------------------------------ #
    session: RefereeSession

    # ------------------------------------------------------------------ #
    # Game configuration (set once at /setup, may change via queued)      #
    # ------------------------------------------------------------------ #
    mode: str = "referee"                  # "referee" | "digital"
    drinking_mode: bool = True

    # ------------------------------------------------------------------ #
    # Dealer-rotation tracking                                            #
    # ------------------------------------------------------------------ #
    rounds_this_dealer: int = 1            # rounds the current dealer has held the role
    switch_this_round: str | None = None   # None | "hard" | "soft"
    _dealer_rotate_every: int = 1          # rotate after N rounds (one full cycle)

    # ------------------------------------------------------------------ #
    # Shared log — broadcast to all clients via /state polling            #
    # ------------------------------------------------------------------ #
    _log_entries: list = field(default_factory=list)
    _log_version: int = 0
    _deferred_hole_card_msgs: list = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Drink / sip accounting                                              #
    # ------------------------------------------------------------------ #
    _drink_csv_rows: list = field(default_factory=list)    # survives across rounds
    _sip_ticker: dict = field(default_factory=dict)        # cumulative sips per player
    _drink_log_harvested: bool = False
    _last_round_sips: dict = field(default_factory=dict)   # sips in last completed round
    _last_round_drinks: list = field(default_factory=list) # detailed entries for Drinks pane
    _prev_round_sips: dict = field(default_factory=dict)   # sips from the round before last
    _prev_round_drinks: list = field(default_factory=list) # drinks from round before last
    _dealer_role_ticker: dict = field(default_factory=dict) # sips earned while dealer

    # ------------------------------------------------------------------ #
    # Client registry                                                     #
    # ------------------------------------------------------------------ #
    _room_clients: dict = field(default_factory=dict)      # client_id → {name, role, kicked}
    _kick_votes: dict = field(default_factory=dict)        # target_lower → set(voter_lower)
    _rejoin_requests: list = field(default_factory=list)   # [{client_id, display_name}]
    _anim_default: bool = True                             # admin animation preference

    # ------------------------------------------------------------------ #
    # Action queues                                                       #
    # ------------------------------------------------------------------ #
    _preselections: dict = field(default_factory=dict)     # "name:hand" → action
    _suggestions: dict = field(default_factory=dict)       # pending dealer→player suggestions
    _insurance_votes: list = field(default_factory=list)   # open insurance vote entries
    _queued_settings: dict = field(default_factory=dict)   # settings to apply next round

    # ------------------------------------------------------------------ #
    # Stats and milestones                                                #
    # ------------------------------------------------------------------ #
    _hand_stats: dict = field(default_factory=dict)        # player → {wins, losses, …}
    _dealer_hand_stats: dict = field(default_factory=dict) # dealer_name → {wins, losses, …}
    _milestones_claimed: dict = field(default_factory=dict) # boundary → winner name
    _pending_milestone: dict | None = None                 # current unclaimed handout
    _last_milestone_result: dict | None = None             # most recent claim result (~15 s)

    # ------------------------------------------------------------------ #
    # Misc UI state                                                       #
    # ------------------------------------------------------------------ #
    _last_peeked: dict | None = None                       # serialised peeked card

    # ------------------------------------------------------------------ #
    # Delegation                                                          #
    # ------------------------------------------------------------------ #
    def __getattr__(self, name: str):
        """Forward any unknown attribute to the wrapped RefereeSession.

        This lets callers use room.all_players, room.dealer_name,
        room.tracker, room.wager, etc. without knowing about the wrapper.
        __getattr__ is only called when normal lookup (instance dict +
        class) has already failed, so GameRoom's own fields take priority.
        """
        # Use object.__getattribute__ to avoid infinite recursion.
        session = object.__getattribute__(self, "session")
        return getattr(session, name)
