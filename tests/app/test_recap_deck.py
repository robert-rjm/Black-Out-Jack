"""
Tests for the session recap deck: app/services/recap_deck.py (numbers and
data-driven wording) and GET /recap_html (app/routes/reports.py).
"""

import re

import pytest

from engine.referee import RefereeSession
from tests.conftest import make_player
from app import create_app
from app.config import TIP_URL
from app.models.game_room import GameRoom, GameConfig
from app.services.recap_deck import analyse, build_html, logo_css
from app.services.session_store import game_sessions, set_session


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def _row(rnd, player, rule, sips, dealer="Alice", role="player"):
    return {"round": rnd, "dealer": dealer, "player": player, "role": role, "rule": rule, "sips": sips}


def _dec(rnd, player, taken, book, result, dealer="Alice", hand=1, ts=1_800_000_000.0):
    return {"session_id": "Deck1", "timestamp": ts + rnd * 60, "round": rnd, "player": player,
            "hand_index": hand, "dealer_name": dealer, "action_taken": taken,
            "basic_strategy_action": book, "is_npc": False, "hand_result": result}


def _session_rows():
    """Bob leads rounds 1-2, Carol overtakes in round 3 and wins."""
    rows = [
        _row(1, "Bob", "Net hand losses", 3), _row(1, "Carol", "Blackjack bonus", 1),
        _row(1, "Alice", "Hard Dealer Switch", 1, role="dealer"),
        _row(2, "Bob", "Suited winning hand", 2), _row(2, "Carol", "Net hand losses", 2),
        _row(3, "Carol", "Other-player sweep", 6), _row(3, "Bob", "Bust vote credit", -1),
        _row(3, "Alice", "Wild Card", 1),
    ]
    decisions = []
    for rnd in (1, 2, 3):
        for p in ("Alice", "Bob", "Carol"):
            # 12 hands per dealer would be needed for the >=10 filter; keep it
            # small so the early-session fallback (anyone who dealt) is used
            decisions.append(_dec(rnd, p, "s", "s" if p != "Bob" else "h", "loss" if p == "Bob" else "win"))
    lottery = [{"player": "Bob", "x_entered": 5}, {"player": "Carol", "x_entered": 1}]
    return rows, decisions, lottery


def _titles(html):
    return re.findall(r"<h1>(.*?)</h1>", html)


# ── analyse ─────────────────────────────────────────────────────────────────

def test_analyse_tracks_race_and_lead_changes():
    rows, decisions, lottery = _session_rows()
    a = analyse(rows, decisions, lottery, "2026-10-30")
    assert a["n_rounds"] == 3
    assert a["total"] == {"Bob": 4, "Carol": 9, "Alice": 2}
    assert a["changes"] == [(1, "Bob"), (3, "Carol")]
    assert a["cum"]["Carol"] == [0, 1, 3, 9]
    assert a["gross_all"] == 16 and a["net"] == 15
    assert a["credits"] == {"Bust vote credit": -1}
    assert a["session_id"] == "Deck1"
    assert a["minutes"] == pytest.approx(2.0)


def test_analyse_normalises_per_round_played_for_late_joiners():
    rows = [_row(1, "Bob", "Net hand losses", 4), _row(2, "Bob", "Net hand losses", 4),
            _row(2, "Dan", "Net hand losses", 4)]
    decisions = [_dec(1, "Bob", "s", "s", "loss"), _dec(2, "Bob", "s", "s", "loss"), _dec(2, "Dan", "s", "s", "loss")]
    a = analyse(rows, decisions, [], "d")
    assert a["present"] == {"Bob": 2, "Dan": 1}
    assert a["joined"]["Dan"] == 2
    assert a["per_round"] == {"Bob": 4.0, "Dan": 4.0}


def test_analyse_counts_round_zero_rows_in_round_one():
    a = analyse([_row(0, "Bob", "Wild Card", 1), _row(1, "Bob", "Net hand losses", 2)], [], [], "d")
    assert a["n_rounds"] == 1
    assert a["cum"]["Bob"] == [0, 3]


