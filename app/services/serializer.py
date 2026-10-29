"""
app/services/serializer.py
===========================
Converts live session state into the JSON snapshots the frontend consumes.

All functions are pure reads — nothing here mutates session state.
The only external dependency is validators.get_client_info so that
per-client fields (my_role, is_dealer_client, etc.) can be included.
"""

import time

from app.models.game_room import GameRoom
from app.models.state_schema import AppState, QueuedSettingsOut
from app.services.validators import get_client_info
from app.services.round_state import (
    play_order, player_done, current_turn, round_phase, serialize_card, serialize_hand,
)
from app.services.stats import (
    _compute_live_drink_totals, compute_payout_data, compute_best_play,
    compute_trophy_holder, compute_kpi_stats,
)
from app.services.serializers.milestone import _serialize_last_milestone, _serialize_pending_milestone
from app.services.serializers.dealer_lottery import _serialize_pending_dealer_lottery, _serialize_last_dealer_lottery_result
from app.services.serializers.targeted_drinking import _serialize_pending_targeted_drinking, _serialize_last_targeted_drinking_result, _serialize_targeted_drinking_summary, _serialize_pending_target_proposal, _serialize_last_target_proposal_result
from app.services.targeted_drinking import targeted_drinking_awaiting_start
from app.services.serializers.admin_afk import _serialize_admin_afk_vote
from app.services.serializers.drink_rate import _serialize_drink_rates
from app.services.serializers.boj import _serialize_boj
from app.services.serializers.bust_vote import _bust_vote_window
from app.services.serializers.insurance import _insurance_outcome_text, _serialize_insurance_vote
from app.services.house_rules import serialize_rules
from app.services.rule_votes import serialize_rule_votes


