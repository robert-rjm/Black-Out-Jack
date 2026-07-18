"""
app/routes/wild_card.py
========================
Easter egg: the Wild Card button (logo press).

POST /wild_card
    A player presses the logo to activate the Wild Card.  The server rolls
    a 35 / 15 / 50 split:

      35 % → presser drinks 1 sip                    ("self")
      15 % → launches Targeted Drinking Mode          ("targeted")
              -- 1/3 of that (5% overall) targets the presser,
                 2/3 of that (10% overall) targets a random player
      50 % → a random other player drinks 1 sip       ("random")

    The "targeted" roll can fail to actually start the subgame (it's
    already running, or still on its post-subgame cooldown -- see
    start_targeted_drinking's guards) -- that falls back to a dud
    ("nothing happens") for this press rather than stacking a second
    subgame or drinking anyone.

    Guards (returning ok=False on failure):
      - Only connected players (not spectators/admins-without-seat) may trigger.
      - Bots (NPC players) are never the presser — the button is hidden for them.
      - Drinking mode must be on (Wild Card is purely a drink mechanic).
      - 3-round cooldown per player (tracked session-lifetime).
      - Milestone gate: if the presser is within 10 sips of the next milestone
        boundary and no one has claimed it yet, the press is blocked so they
        can reach the milestone legitimately.
"""

import random
import logging

from flask import Blueprint, jsonify, request

from app.services.session_store     import game_sessions
from app.services.serializer        import serialize_state, compute_sip_totals, round_phase
from app.services.targeted_drinking import start_targeted_drinking
from app.config                     import MILESTONE_STEP

log = logging.getLogger(__name__)

bp = Blueprint("wild_card", __name__)

# ── Blackjack-themed anonymous names shown in the toast ──────────────────────
# Each entry: (action_template, dud_text)
# action_template: f-string with {name} for the player who drinks (self or random)
# dud_text: shown when nothing happens
_WILD_NAMES = [
    # (action_template, dud_text, name)
    ("Dealer's Ghost haunts {name} — 1 sip!",           "Dealer's Ghost drifts past harmlessly.",
     "Dealer's Ghost"),
    ("The Joker deals {name} an extra sip!",            "The Joker keeps the trick to itself.",
     "The Joker"),
    ("House Edge catches up with {name} — 1 sip!",      "House Edge favours the table tonight.",
     "House Edge"),
    ("Blind Bet costs {name} — 1 sip!",                 "Blind Bet folds — nothing happens.",
     "Blind Bet"),
    ("Lucky Draw isn't so lucky for {name} — 1 sip!",   "Lucky Draw is actually lucky — nothing happens!",
     "Lucky Draw"),
    ("The Pit Boss flags {name} for a sip!",            "The Pit Boss looks the other way.",
     "The Pit Boss"),
    ("High Roller bets against {name} — 1 sip!",        "High Roller passes on this one.",
     "High Roller"),
    ("Dead Man's Hand falls to {name} — 1 sip!",        "Dead Man's Hand belongs to nobody tonight.",
     "Dead Man's Hand"),
]

# ── Wild Card probability configuration ──────────────────────────────────────
WILD_CARD_PROB_SELF     = 0.35                                             # probability presser drinks
WILD_CARD_PROB_RANDOM   = 0.50                                             # probability a random player drinks
WILD_CARD_PROB_TARGETED = 1.0 - WILD_CARD_PROB_SELF - WILD_CARD_PROB_RANDOM  # probability Targeted Drinking launches

# Within the "targeted" roll: how often the presser themselves becomes the
# target vs. a random player (mirrors the "random" branch's own candidate pool).
WILD_CARD_TARGETED_SELF_FRACTION = 1 / 3

_WILD_CARD_COOLDOWN = 3   # rounds that must pass before the same player can press again