def test_analyse_basic_strategy_split():
    rows, decisions, lottery = _session_rows()
    a = analyse(rows, decisions, lottery, "d")
    assert a["bs"]["Bob"] == (0, 3)            # never matched the book
    assert a["bs"]["Carol"] == (3, 3)
    assert a["dev_kinds"][("s", "h")] == 3


# ── build_html ──────────────────────────────────────────────────────────────

def test_deck_titles_follow_the_data():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    titles = _titles(html)
    assert "Carol took the lead in round 3 and held on to win by 5 sips; Bob had led for 2 rounds" in titles
    assert any(t.startswith("A clear win for Carol") for t in titles)
    assert "Thanks for playing!" in html
    assert TIP_URL in html


def test_deck_page_numbers_run_in_order():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    pages = [int(n) for n in re.findall(r"Session recap · (\d+)</span>", html)]
    assert pages == list(range(2, 2 + len(pages)))
    assert html.count('class="slide') == len(pages) + 2           # + cover and thank-you


def test_thin_session_skips_slides_without_data():
    """One player, one round, no decisions: no strategy or house slides, no crash."""
    a = analyse([_row(1, "Solo", "Net hand losses", 2)], [], [], "d")
    html = build_html(a, logo_css(inline=False))
    assert "Decision quality" not in html
    assert "The house" not in html
    assert "By the book" not in html
    pages = [int(n) for n in re.findall(r"Session recap · (\d+)</span>", html)]
    assert pages == list(range(2, 2 + len(pages)))


def test_all_credit_session_does_not_crash():
    a = analyse([_row(1, "Bob", "Bust vote credit", -2)], [], [], "d")
    assert "Thanks for playing!" in build_html(a, logo_css(inline=False))


def test_player_names_are_escaped():
    rows = [_row(1, "<b>x</b>", "Net hand losses", 2), _row(1, "Bob", "Net hand losses", 1)]
    html = build_html(analyse(rows, [], [], "d"), logo_css(inline=False))
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_logo_css_inline_or_static():
    assert "/static/img/logo.png" in logo_css(inline=False)
    assert "data:image/png;base64," in logo_css(inline=True)


# ── GET /recap_html ─────────────────────────────────────────────────────────

def _room(room_code, rows, decisions=()):
    players = [make_player("Alice"), make_player("Bob")]
    players[0].is_dealer = True
    room = GameRoom(session=RefereeSession(players, "Alice", wager=1, num_hands=1),
                    config=GameConfig(mode="digital", drinking_mode=True))
    room.drinks.csv_rows = list(rows)
    room._decision_log = list(decisions)
    set_session(room_code, room)
    return room


def test_recap_html_404_for_unknown_room(client):
    assert client.get("/recap_html?room_code=Nope-404").status_code == 404


def test_recap_html_404_before_any_drinks(client):
    _room("RecapEmpty", [])
    try:
        resp = client.get("/recap_html?room_code=RecapEmpty")
        assert resp.status_code == 404
        assert b"play a round first" in resp.data
    finally:
        game_sessions.pop("RecapEmpty", None)


def test_recap_html_returns_deck(client):
    rows, decisions, _ = _session_rows()
    _room("RecapDeck", rows, decisions)
    try:
        resp = client.get("/recap_html?room_code=RecapDeck")
        assert resp.status_code == 200
        assert resp.mimetype == "text/html"
        body = resp.get_data(as_text=True)
        assert body.count('<section class="slide') >= 10
        assert "/static/img/logo-transparent.png" in body       # served, not inlined
        assert "data:image/png" not in body
    finally:
        game_sessions.pop("RecapDeck", None)


def test_recap_html_falls_back_to_room_code_without_decisions(client):
    _room("RecapNoDec", [_row(1, "Bob", "Net hand losses", 2)])
    try:
        body = client.get("/recap_html?room_code=RecapNoDec").get_data(as_text=True)
        assert "Session recap · RecapNoDec" in body
    finally:
        game_sessions.pop("RecapNoDec", None)
