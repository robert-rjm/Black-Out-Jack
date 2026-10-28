"""
"Off means off" tests for the app-layer rule gates (RuleToggles-Implementation §3.2, §3.3).
"""
import pytest

from engine.blackjack import Card, Hand, NPC_Player, Player, Rank, Shoe, Suit
from engine.referee import RefereeSession
from engine.rules_registry import DEFAULT_RULES, FULL
from app.models.game_room import GameConfig, GameRoom
from app.services.dealer_lottery import check_dealer_lottery_trigger
from app.services.drink_tracker import check_and_set_milestone
from app.services.game_engine import _check_table_number, dealer_turn
from app.services.stats import compute_mandatory_split10, compute_mandatory_split_aces
from app.services.targeted_drinking import propose_targeted_drinking_target, start_targeted_drinking
from tests.conftest import make_card, make_hand, make_player


def off(*ids):
    return FULL.with_changes(off=list(ids))


def make_room(rules=FULL, players=3, dealer_hand=None):
    names = ["Alice", "Bob", "Carol"][:players]
    ps = [make_player(n) for n in names]
    ps[0].is_dealer = True
    ps[0].dealer_hand = dealer_hand if dealer_hand is not None else make_hand()
    raw = RefereeSession(ps, "Alice", wager=1, num_hands=1)
    return GameRoom(session=raw, config=GameConfig(mode="digital", drinking_mode=True, rules=rules))


def test_room_hands_its_rules_to_the_engine_session():
    room = make_room(off("switch.hard"))
    assert room.session.rules is room.config.rules
    room.bust_vote_enabled = True
    assert room.session.rules is room.config.rules and room.session.rules.on("side.bust_vote")


# ---------------------------------------------------------------------------
# Mandatory splits
# ---------------------------------------------------------------------------

def _pair_room(rules, rank_a, suit_a, rank_b, suit_b):
    room = make_room(rules)
    bob = room.session._get_player("Bob")
    bob.hands = [make_hand((rank_a, suit_a), (rank_b, suit_b))]
    return room


def test_split_tens_gate():
    assert compute_mandatory_split10(_pair_room(FULL, "K", "S", "Q", "H"), "Bob", "playing") is True
    assert compute_mandatory_split10(_pair_room(off("table.split_tens"), "K", "S", "Q", "H"),
                                     "Bob", "playing") is False


def test_split_aces_gate():
    assert compute_mandatory_split_aces(_pair_room(FULL, "A", "S", "A", "H"), "Bob", "playing") is True
    assert compute_mandatory_split_aces(_pair_room(off("table.split_aces"), "A", "S", "A", "H"),
                                        "Bob", "playing") is False


def test_each_split_gate_leaves_the_other_alone():
    room = _pair_room(off("table.split_tens"), "A", "S", "A", "H")
    assert compute_mandatory_split_aces(room, "Bob", "playing") is True


def test_bots_and_hints_stand_on_tens_when_split_tens_is_off():
    hand = make_hand(("K", "S"), ("Q", "H"))
    up = make_card("6", "D")
    assert NPC_Player.best_play(hand, up, ["h", "s", "d", "sp"], drinking_mode=True) == "sp"
    assert NPC_Player.best_play(hand, up, ["h", "s", "d", "sp"], drinking_mode=True, split_tens=False) == "s"
    bot = NPC_Player("Bot")
    assert bot.decide(hand, up, ["h", "s", "d", "sp"], drinking_mode=True, split_tens=False) == "s"


# ---------------------------------------------------------------------------
# Devil's Hand / Lucky Sevens
# ---------------------------------------------------------------------------

def _three_of(room, rank, suit_names=("H", "D", "C")):
    for i, s in enumerate(suit_names):
        _check_table_number(room, make_card(rank, s), "Bob", i + 1)
    return room


def test_devils_hand_off():
    assert _three_of(make_room(), "6").round._six_curse_fired is True
    assert _three_of(make_room(off("cards.devils_hand")), "6").round._six_curse_fired is False


def test_lucky_sevens_off():
    assert _three_of(make_room(), "7").round._seven_lucky_fired is True
    assert _three_of(make_room(off("cards.lucky_sevens")), "7").round._seven_lucky_fired is False


