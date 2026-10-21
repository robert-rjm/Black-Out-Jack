# File Placement Refactor Plan

Audit of code, routes and docs that live in the wrong file or layer. This is
the companion to [FileSplitRefactor.md](FileSplitRefactor.md): that plan splits
files that grew too big, this one fixes things that are in the **wrong place**.
Where the two overlap (the `admin.js` split, the `lobby.js` polling split) this
plan says what moves where and defers the how to that file's ground rules.

**Pure moves only.** No behaviour changes. Every step leaves `pytest` green and
the game playable. One step per commit, and click through the affected UI after
each JS step.

Already done: step 1 (services importing from routes), section 6 (routes),
section 7 (docs and data), section 2 (`admin.js`), section 3 (`lobby.js`), section 4 (`setup.js`), section 5 (`admin-settings.js`), and the "Tip us" code moved from `lobby.js` into
`static/js/ui/tip.js` (bundler list, `DOM-Hooks.md` and `Architecture.md`
updated).

## Ground rules

- Same JS rules as FileSplitRefactor.md: classic scripts, concatenated by
  `app/services/asset_bundler.py` (`JS_SOURCES`). New files must load after
  anything they reference at load time and before files that call them at load
  time. Functions only referenced from event handlers are order-insensitive;
  top-level `const`/`class` declarations are not (TDZ).
- `static/js/bundle.js` and `static/css/bundle.css` are generated; never edit.
- Python moves keep the old import path working (thin re-export) until every
  caller and test is migrated, then the shim is deleted.
- Update `docs/Architecture.md` and `docs/DOM-Hooks.md` at the end of each step.

## Findings

| # | Area | Problem | Priority |
|---|---|---|---|
| 1 | Python layering | `services/` imports from `routes/` | High (small, a real violation) |
| 2 | `admin.js` | A grab-bag of unrelated panels, not an admin file | High (largest payoff) |
| 3 | `lobby.js` | Holds the whole polling / disconnect layer and the room QR popup | Medium |
| 4 | `setup.js` | Holds the waiting room and the idle watcher | Medium |
| 5 | `admin-settings.js` | Holds the Rules modal, session summary and exports | Medium |
| 6 | Routes | Static and doc routes in `reports.py`, tip routes in `lobby.py` | Low |
| 7 | Docs / data | Stale ownership notes, `data/` tracking mismatch | Low |

## 1. Services importing from routes

**Status: done.** `auto_transfer_admin` / `transfer_local_names` now live in
`room_manager.py`; `deal_now` and `resolve_endround` (was `_resolve_endround`)
now live in `game_engine.py`. `grep -rn "from app.routes" app/services` is empty
and `pytest` is green (817). The notes below describe the original problem.

Services should never import from `app/routes/`. Two cases today:

- `app/services/tick.py` lazily imports `deal_now` from
  `app/routes/game_commands.py` (`apply_stake_window`).
- `app/services/boj_switch.py` lazily imports `_auto_transfer_admin` from
  `app/routes/admin.py` (`_leave_old_room`).

Plan:

1. Move `_auto_transfer_admin` and its helper `_transfer_local_names` into a
   service. `room_manager.py` is the natural home (it already owns queued
   settings and dealer rotation). Keep `_auto_transfer_admin` importable from
   `routes/admin.py` until its callers (`leave_room`, `kick`, vote handlers)
   use the new location.
2. Move `deal_now` out of `game_commands.py` into `game_engine.py` (or a new
   `services/dealing.py` if it drags in too much). `game_commands.py` then
   imports it, and so does `tick.py`, with no lazy import left.
3. Drop the lazy imports and check with
   `grep -rn "from app.routes" app/services` that it returns nothing.

Done when: that grep is empty and `pytest` is green.

## 2. Split `admin.js`

**Status: done** except `updateRoleUI`, which stays (it is the admin / player role
UI). `ui/seats.js` (local seats, registration, seat transfers, spectate) and
`ui/bets.js` (Normal-mode stake panel) were split out after the drink panels;
`admin.js` is now about 330 lines. **Drink panels:** (`ui/drink-panels.js`, loaded just before
`admin.js`). Moved verbatim: the bust-vote panel and `submitBustVote`, the
bust / Dealer Lottery / Targeted Drinking / buy-in handout panels, the Dealer
Lottery reveal modal and the player toasts. `admin.js` went from about 1,900 to
about 830 lines at that point. The notes below describe the original problem.

