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

from app.models.game_room import GameRoom

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tracker helpers
# ---------------------------------------------------------------------------

class NullTracker:
    """Drop-in replacement for DrinkTracker when drinking mode is off.
    All methods are silent no-ops so game logic can call tracker.apply()
    unconditionally regardless of mode.
    """
    def apply(self, msgs):                    pass
    def apply_end_of_round(self, *msg_lists): pass
    def apply_ace_clubs_credit(self, player): pass
    def print_round_summary(self):            pass
    def _handle_handout(self, *a, **kw):      pass


def patch_tracker(session: RefereeSession) -> None:
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web server never blocks waiting for terminal input.
    """
    tracker = session.tracker
    tracker.verbose = False  # suppress prints in web context

    def web_handout(giver: str, total: int, reason: str):
        log.debug(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        log.debug(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21, auto)", "player")
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

    if "num_decks" in queued and session.mode == "digital":
        session.shoe = Shoe(queued["num_decks"])
        session.shoe.shuffle()
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
    all_names  = [p.name for p in session.all_players]
    cur_idx    = all_names.index(session.dealer_name)
    new_dealer = all_names[(cur_idx + 1) % len(all_names)]
    for p in session.all_players:
        p.is_dealer   = (p.name == new_dealer)
        p.dealer_hand = Hand() if p.is_dealer else None
    session.dealer_name = new_dealer
    log.debug(f"  Dealer rotates => {new_dealer} is now dealer.")
