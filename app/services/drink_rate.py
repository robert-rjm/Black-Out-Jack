"""
app/services/drink_rate.py
===========================
Drink Rate Mode (docs/planning/DrinkTypeMode.md): each seat has a rate that
scales the sips it drinks (engine/drink_rate.py does the maths inside
Player.add_drink / award_sips). This module owns the rules for *who may
change a rate*:

* Drinking more is always the player's own call: any change to a rate that
  is >= 1.0, or >= their current rate, is free (no vote).
* Drinking less (a discount) needs the admin to propose it and a strict
  majority of connected seated players to agree. The beneficiary votes too.
* A player who normalizes to 1.0 is protected for DRINK_RATE_PROTECTION_ROUNDS
  rounds: no new rate can be voted onto them in that window unless they
  explicitly vote Yes themselves.
* Changes land at the next round (immediately if the room is still pre-deal).
* Bots follow the table: they take a rate only when every human seat shares
  the same one (derived in sync_drink_rates, never stored).
"""

from __future__ import annotations

import time

from app.config import DRINK_RATE_PROTECTION_ROUNDS, DRINK_RATE_VOTE_WINDOW_SECONDS
from app.models.game_room import GameRoom
from app.services.afk import is_client_connected
from app.services.serializer import round_phase
from engine.drink_rate import (
    ALLOWED_RATES, PRESETS, RATE_DEFAULT, normalize_rate,
)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _player(session: GameRoom, name: str):
    key = (name or "").lower()
    return next((p for p in session.all_players if p.name.lower() == key), None)


def _humans(session: GameRoom) -> list:
    return [p for p in session.all_players if not getattr(p, "is_npc", False)]


def _holders(session: GameRoom, seat: str) -> list[str]:
    """client_ids that control `seat` (primary name or local_names)."""
    key = seat.lower()
    out = []
    for cid, info in session._room_clients.items():
        if info.get("kicked") or info.get("role") not in ("admin", "player"):
            continue
        if ((info.get("name") or "").lower() == key
                or any((n or "").lower() == key for n in (info.get("local_names") or []))):
            out.append(cid)
    return out


def planned_rate(session: GameRoom, player) -> float:
    return session._drink_rate_queued.get(player.name.lower(), player.drink_rate)


def protection_rounds_left(session: GameRoom, name: str) -> int:
    through = session._drink_rate_protected_through.get(name.lower())
    if through is None:
        return 0
    return max(0, through - session.round_count) if session.round_count <= through else 0


def is_protected(session: GameRoom, name: str) -> bool:
    through = session._drink_rate_protected_through.get(name.lower())
    return through is not None and session.round_count <= through


def rate_label(rate: float) -> str:
    for label, r in PRESETS.items():
        if r == rate and label != "beer":
            return f"{label} ({rate}x)"
    return f"{rate}x"


# ---------------------------------------------------------------------------
# Applying rates
# ---------------------------------------------------------------------------

def sync_drink_rates(session: GameRoom) -> None:
    """Set every Player's effective_drink_rate: humans use their own rate,
    bots use the table's rate only if all humans share one (else 1.0)."""
    humans = _humans(session)
    for p in humans:
        p.effective_drink_rate = p.drink_rate
    shared = {p.drink_rate for p in humans}
    bot_rate = next(iter(shared)) if len(shared) == 1 else RATE_DEFAULT
    for p in session.all_players:
        if getattr(p, "is_npc", False):
            p.effective_drink_rate = bot_rate


def _schedule_rate(session: GameRoom, player, rate: float) -> None:
    """Pre-deal: apply now. Otherwise queue for the next round."""
    key = player.name.lower()
    if round_phase(session) == "pre-deal":
        player.drink_rate = rate
        session._drink_rate_queued.pop(key, None)
        sync_drink_rates(session)
    elif rate == player.drink_rate:
        session._drink_rate_queued.pop(key, None)
    else:
        session._drink_rate_queued[key] = rate


