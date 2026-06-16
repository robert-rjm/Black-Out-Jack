# Black-Out-Jack — Open Issues (16 June 2026)
_16 June 2026 · Busfahrer feature excluded_

Merged from `AUDIT.md` (root, worked through in session) and `docs/AUDIT.md` (broader second-pass audit).
Busfahrer feature excluded throughout. Items already fixed in the session are omitted.

---

## Critical — Fix before next session

These either break functionality, silently corrupt data, or are security risks.

### C1 · Error response shape inconsistency
**File:** `app/routes/lobby.py` `/setup`
`/setup` returns `{"ok": false, "output": "..."}` while every other route uses `{"ok": false, "error": "..."}`. Frontend handlers check both keys inconsistently — likely cause of stuck-UI bugs when setup fails.
**Fix:** Change `/setup` error responses to use `"error"` key consistently.

### C2 · Player name sanitization not applied consistently
**File:** `app/routes/admin.py` (kick L44, make_bot L110, make_human L158, transfer_admin L223, vote_kick L349), `app/routes/polling.py` (`/vote_insurance` L536)
`sanitize_name()` in `validators.py` strips HTML/bidi/length — but these routes use raw `.strip().capitalize()`. A malformed player name can pass through unsanitized.
**Fix:** Replace all raw `.strip().capitalize()` on player-supplied names with `sanitize_name()`.

### C3 · No length limit on raw `/command` string
**File:** `app/routes/game_commands.py` L720-781
Every other input uses a `raw[:40]` guard, but the command route splits the full raw string with no cap. Long inputs can reach downstream parsers.
**Fix:** Add `raw = raw[:120]` (or similar) before `.split()`.

### ~~C4 · `decision_log.py` — `room_code` is always empty~~ — FIXED
`GameRoom` has `room_code: str = ""` set at construction (`lobby.py` L171). `decision_log.py` reads `session.room_code` directly from the `GameRoom` object. Session IDs are populated correctly.

### C5 · XSS: only one call site uses DOMPurify
**File:** `static/js/ui/admin.js` `openRulesModal` (L433-437)
Only this one function runs `DOMPurify.sanitize`. All other rendering relies solely on manual `escapeHtml()`. One missed call on any future user-controlled field is an XSS vector.
**Fix:** Audit all innerHTML-write sites; apply DOMPurify at render boundaries, not just one call site.

### ~~C6 · `startGame` has no `.catch` — Start button permanently disabled on network error~~ — FIXED
Wrapped fetch+json in try/catch in `startGame` (setup.js). Also added catches to `sendCmd`, `honorResolve`, `bankRebuy` (table.js) and `createRoom`/`joinRoom` (lobby.js) which had the same uncaught-rejection pattern.

---

## High — Fix soon (correctness bugs with real game impact)

### H1 · `rotate_dealer` crashes on missing dealer name
**File:** `app/services/room_manager.py` `rotate_dealer` (L195-203)
`all_names.index(session.dealer_name)` raises unhandled `ValueError` if the dealer was removed via `apply_queued_settings` between rounds. Already partially guarded in the code (try/except path) but the except sets `cur_idx = -1` which silently wraps to the last player — it should log a warning at minimum.
**Fix:** Confirm the try/except path is correct; add a warning log on the fallback.

### H2 · Late-joining players have deflated milestone averages
**File:** `app/services/drink_tracker.py` `_apply_worst_player_streak` (L399-450)
Uses `len(session._round_sip_history)` as every player's round count. Players who joined mid-session have their sip average divided by total rounds, not rounds they were present — making them artificially "worst player" candidates.
**Fix:** Use `session._player_rounds_played[name]` as the divisor, defaulting to total rounds if missing.

### H3 · Milestone handout hardcodes MILESTONE_STEP coupling
**File:** `app/services/drink_tracker.py` `check_and_set_milestone` (L453-519)
`handout_sips = 4 + boundary // MILESTONE_STEP` bakes an implicit relationship to `MILESTONE_STEP=50` — changing the constant breaks the formula silently.
**Fix:** Document the coupling with a comment, or derive the `+4` from config explicitly.

