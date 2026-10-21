"""
app/services/afk.py
====================
AFK handling outside the Targeted Drinking subgame:

* Presence -- every /state poll stamps ``session._client_last_seen``; a client
  that hasn't polled for AFK_DISCONNECT_SECONDS is treated as gone (closed tab,
  dead connection).
* Normal-round AFK -- if the seat whose turn it is belongs to a gone client,
  the admin absorbs the seat (``absorb_seat``), same mechanism Targeted
  Drinking's AFK rule uses.
* Admin-AFK vote -- while the game is blocked on the admin, every connected
  seated player can open a unanimous Yes/No vote that the admin is AFK. On a
  pass the route layer (app/routes/admin_transfer.py) hands the admin role over.
"""

from __future__ import annotations

import time

from app.config import (
    AFK_DISCONNECT_SECONDS, ADMIN_AFK_PROMPT_DELAY_SECONDS, ADMIN_AFK_VOTE_WINDOW_SECONDS,
)
from app.models.game_room import GameRoom
from app.services.round_state import round_phase, current_turn


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

def touch_client(session: GameRoom, client_id: str) -> None:
    if client_id and client_id in session._room_clients:
        session._client_last_seen[client_id] = time.monotonic()


def is_client_connected(session: GameRoom, client_id: str, now: float | None = None) -> bool:
    """True if the client polled within AFK_DISCONNECT_SECONDS. A client that
    has never been stamped counts as NOT connected (callers that must be
    conservative check for a missing entry themselves)."""
    seen = session._client_last_seen.get(client_id)
    if seen is None:
        return False
    return (now if now is not None else time.monotonic()) - seen < AFK_DISCONNECT_SECONDS


# ---------------------------------------------------------------------------
# Seat absorption (shared by Targeted Drinking AFK and normal-round AFK)
# ---------------------------------------------------------------------------

def _holds(info: dict, key: str) -> bool:
    return ((info.get("name") or "").lower() == key
            or any((n or "").lower() == key for n in (info.get("local_names") or [])))


def holds_human_seat(session: GameRoom, info: dict) -> bool:
    """True if this client controls at least one non-bot seat. Bots never
    vote and never count toward a vote's majority."""
    names = {(n or "").lower() for n in ([info.get("name")] + list(info.get("local_names") or [])) if n}
    return any(p.name.lower() in names and not getattr(p, "is_npc", False)
               for p in session.all_players)


def _admin_info(session: GameRoom) -> dict | None:
    return next((i for i in session._room_clients.values()
                 if i.get("role") == "admin" and not i.get("kicked")), None)


def _admin_cid(session: GameRoom) -> str | None:
    return next((cid for cid, i in session._room_clients.items()
                 if i.get("role") == "admin" and not i.get("kicked")), None)


def absorb_seat(session: GameRoom, name: str, context: str = "targeted_drinking") -> bool:
    """Moves `name`'s seat onto the admin's local_names (same mutation the
    seat-transfer and registration-approval flows in registration.py do) and
    reverts the original holder's client to spectator. Returns False,
    changing nothing, when there's no admin or the admin already holds the
    seat (admin AFK -- nobody to hand it to).

    `context` ("targeted_drinking" | "turn") only picks the wording of the
    one-shot afk_notice shown to the two affected clients."""
    key = name.lower()
    admin = _admin_info(session)
    if admin is None or _holds(admin, key):
        return False

    session._afk_notice_seq += 1
    seq = session._afk_notice_seq
    for info in session._room_clients.values():
        if info is admin or not _holds(info, key):
            continue
        if info.get("local_names"):
            info["local_names"] = [n for n in info["local_names"] if (n or "").lower() != key]
        if (info.get("name") or "").lower() == key:
            info["name"] = None
            info["role"] = "spectator"
        # One-shot message for the removed player's client (serializer's
        # "afk_notice"); cleared naturally when they re-register.
        info["afk_notice"] = {"reason": "afk_absorbed", "seat": name, "seq": seq, "context": context}

    admin_locals = list(admin.get("local_names") or [])
    if not admin_locals and admin.get("name"):
        admin_locals = [admin["name"]]   # seed so my_names keeps the admin's own seat
    admin_locals.append(name)
    admin["local_names"] = admin_locals
    admin["afk_notice"] = {"reason": "afk_absorbing", "seat": name, "seq": seq, "context": context}
    return True