def apply_queued_rates(session: GameRoom) -> None:
    """Called from reset_round_state: queued rates take effect at round start."""
    queued = session._drink_rate_queued
    if not queued:
        return
    for key, rate in list(queued.items()):
        p = _player(session, key)
        if p is not None and p.drink_rate != rate:
            p.drink_rate = rate
            session.round._log_entries.append(f"  🍷 {p.name} now drinks at {rate_label(rate)}\n")
            session._log_version += 1
    session._drink_rate_queued = {}
    sync_drink_rates(session)


# ---------------------------------------------------------------------------
# Player's own changes (no vote when drinking more)
# ---------------------------------------------------------------------------

def set_own_rate(session: GameRoom, client_id: str, seat: str, raw_rate) -> tuple[bool, str]:
    rate = normalize_rate(raw_rate)
    if rate is None:
        return False, f"Rate must be one of {', '.join(str(r) for r in ALLOWED_RATES)}."
    info = session._room_clients.get(client_id) or {}
    if client_id not in _holders(session, seat):
        return False, "You can only change the rate of a seat you control."
    p = _player(session, seat)
    if p is None or getattr(p, "is_npc", False):
        return False, "No such player seat."
    current = planned_rate(session, p)
    if rate == current:
        return True, ""
    if rate < 1.0 and rate < current:
        return False, ("Drinking less than you do now needs the table's approval -- "
                       "ask the admin to propose it.")
    if rate == 1.0:
        session._drink_rate_protected_through[p.name.lower()] = (
            session.round_count + DRINK_RATE_PROTECTION_ROUNDS
        )
    _schedule_rate(session, p, rate)
    session.round._log_entries.append(f"  🍷 {p.name} will drink at {rate_label(rate)}\n")
    session._log_version += 1
    return True, ""


# ---------------------------------------------------------------------------
# Admin proposal + majority vote
# ---------------------------------------------------------------------------

def _voter_cids(session: GameRoom) -> list[str]:
    out = []
    for cid, info in session._room_clients.items():
        if info.get("kicked") or info.get("role") not in ("admin", "player") or not info.get("name"):
            continue
        if info.get("role") == "admin" or is_client_connected(session, cid):
            out.append(cid)
    return out


def open_rate_proposal(session: GameRoom, client_id: str, seats, raw_rate) -> tuple[bool, str]:
    """`seats` is "all" or a list of seat names."""
    info = session._room_clients.get(client_id) or {}
    if info.get("role") != "admin":
        return False, "Only the admin can propose a rate."
    if session.round._pending_rate_proposal:
        return False, "A rate proposal is already being voted on."
    rate = normalize_rate(raw_rate)
    if rate is None:
        return False, f"Rate must be one of {', '.join(str(r) for r in ALLOWED_RATES)}."

    if seats == "all":
        candidates = _humans(session)
    else:
        candidates = [p for p in (_player(session, n) for n in (seats or [])) if p is not None]
        candidates = [p for p in candidates if not getattr(p, "is_npc", False)]
    if not candidates:
        return False, "Pick at least one player."
    changing = [p for p in candidates if planned_rate(session, p) != rate]
    if not changing:
        return False, "Nobody's rate would change."

    voters = _voter_cids(session)
    if client_id not in voters:
        voters.append(client_id)

    targets, required = [], []
    for p in changing:
        if is_protected(session, p.name):
            holders = [c for c in _holders(session, p.name) if c in voters]
            if not holders:
                continue   # protected and unreachable -- skip rather than block the rest
            required.append(holders[0])
        targets.append(p.name)
    if not targets:
        return False, "Everyone picked is protected right now (they reset to 1.0 recently)."

    votes = {cid: None for cid in voters}
    votes[client_id] = True   # the proposer's own vote is pre-filled Yes
    session.round._pending_rate_proposal = {
        "proposer": info["name"], "rate": rate, "targets": targets,
        "expires_at": time.monotonic() + DRINK_RATE_VOTE_WINDOW_SECONDS,
        "votes": votes, "required": required,
    }
    session.round._log_entries.append(
        f"  🍷 {info['name']} proposes {rate_label(rate)} for {', '.join(targets)}\n"
    )
    session._log_version += 1
    _evaluate(session)
    return True, ""