### H4 · Negative `dealer_idx` wraps silently in `/setup`
**File:** `app/routes/lobby.py` `/setup` L150
`dealer_idx >= 0` is not validated. A negative value wraps via Python negative indexing and silently picks the wrong dealer instead of returning an error.
**Fix:** Add `if not (0 <= dealer_idx < len(names)):` guard (already partially present — verify it covers negative values).

### H5 · `renderLeaderboard` in kpi.js is fully implemented but never called
**File:** `static/js/ui/kpi.js` `renderLeaderboard()` (L110-196), `wrClass()` (L6-11)
Both functions are implemented but `updateKpiPanel` never calls them. Either this is dead code (remove it and the `.lb-*` CSS) or a leaderboard feature was disconnected and needs rewiring.
**Fix:** Decide: restore the leaderboard feature or delete the dead code and CSS.

### H6 · `app.js` reconnect IIFE silently swallows all errors
**File:** `static/js/app.js` reconnect IIFE (L38-62)
Outer `catch (_) {}` catches everything silently. On failure the user is left on the lobby with no message and no recovery.
**Fix:** Show a user-visible "Connection lost — refresh to reconnect" message on catch.

---

## Medium — Refactor / maintainability

### M1 · `harvest_drink_log` is 225 lines handling 8 responsibilities
**File:** `app/services/drink_tracker.py` (L159-384)
Single function does: milestone check, streak tracking, sip ticker update, CSV row building, prev-round snapshot, worst-player logic, round-over seq bump, handout log. Untestable as a unit.
**Fix:** Extract into named private helpers (`_record_sip_csv`, `_update_streaks`, `_snapshot_round`, etc.).

### M2 · Admin-check boilerplate repeated across ~12 routes
**File:** `app/routes/admin.py`
Every route replicates the same 3-line admin check with inconsistent error text ("Not authorised." vs "Admin only." vs "Admin only").
**Fix:** Extract `require_admin(session, client_id) -> tuple[bool, Response]` helper or a `@admin_only` decorator.

### M3 · `/state` route tick logic is 60 lines inline in the route
**File:** `app/routes/polling.py` `/state` (L88-145)
Sequential side-effectful ticks (insurance auto-resolve, bust-vote pause, milestone pause, handout forfeit) are embedded directly in the route function.
**Fix:** Extract `tick(session)` service function for testability and separation.

### M4 · `applyState` in table.js is ~240 lines handling 6 concerns
**File:** `static/js/ui/table.js` `applyState` (L335-575)
Handles identity sync, toasts, log sync, tab switching, modal sync, and animation dispatch in one function.
**Fix:** Split into named phase functions (`_syncIdentity`, `_syncLog`, `_syncModals`, etc.).

### M5 · Phase and role strings are raw literals scattered across JS
**File:** `static/js/ui/table.js`, `admin.js`, `lobby.js`
Phase strings (`"pre-deal"`, `"playing"`, `"round-over"`, `"dealer-ready"`) and role strings (`"admin"`, `"player"`, `"spectator"`, `"kicked"`) repeated as raw literals. A typo causes a silent mismatch.
**Fix:** Centralize in a shared `constants.js` or object at the top of `app.js`.

### M6 · Double iteration over `drink_log` in serializer
**File:** `app/services/serializer.py`
`compute_sip_totals()` and `compute_dealer_role_sips()` are called in the same `serialize_state()` pass but each iterate the full drink log separately.
**Fix:** Single pass accumulating both totals.

### M7 · `_bj_multiplier` conditions computed twice
**File:** `engine/drinking_rules.py`
Suited/A+J/both-black multiplier conditions exist in `_bj_multiplier()` (L17-26) and are recomputed inline in `on_blackjack()` (~L202-209).
**Fix:** Remove the inline recomputation; use `_bj_multiplier()` as the single source.

### M8 · `on_round_end` is a 110-line function with 5 distinct computations
**File:** `engine/drinking_rules.py` (L405-514)
**Fix:** Extract into named helpers (`_net_loss_drinks`, `_double_loss_drinks`, etc.).

