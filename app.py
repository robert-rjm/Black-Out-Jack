"""
app.py
======
Flask web server supporting two modes:

  referee — physical deck; you type cards as they are dealt; app tracks drinks.
  digital — virtual shoe; app deals cards automatically; full playable blackjack.

Run:
    python app.py

Then open http://<your-PC-IP>:5000 on any phone on the same WiFi.
"""

import csv
import io
import contextlib
import os
import re
import random
import secrets
import socket
import time
from collections import defaultdict
from datetime import datetime

from flask import Flask, request, jsonify, render_template, Response, send_from_directory

from referee import RefereeSession
from blackjack import Player, Hand, Shoe, HandEvaluator, NPC_Player
from drinking_rules import DrinkingRules

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Multi-room state — keyed by room code (e.g. "Jack21")
# ---------------------------------------------------------------------------
game_sessions: dict[str, "RefereeSession | None"] = {}   # room_code → session

ROOM_WORDS = [
    # Original set
    "Ace", "Bets", "Bluff", "Bust", "Cards", "Club", "Deal", "Diamond", "Double", "Flush", "Heart",
    "Hit", "Jack", "Joker", "King", "Luck", "Queen", "Spade", "Split", "Stand", "Suit", "Table",
]

def _generate_room_code() -> str:
    """Return a unique code like 'Jack21' not already in game_sessions."""
    while True:
        word   = secrets.choice(ROOM_WORDS)
        number = 1 + secrets.randbelow(999)   # 1–999
        code   = f"{word}{number}"
        if code not in game_sessions:
            return code


# ---------------------------------------------------------------------------
# Join rate-limiter — per source IP, applied to /join_room only.
# ---------------------------------------------------------------------------
_join_attempts: dict[str, list[float]] = defaultdict(list)
_JOIN_RATE_LIMIT  = 5   # max failed attempts
_JOIN_RATE_WINDOW = 30   # per N seconds


def _join_rate_limited(ip: str) -> bool:
    """Return True when this IP has exceeded the failed-join rate limit."""
    now    = time.monotonic()
    cutoff = now - _JOIN_RATE_WINDOW
    prev   = _join_attempts[ip]
    # Drop expired entries
    _join_attempts[ip] = [t for t in prev if t > cutoff]
    if len(_join_attempts[ip]) >= _JOIN_RATE_LIMIT:
        return True
    _join_attempts[ip].append(now)
    return False


_NAME_STRIP_RE = re.compile(r"[<>\"'`\\]")

def _sanitize_name(raw: str) -> str:
    """Sanitize a player name before storing it.

    Strips HTML tags, removes characters that could break out of HTML
    attribute or script contexts (<>\"'`\\), trims whitespace, capitalizes,
    and caps length at 20 characters.  Returns an empty string if nothing
    is left after sanitization.
    """
    # Remove HTML tags first
    name = re.sub(r"<[^>]*>", "", raw)
    # Strip characters dangerous in HTML/JS contexts
    name = _NAME_STRIP_RE.sub("", name)
    name = name.strip()
    if not name:
        return ""
    return name.capitalize()[:20]


# ---------------------------------------------------------------------------
# Null tracker — used in non-drinking mode so all tracker.apply() calls
# become silent no-ops without touching referee.py or drinking_rules.py.
# ---------------------------------------------------------------------------

class _NullTracker:
    """Drop-in replacement for DrinkTracker when drinking mode is off."""
    def apply(self, msgs):                    pass
    def apply_ace_clubs_credit(self, player): pass
    def print_round_summary(self):            pass
    def _handle_handout(self, *a, **kw):      pass


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------

def _patch_tracker(session: RefereeSession):
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web version never blocks waiting for terminal input.
    """
    tracker = session.tracker

    def web_handout(giver: str, total: int, reason: str):
        print(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        print(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21, auto)", "player")
            print(f"    -> {t.name} +1 sip")

    tracker._handle_handout = web_handout


def _capture(fn, *args):
    """Call fn(*args) and return everything it printed as a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _classify_rule(reason: str):
    """
    Normalise a raw drink-reason string to a short canonical rule name.
    Returns None for bookkeeping entries that should not appear in the CSV.
    Mirrors classify_rule() in simulation.py.
    """
    r = reason
    if "A♣" in r and "credit" in r:          return None
    if "protects" in r:                        return None
    if "exempt" in r:                          return None
    if "Hard Dealer Switch" in r:             return "Hard Dealer Switch"
    if "net loss" in r:                       return "Net hand losses"
    if "lost a doubled hand" in r:            return "Lost doubled hand"
    if "lost a suited hand" in r:             return "Lost suited hand"
    if "immunity exception" in r:             return "Doubled win (immunity break)"
    if "won suited hand" in r:                return "Suited winning hand"
    if "split hand" in r:                     return "Split win (immunity break)"
    if "swept all hands" in r:               return "Other-player sweep"
    if "Blackjack by" in r:                   return "Blackjack bonus"
    if "4 Aces" in r and "first deal" in r:  return "Four Aces (first deal)"
    if "4 Aces" in r and "end of round" in r: return "Four Aces (end of round)"
    if "Dealer hand is all" in r:             return "Dealer suited hand"
    if "handed" in r and "5-card 21" in r:   return "5-card 21 handout received"
    if "won with" in r and "cards" in r:      return "5+ card win"
    if "A♠" in r and "to dealer" in r:       return "Ace dealt: Ace of Spades (dealer hand)"
    if "A♥" in r and "dealer" in r:          return "Ace dealt: Ace of Hearts (dealer hand)"
    if "A♦" in r and "dealer" in r:          return "Ace dealt: Ace of Diamonds (dealer hand)"
    if "A♠" in r:                            return "Ace dealt: Ace of Spades (player hand)"
    if "A♥" in r:                            return "Ace dealt: Ace of Hearts (player hand)"
    if "A♦" in r:                            return "Ace dealt: Ace of Diamonds (player hand)"
    return "Other"


def _harvest_drink_log(session: RefereeSession):
    """
    Copy the current round's drink_log entries from every player into the
    session-wide CSV accumulator.  Call this right after cmd_endround() and
    before start_round() resets drink_log to [].
    """
    rows = getattr(session, "_drink_csv_rows", [])
    round_num = session.round_count
    dealer    = session.dealer_name
    for p in session.all_players:
        for entry in p.drink_log:
            sips   = entry[0]
            reason = entry[1]
            role   = entry[2] if len(entry) > 2 else "player"
            if sips <= 0:
                continue
            rule = _classify_rule(reason)
            if rule is None:
                continue
            rows.append({
                "round":  round_num,
                "dealer": dealer,
                "player": p.name,
                "role":   role,
                "rule":   rule,
                "sips":   sips,
            })
    session._drink_csv_rows = rows
    # Update live sip ticker (raw totals, unfiltered)
    ticker = getattr(session, "_sip_ticker", {})
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            if sips > 0:
                ticker[p.name] = ticker.get(p.name, 0) + sips
    session._sip_ticker          = ticker
    session._drink_log_harvested = True

    # Track cumulative dealer-role sips separately (shown in dealer panel)
    d_ticker = getattr(session, "_dealer_role_ticker", {})
    for p in session.all_players:
        for entry in p.drink_log:
            sips = entry[0] if entry else 0
            role = entry[2] if len(entry) > 2 else "player"
            if sips > 0 and role == "dealer":
                d_ticker[p.name] = d_ticker.get(p.name, 0) + sips
    session._dealer_role_ticker = d_ticker

    # Shift previous snapshot before overwriting (enables round-over comparison)
    session._prev_round_sips   = getattr(session, "_last_round_sips",   {})
    session._prev_round_drinks = getattr(session, "_last_round_drinks", [])

    # Snapshot this round's per-player sip totals for the "Last Round" panel
    last = {}
    for p in session.all_players:
        total = sum(e[0] for e in p.drink_log if e and e[0] > 0)
        if total > 0:
            last[p.name] = total
    session._last_round_sips = last

    # Detailed per-entry drink list with reasons for the Drinks pane
    drinks_detail = []
    for p in session.all_players:
        for entry in p.drink_log:
            if entry and len(entry) >= 2 and entry[0] > 0:
                sips   = entry[0]
                reason = entry[1]
                if _classify_rule(reason) is None:   # skip bookkeeping entries
                    continue
                drinks_detail.append({"name": p.name, "sips": sips, "reason": reason})
    session._last_round_drinks = drinks_detail


def _get_client_info(session, client_id: str) -> dict:
    """Return role/name/is_dealer info for a client_id. Safe if _room_clients missing."""
    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id)          # None if not registered at all
    if info is None:
        return {"role": None, "name": None, "is_dealer": False}
    if info.get("kicked"):
        return {"role": "kicked", "name": None, "is_dealer": False}
    role = info.get("role") or "spectator"
    name = info.get("name")
    # Dealer control follows the seat name, not the admin flag.
    # Admin retains session management (kick etc.) but is only the
    # dealer client when their registered name matches the current dealer.
    is_dealer = (bool(name and name.lower() == session.dealer_name.lower()) or role == "admin")
    return {"role": role, "name": name, "is_dealer": is_dealer}


