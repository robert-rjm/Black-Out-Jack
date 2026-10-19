# File-Splitting Refactor Plan

Audit of files that have grown past a single responsibility. Splits are grouped by
logic (feature / layer), ordered by payoff-vs-risk. **Pure moves only** — no
behaviour changes in these steps; every step must leave `pytest` green and the
game playable.

## Ground rules

- One file split per commit; run `pytest` (and click through the affected UI) after each.
- **Python:** keep the old module path importable by turning it into a thin
  re-export (`from .new_module import *`-style explicit imports) until all callers
  and tests are migrated, then delete the shim. Mind circular imports —
  `serializer.py` is imported by many services (`round_phase`, `current_turn`,
  `serialize_card`), so the helpers they need must move to a leaf module first.
- **JS:** the app is classic (non-module) scripts concatenated by
  `app/services/asset_bundler.py` (`JS_SOURCES`) and listed in
  `templates/partials/index/_scripts.html`. Both lists must be updated together,
  in the same order. Top-level `const`/`class` declarations are order-sensitive
  (TDZ), so new files must load **after** anything they reference at load time
  and **before** the files that call them at load time. Functions referenced only
  from event handlers are order-insensitive.
- `static/js/bundle.js` and `static/css/bundle.css` are generated at startup; never edit.
- Update `docs/Architecture.md` and `docs/DOM-Hooks.md` file references at the end.

## Size snapshot (non-generated, non-data)

| Lines | File | Verdict |
|---:|---|---|
| 2302 | tests/app/test_targeted_drinking.py | split |
| 1772 | static/js/ui/table-modals.js | split (6 unrelated panels) |
| 1734 | static/js/ui/admin.js | split (misnamed grab-bag) |
| 1193 | app/services/serializer.py | split |
| 1113 | tests/app/test_dealer_lottery.py | optional |
| 1108 | static/js/ui/table.js | split (lower priority) |
| 1099 | app/routes/polling.py | split |
| 1080 | static/js/ui/admin-settings.js | split |
| 1004 | app/services/drink_tracker.py | split |
| 994 | app/routes/admin.py | split |
| 967 | app/routes/game_commands.py | light split |
| 897 | engine/drinking_rules.py | leave or light split |
| 846 | engine/blackjack.py | light split |
| 820 | engine/referee.py | leave |
| 779 | app/services/targeted_drinking.py | light split |
| 658 | app/models/state_schema.py | optional |
| 618 | static/js/ui/setup.js | split off misplaced code |
| 694 / 666 | modals.css / utilities.css | optional |

Fine as-is: `game_engine.py` (644, cohesive), `game_room.py` (623, already
dataclass-per-concern), `lobby.py`, `reports.py`, `tick.py`, small services.

---

## Phase 1 — Frontend: `admin.js` and `table-modals.js` (highest payoff)

These two files are mostly *feature panels* that were appended wherever there was
room. Both are named for something they only partly contain.

### 1.1 Split `static/js/ui/admin.js` (1734 lines) by feature

| New file | Content (current lines approx.) |
|---|---|
| `ui/roles.js` | `updateRoleUI`, suggest picker (`toggleSuggestPicker`, `sendSuggest`, `respondSuggest`), admin setting toggles (`setStrategyHintEnabled`, `setWildCardEnabled`, `setEasyModeAdmin`, `setGodMode`, `setBustVoteEnabled`), local-seat switching (`cycleLocalSeat`, `showLocalSeatPicker`, `requestLocalSeat`) — L1–355 |
| `ui/bust-vote.js` | `submitBustVote`, `BustVotePanel`, `giveBustSip`, `BustGivePanel` — L193–690 |
| `ui/dealer-lottery.js` | `dlStakeLabel`, `DealerLotteryEntryPanel`, reveal modal helpers (`_dl*`, `_showDealerLotteryRevealModal`), `giveDealerLotterySip`, `DealerLotteryGivePanel` — L691–1146 |
| `ui/toasts-player.js` (or merge into `log.js`) | `_firePlayerToast`, `showBustVoteToast`, `showBustHandoutToast`, `showTargetedDrinkingHandoutToast`, `showInsuranceToast` — L1237–1312. `log.js` already owns the other toasts; moving these there centralises toast code. |
| `ui/registration.js` | register overlay, `PendingRegBanner`, `doRegister`, seat-transfer queue, `handleRegistration`, `doSpectate` — L1314–1590 |
| `ui/bets.js` | `_updateBetPanel`, stepper limits, `_changeBet`, `setPlayerBet`, `setAnimToggle` — L1595–end |