### M9 · `referee.py` cmd_result BJ insurance inconsistency
**File:** `engine/referee.py` `cmd_result` (L369-372)
The BJ-insurance bonus event fires immediately into `_pending_eor_msgs` without passing `hard_switch_dealer`, unlike the equivalent path in `blackjack.py` (L696). The dealer-switch exemption can be missed for this bonus.
**Fix:** Pass `hard_switch_dealer` consistently on this event path.

### M10 · Polling/fetch pattern duplicated across three JS files
**File:** `static/js/ui/lobby.js` `startPolling`, `static/js/ui/setup.js` `startWaiting`, `visibilitychange` handler
All reimplement the same fetch-`/state`-then-`applyState` loop.
**Fix:** Share a `pollState(interval, onResult)` helper.

---

## Low — Polish and minor cleanup

### L1 · Bottom nav labels always hidden (accessibility)
**File:** `static/css/main.css`
`.bnav-label { display: none }` on all breakpoints. Add visible labels at ≥640px or `title` attributes at minimum.

### L2 · Card overflow on long hands
**File:** `static/css/components/table.css`
`.cards-row` has no `overflow-x` — 5+ card hands overflow without scrollbar. Add `overflow-x: auto` or `flex-wrap: wrap`.

### L3 · Done-seat dimming too aggressive
**File:** `static/css/components/table.css`
`.seat.done { opacity: .55 }` makes 3+ player tables hard to read. Reduce to `.80` or use active-seat accent instead.

### L4 · Sip ticker clips on 4+ players
**File:** `static/css/components/kpi.css`
Header has fixed height; rightmost players' sip counts are clipped on mobile with 4+ players.
**Fix:** Move ticker to collapsible panel or add visible scroll indicators.

### L5 · No loading / reconnection state in UI
**File:** `static/js/state.js`, `static/js/app.js`
No visual feedback when `/state` poll is slow or fails. Add a pulsing top bar on in-flight fetches.

### L6 · Magic number in admin nav icon offset
**File:** `static/css/main.css`
`#btn-admin-nav .bnav-icon { transform: translateY(12px); }` — no comment explaining the offset.

### L7 · Action buttons matched by `textContent` — fragile
**File:** `static/js/ui/table.js`, `static/js/ui/admin.js`
`updateActionButtons`/`updateHonorPrompt` match buttons by `textContent` ("SPLIT", "DOUBLE", ...). Use `data-action-code` attributes instead.

### L8 · Toast boilerplate duplicated across admin.js
**File:** `static/js/ui/admin.js`
`showBustVoteToast`, `showBustHandoutToast`, `showInsuranceToast` share ~80% identical display boilerplate.
**Fix:** Extract `_fireToast(opts)` helper.

### L9 · `log.js` classifies log lines by substring match on display text
**File:** `static/js/log.js` `appendLog` (L52-71)
Checks `includes("drink")`, `"win"`, `"bust"` etc. on displayed strings — a player named "win" would mis-tag entries.
**Fix:** Use structured log-entry types from server.

### L10 · `Hand.split()` shoe parameter is unused
**File:** `engine/blackjack.py` `Hand.split()` (L203-214)
`shoe` parameter is accepted but never used — docstring implies dealing should happen here.
**Fix:** Either use the parameter (deal second card here) or remove it and update callers.

### L11 · `Player.net_losses()` bakes a drinking rule into the engine
**File:** `engine/blackjack.py` (L257-261)
Hardcodes "blackjack = 2 wins" — a drinking-game house rule in a supposedly standalone class.
**Fix:** Move to `drinking_rules.py` or accept a multiplier argument.

### L12 · `state.js` `currentTurn` appears unused
**File:** `static/js/state.js` (L21)
Mirrors `lastState.current_turn` but is not referenced elsewhere.
**Fix:** Remove if unused.

### L13 · `admin.py` imports `sanitize_name` inside function bodies
**File:** `app/routes/admin.py` (`request_rejoin`, `update_settings`, `take_back_seat`)
Import should be at module level, not repeated inside three functions.

