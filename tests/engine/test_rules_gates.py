"""
"Off means off" tests for the engine rule gates (RuleToggles-Implementation §3.1, §6.2).

For each gated rule: the scenario produces drinks under FULL, and with only
that rule switched off the same scenario produces none of them. A few rules
that interact get extra cases (loss.doubled/loss.suited combo, sweep cancel,
bonus multipliers, insurance, auto-insurance, Hard Switch).
"""
import pytest

from engine.drinking_rules import DrinkingRules
from engine.referee import RefereeSession
from engine.rules_registry import FULL
from tests.conftest import make_card, make_hand, make_player

NAMES = ["Alice", "Bob", "Carol"]


def off(*ids):
    return FULL.with_changes(off=list(ids))


def card_dealt(card, recipient="Alice", is_dealer_hand=False, rules=FULL, flag=None, pos=1):
    flag = {} if flag is None else flag
    msgs = DrinkingRules.on_card_dealt(card, recipient, pos, NAMES, "Carol", flag,
                                       is_dealer_hand=is_dealer_hand, wager=1, rules=rules)
    return msgs, flag


# ---------------------------------------------------------------------------
# Aces
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("suit,name", [("C", "clubs"), ("S", "spades"), ("H", "hearts"), ("D", "diamonds")])
@pytest.mark.parametrize("seat", ["player", "dealer"])
def test_ace_rules_off_means_off(suit, name, seat):
    rule = f"ace.{name}.{seat}"
    is_dealer_hand = seat == "dealer"
    card = make_card("A", suit)
    msgs, _ = card_dealt(card, is_dealer_hand=is_dealer_hand)
    # A♣ to the dealer only sets a flag, so check output or flags below.
    msgs_off, flag_off = card_dealt(card, is_dealer_hand=is_dealer_hand, rules=off(rule))
    assert msgs_off == []
    assert flag_off == {}
    if rule != "ace.clubs.dealer":
        assert msgs


def test_ace_clubs_dealer_sets_half_protection_only_with_rule_on():
    card = make_card("A", "C")
    assert card_dealt(card, is_dealer_hand=True)[1] == {"half_protected": True}
    assert card_dealt(card, is_dealer_hand=True, rules=off("ace.clubs.dealer"))[1] == {}


def test_ace_clubs_dealer_is_off_when_hard_switch_is_off():
    card = make_card("A", "C")
    assert card_dealt(card, is_dealer_hand=True, rules=off("switch.hard"))[1] == {}


def test_ace_clubs_to_dealer_player_sets_no_protection_when_off():
    card = make_card("A", "C")
    _, flag = card_dealt(card, recipient="Carol")                       # Carol is the dealer-player
    assert flag["partial_protected"] is True
    _, flag = card_dealt(card, recipient="Carol", rules=off("ace.clubs.player"))
    assert flag == {}


def test_other_aces_are_untouched_when_one_suit_is_off():
    msgs, _ = card_dealt(make_card("A", "H"), rules=off("ace.clubs.player"))
    assert msgs


# ---------------------------------------------------------------------------
# Four Aces
# ---------------------------------------------------------------------------

FOUR_ACES = [make_card("A", s) for s in "SHDC"]


def test_four_aces_first_deal_off():
    msgs, fd = DrinkingRules.check_four_aces(FOUR_ACES, "first_deal", False, rules=FULL)
    assert msgs and fd is True
    msgs, fd = DrinkingRules.check_four_aces(FOUR_ACES, "first_deal", False,
                                             rules=off("four_aces.first_deal"))
    assert msgs == [] and fd is False   # the flag that blocks end_round is not set either


def test_four_aces_end_round_off():
    assert DrinkingRules.check_four_aces(FOUR_ACES, "end_of_round", False, rules=FULL)[0]
    assert DrinkingRules.check_four_aces(FOUR_ACES, "end_of_round", False,
                                         rules=off("four_aces.end_round"))[0] == []


def test_four_aces_end_round_fires_when_first_deal_is_off():
    msgs, _ = DrinkingRules.check_four_aces(FOUR_ACES, "end_of_round", False,
                                            rules=off("four_aces.first_deal"))
    assert msgs


