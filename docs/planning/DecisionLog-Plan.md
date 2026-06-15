# Decision Logging & Player-Mimicry Bot Plan

Goal: record every in-game decision (hit/stand/double/split/insurance) made by
each human player, with enough board-state context (own hand, dealer upcard,
**all other visible cards on the table**) to later train per-player bot models
("Rob", "Marko", "David") that mimic each person's real tendencies — alongside
the existing standard basic-strategy bot as a baseline/control.

This is independent of the Normal Mode rebuild (`NormalMode-Plan.md`) and
applies to **both Drinking and Normal modes** — the decision data is the same
shape in either mode; only `drinking_mode`/`bet_amount` context differs.

Status: Phase C mostly done — C1, C2, C3 (incl. C3a, resolved as manual
session-scoped export), C4, and C5 (automated tests) are implemented. Only
the C5 manual play/export spot-check remains before exit criteria are fully
met. See per-section status below. Split into two
phases — **Phase C (logging + export)** is the near-term buildable piece;
**Phase D (training + bot integration)** is the future payoff and can be
designed in more detail once real data exists.

---

## Phase C — Decision logging + export

### C1. Data schema — ✅ DONE
One row per player decision (`hit`, `stand`, `double`, `split`, `insurance`),
captured **before** the action mutates the hand:

| Field | Description |
|---|---|
| `session_id` / `room_code` | identify the game session |
| `timestamp` | wall-clock time |
| `round` | `session.round_count` |
| `player` | player name (Rob/Marco/David/etc.) |
| `hand_index` | which of the player's hands (for splits) |
| `dealer_name` | who's dealing this round (dealer never acts as "player" here) |
| `hand_cards_before` | player's current hand cards at decision time |
| `hand_total_before` | hand value (soft/hard) |
| `is_soft` | bool |
| `dealer_upcard` | dealer's visible card |
| `visible_cards` | **every** card visible table-wide at this instant: all
  players' hands-in-play + dealer upcard. This is the "many 10s already out"
  signal — a simple rank-count histogram derived from this is the basic
  counting feature. |
| `cards_remaining` / `decks_in_play` | shoe depth, for density normalization |
| `valid_actions` | which actions were legally available (h/s/d/sp/insurance) |
| `action_taken` | the actual choice |
| `basic_strategy_action` | what `compute_best_play()` recommends for this
  state — lets us measure each player's *deviation* from basic strategy, which
  is itself a useful training signal |
| `drinking_mode`, `mode` | session context |
| `bet_amount` (normal) / `wager` (drinking) | stake context |
| `hand_result` | win/loss/push — **backfilled** after `_resolve_endround` |

### C2. Capture hooks (`app/routes/game_commands.py`) — ✅ DONE
- Add a small helper in a new module `app/services/decision_log.py`:
  `record_decision(session, player, hand, action)` — builds the row above
  from current session state and appends to `session._decision_log` (new
  `GameRoom` field, `list`, mirrors `_drink_csv_rows`).
- Call it at the top of `_cmd_hit`, `_cmd_stand`, `_cmd_double`, `_cmd_split`,
  `_cmd_insurance` — **before** the underlying engine call mutates the hand,
  so `hand_cards_before`/`hand_total_before` reflect the pre-action state.