def _is_dealer_client(session, client_id: str) -> bool:
    """True if this client is the admin or is registered as the current dealer."""
    info = _get_client_info(session, client_id)
    return info["is_dealer"] or info.get("role") == "admin"


def _apply_queued_settings(session: RefereeSession) -> list[str]:
    """Apply any queued settings to the session before a new round starts.
    Returns a list of human-readable change descriptions."""
    queued = getattr(session, "_queued_settings", {})
    if not queued:
        return []

    changes = []

    if "wager" in queued:
        session.wager = queued["wager"]
        changes.append(f"Sips/hand set to {queued['wager']}")

    if "num_hands" in queued:
        session.num_hands = queued["num_hands"]
        changes.append(f"Hands/player set to {queued['num_hands']}")

    if "num_decks" in queued and getattr(session, "mode", "referee") == "digital":
        from blackjack import Shoe
        session.shoe = Shoe(queued["num_decks"])
        session.shoe.shuffle()
        changes.append(f"Deck count set to {queued['num_decks']}")

    for entry in queued.get("add_players", []):
        name   = entry["name"]
        is_npc = entry["is_npc"]
        if not any(p.name == name for p in session.all_players):
            p = NPC_Player(name) if is_npc else Player(name)
            p.is_dealer = False
            session.all_players.append(p)
            changes.append(f"Added {'bot' if is_npc else 'player'} {name}")

    for name in queued.get("remove_players", []):
        before = len(session.all_players)
        session.all_players = [p for p in session.all_players if p.name != name or p.is_dealer]
        if len(session.all_players) < before:
            changes.append(f"Removed player {name}")

    session._queued_settings = {}
    return changes


def _newround_rotate(session: RefereeSession):
    """Rotate the dealer role one seat clockwise."""
    all_names  = [p.name for p in session.all_players]
    cur_idx    = all_names.index(session.dealer_name)
    new_dealer = all_names[(cur_idx + 1) % len(all_names)]
    for p in session.all_players:
        p.is_dealer   = (p.name == new_dealer)
        p.dealer_hand = Hand() if p.is_dealer else None
    session.dealer_name = new_dealer
    print(f"  Dealer rotates => {new_dealer} is now dealer.")


# ---------------------------------------------------------------------------
# State serialization & turn tracking
# ---------------------------------------------------------------------------

def _play_order(session: RefereeSession):
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
    order.append(session.dealer_name)  # dealer plays their player hands last
    return order


def _hand_done(hand: Hand) -> bool:
    """True if hand cannot/should not act anymore."""
    # Split hand with only 1 card is waiting for its second card — not playable yet
    if hand.from_split and len(hand.cards) < 2:
        return True
    return hand.stood or hand.bust or hand.is_bust() or hand.is_blackjack()


def _player_done(player) -> bool:
    """True if every betting hand for this player is finished."""
    if not player.hands:
        return True
    return all(_hand_done(h) for h in player.hands)


def _current_turn(session: RefereeSession):
    """
    Whose turn is it right now?
    Returns the player name, or None if no one is up (pre-deal or dealer phase).
    Only meaningful when initial deal has happened.
    """
    # Any cards on the table?
    has_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_cards:
        return None

    for name in _play_order(session):
        p = session._get_player(name)
        if p and not _player_done(p):
            return name
    return None  # all player hands done -> dealer phase


def _round_phase(session: RefereeSession) -> str:
    """
    'pre-deal'     -> waiting for initial deal
    'playing'      -> at least one player still has an active hand
    'dealer-ready' -> all player hands done, dealer hand not yet fully revealed
    'round-over'   -> dealer has stood/busted, results assigned
    """
    dealer = session._get_dealer()
    has_player_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_player_cards:
        return "pre-deal"

    if _current_turn(session) is not None:
        return "playing"

    # Player hands all done. Has dealer hand finished?
    d_hand = dealer.dealer_hand if dealer else None
    if d_hand and (d_hand.stood or d_hand.is_bust() or d_hand.score() >= 17 or d_hand.is_blackjack()):
        # Look for any unresolved results — if all hands have a result, round is over.
        all_resolved = all(
            h.result is not None for p in session.all_players for h in p.hands
        )
        if all_resolved:
            return "round-over"
    return "dealer-ready"


def _serialize_card(card) -> dict:
    """Compact JSON for a single card."""
    return {
        "rank": card.rank.label,
        "suit": card.suit.value,   # 'hearts' | 'diamonds' | 'clubs' | 'spades'
        "symbol": card.suit.symbol,
    }


def _serialize_hand(hand: Hand, hide_double: bool = False) -> dict:
    cards = [_serialize_card(c) for c in hand.cards]
    # Doubled card is dealt face-down until dealer plays
    is_hidden_double = hide_double and hand.doubled
    if is_hidden_double and len(cards) > 0:
        cards[-1] = {"rank": "?", "suit": "hidden", "symbol": "?"}
    return {
        "cards":       cards,
        # Hide score and bust status while the doubled card is still face-down
        "score":       None if is_hidden_double else (hand.score() if hand.cards else 0),
        "stood":       hand.stood,
        "bust":        False if is_hidden_double else (hand.bust or bool(hand.cards and hand.is_bust())),
        "doubled":     hand.doubled,
        "from_split":  hand.from_split,
        "insured":     hand.insured,
        "result":      None if is_hidden_double else hand.result,
        "blackjack":   bool(hand.cards) and hand.is_blackjack(),
        "done":        _hand_done(hand),
        "can_split":   hand.can_split(),
    }


def _compute_best_play(session: "RefereeSession", turn: str | None, phase: str) -> str | None:
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
    # First non-done hand
    hand = next((h for h in player.hands if not _hand_done(h)), None)
    if not hand or not hand.cards:
        return None
    dealer_up = dealer.dealer_hand.cards[0]
    valid = ["h", "s"]
    if len(hand.cards) == 2 and not hand.doubled:
        valid.append("d")
    if hand.can_split():
        valid.append("sp")
    return NPC_Player.best_play(hand, dealer_up, valid, drinking_mode=True)


def _compute_sip_totals(session: RefereeSession) -> dict:
    """Return cumulative sip counts per player: past rounds + current round."""
    if not getattr(session, "drinking_mode", True):
        return {}
    ticker = dict(getattr(session, "_sip_ticker", {}))
    # Add current round's sips only if they haven't been harvested yet
    if not getattr(session, "_drink_log_harvested", False):
        for p in session.all_players:
            for entry in p.drink_log:
                sips = entry[0] if entry else 0
                if sips > 0:
                    ticker[p.name] = ticker.get(p.name, 0) + sips
    return ticker


def _compute_dealer_role_sips(session: RefereeSession) -> dict:
    """Return cumulative dealer-role sip counts: past rounds + current round."""
    if not getattr(session, "drinking_mode", True):
        return {}
    ticker = dict(getattr(session, "_dealer_role_ticker", {}))
    # Add current round's dealer-role sips if not yet harvested
    if not getattr(session, "_drink_log_harvested", False):
        for p in session.all_players:
            for entry in p.drink_log:
                sips = entry[0] if entry else 0
                role = entry[2] if len(entry) > 2 else "player"
                if sips > 0 and role == "dealer":
                    ticker[p.name] = ticker.get(p.name, 0) + sips
    return ticker


