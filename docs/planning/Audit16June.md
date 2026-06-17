# Black-Out-Jack — Open Issues (16 June 2026)
_16 June 2026 · Busfahrer feature excluded_

Merged from `AUDIT.md` (root, worked through in session) and `docs/AUDIT.md` (broader second-pass audit).
Busfahrer feature excluded throughout. Items already fixed in the session are omitted.

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

### ~~L10 · `Hand.split()` shoe parameter is unused~~
**File:** `engine/blackjack.py` `Hand.split()` (L203-214)
`shoe` parameter is accepted but never used — docstring implies dealing should happen here.
**Fix:** Either use the parameter (deal second card here) or remove it and update callers.

### ~~L11 · `Player.net_losses()` bakes a drinking rule into the engine~~
**File:** `engine/blackjack.py` (L257-261)
Hardcodes "blackjack = 2 wins" — a drinking-game house rule in a supposedly standalone class.
**Fix:** Move to `drinking_rules.py` or accept a multiplier argument.

### ~~L12 · `state.js` `currentTurn` appears unused~~ False Positive
**File:** `static/js/state.js` (L21)
Mirrors `lastState.current_turn` but is not referenced elsewhere.
**Fix:** Remove if unused.

### ~~L13 · `admin.py` imports `sanitize_name` inside function bodies~~
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

### ~~L17 · Minor script bugs~~
- `load_decision_logs.py` L58: `r["player"]` raises `KeyError` (use `.get()`)
- `load_decision_logs.py` L120: `os.makedirs` crashes if output has no directory component
- `rules_sync.py` L39: no try/except around `json.load`
- `play_referee.py` L55: redundant `.strip()` on already-stripped variable
- `play_terminal.py` L71: `num_npcs += 1` for synthetic House NPC is never read

---

## Checklists

### Critical - DONE

### High - DONE

### Medium - DONE

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
- [X] L10 — Clarify / fix `Hand.split()` unused shoe param
- [X] L11 — Move `Player.net_losses()` drinking rule out of engine
- [X] L12 — Remove `state.js` `currentTurn` if unused
- [X] L13 — Move `sanitize_name` imports to admin.py module level
- [ ] L14 — Replace inline CSS strings in JS with toggled classes
- [ ] L15 — Pick one event-wiring style in admin.js
- [ ] L16 — Consolidate script CLI utilities into `scripts/_cli.py`
- [X] L17 — Fix minor script bugs (load_decision_logs, rules_sync, play_referee, play_terminal)