- `visible_cards` snapshot: a helper `_snapshot_visible_cards(session)` that
  walks `session.all_players` + dealer's revealed upcard and flattens all
  dealt cards currently showing (respecting the hidden-hole-card rule — the
  dealer's hole card is *not* visible to players and must be excluded).
- Backfill pass: in `_resolve_endround` (or `apply_payouts`/`drink_tracker`,
  whichever runs after results are assigned), walk `session._decision_log`
  entries for the current round and fill in `hand_result` once
  `hand.result` is set.
- NPC/bot actions: log them too but tag `is_npc: true` — useful for sanity
  checks (e.g. confirming the "standard" bot always matches
  `basic_strategy_action`), but excluded by default from training exports.

### C3. Export route (`app/routes/reports.py`) — ✅ DONE
- ✅ New `GET /export_decisions?room_code=...&player=<name optional>`
- ✅ Returns CSV (one row per decision, columns as in C1) — same
  BOM/`Content-Disposition` pattern as `/export_csv`.
- ✅ Available in **both** modes (not gated by `drinking_mode`), unlike the
  existing sip-focused export.
- ✅ C3a resolved: **session-scoped download only**, no persistent
  server-side file. Workflow is "play a session → hit Export Decision Log
  before closing the room." Rows live in `session._decision_log`
  (in-memory) until exported or the session expires.
  - Rationale: avoids an admin-toggle/opt-in UX and any disk-write/PII
    surface for a v1; each export already contains everything needed for
    Phase D. If accumulating across sessions becomes painful in practice
    (forgetting to export, wanting a running dataset), revisit a
    persistent-file opt-in then — but don't build it speculatively.
  - Practical note: each export's `session_id` differs per room, so the
    Phase D loader should just concatenate exported CSVs rather than rely on
    a single growing file.

### C4. Frontend — ✅ DONE
- Added an "⬇️ Export Decision Log" button (admin settings modal,
  `_modals.html` / `admin-settings.js`) — visible in both modes, separate from
  the drinking-only "Export Drinks CSV" button.
- No other UI changes required for Phase C; this is a data-collection feature,
  not a gameplay feature.

### C5. Testing (Phase C) — ✅ AUTOMATED TESTS DONE
- [x] Unit test: scripted hit/split decision; assert `_decision_log` rows have
  correct `hand_cards_before`/`hand_total_before` (captured *before*
  mutation) and correct `visible_cards`. See
  `tests/test_decision_log.py::test_record_decision_captures_pre_action_state`.
- [x] Unit test: dealer hole card never appears in `visible_cards` while
  hidden. See
  `tests/test_decision_log.py::test_visible_cards_excludes_hidden_dealer_hole_card`.
- [x] Unit test: `hand_result` backfill — every row for the resolved round
  gets a non-null `hand_result`, idempotently, without touching other rounds'
  rows. See `tests/test_decision_log.py::test_backfill_hand_results`.
- [x] Unit test: `/export_decisions` returns well-formed CSV with the
  documented columns for both Normal mode (`bet_amount` populated, `wager`
  empty) and Drinking mode (vice versa), plus a 404 for an unknown room. See
  `test_export_decisions_normal_mode`, `test_export_decisions_drinking_mode`,
  `test_export_decisions_no_session_returns_404`.
- [ ] Manual: play a few rounds across both modes, export via the UI button,
  spot-check rows by hand against what was actually played. (Not
  automatable — outstanding follow-up for Robert.)

### Exit criteria for Phase C — NEARLY MET
- ✅ Every player decision in a session is captured with full board-state
  context and the eventual result.
- ✅ CSV export works in both modes — verified by automated tests
  (`tests/test_decision_log.py`); manual UI spot-check still recommended.
- ✅ C3a resolved (session-scoped manual export, see C3 above).

---

## Phase D — Per-player bot training & integration (future)

Not designed in detail yet — sketch only, to revisit once Phase C has produced
real data from actual sessions with Rob, Marco, and David.

### D0. Data loading — ✅ DONE (`scripts/load_decision_logs.py`)
- Loads every `decision_log_*.csv` from `data/decisions/` (configurable via
  `--dir`), concatenates them, and prints a per-player breakdown: total
  decisions, action counts (h/s/d/sp/insurance), NPC vs. human, deviation
  from `basic_strategy_action`, and win/loss/push split.
- `--player <name>` filters the summary to one player.
- `--out <path>` writes the concatenated rows to a single combined CSV for
  D1 to consume.
- Run this periodically as exports accumulate to gauge whether there's
  "enough" data per player yet (see Open questions below).

### D1. Feature engineering (offline script, `scripts/train_player_bot.py`)
- Load accumulated `decisions.csv` (via `load_decision_logs.py --out`),
  filter to one player.
- Derive features from `visible_cards`: counts of each rank still
  unseen/seen (simple counting signal), `hand_total_before`, `is_soft`,
  `dealer_upcard`, `valid_actions`, `cards_remaining`.
- Label = `action_taken`.
- Also compute `deviates_from_basic_strategy` (action_taken !=
  basic_strategy_action) as a diagnostic — how "by the book" vs. "by feel"
  each player is, and under what conditions they deviate (e.g. more deviation
  when many 10s are visible).

### D2. Model
- Start simple: a decision tree / gradient-boosted classifier per player,
  predicting `action_taken` from the feature set above, restricted to
  `valid_actions` at inference time.
- Baseline comparison: the existing "standard" bot is just
  `compute_best_play()` — no training needed, already the control group.

### D3. Bot integration (`engine/blackjack.py`)
- Extend `NPC_Player` with a `personality` field (`"basic"`, `"rob"`,
  `"marco"`, `"david"`).
- `best_play()` (or a new `personality_play()`) loads the relevant trained
  model and predicts an action, falling back to `compute_best_play()` for
  states with no/low-confidence training coverage (cold start, since real
  per-player data will be sparse early on).
- Setup UI: when adding an NPC seat, choose personality from a dropdown.

### D4. Testing (Phase D)
- Offline: train/test split on collected decisions, report accuracy vs. basic
  strategy as baseline per player.
- In-game: NPC with a given personality plays a session; spot-check that its
  choices look plausible (not just always matching basic strategy, not
  picking illegal actions).

### Open questions for Phase D
- How much data is "enough" per player before a model is meaningfully
  different from basic strategy? (Likely needs many sessions — Phase C should
  run for a while before D1 is attempted.)
- Per-decision-type models (separate hit/stand vs. double vs. split
  classifiers) or one multi-class model gated by `valid_actions`?
- How to handle the cold-start / low-confidence fallback cleanly so the bot
  never looks "broken" early on.