`admin.js` (about 1,900 lines) is not about admin. What is in it today and
where each group should go:

| Group | Contents | New file |
|---|---|---|
| Drink / handout panels | `BustVotePanel`, `BustGivePanel`, `giveBustSip`, `DealerLotteryEntryPanel`, `DealerLotteryGivePanel`, `dlStakeLabel`, `_dl*` helpers, `submitDealerLotteryX`, reveal modal fns, `TargetedDrinkingGivePanel`, `giveTargetedDrinkingSip`, `BuyinGivePanel`, `giveBuyinSip` | `ui/drink-panels.js` |
| Player toasts | `_firePlayerToast`, `showBustVoteToast`, `showBustHandoutToast`, `showTargetedDrinkingHandoutToast`, `showInsuranceToast` | `ui/drink-panels.js` (or `ui/toasts.js`) |
| Registration and seats | `updateRegisterOverlay`, `_showRegister*`, `PendingRegBanner`, `showRegisterOverlay`, `doRegister`, `handleRegistration`, `doSpectate`, `_processSeatTransferQueue`, `_handleSeatTransfer`, `_syncSeatTransfers`, `cycleLocalSeat`, `_updateLocalSeatSwitcher`, `showLocalSeatPicker`, `requestLocalSeat`, `updateRoleUI` | `ui/seats.js` |
| Cash / bets | `_updateBetPanel`, `_syncBetStepperLimits`, `_changeBet`, `confirmStake`, `setPlayerBet` | `ui/bets.js` |
| Settings toggles | `setBustVoteEnabled`, `setStrategyHintEnabled`, `setWildCardEnabled`, `setEasyModeAdmin`, `setDrinkingModeAdmin`, `setBuyinHandouts`, `setGodMode`, `setAnimToggle`, `setPaused`, `_syncPausedOverlay` | stays in `admin.js` (the only parts that are admin) |
| Suggestions | `toggleSuggestPicker`, `sendSuggest`, `respondSuggest`, `submitBustVote` | `ui/table-modals.js` or stays |

Order caution: the panel classes are top-level `class` declarations and are
instantiated at load time (`const dealerLotteryGivePanel = new ...`), and
`table.js` mounts them in `buildDigitalUI()`. The new files must load before
`table.js` runs `buildDigitalUI()` but that is at call time, so any position
before `bootstrap.js` / `app.js` is safe. Keep the panels' relative order.

Do this as separate commits, one group per commit, drink panels first (largest
and most self-contained).

## 3. Split `lobby.js`

**Status: done.** `ui/poll.js` (poll loop, disconnect screens, visibility
re-poll) and `ui/room-qr.js` (room invite popup) now load right after
`lobby.js`; `lobby.js` is down to about 150 lines (age gate, create / join /
cancel / back to lobby). Moved verbatim; the shared counters stayed in
`state.js`. The notes below describe the original problem.

`lobby.js` mixes three things:

- **Lobby proper:** age gate, create / join / cancel / back to lobby.
- **Polling and connection:** `_pollInterval`, `fetchState`, `_onPollFailure`,
  `showDisconnected`, `showGiveUpScreen`, `tryAgainFromGiveUp`,
  `_updateDisconnectElapsed`, `hideDisconnected`, `_applyStateResult`,
  `startPolling`, `stopPolling`, and the `visibilitychange` re-poll.
- **Room QR popup:** `openRoomQr`, `closeRoomQr`, `copyInviteLink`.

Plan:

1. New `ui/poll.js` for the polling and connection group. It is shared state
   used by every screen. It loads right after `lobby.js` (everything in it is
   call-time only, and the counters it uses stay in `state.js`).
2. Move the room QR popup next to the other invite code: `DOM-Hooks.md` already
   claims it is in `setup.js`, so either move the code there or (preferred)
   into a small `ui/room-qr.js`, and fix the doc.

## 4. `setup.js`

**Status: done.** The waiting room (`renderWaitingPlayers`, `startWaiting`) moved
into `lobby.js`; the idle watcher moved to `ui/idle.js` (loaded right after
`setup.js`). `setup.js` is about 435 lines of actual game setup.

**Leftovers: done.** `DrinkUI` and the `sel` / `selRank` / `selSuit` globals moved to
the top of `table.js` (their users are all in `table.js`, `table-modals.js`,
`table-render.js`, `admin.js`, `lobby.js` and `summary.js`, every one a call-time
use, so no load-order change was needed). The original note follows.

