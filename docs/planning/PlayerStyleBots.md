# Player-Style Bots

**Aim:** Record every in-game decision (hit/stand/double/split/insurance) with full board-state context, then use that data to train per-player bots — "Rob-bot", "Marco-bot", "David-bot" — that mimic each person's real tendencies and deviations from basic strategy. The existing basic-strategy `NPC_Player` stays as the baseline/control.

Applies to **both Drinking and Normal modes** — only the `drinking_mode`/`bet_amount` context columns differ.

---

## What's already done

All logging and export infrastructure (formerly "Phase C") is complete:

- **Schema** — one row per decision capturing hand state *before* the action, dealer upcard, all visible table cards, valid actions, action taken, basic-strategy recommendation, and backfilled round result.
- **Capture hooks** — `record_decision()` called at the top of `_cmd_hit`, `_cmd_stand`, `_cmd_double`, `_cmd_split`, `_cmd_insurance` in `app/routes/game_commands.py`, before the hand is mutated.
- **Export route** — `GET /export_decisions?room_code=...&player=<optional>` in `app/routes/reports.py`; returns CSV, works in both modes, session-scoped (rows live in `session._decision_log` until exported or session expires).
- **Frontend** — "⬇️ Export Decision Log" button in the admin settings modal, separate from the drinking-only export.
- **Data loader** — `scripts/load_decision_logs.py` concatenates exported CSVs from `data/decisions/`, prints per-player breakdowns (action counts, basic-strategy deviation rate, win/loss/push split), supports `--player` and `--out` flags.
- **Automated tests** — `tests/test_decision_log.py` covers: pre-action state capture, hidden dealer hole-card exclusion from `visible_cards`, `hand_result` backfill, and CSV export shape for both modes.

---

## Next steps

### 1. Manual spot-check — export smoke test
*Prerequisites: none — just needs a running local instance.*

- [ ] Play a short session (both Drinking and Normal mode) on localhost
- [ ] Hit "Export Decision Log" from the admin modal after each session
- [ ] Open the CSV and verify: row count matches number of decisions made, `hand_cards_before` reflects pre-action state, `dealer_upcard` is correct, `visible_cards` excludes the hole card, `hand_result` is filled in for every row
- [ ] Confirm the `basic_strategy_action` column looks sane for a few spot-checked rows

---

### 2. Collect real data — beta sessions with Rob, Marco, David
*Prerequisites: step 1 passed; all three players available for a session.*

