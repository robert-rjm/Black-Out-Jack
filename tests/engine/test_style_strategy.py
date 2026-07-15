"""
tests/engine/test_style_strategy.py
====================================
Covers engine/style_strategy.py: basic deviation lookup, backward-compat
for legacy (pre-table-aware) profiles, and the two new context signals --
table_bias (visible ten/ace density) and sibling_awaiting_deal (a split
sibling hand that hasn't been dealt its second card yet).
"""

from engine.style_strategy import best_play_for, _table_bias_bucket, _sibling_awaiting_deal
from tests.conftest import make_card, make_hand


def _profile(deviations):
    return {"player": "Test", "deviations": deviations}


# ---------------------------------------------------------------------------
# Backward compatibility -- legacy entries (no table_bias/sibling fields)
# ---------------------------------------------------------------------------

def test_legacy_deviation_matches_regardless_of_table_state():
    """A pre-existing profile entry (no table_bias/sibling_awaiting_deal)
    must keep matching no matter what table context is passed in -- existing
    profiles like rob.json/david.json must behave identically to before."""
    profile = _profile([{
        "hand_total": 13, "is_soft": False, "dealer_upcard_rank": "7",
        "can_split": False, "can_double": True, "player_action": "s",
    }])
    hand = make_hand(("6", "S"), ("7", "H"))
    dealer_up = make_card("7", "D")
    valid = ["h", "s", "d"]

    # No context supplied at all.
    assert best_play_for(profile, hand, dealer_up, valid) == "s"

    # Context supplied but irrelevant to a legacy entry -- still matches.
    ten_rich = [make_card(r, "S") for r in ("10", "J", "Q", "K", "A")]
    assert best_play_for(profile, hand, dealer_up, valid, visible_cards=ten_rich) == "s"


def test_falls_back_to_basic_strategy_when_no_deviation_recorded():
    profile = _profile([])
    hand = make_hand(("6", "S"), ("7", "H"))
    dealer_up = make_card("7", "D")
    assert best_play_for(profile, hand, dealer_up, ["h", "s", "d"]) in ("h", "s", "d")


# ---------------------------------------------------------------------------
# Table-bias bucket
# ---------------------------------------------------------------------------

def test_table_bias_bucket_thresholds():
    assert _table_bias_bucket([]) == "medium"  # no info -> neutral

    low = [make_card("4", "S"), make_card("5", "H"), make_card("6", "D"), make_card("2", "C")]
    assert _table_bias_bucket(low) == "low"

    high = [make_card("10", "S"), make_card("J", "H"), make_card("A", "D")]
    assert _table_bias_bucket(high) == "high"

    medium = [make_card("10", "S"), make_card("4", "H"), make_card("5", "D")]
    assert _table_bias_bucket(medium) == "medium"


def test_deviation_only_applies_in_its_recorded_table_bias_bucket():
    profile = _profile([{
        "hand_total": 13, "is_soft": False, "dealer_upcard_rank": "7",
        "can_split": False, "can_double": True, "player_action": "h",
        "table_bias": "high", "sibling_awaiting_deal": False,
    }])
    hand = make_hand(("6", "S"), ("7", "H"))
    dealer_up = make_card("7", "D")
    valid = ["h", "s", "d"]

    ten_rich = [make_card(r, "S") for r in ("10", "J", "Q", "K", "A")]
    assert best_play_for(profile, hand, dealer_up, valid, visible_cards=ten_rich) == "h"

    ten_poor = [make_card("4", "S"), make_card("5", "H"), make_card("6", "D")]
    # bucket is "low" here, not "high" -- the table-aware entry shouldn't
    # match, so this falls through to basic strategy instead.
    from engine.strategy import best_play as basic_play
    assert best_play_for(profile, hand, dealer_up, valid, visible_cards=ten_poor) == \
        basic_play(hand, dealer_up, valid, False)


# ---------------------------------------------------------------------------
# Sibling (cross-hand) signal
# ---------------------------------------------------------------------------

def test_sibling_awaiting_deal_true_for_undealt_split_sibling():
    hand    = make_hand(("6", "S"), ("7", "H"))                    # hard 13, hand 1
    sibling = make_hand(("6", "D"), from_split=True)                # 1 card, hand 2 -- not dealt yet
    assert _sibling_awaiting_deal(hand, [hand, sibling]) is True


def test_sibling_awaiting_deal_false_when_sibling_already_dealt_and_played():
    hand    = make_hand(("6", "S"), ("7", "H"))
    sibling = make_hand(("6", "D"), ("5", "C"), from_split=True, stood=True)  # 2 cards, resolved
    assert _sibling_awaiting_deal(hand, [hand, sibling]) is False


def test_sibling_awaiting_deal_false_when_no_siblings():
    hand = make_hand(("6", "S"), ("7", "H"))
    assert _sibling_awaiting_deal(hand, None) is False
    assert _sibling_awaiting_deal(hand, []) is False


def test_deviation_only_applies_when_sibling_signal_matches():
    """The 'don't take away the ten my split hand might want' spot: stand on
    a hard 13 instead of hitting, but only while a sibling hand genuinely
    hasn't been dealt its second card yet."""
    profile = _profile([{
        "hand_total": 13, "is_soft": False, "dealer_upcard_rank": "7",
        "can_split": False, "can_double": True, "player_action": "s",
        "table_bias": "medium", "sibling_awaiting_deal": True,
    }])
    dealer_up = make_card("7", "D")
    valid = ["h", "s", "d"]
    medium_visible = [make_card("10", "S"), make_card("4", "H"), make_card("5", "D")]

    hand1   = make_hand(("6", "S"), ("7", "H"))          # hard 13
    sibling = make_hand(("6", "D"), from_split=True)      # 1 card, undealt sibling

    # Sibling genuinely hasn't been dealt yet -> deviation fires.
    assert best_play_for(
        profile, hand1, dealer_up, valid,
        visible_cards=medium_visible, sibling_hands=[hand1, sibling],
    ) == "s"

    # No sibling in play -> falls through to basic strategy instead.
    from engine.strategy import best_play as basic_play
    assert best_play_for(
        profile, hand1, dealer_up, valid,
        visible_cards=medium_visible, sibling_hands=None,
    ) == basic_play(hand1, dealer_up, valid, False)
