"""
engine/style_strategy.py
==========================
Style-aware strategy resolver for player-mimicry bots.

Usage::

    from engine.style_strategy import best_play_for, load_profile

    profile = load_profile("rob")   # loads engine/player_profiles/rob.json
    action  = best_play_for(profile, hand, dealer_upcard, valid_actions)

``best_play_for`` checks the player's deviation table first.  If no deviation
is found (or the spot has insufficient data), it falls back to
``strategy.best_play`` — so a bot with an empty or sparse profile is
indistinguishable from the standard basic-strategy bot.

Two optional context signals refine the lookup beyond the player's own hand:

- ``visible_cards``: every card visible table-wide right now (all hands in
  play + dealer upcard). Bucketed into a coarse "table_bias" of
  low/medium/high ten-value-and-ace density, vs. a fresh shoe's ~38% (5 of
  13 ranks). Lets a profile record e.g. "stands more on stiff hands when the
  table is already ten-rich."
- ``sibling_hands``: the player's *other* hands this round (only relevant
  after a split). Flags whether a sibling hand hasn't been dealt its second
  card yet — the signal behind a human playing an earlier split hand more
  conservatively to dodge "taking away a ten" from a hand they haven't
  even started yet.

Both are optional and additive: a deviation entry that doesn't record
``table_bias``/``sibling_awaiting_deal`` is matched on the original 5-field
key regardless of table state, so every profile written before this feature
keeps behaving exactly as before.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from engine.strategy import best_play as _basic_strategy_play, is_soft_hand

log = logging.getLogger(__name__)

# Default profile directory — relative to this file's location.
_PROFILES_DIR = Path(__file__).parent / "player_profiles"


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------

def _profiles_dir() -> Path:
    return _PROFILES_DIR


def load_profile(player_name: str, profiles_dir: Optional[Path] = None) -> dict:
    """
    Load and return the profile dict for *player_name*.

    Returns an empty profile (no deviations) if the file doesn't exist,
    so callers never need to handle a missing file specially.
    """
    directory = profiles_dir or _profiles_dir()
    path = directory / f"{player_name.lower()}.json"
    if not path.exists():
        log.warning("style_strategy: no profile found for %r at %s — "
                    "falling back to basic strategy", player_name, path)
        return {"player": player_name, "deviations": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def available_profiles(profiles_dir: Optional[Path] = None) -> list[str]:
    """Return a sorted list of player names that have a profile JSON file."""
    directory = profiles_dir or _profiles_dir()
    if not directory.exists():
        return []
    return sorted(
        p.stem for p in directory.glob("*.json")
    )


# ---------------------------------------------------------------------------
# Rank extraction
# ---------------------------------------------------------------------------

def _rank(card) -> str:
    """
    Extract the rank string from a card object or string.

    Accepts engine Card objects (with a .rank Rank-enum attribute) or raw
    strings like '7♣', 'J♦', '10♥', 'A♠'.
    """
    if hasattr(card, "rank"):
        r = card.rank
        # Rank enum: use .label ("7", "J", "A", …) not str() which gives "Rank.SEVEN"
        if hasattr(r, "label"):
            return r.label
        return str(r)
    s = str(card)
    return s[:-1] if s else ""


# ---------------------------------------------------------------------------
# Table-bias bucket
# ---------------------------------------------------------------------------

_TEN_OR_ACE_LABELS = {"10", "J", "Q", "K", "A"}


def _table_bias_bucket(visible_cards: list, low: float = 0.30, high: float = 0.45) -> str:
    """
    Coarse table-composition bucket from every card currently visible.

    Buckets the share of ten-value-or-ace cards vs. the ~38% (5 of 13 ranks)
    a fresh shoe carries: "low" (ten-poor), "medium" (near-neutral), "high"
    (ten-rich). No visible cards yields "medium" (no information).
    """
    if not visible_cards:
        return "medium"
    ten_ace = sum(1 for c in visible_cards if _rank(c) in _TEN_OR_ACE_LABELS)
    ratio = ten_ace / len(visible_cards)
    if ratio < low:
        return "low"
    if ratio > high:
        return "high"
    return "medium"


# ---------------------------------------------------------------------------
# Cross-hand (sibling split hand) signal
# ---------------------------------------------------------------------------

def _sibling_awaiting_deal(hand, sibling_hands: Optional[list]) -> bool:
    """
    True if another of the player's hands this round (from a split) hasn't
    been dealt its second card yet -- the "don't take away the ten my other
    hand might want" signal.

    _play_hand deals each split hand's second card only once the previous
    hand is fully resolved (see Hand.split()), so a sibling can never be
    caught sitting on a concrete two-card total while this hand is still
    being decided -- it's either already resolved, or still down to its
    single split-off card. That single-card state is the only one worth
    checking.
    """
    if not sibling_hands:
        return False
    return any(
        other is not hand and getattr(other, "from_split", False) and len(other.cards) < 2
        for other in sibling_hands
    )


# ---------------------------------------------------------------------------
# Dealer Lottery stake tendency
# ---------------------------------------------------------------------------

def _owed_bucket(current_owed: int) -> str:
    """
    Coarse bucket for how many sips a player currently owes this round,
    at the moment the Dealer Lottery entry window opens -- the signal a
    real human weighs (higher owed = more upside from a both-bust credit).
    """
    if current_owed <= 0:
        return "none"
    if current_owed <= 2:
        return "low"
    return "high"


def decide_dealer_lottery_stake(profile: dict, current_owed: int) -> int:
    """
    Return this profile's mined Dealer Lottery stake (0-5) for the given
    owed-sips bucket, falling back to 0 (opt out) when the profile has no
    ``lottery_stakes`` entry for that bucket -- mirrors ``best_play_for``'s
    fallback-to-basic-strategy pattern, just for a stake amount instead of
    a hand action.
    """
    bucket = _owed_bucket(current_owed)
    for entry in profile.get("lottery_stakes", []):
        if entry.get("owed_bucket") == bucket:
            return max(0, min(5, round(entry.get("avg_stake", 0))))
    return 0


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

def _build_index(profile: dict) -> tuple[dict[tuple, str], dict[tuple, str]]:
    """
    Pre-index profile deviations for O(1) lookup, split into two tiers:

    - ``full``:  keyed on the 5-field spot *plus* table_bias/sibling_
      awaiting_deal, for entries that actually recorded those dimensions.
    - ``basic``: keyed on just (hand_total, is_soft, dealer_rank, can_split,
      can_double), for entries that didn't — these apply regardless of
      table state, which is exactly how every pre-existing profile behaves.
    """
    full: dict[tuple, str] = {}
    basic: dict[tuple, str] = {}
    for d in profile.get("deviations", []):
        base_key = (
            d["hand_total"],
            d["is_soft"],
            d["dealer_upcard_rank"],
            d["can_split"],
            d["can_double"],
        )
        bias    = d.get("table_bias")
        sibling = d.get("sibling_awaiting_deal")
        if bias is not None or sibling is not None:
            full[base_key + (bias, bool(sibling))] = d["player_action"]
        else:
            basic[base_key] = d["player_action"]
    return full, basic


# Cache indices so we don't rebuild per decision. Keyed by profile identity
# (not just the "player" name field) -- two distinct profile dicts sharing a
# name would otherwise silently reuse each other's stale index.
_index_cache: dict[tuple[str, int], tuple[dict[tuple, str], dict[tuple, str]]] = {}


def _get_index(profile: dict) -> tuple[dict[tuple, str], dict[tuple, str]]:
    key = (profile.get("player", ""), id(profile))
    if key not in _index_cache:
        _index_cache[key] = _build_index(profile)
    return _index_cache[key]


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def best_play_for(profile: dict, hand, dealer_upcard,
                  valid_actions: list[str],
                  drinking_mode: bool = False,
                  visible_cards: Optional[list] = None,
                  sibling_hands: Optional[list] = None) -> str:
    """
    Return the best action for *hand* according to *profile*, falling back
    to basic strategy when no deviation is recorded for this spot.

    Parameters
    ----------
    profile:       dict returned by ``load_profile``
    hand:          engine Hand object
    dealer_upcard: engine Card object (or string) — the dealer's visible card
    valid_actions: list of legal action strings, e.g. ["h", "s", "d"]
    drinking_mode: passed through to the basic-strategy fallback
    visible_cards: every card visible table-wide (all hands in play + dealer
                   upcard), used to bucket table_bias. Omit if unknown — the
                   table-aware tier is simply skipped, same as before.
    sibling_hands: the player's other hands this round (post-split), used to
                   detect a hand pending a strong double. Omit/empty if the
                   player only has one hand.

    Returns
    -------
    One of the strings in *valid_actions*.
    """
    # Build lookup key
    try:
        total      = hand.score()
        soft       = is_soft_hand(hand)
        can_split  = "sp" in valid_actions
        can_double = "d"  in valid_actions
        d_rank     = _rank(dealer_upcard)
    except Exception as exc:
        log.warning("style_strategy: error building key (%s) — using basic strategy", exc)
        return _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode)

    index_full, index_basic = _get_index(profile)
    base_key = (total, soft, d_rank, can_split, can_double)
    fallback_action = None  # computed lazily, only if we find a deviation

    # Most specific tier first: table bias + sibling-hand signal, only
    # attempted when the caller actually supplied that context.
    if visible_cards is not None:
        bias    = _table_bias_bucket(visible_cards)
        sibling = _sibling_awaiting_deal(hand, sibling_hands)
        action  = index_full.get(base_key + (bias, sibling))
        if action is not None and action in valid_actions:
            fallback_action = _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode)
            log.debug(
                "style_strategy [%s]: table-aware deviation at %s%d vs %s "
                "(bias=%s, sibling_awaiting_deal=%s) — %s (not basic %s)",
                profile.get("player"), "soft " if soft else "hard ", total,
                d_rank, bias, sibling, action, fallback_action,
            )
            return action

    # Basic tier: applies regardless of table state.
    action = index_basic.get(base_key)
    if action is not None and action in valid_actions:
        log.debug(
            "style_strategy [%s]: deviation at %s%d vs %s — %s (not basic %s)",
            profile.get("player"), "soft " if soft else "hard ", total,
            d_rank, action,
            fallback_action or _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode),
        )
        return action

    # No deviation found (or deviation action is no longer legal) -- fall back.
    return _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode)
