"""
app/services/serializer.py
===========================
Converts live session state into the JSON snapshots the frontend consumes.

All functions are pure reads — nothing here mutates session state.
The only external dependency is validators.get_client_info so that
per-client fields (my_role, is_dealer_client, etc.) can be included.
"""

import time

from blackjack import Hand, NPC_Player
from referee import RefereeSession

from app.services.validators import get_client_info


# ---------------------------------------------------------------------------
# Turn / phase helpers
# ---------------------------------------------------------------------------

def play_order(session: RefereeSession) -> list[str]:
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


def current_turn(session: RefereeSession) -> str | None:
    """
    Whose turn is it right now?
    Returns the player name, or None if no one is up (pre-deal or dealer phase).
    Only meaningful when the initial deal has happened.
    """
    has_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_cards:
        return None
    for name in play_order(session):
        p = session._get_player(name)
        if p and not player_done(p):
            return name
    return None   # all player hands done → dealer phase


def round_phase(session: RefereeSession) -> str:
    """
    'pre-deal'     → waiting for initial deal
    'playing'      → at least one player still has an active hand
    'dealer-ready' → all player hands done, dealer hand not yet fully revealed
    'round-over'   → dealer has stood/busted, results assigned
    """
    dealer = session._get_dealer()
    has_player_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_player_cards:
        return "pre-deal"

    if current_turn(session) is not None:
        return "playing"

    d_hand = dealer.dealer_hand if dealer else None
    if d_hand and (d_hand.stood or d_hand.is_bust() or d_hand.score() >= 17 or d_hand.is_blackjack()):
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
        "done":       hand_done(hand),
        "can_split":  hand.can_split(),
    }


# ---------------------------------------------------------------------------
# Sip / drink aggregation helpers
# ---------------------------------------------------------------------------

def compute_sip_totals(session: RefereeSession) -> dict:
    """Return cumulative sip counts per player: past rounds + current round."""
    if not getattr(session, "drinking_mode", True):
        return {}
    ticker = dict(getattr(session, "_sip_ticker", {}))
    if not getattr(session, "_drink_log_harvested", False):
        for p in session.all_players:
            for entry in p.drink_log:
                sips = entry[0] if entry else 0
                if sips > 0:
                    ticker[p.name] = ticker.get(p.name, 0) + sips
    return ticker


def compute_dealer_role_sips(session: RefereeSession) -> dict:
    """Return cumulative dealer-role sip counts: past rounds + current round."""
    if not getattr(session, "drinking_mode", True):
        return {}
    ticker = dict(getattr(session, "_dealer_role_ticker", {}))
    if not getattr(session, "_drink_log_harvested", False):
        for p in session.all_players:
            for entry in p.drink_log:
                sips = entry[0] if entry else 0
                role = entry[2] if len(entry) > 2 else "player"
                if sips > 0 and role == "dealer":
                    ticker[p.name] = ticker.get(p.name, 0) + sips
    return ticker


def compute_best_play(session: RefereeSession, turn: str | None, phase: str) -> str | None:
    """
    Return the basic-strategy best action ('h'|'s'|'d'|'sp') for the
    current active hand, or None when it's not applicable.
    Always assumes drinking mode (web is always drinking mode).
    """
    if phase != "playing" or not turn:
        return None
    player = session._get_player(turn)
    if not player:
        return None
    dealer = session._get_dealer()
    if not dealer or not dealer.dealer_hand or not dealer.dealer_hand.cards:
        return None
    active_hand = next((h for h in player.hands if not hand_done(h)), None)
    if not active_hand or not active_hand.cards:
        return None
    dealer_up = dealer.dealer_hand.cards[0]
    valid = ["h", "s"]
    if len(active_hand.cards) == 2 and not active_hand.doubled:
        valid.append("d")
    if active_hand.can_split():
        valid.append("sp")
    return NPC_Player.best_play(active_hand, dealer_up, valid, drinking_mode=True)


# ---------------------------------------------------------------------------
# Full state snapshot
# ---------------------------------------------------------------------------