# ---------------------------------------------------------------------------
# Blackjack bonus and multipliers
# ---------------------------------------------------------------------------

def test_blackjack_bonus_off():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    assert DrinkingRules.on_blackjack("Alice", hand, NAMES, wager=1)
    assert DrinkingRules.on_blackjack("Alice", hand, NAMES, wager=1, rules=off("bonus.blackjack")) == []


def test_blackjack_multipliers_off_is_flat():
    hand = make_hand(("A", "S"), ("J", "S"), result="win")   # suited + A+J + both black
    full = DrinkingRules.on_blackjack("Alice", hand, NAMES, wager=1)
    flat = DrinkingRules.on_blackjack("Alice", hand, NAMES, wager=1,
                                      rules=off("bonus.blackjack.multipliers"))
    assert {m[1] for m in full} == {8}
    assert {m[1] for m in flat} == {1}


def test_insurance_double_bonus_uses_flat_multiplier_when_off():
    hand = make_hand(("A", "S"), ("J", "S"), result="win")
    msgs = DrinkingRules.resolve_insurance_vote("Alice", hand, NAMES, insured=True, dealer_bj=False,
                                                rules=off("bonus.blackjack.multipliers"))
    assert {m[1] for m in msgs} == {2}   # 1x flat, doubled by the failed insurance


def test_insurance_vote_off_resolves_as_decline():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    voted = DrinkingRules.resolve_insurance_vote("Alice", hand, NAMES, insured=True, dealer_bj=False)
    no_vote = DrinkingRules.resolve_insurance_vote("Alice", hand, NAMES, insured=True, dealer_bj=False,
                                                   rules=off("insurance.bj_vote"))
    plain = DrinkingRules.on_blackjack("Alice", hand, NAMES)
    assert {m[1] for m in voted} == {2}
    assert no_vote == plain


def test_insurance_vote_is_off_when_blackjack_bonus_is_off():
    hand = make_hand(("A", "H"), ("K", "D"), result="win")
    msgs = DrinkingRules.resolve_insurance_vote("Alice", hand, NAMES, insured=True, dealer_bj=False,
                                                rules=off("bonus.blackjack"))
    assert msgs == []


# ---------------------------------------------------------------------------
# Auto-insurance
# ---------------------------------------------------------------------------

def _lost_hands_players():
    alice = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "H"), doubled=True, result="loss"),
                                        make_hand(("9", "D"), ("8", "H"), result="loss")])
    return [alice]


def test_auto_insurance_cap_off_falls_through_to_normal_rules():
    players = _lost_hands_players()
    capped = DrinkingRules.on_round_end(players, 1, dealer_bj=True, dealer_shows_ace=True, num_hands=2)
    assert all("auto-insurance" in m[2] for m in capped)
    normal = DrinkingRules.on_round_end(players, 1, dealer_bj=True, dealer_shows_ace=True, num_hands=2,
                                        rules=off("insurance.auto_cap"))
    assert normal and not any("auto-insurance" in m[2] for m in normal)
    assert [m[1] for m in normal if "net loss" in m[2]] == [3]   # doubled loss counts -2 again


def test_dealer_blackjack_keeps_the_five_card_handout_whatever_the_cap():
    # The handout doesn't need a win; the cap rule only limits net-loss sips.
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"), result="loss")

    def handouts(**kw):
        return [m for m in DrinkingRules.on_hand_resolved("Alice", hand, NAMES, dealer_bj=True, **kw)
                if len(m) > 3 and m[3] == "handout"]

    assert handouts() and handouts() == handouts(rules=off("insurance.auto_cap"))
    assert handouts(rules=off("five_card.player_21")) == []


