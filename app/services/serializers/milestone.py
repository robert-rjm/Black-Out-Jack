"""
app/services/serializers/milestone.py
====================================
Milestone snapshot helpers, split out of serializer.py.
"""

import time




def _serialize_last_milestone(result: dict | None) -> dict | None:
    """Serialize the most recent completed milestone for the frontend.

    Returns None if there is no result or it is older than 90 seconds
    (the frontend dismisses the toast after that window anyway).
    """
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "winner":      result["winner"],
        "boundary":    result["boundary"],
        "allocations": result["allocations"],
        "seconds_ago": max(0, round(time.monotonic() - result["set_at"])),
    }


def _serialize_pending_milestone(milestone: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending milestone awaiting the winner's claim / handout.

    Returns None when there is no pending milestone or its claim window has expired.
    ``client_info`` is the caller's _room_clients entry, used to set ``i_am_winner``.
    """
    if not milestone or time.monotonic() >= milestone["expires_at"]:
        return None
    return {
        "boundary":     milestone["boundary"],
        "winner":       milestone["winner"],
        "handout":      milestone["handout"],
        "seconds_left": max(0, round(milestone["expires_at"] - time.monotonic())),
        "i_am_winner":  bool(
            client_info.get("name") and
            milestone["winner"].lower() == client_info["name"].lower()
        ),
    }
