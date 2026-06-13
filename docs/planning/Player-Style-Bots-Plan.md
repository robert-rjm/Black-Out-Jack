# Player-Style Bots Plan

Goal: alongside the existing basic-strategy `NPC_Player`, offer bots that play
the way a specific real player (Rob, Marko, David, ...) tends to play —
including their deviations from basic strategy and any tells around
composition-dependent decisions (e.g. standing on soft hands with certain
suits, reacting to cards already visible on the table).

Status: not started. This doc captures the plan; no code changes yet.

---

## Why the current data isn't enough

`scripts/simulation_log.csv` is a **drinking-rule event log** — one row per
sip-rule trigger (`round, dealer, player, role, rule, sips`). It contains no
information about:

- what cards were in a player's hand at the moment of a decision
- what the dealer's up-card was
- what action the player actually chose (hit/stand/double/split)
- what other cards were visible on the table

So it can't be used to infer how Rob/Marko/David play. We need a **new,
purpose-built decision log**, captured from real play.

---

## Phase A — Add decision logging to the engine

### A1. Define the decision record
For every point where a human player chooses an action, log a row with:

- `session_id`, `round`, `player`
- `hand_cards` — full list of the player's current cards (ranks + suits),
  not just the total — needed to capture "considering own suited hands"
- `hand_total`, `is_soft`, `can_split`, `can_double`
- `dealer_up_card`
- `visible_table_cards` — other players' visible cards / discards at the
  time of the decision (needed for "other cards on table" awareness)
- `valid_actions` — the legal action set at that moment
- `action_taken` — what the player actually picked
- `basic_strategy_action` — what `strategy.best_play()` would have picked,
  for easy deviation comparison
- `round_outcome` — win/loss/push/blackjack (filled in after the round ends)

A flat CSV can represent most of this, but `hand_cards` and
`visible_table_cards` are variable-length lists, so the cleanest format is
**JSONL** (one JSON object per line) or a CSV with those fields
pipe/comma-encoded as strings (e.g. `"AS,9H"`). JSONL is recommended —
easier to extend later without breaking parsers.

### A2. Hook point in `engine/blackjack.py`
Find where the round loop asks a **human** player for their action (the
counterpart to the `NPC_Player.best_play(...)` call around line 553) and add
a logging call there, capturing the hand/table state *before* the action is
applied. Bot-driven decisions (existing `NPC_Player`) are not logged — only
human decisions feed the style model.

### A3. Where logs go
Write to `scripts/decision_log.jsonl` (or per-session files
`scripts/logs/<session_id>.jsonl`), gitignored like the existing simulation
log.

---

## Phase B — Beta session with Rob, Marko, David

- Play a number of real rounds in Normal mode with decision logging enabled
  (Phase A must be done first).
- Each of the three plays their **own seat** for the whole session so
  decisions can be attributed correctly (`player` field = seat name).
- Rough target: **150-300+ logged decisions per player** to get reasonable
  coverage of the common (total, dealer-up) combinations. More hands = better
  coverage of rarer spots (splits, soft hands, doubles).
- Play naturally — i.e. don't deliberately try to "train the bot," just play
  as normal, so the log reflects real tendencies (including suit-driven and
  table-aware decisions).
- At the end of the session, sanity-check the log: row counts per player,
  spot-check a few rows against what was actually played.

---

## Phase C — Build per-player style profiles

### C1. Deviation table (primary approach)
For each player, group logged decisions by `(hand_total, is_soft,
dealer_up_card, can_split, can_double)` and compute the most frequent
`action_taken`. Compare against `basic_strategy_action` to produce a
**deviation table**: spots where the player reliably differs from basic
strategy (e.g. "Marko stands on hard 12 vs dealer 2-3", "Rob always hits soft
17 vs dealer 7+").

- Only record a deviation where there's a clear majority (e.g. >60% of
  observed decisions at that spot) **and** a minimum sample size (e.g. ≥3
  observations) — otherwise fall back to basic strategy for that spot.
- Spots with no/insufficient data simply fall back to basic strategy
  (`strategy.best_play()`), so the bot is "basic strategy + known quirks."