def test_dealer_blackjack_keeps_the_sweep_whatever_the_cap():
    hands = [make_hand(("A", "S"), ("K", "S"), result="push"),
             make_hand(("5", "S"), ("6", "S"), ("K", "S"), result="loss")]
    expected = DrinkingRules.check_all_hands_sweep("Alice", hands, NAMES, 1, dealer_bj=False)
    assert expected
    for rules in (FULL, off("insurance.auto_cap")):
        assert DrinkingRules.check_all_hands_sweep("Alice", hands, NAMES, 1, dealer_bj=True, rules=rules) == expected


# ---------------------------------------------------------------------------
# Lost-hand extras
# ---------------------------------------------------------------------------

def _extras(rules):
    h = make_hand(("K", "S"), ("9", "S"), doubled=True, result="loss")   # doubled AND suited
    p = make_player("Alice", hands=[h])
    return DrinkingRules._extra_loss_drinks([p], 1, "", rules)


def test_lost_doubled_suited_combo_is_two_extra_sips():
    assert sum(m[1] for m in _extras(FULL)) == 2   # suited + combo; the double is in the net


def test_only_loss_doubled_on_adds_no_extra():
    assert _extras(off("loss.suited")) == []


def _net(rules):
    p = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "H"), doubled=True, result="win"),
                                    make_hand(("5", "S"), ("9", "D"), result="loss"),
                                    make_hand(("6", "S"), ("8", "H"), result="loss")])
    return DrinkingRules._net_loss_drinks([p], 1, "", rules)


def test_loss_doubled_off_scores_doubles_as_one():
    assert _net(FULL) == []                                  # doubled win +2 offsets two losses
    assert [m[1] for m in _net(off("loss.doubled"))] == [1]  # +1 - 2


def test_only_loss_suited_on_adds_one():
    assert sum(m[1] for m in _extras(off("loss.doubled"))) == 1


def test_both_loss_extras_off_adds_nothing():
    assert _extras(off("loss.doubled", "loss.suited")) == []


# ---------------------------------------------------------------------------
# Other players' results
# ---------------------------------------------------------------------------

def _sweeper_round():
    alice = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "H"), result="win"),
                                        make_hand(("K", "D"), ("8", "H"), result="win")])
    bob = make_player("Bob", hands=[make_hand(("K", "C"), ("5", "H"), result="loss")])
    return [alice, bob]


def test_wins_all_off():
    assert any("swept all hands" in m[2] for m in DrinkingRules.on_round_end(_sweeper_round(), 1))
    assert not any("swept all hands" in m[2]
                   for m in DrinkingRules.on_round_end(_sweeper_round(), 1, rules=off("others.wins_all")))


def test_immunity_split_off():
    def split_round():
        alice = make_player("Alice", hands=[make_hand(("9", "S"), ("9", "H"), result="win"),
                                            make_hand(("9", "D"), ("9", "C"), result="win", from_split=True),
                                            make_hand(("8", "D"), ("9", "C"), result="win", from_split=True)])
        bob = make_player("Bob", hands=[make_hand(("K", "C"), ("5", "H"), result="loss")])
        return [alice, bob]
    assert any("split hand" in m[2] for m in DrinkingRules.on_round_end(split_round(), 1))
    assert not any("split hand" in m[2]
                   for m in DrinkingRules.on_round_end(split_round(), 1, rules=off("others.immunity.split")))


def test_immunity_doubled_off():
    hand = make_hand(("K", "S"), ("9", "H"), doubled=True, result="win")
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES)
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES, rules=off("others.immunity.doubled")) == []


def test_immunity_suited_off():
    hand = make_hand(("K", "S"), ("9", "S"), result="win")
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES)
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES, rules=off("others.immunity.suited")) == []


# ---------------------------------------------------------------------------
# 5+ cards
# ---------------------------------------------------------------------------

def test_five_card_player_21_handout_off():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"), result="loss")
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES)
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES, rules=off("five_card.player_21")) == []


def test_five_card_player_win_off():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("6", "H"), result="win")
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES)
    assert DrinkingRules.on_hand_resolved("Alice", hand, NAMES, rules=off("five_card.player_win")) == []


