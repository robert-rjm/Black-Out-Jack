# Black-Out-Jack — Open Issues (17 June 2026)
_17 June 2026 · Busfahrer feature excluded_

Builds on `Audit16June.md`. Items marked ~~strikethrough~~ were resolved before this session.
Carries forward all still-open L-items from 16 June and adds new N-items found in this pass.

---

## Carried-Forward Issues (still open from 16 June)

### ~~L1 · Bottom nav labels always hidden (accessibility)~~
Already implicitly done on browser when howevering
**File:** `static/css/main.css` (line 222)
`.bnav-label { display: none }` applies on all breakpoints. Add visible labels at ≥640px or `title` attributes at minimum.

### ~~L2 · Card overflow on long hands — lower risk than originally rated~~
**File:** `static/css/components/table.css` (lines 35, 50)
`.cards-row` has `flex-wrap: nowrap` and no explicit `overflow-x`. The *parent* `.hand-block` already has `overflow-x: auto` (line 35), so cards do scroll in practice. Original bug was correct but severity is lower — the overflow is handled one level up. Still worth adding `overflow-x: auto` directly on `.cards-row` for explicit intent.

### ~~L3 · Done-seat dimming too aggressive~~
consider to ignore, dimming seems fine as of rn
**File:** `static/css/components/table.css` (line 15)
`.seat.done { opacity: .55 }` — still `.55`. Reduce to `.80` or switch to an active-seat accent.
Note: `.hand-block.done { opacity: .65; }` (line 43) is also present and was added since the June 16 audit. Same concern applies there.

### L4 · Sip ticker clips on 4+ players
**File:** `static/css/components/kpi.css`, `static/js/ui/log.js`
Header strip renders per-player sip counts inline. No overflow guard on the ticker row for 5+ players on narrow screens.

### L5 · No loading / reconnection state in UI
**File:** `static/js/state.js`, `static/js/app.js`
No visual feedback when `/state` poll is slow or fails — `_requestsInFlight` tracks in-flight requests but nothing renders a spinner or top-bar indicator. Add a pulsing indicator on in-flight fetches.

### ~~L6 · Magic number in admin nav icon offset~~
**File:** `static/css/main.css` (line 221)
`#btn-admin-nav .bnav-icon { transform: translateY(12px); }` — add a comment explaining why the offset exists.

### L7 · Action buttons matched by `textContent` — fragile
**File:** `static/js/ui/table.js`, `static/js/ui/admin.js`
`updateActionButtons`, `updateBestPlay`, `updateRoleUI`, and `updateHonorPrompt` all match buttons by checking `b.textContent.trim() === "SPLIT"` / `"HIT"` / etc. A copy-change would silently break logic. Use `data-action-code` attributes instead.

### ~~L8 · Toast boilerplate duplicated across admin.js~~
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

## Checklist

### Carried forward from 16 June
- [X] L1 — Bottom nav labels on desktop / `title` attributes
- [X] L2 — `overflow-x: auto` on `.cards-row` (lower risk; parent handles it)
- [X] L3 — Soften `.seat.done` opacity to `.80`; also `.hand-block.done`
- [ ] L4 — Fix sip ticker clip on 4+ players
- [ ] L5 — Add loading / reconnection indicator
- [X] L6 — Comment magic `translateY(12px)` offset
- [ ] L7 — Switch action-button matching to `data-action-code`
- [X] L8 — Extract `_firePlayerToast()` helper in admin.js
- [x] L9 — `log.js` substring classification — RESOLVED (appendLog is a stub)
- [ ] L14 — Replace inline CSS strings in JS with toggled classes
- [ ] L15 — Pick one event-wiring style in admin.js
- [ ] L16 — Consolidate script CLI utilities into `scripts/_cli.py`
