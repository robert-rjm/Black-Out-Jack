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
"""

from __future__ import annotations

import json
import logging
import os
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
# Lookup
# ---------------------------------------------------------------------------

def _build_index(profile: dict) -> dict[tuple, str]:
    """
    Pre-index profile deviations for O(1) lookup.

    Key: (hand_total, is_soft, dealer_rank, can_split, can_double)
    Value: player_action string
    """
    index = {}
    for d in profile.get("deviations", []):
        key = (
            d["hand_total"],
            d["is_soft"],
            d["dealer_upcard_rank"],
            d["can_split"],
            d["can_double"],
        )
        index[key] = d["player_action"]
    return index


# Cache indices so we don't rebuild per decision.
_index_cache: dict[str, dict[tuple, str]] = {}


def _get_index(profile: dict) -> dict[tuple, str]:
    player = profile.get("player", "")
    if player not in _index_cache:
        _index_cache[player] = _build_index(profile)
    return _index_cache[player]


# ---------------------------------------------------------------------------
# Main resolver
# ---------------------------------------------------------------------------

def best_play_for(profile: dict, hand, dealer_upcard,
                  valid_actions: list[str],
                  drinking_mode: bool = False) -> str:
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

    index = _get_index(profile)
    key   = (total, soft, d_rank, can_split, can_double)
    action = index.get(key)

    if action is not None and action in valid_actions:
        log.debug(
            "style_strategy [%s]: deviation at %s%d vs %s — %s (not basic %s)",
            profile.get("player"), "soft " if soft else "hard ", total,
            d_rank, action,
            _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode),
        )
        return action

    # No deviation found (or deviation action is no longer legal) -- fall back.
    return _basic_strategy_play(hand, dealer_upcard, valid_actions, drinking_mode)
