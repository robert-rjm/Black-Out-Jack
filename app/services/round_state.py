"""
app/services/round_state.py
===========================
Leaf module: turn order, round phase and card / hand serialisation.
Imports nothing from serializer.py, so domain services can use these helpers
without depending on the presentation layer.
"""

from engine.blackjack import Hand
from engine.drinking_rules import _bj_multiplier

from app.models.game_room import GameRoom


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
