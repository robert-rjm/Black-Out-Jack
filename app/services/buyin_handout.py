"""
app/services/buyin_handout.py
==============================
Optional Normal-mode perk: at the end of each round, every player whose
bankroll is above the starting buy-in gets to hand out a sip. Bots hand theirs
out straight away; humans pick a recipient in the give panel (or pass).

Deliberately separate from the Drinking-mode sip ledger: Normal mode never
records sips, so this only writes round-log lines and is gated behind the
``buyin_handouts`` setting (off by default). Unclaimed handouts lapse when the
next round starts (RoundState is replaced then).
"""

from __future__ import annotations

from app.models.game_room import GameRoom
from app.services.payout_tracker import init_bankrolls, is_cash_mode

BUYIN_HANDOUT_SIPS = 1


def compute_buyin_handouts(session: GameRoom) -> None:
    """Snapshot who earned a handout this round. Call after apply_payouts."""
    session.round._buyin_pending = {}
    session.round._buyin_given = set()
    if not (is_cash_mode(session) and session.buyin_handouts):
        return
    init_bankrolls(session)
    for p in session.all_players:
        if session._bankrolls.get(p.name, session.starting_bankroll) <= session.starting_bankroll:
            continue
        session.round._buyin_pending[p.name] = BUYIN_HANDOUT_SIPS
    # Bots never wait for a click: hand to the next seat that isn't themselves.
    names = [p.name for p in session.all_players]
    for p in session.all_players:
        if p.name in session.round._buyin_pending and getattr(p, "is_npc", False):
            others = [n for n in names if n != p.name]
            if others:
                give_buyin_sip(session, p.name, others[session.round_count % len(others)])


def give_buyin_sip(session: GameRoom, giver: str, recipient: str | None) -> bool:
    """Giver hands their sip(s) to ``recipient``; ``None`` passes the handout.
    False if there's nothing pending for this giver or the recipient is invalid."""
    amount = session.round._buyin_pending.get(giver)
    if not amount or giver in session.round._buyin_given:
        return False
    if recipient is not None:
        if recipient.lower() == giver.lower():
            return False
        if not any(p.name == recipient for p in session.all_players):
            return False
        session.round._log_entries.append(
            f"  🍻 {giver} is above the buy-in and hands {amount} sip(s) to {recipient}\n")
        session._log_version += 1
    session.round._buyin_given.add(giver)
    return True