def _serialize_state(session: RefereeSession | None, client_id: str = "") -> dict:
    """Full snapshot for the UI."""
    if not session:
        return {"ok": False}

    _ci = _get_client_info(session, client_id) if client_id else {}

    dealer = session._get_dealer()
    phase  = _round_phase(session)
    turn   = _current_turn(session)

    hide_double = (phase != "round-over")   # reveal doubled card once round is over

    table = []
    for p in session.all_players:
        entry = {
            "name":      p.name,
            "is_dealer": p.is_dealer,
            "is_npc":    getattr(p, "is_npc", False),
            "hands":     [_serialize_hand(h, hide_double=hide_double) for h in p.hands],
            "done":      _player_done(p),
            "is_turn":   (p.name == turn),
        }
        table.append(entry)

    # Dealer hand — hide hole card while players are still acting (digital only)
    mode = getattr(session, "mode", "referee")
    d_hand_state = None
    if dealer and dealer.dealer_hand:
        d_cards = dealer.dealer_hand.cards
        if mode == "digital" and phase in ("playing", "pre-deal") and len(d_cards) >= 2:
            d_hand_state = {
                "cards":     [_serialize_card(d_cards[0]),
                              {"rank": "?", "suit": "hidden", "symbol": "?"}]
                              + [_serialize_card(c) for c in d_cards[2:]],
                "score":     "?",
                "hidden":    True,
                "blackjack": False,
                "bust":      False,
                "done":      False,
            }
        else:
            d_hand_state = {
                "cards":     [_serialize_card(c) for c in d_cards],
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
    switch          = getattr(session, "switch_this_round", None)
    rounds_td       = getattr(session, "rounds_this_dealer", 1)
    num_p           = len(session.all_players)
    suggest_rotate  = bool(switch in ("hard", "soft") or rounds_td >= num_p)
    if switch == "hard":
        rotate_reason = "Hard switch — dealer lost all hands"
    elif switch == "soft":
        rotate_reason = "Soft switch — dealer won all hands"
    elif suggest_rotate:
        rotate_reason = f"Round {rounds_td} of {num_p} — every player has been dealer"
    else:
        rotate_reason = f"Round {rounds_td} of {num_p} as dealer"

    return {
        "ok":              True,
        "round":           session.round_count,
        "dealer":          session.dealer_name,
        "players":         [p.name for p in session.all_players],
        "num_hands":       session.num_hands,
        "mode":            getattr(session, "mode", "referee"),
        "table":           table,
        "dealer_hand":     d_hand_state,
        "current_turn":    turn,
        "play_order":      _play_order(session),
        "phase":           phase,
        "drinking_mode":      getattr(session, "drinking_mode", True),
        "best_play":          _compute_best_play(session, turn, phase),
        "suggest_rotate":     suggest_rotate,
        "rotate_reason":      rotate_reason,
        "rounds_this_dealer":  rounds_td,
        "dealer_rotate_every": getattr(session, "_dealer_rotate_every", 1),
        "switch_this_round":   switch,   # None | "hard" | "soft"
        # Shared log — all players see the same entries via polling
        "log_entries":        getattr(session, "_log_entries", []),
        "log_count":          len(getattr(session, "_log_entries", [])),
        "log_version":        getattr(session, "_log_version", 0),
        # Peeked card — visible to all players in the session
        "peeked_card":        getattr(session, "_last_peeked", None),
        # Live sip ticker (drinking mode only)
        "sip_totals":        _compute_sip_totals(session),
        "sip_grand_total":   sum(_compute_sip_totals(session).values()),
        # Last completed round's sip counts per player
        "last_round_sips":     getattr(session, "_last_round_sips",   {}),
        # Detailed drink entries for the Drinks pane (name, sips, reason)
        "last_round_drinks":   getattr(session, "_last_round_drinks", []),
        # Round before last — for comparison ("this round vs last round")
        "prev_round_sips":     getattr(session, "_prev_round_sips",   {}),
        "prev_round_drinks":   getattr(session, "_prev_round_drinks", []),
        # Cumulative sips earned while acting as the dealer role (live incl. current round)
        "dealer_role_sips":    _compute_dealer_role_sips(session),
        # Pre-selected player actions and pending dealer suggestions
        "preselections":     getattr(session, "_preselections", {}),
        "suggestions":       getattr(session, "_suggestions",   {}),
        # Vote-to-kick counts visible to all players; which targets this client voted for
        "kick_votes":        {k: len(v) for k, v in getattr(session, "_kick_votes", {}).items()},
        "kick_votes_mine":   [k for k, v in getattr(session, "_kick_votes", {}).items()
                              if (_ci.get("name") or "").lower() in v],
        # Voter names per target so UI can display "Alice votes to kick Bob"
        "kick_votes_detail": {k: sorted(v) for k, v in getattr(session, "_kick_votes", {}).items()},
        # Rejoin requests — full list shown to admin; just a flag shown to the requesting client
        "rejoin_requests":   [r for r in getattr(session, "_rejoin_requests", [])
                              if _ci.get("role") == "admin"],
        "my_rejoin_pending": any(r["client_id"] == client_id
                                 for r in getattr(session, "_rejoin_requests", [])),
        # Admin's animation preference (used as default for new joiners)
        "anim_default":      getattr(session, "_anim_default", True),
        # All connected clients (for registration overlay)
        "connected_clients": [
            {"name": info.get("name"), "role": info.get("role")}
            for info in getattr(session, "_room_clients", {}).values()
            if not info.get("kicked")
        ],
        # Kicked clients — only exposed to admin so they can undo kicks
        "kicked_clients": [
            {"client_id": cid, "name": info.get("name") or ""}
            for cid, info in getattr(session, "_room_clients", {}).items()
            if info.get("kicked") and info.get("name")
        ] if _ci.get("role") == "admin" else [],
        # Per-client fields (populated only when client_id is provided)
        "my_role":           _ci.get("role"),
        "my_name":           _ci.get("name"),
        "is_dealer_client":  _ci.get("is_dealer", False) or _ci.get("role") == "admin",
        # Queued settings — applied at next newround (admin only writes; all can read pending)
        "queued_settings":   getattr(session, "_queued_settings", {}),
        # Insurance votes — pending entries visible to all players so UI can prompt
        "insurance_votes": [
            {
                "bj_player":    v["player"],
                "hand_idx":     v["hand_idx"],
                "resolved":     v["resolved"],
                "my_vote":      v["votes"].get(_ci.get("name") or "", None),
                # How many votes are cast vs. needed — lets the UI know when
                # all eligible voters have responded (without spoiling who voted how)
                "votes_cast":   len(v["votes"]),
                "votes_needed": sum(1 for p in session.all_players
                                    if p.name.lower() != v["player"].lower()),
                # Show vote counts only after resolution (no spoilers before then)
                "insure_count":  sum(1 for x in v["votes"].values() if x)     if v["resolved"] else None,
                "decline_count": sum(1 for x in v["votes"].values() if not x) if v["resolved"] else None,
            }
            for v in getattr(session, "_insurance_votes", [])
        ],
    }


# ---------------------------------------------------------------------------
# Digital mode helpers
# ---------------------------------------------------------------------------

def _deal_pending_split_cards(session: RefereeSession):
    """
    After any player action, check whether a split hand is waiting for its
    second card and its predecessor is now fully done (stood/bust/BJ).
    Deals the second card automatically so the player can immediately play it.
    Handles chain splits by looping until no more cards need to be dealt.
    """
    changed = True
    while changed:
        changed = False
        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if not (hand.from_split and len(hand.cards) == 1):
                    continue
                # Use raw done-ness of predecessor (bypass the 1-card guard in _hand_done)
                if i == 0:
                    prev_done = True
                else:
                    prev = p.hands[i - 1]
                    prev_done = (len(prev.cards) >= 2 and
                                 (prev.stood or prev.bust or
                                  prev.is_bust() or prev.is_blackjack()))
                if not prev_done:
                    continue
                card = _digital_deal_card(session, hand, p.name)
                print(f"  {p.name} hand{i+1}: second card dealt — {hand}")
                if hand.is_blackjack():
                    hand.stood = True
                    print(f"  {p.name} hand{i+1}: BLACKJACK! auto-stands.")
                    # Create an insurance vote entry for this split BJ if dealer
                    # shows Ace and one doesn't already exist for this hand.
                    dealer = session._get_dealer()
                    if (dealer and dealer.dealer_hand and dealer.dealer_hand.cards
                            and dealer.dealer_hand.cards[0].rank.label == "A"
                            and getattr(session, "drinking_mode", True)):
                        existing = next(
                            (v for v in getattr(session, "_insurance_votes", [])
                             if v["player"] == p.name and v["hand_idx"] == i),
                            None,
                        )
                        if not existing:
                            session._insurance_votes.append({
                                "player":   p.name,
                                "hand_idx": i,
                                "votes":    {},
                                "resolved": False,
                            })
                elif hand.score() == 21:
                    hand.stood = True
                    print(f"  {p.name} hand{i+1}: auto-stands at 21.")
                elif hand.is_bust():
                    hand.bust = hand.stood = True
                    hand.result = "loss"
                    print(f"  {p.name} hand{i+1}: BUST on second card!")
                changed = True
                break          # restart scan after each deal
            if changed:
                break


def _digital_get_player_hand(player, hand_label: str):
    """
    Get a player's betting hand by label, always using player.hands[idx].
    Unlike RefereeSession._get_hand, this never redirects to dealer_hand,
    so the dealer-player can still play their own betting hands.
    """
    try:
        idx = int(hand_label.lower().replace("hand", "").strip()) - 1
    except (ValueError, AttributeError):
        idx = 0
    while len(player.hands) <= idx:
        player.hands.append(Hand())
    return player.hands[idx]


def _digital_deal_card(session: RefereeSession, hand: Hand, recipient_name: str):
    """Deal one card from shoe into hand and fire ace drinking rules."""
    card     = session.shoe.deal_card()
    card_pos = len(hand.cards) + 1
    hand.cards.append(card)

    if getattr(session, "drinking_mode", True):
        all_names      = [p.name for p in session.all_players]
        dealer         = session._get_dealer()
        is_dealer_hand = (dealer is not None and hand is dealer.dealer_hand)
        # card_pos==2 on the dealer hand = the hidden hole card; defer messages
        # until _digital_dealer_turn so the ace is not spoiled in the log.
        # hand.doubled being True when _digital_deal_card is called means this
        # card is the face-down doubled card — defer for the same reason.
        # Note: on_card_dealt already mutates ace_clubs_flag directly before
        # returning, so the game-mechanic side-effect is always immediate.
        is_hole_card   = is_dealer_hand and card_pos == 2
        is_double_card = (not is_dealer_hand) and hand.doubled  # face-down doubled card
        msgs = DrinkingRules.on_card_dealt(
            card, recipient_name, card_pos,
            all_names, session.dealer_name,
            session._ace_clubs_flag,
            is_dealer_hand=is_dealer_hand,
        )
        for msg in msgs:
            r, s, reason = msg[0], msg[1], msg[2]
            if s == -1:
                # Ace-clubs credit — only ever fires for player hands, never hole card
                session._ace_credits.append(recipient_name)
                print(f"    (i) {reason}")
            elif is_hole_card or is_double_card:
                # Defer: don't print or assign drinks until the card is revealed
                # (hole card revealed at dealer turn; doubled card revealed at round-over)
                if not hasattr(session, "_deferred_hole_card_msgs"):
                    session._deferred_hole_card_msgs = []
                session._deferred_hole_card_msgs.append(msg)
            else:
                session.tracker.apply([msg])   # pass full tuple; apply() extracts optional role
    return card


def _digital_initial_deal(session: RefereeSession):
    """Deal 2 cards to every player hand and the dealer hand from the shoe."""
    session._deferred_hole_card_msgs = []   # reset for fresh deal
    dealer    = session._get_dealer()
    all_names = [p.name for p in session.all_players]

    print("\n--- Dealing ---")
    for _ in range(2):
        for p in session.all_players:
            for hand in p.hands:
                _digital_deal_card(session, hand, p.name)
        _digital_deal_card(session, dealer.dealer_hand, dealer.name)

    print(f"\n  Dealer ({dealer.name}) shows: {dealer.dealer_hand.cards[0]}, ?")
    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            tag = " (also dealer)" if p.is_dealer else ""
            print(f"  {p.name}{tag} Hand {i+1}: {hand}")
            if hand.is_blackjack():
                print(f"  *** {p.name} Hand {i+1} — BLACKJACK! ***")

    # Four-aces check after first deal (drinking mode only)
    if getattr(session, "drinking_mode", True):
        all_cards = [c for p in session.all_players for h in p.hands for c in h.cards]
        all_cards += dealer.dealer_hand.cards
        msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, "first_deal", session._four_aces_fd)
        session.tracker.apply(msgs)

    # Set up insurance vote slots if dealer shows Ace
    # Each entry: { "player": name, "hand_idx": i, "votes": {voter: bool}, "resolved": False }
    session._insurance_votes = []
    if dealer.dealer_hand.cards[0].rank.label == "A" and getattr(session, "drinking_mode", True):
        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if hand.is_blackjack():
                    session._insurance_votes.append({
                        "player":   p.name,
                        "hand_idx": i,
                        "votes":    {},      # voter_name -> True (insure) / False (decline)
                        "resolved": False,
                    })


