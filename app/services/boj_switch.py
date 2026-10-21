"""
app/services/boj_switch.py
===========================
"Switch to BOJ" poll for Normal-mode tables.

Any seated human can ask the table to switch to Black(Out)Jack (Drinking mode).
Every connected, non-spectator human seat votes Yes/No:

* **Majority Yes** -- the whole table switches (queued for the next round,
  same room, same seats).
* **Otherwise** -- the table stays Normal and only the Yes voters leave to a
  brand-new Drinking room. Each mover first gets a short cancel modal; after
  it, their client is pre-registered in the new room (no re-entering a name)
  and their seats are removed from the old table at its next round.

The poll resolves the moment the outcome is decided (strict majority Yes, or
majority no longer reachable), or when its window runs out. Unanswered voters
count as staying.
"""

from __future__ import annotations

import time

from app.config import (
    BOJ_POLL_WINDOW_SECONDS, BOJ_SPLIT_GRACE_SECONDS, BOJ_SPLIT_PLAN_TTL_SECONDS,
    DEFAULT_WAGER, DEFAULT_NUM_HANDS,
)
from app.models.game_room import GameRoom
from app.services.session_store import game_sessions, reserve_room

RESULT_FLASH_SECONDS = 15


# ---------------------------------------------------------------------------
# Poll
# ---------------------------------------------------------------------------

def eligible_voter_names(session: GameRoom) -> list[str]:
    """Connected, non-spectator, non-bot seats (canonical roster casing)."""
    connected_lc = {
        (v.get("name") or "").lower()
        for v in session._room_clients.values()
        if not v.get("kicked") and v.get("name") and v.get("role") != "spectator"
    }
    return [p.name for p in session.all_players
            if not getattr(p, "is_npc", False) and p.name.lower() in connected_lc]


def start_boj_poll(session: GameRoom, proposer_name: str) -> tuple[bool, str | None]:
    """Open the poll. The proposer's own vote is pre-filled Yes."""
    if session.drinking_mode:
        return False, "This table is already in Drinking mode."
    if session.mode != "digital":
        return False, "Switching is only available in digital games."
    if session._boj_poll is not None or session._boj_split is not None:
        return False, "A switch vote is already in progress."
    eligible = eligible_voter_names(session)
    proposer = next((n for n in eligible if n.lower() == proposer_name.lower()), None)
    if proposer is None:
        return False, "You must be a connected, seated player to start this vote."

    votes = {n: None for n in eligible}
    votes[proposer] = True
    session._boj_poll = {
        "proposer":   proposer,
        "votes":      votes,
        "expires_at": time.monotonic() + BOJ_POLL_WINDOW_SECONDS,
    }
    session.round._log_entries.append(f"  🍻 {proposer} asked the table to switch to BOJ\n")
    session._log_version += 1
    _maybe_resolve(session)
    return True, None


def submit_boj_vote(session: GameRoom, voter_name: str, vote: bool) -> bool:
    poll = session._boj_poll
    if not poll:
        return False
    key = next((k for k in poll["votes"] if k.lower() == voter_name.lower()), None)
    if key is None:
        return False
    poll["votes"][key] = bool(vote)
    _maybe_resolve(session)
    return True


def tally(poll: dict) -> tuple[int, int, int]:
    """(yes, no, undecided)."""
    votes = poll["votes"]
    yes = sum(1 for v in votes.values() if v is True)
    no  = sum(1 for v in votes.values() if v is False)
    return yes, no, len(votes) - yes - no


def _maybe_resolve(session: GameRoom) -> None:
    poll = session._boj_poll
    if not poll:
        return
    total = len(poll["votes"])
    yes, no, _undecided = tally(poll)
    if total and yes > total / 2:
        _finish(session)            # strict majority: whole table switches
    elif no >= total / 2:
        _finish(session)            # majority is out of reach: Yes voters split off


def apply_boj_poll_forfeit(session: GameRoom) -> None:
    """Resolve an expired poll on whatever votes were cast. Safe every tick."""
    poll = session._boj_poll
    if poll and time.monotonic() >= poll["expires_at"]:
        _finish(session)


def _finish(session: GameRoom) -> None:
    poll = session._boj_poll
    if not poll:
        return
    session._boj_poll = None
    total = len(poll["votes"])
    yes, _no, _undecided = tally(poll)
    yes_names = [n for n, v in poll["votes"].items() if v is True]
    now = time.monotonic()

    if total and yes > total / 2:
        session._queued_settings["drinking_mode"] = True
        session.round._log_entries.append("  🍻 The table voted to switch to BOJ -- from next round\n")
        session._boj_last_result = {"kind": "table", "names": yes_names, "set_at": now}
    elif yes_names:
        plan = _plan_split(session, yes_names)
        if plan:
            session._boj_split = plan
            session.round._log_entries.append(
                f"  🍻 {', '.join(yes_names)} will start a new BOJ table\n")
            session._boj_last_result = {"kind": "split", "names": yes_names, "set_at": now}
        else:
            session._boj_last_result = {"kind": "none", "names": [], "set_at": now}
    else:
        session._boj_last_result = {"kind": "none", "names": [], "set_at": now}
    session._log_version += 1