# ---------------------------------------------------------------------------
# Normal-round AFK
# ---------------------------------------------------------------------------

def apply_normal_round_afk(session: GameRoom) -> None:
    """If the seat whose turn it is belongs to a disconnected (non-admin,
    human) client, hand that seat to the admin so the round can continue.
    Safe to call every tick."""
    if round_phase(session) != "playing":
        return
    turn = current_turn(session)
    if not turn:
        return
    player = session._get_player(turn)
    if player is None or getattr(player, "is_npc", False):
        return
    key = turn.lower()
    admin = _admin_info(session)
    if admin is None or _holds(admin, key):
        return
    holders = [cid for cid, info in session._room_clients.items()
               if not info.get("kicked") and _holds(info, key)]
    if not holders:
        return   # unclaimed seat -- not an AFK problem
    now = time.monotonic()
    for cid in holders:
        if cid not in session._client_last_seen:
            return   # never stamped -- can't tell gone from just-joined; be conservative
        if is_client_connected(session, cid, now):
            return   # someone holding this seat is still around
    if absorb_seat(session, turn, context="turn"):
        session.round._log_entries.append(
            f"  💤 {turn} disconnected on their turn — the host now plays their seat\n"
        )
        session._log_version += 1


# ---------------------------------------------------------------------------
# Admin-AFK vote
# ---------------------------------------------------------------------------

def admin_is_blocking(session: GameRoom) -> bool:
    """True when the game is waiting on something only the admin (or a seat
    they control) can do: their seat's turn, the dealer role while the
    round is between hands, or a pending registration request."""
    admin = _admin_info(session)
    if admin is None:
        return False
    names = {(n or "").lower() for n in (admin.get("local_names")
             or ([admin["name"]] if admin.get("name") else []))}
    if session._pending_registrations:
        return True
    phase = round_phase(session)
    if phase == "playing":
        turn = current_turn(session)
        return bool(turn) and turn.lower() in names
    if phase in ("pre-deal", "round-over"):   # dealer-ready is auto-played by tick
        return session.dealer_name.lower() in names
    return False


def track_admin_blocking(session: GameRoom) -> None:
    """Remember how long the admin has been holding the game up. The timer
    restarts whenever what we are waiting on changes (new round, new turn,
    new pending join request), so it measures one continuous wait."""
    if not admin_is_blocking(session):
        session._admin_blocking = None
        return
    sig = (session.round_count, round_phase(session), current_turn(session),
           bool(session._pending_registrations))
    cur = session._admin_blocking
    if cur is None or cur[0] != sig:
        session._admin_blocking = (sig, time.monotonic())


def admin_blocking_seconds(session: GameRoom) -> float:
    track_admin_blocking(session)
    cur = session._admin_blocking
    return 0.0 if cur is None else time.monotonic() - cur[1]


def eligible_voter_cids(session: GameRoom) -> list[str]:
    """Connected, seated, non-admin human clients -- the unanimity pool."""
    now = time.monotonic()
    admin_cid = _admin_cid(session)
    out = []
    for cid, info in session._room_clients.items():
        if cid == admin_cid or info.get("kicked") or info.get("role") != "player":
            continue
        if not info.get("name") or not is_client_connected(session, cid, now):
            continue
        if not holds_human_seat(session, info):
            continue
        out.append(cid)
    return out


def _finish(session: GameRoom, passed: bool, reason: str) -> None:
    pending = session.round._pending_admin_afk_vote
    session.round._pending_admin_afk_vote = None
    session._admin_afk_result_seq += 1
    session._admin_afk_last_result = {
        "passed": passed, "reason": reason,
        "opener": pending["opener"] if pending else "",
        "new_admin": None, "seq": session._admin_afk_result_seq,
    }
    session.round._log_entries.append(
        "  🚨 Admin-AFK vote passed — admin role is changing hands\n" if passed
        else f"  🚨 Admin-AFK vote failed ({reason})\n"
    )
    session._log_version += 1


