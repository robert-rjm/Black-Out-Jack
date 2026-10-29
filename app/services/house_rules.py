"""
app/services/house_rules.py
===========================
The admin's house-rule edits (RuleToggles-Implementation.md §4): validating
/update_settings rule keys, queuing the target set for the next round,
applying it at round start, and the "rules" block of /state.

The queue holds the *full target set* (``queued_settings["rules"]``, a list
of IDs), never a diff, so repeated edits collapse and the UI can compare
target against live. Live rules (``RuleDef.live``: bust vote, wild card)
never wait: they apply at once, and the queued list's copy of them is
ignored in favour of the room's current state.
"""

from __future__ import annotations

from engine.rules_registry import GROUPS, LIVE, LOCKED, PRESETS, RULES, RULES_BY_ID, RuleSet

RULE_KEYS = ("rules_preset", "rules_on", "rules_off", "rules_next", "rules_discard")
RULES_NOTICE = "📜 House rules changed"
# A notice lists rules by name up to this many per side, then just counts them.
_MAX_NAMED = 4


def queued_target(session, queued: dict | None = None) -> RuleSet | None:
    """The set the next round will start with, or None when nothing is queued."""
    queued = session._queued_settings if queued is None else queued
    if "rules" not in queued:
        return None
    return RuleSet((frozenset(queued["rules"]) - LIVE) | (session.rules.enabled & LIVE))


def _id_set(raw) -> set[str] | None:
    if raw is None:
        return set()
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        return None
    return set(raw)


def update_rules(session, data: dict, queued: dict) -> str | None:
    """Apply the rule keys of an /update_settings payload. Live rules change
    now; the rest goes into ``queued["rules"]``. Returns an error message, or
    None on success. Nothing changes when the payload is invalid."""
    if not any(k in data for k in RULE_KEYS):
        return None

    on, off = _id_set(data.get("rules_on")), _id_set(data.get("rules_off"))
    if on is None or off is None:
        return "rules_on and rules_off must be lists of rule IDs."
    unknown = (on | off) - RULES_BY_ID.keys()
    if unknown:
        return f"Unknown rule: {sorted(unknown)[0]}"
    locked = (on | off) & LOCKED
    if locked:
        return f"{RULES_BY_ID[sorted(locked)[0]].name} is part of the game itself and can't be switched."
    if on & off:
        return f"{RULES_BY_ID[sorted(on & off)[0]].name} can't be switched on and off at once."
    preset = data.get("rules_preset")
    if preset is not None and preset not in PRESETS:
        return "Unknown preset."

    if data.get("rules_discard"):
        queued.pop("rules", None)
    live_now = session.rules
    target = queued_target(session, queued) or live_now
    if preset is not None:
        target = RuleSet.from_preset(preset)
    target = target.with_changes(on=on, off=off)
    if data.get("rules_next"):
        target = target.with_changes(on=target.next_unlock())

    # Live rules: apply immediately, as their old toggles did.
    live_on  = {r for r in LIVE if r in target.enabled and r not in live_now.enabled}
    live_off = {r for r in LIVE if r not in target.enabled and r in live_now.enabled}
    if live_on or live_off:
        session.rules = live_now.with_changes(on=live_on, off=live_off)
        if "side.bust_vote" in live_on | live_off:
            session.round._bust_votes = {}   # clear any stale votes when toggling

    # Everything else waits for the next round. Nothing left to change
    # means nothing is queued.
    if target.enabled - LIVE == session.rules.enabled - LIVE:
        queued.pop("rules", None)
    else:
        queued["rules"] = [r.id for r in RULES if r.id in target.enabled]
    return None


def describe_rule_diff(old: RuleSet, new: RuleSet) -> str:
    """The round-log notice, e.g. "📜 House rules changed: Dealer Lottery
    off", by effective state (what the table actually plays). Empty when nothing
    players would notice changed."""
    def names(ids: frozenset[str]) -> str:
        picked = [r.name for r in RULES if r.id in ids]
        return ", ".join(picked) if len(picked) <= _MAX_NAMED else f"{len(picked)} rules"

    turned_on  = new.effective() - old.effective()
    turned_off = old.effective() - new.effective()
    parts = []
    if turned_on:
        parts.append(f"{names(turned_on)} on")
    if turned_off:
        parts.append(f"{names(turned_off)} off")
    return f"{RULES_NOTICE}: {'; '.join(parts)}" if parts else ""


def apply_queued_rules(session, queued: dict) -> str:
    """Round start: switch to the queued set. Returns the round-log notice
    ("" when nothing visible changed). Events already running (lottery,
    targeted, a milestone claim) aren't cancelled; their gates only run at
    trigger time."""
    target = queued_target(session, queued)
    if target is None:
        return ""
    old = session.rules
    # One write is enough: the engine session reads room.rules live.
    session.rules = target
    return describe_rule_diff(old, target)


def serialize_rules(session) -> dict:
    rules  = session.rules
    target = queued_target(session)
    return {
        "preset":    rules.preset,
        "enabled":   [r.id for r in RULES if r.id in rules.enabled],
        "effective": [r.id for r in RULES if rules.on(r.id)],
        "queued":    [r.id for r in RULES if r.id in target.enabled] if target else None,
    }


def registry_payload() -> dict:
    """Static registry data for GET /rules_registry (fetched once, cached)."""
    return {
        "ok":      True,
        "groups":  [{"id": g, "label": label} for g, label in GROUPS],
        "rules":   [{
            "id":          r.id,
            "name":        r.name,
            "summary":     r.summary,
            "group":       r.group,
            "kind":        r.kind,
            "timing":      r.timing,
            "preset":      r.preset,
            "unlock_step": r.unlock_step,
            "depends_on":  list(r.depends_on),
            "doc_anchor":  r.doc_anchor,
            "live":        r.live,
            "halvable":    r.halvable,
        } for r in RULES],
        "presets": {name: [r.id for r in RULES if r.id in ids] for name, ids in PRESETS.items()},
    }
