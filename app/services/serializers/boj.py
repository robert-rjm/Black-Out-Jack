"""
app/services/serializers/boj.py
==============================
BOJ switch snapshot helpers, split out of serializer.py.
"""

import time

from app.models.game_room import GameRoom


def _serialize_boj(session: GameRoom, client_info: dict, client_id: str) -> dict:
    """Normal-mode "switch to BOJ" poll: the open vote, its recent outcome,
    and (for a client that is moving to a new room) the cancel-window plan."""
    from app.services import boj_switch   # lazy: boj_switch imports session_store/room_manager

    now  = time.monotonic()
    poll = session._boj_poll
    poll_out = None
    if poll and now < poll["expires_at"]:
        yes, no, _undecided = boj_switch.tally(poll)
        total = len(poll["votes"])
        mine  = next((v for n, v in poll["votes"].items()
                      if n.lower() == (client_info.get("name") or "").lower()), None)
        eligible = any(n.lower() == (client_info.get("name") or "").lower()
                       for n in poll["votes"])
        poll_out = {
            "proposer": poll["proposer"], "yes_count": yes, "no_count": no,
            "total_voters": total, "needed": total // 2 + 1,
            "seconds_left": max(0, round(poll["expires_at"] - now)),
            "my_vote": mine, "eligible": eligible,
        }

    last = session._boj_last_result
    last_out = None
    if last and now - last["set_at"] < boj_switch.RESULT_FLASH_SECONDS:
        last_out = {"kind": last["kind"], "names": list(last["names"]),
                    "seconds_ago": max(0, round(now - last["set_at"]))}

    plan = session._boj_split
    split_out = None
    if (plan and client_id in plan["clients"]
            and client_id not in plan["cancelled"] and client_id not in plan["moved"]):
        split_out = {
            "new_room": plan["new_room"],
            "seconds_until_go": max(0, round(plan["go_at"] - now)),
            "can_cancel": (not plan["built"]) and now < plan["go_at"],
        }

    can_propose = bool(
        not session.drinking_mode and session.mode == "digital"
        and poll is None and plan is None
        and client_info.get("name") and client_info.get("role") != "spectator")
    return {"poll": poll_out, "last_result": last_out,
            "my_split": split_out, "can_propose": can_propose}