Leftovers found while doing this: `setup.js` still opens with
`DrinkUI` (the drink-summary / milestone-toast state) and the `sel` /
`selRank` / `selSuit` table-selection globals. `DrinkUI` is read by `table.js`
and `table-modals.js` at call time, so it could move to `drink-panels.js` (it must
then load before them, i.e. stay ahead of `table.js` in `JS_SOURCES`), and `sel`
to `table.js`. The notes below describe the original problem.

`setup.js` also owns two things that are not game setup:

- Waiting room: `renderWaitingPlayers`, `startWaiting` (FileSplitRefactor.md
  already plans this into `lobby.js`).
- Idle watcher: `_playIdleSound`, `resetIdleTimer`, `_tickIdleWatcher`,
  `startIdleWatcher` (a small `ui/idle.js`).

## 5. `admin-settings.js`

**Status: done.** `ui/rules.js` (Rules modal) and `ui/summary.js` (session summary,
drink CSV / decision-log downloads, auto-export) load right after
`admin-settings.js`; `resetToSetup` moved to the end of `lobby.js`.
`admin-settings.js` is down from about 1,160 to about 900 lines (settings and
players modals, game settings, Targeted Drinking admin controls). The notes
below describe the original problem.

Not settings: the Rules modal (`_ruleSlug`, `_decorateRules`, `openRulesModal`,
`closeRulesModal`, `handleRulesBackdropClick`), the session summary and exports
(`showSessionSummary`, `closeSummaryModal`, `exportDrinkCSV`,
`exportDecisionLog`, auto-export helpers) and `resetToSetup`.

Plan: `ui/rules.js` for the Rules modal, `ui/summary.js` for the summary and
exports. `resetToSetup` goes with the lobby code. FileSplitRefactor.md section
1.3 already covers the `admin-settings.js` split, so do both in one pass.

## 6. Routes

**Status: done.** New `routes/static_pages.py` blueprint serves `/logo.png`,
`/manifest.json`, `/rules`, `/beer` and `/beer_qr` (URLs unchanged). The shared QR
renderer moved to `services/qr.py` (`qr_svg`) so `lobby.py` (`/room_invite`) and
`static_pages.py` both use it. All 817 tests pass and every moved URL was
checked. The notes below describe the original problem.

- `reports.py` serves `/manifest.json`, `/logo.png` and `/rules`, which are
  static / doc routes, not reports. Move them to a small `routes/static_pages.py`
  blueprint and register it in `app/__init__.py`.
- `lobby.py` has `/beer` and `/beer_qr` (tip links). Move to the same new
  blueprint or a `routes/tip.py`, next to `static/js/ui/tip.js`.

Check route names in templates and JS (`url_for`, hard-coded paths) before
moving. The URLs themselves must not change.

## 7. Docs and data

**Status: done** (the room QR ownership note moved to `lobby.js` for now, and
will follow the code when section 3 moves it). `data/decisions/` is tracked on
purpose (`Dev-Cheat-Sheet.md` says so), so the docs were corrected to match
rather than gitignoring it. The dead `data/drinks/` ignore line and the
non-existent `data/drinks/` folder entry are gone, and `data/profile_backups/`
is now documented. The notes below describe the original problem.

- `docs/DOM-Hooks.md`: fix the room QR ownership note (see section 3) and keep
  every module section in step with the moves above.
- `docs/Architecture.md` says `data/decisions/` and `data/drinks/` are
  gitignored, but `data/decisions/*` is tracked, and `.gitignore` says it is
  "no longer gitignored" and lists a `data/drinks/` folder that does not exist.
  Decide which is true: either gitignore the exports (real session data, not
  code) or keep tracking them, then make `Architecture.md` and `.gitignore`
  agree and remove the dead `data/drinks/` line.

## Suggested order

1. Section 1 (small, a real layering fix).
2. Section 7 docs and data (no code risk).
3. Section 6 routes (small, URLs unchanged).
4. Section 2 (`admin.js`), drink panels first.
5. Sections 3, 4, 5 (JS splits shared with FileSplitRefactor.md).

## Done when

- `grep -rn "from app.routes" app/services` is empty.
- No JS file owns functions unrelated to its name.
- `docs/Architecture.md` and `docs/DOM-Hooks.md` match the code.
- `pytest` is green and the game plays through lobby, a Normal round, a
  Drinking round and the BOJ switch vote.