def _digital_dealer_turn(session: RefereeSession):
    """
    Reveal dealer hole card, hit until 17+, then auto-evaluate all player
    hands and fire the relevant drinking rules.
    """
    dealer = session._get_dealer()
    d_hand = dealer.dealer_hand

    # Now that the dealer hand is revealed, apply any ace drinking rules that
    # were deferred to avoid spoiling hidden cards (dealer hole card + any
    # face-down doubled cards dealt during the round).
    deferred = getattr(session, "_deferred_hole_card_msgs", [])
    if deferred:
        session.tracker.apply(deferred)
        session._deferred_hole_card_msgs = []

    print(f"\n--- Dealer ({dealer.name}) reveals ---")
    print(f"  Full hand: {d_hand}")

    if d_hand.is_blackjack():
        print("  Dealer BLACKJACK!")
    else:
        while d_hand.score() < 17:
            card = _digital_deal_card(session, d_hand, dealer.name)
            print(f"  Dealer hits: {card}  -> {d_hand}")
        if d_hand.is_bust():
            print("  Dealer BUSTS!")
        else:
            print(f"  Dealer stands at {d_hand.score()}.")

    drinking = getattr(session, "drinking_mode", True)
    if drinking:
        session.tracker.apply(DrinkingRules.on_dealer_hand_revealed(d_hand))
        if DrinkingRules.dealer_21_five_cards(d_hand):
            print(f"\n  ★ Dealer 21 with {len(d_hand.cards)} cards — wager DOUBLED this round!")

    # Auto-evaluate every player hand
    print("\n--- Results ---")
    dealer_bj       = d_hand.is_blackjack()
    winning_hds     = []
    dealer_lost_all = True
    all_names       = [p.name for p in session.all_players]

    if dealer_bj and drinking:
        print("  ★ Dealer blackjack — auto-insurance: only net-loss sips will apply.")

    # Pass 1 — evaluate all results, collect wins/losses (no drinking events yet)
    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            if not hand.result:
                hand.result = HandEvaluator.compare(hand, d_hand)
            icon = {"win": "WIN", "loss": "LOSS", "push": "PUSH"}[hand.result]
            print(f"  {p.name} Hand {i+1}: {hand}  => {icon}")
            if hand.result == "win":
                winning_hds.append((p.name, hand))
            else:
                dealer_lost_all = False

    # Detect hard / soft dealer switch for rotation suggestion.
    # A push on ANY hand cancels both switches — all results must be uniform.
    all_results = [h.result for p in session.all_players for h in p.hands]
    hard_switch = bool(all_results) and all(r == "win"  for r in all_results)
    soft_switch = bool(all_results) and all(r == "loss" for r in all_results)
    if soft_switch:
        insured_bj = any(
            h.insured and h.is_blackjack()
            for p in session.all_players for h in p.hands
        )
        if insured_bj:
            soft_switch = False
            print("  Soft Switch suppressed — insurance on blackjack.")
    if hard_switch:
        session.switch_this_round = "hard"
        print("  >>> HARD DEALER SWITCH <<<")
    elif soft_switch:
        session.switch_this_round = "soft"
        print("  >>> SOFT DEALER SWITCH — dealer wins all, role passes <<<")
    else:
        session.switch_this_round = None

    # Pass 2 — fire drinking events now that hard_switch is known.
    # Dealer is exempt from bonus-win drinks ONLY on a hard switch.
    if drinking:
        exempt_dealer  = session.dealer_name if hard_switch else ""
        insurance_votes = getattr(session, "_insurance_votes", [])
        voted_keys      = {(v["player"], v["hand_idx"]) for v in insurance_votes}

        for p in session.all_players:
            for i, hand in enumerate(p.hands):
                if hand.is_blackjack() and (p.name, i) in voted_keys:
                    # Resolve via group vote — always, even when result is "push"
                    # (dealer BJ causes a push, but insured hands still need resolution).
                    vote = next(v for v in insurance_votes
                                if v["player"] == p.name and v["hand_idx"] == i)
                    voters        = [x for x in session.all_players if x.name != p.name]
                    insure_count  = sum(1 for v in vote["votes"].values() if v)
                    # Non-insure voters (human abstain + explicit decline + NPC default decline)
                    # all simplify to: total voters minus those who voted insure
                    decline_count = len(voters) - insure_count
                    insured       = insure_count > decline_count  # tie → decline
                    vote["resolved"] = True
                    session.tracker.apply(
                        DrinkingRules.resolve_insurance_vote(
                            p.name, hand, all_names,
                            insured=insured, dealer_bj=dealer_bj,
                            hard_switch_dealer=exempt_dealer))
                elif hand.is_blackjack() and hand.result == "win":
                    # No vote held (dealer didn't show Ace) — normal BJ bonus
                    session.tracker.apply(
                        DrinkingRules.on_blackjack(p.name, hand, all_names,
                                                   hard_switch_dealer=exempt_dealer))
                session.tracker.apply(
                    DrinkingRules.on_hand_resolved(p.name, hand, all_names,
                                                   dealer_bj=dealer_bj,
                                                   dealer_name=exempt_dealer))

        # Four-aces end-of-round check
        all_cards  = [c for p in session.all_players for h in p.hands for c in h.cards]
        all_cards += d_hand.cards
        msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, "end_of_round", session._four_aces_fd)
        session.tracker.apply(msgs)


# ---------------------------------------------------------------------------
# NPC auto-play
# ---------------------------------------------------------------------------