def open_admin_afk_vote(session: GameRoom, client_id: str) -> tuple[bool, str, bool]:
    """Returns (ok, error, passed). `passed` is True only if the opener was
    the sole eligible voter, so unanimity was met on the spot."""
    if session.round._pending_admin_afk_vote:
        return False, "An admin-AFK vote is already open.", False
    admin_cid = _admin_cid(session)
    if admin_cid is None or client_id == admin_cid:
        return False, "No admin to vote on.", False
    voters = eligible_voter_cids(session)
    if client_id not in voters:
        return False, "Only connected, seated players can start this vote.", False
    if not admin_is_blocking(session):
        return False, "The game isn't waiting on the admin right now.", False
    if admin_blocking_seconds(session) < ADMIN_AFK_PROMPT_DELAY_SECONDS:
        return False, (f"Give the admin a moment -- this can be started after "
                       f"{ADMIN_AFK_PROMPT_DELAY_SECONDS} seconds of waiting."), False
    info = session._room_clients[client_id]
    votes = {cid: None for cid in voters}
    votes[client_id] = True   # opener's own vote is pre-filled Yes
    session.round._pending_admin_afk_vote = {
        "opener": info["name"],
        "expires_at": time.monotonic() + ADMIN_AFK_VOTE_WINDOW_SECONDS,
        "votes": votes,
    }
    session.round._log_entries.append(f"  🚨 {info['name']} started a vote: is the admin AFK?\n")
    session._log_version += 1
    if all(v is True for v in votes.values()):
        _finish(session, True, "unanimous")
        return True, "", True
    return True, "", False


def cast_admin_afk_vote(session: GameRoom, client_id: str, vote: bool) -> tuple[bool, str, str | None]:
    """Returns (ok, error, outcome) with outcome None | "passed" | "failed"."""
    pending = session.round._pending_admin_afk_vote
    if not pending:
        return False, "No admin-AFK vote is open.", None
    if client_id not in pending["votes"]:
        return False, "You're not eligible to vote on this.", None
    pending["votes"][client_id] = bool(vote)
    if not vote:
        _finish(session, False, "someone voted no")
        return True, "", "failed"
    if all(v is True for v in pending["votes"].values()):
        _finish(session, True, "unanimous")
        return True, "", "passed"
    return True, "", None


def apply_admin_afk_vote_forfeit(session: GameRoom) -> None:
    """Fails the vote when its window expires, or when the admin is no
    longer blocking the game (they came back and acted). Safe every tick."""
    pending = session.round._pending_admin_afk_vote
    if not pending:
        return
    if time.monotonic() >= pending["expires_at"]:
        _finish(session, False, "timed out")
    elif not admin_is_blocking(session):
        _finish(session, False, "admin is back")


def serialize_admin_afk_vote(session: GameRoom, client_id: str) -> dict:
    """The "admin_afk_vote" block of /state for this client."""
    pending = session.round._pending_admin_afk_vote
    now = time.monotonic()
    out_pending = None
    if pending and now < pending["expires_at"]:
        votes = pending["votes"]
        out_pending = {
            "opener":       pending["opener"],
            "yes_count":    sum(1 for v in votes.values() if v is True),
            "no_count":     sum(1 for v in votes.values() if v is False),
            "total_voters": len(votes),
            "seconds_left": max(0, round(pending["expires_at"] - now)),
            "my_vote":      votes.get(client_id),
            "eligible":     client_id in votes,
        }
    can_open = (
        out_pending is None
        and client_id in eligible_voter_cids(session)
        and admin_is_blocking(session)
        and admin_blocking_seconds(session) >= ADMIN_AFK_PROMPT_DELAY_SECONDS
    )
    return {
        "pending":     out_pending,
        "can_open":    can_open,
        "last_result": session._admin_afk_last_result,
        "result_seq":  session._admin_afk_result_seq,
    }