def test_devils_hand_off_leaves_lucky_sevens_working():
    assert _three_of(make_room(off("cards.devils_hand")), "7").round._seven_lucky_fired is True


# ---------------------------------------------------------------------------
# Milestones, L badge, lottery, targeted drinking
# ---------------------------------------------------------------------------

def _milestone_room(rules):
    room = make_room(rules)
    room.drinks.sip_ticker = {"Bob": 55}
    room.drinks.last_round_sips = {"Bob": 55}
    check_and_set_milestone(room)
    return room


def test_milestone_handout_off():
    assert _milestone_room(FULL).round._pending_milestone is not None
    room = _milestone_room(off("milestone.handout"))
    assert room.round._pending_milestone is None
    assert room.drinks.sip_ticker == {"Bob": 55}          # the ticker still counts


def test_lottery_trigger_off():
    pair = make_hand(("9", "S"), ("9", "H"))
    room = make_room(FULL, dealer_hand=pair)
    check_dealer_lottery_trigger(room)
    assert room.round._dealer_lottery_eligible is True
    room = make_room(off("event.dealer_lottery"), dealer_hand=pair)
    check_dealer_lottery_trigger(room)
    assert room.round._dealer_lottery_eligible is False


def test_targeted_drinking_off_blocks_every_entry_point():
    assert start_targeted_drinking(make_room(), ["Bob"]) is True
    room = make_room(off("event.targeted"))
    assert start_targeted_drinking(room, ["Bob"]) is False
    ok, reason = propose_targeted_drinking_target(room, "Carol", "Bob")
    assert ok is False and "switched off" in reason


def test_l_badge_off_clears_the_badge_without_a_hand_off_sip():
    from app.services.drink_tracker import _update_worst_streak_holder
    room = make_room(off("streak.l_badge"))
    room.stats.worst_streak_holder = "Bob"
    room.stats.streaks = {"Bob": {"current": -5}, "Carol": {"current": -6}}
    _update_worst_streak_holder(room)
    assert room.stats.worst_streak_holder is None
    assert room.session._get_player("Bob").drinks_owed() == 0


# ---------------------------------------------------------------------------
# Hard Switch in the web engine: the role still rotates, the penalty is gone
# ---------------------------------------------------------------------------

def _hard_switch_room(rules):
    def hand(*cards):
        h = Hand()
        for r, s in cards:
            h.cards.append(Card(getattr(Rank, r), getattr(Suit, s)))
        h.stood = True
        return h
    alice = Player("Alice")
    alice.hands = [hand(("KING", "SPADES"), ("NINE", "HEARTS"))]
    bob = Player("Bob")
    bob.is_dealer = True
    bob.dealer_hand = hand(("FIVE", "SPADES"), ("FIVE", "DIAMONDS"))
    raw = RefereeSession([bob, alice], "Bob", wager=1, num_hands=1)
    room = GameRoom(session=raw, config=GameConfig(mode="digital", drinking_mode=True, rules=rules))
    room.shoe = Shoe(1)
    room.shoe.cards = [Card(Rank.SEVEN, Suit.SPADES)]
    room.shoe.penetration = 1.0
    room.shoe.total_cards = len(room.shoe.cards)
    dealer_turn(room)
    return room


def test_hard_switch_on_charges_the_dealer_and_rotates():
    room = _hard_switch_room(FULL)
    assert room.round.switch_this_round == "hard"
    assert any("Hard Dealer Switch" in m[2] for m in room.round._eor_msgs_buffer)


def test_hard_switch_off_still_rotates_but_charges_nothing():
    room = _hard_switch_room(off("switch.hard"))
    assert room.round.switch_this_round == "hard"
    assert not any("Hard Dealer Switch" in m[2] for m in room.round._eor_msgs_buffer)
    assert room.session._hard_switch_drinking_applied is False


def test_default_room_keeps_todays_behaviour():
    room = _hard_switch_room(DEFAULT_RULES)
    assert any("Hard Dealer Switch" in m[2] for m in room.round._eor_msgs_buffer)
