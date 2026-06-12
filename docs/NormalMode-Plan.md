# Normal Mode Rebuild Plan

Goal: make "🃏 Normal" a fully working, standalone blackjack mode with **zero drinking
references** — no sip ticker, drink panel, drink stats, milestone toasts, or
drinking trivia — while keeping the existing "🍺 Drinking" mode untouched.

Status: Normal mode currently shows a maintenance overlay on selection
("Continue Anyway" / "← Back to Drinking"). It stays gated behind that overlay
until Phase A is complete and verified.

---

## Phase A — Cleanup (make Normal mode usable as plain blackjack)

### A1. Setup screen (`static/js/ui/setup.js`, `templates/partials/index/_setup.html`)
- Keep `_showMaintenanceOverlay()` for `type === "normal"` until Phase A is
  fully done and tested — do **not** remove it yet.
- When `setGameType("normal")` is selected:
  - Hide/disable the **Easy Mode** toggle entirely (`#easy-mode-setup-toggle`,
    its label/pill). Easy Mode only makes sense in drinking mode (halves
    drinks per round) and should not appear as an option for Normal.
  - Confirm wager/"Sips per hand" stepper stays hidden (already handled via
    `wagerCell.style.display = "none"`).

### A2. Fix drink panel/stat leakage in Normal mode (bug fix)
Currently, even with `drinking_mode = false` (via "Continue Anyway"), drink UI
still renders. Gate the following on `state.drinking_mode === false`:

- **`templates/partials/index/_game.html`**
  - Header "🍺 Last round drinks" button (`#btn-last-round-header`)
  - `#sip-ticker`
  - "🍺 Drinks" tab (`#dig-drinks-tab`) and its panel
    (`#dig-drinks-panel`, `#dig-drinks-agg`, `#dig-drinks-detail`,
    `#dig-drinks-none`, `#dig-drinks-progress`, `#dig-drinks-waiting`)
  - "📊 Export Drinks CSV" button
  - Bottom-nav "Last Round" button (`#btn-last-round-nav`)

- **`templates/partials/index/_modals.html`**
  - "🍺 Last Round" modal
  - Milestone ack modal ("OK, I'll drink!")
  - "Hand out sips" milestone modal
  - "⬇️ Export Drinks CSV" button
  - Easy Mode kick-toggle label ("halve drinks every round") — hide alongside
    A1 since Easy Mode is unavailable in Normal mode

- **`static/js/ui/log.js`**
  - `updateSipTicker` — confirm it hides (`display:none`) rather than leaving
    an empty element, when `state.drinking_mode === false`
  - `showPlayerDrinkToast` — never call when `drinking_mode === false`
  - Mode badge — add a "🃏 Normal" badge variant (instead of "🍺 Drinking")
  - `processAceDrinkEvents` / ace-drink toast — skip entirely when
    `drinking_mode === false`

- **`static/js/ui/table.js`**
  - Drinks pane/card rendering (`.drinks-card`, `drinksPaneSelected`) — hide
    container entirely in Normal mode
  - Skip `processAceDrinkEvents(state)` call when `!state.drinking_mode`

- **`static/js/ui/kpi.js`**
  - Hide sip-related leaderboard columns/rows: `🍺` sip totals, "Avg🍺",
    "Peak🍺", sips/min stat, sip-based sort fallback
  - Leaderboard falls back to win/loss/push/streak-only view for Normal mode

- **`static/js/ui/trivia.js`**
  - Filter out all `cat: "drinking"` trivia entries and the "Drinking"
    category button/label/color when `drinking_mode === false`
  - (Optional) add a small set of general blackjack strategy/history facts to
    backfill the removed drinking entries so the trivia pool isn't thin in
    Normal mode

- **`static/js/ui/admin-settings.js` / `admin.js`**
  - Hide drink-related admin controls (drink CSV export, milestone settings,
    easy-mode description) when `drinking_mode === false`

### A3. Implementation approach
- Introduce one shared flag, e.g. `state.drinking_mode` → cached as
  `DRINKING_ENABLED` on game start / each poll — and use it consistently to
  toggle visibility of every block above, rather than scattering ad-hoc
  checks across files.
