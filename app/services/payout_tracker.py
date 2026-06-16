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


def _hand_payout(hand, bet: float) -> float:
    """Net $ change for one resolved hand."""
    result = getattr(hand, "result", None)
    if result == "win":
        if hand.is_blackjack():
            return bet * 1.5
        return bet
    if result == "loss":
        return -bet
    # push or unresolved -> no change
    return 0.0


def apply_payouts(session: GameRoom) -> None:
    """Settle this round's bets against each player's bankroll.

    Called once per round from _resolve_endround(), right after
    cmd_endround(). No-op in Drinking mode or referee mode (cash wagers are
    a Normal/digital-mode-only feature).
    """
    if session.drinking_mode or session.mode != "digital":
        return

    init_bankrolls(session)

    bet = session.bet_amount
    payouts: dict[str, float] = {}

    for p in session.all_players:
        net = 0.0
        for hand in p.hands:
            net += _hand_payout(hand, bet)
        if net != 0:
            payouts[p.name] = net
            session._bankrolls[p.name] = session._bankrolls.get(p.name, session.starting_bankroll) + net

    session._last_round_payouts = payouts

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
    bank_run = [name for name, bal in session._bankrolls.items() if bal <= 0]
    session._bank_run_players = bank_run


def cmd_rebuy(session: GameRoom, player_name: str) -> bool:
    """Reset a busted player's bankroll back to the starting amount.
    Returns True if the player was re-bought, False if they weren't eligible
    (not currently in a bank-run state)."""
    if player_name not in session._bank_run_players:
        return False
    session._bankrolls[player_name] = session.starting_bankroll
    session._bank_run_players = [n for n in session._bank_run_players if n != player_name]
    session.round._log_entries.append(f"  💸 {player_name} hits the ATM and re-buys for ${session.starting_bankroll:.2f}\n")
    session._log_version += 1
    return True
