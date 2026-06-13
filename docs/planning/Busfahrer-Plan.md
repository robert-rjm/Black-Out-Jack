# Busfahrer Mode — Implementation Plan

Admin-controlled end-of-night drinking game, run as a sub-mode of an
existing room. Draft engine already exists at `engine/busfahrer.py` and
covers most of the core flow — this plan covers how to adapt it to spec
and wire it into the live app (GameRoom, drink tracker, CSV, polling, UI).

## 1. Rules summary (target spec)

- Admin starts a "Busfahrer round" from the admin panel and toggles which
  connected players (and bots) participate. Requires >= 2 participants.
- Elimination rounds, each player dealt one card per round:
  - **R1 — Black or Red** (1 sip)
  - **R2 — Higher or Lower** than own R1 card (2 sips)
  - **R3 — Inside or Outside** own R1/R2 cards (3 sips)
  - **R4 — Guess the Suit** (4 sips)
- Each round: correct guessers are eliminated (safe). Wrong guessers stay
  active and drink (or allocate) that round's sip value.
  - If a round produces zero losers (everyone correct), one player is
    randomly chosen to stay active ("unlucky" — keeps the game moving).
- After R4, if more than one player is still active, repeat R4 until one
  remains (per existing draft behavior) — confirm this is acceptable, or
  consider re-running R1 instead (open question, see §6).
- The last remaining player becomes the **Busfahrer** ("bus driver") and
  enters the **Bus Ride**:
  - Anchor card = the Busfahrer's last card from elimination.
  - Remaining deck is reshuffled.
  - Repeatedly guess higher/lower vs. the current anchor.
  - Correct guess → streak += 1, new card becomes the anchor.
  - 5 correct in a row → escapes the bus.
  - Wrong guess → drink (scaling — see §6), streak resets to 0, anchor
    resets to the original card, deck reshuffles.
- A **"Finished my drink"** button lets the Busfahrer (and/or any player
  who owes sips) confirm they've completed their drink, closing out the
  Busfahrer round.
- All sips from this mode are tracked in the existing sip ticker and CSV
  export, same as regular gameplay drinks.

## 2. What the existing draft (`engine/busfahrer.py`) already gives us

- `BusfahrerGame` state machine with `GamePhase` (LOBBY → R1-4 → BUS_RIDE
  → FINISHED) and `PlayerStatus` (ACTIVE/ELIMINATED/BUS_DRIVER/DONE).
- `ROUNDS` dict matches R1-4 names, prompts, options, and sip values
  (1/2/3/4) exactly.
- `_evaluate_round` / `_check_guess`: correct elimination logic, including
  the "everyone correct → random unlucky player stays active" rule.
- `_start_bus_ride` / `_bus_ride_guess`: anchor-card + reshuffle + streak
  + restart-on-fail mechanic, matching the spec.
- `allocate_sips`: lets a player push sips to someone else.
- `player_finished_drink`: marks a player DONE.
- `get_state` / `get_player_view`: serialization helpers for API responses.

This is a strong starting point but is fully standalone (its own `Deck`/
`Card` from `engine/blackjack.py`, in-memory player dicts, no ties to
`GameRoom`, sip ticker, or CSV).

## 3. Gaps vs. spec to close

1. **Drink-or-allocate prompt.** Currently `_evaluate_round` immediately
   commits sips to `sips_drunk` for losers. Need an intermediate state
   per round where each loser is prompted "drink it yourself or give it
   to someone else" before the sip is finalized and logged.
2. **"Finished my drink" flow.** Currently just flips a status enum with
   no side effects. Needs to:
   - Be scoped to whoever currently owes a drink (round losers and/or
     the Busfahrer after a failed bus-ride attempt / after escaping).
   - On click: write the sip(s) to `_drink_csv_rows` / `_sip_ticker` /
     `_last_round_drinks`, append a log line, and unblock game flow
     (advance phase, or end the Busfahrer round if it was the final
     step).
3. **Tie-break rule for "everyone correct"** — confirm random-unlucky-
   player approach is desired (see §6).
4. **Repeat-R4 vs repeat-R1** when >1 player remains after R4 (see §6).
5. **Bus-ride wrong-guess sip scaling** — draft uses `streak + 1`
   (escalating pain); spec doesn't explicitly define this — confirm vs.
   a flat value (see §6).

## 4. Integration with the live app

### 4.1 GameRoom / session state
- Add a `_busfahrer` field to `GameRoom` (e.g. `Optional[BusfahrerGame]`
  or a plain dict mirror of its state) — `None` when not running.
- Add `_busfahrer_active: bool` flag. While `True`, normal round flow
  (`cmd_deal`, hit/stand/etc., NPC auto-play) is paused — the polling
  loop should skip blackjack-round ticks and just serve Busfahrer state.
- Reuse `session.shoe` or a fresh `Deck(1)` — recommend a **fresh deck**
  scoped to the Busfahrer instance so it doesn't interact with the main
  game's shoe/penetration tracking. Card rendering needs to match the
  existing `.card-vis` rank/suit format used by `serializer.py` (reuse
  whatever symbol/rank mapping the main game already serializes with, so
  the frontend can reuse `.card-vis`/`.card-vis.hidden` styles).

