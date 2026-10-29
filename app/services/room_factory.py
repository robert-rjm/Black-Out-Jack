"""
app/services/room_factory.py
=============================
Builds a fully initialised GameRoom (players, config, shoe, tracker, first
round) and stores it against a reserved room code. Shared by POST /setup and
by the "switch to BOJ" table split (services/boj_switch.py).
"""

from engine.blackjack import Player, Hand, Shoe, NPC_Player
from engine.referee import RefereeSession

from app.models.game_room import GameRoom, GameConfig
from engine.rules_registry import DEFAULT_RULES
from app.services.session_store import set_session
from app.services.room_manager import NullTracker, patch_tracker, capture
from app.services.payout_tracker import init_bankrolls


def build_game_room(room_code, client_id, names, npc_names, npc_personalities,
                    dealer_name, *, mode, drinking, wager, num_hands,
                    bet_amount, starting_bankroll, num_decks,
                    rules=DEFAULT_RULES, easy_mode=False):
    """Create the GameRoom for ``room_code`` and start its first round.

    ``rules`` is the room's full RuleSet, so a table built from another one
    (the BOJ split) keeps every house rule, not just the bust vote.

    ``client_id`` (may be empty) is registered as the admin, seated at the
    first non-bot name. Returns ``(room, output)``; the first round's log output
    is already appended to the room's round log.
    """
    players = []
    for name in names:
        if name in npc_names:
            personality = npc_personalities.get(name, "basic")
            p           = NPC_Player(name, personality=personality)
        else:
            p           = Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    raw_session = RefereeSession(players, dealer_name, wager, num_hands)
    room = GameRoom(
        session=raw_session,
        room_code=room_code,
        rounds_this_dealer=1,
        config=GameConfig(
            mode=mode,
            drinking_mode=drinking,
            dealer_rotate_every=len(players),
            rules=rules,
            easy_mode=easy_mode,
            bet_amount=bet_amount,
            starting_bankroll=starting_bankroll,
        ),
    )
    if client_id:
        # All non-NPC seats start as local — a seat moves to remote only when
        # another device registers and claims it (handle_registration removes it).
        local_names = [p.name for p in players if p.name not in npc_names]
        # Admin is always seated at Player1 (first non-NPC seat) regardless of
        # who the dealer is. god_mode keeps them in game control either way.
        # This ensures that when they transfer admin, they retain a player seat
        # automatically without any extra steps.
        admin_seat = local_names[0] if local_names else dealer_name
        room._room_clients[client_id] = {
            "name": admin_seat, "local_names": local_names,
            "role": "admin", "kicked": False,
        }
    set_session(room_code, room)

    if mode == "digital":
        raw_session.shoe = Shoe(num_decks)
        raw_session.shoe.shuffle(quiet=True)

    if not drinking:
        raw_session.tracker = NullTracker()

    if mode == "digital" and not drinking:
        init_bankrolls(room)

    output = capture(raw_session.start_round)
    if drinking:
        patch_tracker(raw_session)  # must run AFTER start_round creates a fresh tracker
        raw_session.tracker.easy_mode = room.easy_mode
    if output.strip():
        room.round._log_entries.append(output)
    return room, output
