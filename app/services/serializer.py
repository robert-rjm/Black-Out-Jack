"""
app/services/serializer.py
===========================
Converts live session state into the JSON snapshots the frontend consumes.

All functions are pure reads — nothing here mutates session state.
The only external dependency is validators.get_client_info so that
per-client fields (my_role, is_dealer_client, etc.) can be included.
"""

import time

from engine.blackjack import Hand, NPC_Player
from engine.drinking_rules import _bj_multiplier

from app.models.game_room import GameRoom
from app.services.validators import get_client_info


# ---------------------------------------------------------------------------
# Turn / phase helpers
# ---------------------------------------------------------------------------

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


def current_turn(session: GameRoom) -> str | None:
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


def round_phase(session: GameRoom) -> str:
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
        "bj_mult":    _bj_multiplier(hand),
        "done":       hand_done(hand),
        "can_split":  hand.can_split(),
    }


# ---------------------------------------------------------------------------
# Bust-vote window helper
# ---------------------------------------------------------------------------

def _bust_vote_window(session: GameRoom) -> dict:
    """Return bust_vote_window_open and bust_vote_seconds_left for the frontend."""
    if not session.bust_vote_enabled or not session._bust_vote_expires_at:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    now        = time.monotonic()
    secs_left  = session._bust_vote_expires_at - now
    if secs_left <= 0:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    # Early close: all non-NPC players have voted or passed
    human_players = [p for p in session.all_players
                     if not getattr(p, "is_npc", False)]
    all_decided = bool(human_players) and all(
        session._bust_votes.get(p.name) is not None for p in human_players
    )
    if all_decided:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    return {
        "bust_vote_window_open":   True,
        "bust_vote_seconds_left":  max(1, int(secs_left)),
    }


# ---------------------------------------------------------------------------
# Sip / drink aggregation helpers
# ---------------------------------------------------------------------------

def compute_sip_totals(session: GameRoom) -> dict:
    """Return cumulative sip counts per player: past rounds + current round."""
    if not session.drinking_mode:
        return {}
    ticker = dict(session._sip_ticker)
    if not session._drink_log_harvested:
        for p in session.all_players:
            net = max(0, sum((e[0] or 0) for e in p.drink_log if e))
            if net > 0:
                ticker[p.name] = ticker.get(p.name, 0) + net
    return ticker


def compute_dealer_role_sips(session: GameRoom) -> dict:
    """Return cumulative dealer-role sip counts: past rounds + current round."""
    if not session.drinking_mode:
        return {}
    ticker = dict(session._dealer_role_ticker)
    if not session._drink_log_harvested:
        for p in session.all_players:
            for entry in p.drink_log:
                sips = entry[0] if entry else 0
                role = entry[2] if len(entry) > 2 else "player"
                if sips > 0 and role == "dealer":
                    ticker[p.name] = ticker.get(p.name, 0) + sips
    return ticker


def compute_best_play(session: GameRoom, turn: str | None, phase: str) -> str | None:
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
# Insurance vote serializer helper
# ---------------------------------------------------------------------------

def _serialize_insurance_vote(v: dict, session: GameRoom, client_info: dict) -> dict:
    """Serialize one insurance vote entry.

    insure_count / decline_count are exposed as soon as every eligible player
    has cast a vote — not gated on `resolved` (which only flips after the 60s
    timeout). This means the banner can show the correct result immediately
    when the last vote comes in rather than always defaulting to "DECLINE".
    """
    bj_player    = v["player"]
    votes_needed = sum(1 for p in session.all_players
                       if p.name.lower() != bj_player.lower())
    votes_cast   = len(v["votes"])
    counts_ready = v["resolved"] or votes_cast >= votes_needed
    return {
        "bj_player":      bj_player,
        "hand_idx":       v["hand_idx"],
        "resolved":       v["resolved"],
        "my_vote":        v["votes"].get(client_info.get("name") or "", None),
        "votes_cast":     votes_cast,
        "votes_needed":   votes_needed,
        "votes_cast_by":  dict(v["votes"]),   # {voter_name: bool} — local multiplayer uses this to advance seats
        "insure_count":  sum(1 for x in v["votes"].values() if x)     if counts_ready else None,
        "decline_count": sum(1 for x in v["votes"].values() if not x) if counts_ready else None,
        "seconds_left":  max(0, int(60 - (time.monotonic() - v.get("started_at", time.monotonic())))),
    }


