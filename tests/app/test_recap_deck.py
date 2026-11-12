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


def test_one_recap_slide_per_player_in_finishing_order():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    trackers = re.findall(r'<div class="tracker">Player recap · (\w+)</div>', html)
    assert trackers == ["Carol", "Bob", "Alice"]
    assert "Carol finished 1st of 3 with 9 net sips" in html


def _rated_rows():
    """Bob on a 1.5× booster, Carol on wine (0.6×); sips_raw is before the factor."""
    return [
        {**_row(1, "Bob", "Net hand losses", 3), "sips_raw": 2, "rate": 1.5},
        {**_row(1, "Carol", "Net hand losses", 1), "sips_raw": 2, "rate": 0.6},
        {**_row(2, "Bob", "Ace dealt: Ace of Spades (player hand)", 1), "sips_raw": 1, "rate": 1.0},   # skips boosters
        {**_row(2, "Carol", "Blackjack bonus", 2), "sips_raw": 3, "rate": 0.6},
    ]


def test_analyse_drink_rate_from_rows():
    a = analyse(_rated_rows(), [], [], "d")
    assert a["rate_used"]
    assert a["raw_total"] == {"Bob": 3, "Carol": 5}
    assert a["raw_gross_all"] == 8 and a["gross_all"] == 7
    # Round 2's only row is an ace, which skips boosters and logs 1.0: from rows
    # alone that round reads as 1.0 (live sessions pass rate_rounds instead)
    assert a["factor_rounds"]["Bob"] == {1.5: 1, 1.0: 1}
    assert a["avg_factor"]["Carol"] == pytest.approx(0.6)


def test_analyse_prefers_live_rate_rounds():
    a = analyse(_rated_rows(), [], [], "d", {"rate_rounds": {"Bob": {1.0: 1, 1.5: 1}}})
    assert a["factor_rounds"]["Bob"] == {1.0: 1, 1.5: 1}
    assert a["avg_factor"]["Bob"] == pytest.approx(1.25)


def test_rows_without_rate_count_as_one():
    """No rate column: 1.0×, even when sips_raw differs (older exports used
    it for other things, e.g. Easy Mode halving)."""
    a = analyse([{**_row(1, "Bob", "Net hand losses", 3), "sips_raw": 6},
                 _row(1, "Carol", "Net hand losses", 2)], [], [], "d")
    assert a["factor_rounds"]["Bob"] == {1.0: 1}
    assert a["factor_rounds"]["Carol"] == {1.0: 1}
    assert not a["rate_used"]


def _night_rows():
    """Two seats, 6 rounds: a milestone, a Hard Dealer Switch, Targeted Drinking,
    bust calls and a 1.4× booster in rounds 4-6."""
    rows = []
    for rnd in range(1, 7):
        rate = 1.4 if rnd >= 4 else 1.0
        rows.append({**_row(rnd, "Bob", "Net hand losses", 14), "sips_raw": 10, "rate": rate})
        rows.append({**_row(rnd, "Carol", "Net hand losses", 1), "sips_raw": 1, "rate": rate})
    rows += [_row(3, "Bob", "Milestone handout", 5), _row(2, "Carol", "Hard Dealer Switch", 6, role="dealer"),
             _row(5, "Carol", "Targeted Drinking wrong guess", 2), _row(6, "Carol", "Targeted Drinking wrong guess", 2),
             _row(1, "Bob", "Bust vote credit", -1), _row(2, "Bob", "Bust vote wrong call", 1)]
    decisions = [_dec(rnd, p, "s", "s", "loss" if p == "Bob" else ("win" if rnd % 2 else "loss"))
                 for rnd in range(1, 7) for p in ("Bob", "Carol")]
    return rows, decisions


def test_analyse_milestones_switches_targeted_streaks():
    rows, decisions = _night_rows()
    a = analyse(rows, decisions, [], "d", {"milestones": {50: "Bob"}})
    assert a["milestones"] == [(50, "Bob", 4)]                    # Bob's running total passes 50 in round 4
    assert a["hard_switches"] == [(2, "Carol", 6)]
    assert a["targeted"]["Carol"] == {"sips": 4, "wrong": 2}
    assert a["bust_by"]["Bob"] == (1, 1)
    assert a["longest_loss"]["Bob"] == 6                          # lost every round
    assert a["longest_loss"]["Carol"] == 1                        # alternates win / loss
    assert a["rate_spans"] == [(4, 6, "1.4×")]


def test_analyse_prefers_live_longest_loss():
    rows, decisions = _night_rows()
    a = analyse(rows, decisions, [], "d", {"longest_loss": {"Bob": 9}})
    assert a["longest_loss"] == {"Bob": 9, "Carol": 0}


def test_sips_per_hand_leaves_out_side_games():
    rows, decisions = _night_rows()
    a = analyse(rows, decisions, [], "d")
    # Bob: 6 × 14 net-loss sips over 6 hands; the milestone and bust-vote rows don't count
    assert a["per_hand"]["Bob"] == pytest.approx(14.0)


def test_deck_shows_new_moments_and_side_game():
    rows, decisions = _night_rows()
    html = build_html(analyse(rows, decisions, [], "d", {"milestones": {50: "Bob"}}), logo_css(inline=False))
    assert "Bob first to 50 sips" in html
    assert "Hard Dealer Switch: Carol drinks 6" in html
    assert "Drink Rate 1.4×" in html
    assert "net sips from Targeted Drinking (2 wrong calls)" in html
    assert "Sips / hand" in html
    assert "lost 6 in a row" in html


