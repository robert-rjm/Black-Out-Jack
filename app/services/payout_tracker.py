"""
app/services/payout_tracker.py
===============================
Cash wager / bankroll bookkeeping for Normal mode (drinking_mode = False).

Mirrors the shape of app/services/drink_tracker.py but tracks dollars instead
of sips: each player starts with a bankroll, bets a fixed amount per hand,
and wins/loses/pushes that amount (blackjack pays 3:2) at the end of each
round. Entirely inert in Drinking mode.
"""

from __future__ import annotations

from app.models.game_room import GameRoom


def init_bankrolls(session: GameRoom) -> None:
    """Seed each player's bankroll on the first round of a Normal-mode game.
    Safe to call repeatedly — only fills in players who don't have a balance
    yet (e.g. a seat added mid-session)."""
    for p in session.all_players:
        if p.name not in session._bankrolls:
            session._bankrolls[p.name] = session.starting_bankroll


MIN_BET = 2.5   # smallest bet step; mirrors /set_player_bet's clamp


def is_cash_mode(session: GameRoom) -> bool:
    """True when the cash bankroll system is active (Normal digital mode)."""
    return (not session.drinking_mode) and session.mode == "digital"


def stake_per_hand(session: GameRoom, player_name: str) -> float:
    """The per-hand bet for a player (custom bet if set, else table default)."""
    return getattr(session, "_player_bets", {}).get(player_name, session.bet_amount)


def can_afford_extra(session: GameRoom, player_name: str) -> bool:
    """True if the player can cover one more bet (double, split) right now.
    Always True outside Normal mode."""
    if not is_cash_mode(session):
        return True
    init_bankrolls(session)
    return (session._bankrolls.get(player_name, session.starting_bankroll)
            >= stake_per_hand(session, player_name))


def min_stake(session: GameRoom) -> float:
    """Smallest possible total stake for one round (min bet on every hand)."""
    return MIN_BET * max(1, session.num_hands)


