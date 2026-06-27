"""
Tests for DrinkTracker — engine/drinking_rules.py
"""

import math
import pytest

from engine.drinking_rules import DrinkTracker
from tests.conftest import make_player


def _tracker(players, dealer=None, verbose=False):
    return DrinkTracker(players, dealer or players[0], verbose=verbose)


# ---------------------------------------------------------------------------
# _resolve
# ---------------------------------------------------------------------------

def test_resolve_all_includes_dealer_player():
    alice = make_player("Alice")
    bob = make_player("Bob", is_dealer=True)
    t = _tracker([alice, bob], dealer=bob)
    assert t._resolve("all") == [alice, bob]


def test_resolve_players_only_excludes_dealer():
    alice = make_player("Alice")
    bob = make_player("Bob", is_dealer=True)
    t = _tracker([alice, bob], dealer=bob)
    assert t._resolve("players_only") == [alice]


def test_resolve_exact_name_case_insensitive():
    alice = make_player("Alice")
    bob = make_player("Bob")
    t = _tracker([alice, bob])
    assert t._resolve("aLiCe") == [alice]


def test_resolve_unknown_name_empty():
    alice = make_player("Alice")
    t = _tracker([alice])
    assert t._resolve("Zach") == []


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_none_recipient_no_drink():
    alice = make_player("Alice")
    t = _tracker([alice])
    t.apply([(None, 0, "info only")])
    assert alice.drink_log == []


def test_apply_zero_sips_no_drink():
    alice = make_player("Alice")
    t = _tracker([alice])
    t.apply([("Alice", 0, "no-op")])
    assert alice.drink_log == []


def test_apply_negative_sips_handout_role_routes_to_handle_handout(monkeypatch):
    alice = make_player("Alice")
    bob = make_player("Bob")
    t = _tracker([alice, bob])
    called = {}

    def fake_handle_handout(giver, total, reason):
        called["args"] = (giver, total, reason)

    monkeypatch.setattr(t, "_handle_handout", fake_handle_handout)
    t.apply([("Alice", -3, "handout reason", "handout")])
    assert called["args"] == ("Alice", 3, "handout reason")
    assert alice.drink_log == []  # no direct drink applied


def test_apply_negative_sips_non_handout_is_direct_credit():
    alice = make_player("Alice")
    t = _tracker([alice])
    t.apply([("Alice", -1, "Sweep cancels doubled-hand drink for Alice")])
    assert alice.drink_log == [(-1, "Sweep cancels doubled-hand drink for Alice", "player")]


def test_apply_positive_sips_default_role_player():
    alice = make_player("Alice")
    t = _tracker([alice])
    t.apply([("Alice", 2, "some reason")])
    assert alice.drink_log == [(2, "some reason", "player")]


def test_apply_positive_sips_dealer_role():
    alice = make_player("Alice", is_dealer=True)
    t = _tracker([alice], dealer=alice)
    t.apply([("Alice", 1, "dealer reason", "dealer")])
    assert alice.drink_log == [(1, "dealer reason", "dealer")]


# ---------------------------------------------------------------------------
# apply_end_of_round
# ---------------------------------------------------------------------------

def test_apply_end_of_round_under_4_players_no_halving():
    alice = make_player("Alice")
    bob = make_player("Bob")
    carol = make_player("Carol")
    t = _tracker([alice, bob, carol])
    t.apply_end_of_round([("Alice", 3, "reason")])
    assert alice.drinks_owed() == 3
    assert not any("halving" in e[1] for e in alice.drink_log)


@pytest.mark.parametrize("gained,expected_credit", [(1, 0), (2, 1), (3, 1), (5, 2)])
def test_apply_end_of_round_4plus_players_halving(gained, expected_credit):
    players = [make_player(n) for n in ["Alice", "Bob", "Carol", "Dave"]]
    t = _tracker(players)
    t.apply_end_of_round([("Alice", gained, "reason")])
    halved = math.ceil(gained / 2)
    net = sum(e[0] for e in players[0].drink_log)
    assert players[0].drinks_owed() == gained  # raw positive entry unchanged
    assert net == gained - expected_credit == halved
    if expected_credit > 0:
        assert any("halving" in e[1] for e in players[0].drink_log)
    else:
        assert not any("halving" in e[1] for e in players[0].drink_log)


