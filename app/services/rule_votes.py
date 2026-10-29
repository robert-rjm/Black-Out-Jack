"""
app/services/rule_votes.py
==========================
Players' say in the house rules (RuleToggles-SettingsModal.md §10).

* **Suggest.** A player suggests switching one rule on or off. By default
  the suggestion lands in the admin's inbox (📜 House rules), where one tap
  accepts it (queued like any admin change) or dismisses it.
* **Table votes.** Any player can ask the table to "vote on new rules". If
  a strict majority says Yes, rule voting is on: from then on a player's
  suggestion opens a table vote instead, and a passing vote queues the
  change for the next round with no admin step. The admin can switch rule
  voting off again (and can always edit the rules directly).

One vote is open at a time. Voters are the connected, non-spectator human
players (the same pool as a Targeted Drinking proposal). A vote passes the
moment a strict majority says Yes, fails the moment that's out of reach,
and otherwise fails when RULE_VOTE_WINDOW_SECONDS runs out. A failed
change vote freezes its proposer for RULE_VOTE_FREEZE_ROUNDS rounds.
"""

from __future__ import annotations

import time

from app.config import MAX_RULE_SUGGESTIONS, RULE_VOTE_FREEZE_ROUNDS, RULE_VOTE_WINDOW_SECONDS
from app.services.house_rules import queued_target, update_rules
from app.services.targeted_drinking import _target_proposal_eligible_names
from engine.rules_registry import LOCKED, RULES, RULES_BY_ID


def _voters(session) -> list[str]:
    return _target_proposal_eligible_names(session, "")


def _change_ids(session, rule_id: str, on: bool) -> tuple[list[str] | None, str | None]:
    """The IDs a suggestion touches: the rule, plus (when switching it on)
    any ancestors that are off, so the change takes effect. Error message
    instead when the rule can't be suggested."""
    if rule_id not in RULES_BY_ID:
        return None, "Unknown rule."
    if rule_id in LOCKED:
        return None, f"{RULES_BY_ID[rule_id].name} is part of the game itself."
    target = queued_target(session) or session.rules
    if (rule_id in target.enabled) == on:
        return None, f"{RULES_BY_ID[rule_id].name} is already {'on' if on else 'off'}."
    ids = {rule_id}
    if on:
        stack = list(RULES_BY_ID[rule_id].depends_on)
        while stack:
            cur = stack.pop()
            if cur not in ids and not target.on(cur):
                ids.add(cur)
                stack.extend(RULES_BY_ID[cur].depends_on)
    return [r.id for r in RULES if r.id in ids], None


def describe_change(ids: list[str], on: bool) -> str:
    names = " + ".join(RULES_BY_ID[i].name for i in ids)
    return f"{'switch on' if on else 'switch off'} {names}"


def _apply_change(session, ids: list[str], on: bool) -> None:
    key = "rules_on" if on else "rules_off"
    update_rules(session, {key: ids}, session._queued_settings)


def _log(session, text: str) -> None:
    session.round._log_entries.append(f"  📜 {text}\n")
    session._log_version += 1


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def suggest_rule(session, player_name: str, rule_id: str, on: bool) -> str | None:
    """A player suggests a change. Goes to a table vote when rule voting is
    on, else to the admin's inbox. Returns an error message or None."""
    ids, err = _change_ids(session, rule_id, on)
    if err:
        return err
    if session._rule_voting:
        return _open_vote(session, player_name, kind="change", ids=ids, on=on)
    # One suggestion per rule: a newer one replaces the older.
    session._rule_suggestions = [s for s in session._rule_suggestions if rule_id not in s["ids"]]
    session._rule_suggestions.append({"ids": ids, "on": on, "by": player_name})
    session._rule_suggestions = session._rule_suggestions[-MAX_RULE_SUGGESTIONS:]
    _log(session, f"{player_name} suggests: {describe_change(ids, on)}")
    return None


def answer_suggestion(session, index: int, accept: bool) -> str | None:
    """Admin accepts (queues) or dismisses suggestion ``index``."""
    if not 0 <= index < len(session._rule_suggestions):
        return "That suggestion is gone."
    sug = session._rule_suggestions.pop(index)
    if accept:
        # The rules may have moved since; switching an already-on rule on is harmless.
        _apply_change(session, sug["ids"], sug["on"])
    return None


# ---------------------------------------------------------------------------
# Table votes
# ---------------------------------------------------------------------------