### 4.2 Admin routes (new, in `app/routes/admin.py`)
Follow the existing pattern of `make_bot` / `toggle_god_mode` / etc.:
- `POST /busfahrer/start` — admin only; body: list of participant names
  (toggled ON). Validates >= 2 participants, creates `BusfahrerGame`,
  sets `_busfahrer_active = True`.
- `POST /busfahrer/toggle_player` — admin only; add/remove a participant
  while in LOBBY phase.
- `POST /busfahrer/advance` — admin only; calls `advance_phase()` once
  all active players have guessed (mirrors `claim_milestone`-style admin
  gating).
- `POST /busfahrer/cancel` — admin abort, clears `_busfahrer` state and
  resumes normal play.

### 4.3 Player routes (new, in `app/routes/game_commands.py` or a new
`app/routes/busfahrer.py`)
- `POST /busfahrer/guess` — player submits a guess for current phase.
- `POST /busfahrer/allocate` — loser allocates sips to another player
  (only available during the new drink-or-allocate step, §3.1).
- `POST /busfahrer/finished_drink` — "Finished my drink" button (§3.2).

### 4.4 Drink tracking / CSV / sip ticker
For every sip event generated by Busfahrer (round loss, allocation,
bus-ride fail, bus-ride completion if applicable), follow the exact
pattern used in `apply_bust_vote_penalties`:
```python
session._sip_ticker[name] = session._sip_ticker.get(name, 0) + sips
session._last_round_sips[name] = session._last_round_sips.get(name, 0) + sips
session._last_round_drinks.append({"name": name, "sips": sips, "reason": reason})
session._drink_csv_rows.append({
    "round":  session.round_count,
    "dealer": session.dealer_name,
    "player": name,
    "role":   "player",
    "rule":   "Busfahrer <something>",
    "sips":   sips,
})
check_and_set_milestone(session)
```
- New rule strings needed in `engine/drinking_rules.py` /
  `classify_rule()`: e.g. `"Busfahrer round 1/2/3/4"`, `"Busfahrer bus
  ride fail"`, `"Busfahrer allocation"`.

### 4.5 NPC participation
- If a bot is toggled ON as a participant, auto-submit a guess via
  `submit_guess()` with a random valid option immediately after dealing
  (mirrors `auto_play_npc_turns`'s "don't block on bots" philosophy).
- Bots should never be the final Busfahrer's *recipient* of an allocation
  in a way that's meaningless — but bots *can* become the Busfahrer
  (drink sips conceptually / just logged for tracking, no real consequence
  beyond the log — acceptable since it's just for tracking purposes).

### 4.6 Polling / serializer
- Add a `busfahrer` block to the `/state` serializer output (mirrors
  `pending_milestone` block) containing: phase, prompt/options for the
  current round, each participant's status + current card (only reveal a
  player's own hidden card to themselves, like the dealer's hidden card
  today), bus-ride streak/anchor, and whether "Finished my drink" should
  be shown to the requesting client.
- `apply_milestone_forfeit`-style "safe to call every tick" function for
  any time-boxed steps (if we add a TTL to the drink-or-allocate prompt).

### 4.7 Frontend
- New partial `templates/partials/index/_busfahrer.html` — full-screen
  modal/overlay, reusing `.card-vis` / `.card-vis.hidden` styles from
  `table.css`.
- New JS module `static/js/ui/busfahrer.js` (mirrors `table-modals.js`
  structure): renders current phase/prompt, guess buttons, drink-or-
  allocate choice, bus-ride streak counter, "Finished my drink" button.
- Admin panel addition in `admin-settings.js` / `_modals.html`: "Start
  Busfahrer" button + participant toggle list (only enabled when
  `round_phase != "playing"`).

## 5. Suggested build order

1. Port `BusfahrerGame` engine into `app/services/busfahrer.py`, adapting
   `Card`/`Deck` usage to match the main app's card representation (so
   serialization is trivial).
2. Wire admin start/cancel + `_busfahrer` field on `GameRoom`, with
   `_busfahrer_active` pausing normal polling/round flow.
3. Add player guess/allocate/finished routes + serializer block.
4. Hook sip events into `_sip_ticker`/`_drink_csv_rows`/`_last_round_drinks`
   + new `classify_rule` entries.
5. NPC auto-guess support.
6. Frontend modal + admin controls.
7. Manual playtest with 2-4 players (mix of human/bot) covering: normal
   elimination through all 4 rounds, "everyone correct" tie-break, bus
   ride escape, bus ride multiple failures, allocate-vs-drink choice,
   admin cancel mid-game.

## 6. Open questions (need decisions before/while building)

- **Repeat round after R4**: if >1 player remains after R4, repeat R4
  (draft's current behavior) or restart from R1 for the remaining
  players?
- **Bus-ride wrong-guess sips**: flat value (e.g. always 1, or always the
  R4 value of 4) vs. escalating `streak + 1` as in the draft?
- **Drink-or-allocate timing**: prompt immediately after each R1-4 loss
  (per-round), or batch all of a player's owed sips and ask once at the
  end of elimination?
- **Pause vs. block normal play**: does starting Busfahrer fully pause
  blackjack round progression for everyone, or can it run in parallel
  (e.g. only between hands)?
- **Bot-as-Busfahrer**: any special handling needed, or just log it and
  move on?