def test_bust_chance_of_one_more_card():
    from app.services.recap_deck import _bust_chance
    assert _bust_chance(11) == 0
    assert _bust_chance(12) == pytest.approx(4 / 13)             # only ten-value cards bust 12
    assert _bust_chance(16) == pytest.approx(8 / 13)
    assert _bust_chance(20) == pytest.approx(12 / 13)            # only an Ace saves 20


def _hand(rnd, player, cards, total, taken, result, soft=False, upcard="7♦"):
    return {**_dec(rnd, player, taken, taken, result), "hand_cards_before": cards, "hand_total_before": total,
            "is_soft": soft, "dealer_upcard": upcard}


def test_average_hand_and_paid_off_risk():
    decisions = [
        _hand(1, "Bob", "10♠ 6♥", 16, "h", "win"),                # hit hard 16, won: 62% risk
        _hand(1, "Bob", "10♠ 6♥ 3♣", 19, "s", "win"),
        _hand(2, "Bob", "9♠ 9♥", 18, "s", "loss"),
        _hand(1, "Carol", "A♠ 6♥", 17, "h", "win", soft=True),   # soft: no bust risk, not counted
        _hand(2, "Carol", "10♦ 5♣", 15, "h", "loss"),             # risky but lost: not counted
    ]
    rows = [_row(1, "Bob", "Net hand losses", 1), _row(1, "Carol", "Net hand losses", 1)]
    a = analyse(rows, decisions, [], "d")
    assert a["avg_start"]["Bob"] == pytest.approx(17)             # 16 and 18
    assert a["avg_stand"]["Bob"] == pytest.approx(18.5)           # stood on 19 and 18
    assert [(r[2], r[4]) for r in a["risks"]] == [("Bob", 16)]
    html = build_html(a, logo_css(inline=False))
    assert "Paid-off risk" in html and "hit hard 16 vs 7♦" in html
    assert "Avg starting hand" in html and "starts on 17.0" in html


def test_executive_summary_has_no_beer_equivalent():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    assert "beers' worth" not in html


def test_deck_shows_drink_rate_when_used():
    html = build_html(analyse(_rated_rows(), [], [], "d"), logo_css(inline=False))
    assert "Drink Rate factors removed 1 sip" in html          # bridge title
    assert ">Net sips</text>" in html or "Net sips drunk" in html   # bridge ends on the net bill
    assert "Avg drink factor" in html                       # league table + comparables
    assert "🚀 Booster" in html and "🍷 Sipping smart" in html
    assert "Drink Rate took off 1 sip: 8 owed at 1.0× became 7" in html


def test_drink_rate_that_changed_nothing_says_so():
    """Factors in play (live rate_rounds) but every sip landed at 1.0× -- no "+0 sips"."""
    rows = [_row(1, "Bob", "Net hand losses", 1), _row(1, "Carol", "Net hand losses", 2)]
    html = build_html(analyse(rows, [], [], "d", {"rate_rounds": {"Bob": {1.5: 1}}}), logo_css(inline=False))
    assert "netted out" in html
    assert "+0 sips" not in html and "added 0 sip" not in html


def test_deck_without_drink_rate_hides_it():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    assert "Avg drink factor" not in html
    assert ">at 1.0×</text>" not in html
    assert "everyone at 1.0×" in html                        # setup slide


def test_setup_slide_lists_rules_that_are_off():
    from engine.rules_registry import PRESETS, RULES, RuleSet
    rules = RuleSet(PRESETS["standard"] - {"side.bust_vote"})
    off = [r for r in RULES if not rules.on(r.id)]
    rows, decisions, lottery = _session_rows()
    a = analyse(rows, decisions, lottery, "d", {"rules": rules, "wager": 1, "hands": 2, "easy_mode": False})
    html = build_html(a, logo_css(inline=False))
    # The bust vote is a live rule, which presets ignore, so this is still Standard
    assert f"Played on the Standard preset with {len(off)} of {len(RULES)} rules off" in html
    assert "Side bet: dealer bust vote" in html


def test_setup_slide_without_rules_says_so():
    rows, decisions, lottery = _session_rows()
    html = build_html(analyse(rows, decisions, lottery, "d"), logo_css(inline=False))
    assert "Not part of this export" in html


def test_side_games_only_show_games_in_play():
    from engine.rules_registry import PRESETS, RuleSet
    rows = [_row(1, "Bob", "Net hand losses", 2), _row(1, "Carol", "Net hand losses", 1)]
    starter = RuleSet(PRESETS["starter"])
    assert not starter.on("side.bust_vote") and not starter.on("event.dealer_lottery")
    html = build_html(analyse(rows, [], [], "d", {"rules": starter}), logo_css(inline=False))
    assert "Behaviour · Side games" not in html
    # A rule switched off mid-session still shows if it left sips
    rows.append(_row(1, "Bob", "Bust vote wrong call", 1))
    html = build_html(analyse(rows, [], [], "d", {"rules": starter}), logo_css(inline=False))
    assert "Behaviour · Side games" in html
    assert "Not played this session: Dealer Lottery" in html


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
        assert "Appendix · Table setup" in body
        assert "House rules: " in body                          # live room passes its RuleSet
    finally:
        game_sessions.pop("RecapDeck", None)


def test_recap_html_falls_back_to_room_code_without_decisions(client):
    _room("RecapNoDec", [_row(1, "Bob", "Net hand losses", 2)])
    try:
        body = client.get("/recap_html?room_code=RecapNoDec").get_data(as_text=True)
        assert "Session recap · RecapNoDec" in body
    finally:
        game_sessions.pop("RecapNoDec", None)
