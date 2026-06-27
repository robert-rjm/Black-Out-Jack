"""
app/services/room_manager.py
=============================
Room lifecycle helpers: tracker setup, queued settings, dealer rotation,
and the stdout-capture utility used by setup/command routes.

All functions accept a session object — this module never imports
session_store. The route layer owns the store lookup and passes the
session down.
"""

import contextlib
import io
import logging

from engine.blackjack import Hand, NPC_Player, Player, Shoe
from engine.referee import RefereeSession

from app.models.game_room import GameRoom, RoundState

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tracker helpers
# ---------------------------------------------------------------------------

class NullTracker:
    """Drop-in replacement for DrinkTracker when drinking mode is off.
    All methods are silent no-ops so game logic can call tracker.apply()
    unconditionally regardless of mode.
    """
    easy_mode: bool = False  # mirrors DrinkTracker.easy_mode; written by apply_queued_settings

    def apply(self, msgs):                    pass
    def apply_end_of_round(self, msgs: list): pass
    def apply_ace_clubs_credit(self, player): pass
    def print_round_summary(self):            pass


def patch_tracker(session: RefereeSession) -> None:
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web server never blocks waiting for terminal input.
    """
    tracker = session.tracker
    tracker.verbose = False  # suppress prints in web context
    session.verbose = False  # suppress RefereeSession's own round-summary prints

    def web_handout(giver: str, total: int, reason: str, label: str = "5-card 21"):
        log.debug(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        log.debug(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} ({label}, auto)", "player")
            log.debug(f"    -> {t.name} +1 sip")

    tracker._handle_handout = web_handout


# ---------------------------------------------------------------------------
# Stdout capture
# ---------------------------------------------------------------------------

def capture(fn, *args) -> str:
    """Call fn(*args) and return everything it printed as a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Round lifecycle
# ---------------------------------------------------------------------------

def reset_round_state(session: GameRoom, *, digital: bool = False) -> None:
    """Replace the per-round RoundState and reset non-RoundState guards.

    RoundState is replaced wholesale so every field defined there is
    automatically cleared — no need to update this function when new
    per-round fields are added to RoundState.

    The three items below live outside RoundState because they are either
    session-lifetime counters or properties that delegate into RefereeSession:

    - _log_version: increments each round so clients detect log changes
    - _hard_switch_drinking_applied: guard on RefereeSession
    - _insurance_result: attribute on RefereeSession

    The ``digital`` parameter is retained for call-site compatibility;
    _deferred_hole_card_msgs is now part of RoundState so it is cleared in
    both modes (harmless in referee mode, which never populates it).
    """
    session.round                         = RoundState()
    session._log_version                 += 1
    session._hard_switch_drinking_applied = False
    session._insurance_result             = None


def apply_queued_settings(session: GameRoom) -> list[str]:
    """Apply any queued settings to the session before a new round starts.
    Returns a list of human-readable change descriptions.
    """
    queued = session._queued_settings
    if not queued:
        return []

    changes = []

    if "wager" in queued:
        session.wager = queued["wager"]
        changes.append(f"Sips/hand set to {queued['wager']}")

    if "num_hands" in queued:
        session.num_hands = queued["num_hands"]
        changes.append(f"Hands/player set to {queued['num_hands']}")

    if "easy_mode" in queued:
        session.easy_mode = bool(queued["easy_mode"])
        session.tracker.easy_mode = session.easy_mode
        changes.append(f"Easy Mode {'ON' if session.easy_mode else 'OFF'}")

    if "num_decks" in queued and session.mode == "digital":
        session.shoe = Shoe(queued["num_decks"])
        session.shoe.shuffle(quiet=True)
        changes.append(f"Deck count set to {queued['num_decks']}")

    for entry in queued.get("add_players", []):
        name   = entry["name"]
        is_npc = entry["is_npc"]
        if not any(p.name == name for p in session.all_players):
            p           = NPC_Player(name) if is_npc else Player(name)
            p.is_dealer = False
            # Insert just before the dealer so the new seat appears in the
            # correct visual position (dealer's right) rather than at the end.
            players    = session.all_players
            dealer_idx = next((i for i, pl in enumerate(players) if pl.is_dealer), len(players))
            players.insert(dealer_idx, p)
            changes.append(f"Added {'bot' if is_npc else 'player'} {name}")
            # Non-bot new players are local by default
            if not is_npc:
                for info in session._room_clients.values():
                    if info.get("role") == "admin":
                        local_names = info.get("local_names") or []
                        if name not in local_names:
                            info["local_names"] = local_names + [name]
                        break

    # Auto-bump to 2 decks when player count reaches 4+ (digital mode only),
    # unless the admin explicitly queued a deck count this round.
    if (session.mode == "digital"
            and "num_decks" not in queued
            and len(session.all_players) >= 4
            and getattr(session.shoe, "num_decks", 1) < 2):
        session.shoe = Shoe(2)
        session.shoe.shuffle(quiet=True)
        changes.append("Deck count auto-bumped to 2 (4+ players)")

    for name in queued.get("remove_players", []):
        before = len(session.all_players)
        session.all_players = [
            p for p in session.all_players if p.name != name or p.is_dealer
        ]
        if len(session.all_players) < before:
            changes.append(f"Removed player {name}")
            # Prune the removed name from admin's local_names so the give-bust
            # panel (my_bust_handout_pending) never references a ghost player.
            for info in session._room_clients.values():
                if info.get("role") == "admin":
                    local_names = info.get("local_names") or []
                    info["local_names"] = [n for n in local_names
                                           if n.lower() != name.lower()]
                    break

    session._queued_settings = {}
    return changes


def rotate_dealer(session: GameRoom) -> None:
    """Rotate the dealer role one seat clockwise."""
    all_names = [p.name for p in session.all_players]
    if not all_names:
        return
    try:
        cur_idx = all_names.index(session.dealer_name)
    except ValueError:
        # Current dealer no longer exists (e.g. removed via
        # apply_queued_settings) — fall back to the first seat.
        cur_idx = -1
    new_dealer = all_names[(cur_idx + 1) % len(all_names)]
    for p in session.all_players:
        p.is_dealer   = (p.name == new_dealer)
        p.dealer_hand = Hand() if p.is_dealer else None
    session.dealer_name = new_dealer
    log.debug(f"  Dealer rotates => {new_dealer} is now dealer.")