@bp.route("/wild_card", methods=["POST"])
def wild_card():
    """Easter-egg logo press — 45/5/50 drink assignment."""
    data      = request.json or {}
    room_code = (data.get("room_code") or "").strip()
    client_id = (data.get("client_id") or "").strip()

    session = game_sessions.get(room_code)
    if not session:
        return jsonify({"ok": False, "output": "Room not found."})

    if not session.drinking_mode:
        return jsonify({"ok": False, "output": "Wild Card only works in drinking mode."})

    if not session.wild_card_enabled:
        return jsonify({"ok": False, "output": "Wild Card is disabled."})

    phase = round_phase(session)
    if phase not in ("playing", "dealer-ready"):
        return jsonify({"ok": False, "output": "Wild Card only works during an active round."})

    # ── Identify the presser ─────────────────────────────────────────────────
    client_info = session._room_clients.get(client_id, {})
    player_name = client_info.get("name", "")

    if not player_name:
        return jsonify({"ok": False, "output": "You must be seated to use Wild Card."})

    # Confirm the player is actually seated (not kicked / spectator-only)
    player = session._get_player(player_name)
    if not player:
        return jsonify({"ok": False, "output": "You must be seated to use Wild Card."})
    if getattr(player, "is_npc", False):
        return jsonify({"ok": False, "output": "Bots can't press the logo."})

    # ── 3-round cooldown ─────────────────────────────────────────────────────
    last_used    = session._wild_card_last_used.get(player_name, -_WILD_CARD_COOLDOWN)
    rounds_since = session.round_count - last_used
    if rounds_since < _WILD_CARD_COOLDOWN:
        remaining = _WILD_CARD_COOLDOWN - rounds_since
        return jsonify({
            "ok":     False,
            "output": f"Wild Card cooling down — {remaining} more round(s) to go.",
        })

    # ── Milestone gate ───────────────────────────────────────────────────────
    sip_totals     = compute_sip_totals(session)
    player_total   = sip_totals.get(player_name, 0)
    next_boundary  = ((player_total // MILESTONE_STEP) + 1) * MILESTONE_STEP
    sips_to_ms     = next_boundary - player_total
    ms_not_claimed = next_boundary not in session.drinks.milestones_claimed
    if sips_to_ms <= 10 and ms_not_claimed:
        return jsonify({
            "ok":     False,
            "output": f"You're {sips_to_ms} sip(s) from a milestone — earn it first!",
        })

    # ── Roll ─────────────────────────────────────────────────────────────────
    roll                       = random.random()
    action_tmpl, dud_t, label = random.choice(_WILD_NAMES)
    if roll < WILD_CARD_PROB_SELF:
        # Self drinks
        outcome = "self"
        player.add_drink(1, f"Wild Card 🃏 — {label}", "player")
        text = f"🃏 {action_tmpl.format(name=player_name)}"
    elif roll < WILD_CARD_PROB_SELF + WILD_CARD_PROB_TARGETED:
        # Launch Targeted Drinking Mode -- target the presser 1/3 of the
        # time, otherwise a random player (same candidate pool as "random").
        candidates = [
            p for p in session.all_players
            if not getattr(p, "is_npc", False)
        ]
        if random.random() < WILD_CARD_TARGETED_SELF_FRACTION or not candidates:
            target_name = player_name
        else:
            target_name = random.choice(candidates).name

        if start_targeted_drinking(session, [target_name]):
            outcome = "targeted"
            text = f"🃏 {label} marks {target_name} for Targeted Drinking!"
        else:
            # Already running / still cooling down from a prior subgame --
            # fall back to a dud rather than stacking a second one.
            outcome = "dud"
            text = f"🃏 {dud_t}"
    else:
        # Random player drinks (including the presser)
        candidates = [
            p for p in session.all_players
            if not getattr(p, "is_npc", False)
        ]
        if not candidates:
            # No valid targets → fall back to dud
            outcome = "dud"
            text = f"\U0001f0cf {dud_t}"
        else:
            target  = random.choice(candidates)
            outcome = "random"
            target.add_drink(1, f"Wild Card 🃏 — {label}", "player")
            text = f"\U0001f0cf {action_tmpl.format(name=target.name)}"

    # ── Record result ─────────────────────────────────────────────────────
    wc = session.drinks.wild_card_presses.setdefault(
        player_name, {"presses": 0, "self": 0, "random": 0, "dud": 0, "targeted": 0})
    wc["presses"] += 1
    wc[outcome]   += 1
    session._wild_card_last_used[player_name] = session.round_count
    session.round._wild_card_seq    += 1
    session.round._wild_card_result  = {"text": text, "outcome": outcome}

    state = serialize_state(session, client_id)
    state["output"] = ""
    return jsonify(state)
