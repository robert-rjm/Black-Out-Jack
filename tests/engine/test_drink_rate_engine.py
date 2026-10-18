"""Unit tests for engine/drink_rate.py and Player.add_drink's use of it."""

import pytest

from engine.blackjack import Player, NPC_Player
from engine.drink_rate import (
    ALLOWED_RATES, DrinkEntry, PRESETS, normalize_rate, scale_sips,
)


@pytest.mark.parametrize("rate, expected", [
    (0.2, [1, 1, 1, 1, 1, 2, 2, 2]),
    (0.4, [1, 1, 2, 2, 2, 3, 3, 4]),
    (0.6, [1, 2, 2, 3, 3, 4, 5, 5]),
    (0.8, [1, 2, 3, 4, 4, 5, 6, 7]),
    (1.0, [1, 2, 3, 4, 5, 6, 7, 8]),
])
def test_discount_rounds_up_and_never_below_one(rate, expected):
    assert [scale_sips(n, rate) for n in range(1, 9)] == expected


@pytest.mark.parametrize("rate, expected", [
    (1.2, [1, 3, 4, 5, 6]),
    (1.4, [2, 3, 4, 6, 7]),
    (1.5, [2, 3, 5, 6, 8]),
])
def test_booster_rounds_up_from_a_quarter_sip(rate, expected):
    assert [scale_sips(n, rate) for n in range(1, 6)] == expected


def test_credits_scale_symmetrically():
    assert scale_sips(-1, 0.4) == -1
    assert scale_sips(-2, 1.5) == -3
    assert scale_sips(-5, 0.6) == -3


def test_zero_and_default_rate_are_untouched():
    assert scale_sips(0, 0.6) == 0
    assert scale_sips(7, 1.0) == 7


def test_normalize_rate_accepts_only_allowed_values():
    assert normalize_rate("0.6") == 0.6
    assert normalize_rate(1) == 1.0
    assert normalize_rate(1.5) == 1.5
    assert normalize_rate(0.5) is None
    assert normalize_rate(1.6) is None
    assert normalize_rate(0.1) is None
    assert normalize_rate("wine") is None
    assert set(PRESETS.values()) <= set(ALLOWED_RATES)


def test_presets():
    assert PRESETS == {"beer": 1.0, "wine": 0.6, "cocktail": 0.4}


def test_drink_entry_is_a_drop_in_three_tuple():
    e = DrinkEntry(2, "why", "player", raw=3)
    sips, reason, role = e            # unpacking still works
    assert (sips, reason, role) == (2, "why", "player")
    assert e[0] == 2 and e == (2, "why", "player")
    assert e.raw == 3
    assert DrinkEntry(2, "why").raw == 2


def test_add_drink_applies_effective_rate_and_keeps_raw():
    p = Player("Bob")
    p.effective_drink_rate = 0.6
    p.add_drink(3, "loss", "player")
    assert p.drink_log[0][0] == 2
    assert p.drink_log[0].raw == 3


def test_add_drink_default_rate_is_unchanged():
    p = Player("Bob")
    p.add_drink(3, "loss")
    assert p.drink_log == [(3, "loss", "player")]
    assert p.drink_log[0].raw == 3


def test_add_drink_scales_credits():
    p = Player("Bob")
    p.effective_drink_rate = 1.5
    p.add_drink(-2, "credit")
    assert p.drink_log[0][0] == -3 and p.drink_log[0].raw == -2


def test_npc_player_inherits_rate_support():
    b = NPC_Player("Bot")
    b.effective_drink_rate = 0.4
    b.add_drink(4, "loss")
    assert b.drink_log[0][0] == 2