def max_affordable_bet(session: GameRoom, player_name: str) -> float:
    """Largest per-hand bet (multiple of MIN_BET) the player can cover for a
    full round of ``num_hands`` hands. 0 if they can't cover the minimum."""
    init_bankrolls(session)
    bal = session._bankrolls.get(player_name, session.starting_bankroll)
    steps = int(bal // (max(1, session.num_hands) * MIN_BET))
    return steps * MIN_BET


def unaffordable_players(session: GameRoom) -> list[str]:
    """Humans who can't cover their opening stake. NPCs are topped up /
    their bet lowered automatically (see ensure_npc_stakes)."""
    init_bankrolls(session)
    out = []
    for p in session.all_players:
        stake = stake_per_hand(session, p.name) * max(1, session.num_hands)
        if session._bankrolls.get(p.name, session.starting_bankroll) < stake:
            out.append(p.name)
    return out


def ensure_npc_stakes(session: GameRoom) -> None:
    """Bots never get stuck: lower their bet to what they can afford, or
    re-buy when they can't cover even the minimum."""
    if not is_cash_mode(session):
        return
    init_bankrolls(session)
    for p in session.all_players:
        if not getattr(p, "is_npc", False):
            continue
        stake = stake_per_hand(session, p.name) * max(1, session.num_hands)
        bal   = session._bankrolls.get(p.name, session.starting_bankroll)
        if bal >= stake:
            continue
        affordable = max_affordable_bet(session, p.name)
        if affordable >= MIN_BET:
            session._player_bets[p.name] = affordable
        else:
            session._bankrolls[p.name] = session.starting_bankroll
            session._bank_run_players = [n for n in session._bank_run_players if n != p.name]
            session.round._log_entries.append(
                f"  💸 {p.name} hits the ATM and re-buys for ${session.starting_bankroll:.2f}\n")
            session._log_version += 1


def deduct_double_bet(session: GameRoom, player_name: str) -> None:
    """Deduct the extra bet when a hand doubles down. No-op outside Normal mode."""
    if not is_cash_mode(session):
        return
    session._bankrolls[player_name] = (
        session._bankrolls.get(player_name, session.starting_bankroll)
        - stake_per_hand(session, player_name)
    )


def deduct_bets(session: GameRoom) -> None:
    """Deduct the initial bet from every player's bankroll at deal time.

    Called from _cmd_deal_digital immediately after initial_deal so the
    bankroll badge drops by (bet_amount * num_hands) as soon as cards are
    dealt — reflecting that the stake is now 'at risk'.  The money is paid
    back (in full or with profit) by apply_payouts at endround.

    No-op in Drinking mode or referee mode.
    """
    if session.drinking_mode or session.mode != "digital":
        return
    init_bankrolls(session)
    _pbets = getattr(session, "_player_bets", {})
    for p in session.all_players:
        stake = _pbets.get(p.name, session.bet_amount) * max(1, session.num_hands)
        session._bankrolls[p.name] = (
            session._bankrolls.get(p.name, session.starting_bankroll) - stake
        )


def deduct_split_bet(session: GameRoom, player_name: str) -> None:
    """Deduct one additional bet when a player splits a hand.

    Splitting creates a second hand that requires its own equal bet, so the
    bankroll must drop by bet_amount at the moment the split is executed.
    apply_payouts will return the correct amount for each split hand at
    endround.  No-op in Drinking mode or referee mode.
    """
    if session.drinking_mode or session.mode != "digital":
        return
    _pbets = getattr(session, "_player_bets", {})
    pbet   = _pbets.get(player_name, session.bet_amount)
    session._bankrolls[player_name] = (
        session._bankrolls.get(player_name, session.starting_bankroll)
        - pbet
    )


def _hand_return(hand, bet: float) -> float:
    """Total $ paid back for one resolved hand at endround.

    The bet was already deducted upfront at deal/split time, so this is the
    'return' (not the net).  Subtracting bet from the return gives the net
    P/L per hand: win=+bet, push=0, loss=-bet.
    """
    result = getattr(hand, "result", None)
    if getattr(hand, "doubled", False):
        bet = bet * 2          # a doubled hand has twice the stake riding
    if result == "win":
        if hand.is_blackjack():
            return bet * 2.5   # bet back + 1.5× profit
        return bet * 2.0       # bet back + 1× profit
    if result == "push":
        return bet             # bet back, no profit
    # loss or unresolved → nothing returned (bet already gone)
    return 0.0


def apply_payouts(session: GameRoom) -> None:
    """Return staked bets (with profit where applicable) at round end.

    Called once per round from _resolve_endround(), right after
    cmd_endround().  Bets were deducted upfront by deduct_bets() /
    deduct_split_bet(), so this function only adds money back — the net
    bankroll change for the round is: return - stake_per_hand.

    No-op in Drinking mode or referee mode (cash wagers are a
    Normal/digital-mode-only feature).
    """
    if session.drinking_mode or session.mode != "digital":
        return

    init_bankrolls(session)

    _pbets  = getattr(session, "_player_bets", {})
    payouts: dict[str, float] = {}   # net P/L per player (for display / stats)

    for p in session.all_players:
        bet          = _pbets.get(p.name, session.bet_amount)
        total_return = 0.0
        net_display  = 0.0
        for hand in p.hands:
            ret          = _hand_return(hand, bet)
            stake        = bet * (2 if getattr(hand, "doubled", False) else 1)
            total_return += ret
            net_display  += ret - stake   # net per hand: win=+stake, push=0, loss=-stake

        # Pay back what was returned (may be 0 on a full-loss round)
        if total_return > 0:
            session._bankrolls[p.name] = (
                session._bankrolls.get(p.name, session.starting_bankroll)
                + total_return
            )

        if net_display != 0:
            payouts[p.name] = net_display

    # Settle bust-vote side bets (normal mode only — drinking mode uses sips instead).
    # Each player's own stake (their custom per-hand bet if set, else the table
    # default / 2) was already computed in apply_bust_vote_penalties and must be
    # read per-player here too -- using one shared amount for everyone previously
    # mismatched anyone with a custom bet (Code-Audit-2026-07.md #1).
    # Casino-standard 2:1 payout on a correct bust call.
    bust_result = session.round._bust_vote_result
    if bust_result and bust_result.get("side_bets"):
        side_bets = bust_result["side_bets"]
        for name in bust_result.get("winners", []):
            side_bet = side_bets.get(name, session.bet_amount / 2)
            # Stake was already deducted at vote time — return stake + 2:1 profit = 3× total
            ret_amt = side_bet * 3
            session._bankrolls[name] = session._bankrolls.get(name, session.starting_bankroll) + ret_amt
            net_profit = side_bet * 2
            payouts[name] = payouts.get(name, 0.0) + net_profit   # include in badge / stats
            session.round._log_entries.append(f"  {name} bust side bet: won +${net_profit:.2f} (2:1)\n")
            session._log_version += 1
        for name in bust_result.get("losers", []):
            side_bet = side_bets.get(name, session.bet_amount / 2)
            # Stake already gone — subtract from display so badge reflects the loss
            payouts[name] = payouts.get(name, 0.0) - side_bet
            session.round._log_entries.append(f"  {name} bust side bet: lost -${side_bet:.2f}\n")
            session._log_version += 1

    # Snapshot after side bets so badge and stats reflect total round P/L
    session._last_round_payouts = {k: v for k, v in payouts.items() if v != 0}

    # Track each player's best (biggest win) and worst (biggest loss) single round
    for name, net in payouts.items():
        rec = session._biggest_round_payouts.setdefault(name, {"best": 0.0, "worst": 0.0})
        if net > rec["best"]:
            rec["best"] = net
        if net < rec["worst"]:
            rec["worst"] = net

    # Round-end log lines, mirrored into the shared log so the UI's existing
    # log pipeline picks them up automatically.
    for p in session.all_players:
        net = payouts.get(p.name)
        if net is None:
            continue
        if net > 0:
            line = f"  {p.name} wins ${net:.2f}\n"
        else:
            line = f"  {p.name} loses ${abs(net):.2f}\n"
        session.round._log_entries.append(line)
        session._log_version += 1

    # Bank run detection — bankroll at or below $0
    floor    = min_stake(session)
    bank_run = [name for name, bal in session._bankrolls.items() if bal < floor]
    session._bank_run_players = bank_run


def cmd_rebuy(session: GameRoom, player_name: str) -> bool:
    """Reset a busted player's bankroll back to the starting amount.
    Returns True if the player was re-bought, False if they weren't eligible
    (not currently in a bank-run state)."""
    if player_name not in session._bank_run_players:
        return False
    # (a bank-run player can't cover even the minimum bet)
    session._bankrolls[player_name] = session.starting_bankroll
    session._bank_run_players = [n for n in session._bank_run_players if n != player_name]
    msg = f"  💸 {player_name} hits the ATM and re-buys for ${session.starting_bankroll:.2f}\n"
    session.round._log_entries.append(msg)
    session._log_version += 1
    return True