def cast_rate_vote(session: GameRoom, client_id: str, vote: bool) -> tuple[bool, str]:
    pending = session.round._pending_rate_proposal
    if not pending:
        return False, "No rate proposal is open."
    if client_id not in pending["votes"]:
        return False, "You're not eligible to vote on this."
    pending["votes"][client_id] = bool(vote)
    _evaluate(session)
    return True, ""


def _evaluate(session: GameRoom) -> None:
    p = session.round._pending_rate_proposal
    if not p:
        return
    votes = p["votes"]
    n = len(votes)
    yes = sum(1 for v in votes.values() if v is True)
    no = sum(1 for v in votes.values() if v is False)
    if any(votes.get(c) is False for c in p["required"]):
        _finish(session, False, "a protected player voted no")
    elif yes * 2 > n and all(votes.get(c) is True for c in p["required"]):
        _finish(session, True, "majority")
    elif no * 2 >= n:
        _finish(session, False, "not enough votes")


def apply_drink_rate_forfeit(session: GameRoom) -> None:
    """Fails an open proposal whose window ran out. Safe every tick."""
    p = session.round._pending_rate_proposal
    if p and time.monotonic() >= p["expires_at"]:
        _finish(session, False, "timed out")


def _finish(session: GameRoom, passed: bool, reason: str) -> None:
    p = session.round._pending_rate_proposal
    session.round._pending_rate_proposal = None
    session._drink_rate_result_seq += 1
    session._drink_rate_last_result = {
        "passed": passed, "reason": reason, "proposer": p["proposer"],
        "rate": p["rate"], "targets": list(p["targets"]),
        "seq": session._drink_rate_result_seq,
    }
    if passed:
        for name in p["targets"]:
            player = _player(session, name)
            if player is not None:
                _schedule_rate(session, player, p["rate"])
        session.round._log_entries.append(
            f"  🍷 Rate vote passed: {', '.join(p['targets'])} -> {rate_label(p['rate'])}\n"
        )
    else:
        session.round._log_entries.append(f"  🍷 Rate vote failed ({reason})\n")
    session._log_version += 1


# ---------------------------------------------------------------------------
# State for /state
# ---------------------------------------------------------------------------

def serialize_drink_rates(session: GameRoom, client_id: str) -> dict:
    now = time.monotonic()
    seats = []
    for p in session.all_players:
        queued = session._drink_rate_queued.get(p.name.lower())
        seats.append({
            "name": p.name,
            "rate": p.drink_rate,
            "effective_rate": p.effective_drink_rate,
            "queued_rate": queued,
            "protected_rounds_left": protection_rounds_left(session, p.name),
            "is_bot": bool(getattr(p, "is_npc", False)),
        })

    pending = session.round._pending_rate_proposal
    out_pending = None
    if pending and now < pending["expires_at"]:
        votes = pending["votes"]
        out_pending = {
            "proposer": pending["proposer"],
            "rate": pending["rate"],
            "targets": list(pending["targets"]),
            "yes_count": sum(1 for v in votes.values() if v is True),
            "no_count": sum(1 for v in votes.values() if v is False),
            "total_voters": len(votes),
            "seconds_left": max(0, round(pending["expires_at"] - now)),
            "my_vote": votes.get(client_id),
            "eligible": client_id in votes,
            "needs_my_yes": client_id in pending["required"],
        }
    return {
        "seats": seats,
        "pending": out_pending,
        "last_result": session._drink_rate_last_result,
        "result_seq": session._drink_rate_result_seq,
        "allowed_rates": list(ALLOWED_RATES),
        "presets": dict(PRESETS),
        "protection_rounds": DRINK_RATE_PROTECTION_ROUNDS,
    }