`TargetedDrinkingGivePanel` / `giveTargetedDrinkingSip` (L1148–1234) belongs with
the targeted-drinking file in 1.2, not here.

### 1.2 Split `static/js/ui/table-modals.js` (1772 lines) by feature

| New file | Content |
|---|---|
| `ui/insurance.js` | `InsurancePanel`, `castInsuranceVote` — L1–297 |
| `ui/milestone.js` | `MilestonePanel`, `milestoneAdjust`, `submitMilestoneHandout` — L298–582 |
| `ui/targeted-drinking.js` | `TargetedDrinkingPanel`, vote/begin/continue, `_tdRevealLine`, `TargetProposalPanel`, `castTargetProposalVote`, `proposeTargetedDrinkingTarget`, plus `TargetedDrinkingGivePanel`/`giveTargetedDrinkingSip` from admin.js — L583–1360. This is the single largest block (~780 lines); consider a further split: `targeted-drinking.js` (round panel) and `target-proposal.js`. |
| `ui/admin-afk.js` | `AdminAfkPanel`, `_postAdminAfk`, open/cast — L1361–1496 |
| `ui/drink-rate.js` | `_rateName`, `DrinkRatePanel`, `_postDrinkRate`, open/close, `LateJoinPanel` — L1497–end |

After this, delete `table-modals.js`; `ui/` ends up with roughly one file per game feature.

### 1.3 Split `static/js/ui/admin-settings.js` (1080 lines)

| New file | Content |
|---|---|
| `ui/settings-players.js` | settings subview + `openKickModal` (L1–~340, the big player-list renderer) and the player actions `doTransferAdmin`, `doVoteKick`, `doMakeHuman/Bot`, `doSetPersonality`, `doKick`, `doResetRegistration`, `doUndoKick`, rejoin handlers, `renderKickVoteBanner` |
| `ui/settings-game.js` | `_populateSettingsUI`, queued-settings banner, `queueSettings`, add/remove player, rotate dealer, `takeBackSeat`, targeted-drinking admin controls |
| `ui/summary-export.js` | rules modal, final summary modal, CSV/decision-log export + auto-export, `resetToSetup` (L510–552, L923–end) |

`openKickModal` alone is ~320 lines — extract inner row builders into helpers
while moving it (the only non-mechanical change in this phase; keep it separate).

### 1.4 `static/js/ui/setup.js` (618 lines) — move out misplaced code

- `DrinkUI` state + `openLastRoundModal` (L1–60) → `ui/drink-summary.js` (it is
  drink-summary state used by `table.js`/`log.js`, not setup). **Load order:**
  `DrinkUI` is a top-level `const` used at call time only, but keep it before
  `table.js`.
- Idle watcher (L525–end: `IDLE_*`, `_playIdleSound`, `resetIdleTimer`,
  `startIdleWatcher`) → `ui/idle-watcher.js`.
- Waiting-room (`renderWaitingPlayers`, `startWaiting`) → `ui/lobby.js` (already exists).
- What remains in `setup.js` is the game-setup form — correctly named.

### 1.5 `static/js/ui/table.js` (1108 lines) — lower priority

| New file | Content |
|---|---|
| `ui/table-build.js` | `buildGameUI`, `buildRefereeUI`, `buildDigitalUI`, button/grid builders, selection helpers (L1–225) |
| `ui/table-commands.js` | `sendResult/Action/DigitalPlay/Preselect`, `sendCmd`, `tryDeal` (L213–365) |
| `ui/apply-state.js` | the `_apply*`/`_sync*` helpers and `applyState` (L366–715) |
| `ui/table-prompts.js` | honor prompt, bank-run prompt, best-play, action-button state (L715–884) |
| `ui/drinks-panel.js` | `DrinksPanel`, `autoSwitchDigTab`, `activateDigTab` (L885–end) |

### 1.6 Bundler / template updates (do once per file moved)

Update `JS_SOURCES` in `asset_bundler.py` **and** `_scripts.html` together. New
panel files can be inserted where their parent file was. Verify by loading the
page with the console open — a missing class shows up as `ReferenceError` on boot.

---

## Phase 2 — Backend: routes