def serialize_state(session: RefereeSession | None, client_id: str = "") -> dict:
    """Full snapshot for the UI."""
    if not session:
        return {"ok": False}

    _ci = get_client_info(session, client_id) if client_id else {}

    dealer      = session._get_dealer()
    phase       = round_phase(session)
    turn        = current_turn(session)
    hide_double = (phase != "round-over")   # reveal doubled card once round is over

    table = []
    for p in session.all_players:
        table.append({
            "name":      p.name,
            "is_dealer": p.is_dealer,
            "is_npc":    getattr(p, "is_npc", False),
            "hands":     [serialize_hand(h, hide_double=hide_double) for h in p.hands],
            "done":      player_done(p),
            "is_turn":   (p.name == turn),
        })

    # Dealer hand — hide hole card while players are still acting (digital only)
    mode         = getattr(session, "mode", "referee")
    d_hand_state = None
    if dealer and dealer.dealer_hand:
        d_cards = dealer.dealer_hand.cards
        if mode == "digital" and phase in ("playing", "pre-deal") and len(d_cards) >= 2:
            d_hand_state = {
                "cards":     [serialize_card(d_cards[0]),
                              {"rank": "?", "suit": "hidden", "symbol": "?"}]
                              + [serialize_card(c) for c in d_cards[2:]],
                "score":     "?",
                "hidden":    True,
                "blackjack": False,
                "bust":      False,
                "done":      False,
            }
        else:
            d_hand_state = {
                "cards":     [serialize_card(c) for c in d_cards],
                "score":     dealer.dealer_hand.score() if d_cards else 0,
                "hidden":    False,
                "blackjack": bool(d_cards) and dealer.dealer_hand.is_blackjack(),
                "bust":      bool(d_cards) and dealer.dealer_hand.is_bust(),
                "done":      bool(d_cards) and (
                    dealer.dealer_hand.stood
                    or dealer.dealer_hand.is_bust()
                    or dealer.dealer_hand.score() >= 17
                ),
            }

    # Dealer-rotation suggestion
    switch         = getattr(session, "switch_this_round", None)
    rounds_td      = getattr(session, "rounds_this_dealer", 1)
    num_p          = len(session.all_players)
    suggest_rotate = bool(switch in ("hard", "soft") or rounds_td >= num_p)
    if switch == "hard":
        rotate_reason = "Hard switch — dealer lost all hands"
    elif switch == "soft":
        rotate_reason = "Soft switch — dealer won all hands"
    elif suggest_rotate:
        rotate_reason = f"Round {rounds_td} of {num_p} — every player has been dealer"
    else:
        rotate_reason = f"Round {rounds_td} of {num_p} as dealer"

    sip_totals = compute_sip_totals(session)

    return {
        "ok":              True,
        "round":           session.round_count,
        "dealer":          session.dealer_name,
        "players":         [p.name for p in session.all_players],
        "num_hands":       session.num_hands,
        "wager":           session.wager,
        "mode":            getattr(session, "mode", "referee"),
        "table":           table,
        "dealer_hand":     d_hand_state,
        "current_turn":    turn,
        "play_order":      play_order(session),
        "phase":           phase,
        "drinking_mode":          getattr(session, "drinking_mode", True),
        "best_play":              compute_best_play(session, turn, phase),
        "suggest_rotate":         suggest_rotate,
        "rotate_reason":          rotate_reason,
        "rounds_this_dealer":     rounds_td,
        "dealer_rotate_every":    getattr(session, "_dealer_rotate_every", 1),
        "switch_this_round":      switch,
        "log_entries":            getattr(session, "_log_entries", []),
        "log_count":              len(getattr(session, "_log_entries", [])),
        "log_version":            getattr(session, "_log_version", 0),
        "peeked_card":            getattr(session, "_last_peeked", None),
        "sip_totals":             sip_totals,
        "sip_grand_total":        sum(sip_totals.values()),
        "last_round_sips":        getattr(session, "_last_round_sips",   {}),
        "last_round_drinks":      getattr(session, "_last_round_drinks", []),
        "prev_round_sips":        getattr(session, "_prev_round_sips",   {}),
        "prev_round_drinks":      getattr(session, "_prev_round_drinks", []),
        "dealer_role_sips":       compute_dealer_role_sips(session),
        "preselections":          getattr(session, "_preselections", {}),
        "suggestions":            getattr(session, "_suggestions",   {}),
        "kick_votes":             {k: len(v) for k, v in getattr(session, "_kick_votes", {}).items()},
        "kick_votes_mine":        [k for k, v in getattr(session, "_kick_votes", {}).items()
                                   if (_ci.get("name") or "").lower() in v],
        "kick_votes_detail":      {k: sorted(v) for k, v in getattr(session, "_kick_votes", {}).items()},
        "rejoin_requests":        [r for r in getattr(session, "_rejoin_requests", [])
                                   if _ci.get("role") == "admin"],
        "my_rejoin_pending":      any(r["client_id"] == client_id
                                      for r in getattr(session, "_rejoin_requests", [])),
        "anim_default":           getattr(session, "_anim_default", True),
        "connected_clients":      [
            {"name": info.get("name"), "role": info.get("role")}
            for info in getattr(session, "_room_clients", {}).values()
            if not info.get("kicked")
        ],
        "kicked_clients":         [
            {"client_id": cid, "name": info.get("name") or ""}
            for cid, info in getattr(session, "_room_clients", {}).items()
            if info.get("kicked") and info.get("name")
        ] if _ci.get("role") == "admin" else [],
        "my_role":                _ci.get("role"),
        "my_name":                _ci.get("name"),
        "is_dealer_client":       _ci.get("is_dealer", False) or _ci.get("role") == "admin",
        "queued_settings":        getattr(session, "_queued_settings", {}),
        "last_milestone_result":  (lambda r: {
            "winner":      r["winner"],
            "boundary":    r["boundary"],
            "allocations": r["allocations"],
            "seconds_ago": max(0, round(time.monotonic() - r["set_at"])),
        } if r and time.monotonic() - r["set_at"] < 15 else None)(
            getattr(session, "_last_milestone_result", None)
        ),
        "pending_milestone":      (lambda m: {
            "boundary":     m["boundary"],
            "winner":       m["winner"],
            "handout":      m["handout"],
            "seconds_left": max(0, round(m["expires_at"] - time.monotonic())),
            "i_am_winner":  bool(_ci.get("name") and
                                 m["winner"].lower() == _ci["name"].lower()),
        } if m and time.monotonic() < m["expires_at"] else None)(
            getattr(session, "_pending_milestone", None)
        ),
        "insurance_votes":        [
            {
                "bj_player":    v["player"],
                "hand_idx":     v["hand_idx"],
                "resolved":     v["resolved"],
                "my_vote":      v["votes"].get(_ci.get("name") or "", None),
                "votes_cast":   len(v["votes"]),
                "votes_needed": sum(1 for p in session.all_players
                                    if p.name.lower() != v["player"].lower()),
                "insure_count":  sum(1 for x in v["votes"].values() if x)     if v["resolved"] else None,
                "decline_count": sum(1 for x in v["votes"].values() if not x) if v["resolved"] else None,
            }
            for v in getattr(session, "_insurance_votes", [])
        ],
    }
