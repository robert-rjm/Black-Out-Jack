"""
app/services/serializers/dealer_lottery.py
=========================================
Dealer Lottery snapshot helpers, split out of serializer.py.
"""

import time




def _serialize_pending_dealer_lottery(pending: dict | None, client_info: dict) -> dict | None:
    """Serialize a pending Dealer Lottery entry window.

    Returns None when there is no pending lottery or its entry window has
    expired. Only reveals this client's own local players' submitted
    values (``my_entries``) plus an answered/total count -- never anyone
    else's individual entry, to avoid metagaming the table's choices.
    """
    if not pending or time.monotonic() >= pending["expires_at"]:
        return None
    entries  = pending["entries"]
    my_names = set(client_info.get("local_names") or
                   ([client_info["name"]] if client_info.get("name") else []))
    return {
        "seconds_left":   max(0, round(pending["expires_at"] - time.monotonic())),
        "answered_count": sum(1 for v in entries.values() if v is not None),
        "total_count":    len(entries),
        "my_entries":     {n: v for n, v in entries.items() if n in my_names},
    }


def _serialize_last_dealer_lottery_result(result: dict | None) -> dict | None:
    """Serialize the most recently resolved Dealer Lottery draw for the
    frontend. Returns None if there is no result or it is older than 90
    seconds (matches _serialize_last_milestone's dismissal window)."""
    if not result or time.monotonic() - result["set_at"] >= 90:
        return None
    return {
        "hands":        [dict(h) for h in result["hands"]],
        "busted":       result["busted"],
        "entries":      dict(result["entries"]),
        "drink_amounts":  dict(result.get("drink_amounts", {})),
        "credit_amounts": dict(result.get("credit_amounts", {})),
        "seconds_ago":  max(0, round(time.monotonic() - result["set_at"])),
    }