def _auto_play_npc_turns(session: RefereeSession):
    """
    Auto-play all consecutive NPC turns using basic strategy.
    Loops until the current turn belongs to a human player, no one
    is up, or the phase leaves 'playing'. Safety-capped at 100 steps.
    """
    for _ in range(100):
        _deal_pending_split_cards(session)
        if _round_phase(session) != "playing":
            break
        turn = _current_turn(session)
        if not turn:
            break
        player = session._get_player(turn)
        if not player or not getattr(player, "is_npc", False):
            break  # human's turn — stop

        hand = next((h for h in player.hands if not _hand_done(h)), None)
        if not hand:
            break

        hand_idx   = player.hands.index(hand)
        hand_label = f"hand{hand_idx + 1}"
        dealer     = session._get_dealer()
        dealer_up  = dealer.dealer_hand.cards[0]

        valid = ["h", "s"]
        if len(hand.cards) == 2 and not hand.doubled:
            valid.append("d")
        if hand.can_split():
            valid.append("sp")

        action = NPC_Player.best_play(
            hand, dealer_up, valid,
            drinking_mode=getattr(session, "drinking_mode", True))
        print(f"  {player.name} (NPC) {hand_label}: {action.upper()}")

        if action == "h":
            card = _digital_deal_card(session, hand, player.name)
            print(f"  {player.name} {hand_label} hits {card}: {hand}")
            if hand.is_bust():
                hand.bust = hand.stood = True
                hand.result = "loss"
                print("  BUST!")
            elif hand.score() == 21:
                hand.stood = True
                print(f"  {player.name} {hand_label}: auto-stands at 21.")

        elif action == "s":
            hand.stood = True
            print(f"  {player.name} {hand_label}: stands at {hand.score()}.")

        elif action == "d":
            hand.doubled = True
            _digital_deal_card(session, hand, player.name)
            hand.stood = True
            print(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
            if hand.is_bust():
                hand.bust = True
                hand.result = "loss"

        elif action == "sp":
            new_hand = Hand(from_split=True)
            new_hand.cards.append(hand.cards.pop())
            hand.from_split    = True
            hand.split_count  += 1
            new_hand.split_count = hand.split_count
            player.hands.insert(hand_idx + 1, new_hand)
            _digital_deal_card(session, hand, player.name)
            print(f"  {player.name} splits {hand_label}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.after_request
def no_cache(response):
    """Prevent Safari from caching JSON polling responses."""
    if response.content_type and "json" in response.content_type:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


_ROOT = os.path.dirname(os.path.abspath(__file__))

@app.route("/logo.png")
def serve_logo():
    return send_from_directory(os.path.join(_ROOT, "static"), "Logo-BlackOutJack.png")

@app.route("/manifest.json")
def serve_manifest():
    return jsonify({
        "name":             "Black-Out Jack",
        "short_name":       "Black-Out Jack",
        "start_url":        "/",
        "display":          "standalone",
        "background_color": "#0f1117",
        "theme_color":      "#0f1117",
        "icons": [
            {"src": "/logo.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/logo.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


# ---------------------------------------------------------------------------
# Lobby routes
# ---------------------------------------------------------------------------

@app.route("/create_room", methods=["POST"])
def create_room():
    code = _generate_room_code()
    game_sessions[code] = None   # slot reserved; game not yet started
    return jsonify({"ok": True, "code": code})


@app.route("/join_room", methods=["POST"])
def join_room():
    data      = request.json or {}
    raw       = (data.get("code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    # Generic error — same message whether the code is malformed or simply absent, so the response cannot be used as a room-existence oracle.
    _bad = {"ok": False, "error": "Invalid room code. Check the code and try again."}

    # Rate-limit failed join attempts per source IP to slow enumeration.
    ip   = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if _join_rate_limited(ip):
        return jsonify({"ok": False, "error": "Too many attempts. Please wait a moment."}), 429

    # Case-insensitive lookup (codes are stored as "Ace427" etc.)
    code = next((k for k in game_sessions if k.lower() == raw.lower()), None)
    if code is None:
        return jsonify(_bad)

    session  = game_sessions[code]
    has_game = session is not None
    state    = _serialize_state(session, client_id)
    state["ok"]        = True
    state["has_game"]  = has_game
    state["room_code"] = code   # return canonical casing
    return jsonify(state)


@app.route("/setup", methods=["POST"])
def setup():
    data      = request.json
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    if room_code not in game_sessions:
        return jsonify({"ok": False, "output": "Room not found."})

    # Prevent any client from overwriting an active game.
    # The admin (session creator) may reconfigure; everyone else is blocked.
    existing = game_sessions[room_code]
    if existing is not None:
        clients = getattr(existing, "_room_clients", {})
        if clients.get(client_id, {}).get("role") != "admin":
            return jsonify({"ok": False, "output": "Game already in progress."})

    names = [_sanitize_name(n) for n in data["players"] if n.strip()]
    names = [n for n in names if n]   # drop any that became empty after sanitization
    if not names:
        return jsonify({"ok": False, "output": "No player names provided."})

    mode        = data.get("mode", "referee")   # "referee" | "digital"
    dealer_idx  = int(data.get("dealer_index", 0))
    dealer_name = names[min(dealer_idx, len(names) - 1)]
    wager       = int(data.get("wager", 1))
    num_hands   = int(data.get("num_hands", 2))

    npc_names = {_sanitize_name(n) for n in data.get("npcs", []) if n.strip()}

    players = []
    for name in names:
        p           = NPC_Player(name) if name in npc_names else Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    drinking = bool(data.get("drinking", True))

    game_session                         = RefereeSession(players, dealer_name, wager, num_hands)
    game_sessions[room_code]             = game_session   # store in room slot
    game_session.mode                    = mode
    game_session.drinking_mode           = drinking
    game_session.rounds_this_dealer      = 1   # rounds the current dealer has held the role
    game_session.switch_this_round       = None  # None | "hard" | "soft"
    game_session._dealer_rotate_every    = len(players)   # rotate after N rounds (default = one full cycle through all players)
    # Shared log — broadcast to all players via /state polling
    game_session._log_entries            = []
    game_session._log_version            = 0
    game_session._deferred_hole_card_msgs = []
    # CSV accumulator — survives across rounds; never reset between newrounds
    game_session._drink_csv_rows         = []
    # Live sip ticker — cumulative across all rounds
    game_session._sip_ticker             = {}
    game_session._drink_log_harvested    = False
    game_session._last_round_sips        = {}   # per-player sips in the last completed round
    game_session._last_round_drinks      = []   # detailed drink entries for the Drinks pane
    game_session._prev_round_sips        = {}   # sips from the round before last (for comparison)
    game_session._prev_round_drinks      = []   # drinks from the round before last
    game_session._dealer_role_ticker     = {}   # cumulative sips earned while acting as dealer
    # Identity — session creator is admin, auto-registered with the dealer's name
    game_session._room_clients  = {}
    game_session._preselections = {}
    game_session._suggestions   = {}   # pending dealer→player action suggestions
    game_session._kick_votes    = {}   # {target_name_lower: set(voter_name_lower)}
    game_session._rejoin_requests = []  # [{client_id, display_name}] — kicked players asking to rejoin
    game_session._anim_default  = True # admin's animation preference, broadcast to joiners
    game_session._queued_settings = {}  # settings queued to apply at start of next round
    if client_id:
        game_session._room_clients[client_id] = {
            "name": dealer_name, "role": "admin", "kicked": False,
        }

    if mode == "digital":
        num_decks         = int(data.get("num_decks", 1))
        game_session.shoe = Shoe(num_decks)
        game_session.shoe.shuffle()

    if drinking:
        _patch_tracker(game_session)
    else:
        game_session.tracker = _NullTracker()

    output = _capture(game_session.start_round)
    if output.strip():
        game_session._log_entries.append(output)
    state  = _serialize_state(game_session, client_id)
    state["output"] = output   # kept for host's immediate display
    return jsonify(state)


@app.route("/command", methods=["POST"])
def command():
    _req         = request.json or {}
    room_code    = _req.get("room_code", "")
    game_session = game_sessions.get(room_code)
    if not game_session:
        return jsonify({"ok": False, "output": "No active session — set up a game first."})

    cmd_str = _req.get("cmd", "").strip()
    client_id = _req.get("client_id", "")
    if not cmd_str:
        return jsonify({"ok": False, "output": "Empty command."})

    parts = cmd_str.split()
    cmd   = parts[0].lower()
    mode  = getattr(game_session, "mode", "referee")

    # Turn-order gate: in digital mode, per-player actions must come from the
    # player whose turn it currently is. (deal/dealer/endround/newround/status/help
    # are session-wide and bypass the gate.)
    TURN_GATED = {"hit", "stand", "double", "split", "insurance", "blackjack"}
    if mode == "digital" and cmd in TURN_GATED and len(parts) >= 2:
        current = _current_turn(game_session)
        target  = parts[1].strip().capitalize()
        if current is None:
            return jsonify({
                **_serialize_state(game_session),
                "output": "  Not in play phase — deal cards or run dealer turn.\n",
            })
        if target.lower() != current.lower():
            return jsonify({
                **_serialize_state(game_session),
                "output": f"  Out of order — it's {current}'s turn (not {target}).\n",
            })

    # Gate the dealer-reveal command too: only allow when all players are done
    if mode == "digital" and cmd == "dealer":
        phase = _round_phase(game_session)
        if phase == "pre-deal":
            return jsonify({
                **_serialize_state(game_session),
                "output": "  Deal cards first.\n",
            })
        if phase == "playing":
            current = _current_turn(game_session) or "a player"
            return jsonify({
                **_serialize_state(game_session),
                "output": f"  Cannot reveal dealer — {current} still has hands to play.\n",
            })

    # Dealer-gate: only dealer or admin may execute game-changing commands
    DEALER_GATED_CMDS = {
        "deal", "hit", "stand", "double", "split", "insurance", "blackjack",
        "dealer", "endround", "newround", "peek", "action", "result", "fouraces",
    }
    if (cmd in DEALER_GATED_CMDS
            and getattr(game_session, "_room_clients", None)
            and not _is_dealer_client(game_session, client_id)):
        state = _serialize_state(game_session, client_id)
        state["output"] = "  Not authorised — only the dealer can do that.\n"
        return jsonify(state)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):

        # ── Digital-only commands ────────────────────────────────────────────
        if mode == "digital":

            if cmd == "deal":
                # Initial deal — no card args; shoe deals automatically
                game_session._last_peeked = None   # peeked card is now stale
                game_session._preselections = {}
                game_session._suggestions   = {}
                _digital_initial_deal(game_session)
                _auto_play_npc_turns(game_session)

            elif cmd == "hit":
                # hit <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: hit <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            card = _digital_deal_card(game_session, hand, player.name)
                            print(f"  {player.name} {hand_label} hits {card}: {hand}")
                            if hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                print("  BUST!")
                            elif hand.score() == 21:
                                hand.stood = True
                                print(f"  {player.name} {hand_label}: auto-stands at 21.")

            elif cmd == "stand":
                # stand <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: stand <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label  = parts[2] if len(parts) > 2 else "hand1"
                        hand        = _digital_get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            hand.stood  = True
                            print(f"  {player.name} {hand_label}: stands at {hand.score()}.")

            elif cmd == "double":
                # double <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: double <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if len(hand.cards) != 2:
                            print("  Can only double on first two cards.")
                        elif hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            hand.doubled = True
                            _digital_deal_card(game_session, hand, player.name)
                            hand.stood   = True
                            print(f"  {player.name} {hand_label}: doubles — card dealt face-down.")
                            if hand.is_bust():
                                hand.bust = True
                                hand.result = "loss"

            elif cmd == "split":
                # split <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: split <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if not hand.can_split():
                            # Give a specific message when the split limit is the reason
                            if (len(hand.cards) == 2
                                    and hand.cards[0].rank.blackjack_value == hand.cards[1].rank.blackjack_value
                                    and hand.split_count >= Hand.MAX_SPLITS):
                                print(f"  Max splits reached ({Hand.MAX_SPLITS} splits per hand).")
                            else:
                                print("  Cannot split this hand.")
                        else:
                            # Move second card to new hand (no second cards dealt yet)
                            new_hand = Hand(from_split=True)
                            new_hand.cards.append(hand.cards.pop())
                            hand.from_split   = True
                            hand.split_count += 1
                            new_hand.split_count = hand.split_count  # child inherits so chain limit holds
                            idx       = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
                            new_label = f"hand{idx + 2}"
                            player.hands.insert(idx + 1, new_hand)
                            # Deal second card to H1; check for instant 21/bust
                            _digital_deal_card(game_session, hand, player.name)
                            if hand.score() == 21:
                                hand.stood = True
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  (21 — auto-stands)")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            elif hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  BUST!")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")
                            else:
                                print(f"  {player.name} splits:")
                                print(f"    {hand_label}: {hand}  ← play this hand first")
                                print(f"    {new_label}: [{new_hand.cards[0]}] waiting for second card")

            elif cmd == "insurance":
                # insurance <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: insurance <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if not hand.is_blackjack():
                            print(f"  Insurance only applies when the player has a Blackjack (dealer shows Ace).")
                        else:
                            hand.insured = True
                            # Sync with the vote system: force all voters' votes to True so
                            # _digital_dealer_turn resolves this hand as insured via voted_keys.
                            hand_idx   = player.hands.index(hand)
                            vote_entry = next(
                                (v for v in getattr(game_session, "_insurance_votes", [])
                                 if v["player"] == player.name and v["hand_idx"] == hand_idx
                                 and not v.get("resolved")),
                                None,
                            )
                            if vote_entry:
                                voters = [x for x in game_session.all_players if x.name != player.name]
                                for x in voters:
                                    vote_entry["votes"][x.name] = True
                            print(f"  {player.name} {hand_label}: insured.")

            elif cmd == "blackjack":
                # blackjack <player> [hand<n>] — confirm natural BJ, fire drink rules
                if len(parts) < 2:
                    print("  Usage: blackjack <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        hand.stood = True
                        all_names  = [p.name for p in game_session.all_players]
                        game_session.tracker.apply(
                            DrinkingRules.on_blackjack(player.name, hand, all_names))
                        print(f"  {player.name} BLACKJACK confirmed.")

            elif cmd == "peek":
                # Toggle: hide peeked card if already shown, otherwise reveal it
                shoe = getattr(game_session, "shoe", None)
                if getattr(game_session, "_last_peeked", None):
                    # Already showing — toggle off
                    game_session._last_peeked = None
                    print("  Next card hidden.")
                elif shoe and shoe.cards:
                    card = shoe.cards[-1]   # pop() takes from the end
                    print(f"  Next card in shoe: {card}")
                    print(f"  ({len(shoe.cards)} cards remaining)")
                    game_session._last_peeked = _serialize_card(card)
                else:
                    print("  Shoe is empty or not available.")
                    game_session._last_peeked = None

            elif cmd == "dealer":
                # Auto-run dealer turn + evaluate all hands
                _digital_dealer_turn(game_session)

            elif cmd == "endround":
                game_session.cmd_endround()
                _harvest_drink_log(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = _apply_queued_settings(game_session)
                for msg in setting_changes:
                    print(f"  ⚙️  {msg}")
                if rotate:
                    _newround_rotate(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = getattr(game_session, "rounds_this_dealer", 0) + 1
                game_session.switch_this_round = None
                # Clear shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = getattr(game_session, "_log_version", 0) + 1
                game_session._deferred_hole_card_msgs = []
                game_session._last_peeked = None
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._drink_log_harvested = False
                game_session._kick_votes    = {}  # reset vote-kick tally each round
                if getattr(game_session, "drinking_mode", True) or game_session.shoe.needs_reshuffle():
                    game_session.shoe.reset()
                    print("  Shoe reshuffled.")
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                _print_digital_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

            # Clear the pre-selection for the player whose action just executed
            if cmd in {"hit", "stand", "double", "split"} and len(parts) >= 2:
                _p  = parts[1].strip().capitalize()
                _h  = (parts[2] if len(parts) > 2 else "hand1").strip().lower()
                if hasattr(game_session, "_preselections"):
                    game_session._preselections.pop(f"{_p.lower()}:{_h}", None)

            # After any player action: deal pending second cards to split hands
            # whose predecessor just finished, then check if dealer should auto-play
            if cmd in {"hit", "stand", "double", "split"}:
                _deal_pending_split_cards(game_session)
                _auto_play_npc_turns(game_session)
                if _round_phase(game_session) == "dealer-ready":
                    print("\n  (All players done — dealer plays automatically)")
                    _digital_dealer_turn(game_session)
                    game_session.cmd_endround()
                    _harvest_drink_log(game_session)

        # ── Referee mode (original behaviour, unchanged) ─────────────────────
        else:

            if cmd == "deal":
                game_session.cmd_deal(parts)

            elif cmd == "action":
                game_session.cmd_action(parts)

            elif cmd == "result":
                game_session.cmd_result(parts)

            elif cmd == "dealer":
                game_session.cmd_dealer(parts)

            elif cmd == "fouraces":
                game_session.cmd_fouraces(parts)

            elif cmd == "endround":
                game_session.cmd_endround()
                _harvest_drink_log(game_session)

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                # Apply queued settings before the round starts
                setting_changes = _apply_queued_settings(game_session)
                for msg in setting_changes:
                    print(f"  ⚙️  {msg}")
                if rotate:
                    _newround_rotate(game_session)
                    game_session.rounds_this_dealer = 1
                else:
                    game_session.rounds_this_dealer = getattr(game_session, "rounds_this_dealer", 0) + 1
                game_session.switch_this_round = None
                # Clear the shared log and peeked card for the new round
                game_session._log_entries = []
                game_session._log_version = getattr(game_session, "_log_version", 0) + 1
                game_session._last_peeked = None
                game_session._preselections = {}
                game_session._suggestions   = {}
                game_session._drink_log_harvested = False
                game_session._kick_votes    = {}  # reset vote-kick tally each round
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                RefereeSession.print_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    output = buf.getvalue()
    # Append to the shared log so polling clients see this output too.
    # newround already cleared _log_entries above; appending here adds the
    # new-round start text to the fresh log.
    if output.strip():
        game_session._log_entries.append(output)
    state = _serialize_state(game_session, client_id)
    state["output"] = output   # kept for immediate display on the sender's side
    # peeked_card is included in _serialize_state and persists until cleared
    # by newround/deal so all polling clients can see it.
    return jsonify(state)


@app.route("/register", methods=["POST"])
def register():
    """A joining client claims a seat or becomes spectator.
    Body: { room_code, client_id, name }  — name="" means spectator."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    name      = _sanitize_name((data.get("name") or "").strip())

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    if not hasattr(session, "_room_clients"):
        session._room_clients = {}

    existing = session._room_clients.get(client_id, {})
    if existing.get("kicked"):
        if not name:
            # Kicked player wants to spectate — allow it, clear kicked flag
            session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
            # Remove any pending rejoin request for this client
            session._rejoin_requests = [r for r in getattr(session, "_rejoin_requests", [])
                                        if r["client_id"] != client_id]
            return jsonify({**_serialize_state(session, client_id), "ok": True})
        return jsonify({"ok": False, "error": "You have been removed from this session."})

    if not name:
        session._room_clients[client_id] = {"name": None, "role": "spectator", "kicked": False}
        return jsonify({**_serialize_state(session, client_id), "ok": True})

    valid_names = [p.name for p in session.all_players]
    if name not in valid_names:
        return jsonify({"ok": False,
                        "error": f"'{name}' is not a seat. Available: {', '.join(valid_names)}"})

    for cid, info in session._room_clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == name.lower()):
            return jsonify({"ok": False, "error": f"'{name}' is already taken."})

    role = "admin" if existing.get("role") == "admin" else "player"
    session._room_clients[client_id] = {"name": name, "role": role, "kicked": False}
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/kick", methods=["POST"])
def kick():
    """Admin removes a client. Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    admin_name_lc = (admin_info.get("name") or "").lower()
    if target_name.lower() == admin_name_lc:
        return jsonify({"ok": False, "error": "Cannot kick yourself."})

    for cid, info in clients.items():
        if (cid != client_id and not info.get("kicked")
                and (info.get("name") or "").lower() == target_name.lower()):
            info["kicked"] = True
            return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})


@app.route("/undo_kick", methods=["POST"])
def undo_kick():
    """Admin reinstates a previously kicked client as a spectator.
    Body: { room_code, client_id, target_client_id }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    target_info = clients.get(target_client_id)
    if not target_info:
        return jsonify({"ok": False, "error": "Client not found."})
    if not target_info.get("kicked"):
        return jsonify({"ok": False, "error": "Player is not kicked."})

    # Reinstate as spectator — they can then request to rejoin as a player
    target_info["kicked"] = False
    target_info["role"]   = "spectator"

    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/make_bot", methods=["POST"])
def make_bot():
    """Admin converts a seated player to an NPC bot.
    Body: { room_code, client_id, player_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    player = next(
        (p for p in getattr(session, "all_players", [])
         if p.name.lower() == target_name.lower()),
        None,
    )
    if not player:
        return jsonify({"ok": False, "error": f"Player '{target_name}' not found."})
    if getattr(player, "is_npc", False):
        return jsonify({"ok": False, "error": f"'{target_name}' is already a bot."})

    player.is_npc = True

    # Disconnect the player's client connection if present
    for cid, info in list(clients.items()):
        if cid != client_id and (info.get("name") or "").lower() == target_name.lower():
            info["kicked"] = True  # marks as disconnected so poll loop drops them

    # Clear any pending preselections / suggestions for this player
    key_prefix = f"{target_name.lower()}:"
    for d in (getattr(session, "_preselections", {}), getattr(session, "_suggestions", {})):
        for k in [k for k in d if k.startswith(key_prefix)]:
            d.pop(k, None)

    # If it's the new bot's turn, auto-play immediately
    if _round_phase(session) == "playing":
        _auto_play_npc_turns(session)

    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/transfer_admin", methods=["POST"])
def transfer_admin():
    """Admin hands admin role to another connected player.
    Body: { room_code, client_id, target_name }"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Find the target client
    target_cid = next(
        (cid for cid, info in clients.items()
         if cid != client_id
         and not info.get("kicked")
         and (info.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if not target_cid:
        return jsonify({"ok": False, "error": f"No connected player named '{target_name}'."})

    # Transfer: demote old admin, promote new one
    admin_info["role"]            = "player"
    clients[target_cid]["role"]   = "admin"

    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/set_anim_pref", methods=["POST"])
def set_anim_pref():
    """Admin pushes their animation preference so new joiners inherit it.
    Body: { room_code, client_id, enabled: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    enabled   = bool(data.get("enabled", True))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    if clients.get(client_id, {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    session._anim_default = enabled
    return jsonify({"ok": True})


@app.route("/vote_kick", methods=["POST"])
def vote_kick():
    """Player casts or retracts a kick vote for a target player.
    Body: { room_code, client_id, target_name }
    Toggles the vote — calling again retracts it.
    Auto-kicks when strict majority of eligible voters agree."""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("target_name") or "").strip().capitalize()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})
    voter_name = (info.get("name") or "").lower()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote to kick."})
    if voter_name == target_name.lower():
        return jsonify({"ok": False, "error": "Cannot vote to kick yourself."})

    # Verify target exists as a connected, non-bot, non-admin player
    target_info = next(
        (v for v in clients.values()
         if not v.get("kicked") and (v.get("name") or "").lower() == target_name.lower()),
        None,
    )
    if target_info and target_info.get("role") == "admin":
        return jsonify({"ok": False, "error": "Cannot vote to kick the admin."})
    target_connected = target_info is not None
    if not target_connected:
        return jsonify({"ok": False, "error": f"'{target_name}' is not in the session."})

    if not hasattr(session, "_kick_votes"):
        session._kick_votes = {}

    key = target_name.lower()
    votes = session._kick_votes.setdefault(key, set())

    # Toggle
    if voter_name in votes:
        votes.discard(voter_name)
    else:
        votes.add(voter_name)

    # Count eligible voters: all non-kicked, named, non-bot players except the target
    all_players_lc = {
        (v.get("name") or "").lower()
        for v in clients.values()
        if not v.get("kicked") and v.get("name") and v.get("role") != "spectator"
    }
    eligible = all_players_lc - {key}  # exclude target

    # Auto-kick at strict majority
    kicked = False
    if len(eligible) > 0 and len(votes) > len(eligible) / 2:
        for cid, v in list(clients.items()):
            if (v.get("name") or "").lower() == key:
                v["kicked"] = True
        session._kick_votes.pop(key, None)
        kicked = True

    state = _serialize_state(session, client_id)
    state["ok"]    = True
    state["kicked"] = kicked
    return jsonify(state)


@app.route("/request_rejoin", methods=["POST"])
def request_rejoin():
    """Spectator (formerly kicked) asks admin to let them rejoin.
    Body: { room_code, client_id, display_name }"""
    data         = request.json or {}
    room_code    = (data.get("room_code") or "").strip()
    client_id    = (data.get("client_id") or "").strip()
    display_name = _sanitize_name((data.get("display_name") or "").strip()) or "Unknown"

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not in session."})

    requests_list = getattr(session, "_rejoin_requests", [])
    # Avoid duplicate requests
    if any(r["client_id"] == client_id for r in requests_list):
        return jsonify({**_serialize_state(session, client_id), "ok": True})

    requests_list.append({"client_id": client_id, "display_name": display_name or "Unknown"})
    session._rejoin_requests = requests_list
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/handle_rejoin", methods=["POST"])
def handle_rejoin():
    """Admin approves or denies a rejoin request.
    Body: { room_code, client_id, target_client_id, approve: bool }"""
    data             = request.json or {}
    room_code        = (data.get("room_code") or "").strip()
    client_id        = (data.get("client_id") or "").strip()
    target_client_id = (data.get("target_client_id") or "").strip()
    approve          = bool(data.get("approve", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Not authorised."})

    # Remove from rejoin requests regardless of decision
    session._rejoin_requests = [r for r in getattr(session, "_rejoin_requests", [])
                                 if r["client_id"] != target_client_id]

    if approve:
        # Remove the client entry so they get the register overlay on next poll
        clients.pop(target_client_id, None)

    state = _serialize_state(session, client_id)
    state["ok"] = True
    return jsonify(state)


@app.route("/vote_insurance", methods=["POST"])
def vote_insurance():
    """
    Player casts their insurance vote for a specific blackjack hand.
    Body: { room_code, client_id, bj_player, hand_idx, vote: true=insure/false=decline }
    Can be called multiple times — last vote wins.
    """
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    bj_player = (data.get("bj_player") or "").strip().capitalize()
    hand_idx  = int(data.get("hand_idx", 0))
    vote      = bool(data.get("vote", False))   # True = insure, False = decline

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    voter_name = (info.get("name") or "").strip()
    if not voter_name:
        return jsonify({"ok": False, "error": "Spectators cannot vote."})
    if voter_name.lower() == bj_player.lower():
        return jsonify({"ok": False, "error": "You cannot vote on your own blackjack."})

    insurance_votes = getattr(session, "_insurance_votes", [])
    vote_entry = next(
        (v for v in insurance_votes
         if v["player"].lower() == bj_player.lower() and v["hand_idx"] == hand_idx),
        None,
    )
    if not vote_entry:
        return jsonify({"ok": False, "error": "No insurance vote open for that hand."})
    if vote_entry.get("resolved"):
        return jsonify({"ok": False, "error": "This vote has already been resolved."})

    vote_entry["votes"][voter_name] = vote
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/preselect", methods=["POST"])
def preselect():
    """Player pre-votes their intended action. Dealer sees this in the UI.
    Body: { room_code, client_id, hand, action }  action: h|s|d|sp"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    action    = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered in this session."})

    name = info.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Spectators cannot pre-select actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    if not hasattr(session, "_preselections"):
        session._preselections = {}

    session._preselections[f"{name.lower()}:{hand}"] = action
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/suggest_action", methods=["POST"])
def suggest_action():
    """Dealer suggests a different action to a player.
    Body: { room_code, client_id, player_name, hand, action }  action: h|s|d|sp"""
    data        = request.json or {}
    room_code   = (data.get("room_code") or "").strip()
    client_id   = (data.get("client_id") or "").strip()
    target_name = (data.get("player_name") or "").strip().capitalize()
    hand        = (data.get("hand") or "hand1").strip().lower()
    action      = (data.get("action") or "").strip().lower()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not _is_dealer_client(session, client_id):
        return jsonify({"ok": False, "error": "Only the dealer can suggest actions."})

    if action not in ("h", "s", "d", "sp"):
        return jsonify({"ok": False, "error": f"Invalid action '{action}'."})

    if not hasattr(session, "_suggestions"):
        session._suggestions = {}

    session._suggestions[f"{target_name.lower()}:{hand}"] = action
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/respond_suggest", methods=["POST"])
def respond_suggest():
    """Player accepts or declines a dealer suggestion.
    Body: { room_code, client_id, hand, accept: bool }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    hand      = (data.get("hand") or "hand1").strip().lower()
    accept    = bool(data.get("accept", False))

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients = getattr(session, "_room_clients", {})
    info    = clients.get(client_id, {})
    if not info or info.get("kicked"):
        return jsonify({"ok": False, "error": "Not registered."})

    name = info.get("name", "")
    key  = f"{name.lower()}:{hand}"

    suggestions = getattr(session, "_suggestions", {})
    suggestion  = suggestions.get(key)
    if not suggestion:
        return jsonify({"ok": False, "error": "No pending suggestion."})

    if accept:
        if not hasattr(session, "_preselections"):
            session._preselections = {}
        session._preselections[key] = suggestion

    session._suggestions.pop(key, None)
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/export_csv")
def export_csv():
    """
    Return a CSV file of all drinks recorded so far in this session.
    Columns: round, dealer, player, role, rule, sips
    Usage: GET /export_csv?room_code=Jack-21
    """
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return Response("No active session.", status=404, mimetype="text/plain")

    rows = getattr(session, "_drink_csv_rows", [])

    # Aggregate: player_sips[player][rule] and dealer_sips[player][rule]
    player_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    dealer_sips: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    num_rounds = max((r["round"] for r in rows), default=1)
    players_seen: list[str] = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        bucket = dealer_sips if row["role"] == "dealer" else player_sips
        bucket[name][row["rule"]] += row["sips"]

    all_rules = sorted({row["rule"] for row in rows})

    # Build summary CSV
    buf = io.StringIO()
    w   = csv.writer(buf)

    # Header metadata
    w.writerow(["Drinking Blackjack — Session Summary"])
    w.writerow(["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    w.writerow(["Rounds completed", num_rounds])
    w.writerow([])

    # Per-player tables
    for name in players_seen:
        pt = sum(player_sips[name].values())
        dt = sum(dealer_sips[name].values())
        gt = pt + dt
        w.writerow([
            f"{name}",
            f"total sips: {gt}",
            f"as player: {pt}",
            f"as dealer: {dt}",
            f"sips/round: {gt/num_rounds:.2f}",
        ])
        w.writerow(["Rule", "Player sips", "Dealer sips", "Total", "Sips/round", "% of own"])
        for rule in all_rules:
            ps = player_sips[name].get(rule, 0)
            ds = dealer_sips[name].get(rule, 0)
            total = ps + ds
            if total == 0:
                continue
            pct = f"{total/gt*100:.1f}%" if gt else "—"
            w.writerow([rule, ps, ds, total, f"{total/num_rounds:.2f}", pct])
        w.writerow([])

    # Grand totals table
    rule_totals: dict[str, int] = defaultdict(int)
    for name in players_seen:
        for rule, s in player_sips[name].items():
            rule_totals[rule] += s
        for rule, s in dealer_sips[name].items():
            rule_totals[rule] += s
    grand_total = sum(rule_totals.values())

    w.writerow(["ALL PLAYERS COMBINED"])
    w.writerow(["Rule", "Total sips", "Sips/round", "% of total"])
    for rule in sorted(rule_totals, key=lambda r: -rule_totals[r]):
        total = rule_totals[rule]
        pct   = f"{total/grand_total*100:.1f}%" if grand_total else "\u2014"
        w.writerow([rule, total, f"{total/num_rounds:.2f}", pct])
    w.writerow([])
    w.writerow(["Grand total", grand_total, f"{grand_total/num_rounds:.2f} sips/round"])

    return Response(
        buf.getvalue().encode("utf-8"),
        status=200,
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="drinks_summary.csv"'},
    )


@app.route("/summary_json")
def summary_json():
    """Return session drink summary as JSON for on-screen display."""
    room_code = request.args.get("room_code", "")
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    rows       = getattr(session, "_drink_csv_rows", [])
    num_rounds = max((r["round"] for r in rows), default=0)

    player_sips: dict[str, int] = defaultdict(int)
    dealer_sips: dict[str, int] = defaultdict(int)
    players_seen: list[str]     = []

    for row in rows:
        name = row["player"]
        if name not in players_seen:
            players_seen.append(name)
        if row["role"] == "dealer":
            dealer_sips[name] += row["sips"]
        else:
            player_sips[name] += row["sips"]

    summary = []
    for name in players_seen:
        ps = player_sips[name]
        ds = dealer_sips[name]
        summary.append({"name": name, "player_sips": ps,
                         "dealer_sips": ds, "total_sips": ps + ds})
    summary.sort(key=lambda x: -x["total_sips"])

    return jsonify({"ok": True, "rounds": num_rounds, "players": summary})


@app.route("/state")
def state():
    room_code = request.args.get("room_code", "")
    client_id = request.args.get("client_id", "")
    session   = game_sessions.get(room_code)
    return jsonify(_serialize_state(session, client_id))


@app.route("/update_settings", methods=["POST"])
def update_settings():
    """Queue game settings to apply at the start of the next round (admin only)."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()
    session   = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    admin_name_lc = (admin_info.get("name") or "").lower()
    queued = getattr(session, "_queued_settings", {})

    # Validate and queue each provided setting
    if "wager" in data:
        v = int(data["wager"])
        if v >= 1:
            queued["wager"] = v

    if "num_hands" in data:
        v = int(data["num_hands"])
        if v >= 1:
            queued["num_hands"] = v

    if "num_decks" in data:
        v = int(data["num_decks"])
        if 1 <= v <= 8:
            queued["num_decks"] = v

    if "add_player" in data:
        name = str(data["add_player"]).strip().capitalize()
        is_npc = bool(data.get("add_player_npc", False))
        if name:
            adds = queued.get("add_players", [])
            if not any(a["name"] == name for a in adds):
                adds.append({"name": name, "is_npc": is_npc})
            queued["add_players"] = adds

    if "remove_player" in data:
        name = str(data["remove_player"]).strip().capitalize()
        if name:
            if name.lower() == admin_name_lc:
                return jsonify({"ok": False, "error": "Cannot remove your own seat."})
            target = next(
                (p for p in session.all_players if p.name.lower() == name.lower()),
                None,
            )
            if target and getattr(target, "is_dealer", False):
                return jsonify({"ok": False, "error": "Cannot remove the current dealer's seat."})
            removes = queued.get("remove_players", [])
            if name not in removes:
                removes.append(name)
            queued["remove_players"] = removes

    if "clear_queued" in data and data["clear_queued"]:
        queued = {}

    # dealer_rotate_every is a live setting — applied immediately, not queued
    if "dealer_rotate_every" in data:
        v = int(data["dealer_rotate_every"])
        if v >= 1:
            session._dealer_rotate_every = v

    session._queued_settings = queued
    state = _serialize_state(session, client_id)
    state["output"] = ""
    return jsonify(state)


@app.route("/rotate_dealer", methods=["POST"])
def rotate_dealer():
    """Admin immediately rotates the dealer to the next player (lobby/name order).
    Resets rounds_this_dealer to 1. Does not start a new round.
    Body: { room_code, client_id }"""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "error": "Room not found."})

    clients    = getattr(session, "_room_clients", {})
    admin_info = clients.get(client_id, {})
    if admin_info.get("role") != "admin":
        return jsonify({"ok": False, "error": "Admin only."})

    _newround_rotate(session)
    session.rounds_this_dealer = 1
    return jsonify({**_serialize_state(session, client_id), "ok": True})


@app.route("/rules")
def rules():
    """Serve the Rules.md content as plain text for frontend markdown rendering."""
    rules_path = os.path.join(os.path.dirname(__file__), "docs", "Rules.md")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"ok": True, "content": content})
    except FileNotFoundError:
        return jsonify({"ok": False, "content": "# Rules\n\nRules file not found."})
# ---------------------------------------------------------------------------
# Digital help
# ---------------------------------------------------------------------------

def _print_digital_help():
    print("""
  DIGITAL MODE COMMANDS
  =====================
  deal
      Deal initial 2 cards to all hands from the shoe.

  hit <player> [hand<n>]
      Deal one card from the shoe to that hand.
      Example: hit Rob hand1

  stand <player> [hand<n>]
      Mark the hand as stood.
      Example: stand Alice hand2

  double <player> [hand<n>]
      Double down -- deal one card then stand. Must be on first two cards.
      Example: double Rob hand1

  split <player> [hand<n>]
      Split the hand and deal one card to each resulting hand.
      Example: split Rob hand1

  insurance <player> [hand<n>]
      Mark the hand as insured (when dealer shows Ace).

  blackjack <player> [hand<n>]
      Confirm a natural blackjack and fire drinking rules.

  dealer
      Reveal the hole card, hit until 17+, then auto-evaluate all hands.

  endround
      Finalise the round -- fire end-of-round drinking rules and print summary.

  newround [rotate]
      Start a new round. Add 'rotate' to pass the dealer role clockwise.

  status
      Show current state of all hands.
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"

    print("\n  Drinking Blackjack Referee -- Web Mode")
    print(f"  Local:   http://localhost:5000")
    print(f"  iPhone:  http://{local_ip}:5000  (same WiFi)")
    print("  (Ctrl+C to stop)\n")

    app.run(host="0.0.0.0", port=5000, debug=False)