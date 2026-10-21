"""
app/services/serializers/bust_vote.py
====================================
bust-vote window snapshot helpers, split out of serializer.py.
"""

import time

from app.models.game_room import GameRoom


def _bust_vote_window(session: GameRoom) -> dict:
    """Return bust_vote_window_open and bust_vote_seconds_left for the frontend."""
    if not session.bust_vote_enabled or not session.round._bust_vote_expires_at:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    now        = time.monotonic()
    secs_left  = session.round._bust_vote_expires_at - now
    if secs_left <= 0:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    # Early close: all non-NPC players have voted or passed
    human_players = [p for p in session.all_players
                     if not getattr(p, "is_npc", False)]
    all_decided = bool(human_players) and all(
        session.round._bust_votes.get(p.name) is not None for p in human_players
    )
    if all_decided:
        return {"bust_vote_window_open": False, "bust_vote_seconds_left": 0}

    return {
        "bust_vote_window_open":   True,
        "bust_vote_seconds_left":  max(1, int(secs_left)),
    }


# ---------------------------------------------------------------------------
# Insurance vote serializer helper
# ---------------------------------------------------------------------------
