"""
engine/drink_rate.py
=====================
Drink Rate Mode: per-seat multiplier on the sips a seat has to drink, so
someone drinking wine or a cocktail takes fewer sips than a beer drinker
(and anyone can opt to drink more, up to BOOSTER_MAX). See
docs/planning/DrinkTypeMode.md for the design.

Pure functions only -- no session or web imports -- so Player.add_drink can
apply it directly.
"""

import math

RATE_BEER     = 1.0
RATE_WINE     = 0.6
RATE_COCKTAIL = 0.4
RATE_DEFAULT  = RATE_BEER

DISCOUNT_RATES = (0.2, 0.4, 0.6, 0.8)      # below 1.0
BOOSTER_RATES  = (1.2, 1.4, 1.5)           # above 1.0, 1.5 is the maximum
ALLOWED_RATES  = DISCOUNT_RATES + (1.0,) + BOOSTER_RATES

PRESETS = {"beer": RATE_BEER, "wine": RATE_WINE, "cocktail": RATE_COCKTAIL}

# A booster rate's fractional sip of at least this much rounds up.
BOOSTER_ROUND_UP_FRACTION = 0.25


def normalize_rate(value) -> float | None:
    """Return `value` as one of ALLOWED_RATES, or None if it isn't one."""
    try:
        v = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    for r in ALLOWED_RATES:
        if abs(v - r) < 1e-9:
            return r
    return None


def exempt_rate(rate: float) -> float:
    """Rate applied to events that skip boosters (aces, bust vote, 666/777,
    Wild Card): a discount still applies, a booster does not."""
    return min(rate, 1.0)


def scale_sips(sips: int, rate: float) -> int:
    """Sips actually drunk for `sips` owed at `rate`.

    Discounts (rate < 1.0) always round up, so a non-zero event never drops
    below 1 sip. Boosters (rate > 1.0) round up only when the fractional
    sip is at least BOOSTER_ROUND_UP_FRACTION. The sign is preserved, so
    credits (negative sips) scale the same way as penalties.
    """
    if not sips or rate == 1.0:
        return sips
    sign = -1 if sips < 0 else 1
    x = round(abs(sips) * rate, 9)
    if rate < 1.0:
        scaled = math.ceil(x)
    else:
        base = math.floor(x)
        scaled = base + 1 if round(x - base, 9) >= BOOSTER_ROUND_UP_FRACTION else base
    return sign * max(1, scaled)


class DrinkEntry(tuple):
    """One drink_log entry. Behaves exactly like the old (sips, reason, role)
    3-tuple -- indexing, unpacking and equality all work -- but also carries
    `.raw`, the sips owed before the seat's rate was applied."""

    def __new__(cls, sips, reason, role="player", raw=None, rate=1.0):
        obj = super().__new__(cls, (sips, reason, role))
        obj.raw = sips if raw is None else raw
        obj.rate = rate   # factor actually applied (1.0 for exempt events)
        return obj