def serialize_state(session: GameRoom | None, client_id: str = "") -> dict:
    """Full snapshot for the UI."""
    if not session:
        return {"ok": False}

    _ci = get_client_info(session, client_id) if client_id else {}

    dealer      = session._get_dealer()
    order       = play_order(session)
    turn        = current_turn(session, order=order)
    phase       = round_phase(session, turn=turn)
    hide_double = (phase != "round-over")   # reveal doubled card once round is over

    # Build a name→hint lookup from the session-level hint set
    # (stored on session._hint_seats to survive client reconnections)
    _hint_names = getattr(session, "_hint_seats", set())

    table = []
    _cash = (not session.drinking_mode) and session.mode == "digital"
    for p in session.all_players:
        _hands = [serialize_hand(h, rules=session.rules, hide_double=hide_double) for h in p.hands]
        if _cash:
            # Normal mode: doubling/splitting costs another bet -- don't offer
            # it to a player who can't cover it.
            from app.services.payout_tracker import can_afford_extra
            if not can_afford_extra(session, p.name):
                for _h in _hands:
                    _h["can_double"] = False
                    _h["can_split"]  = False
        table.append({
            "name":                   p.name,
            "is_dealer":              p.is_dealer,
            "is_npc":                 getattr(p, "is_npc", False),
            "personality":            getattr(p, "personality", "basic") if getattr(p, "is_npc", False) else None,
            "hands":                  _hands,
            "done":                   player_done(p),
            "is_turn":                (p.name == turn),
            "strategy_hint_enabled":  p.name.lower() in _hint_names,
            "player_bet":             getattr(session, "_player_bets", {}).get(p.name, session.bet_amount),
        })

    # Dealer hand — hide hole card while players are still acting (digital only)
    mode         = session.mode
    d_hand_state = None
    if dealer and dealer.dealer_hand:
        d_cards = dealer.dealer_hand.cards
        if mode == "digital" and phase in ("playing", "pre-deal") and len(d_cards) >= 2:
            d_hand_state = {
                "cards":     [serialize_card(d_cards[0]),
                              {"rank": "?", "suit": "hidden", "symbol": "?"}]
                              + [serialize_card(c) for c in d_cards[2:]],
                "score":     "?",
                "hidden":    True,
                "blackjack": False,
                "bust":      False,
                "done":      False,
            }
        else:
            d_hand_state = {
                "cards":     [serialize_card(c) for c in d_cards],
                "score":     dealer.dealer_hand.score() if d_cards else 0,
                "hidden":    False,
                "blackjack": bool(d_cards) and dealer.dealer_hand.is_blackjack(),
                "bust":      bool(d_cards) and dealer.dealer_hand.is_bust(),
                "done":      bool(d_cards) and (
                    dealer.dealer_hand.stood
                    or dealer.dealer_hand.is_bust()
                    or dealer.dealer_hand.score() >= 17
                ),
            }

    # Dealer-rotation suggestion (drinking mode only — Normal mode has a fixed
    # house dealer that never rotates, so all rotation state is suppressed)
    if session.drinking_mode:
        switch         = session.round.switch_this_round
        rounds_td      = session.rounds_this_dealer
        num_p          = len(session.all_players)
        suggest_rotate = bool(switch in ("hard", "soft") or rounds_td >= num_p)
        if switch == "hard":
            rotate_reason = "Hard switch — dealer lost all hands"
        elif switch == "soft":
            rotate_reason = "Soft switch — dealer won all hands"
        elif suggest_rotate:
            rotate_reason = f"Round {rounds_td} of {num_p} — every player has been dealer"
        else:
            rotate_reason = f"Round {rounds_td} of {num_p} as dealer"
    else:
        switch         = None
        rounds_td      = 0
        suggest_rotate = False
        rotate_reason  = ""

    sip_totals, _dealer_role_sips = (
        _compute_live_drink_totals(session) if session.drinking_mode else ({}, {})
    )

    _payout_data = compute_payout_data(session)

    # ---- This-round / last-round drink summaries ----
    _drink_summary_data = {
        "sip_totals":             sip_totals,
        "sip_grand_total":        sum(sip_totals.values()),
        "round_over_seq":         session.drinks.round_over_seq,
        "last_round_sips":        {k: max(0, v) for k, v in session.drinks.last_round_sips.items()},
        "clean_streaks":          dict(session.stats.clean_streak),
        "total_clean_rounds":     dict(session.stats.total_clean_rounds),
        "trophy_holder":          compute_trophy_holder(session),
        "worst_streak_holder":    session.stats.worst_streak_holder,
        "last_round_drinks":      session.drinks.last_round_drinks,
        "round_notices":          session.drinks.round_notices,
        "prev_round_sips":        {k: max(0, v) for k, v in session.drinks.prev_round_sips.items()},
        "prev_round_drinks":      session.drinks.prev_round_drinks,
        "dealer_role_sips":       _dealer_role_sips,
        "ace_drink_events":       session.round._ace_drink_events,
        "ace_drink_seq":          session.round._ace_drink_seq,
        "reshuffle_events":       session.round._reshuffle_events,
        "reshuffle_seq":          session.round._reshuffle_seq,
        # Wild Card Easter egg
        "wild_card_enabled":      session.wild_card_enabled,
        "buyin_handouts":         session.buyin_handouts,
        "my_buyin_handouts":      {
            n: a for n, a in session.round._buyin_pending.items()
            if n not in session.round._buyin_given
            and n in set(_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
        },
        "wild_card_seq":          session.round._wild_card_seq,
        "wild_card_text":         (session.round._wild_card_result or {}).get("text"),
        "wild_card_outcome":      (session.round._wild_card_result or {}).get("outcome"),
        # Devil's Hand (666) / Lucky Sevens (777)
        "table_events":           session.round._table_events,
        "table_event_seq":        session.round._table_event_seq,
    }

    # ---- Bust-vote data ----
    _bust_vote_data = {
        "bust_vote_enabled":      session.bust_vote_enabled,
        "bust_votes":             dict(session.round._bust_votes),
        "my_bust_vote":           session.round._bust_votes.get((_ci.get("name") or "").capitalize()),
        "my_bust_votes":          {
            n: session.round._bust_votes.get(n)
            for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
        },
        "bust_vote_result":       session.round._bust_vote_result,
        "bust_handout_seconds_left": (
            max(0, round(session.round._bust_handout_expires_at - time.monotonic()))
            if session.round._bust_handout_expires_at else 0
        ),
        "my_bust_handout_pending": [
            n for n in (_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
            if (session.round._bust_vote_result or {}).get("dealer_busted")
            and n in (session.round._bust_vote_result or {}).get("winners", [])
            and n not in session.round._bust_handouts_given
        ],
        # max_round_sips kept here (not inside kpi_stats) because table-render.js
        # reads it directly for the "worst rond" badge on the score panel.
        "max_round_sips":         dict(session.stats.max_round_sips),
        "bust_handout_seq":       session._bust_handout_seq,
        "bust_handout_results":   list(session.round._bust_handout_log),
        **_bust_vote_window(session),
    }

    # ---- Insurance data ----
    _insurance_data = {
        "insurance_result":       [
            {**r, "outcome_text": _insurance_outcome_text(r)}
            for r in (session._insurance_result or [])
        ],
        "insurance_votes":        [
            _serialize_insurance_vote(v, session, _ci)
            for v in session.round._insurance_votes
        ],
    }

    # ---- Milestone data ----
    _show_milestone_run = (session.drinks.milestone_win_streak >= 2
                           and session.rules.on("milestone.back_to_back"))
    _milestone_data = {
        "last_milestone_result": _serialize_last_milestone(session.drinks.last_milestone_result),
        "pending_milestone":     _serialize_pending_milestone(session.round._pending_milestone, _ci),
        "last_milestone_worst":  session.drinks.last_milestone_worst,
        # Back-to-back milestone run: only surfaced once it is an actual
        # run (2+), so the frontend badge is a plain name comparison like
        # every other seat badge. Hidden when milestone.back_to_back is off.
        "milestone_run_holder": (session.drinks.last_milestone_winner
                                 if _show_milestone_run else None),
        "milestone_run_length": (session.drinks.milestone_win_streak
                                 if _show_milestone_run else 0),
    }

    _boj_data = {"boj": _serialize_boj(session, _ci, client_id)}

    # ---- Dealer Lottery data ----
    # Exclude givers who already gave (mirrors my_bust_handout_pending's
    # "n not in _bust_handouts_given" filter) -- last_dealer_lottery_result's
    # pending_handouts is a static snapshot from resolve_dealer_lottery() and
    # is never mutated by give_dealer_lottery_sip(), so without this filter
    # the give-overlay panel keeps showing an already-given giver's button
    # for the rest of the 90-second result window, blocking the table.
    _dl_pending_handouts = {
        n: a for n, a in (session.drinks.last_dealer_lottery_result or {}).get(
            "pending_handouts", {}).items()
        if n not in session.round._dealer_lottery_handouts_given
    }
    from app.services.dealer_lottery import dealer_lottery_reveal_waiting_on  # lazy: dealer_lottery imports this module
    _dl_my_names = set(_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
    _dealer_lottery_data = {
        "dealer_lottery": {
            "pending":              _serialize_pending_dealer_lottery(
                                        session.round._pending_dealer_lottery, _ci),
            "last_result":          _serialize_last_dealer_lottery_result(
                                        session.drinks.last_dealer_lottery_result),
            "result_seq":           session.drinks._dealer_lottery_result_seq,
            "pending_handouts":     dict(_dl_pending_handouts),
            "my_pending_handouts":  {n: a for n, a in _dl_pending_handouts.items()
                                     if n in _dl_my_names},
            "handout_seconds_left": (
                max(0, round(session.round._dealer_lottery_handout_expires_at - time.monotonic()))
                if session.round._dealer_lottery_handout_expires_at else 0
            ),
            # True while the handout is held back until everyone closes the reveal
            "reveal_pending":       session.round._dealer_lottery_reveal_deadline is not None,
            "reveal_acked_by_me":   client_id in session.round._dealer_lottery_reveal_acked,
            "reveal_waiting_on":    dealer_lottery_reveal_waiting_on(session),
        },
    }

    # ---- Targeted Drinking Mode data (Rules.md §5.10) ----
    # Perfect-graduation handout -- exclude givers who already gave, same
    # "n not in ..._given" filter as Dealer Lottery's own pending_handouts
    # (see the comment above _dl_pending_handouts).
    _td_pending_handouts = {
        n: a for n, a in (session.drinks.last_targeted_drinking_result or {}).get(
            "pending_handouts", {}).items()
        if n not in session.round._targeted_drinking_handouts_given
    }
    _td_my_names = set(_ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []))
    _targeted_drinking_data = {
        "targeted_drinking": {
            "active":               session._targeted_drinking_active,
            "targets":              list(session._targeted_drinking_targets),
            "streaks":              dict(session._targeted_drinking_streaks),
            "losing_streaks":       dict(session._targeted_drinking_losing_streaks),
            "streak_calls":         {n: list(c) for n, c in session._targeted_drinking_streak_calls.items()},
            "cooldown_until_round": session._targeted_drinking_cooldown_until_round,
            # Majority-vote-to-target proposal (tap a player's name at the
            # table): the pending Yes/No vote (if any), how many more
            # rounds *this* client is frozen from opening a new proposal
            # (0 if not frozen), and the most recent proposal's pass/fail
            # outcome (a brief one-shot flash, not a lasting result).
            "pending_proposal":     _serialize_pending_target_proposal(
                                        session.round._pending_target_proposal, _ci),
            "propose_cooldown_remaining": max(0, session._targeted_drinking_propose_cooldowns.get(
                                        (_ci.get("name") or "").lower(), 0) - session.round_count),
            "last_proposal_result": _serialize_last_target_proposal_result(
                                        session.drinks.last_target_proposal_result),
            "pending":              _serialize_pending_targeted_drinking(
                                        session.round._pending_targeted_drinking, _ci),
            "last_result":          _serialize_last_targeted_drinking_result(
                                        session.drinks.last_targeted_drinking_result),
            "result_seq":           session.drinks._targeted_drinking_result_seq,
            "last_summary":         _serialize_targeted_drinking_summary(
                                        session.drinks.last_targeted_drinking_summary),
            "summary_seq":          session.drinks._targeted_drinking_summary_seq,
            "awaiting_start":       targeted_drinking_awaiting_start(session),
            # Raw eligibility flag -- true whenever a mini-round could be
            # queued up right now (whether it's actually open yet, waiting
            # on Start Targeting Now, or blocked by the reveal-pause/
            # milestone/Dealer Lottery gates). The frontend uses this to
            # tell "something's genuinely about to happen" apart from
            # "nothing is queued at all" (e.g. the subgame was started
            # while already between rounds, so nothing will arm it until
            # a new round ends) -- see targeted_drinking.py's own
            # start_targeted_drinking docstring for the failure mode this
            # guards against.
            "eligible":             session.round._targeted_drinking_eligible,
            # Live run-wide statistics table (Rules.md §5.10) -- unlike
            # last_result/last_summary this isn't seq-gated one-shot data,
            # it's just the current running tally, always present so
            # targeted players can see it update while deciding their
            # next call.
            "stats": {
                "correct":      dict(session._targeted_drinking_correct_counts),
                "wrong":        dict(session._targeted_drinking_wrong_counts),
                "dealer_hands": session._targeted_drinking_dealer_hands,
                "dealer_busts": session._targeted_drinking_dealer_busts,
            },
            "pending_handouts":     dict(_td_pending_handouts),
            "my_pending_handouts":  {n: a for n, a in _td_pending_handouts.items()
                                     if n in _td_my_names},
            "handout_seconds_left": (
                max(0, round(session.round._targeted_drinking_handout_expires_at - time.monotonic()))
                if session.round._targeted_drinking_handout_expires_at else 0
            ),
            # Bumped once every pending giver for a mini-round has given or
            # forfeited (mirrors bust_handout_seq) -- the frontend gates the
            # recipient toast on this advancing, so it fires exactly once per
            # resolved handout batch rather than once per give_sip call.
            "handout_seq":          session._targeted_drinking_handout_seq,
            "handout_results":      list(session.round._targeted_drinking_handout_log),
        },
    }

    # ---- Connection / room-membership data (admin-only fields gated below) ----
    _connection_data = {
        "kick_votes":             {k: len(v) for k, v in session.round._kick_votes.items()},
        "kick_votes_mine":        [k for k, v in session.round._kick_votes.items()
                                   if (_ci.get("name") or "").lower() in v],
        "kick_votes_detail":      {k: sorted(v) for k, v in session.round._kick_votes.items()},
        "rejoin_requests":        [r for r in session._rejoin_requests
                                   if _ci.get("role") == "admin"],
        "my_rejoin_pending":      any(r["client_id"] == client_id
                                      for r in session._rejoin_requests),
        "pending_registrations":  [{"client_id": r["client_id"], "name": r["name"]}
                                   for r in session._pending_registrations
                                   if _ci.get("role") == "admin"],
        "my_registration_pending": any(r["client_id"] == client_id
                                       for r in session._pending_registrations),
        "my_registration_rejected": _ci.get("role") == "denied",
        "my_registration_denied":   (
            _ci.get("role") == "denied" and
            _ci.get("reg_denials", 0) >= 2
        ),
        "connected_clients":      [
            {"name": info.get("name"), "role": info.get("role"),
             "local_names": info.get("local_names") or []}
            for info in session._room_clients.values()
            if not info.get("kicked")
        ],
        "pending_seat_transfers": [
            {"requester_name": t["requester_name"], "target": t["target"]}
            for t in session._pending_seat_transfers
            if t["controller_cid"] == client_id
        ],
        "kicked_clients":         [
            {"client_id": cid, "name": info.get("name") or ""}
            for cid, info in session._room_clients.items()
            if info.get("kicked") and info.get("name")
        ] if _ci.get("role") == "admin" else [],
        "denied_clients":         [
            {"client_id": cid}
            for cid, info in session._room_clients.items()
            if info.get("role") == "denied" and info.get("reg_denials", 0) >= 2
        ] if _ci.get("role") == "admin" else [],
    }

    # ---- This client's identity / permissions ----
    _client_identity_data = {
        "my_role":                _ci.get("role"),
        "my_name":                _ci.get("name"),
        "afk_notice":             (session._room_clients.get(client_id) or {}).get("afk_notice"),
        "admin_afk_vote":         _serialize_admin_afk_vote(session, client_id),
        "drink_rates":            _serialize_drink_rates(session, client_id),
        "my_names":               _ci.get("local_names") or ([_ci.get("name")] if _ci.get("name") else []),
        "can_add_local_seat":     (
            _ci.get("role") in ("admin", "player") and
            any(
                # Not already one of this client's own seats
                p.name.lower() not in {(n or "").lower()
                               for n in (_ci.get("local_names") or []) + (
                                   [_ci.get("name")] if _ci.get("name") else [])}
                # Not claimed as another client's primary (remote) registration
                and p.name.lower() not in {(info.get("name") or "").lower()
                               for cid, info in session._room_clients.items()
                               if cid != client_id and not info.get("kicked")
                               and info.get("name")}
                # Not an NPC
                and not getattr(p, "is_npc", False)
                for p in session.all_players
            )
        ),
        "is_dealer_client":       (
            (_ci.get("role") == "admin" and session._god_mode) or
            session.dealer_name.lower() in {
                (n or "").lower()
                for n in ([_ci.get("name")] + list(_ci.get("local_names") or []))
            }
        ),
    }

    state = {
        "ok":              True,
        "round":           session.round_count,
        "dealer":          session.dealer_name,
        "players":         [p.name for p in session.all_players],
        "num_hands":       session.num_hands,
        "wager":           session.wager,
        "mode":            session.mode,
        "table":           table,
        "dealer_hand":     d_hand_state,
        "current_turn":    turn,
        "play_order":      order,
        "phase":           phase,
        "drinking_mode":          session.drinking_mode,
        "best_play":              compute_best_play(session, turn, phase),
        "honor_pending":          bool(session.drinking_mode and session.round._honor_pending),
        "honor_pending_action":   (session.round._honor_pending or {}).get("action") if session.drinking_mode else None,
        "honor_pending_reason":   (session.round._honor_pending or {}).get("reason") if session.drinking_mode else None,
        "suggest_rotate":         suggest_rotate,
        "rotate_reason":          rotate_reason,
        "rounds_this_dealer":     rounds_td,
        "dealer_rotate_every":    session._dealer_rotate_every,
        "switch_this_round":      switch,
        "log_entries":            session.round._log_entries,
        "log_count":              len(session.round._log_entries),
        "log_version":            session._log_version,
        "peeked_card":            session.round._last_peeked,
        "preselections":          session.round._preselections,
        "suggestions":            session.round._suggestions,
        "anim_default":           session._anim_default,
        "easy_mode":              session.easy_mode,
        "god_mode_enabled":       session._god_mode,
        "paused":                 session._paused_at is not None,
        # Validated against the real shape, then dumped back to a sparse
        # dict (only actually-queued keys) -- the frontend's
        # _renderQueuedBanner checks presence with `"wager" in queued`, so
        # every-key-with-null (a plain AppState field would dump that way)
        # would break it. See QueuedSettingsOut's docstring.
        "queued_settings": QueuedSettingsOut(**session._queued_settings).model_dump(exclude_none=True),
        "num_decks":              session.shoe.num_decks if session.shoe else 1,
        # House rules: ID lists only; names and groups come from the cached
        # GET /rules_registry.
        "rules":                  serialize_rules(session),
        "rule_votes":             serialize_rule_votes(session, _ci),
        "kpi_stats":              compute_kpi_stats(session, sip_ticker=sip_totals, order=order),
        **_payout_data,
        **_drink_summary_data,
        **_bust_vote_data,
        **_insurance_data,
        **_milestone_data,
        **_boj_data,
        **_dealer_lottery_data,
        **_targeted_drinking_data,
        **_connection_data,
        **_client_identity_data,
        "state_seq":            int(time.monotonic() * 1_000_000),
    }

    # Validate against the AppState schema -- raises immediately (rather than
    # reaching the frontend as a missing/misshapen field) if a bug ever makes
    # this dict drift from the documented contract in state_schema.py.
    return AppState(**state).model_dump()
