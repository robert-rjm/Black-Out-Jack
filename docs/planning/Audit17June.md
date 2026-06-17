# Black-Out-Jack — Open Issues (17 June 2026)
_17 June 2026 · Busfahrer feature excluded_

Builds on `Audit16June.md`. Items marked ~~strikethrough~~ were resolved before this session.
Carries forward all still-open L-items from 16 June and adds new N-items found in this pass.

---

## Carried-Forward Issues (still open from 16 June)

### L1 · Bottom nav labels always hidden (accessibility)
**File:** `static/css/main.css` (line 222)
`.bnav-label { display: none }` applies on all breakpoints. Add visible labels at ≥640px or `title` attributes at minimum.

### L2 · Card overflow on long hands — lower risk than originally rated
**File:** `static/css/components/table.css` (lines 35, 50)
`.cards-row` has `flex-wrap: nowrap` and no explicit `overflow-x`. The *parent* `.hand-block` already has `overflow-x: auto` (line 35), so cards do scroll in practice. Original bug was correct but severity is lower — the overflow is handled one level up. Still worth adding `overflow-x: auto` directly on `.cards-row` for explicit intent.

### L3 · Done-seat dimming too aggressive
**File:** `static/css/components/table.css` (line 15)
`.seat.done { opacity: .55 }` — still `.55`. Reduce to `.80` or switch to an active-seat accent.
Note: `.hand-block.done { opacity: .65; }` (line 43) is also present and was added since the June 16 audit. Same concern applies there.

### L4 · Sip ticker clips on 4+ players
**File:** `static/css/components/kpi.css`, `static/js/ui/log.js`
Header strip renders per-player sip counts inline. No overflow guard on the ticker row for 5+ players on narrow screens.

### L5 · No loading / reconnection state in UI
**File:** `static/js/state.js`, `static/js/app.js`
No visual feedback when `/state` poll is slow or fails — `_requestsInFlight` tracks in-flight requests but nothing renders a spinner or top-bar indicator. Add a pulsing indicator on in-flight fetches.

### L6 · Magic number in admin nav icon offset
**File:** `static/css/main.css` (line 221)
`#btn-admin-nav .bnav-icon { transform: translateY(12px); }` — add a comment explaining why the offset exists.

### L7 · Action buttons matched by `textContent` — fragile
**File:** `static/js/ui/table.js`, `static/js/ui/admin.js`
`updateActionButtons`, `updateBestPlay`, `updateRoleUI`, and `updateHonorPrompt` all match buttons by checking `b.textContent.trim() === "SPLIT"` / `"HIT"` / etc. A copy-change would silently break logic. Use `data-action-code` attributes instead.

### L8 · Toast boilerplate duplicated across admin.js
**File:** `static/js/ui/admin.js`
`showBustVoteToast`, `showBustHandoutToast`, and `showInsuranceToast` each repeat the same 5-line pattern:
```js
const toast = document.getElementById("player-toast");
if (!toast) return;
// ... build parts ...
toast.className = (iDrink ? "drink" : "clean") + " show";
void toast.offsetWidth;
toast.classList.add("show");
setTimeout(() => toast.classList.remove("show"), N);
```
Extract `_firePlayerToast(html, iDrink, ms)` helper.

### ~~L9 · `log.js` classifies log lines by substring match on display text~~ — RESOLVED
`appendLog` is now a no-op stub (`function appendLog() {}`). Log classification was removed when the module was refactored to structured events. No action needed.

### L14 · Inline CSS strings in JS
**File:** `static/js/ui/admin.js`, `static/js/ui/table.js`, `static/js/ui/log.js`
Extensive use of `element.style.cssText = "..."` and template-literal inline styles throughout dynamically constructed markup (`_renderBustVoteCards`, `_renderBustGivePanel`, `showLocalSeatPicker`, `renderDrinksDetail`, `updateRoundPane`, `showPeekedCard`, and more). These were already flagged in June; the pattern has spread further as new features were added. Convert hot-path elements to toggled CSS classes.

### L15 · Mixed event-wiring style in admin.js
**File:** `static/js/ui/admin.js`
`el.onclick = () => ...` and `addEventListener("click", ...)` still mixed. E.g. `bustBtn.onclick`, `passBtn.onclick`, `btn.onclick` set directly while `requestLocalSeat` wires via `addEventListener`. Pick one convention.

### L16 · Script CLI utilities duplicated
**File:** `scripts/play_terminal.py`, `scripts/play_referee.py`, `scripts/simulation.py`
`play_terminal.py` has `_safe_int()` and `_yes_no()` helpers; `play_referee.py` has its own integer-prompt loop. Consolidate into `scripts/_cli.py`.

---

## New Issues (found 17 June)

### ~~N1 · Architecture.md references a non-existent `Test-Plan.md`~~
**File:** `docs/Architecture.md` (Development Guide → Running locally section)
The closing line `See [docs/planning/Test-Plan.md](planning/Test-Plan.md) for coverage details.` points to a file that does not exist in the repository. Either create it or remove the reference.

### ~~N2 · `run_all_configs.py` and `compare_configs.py` missing from Architecture.md~~
**File:** `docs/Architecture.md` (Project Structure tree and File Dependencies table)
Two scripts exist on disk (`scripts/run_all_configs.py`, `scripts/compare_configs.py`) but are absent from the documented project structure and file-deps table. Add entries with their purpose.

### ~~N3 · `engine/events.py` absent from Architecture.md file-deps table~~
**File:** `docs/Architecture.md`
`engine/events.py` is listed in the project-structure tree (implicitly, the tree lists the engine directory) but is **not** in the File Dependencies table. It is now a first-class dependency of both `engine/drinking_rules.py` (via `DrinkingRules.handle(event)`) and `app/services/game_engine.py`. Add a row:

