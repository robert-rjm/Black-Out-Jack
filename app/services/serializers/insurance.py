"""
app/services/serializers/insurance.py
====================================
insurance vote snapshot helpers, split out of serializer.py.
"""

import time

from app.models.game_room import GameRoom
from app.config import INSURANCE_VOTE_TIMEOUT


def _insurance_outcome_text(r: dict) -> str:
    """Return the canonical human-readable outcome string for one insurance result entry.

    Centralised here so both the toast (admin.js) and the banner
    (table-modals.js) display identical wording without duplicating logic.
    """
    insured   = r.get("insured")
    dealer_bj = r.get("dealer_bj")
    if insured and dealer_bj:
        return "dealer had BJ — BJ holder drinks own bonus, group safe"
    if insured and not dealer_bj:
        return "no dealer BJ — group drinks double"
    if not insured and not dealer_bj:
        return "no dealer BJ — normal BJ bonus"
    return "dealer had BJ — auto-insurance applies"


def _serialize_insurance_vote(v: dict, session: GameRoom, client_info: dict) -> dict:
    """Serialize one insurance vote entry.

    insure_count / decline_count are exposed as soon as every eligible player
    has cast a vote — not gated on `resolved` (which only flips after the 60s
    timeout). This means the banner can show the correct result immediately
    when the last vote comes in rather than always defaulting to "DECLINE".
    """
    bj_player    = v["player"]
    # NPCs never cast insurance votes, so exclude them from the required
    # count — otherwise votes_cast can never reach votes_needed when NPCs
    # are seated, and the vote sits "unresolved" for the full 60s timeout,
    # stalling the dealer's turn even though every human has already voted.
    votes_needed = sum(1 for p in session.all_players
                       if p.name.lower() != bj_player.lower()
                       and not getattr(p, "is_npc", False))
    votes_cast   = len(v["votes"])
    counts_ready = v["resolved"] or votes_cast >= votes_needed
    # Bots abstain — only humans with drinking stake count toward the
    # majority. Any human who hasn't voted (or voted decline) counts toward
    # decline_count, so non-voters default to decline. Ties (incl. 0-0 when
    # everyone is a bot) default to decline via `insured = insure > decline`.
    insure_count  = sum(1 for x in v["votes"].values() if x)
    decline_count = votes_needed - insure_count
    return {
        "bj_player":      bj_player,
        "hand_idx":       v["hand_idx"],
        "resolved":       v["resolved"],
        "my_vote":        v["votes"].get(client_info.get("name") or "", None),
        "votes_cast":     votes_cast,
        "votes_needed":   votes_needed,
        "votes_cast_by":  dict(v["votes"]),   # {voter_name: bool} — local multiplayer uses this to advance seats
        "insure_count":  insure_count  if counts_ready else None,
        "decline_count": decline_count if counts_ready else None,
        "seconds_left":  max(0, int(INSURANCE_VOTE_TIMEOUT -
                                    (time.monotonic() - v.get("started_at", time.monotonic())))),
    }


# ---------------------------------------------------------------------------
# Full state snapshot
# ---------------------------------------------------------------------------
