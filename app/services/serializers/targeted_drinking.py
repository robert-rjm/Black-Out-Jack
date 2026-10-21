"""
app/services/serializers/targeted_drinking.py
============================================
Targeted Drinking (round, proposal, summary) snapshot helpers, split out of serializer.py.
"""

import time



def _serialize_pending_targeted_drinking(pending: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending Targeted Drinking Mode vote window (Rules.md §5.10).

    Returns None when there is no pending mini-round or its vote window has
    expired. ``my_vote`` reveals only this client's own primary-name vote
    (mirrors cast_bust_vote's single-seat convention) -- local multiplayer
    with more than one targeted seat reads each target's vote from
    ``votes_cast`` instead, same as Dealer Lottery's own ``my_entries`` vs.
    the plain entry count.
    """
    if not pending or time.monotonic() >= pending["expires_at"]:
        return None
    votes   = pending["votes"]
    my_name = (client_info.get("name") or "").capitalize()
    return {
        "seconds_left": max(0, round(pending["expires_at"] - time.monotonic())),
        "my_vote":      votes.get(my_name),
        "votes_cast":   {n: v for n, v in votes.items() if v is not None},
    }


def _serialize_last_targeted_drinking_result(result: dict | None) -> dict | None:
    """Serialize the most recently resolved Targeted Drinking mini-round
    for the frontend. Returns None if there is no result or it is older
    than 90 seconds (matches _serialize_last_dealer_lottery_result's
    dismissal window)."""
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "hand":        dict(result["hand"]),
        "votes":       dict(result["votes"]),
        "correct":     dict(result["correct"]),
        "streaks":     dict(result["streaks"]),
        "graduated":   list(result["graduated"]),
        "capped_out":  list(result.get("capped_out", [])),
        "sips":        dict(result["sips"]),
        "seconds_ago": max(0, round(time.monotonic() - result["set_at"])),
    }


def _serialize_targeted_drinking_summary(summary: dict | None) -> dict | None:
    """Serialize the most recent Targeted Drinking Mode subgame-ending
    recap (reason + total sips per target, plus the run's final
    statistics table). Returns None if there is no summary yet or it's
    older than 90 seconds (same dismissal window as the per-mini-round
    result)."""
    if not summary or time.monotonic() - summary["set_at"] >= 90:
        return None
    return {
        "reason": summary["reason"],
        "totals": dict(summary["totals"]),
        "stats": {
            "correct":      dict(summary.get("correct", {})),
            "wrong":        dict(summary.get("wrong", {})),
            "dealer_hands": summary.get("dealer_hands", 0),
            "dealer_busts": summary.get("dealer_busts", 0),
        },
    }


def _serialize_pending_target_proposal(pending: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending majority-vote-to-target proposal (tap a
    player's name at the table). Returns None once its vote window has
    expired -- apply_target_proposal_vote_forfeit clears it on the very
    next tick, so this is mostly a belt-and-suspenders check."""
    if not pending or time.monotonic() >= pending["expires_at"]:
        return None
    votes = pending["votes"]
    total = len(votes)
    yes   = sum(1 for v in votes.values() if v is True)
    no    = sum(1 for v in votes.values() if v is False)
    my_names_lc = {n.lower() for n in (client_info.get("local_names") or
                   ([client_info["name"]] if client_info.get("name") else []))}
    my_vote  = None
    eligible = False
    for name, v in votes.items():
        if name.lower() in my_names_lc:
            my_vote  = v
            eligible = True
            break
    return {
        "target":       pending["target"],
        "proposer":     pending["proposer"],
        "yes_count":    yes,
        "no_count":     no,
        "total_voters": total,
        "needed":       total // 2 + 1,
        "seconds_left": max(0, round(pending["expires_at"] - time.monotonic())),
        "my_vote":      my_vote,
        # False for the proposed target themselves (excluded from voting on
        # their own proposal) or anyone not in the eligible-voter pool (e.g.
        # a spectator, or a client that connected after the vote opened) --
        # lets the frontend show a read-only view instead of Yes/No buttons
        # it would just reject.
        "eligible":     eligible,
    }


def _serialize_last_target_proposal_result(result: dict | None) -> dict | None:
    """Serialize the most recently resolved target proposal (pass/fail).
    Returns None if there is none yet or it's older than 15 seconds -- this
    is a brief pass/fail flash, not a lasting result like the mini-round
    reveal, so it dismisses itself much sooner."""
    if not result or time.monotonic() - result["set_at"] >= 15:
        return None
    return {
        "target":     result["target"],
        "proposer":   result["proposer"],
        "passed":     result["passed"],
        "seconds_ago": max(0, round(time.monotonic() - result["set_at"])),
    }


# ---------------------------------------------------------------------------
# Bust-vote window helper
# ---------------------------------------------------------------------------