### 2.1 Split `app/routes/polling.py` (1099 lines)

Despite the name, it holds registration, votes, side-bets and targeted drinking.
Keep `polling.py` for `/state` only.

| New blueprint module | Routes |
|---|---|
| `routes/polling.py` | `/state` |
| `routes/registration.py` | `/register`, `/request_local_seat`, `/handle_seat_transfer`, `/handle_registration`, `/reset_registration` |
| `routes/suggestions.py` | `/preselect`, `/suggest_action`, `/respond_suggest` |
| `routes/side_bets.py` | `/vote_insurance`, `/cast_bust_vote`, `/give_bust_sip`, `/set_player_bet` |
| `routes/dealer_lottery.py` | `/dealer_lottery/enter`, `/dealer_lottery/give_sip` |
| `routes/targeted_drinking.py` | all `/targeted_drinking/*` routes from polling.py **and** admin.py (start/cancel/continue) — one blueprint for one feature |

Register new blueprints in `app/__init__.py`. Note `polling.py` imports
`_require_admin` / `_require_host_or_dealer` from `admin.py` — move those to a
new `app/routes/_auth.py` first (step 2.0) to avoid route-to-route imports.

### 2.2 Split `app/routes/admin.py` (994 lines)

| Module | Routes |
|---|---|
| `routes/_auth.py` (new, step 2.0) | `_require_admin`, `_require_host_or_dealer` |
| `routes/moderation.py` | `/kick`, `/undo_kick`, `/vote_kick`, `/request_rejoin`, `/handle_rejoin`, `/leave_room` |
| `routes/admin_transfer.py` | `/transfer_admin`, `/admin_afk/*`, `_auto_transfer_admin`, `_hand_admin_to_voter` |
| `routes/players.py` | `/make_bot`, `/make_human`, `/set_bot_personality`, `/take_back_seat`, `/rotate_dealer` |
| `routes/admin.py` (remainder) | `/update_settings`, `/set_hint`, `/set_anim_pref`, `/toggle_god_mode`, `/claim_milestone` |

`/claim_milestone` (~115 lines of logic) should move its body into
`drink_tracker`/a `milestone` service and leave the route thin (see 3.2).

### 2.3 `app/routes/game_commands.py` (967 lines) — light split

- Extract action helpers (`_record_strategy_decision`, `_check_honor_house_rule`,
  `_penalize_unsplit_aces`, `_perform_action_without_honor`, `_after_player_action`,
  `_resolve_endround`) to `app/services/player_actions.py` (they are not HTTP logic).
- Extract the `_cmd_*` digital handlers + registries to `routes/commands/digital.py`
  and referee handlers to `routes/commands/referee.py`; leave `/command`, `/rebuy`,
  `/honor_resolve` and the dispatcher in `game_commands.py`.
- `_print_digital_help` → alongside the digital handlers.

---

## Phase 3 — Backend: services

### 3.1 Split `app/services/serializer.py` (1193 lines)

It mixes round-state derivation, per-feature serializers, stats computation and
the top-level snapshot. Other services import `round_phase`/`current_turn`/
`serialize_card`/`hand_done`, so split bottom-up:

| New module | Content |
|---|---|
| `services/round_state.py` (leaf; no serializer imports) | `play_order`, `hand_done`, `player_done`, `current_turn`, `round_phase`, `serialize_card`, `serialize_hand` |
| `services/stats.py` | `_compute_live_drink_totals`, `compute_sip_totals`, `compute_payout_data`, `compute_best_play`, `compute_mandatory_split*`, `compute_trophy_holder`, `compute_kpi_stats` (the 140-line KPI function is the next candidate to decompose) |
| `services/serializers/` package: `milestone.py`, `dealer_lottery.py`, `targeted_drinking.py`, `insurance.py`, `bust_vote.py`, `drink_rate.py` / `admin_afk.py` | the `_serialize_*` per-feature helpers |
| `services/serializer.py` | `serialize_state` only, importing from the above |

Migrate `afk.py`, `game_engine.py`, `tick.py`, `drink_rate.py`,
`dealer_lottery.py`, `targeted_drinking.py` to import from `round_state`. This
also removes the services → serializer dependency direction, which is currently
backwards (domain logic importing a presentation layer).

### 3.2 Split `app/services/drink_tracker.py` (1004 lines)