# ---------------------------------------------------------------------------
# Full state snapshot
# ---------------------------------------------------------------------------

def serialize_state(session: GameRoom | None, client_id: str = "") -> dict:
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
    mode         = session.mode
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
    switch         = session.switch_this_round
    rounds_td      = session.rounds_this_dealer
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

    # KPI panel data — cumulative per-player hand outcomes + session stats
    hand_stats = dict(session._hand_stats)

    return {
        "ok":              True,
        "round":           session.round_count,
        "dealer":          session.dealer_name,
        "players":         [p.name for p in session.all_players],
        "num_hands":       session.num_hands,
        "wager":           session.wager,
        "mode":            session.mode,
        "table":           table,
        "dealer_hand":     d_hand_state,
        "current_turn":    turn,
        "play_order":      play_order(session),
        "phase":           phase,
        "drinking_mode":          session.drinking_mode,
        "best_play":              compute_best_play(session, turn, phase),
        "suggest_rotate":         suggest_rotate,
        "rotate_reason":          rotate_reason,
        "rounds_this_dealer":     rounds_td,
        "dealer_rotate_every":    session._dealer_rotate_every,
        "switch_this_round":      switch,
        "log_entries":            session._log_entries,
        "log_count":              len(session._log_entries),
        "log_version":            session._log_version,
        "peeked_card":            session._last_peeked,
        "sip_totals":             sip_totals,
        "sip_grand_total":        sum(sip_totals.values()),
        "round_over_seq":         session._round_over_seq,
        # KPI panel data
        "hand_stats":             hand_stats,
        "strategy_decisions":     dict(session._strategy_decisions),
        "streaks":                dict(session._streaks),
        "max_round_sips":         dict(session._max_round_sips),
        "dealer_bust_rounds":     session._dealer_bust_rounds,
        "round_sip_history":      list(session._round_sip_history),
        "session_seconds":        max(0, round(time.monotonic() - session._session_started_at)),
        "last_round_sips":        {k: max(0, v) for k, v in session._last_round_sips.items()},
        "last_round_drinks":      session._last_round_drinks,
        "round_notices":          session._round_notices,
        "prev_round_sips":        {k: max(0, v) for k, v in session._prev_round_sips.items()},
        "prev_round_drinks":      session._prev_round_drinks,
        "dealer_role_sips":       compute_dealer_role_sips(session),
        "preselections":          session._preselections,
        "suggestions":            session._suggestions,
        "kick_votes":             {k: len(v) for k, v in session._kick_votes.items()},
        "kick_votes_mine":        [k for k, v in session._kick_votes.items()
                                   if (_ci.get("name") or "").lower() in v],
        "kick_votes_detail":      {k: sorted(v) for k, v in session._kick_votes.items()},
        "rejoin_requests":        [r for r in session._rejoin_requests
                                   if _ci.get("role") == "admin"],
        "my_rejoin_pending":      any(r["client_id"] == client_id
                                      for r in session._rejoin_requests),
        "pending_registrations":  [{"client_id": r["client_id"], "name": r["name"]}
                                   for r in session._pending_registrations
                                   if _ci.get("role") == "admin"],
        "my_registration_pending": any(r["client_id"] == client_id
                                       for r in session._pending_registrations),
        "my_registration_rejected": _ci.get("role") == "denied",         # any denial
        "my_registration_denied":   (                                     # permanent block
            _ci.get("role") == "denied" and
            _ci.get("reg_denials", 0) >= 2
        ),
        "anim_default":           session._anim_default,
        "easy_mode":              session.easy_mode,
        "bust_vote_enabled":      session.bust_vote_enabled,
        "god_mode_enabled":       session._god_mode,
        "bust_votes":             dict(session._bust_votes),
        "my_bust_vote":           session._bust_votes.get((_ci.get("name") or "").capitalize()),
        "bust_vote_result":       session._bust_vote_result,
        "bust_handout_seconds_left": (
            max(0, round(session._bust_handout_expires_at - time.monotonic()))
            if session._bust_handout_expires_at else 0
        ),
        "insurance_result":       session._insurance_result,
        "ace_drink_events":       session._ace_drink_events,
        "ace_drink_seq":          session._ace_drink_seq,
        "my_bust_handout_pending": [
            n for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
            if (session._bust_vote_result or {}).get("dealer_busted")
            and n in (session._bust_vote_result or {}).get("winners", [])
            and n not in session._bust_handouts_given
        ],
        **_bust_vote_window(session),
        "connected_clients":      [
            {"name": info.get("name"), "role": info.get("role")}
            for info in session._room_clients.values()
            if not info.get("kicked")
        ],
        "kicked_clients":         [
            {"client_id": cid, "name": info.get("name") or ""}
            for cid, info in session._room_clients.items()
            if info.get("kicked") and info.get("name")
        ] if _ci.get("role") == "admin" else [],
        "denied_clients":         [
            {"client_id": cid}
            for cid, info in session._room_clients.items()
            if info.get("role") == "denied" and info.get("reg_denials", 0) >= 2
        ] if _ci.get("role") == "admin" else [],
        "my_role":                _ci.get("role"),
        "my_name":                _ci.get("name"),
        "my_names":               _ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []),
        "can_add_local_seat":     (
            _ci.get("role") == "admin" and
            any(
                p.name not in {(info.get("name") or "").capitalize()
                               for info in session._room_clients.values()
                               if not info.get("kicked")}
                and p.name not in (_ci.get("local_names") or [])
                for p in session.all_players
            )
        ),
        "my_bust_votes":          {
            n: session._bust_votes.get(n)
            for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
        },
        "is_dealer_client":       (
            (_ci.get("role") == "admin" and session._god_mode) or
            session.dealer_name.lower() in {
                (n or "").lower()
                for n in ([_ci.get("name")] + list(_ci.get("local_names") or []))
            }
        ),
        "queued_settings":        session._queued_settings,
        "num_decks":              session.shoe.num_decks if session.shoe else 1,
        "last_milestone_result":  (lambda r: {
            "winner":      r["winner"],
            "boundary":    r["boundary"],
            "allocations": r["allocations"],
            "seconds_ago": max(0, round(time.monotonic() - r["set_at"])),
        } if r and time.monotonic() - r["set_at"] < 90 else None)(
            session._last_milestone_result
        ),
        "pending_milestone":      (lambda m: {
            "boundary":     m["boundary"],
            "winner":       m["winner"],
            "handout":      m["handout"],
            "seconds_left": max(0, round(m["expires_at"] - time.monotonic())),
            "i_am_winner":  bool(_ci.get("name") and
                                 m["winner"].lower() == _ci["name"].lower()),
        } if m and time.monotonic() < m["expires_at"] else None)(
            session._pending_milestone
        ),
        "insurance_votes":        [
            _serialize_insurance_vote(v, session, _ci)
            for v in session._insurance_votes
        ],
        # Monotonically increasing token (µs since process start).
        # The frontend drops any applyState() call whose state_seq is older
        # than the last one it applied — prevents stale poll responses from
        # overwriting fresher command/preselect responses.
        "state_seq":              int(time.monotonic() * 1_000_000),
    }