- [ ] Each player sits their **own named seat** for the whole session so decisions attribute correctly (`player` field = seat name — don't swap seats mid-session)
- [ ] Play naturally — don't try to "train the bot," just play normally so the log reflects real tendencies
- [ ] Target **≥150 decisions per player** before attempting to build profiles (roughly 100–150 rounds; each round yields ~1–2 decisions per player). More is better for rarer spots (splits, soft hands, doubles)
- [ ] Export the CSV at the end of every session before closing the room; save to `data/decisions/` (gitignored)
- [ ] Run `scripts/load_decision_logs.py --dir data/decisions/` periodically to check per-player row counts and decide when there's "enough" data

---

### 3. Build per-player deviation tables
*Prerequisites: step 2 complete with ≥150 decisions per player; `load_decision_logs.py --out combined.csv` run to produce a single combined file.*

The approach is a lookup table ("basic strategy + known quirks"), not a full ML model — simpler, interpretable, and honest about what the data actually supports.

- [ ] For each player, group decisions by `(hand_total_before, is_soft, dealer_upcard, can_split, can_double)` and find the majority `action_taken`
- [ ] Record a deviation only where majority is **>60%** of observations **and** there are **≥3 samples** at that spot; everything else falls back to basic strategy
- [ ] Optionally extend the grouping key with:
  - `is_suited` (player's hand is same-suit) — useful for soft-hand and pair decisions if sample size supports it
  - a coarse "table high-card bias" bucket (count of 10/J/Q/K/A visible, bucketed low/medium/high) — for borderline hit/stand spots (12–16 vs dealer 2–6); only add if enough data exists for it to be meaningful. **Resolver support for this now exists** (`table_bias` in step 4) — this bullet is just about mining it from real decision logs when there's enough data.
  - a `sibling_awaiting_deal` flag (another of the player's hands this round, from a split, hasn't been dealt its second card yet) — for spots where a player seems to play an earlier split hand more conservatively to protect a sibling hand not yet in play. **Implemented** (`sibling_awaiting_deal` in step 4, mined automatically by `scripts/build_player_profiles.py`).
- [x] Write each player's profile to `engine/player_profiles/<name>.json` containing: the deviation table, sample sizes per entry, thresholds used, and the date/session of the source data
- [ ] Sanity-check: re-run the beta log's situations through the profile and confirm the majority-deviation spots are captured correctly

---

### 4. Implement the style-aware strategy resolver
*Prerequisites: step 3 complete; at least one player profile JSON exists.*

- [x] Create `engine/style_strategy.py` with `best_play_for(profile, hand, dealer_upcard, valid_actions, ...) -> action`:
  1. Build the lookup key from the hand state
  2. Check the player's deviation table — most specific key first (table-aware), then basic key
  3. If a match is found with sufficient confidence → return that action
  4. Otherwise fall back to `strategy.best_play(...)`
- [x] Ensure the fallback to `strategy.best_play()` is always a legal action (i.e. in `valid_actions`) — guard against edge cases where the profile recommends an action not currently available
- [x] Unit test: given a small fixture profile, confirm correct deviation lookup, fallback for unknown spots, and fallback for insufficient-sample spots (`tests/engine/test_style_strategy.py`)
- [ ] Regression test: a `StylePlayer` with an **empty** profile must behave identically to plain `NPC_Player` (pure basic strategy)

**Table-aware tier (done):** `best_play_for` now accepts two optional context
params, `visible_cards` and `sibling_hands`, that add a second, more specific
lookup tier on top of the original 5-field key:
- `table_bias` — every visible card (all hands in play + dealer upcard)
  bucketed into low/medium/high ten-value-and-ace density vs. a fresh
  shoe's ~38% baseline.
- `sibling_awaiting_deal` — true when another of the player's hands this
  round (from a split) hasn't been dealt its second card yet. Since
  `_play_hand` deals each split hand's second card only after the previous
  hand fully resolves, a sibling can never be caught sitting on a concrete
  two-card total while this hand is being decided — it's either already
  resolved or still down to one card, so that single-card "not started yet"
  state is the only real-world signal to check. Models a human playing an
  earlier split hand more conservatively because they know another hand is
  still coming.

A deviation entry only needs `table_bias`/`sibling_awaiting_deal` keys if
the underlying data actually showed the player's choice depends on them;
entries without those keys match on the plain 5-field spot regardless of
table state, so `rob.json`/`david.json` needed no manual changes and kept
behaving exactly as before the rebuild below. `NPC_Player.decide()` and
`game_engine.auto_play_npc_turns` now compute and pass both signals
automatically for every in-game NPC turn (this also fixed a pre-existing bug
where auto-play always called the static basic-strategy `best_play`, so
`personality` was silently never applied during real games).

**Mining pipeline (done):** `scripts/build_player_profiles.py` now computes
`table_bias` from each row's `visible_cards` column (reusing
`style_strategy._table_bias_bucket`) and `sibling_awaiting_deal` from each
row's `hand_index` vs. the max `hand_index` seen for that player+round in
the log (a strictly larger hand_index anywhere in the round means that hand
was still undealt at this decision, given the engine's sequential split
order). A fine-grained (7-field) deviation is only written when its
majority action differs from what the coarser 5-field grouping would have
produced — otherwise the extra dimensions are noise, and the plain
5-field deviation (or basic strategy) already covers the spot.

---

### 5. Wire style bots into `NPC_Player`
*Prerequisites: step 4 complete and tests passing.*

- [ ] Add a `personality` field to `NPC_Player` (values: `"basic"` | `"rob"` | `"marco"` | `"david"`)
- [ ] In `NPC_Player.decide()` (or equivalent), route to `style_strategy.best_play_for(profile, ...)` when `personality != "basic"`, loading the corresponding profile from `engine/player_profiles/`
- [ ] Profile loading: load once at bot-creation time (not per-decision); handle missing profile file gracefully by falling back to basic strategy and logging a warning
- [ ] NPC decisions are already logged with `is_npc: true` — confirm the style bot's choices show up correctly in the decision log (useful for verifying the bot isn't just always matching basic strategy)

---

### 6. UI — bot personality selection
*Prerequisites: step 5 complete.*

- [ ] Add a personality dropdown when adding an NPC seat in the setup screen (options: "Bot (basic strategy)", "Rob-bot", "Marco-bot", "David-bot")
- [ ] Only show personality options for profiles that actually exist in `engine/player_profiles/` — don't expose a bot whose profile hasn't been built yet
- [ ] Optional: add an admin/debug view listing each bot's known deviations (the deviation table entries), so players can see what the bot "learned"

---

### 7. Validation
*Prerequisites: steps 4–6 complete; original beta log CSVs still available.*

- [ ] Offline: re-run every decision from the beta log through `best_play_for` and check that the bot's choice matches the player's actual majority choice for each deviation spot
- [ ] In-game: run a simulated session with each style bot and spot-check that its choices look plausible (not always matching basic strategy, not picking illegal actions, sensible fallback on rare spots)
- [ ] Regression: confirm the existing basic-strategy bot is unaffected