# ---------------------------------------------------------------------------
# Split into a new room
# ---------------------------------------------------------------------------

def _plan_split(session: GameRoom, yes_names: list[str]) -> dict | None:
    """Map each Yes seat to its client and reserve the new room's code."""
    seat_names = {p.name.lower(): p.name for p in session.all_players
                  if not getattr(p, "is_npc", False)}
    clients: dict[str, list[str]] = {}
    for name in yes_names:
        cid = next((c for c, v in session._room_clients.items()
                    if not v.get("kicked") and (v.get("name") or "").lower() == name.lower()),
                   None)
        if cid is None or cid in clients:
            continue
        info  = session._room_clients[cid]
        seats = [seat_names[s.lower()] for s in (info.get("local_names") or [info["name"]])
                 if s.lower() in seat_names]
        if seats:
            clients[cid] = seats
    if not clients:
        return None
    now = time.monotonic()
    return {
        "new_room":   reserve_room(),
        "clients":    clients,                      # client_id -> seats that move with it
        "go_at":      now + BOJ_SPLIT_GRACE_SECONDS,
        "expires_at": now + BOJ_SPLIT_PLAN_TTL_SECONDS,
        "cancelled":  set(),
        "moved":      set(),
        "built":      False,
    }


def cancel_split(session: GameRoom, client_id: str) -> bool:
    """A mover backs out during the cancel window. False once too late."""
    plan = session._boj_split
    if not plan or client_id not in plan["clients"] or plan["built"]:
        return False
    if time.monotonic() >= plan["go_at"]:
        return False
    plan["cancelled"].add(client_id)
    if len(plan["cancelled"]) >= len(plan["clients"]):
        game_sessions.pop(plan["new_room"], None)   # nobody left to move
        session._boj_split = None
    return True


def go_split(session: GameRoom, client_id: str) -> str | None:
    """A mover's redirect once the cancel window has passed. Builds the new
    room on the first call, registers this client in it, and takes their seats
    out of the old table. Returns the new room code, or None if not allowed."""
    plan = session._boj_split
    if (not plan or client_id not in plan["clients"]
            or client_id in plan["cancelled"]
            or time.monotonic() < plan["go_at"]):
        return None
    with session._registry_lock:
        if not plan["built"]:
            _build_new_room(session, plan)
        if client_id not in plan["moved"]:
            _leave_old_room(session, client_id, plan["clients"][client_id])
            plan["moved"].add(client_id)
        active = [c for c in plan["clients"] if c not in plan["cancelled"]]
        if all(c in plan["moved"] for c in active):
            session._boj_split = None
    return plan["new_room"]


def _build_new_room(session: GameRoom, plan: dict) -> None:
    from app.services.room_factory import build_game_room   # lazy: factory imports a lot

    active = {c: s for c, s in plan["clients"].items() if c not in plan["cancelled"]}
    # The old admin stays admin if they're moving, otherwise the first mover.
    admin_cid = next((c for c in active
                      if session._room_clients.get(c, {}).get("role") == "admin"),
                     next(iter(active)))
    order = [admin_cid] + [c for c in active if c != admin_cid]
    names = [n for c in order for n in active[c]]

    room, _output = build_game_room(
        plan["new_room"], admin_cid, names, set(), {}, names[0],
        mode="digital", drinking=True, wager=DEFAULT_WAGER, num_hands=DEFAULT_NUM_HANDS,
        bet_amount=session.bet_amount, starting_bankroll=session.starting_bankroll,
        num_decks=2 if len(names) >= 4 else 1,
        bust_vote_enabled=session.bust_vote_enabled, easy_mode=session.easy_mode,
    )
    for cid in order:
        seats = active[cid]
        room._room_clients[cid] = {
            "name": seats[0], "local_names": list(seats), "kicked": False,
            "role": "admin" if cid == admin_cid else "player",
        }
    plan["built"] = True


def _leave_old_room(session: GameRoom, client_id: str, seats: list[str]) -> None:
    """Mirror /leave_room, and queue the mover's seats for removal at the
    old table's next round (a dealer seat hands the deal on first)."""
    from app.routes.admin import _auto_transfer_admin   # lazy: routes import services

    clients = session._room_clients
    if clients.get(client_id, {}).get("role") == "admin":
        _auto_transfer_admin(session, client_id)
    clients.pop(client_id, None)
    session._pending_registrations = [
        r for r in session._pending_registrations if r["client_id"] != client_id]
    removes = session._queued_settings.setdefault("remove_players", [])
    removes.extend(n for n in seats if n not in removes)


def apply_boj_split_expiry(session: GameRoom) -> None:
    """Drop a split plan nobody acted on. Safe every tick."""
    plan = session._boj_split
    if plan and time.monotonic() >= plan["expires_at"]:
        if not plan["built"]:
            game_sessions.pop(plan["new_room"], None)
        session._boj_split = None