def propose_rule_voting(session, player_name: str) -> str | None:
    """Ask the table to allow rule changes by vote."""
    if session._rule_voting:
        return "Rule changes already go to a table vote."
    return _open_vote(session, player_name, kind="enable", ids=[], on=True)


def _open_vote(session, proposer: str, *, kind: str, ids: list[str], on: bool) -> str | None:
    if session._pending_rule_vote is not None:
        return "A rule vote is already open."
    voters = _voters(session)
    me = next((n for n in voters if n.lower() == proposer.lower()), None)
    if me is None:
        return "Only connected players can start a rule vote."
    until = session._rule_vote_cooldowns.get(me.lower(), 0)
    if kind == "change" and session.round_count < until:
        return "Your last rule vote failed. Try again next round."
    votes = {n: None for n in voters}
    votes[me] = True   # proposing it is an automatic Yes
    session._pending_rule_vote = {
        "kind": kind, "ids": ids, "on": on, "proposer": me,
        "votes": votes, "expires_at": time.monotonic() + RULE_VOTE_WINDOW_SECONDS,
    }
    _maybe_resolve(session)
    return None


def cast_rule_vote(session, voter_name: str, vote: bool) -> bool:
    pending = session._pending_rule_vote
    if not pending:
        return False
    key = next((k for k in pending["votes"] if k.lower() == voter_name.lower()), None)
    if key is None:
        return False
    pending["votes"][key] = bool(vote)
    _maybe_resolve(session)
    return True


def _maybe_resolve(session) -> None:
    pending = session._pending_rule_vote
    if not pending:
        return
    votes = pending["votes"].values()
    total = len(pending["votes"])
    yes   = sum(1 for v in votes if v is True)
    open_ = sum(1 for v in votes if v is None)
    if yes > total / 2:
        _finish(session, passed=True)
    elif yes + open_ <= total / 2:
        _finish(session, passed=False)


def apply_rule_vote_forfeit(session) -> None:
    """Tick: a vote whose window ran out without a majority fails."""
    pending = session._pending_rule_vote
    if pending and time.monotonic() >= pending["expires_at"]:
        _finish(session, passed=False)


def _finish(session, *, passed: bool) -> None:
    pending = session._pending_rule_vote
    session._pending_rule_vote = None
    proposer = pending["proposer"]
    if pending["kind"] == "enable":
        if passed:
            session._rule_voting = True
            text = "The table voted to decide rule changes by vote"
        else:
            text = f"Vote to decide rule changes by vote failed ({proposer} asked)"
    else:
        what = describe_change(pending["ids"], pending["on"])
        if passed:
            _apply_change(session, pending["ids"], pending["on"])
            text = f"The table voted to {what}, from next round"
        else:
            session._rule_vote_cooldowns[proposer.lower()] = session.round_count + RULE_VOTE_FREEZE_ROUNDS
            text = f"Vote to {what} failed ({proposer} asked)"
    _log(session, text)
    session._rule_vote_seq += 1
    session._rule_vote_result = {"text": text, "passed": passed, "seq": session._rule_vote_seq}


def serialize_rule_votes(session, client_info: dict) -> dict:
    """The "rule_votes" block of /state."""
    pending = session._pending_rule_vote
    vote_out = None
    if pending and time.monotonic() < pending["expires_at"]:
        votes = pending["votes"]
        mine_lc = {n.lower() for n in (client_info.get("local_names") or
                   ([client_info["name"]] if client_info.get("name") else []))}
        my_key = next((n for n in votes if n.lower() in mine_lc), None)
        vote_out = {
            "kind":         pending["kind"],
            "ids":          list(pending["ids"]),
            "on":           pending["on"],
            "proposer":     pending["proposer"],
            "yes_count":    sum(1 for v in votes.values() if v is True),
            "no_count":     sum(1 for v in votes.values() if v is False),
            "total_voters": len(votes),
            "needed":       len(votes) // 2 + 1,
            "seconds_left": max(0, round(pending["expires_at"] - time.monotonic())),
            "eligible":     my_key is not None,
            "my_vote":      votes[my_key] if my_key else None,
        }
    is_admin = client_info.get("role") == "admin"
    return {
        "voting":      session._rule_voting,
        "pending":     vote_out,
        "result":      session._rule_vote_result,
        # The admin's inbox; other clients only need the count.
        "suggestions": [dict(s, ids=list(s["ids"])) for s in session._rule_suggestions] if is_admin else [],
        "suggestion_count": len(session._rule_suggestions),
    }