| New module | Content |
|---|---|
| `services/drink_tracker.py` | `award_sips` (the core) + rule classification |
| `services/bust_vote_penalties.py` | `apply_bust_vote_penalties`, `apply_bust_handout_forfeit` |
| `services/round_harvest.py` | `harvest_drink_log` and its `_record_*`/`_update_*`/`_snapshot_round`/`_with_raw` stat helpers (L357–708) |
| `services/milestones.py` | milestone check/assign/tie/round-robin/forfeit (L709–end) plus the body of `/claim_milestone` |

`tests/app/test_harvest_helpers.py` and `test_milestone_win_streak.py` already
map 1:1 to the last two.

### 3.3 `app/services/targeted_drinking.py` (779 lines) — light split

- `target_proposal.py`: `propose_targeted_drinking_target`,
  `submit_target_proposal_vote`, `_finish_target_proposal`,
  `_maybe_resolve_target_proposal`, `apply_target_proposal_vote_forfeit`
  (L545–717) — a separate sub-feature (vote to propose a target).
- Leave round lifecycle + `resolve_targeted_drinking_round` (210-line function;
  split the function itself into draw / score / payout steps in a later pass).
- Also fold in the duplicate `_targeted_drinking_awaiting_start` in the serializer
  (L135) vs `targeted_drinking_awaiting_start` here — dedupe while moving.

### 3.4 `app/models/state_schema.py` (658 lines) — optional

Pure Pydantic models, cohesive but long. If split: `schema/core.py`
(cards/hands/seat/clients/log events), `schema/kpi.py`, and one file per feature
(`dealer_lottery`, `drink_rate`, `targeted_drinking`, `milestone`) mirroring the
`serializers/` package in 3.1; `AppState` stays in `state_schema.py`.

---

## Phase 4 — Engine (low priority)

- `engine/blackjack.py` (846): cards/shoe/hand/player (`Suit`…`NPC_Player`,
  ~L1–360) → `engine/cards.py` + `engine/players.py`; `HandEvaluator` +
  `RoundManager` stay. Keep `engine/blackjack.py` re-exporting, since scripts and
  the profiles likely import from it.
- `engine/drinking_rules.py` (897): `DrinkingRules` is one cohesive 650-line
  static-method class; `DrinkTracker` (L704–end) → `engine/drink_tracker.py`.
  Leave `DrinkingRules` itself, optionally grouped into mixin modules later.
- `engine/referee.py` (820): one class; leave.

## Phase 5 — Tests and CSS (do alongside the matching source split)

- `tests/app/test_targeted_drinking.py` (2302 lines, ~16 `# ----` sections) →
  `tests/app/targeted_drinking/` with `conftest.py` (the `_ScriptedDeck` and
  helpers, L47–160) and files by section: `test_trigger.py`, `test_voting.py`,
  `test_resolution.py`, `test_proposals.py`, `test_handouts.py`,
  `test_serializer.py`. Mirror the service split in 3.3.
- `tests/app/test_dealer_lottery.py` (1113): same treatment if it keeps growing;
  otherwise leave.
- `static/css/components/modals.css` (694): split by feature to match the JS
  panels (`modal-targeted-drinking.css`, `modal-drink-rate.css`, …) and add to
  `CSS_SOURCES`; `utilities.css` (666) deserves an audit for feature-specific
  rules that belong next to their component.

---

## Suggested order

1. **2.0** `_auth.py` extraction (tiny, unblocks routes).
2. **3.1** serializer → `round_state.py` first (breaks the import-direction smell).
3. **1.2 → 1.1** frontend panels (`table-modals.js`, `admin.js`) — largest readability win, lowest runtime risk.
4. **2.1 / 2.2** route splits.
5. **3.2 / 3.3** drink_tracker and targeted_drinking.
6. **1.3 – 1.5**, **2.3**, then Phases 4–5 as time allows.

## Risks / watch-outs

- Circular imports in Python (`routes/polling` ↔ `routes/admin`, services ↔ serializer) — resolve via leaf modules, not lazy imports.
- JS globals: no module system, so function names must stay unique across files; grep for collisions before moving.
- Tests may monkeypatch `app.services.drink_tracker.<name>` or `app.routes.polling.<name>`; after a move, patch targets must point at the module where the name is *used*.
- Docs (`Architecture.md`, `DOM-Hooks.md`, `Dev-Cheat-Sheet.md`) reference file paths; update in the same commit as each move.