def test_apply_end_of_round_easy_mode_under_4_players():
    alice = make_player("Alice")
    bob = make_player("Bob")
    t = _tracker([alice, bob])
    t.easy_mode = True
    t.apply_end_of_round([("Alice", 3, "reason")])
    net = sum(e[0] for e in alice.drink_log)
    assert net == 2  # ceil(3/2)
    halving_entries = [e for e in alice.drink_log if "halving" in e[1]]
    assert len(halving_entries) == 1
    assert "Easy mode" in halving_entries[0][1]


def test_apply_end_of_round_combines_multiple_msg_lists():
    players = [make_player(n) for n in ["Alice", "Bob", "Carol", "Dave"]]
    t = _tracker(players)
    # Combined list: Alice +1 twice -> gained = 2 -> halved once
    t.apply_end_of_round([("Alice", 1, "reason1"), ("Alice", 1, "reason2")])
    net = sum(e[0] for e in players[0].drink_log)
    assert net == 1  # ceil(2/2) = 1, halved once not twice
    halving_entries = [e for e in players[0].drink_log if "halving" in e[1]]
    assert len(halving_entries) == 1


def test_apply_end_of_round_zero_gain_no_halving_message():
    players = [make_player(n) for n in ["Alice", "Bob", "Carol", "Dave"]]
    t = _tracker(players)
    t.apply_end_of_round([("Alice", 1, "reason")])  # Bob gains nothing
    assert not any("halving" in e[1] for e in players[1].drink_log)


# ---------------------------------------------------------------------------
# apply_ace_clubs_credit
# ---------------------------------------------------------------------------

def test_ace_clubs_credit_applied_when_owed_positive():
    alice = make_player("Alice")
    alice.add_drink(2, "some drink", "player")
    t = _tracker([alice])
    t.apply_ace_clubs_credit(alice)
    assert alice.drink_log[-1] == (-1, "Alice A♣ credit: -1 sip", "player")


def test_ace_clubs_credit_noop_when_owed_zero():
    alice = make_player("Alice")
    t = _tracker([alice])
    t.apply_ace_clubs_credit(alice)
    assert alice.drink_log == []


# ---------------------------------------------------------------------------
# _handle_handout
# ---------------------------------------------------------------------------

def test_handout_no_other_players_noop():
    alice = make_player("Alice")
    t = _tracker([alice])
    t._handle_handout("Alice", 2, "reason")
    assert alice.drink_log == []


def test_handout_npc_giver_round_robin():
    alice = make_player("Alice", is_npc=True)
    bob = make_player("Bob")
    carol = make_player("Carol")
    t = _tracker([alice, bob, carol])
    t._handle_handout("Alice", 3, "reason")
    # 3 sips round-robin across [Bob, Carol] -> Bob gets 2, Carol gets 1
    assert bob.drinks_owed() == 2
    assert carol.drinks_owed() == 1


def test_handout_human_giver_rejects_invalid_then_self_then_valid(monkeypatch, capsys):
    alice = make_player("Alice")
    bob = make_player("Bob")
    t = _tracker([alice, bob], verbose=True)

    inputs = iter(["Zach", "Alice", "Bob"])
    monkeypatch.setattr("builtins.input", lambda *_args, **_kw: next(inputs))

    t._handle_handout("Alice", 1, "reason")
    assert bob.drinks_owed() == 1


# ---------------------------------------------------------------------------
# print_round_summary — smoke test
# ---------------------------------------------------------------------------

def test_print_round_summary_smoke_quiet():
    alice = make_player("Alice", is_dealer=True)
    house = make_player("House")
    alice.add_drink(2, "dealer reason", "dealer")
    alice.add_drink(1, "player reason", "player")
    t = _tracker([alice, house], dealer=alice, verbose=False)
    # Should not raise even with mixed roles and a House player with no log
    t.print_round_summary()


def test_print_round_summary_verbose_contains_key_substrings(capsys):
    alice = make_player("Alice", is_dealer=True)
    alice.add_drink(2, "dealer reason", "dealer")
    t = _tracker([alice], dealer=alice, verbose=True)
    t.print_round_summary()
    out = capsys.readouterr().out
    assert "DRINK SUMMARY" in out
    assert "Dealer (Alice)" in out
    assert "dealer reason" in out
