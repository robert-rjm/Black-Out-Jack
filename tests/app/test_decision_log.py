"""
tests/test_decision_log.py
===========================
C5 (Phase C testing) — docs/planning/DecisionLog-Plan.md

Covers:
  1. record_decision captures pre-action state (hand_cards_before /
     hand_total_before) before the action mutates the hand, and
     visible_cards reflects the table at that instant.
  2. The dealer's hidden hole card never appears in visible_cards.
  3. backfill_hand_results fills hand_result for the current round once
     hand.result is set, and leaves other rounds / already-filled rows
     alone.
  4. /export_decisions returns well-formed CSV with the documented
     columns, for both Normal mode (bet_amount) and Drinking mode (wager).
"""

import csv
import io

import pytest

from engine.blackjack import Player, Shoe
from engine.referee import RefereeSession
from app.models.game_room import GameRoom, GameConfig
from app.services.decision_log import (
    record_decision,
    backfill_hand_results,
    _snapshot_visible_cards,
)
from app.services.session_store import game_sessions

from tests.conftest import make_card


# ---------------------------------------------------------------------------
# Helper: build a minimal, started GameRoom
# ---------------------------------------------------------------------------

def _make_room(drinking_mode: bool = True) -> GameRoom:
    rob   = Player("Rob")
    marco = Player("Marco")
    marco.is_dealer = True

    session = RefereeSession([rob, marco], dealer_name="Marco")
    session.start_round(digital=True)
    session.shoe = Shoe(num_decks=4)
    session.shoe.shuffle(quiet=True)

    room = GameRoom(
        session=session,
        config=GameConfig(
            mode="digital",
            drinking_mode=drinking_mode,
        ),
    )
    return room


# ---------------------------------------------------------------------------
# 1. Pre-action snapshot + visible_cards
# ---------------------------------------------------------------------------

def test_record_decision_captures_pre_action_state():
    room = _make_room(drinking_mode=False)
    rob   = room._get_player("Rob")
    marco = room._get_player("Marco")

    # Rob's hand: 10, 6 (=16) -- about to hit
    rob_hand = rob.hands[0]
    rob_hand.cards.extend([make_card("10", "S"), make_card("6", "H")])

    # Dealer shows an upcard + hidden hole card
    marco.dealer_hand.cards.extend([make_card("7", "C"), make_card("K", "D")])

    record_decision(room, rob, rob_hand, "h")

    row = room._decision_log[-1]
    assert row["hand_cards_before"] == "10♠ 6♥"
    assert row["hand_total_before"] == 16
    assert row["is_soft"] is False
    assert row["dealer_upcard"] == "7♣"
    assert row["action_taken"] == "h"
    assert row["round"] == room.round_count
    assert row["player"] == "Rob"
    assert row["hand_index"] == 1

    # Now mutate the hand (simulate the hit) -- the recorded row must NOT change.
    rob_hand.cards.append(make_card("5", "D"))
    assert row["hand_cards_before"] == "10♠ 6♥"
    assert row["hand_total_before"] == 16

    # visible_cards at decision time: Rob's pre-hit hand + dealer upcard only
    # (hole card K♦ excluded).
    visible = row["visible_cards"]
    assert "10♠" in visible and "6♥" in visible
    assert "7♣" in visible
    assert "K♦" not in visible
    assert "5♦" not in visible  # dealt after the decision was recorded


# ---------------------------------------------------------------------------
# 2. Hole card exclusion (direct snapshot check)
# ---------------------------------------------------------------------------

def test_visible_cards_excludes_hidden_dealer_hole_card():
    room = _make_room(drinking_mode=False)
    rob   = room._get_player("Rob")
    marco = room._get_player("Marco")

    rob.hands[0].cards.extend([make_card("9", "S"), make_card("9", "H")])
    marco.dealer_hand.cards.extend([make_card("A", "C"), make_card("Q", "D")])

    visible = _snapshot_visible_cards(room)
    assert "A♣" in visible          # upcard visible
    assert "Q♦" not in visible      # hole card hidden
    assert "9♠" in visible and "9♥" in visible


# ---------------------------------------------------------------------------
# 3. hand_result backfill
# ---------------------------------------------------------------------------

def test_backfill_hand_results():
    room = _make_room(drinking_mode=False)
    rob   = room._get_player("Rob")
    marco = room._get_player("Marco")

    rob.hands[0].cards.extend([make_card("10", "S"), make_card("9", "H")])
    marco.dealer_hand.cards.extend([make_card("7", "C"), make_card("K", "D")])

    record_decision(room, rob, rob.hands[0], "s")
    row = room._decision_log[-1]
    assert row["hand_result"] is None

    # A row from a previous round, already filled -- must stay untouched.
    stale_row = dict(row)
    stale_row["round"] = room.round_count - 1
    stale_row["hand_result"] = "win"
    stale_row["_hand_id"] = -12345
    room._decision_log.append(stale_row)

    # Resolve the round.
    rob.hands[0].result = "win"
    backfill_hand_results(room)

    assert row["hand_result"] == "win"
    assert stale_row["hand_result"] == "win"  # unchanged

    # Calling again is a no-op (idempotent).
    backfill_hand_results(room)
    assert row["hand_result"] == "win"


# ---------------------------------------------------------------------------
# 4. /export_decisions CSV shape
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client():
    from app import create_app
    app = create_app()
    app.testing = True
    return app.test_client()


def _populate_and_export(app_client, drinking_mode: bool, room_code: str):
    room = _make_room(drinking_mode=drinking_mode)
    rob   = room._get_player("Rob")
    marco = room._get_player("Marco")

    rob.hands[0].cards.extend([make_card("8", "S"), make_card("8", "H")])
    marco.dealer_hand.cards.extend([make_card("6", "C"), make_card("2", "D")])

    record_decision(room, rob, rob.hands[0], "sp")

    game_sessions[room_code] = room
    try:
        resp = app_client.get(f"/export_decisions?room_code={room_code}")
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"

        body = resp.data.decode("utf-8-sig")  # strip BOM
        reader = csv.reader(io.StringIO(body))
        rows = list(reader)
        return rows
    finally:
        game_sessions.pop(room_code, None)


def test_export_decisions_normal_mode(app_client):
    rows = _populate_and_export(app_client, drinking_mode=False, room_code="TestNormal1")
    header, data_row = rows[0], rows[1]

    assert "_hand_id" not in header
    assert "bet_amount" in header
    assert "wager" in header

    as_dict = dict(zip(header, data_row))
    assert as_dict["player"] == "Rob"
    assert as_dict["action_taken"] == "sp"
    assert as_dict["drinking_mode"] == "False"
    assert as_dict["bet_amount"] != ""   # normal mode -> bet_amount populated
    assert as_dict["wager"] == ""        # ... and wager empty


def test_export_decisions_drinking_mode(app_client):
    rows = _populate_and_export(app_client, drinking_mode=True, room_code="TestDrink1")
    header, data_row = rows[0], rows[1]

    as_dict = dict(zip(header, data_row))
    assert as_dict["drinking_mode"] == "True"
    assert as_dict["wager"] != ""        # drinking mode -> wager populated
    assert as_dict["bet_amount"] == ""   # ... and bet_amount empty


def test_export_decisions_no_session_returns_404(app_client):
    resp = app_client.get("/export_decisions?room_code=NoSuchRoom")
    assert resp.status_code == 404