| `engine/events.py` | nothing | Typed dataclass events dispatched to `DrinkingRules.handle()` |

### ~~N4 · `app/services/tick.py` and `app/services/validators.py` absent from file-deps table~~
**File:** `docs/Architecture.md`
Both files are described in the project-structure comment block but have no rows in the File Dependencies table. `tick.py` is a per-poll side-effect driver imported by `polling.py`; `validators.py` provides `sanitize_name` and `get_client_info` used across multiple routes and the serializer.

### N5 · DOM-Hooks.md severely out of date — 20+ new element IDs undocumented
**File:** `docs/DOM-Hooks.md`
Large batches of DOM elements added since the doc was last updated have no module-ownership entry. Partial list by owner:

**admin.js (bust vote)**
`#bust-vote-modal-overlay`, `#bust-vote-timer-bar`, `#bust-vote-timer-label`, `#bust-vote-players-wrap`, `#bust-vote-modal-tally`, `#bust-vote-status`, `#bust-vote-status-round`, `#bust-vote-toggle-modal`, `#bust-give-overlay`, `#bust-give-body`

**admin.js (honor / suggest / local seat)**
`#honor-split-overlay`, `#honor-no-btn`, `#suggest-picker`, `#suggest-banner`, `#suggest-text`, `#suggest-toggle-row`, `#local-seat-switcher`, `#local-seat-active`, `#local-seat-picker`, `#add-local-seat-row`

**admin.js (registration)**
`#register-pending`, `#register-denied`, `#pending-reg-banner`

**table.js (pre-deal / rounds / misc)**
`#dig-predeal-panel`, `#dig-play-content`, `#dig-round-notices`, `#dig-drinks-progress`, `#bank-run-overlay`, `#bank-run-player-name`, `#peeked-card-wrap`, `#peeked-card-display`, `#btn-peek`

**admin-settings.js** (see N6)

**Fix:** Add module-ownership sections for each of these groups and for `admin-settings.js`.

### N6 · `admin-settings.js` has no DOM-Hooks.md ownership entry
**File:** `docs/DOM-Hooks.md`
`static/js/ui/admin-settings.js` exists and manages the settings panel (wager/hands/decks inputs, easy-mode toggle, bust-vote toggle, strategy-hint toggle, god-mode toggle, etc.) but has **zero** coverage in DOM-Hooks.md. The module and its owned element IDs (`#setting-wager`, `#setting-num-hands`, `#setting-num-decks`, `#bust-vote-toggle-modal`, `#god-mode-toggle-modal`, etc.) should be added to the module-ownership section.

### N7 · Stale section-header comment in `drinking_rules.py`
**File:** `engine/drinking_rules.py` (between `_bj_multiplier` and `DrinkingRules` class)
```python
# =============================================================================
# Rule classifier — canonical name for a raw drink-reason string.
# Used by drink_tracker.py (CSV export) and simulation.py.
# =============================================================================
```
`classify_rule` was moved to `app/services/utils.py` (refactor 4.2) but this section header was left behind, implying the classifier still lives here. Remove or replace with a redirect comment: `# classify_rule() lives in app/services/utils.py`.

### N8 · `drink_tracker.py` `_record_drinks_detail` uses fragile substring matching
**File:** `app/services/drink_tracker.py` → `_record_drinks_detail()` (~line 195)
Like the old L9 pattern (now resolved in the JS log), the Python side still detects special-case drink entries by checking raw reason strings:
```python
if "bust vote correct" in reason: ...
if "A♣ protection credit" in reason or ("A♣" in reason and "credit" in reason): ...
if "Sweep cancels doubled-hand drink" in reason: ...
if "4-player halving" in reason or "Easy mode halving" in reason: ...
if "Hard Switch triggered" in reason: ...
```
If any reason string changes in `drinking_rules.py`, the Drinks-pane display silently breaks.
**Fix:** Use `classify_rule()` for all entries (extend it to cover these cases), or add a `role` / `category` field to drink-log entries so downstream code doesn't inspect free-text strings.

---

## Checklist

### Carried forward from 16 June
- [ ] L1 — Bottom nav labels on desktop / `title` attributes
- [ ] L2 — `overflow-x: auto` on `.cards-row` (lower risk; parent handles it)
- [ ] L3 — Soften `.seat.done` opacity to `.80`; also `.hand-block.done`
- [ ] L4 — Fix sip ticker clip on 4+ players
- [ ] L5 — Add loading / reconnection indicator
- [ ] L6 — Comment magic `translateY(12px)` offset
- [ ] L7 — Switch action-button matching to `data-action-code`
- [ ] L8 — Extract `_firePlayerToast()` helper in admin.js
- [x] L9 — `log.js` substring classification — RESOLVED (appendLog is a stub)
- [ ] L14 — Replace inline CSS strings in JS with toggled classes
- [ ] L15 — Pick one event-wiring style in admin.js
- [ ] L16 — Consolidate script CLI utilities into `scripts/_cli.py`

### New (17 June)
- [x] N1 — Remove or create `docs/planning/Test-Plan.md` (broken link in Architecture.md)
- [x] N2 — Document `run_all_configs.py` and `compare_configs.py` in Architecture.md
- [x] N3 — Add `engine/events.py` row to Architecture.md file-deps table
- [x] N4 — Add `tick.py` and `validators.py` rows to Architecture.md file-deps table
- [ ] N5 — Update DOM-Hooks.md with 20+ undocumented element IDs
- [ ] N6 — Add `admin-settings.js` ownership section to DOM-Hooks.md
- [ ] N7 — Remove stale `# Rule classifier` section header from `drinking_rules.py`
- [ ] N8 — Replace substring matching in `_record_drinks_detail` with `classify_rule` or typed log entries