- Backend (`game_engine.py`, `drink_tracker.py`, `serializer.py`,
  `game_commands.py`) already gates most drink logic behind
  `session.drinking_mode`. Do a verification pass to confirm:
  - No drink/sip messages appear in the event log when `drinking_mode = False`
  - Serialized state omits or zeroes `sip_totals`, `last_round_sips`,
    `ace_drink_events`, `max_round_sips`, `round_sip_history`, etc.

### A4. Testing (Phase A)
- New test: full round with `drinking=False` → assert no drink/sip
  strings appear in `events`/log, serialized state has empty sip data, no
  milestone/ace-drink events fire.
- Manual UI pass: start a Normal game (via "Continue Anyway"), confirm no
  "🍺", "sip", or "drink" text appears anywhere during setup or gameplay.

### A5. Exit criteria for Phase A
- Normal mode plays a clean, standard blackjack round with no drinking UI,
  stats, or copy anywhere in active gameplay screens.
- Once verified, remove the maintenance overlay for `type === "normal"` (still
  keep it for `type === "referee"` unless/until that mode is also revisited).

---

## Phase B — Cash wager / bankroll system ("Bet $10")

Replace the sips-based wager with a cash-based betting system for Normal mode.

### B1. Design decisions (to confirm before building)
- Default bet amount (e.g. $10) — fixed or configurable per game in setup?
- Starting bankroll per player (e.g. $100, $500) — configurable?
- Min/max bet limits, bet-sizing UI (stepper similar to "Sips/hand")?
- Payout rules: blackjack 3:2 (or 6:5?), standard win 1:1, push returns bet,
  dealer-bust side bet (already exists for drinking — does it carry over?)
- What happens at $0 bankroll — re-buy, game over, or just block further
  betting?

### B2. Engine changes (`engine/blackjack.py`, `app/models/game_room.py`,
`app/services/game_engine.py`)
- Add per-player `bankroll`/`balance` field to player model
- Replace/extend `wager` concept with a cash bet amount per hand
- Add payout calculation pass at round resolution (win/loss/push/blackjack
  multiplier) updating each player's balance
- Persist balances across rounds within a session

### B3. Serializer / API (`app/services/serializer.py`,
`app/routes/game_commands.py`, `app/routes/lobby.py`)
- Include `balances`, `bets`, `round_payouts` (or similar) in serialized state
- Setup payload: accept `bet_amount` / `starting_bankroll` instead of/alongside
  `wager`

### B4. Frontend
- **Setup (`_setup.html`, `setup.js`)**: for Normal mode, show a "Bet / hand"
  stepper (e.g. default $10, step $5 or $10) where the "Sips/hand" stepper
  currently is; show "Starting bankroll" field if configurable
- **Table (`table.js`, `table-render.js`)**: show each player's current
  bankroll near their seat; show bet amount per hand
- **KPI / leaderboard (`kpi.js`)**: replace sip totals/Avg🍺/Peak🍺 with
  $ won/lost, current bankroll, biggest single-round win/loss
- **Log (`log.js`)**: round-end messages report $ won/lost instead of
  sips ("Player wins $15", "Push — bet returned", etc.)

### B5. Testing (Phase B)
- Unit tests for payout math (win, loss, push, blackjack 3:2, dealer bust)
- Integration test: multi-round session, verify bankroll updates correctly
  and never goes negative (per B1 ruleset)
- Manual UI pass: bet stepper, bankroll display, leaderboard $ columns

---

## Future / optional enhancements (post Phase B)

These are not required for a working Normal mode but are natural extensions
of this rebuild and worth tracking:

- **Side bets**: re-enable dealer-bust side bet (already exists for drinking
  mode) as a cash side bet in Normal mode
- **Bet history / session P&L**: per-player running profit/loss chart across
  the session (reuse `kpi.js` chart infrastructure used for sip history)
- **Configurable table rules**: dealer hits/stands on soft 17, double-after-
  split, surrender, blackjack payout ratio (3:2 vs 6:5) — exposed in setup
  for Normal mode
- **Re-buy / bankruptcy flow**: UI prompt to add chips when a player hits $0
- **Normal-mode trivia set**: dedicated strategy/odds trivia pool (no
  drinking-flavored facts) once the drinking trivia is filtered out in A2
- **Referee mode parity**: once Normal mode is stable, consider whether
  Referee mode (also under maintenance) should get a similar non-drinking
  pass
- **Rename/copy pass**: revisit whether Normal mode needs its own subtitle,
  mode badge color, or icon distinct from "🃏" once the bet system is in place