### L14 · Inline CSS strings in JS
**File:** `static/js/ui/table.js`, `static/js/app.js`
`element.style.cssText = "font-size:11px; color:..."` — visual changes require JS edits and break theming. Convert to toggled CSS classes.

### L15 · Mixed event-wiring style in admin.js
`el.onclick = () => ...` and `addEventListener` mixed throughout. Pick one convention.

### L16 · Script utilities duplicated across CLI scripts
**File:** `scripts/play_terminal.py`, `scripts/play_referee.py`, `scripts/simulation.py`
All duplicate: `sys.path` bootstrap, `raw.capitalize()` normalization, and "prompt for int with default/bounds" helpers.
**Fix:** Consolidate into `scripts/_cli.py`.

### L17 · Minor script bugs
- `load_decision_logs.py` L58: `r["player"]` raises `KeyError` (use `.get()`)
- `load_decision_logs.py` L120: `os.makedirs` crashes if output has no directory component
- `rules_sync.py` L39: no try/except around `json.load`
- `play_referee.py` L55: redundant `.strip()` on already-stripped variable
- `play_terminal.py` L71: `num_npcs += 1` for synthetic House NPC is never read

---

## Checklists

### Critical
- [ ] C1 — Error response shape: `/setup` → use `"error"` key
- [ ] C2 — Sanitize player names in admin.py and polling.py
- [ ] C3 — Add command string length cap before `.split()`
- [x] C4 — Fix `decision_log.py` `room_code` always empty — DONE
- [ ] C5 — Audit XSS: apply DOMPurify at all innerHTML render boundaries
- [x] C6 — Add `.catch` to `startGame` fetch; re-enable button on failure — DONE

### High
- [ ] H1 — `rotate_dealer` ValueError guard / warn on fallback
- [ ] H2 — Use `_player_rounds_played` for milestone average denominator
- [ ] H3 — Document or fix `MILESTONE_STEP` coupling in `check_and_set_milestone`
- [ ] H4 — Validate `dealer_idx >= 0` in `/setup`
- [ ] H5 — Decide: restore `renderLeaderboard` or delete dead code + CSS
- [ ] H6 — Show user-visible error in `app.js` reconnect catch

### Medium
- [ ] M1 — Split `harvest_drink_log` into named helpers
- [ ] M2 — Extract `require_admin` helper / decorator in admin.py
- [ ] M3 — Extract `tick(session)` from `/state` route
- [ ] M4 — Split `applyState` into named phase functions
- [ ] M5 — Centralize phase/role string constants in JS
- [ ] M6 — Single-pass sip total accumulation in serializer
- [ ] M7 — Remove inline `_bj_multiplier` recomputation in `on_blackjack`
- [ ] M8 — Split `on_round_end` into named helpers
- [ ] M9 — Pass `hard_switch_dealer` in `cmd_result` BJ insurance path
- [ ] M10 — Share `pollState` helper across lobby/setup/visibility JS

### Low
- [ ] L1 — Bottom nav labels on desktop / `title` attributes
- [ ] L2 — `overflow-x: auto` on `.cards-row`
- [ ] L3 — Soften `.seat.done` opacity to `.80`
- [ ] L4 — Fix sip ticker clip on 4+ players
- [ ] L5 — Add loading / reconnection indicator
- [ ] L6 — Comment magic `translateY(12px)` offset
- [ ] L7 — Switch action-button matching to `data-action-code`
- [ ] L8 — Extract `_fireToast()` in admin.js
- [ ] L9 — Use structured log-entry types instead of substring matching
- [ ] L10 — Clarify / fix `Hand.split()` unused shoe param
- [ ] L11 — Move `Player.net_losses()` drinking rule out of engine
- [ ] L12 — Remove `state.js` `currentTurn` if unused
- [ ] L13 — Move `sanitize_name` imports to admin.py module level
- [ ] L14 — Replace inline CSS strings in JS with toggled classes
- [ ] L15 — Pick one event-wiring style in admin.js
- [ ] L16 — Consolidate script CLI utilities into `scripts/_cli.py`
- [ ] L17 — Fix minor script bugs (load_decision_logs, rules_sync, play_referee, play_terminal)