### C2. Composition-dependent factors (suits / visible cards)
This is the harder part — basic strategy tables are keyed only on
`(total, dealer_up)`, but the request is to also reflect:

- **own suited hands** — e.g. a player who plays a suited soft hand
  differently than basic strategy because they're chasing a flush/visual
  pattern
- **other visible cards** — e.g. a player who hits more aggressively when
  they've seen a lot of low cards already (informal card-counting-ish
  behavior)

For C1's table to capture these, extend the grouping key with optional extra
dimensions only where the data supports it:
- `is_suited` (player's hand is same-suit) as an extra key dimension for
  soft-hand and pair-split decisions
- a coarse "table card bias" feature (e.g. count of high cards 10/J/Q/K/A
  visible so far this round, bucketed low/medium/high) for borderline
  hit/stand spots (12-16 vs dealer 2-6)

Given the beta sample size, these extra dimensions will likely only yield
usable signal for the most common situations (soft hands, pairs, 12-16 vs
small dealer card). Anything with too few samples falls back to C1's
non-suited/non-table-aware table, and ultimately to basic strategy. This
keeps the model honest about what it actually learned vs. guessed.

### C3. Output format
Store each player's profile as a small JSON/Python data file, e.g.
`engine/player_profiles/marko.json`, containing the deviation table(s) and
metadata (sample sizes, date of beta session).

---

## Phase D — Implement player-style bots

### D1. New strategy resolver
Add `engine/style_strategy.py` with a `best_play_for(profile, hand, dealer_up,
visible_cards, valid_actions, drinking_mode)` function:
1. Build the lookup key from hand/dealer/visible-card state.
2. Check the player's deviation table for that key (most specific match
   first: suited/table-aware key, then basic key).
3. If found and confidence/sample size meets threshold → return that action.
4. Otherwise fall back to `strategy.best_play(...)`.

### D2. Wire into `NPC_Player`
Extend `NPC_Player` (or add a `StylePlayer` subclass) that takes a
`profile` argument and calls `style_strategy.best_play_for(...)` instead of
`strategy.best_play(...)` in `decide()`. Keep the existing basic-strategy
`NPC_Player` as the default/"Bot" option.

### D3. Setup / UI
- Add selectable bot personalities in the setup screen (e.g. "Rob-bot",
  "Marko-bot", "David-bot", alongside the existing generic "Bot").
- Surface which deviations a bot is known for somewhere (optional, fun
  "cheat sheet" — e.g. an admin/debug view listing each profile's learned
  deviations).

---

## Phase E — Testing & validation

- Unit tests for `style_strategy.best_play_for`: given a small fixture
  profile, confirm correct fallback behavior (known deviation vs. unknown
  spot vs. insufficient-sample spot).
- Regression test: a `StylePlayer` with an **empty** profile must behave
  identically to plain `NPC_Player` (pure basic strategy) — guards against
  the fallback chain breaking.
- Manual validation: after building profiles from the beta log, re-run the
  beta log's situations through `best_play_for` and check the bot's choice
  matches the player's actual majority choice for the deviation spots
  identified in Phase C.

---

## Open questions / decisions needed before starting

1. How many beta rounds are realistic to get ≥150-300 decisions/player?
   (Roughly: each round gives each player ~1-2 decisions on average, so this
   likely means 100-200+ rounds — a few longer sessions.)
2. Minimum sample-size/majority thresholds for C1/C2 — start conservative
   (≥3 samples, ≥60%) and tune after seeing real data volume.
3. Do we want the "table card bias" feature (C2) at all for v1, given it
   needs the most data? Could be deferred to a v2 once basic per-player
   deviation tables are working and more sessions have been logged.
4. Where do beta logs live and for how long — keep raw JSONL logs
   (gitignored) for future re-training, or just keep the derived profiles?

---

## Summary of required steps

1. Add decision-logging hook to the engine (Phase A).
2. Play a beta session (Rob, Marko, David) with logging on (Phase B).
3. Build per-player deviation tables/profiles from the log (Phase C).
4. Implement style-aware strategy resolver + bot wiring (Phase D).
5. Test fallback behavior and validate against the beta log (Phase E).