def test_dealer_five_card_21_off():
    hand = make_hand(("2", "H"), ("3", "D"), ("4", "C"), ("5", "S"), ("7", "H"))
    assert DrinkingRules.dealer_21_five_cards(hand) is True
    assert DrinkingRules.dealer_21_five_cards(hand, off("five_card.dealer_21")) is False


# ---------------------------------------------------------------------------
# Sweeps and dealer suited hand
# ---------------------------------------------------------------------------

def _sweep(rules, hands):
    return DrinkingRules.check_all_hands_sweep("Alice", hands, NAMES, 1, rules=rules)


def test_sweep_same_suit_off():
    hands = [make_hand(("9", "S"), ("7", "S")), make_hand(("8", "S"), ("6", "S"))]
    assert _sweep(FULL, hands)
    assert _sweep(off("sweep.same_suit"), hands) == []


def test_sweep_all_21_off():
    hands = [make_hand(("9", "H"), ("7", "D"), ("5", "C")),
             make_hand(("8", "S"), ("6", "H"), ("7", "C"))]
    assert _sweep(FULL, hands)
    assert _sweep(off("sweep.all_21"), hands) == []


def test_sweep_with_only_all_21_on_pays_the_all_21_amount_for_a_suited_hand():
    hands = [make_hand(("9", "H"), ("7", "H"), ("5", "H")), make_hand(("8", "H"), ("6", "H"), ("7", "H"))]
    assert {m[1] for m in _sweep(FULL, hands)} == {6}
    assert {m[1] for m in _sweep(off("sweep.same_suit"), hands)} == {2}


def test_sweep_cancel_is_not_emitted_when_immunity_doubled_is_off():
    hands = [make_hand(("9", "S"), ("7", "D"), ("5", "C"), doubled=True, result="win"),
             make_hand(("8", "S"), ("6", "H"), ("7", "C"), result="win")]
    assert any(m[1] < 0 for m in _sweep(FULL, hands))
    assert not any(m[1] < 0 for m in _sweep(off("others.immunity.doubled"), hands))


def test_dealer_suited_hand_off():
    hand = make_hand(("9", "S"), ("7", "S"))
    assert DrinkingRules.on_dealer_hand_revealed(hand)
    assert DrinkingRules.on_dealer_hand_revealed(hand, rules=off("dealer.suited_hand")) == []


# ---------------------------------------------------------------------------
# Hard Switch
# ---------------------------------------------------------------------------

def test_hard_switch_penalty_off():
    winning = [("Alice", make_hand(("K", "S"), ("9", "H"), result="win"))]
    assert DrinkingRules.on_hard_dealer_switch("Bob", winning)
    assert DrinkingRules.on_hard_dealer_switch("Bob", winning, rules=off("switch.hard")) == []


def _heads_up_hard_switch(rules):
    """Alice wins a doubled hand; the dealer-player Bob wins his own hand too,
    so the dealer lost every hand: a Hard Switch."""
    alice = make_player("Alice", hands=[make_hand(("K", "S"), ("9", "H"), doubled=True, result="win")])
    bob = make_player("Bob", is_dealer=True, dealer_hand=make_hand(("5", "S"), ("Q", "D")),
                      hands=[make_hand(("K", "H"), ("9", "D"), result="win")])
    session = RefereeSession([bob, alice], "Bob", wager=1, num_hands=1, verbose=False)
    session.rules = rules
    # Buffer the per-hand results the way the live commands do.
    session.cmd_result(["result", "Alice", "win", "hand1"])
    session.cmd_result(["result", "Bob", "win", "hand1"])
    session.cmd_endround()
    return bob


def test_hard_switch_off_dealer_drinks_ordinary_player_sips_instead():
    on = _heads_up_hard_switch(FULL)
    assert any("Hard Dealer Switch" in r for _, r, _ in on.drink_log)
    assert on.drinks_owed() == 3                       # 2 (doubled win) + 1 (own win); immunity break exempt

    off_ = _heads_up_hard_switch(off("switch.hard"))
    assert not any("Hard Dealer Switch" in r for _, r, _ in off_.drink_log)
    assert off_.drinks_owed() == 1                     # only the doubled-win immunity break, like any player
