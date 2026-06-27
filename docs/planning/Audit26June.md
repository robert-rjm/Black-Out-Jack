# Codebase Audit — 26 June 2026

> Scope: all code except `engine/busfahrer.py` (not yet implemented).
> Busfahrer stubs are acknowledged and intentionally excluded.

---

## Severity Legend

| Level | Meaning |
|---|---|
| 🔴 CRITICAL | Incorrect game behaviour — wrong drinks fired, double-counted, or skipped |
| 🟠 HIGH | Silent failures, maintenance hazards, or memory/state growth bugs |
| 🟡 MEDIUM | Code smell, inconsistent patterns, minor correctness edge-cases |
| 🟢 LOW | Cleanup, style, and quality-of-life improvements |

---

## 🔴 CRITICAL

### ~~C-1~~ → L-8 · `_cmd_blackjack` registered in `DIGITAL_COMMANDS` — dead code, not an active bug
**File:** `app/routes/game_commands.py` — `_cmd_blackjack` (line 577); `DIGITAL_COMMANDS` (line 690)
**Reclassified from CRITICAL after review.**
**Problem:**
`_cmd_blackjack` is listed in `DIGITAL_COMMANDS` and appears in the digital `help` output, implying it is a valid digital command. In reality there is no frontend UI path to send it in digital mode — `sendCmd()` is only called from HIT/STAND/DOUBLE/SPLIT/DEAL/DEALER buttons and `doNewRound()`. God mode grants `is_dealer_client = true` but exposes no text command input. The handler can only be triggered via browser console or a direct HTTP POST with a known `client_id`. If triggered that way, it would double-fire BJ drinks (once immediately via `tracker.apply()`, bypassing the EOR buffer; once again when `dealer_turn()` runs the EOR flush) and bypass 4-player halving. But this is not reachable in normal gameplay.
**Fix:** Remove `"blackjack"` from `DIGITAL_COMMANDS` and from the digital help text. It is only meaningful in referee mode, where natural BJs must be manually declared.

---

### C-2 · `is_soft_hand()` returns wrong result for hands with 2+ aces
**File:** `engine/strategy.py` — `is_soft_hand()` (line 60)
**Problem:**
```python
total = sum(c.rank.blackjack_value for c in hand.cards)   # aces always = 11
aces  = sum(1 for c in hand.cards if c.rank.blackjack_value == 11)
return aces > 0 and total <= 21
```
For A, A: `total = 22`, `aces = 2`, `22 > 21` → returns **False**.
But `Hand.score()` = 12 (one ace soft), which IS a soft hand. Any multi-ace hand where the raw ace-as-11 sum exceeds 21 is misclassified as hard, causing wrong basic-strategy advice. Relevant when max splits are reached and a player holds multiple aces.
**Fix:**
```python
def is_soft_hand(hand) -> bool:
    has_ace = any(c.rank.blackjack_value == 11 for c in hand.cards)
    if not has_ace:
        return False
    # Score with all aces as 1
    hard_total = sum(
        1 if c.rank.blackjack_value == 11 else c.rank.blackjack_value
        for c in hand.cards
    )
    return hand.score() > hard_total   # ace(s) counting as 11 → score > hard_total
```

---

## 🟠 HIGH

### H-1 · Dead field `ace_clubs_flag["protected"]`
**File:** `engine/referee.py` line 117, `engine/blackjack.py` line 363, `app/models/game_room.py` via `session._ace_clubs_flag`
**Problem:** The dict is always initialized with a `"protected": False` key, but no code ever sets or reads this key. Only `"partial_protected"`, `"half_protected"`, and `"dealer_player_pending_credit"` are used. The dead key is misleading — it looks like it should be meaningful but silently does nothing.
**Fix:** Remove `"protected"` from all initializations of `_ace_clubs_flag`. Add a comment listing the active keys.

---

### H-2 · Parallel bust-vote resolution — logic drift risk
**Files:** `app/services/drink_tracker.py:apply_bust_vote_penalties` · `engine/referee.py:_resolve_bust_votes`
**Problem:** Two completely separate implementations of bust-vote settlement exist. The web path uses `apply_bust_vote_penalties` (called from `round_pipeline.py`). The terminal-CLI path uses `_resolve_bust_votes` (called from `RefereeSession.cmd_endround`). They differ in their handout handling — the terminal version calls `tracker._handle_handout` interactively; the web version opens a `_bust_handout_expires_at` timed window. Any rule change must be applied in both places. This is already the case — but the CLI version is the one that would get forgotten.
Additionally: `RefereeSession` is always constructed in `lobby.py` with default `bust_vote_enabled=False`, so `_resolve_bust_votes` always exits immediately in web mode. This means `_resolve_bust_votes` is dead code for web sessions but still maintained and could cause confusion.
**Fix (short term):** Add a comment to both functions explicitly naming the other and explaining why they're separate.
**Fix (long term):** Extract shared logic into a single `_bust_vote_outcomes(dealer_busted, voters)` function that returns `(winners, losers)`, then call it from both paths.

---

### H-3 · `compute_sip_totals` and `compute_dealer_role_sips` are redundant
**File:** `app/services/serializer.py` lines 232-257
**Problem:** `serialize_state` uses `_compute_live_drink_totals` which does both calculations in one pass. `compute_sip_totals` and `compute_dealer_role_sips` are separate exported functions that walk the same data independently. `compute_sip_totals` is used only in `wild_card.py`; `compute_dealer_role_sips` appears to be unused entirely.
**Fix:** Remove `compute_dealer_role_sips`. For `compute_sip_totals`, inline the call to `_compute_live_drink_totals` and return the first element, or just let `wild_card.py` call `_compute_live_drink_totals` directly. This eliminates a second full pass over the drink log.

---

### H-4 · `_join_attempts` dict grows unbounded
**File:** `app/services/session_store.py` line 43
**Problem:** The rate-limiter dict `_join_attempts: dict[str, list[float]]` cleans up expired timestamps per-IP on each access, but IPs that never attempt a join again retain their (now-empty) list forever. In long-running sessions with many unique client IPs this is a soft memory leak.
**Fix:** In `is_join_rate_limited`, after pruning expired timestamps, delete the key if the list becomes empty:
```python
_join_attempts[ip] = [t for t in prev if t > cutoff]
if not _join_attempts[ip]:
    del _join_attempts[ip]
```

---

### H-5 · `RefereeSession._insurance_result` not initialized in `__init__`
**File:** `engine/referee.py`
**Problem:** `RefereeSession.__init__` never sets `self._insurance_result`. The attribute is only created by `reset_round_state()` (via the `GameRoom` property setter). If `cmd_endround` is called on a `RefereeSession` directly (e.g., in tests, CLI mode, or before any `reset_round_state` call), line 601 guards with `hasattr(self, "_insurance_result")` — a code smell that signals the missing initializer.
**Fix:** Add `self._insurance_result = None` to `RefereeSession.__init__` alongside the other round-state fields. Remove the `hasattr` guard and simplify to `if self._insurance_result is None:`.

---

## 🟡 MEDIUM

### M-1 · Lazy imports inside `_deal_card_to` in `blackjack.py`
**File:** `engine/blackjack.py` — `RoundManager._deal_card_to` lines 417-420
**Problem:**
```python
from engine.drinking_rules import DrinkingRules
from engine.events import CardDealtEvent
```
These imports are inside a method that is called for every single card dealt. Python caches module imports so there is no re-execution penalty, but the attribute lookup chain (`sys.modules[...]`) runs on every call. More importantly, it obscures dependencies — a reader has to search inside method bodies to find what `_deal_card_to` depends on.
**Fix:** Move these to the module top-level, guarded by `TYPE_CHECKING` if circular-import issues arise. Since `blackjack.py` is already imported by `drinking_rules.py`, check import order first — they may need to be conditional.

---

### M-2 · `print_round_summary` — three consecutive `if self.verbose` guards
**File:** `engine/drinking_rules.py` — `DrinkTracker.print_round_summary` lines 829-835
**Problem:**
```python
if self.verbose:
    print("\n" + "="*52)
if self.verbose:
    print("  DRINK SUMMARY")
if self.verbose:
    print("="*52)
```
Three separate guard checks for three sequential prints. Slightly wasteful and visually noisy.
**Fix:** Collapse into one block:
```python
if self.verbose:
    print("\n" + "="*52)
    print("  DRINK SUMMARY")
    print("="*52)
```

---

### M-3 · `_cmd_newround` double-resets the shoe when deck count was queued
**File:** `app/routes/game_commands.py` — `_cmd_newround` lines 621-635
**Problem:** When a player queues a `num_decks` change, `apply_queued_settings` creates a fresh `Shoe(new_count)` and calls `shoe.shuffle()`. Then `_cmd_newround` checks `game_session.shoe.needs_reshuffle()` and (in drinking mode or if penetration triggered) calls `game_session.shoe.reset()` — re-shuffling the already-fresh shoe for no reason.
**Fix:** Skip the `shoe.reset()` call when `apply_queued_settings` already created a new shoe. One option: have `apply_queued_settings` return a flag `new_shoe_created`, and skip the reset when it's True.

---

### M-4 · `DrinkTracker.apply_end_of_round` has a confusing variadic signature
**File:** `engine/drinking_rules.py` line 717
**Problem:** `def apply_end_of_round(self, *msg_lists)` suggests it accepts multiple separate lists. But every call site passes a single list: `tracker.apply_end_of_round(eor_msgs)`. The variadic form adds confusion and makes grep for callers harder.
**Fix:** Change signature to `def apply_end_of_round(self, msgs: list)`. Update the internal flatten to just use `msgs` directly. Update `NullTracker.apply_end_of_round` to match.

---

### M-5 · `_cmd_blackjack` in referee mode doesn't buffer for hard-switch exemption
**File:** `engine/referee.py` — `cmd_action` `"blackjack"` branch (line 314-317)
**Problem:** When `action blackjack` is used in referee mode, the hand is appended to `_pending_bj_hands`. These are then fired in `cmd_endround` after `exempt_dealer` (hard switch) is known. This part is correct. However, if someone calls `action blackjack` *after* `endround` has already run (operator error), the pending list was cleared and the BJ drinks are silently dropped.
**Fix:** Log a warning in `cmd_endround` if `_pending_bj_hands` is non-empty when it shouldn't be (phase already resolved).

---

### M-6 · `classify_rule` has no catch for A♣ negative-sip from dealer-player
**File:** `app/services/utils.py` — `classify_rule`
**Problem:** The reason string for the deferred dealer-player A♣ credit is:
`f"{player.name} A♣ credit: -1 sip"` (from `DrinkTracker.apply_ace_clubs_credit`).
This matches `"A♣" in r and "credit" in r` → `"A♣ protection credit"`. ✓ That works. But the *informational* message logged before deciding whether to apply the credit:
`"A♣ dealt to {recipient} (also dealer) => partial Hard Switch protection; -1 sip credit applies only if no hard switch"`
— contains both `"A♣"` and `"credit"`, so it would also match `"A♣ protection credit"` if it ever appeared in a drink log. In practice it is logged with `sips=0` so it's skipped via the `if sips == 0: continue` guard in `_record_csv_rows`. No actual bug, but fragile — a future sips change could make it surface.
**Fix:** Add `"applies only if no hard switch"` as an explicit None return before the A♣ credit branch, or use a more specific substring match.

---

### M-7 · Strategy hint in Normal mode references drinking-mode overrides
**File:** `app/services/serializer.py` — `compute_best_play` line 298
**Problem:** `compute_best_play` passes `drinking_mode=session.drinking_mode` to `NPC_Player.best_play`. In Normal mode, `drinking_mode=False` — correct. But `strategy.best_play` uses the `drinking_mode` flag to force-split unsuited 10-pairs. Since Normal mode sessions always have `drinking_mode=False`, this is currently harmless. However if `strategy_hint_enabled` is True in Normal mode, the hint is computed without the mandatory-split-10 override, which is correct. No bug — just documenting that this is intentional.
**No action required.** Add an inline comment confirming intent.

---

## 🟢 LOW

### L-1 · `is_dealer_client` duplicates `get_client_info` logic
**File:** `app/services/validators.py` lines 70-73
**Problem:**
```python
def is_dealer_client(session, client_id: str) -> bool:
    info = get_client_info(session, client_id)
    god_mode = session._god_mode
    return info["is_dealer"] or (info.get("role") == "admin" and god_mode)
```
`get_client_info` already computes `is_dealer` using the same god_mode check (line 66). So `is_dealer_client` is `info["is_dealer"]` — the second OR clause is already incorporated. The function duplicates one check that is already embedded in `get_client_info`.
**Fix:** Simplify to:
```python
def is_dealer_client(session, client_id: str) -> bool:
    return get_client_info(session, client_id)["is_dealer"]
```

---

### L-2 · Test suite fails to collect without Flask installed
**File:** `tests/test_bust_vote.py` (and any test that imports `from app import create_app`)
**Problem:** Running `pytest` without `pip install -r requirements.txt` fails at collection with `ModuleNotFoundError: No module named 'flask'`. The engine-only tests (`test_drinking_rules_*`, `test_classify_rule`, `test_regression_snapshots`, etc.) could run fine, but the entire suite is aborted.
**Fix:** Add a `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` `testpaths` split, or use `pytest.importorskip("flask")` in Flask-dependent test files so engine tests remain runnable in isolation.

---

### L-3 · `_waiting_clients` pruning doesn't clean up the room key
**File:** `app/services/session_store.py` — `get_waiting_clients` line 131
**Problem:** After all clients leave a waiting room, `_waiting_clients[room_code]` becomes an empty dict `{}` but the key is never removed. Over many room lifecycles this leaves empty entries.
**Fix:** After pruning stale clients, `if not clients: del _waiting_clients[room_code]`.

---

### L-4 · ANSI colour codes at module top of `blackjack.py`
**File:** `engine/blackjack.py` lines 19-20
**Problem:** `_BLUE` and `_RESET` are defined at module level and only used inside `RoundManager._play_hand` (terminal interactive game only). They're harmless in web mode but add noise.
**Fix:** Move them inside `_play_hand` or into a `_terminal_only` block, or prefix with a comment `# terminal-only`.

---

### L-5 · `_ace_drink_events` sequence counter resets per round but frontend tracks by seq
**File:** `app/models/game_room.py` — `RoundState._ace_drink_seq`
**Problem:** `_ace_drink_seq` resets to 0 on every `newround` (because `RoundState` is replaced wholesale). The frontend uses this sequence to avoid re-processing events. If the last ace event of round N was seq=3, and round N+1 starts, the frontend sees seq=1 and correctly processes it as new. This works because the frontend also resets its local pointer when it detects a new round via `round_count`. No bug — but it's fragile; the interaction between `round` counter and `_ace_drink_seq` is implicit.
**Fix:** Document this contract explicitly in a comment on `RoundState._ace_drink_seq`.

---

### L-6 · `Shoe.shuffle()` prints to stdout in non-quiet paths
**File:** `engine/blackjack.py` — `Shoe.shuffle` line 133
**Problem:** `Shoe.shuffle(quiet=False)` calls `print(f"Shoe shuffled ...")`. In referee mode, the web layer captures stdout via `contextlib.redirect_stdout`, but `Shoe.shuffle` is also called from `apply_queued_settings → Shoe(n); shoe.shuffle()` which is NOT inside a `capture()` call. This leaks a `"Shoe shuffled"` print to the web server's stdout.
**Fix:** In `apply_queued_settings` and `_cmd_newround`, call `shoe.shuffle(quiet=True)`, or route shuffle prints through `log.debug`.

---

### L-7 · `reports.py` not audited for data-export correctness
**File:** `app/routes/reports.py`
**Note:** The CSV export route was not fully audited. Confirm that `_drink_csv_rows` entries are correctly flushed and that concurrent sessions don't share state (they don't — each `GameRoom` owns its own `_drink_csv_rows` list).

---

---

## Frontend Audit

> Principle: **all game logic belongs in the backend.** The frontend's job is rendering server state, capturing user intent, and forwarding it to the server. Any computation that derives a game outcome, enables/disables a mechanic, or produces user-facing text about rules belongs in Python, not JS.

---

## 🔴 CRITICAL (Frontend)

### FC-1 · `onclick` strings break on player names containing apostrophes
**Files:** `static/js/ui/table-modals.js` — `_renderInsuranceBanner()` (line 198); `_renderMilestoneSteppers()` (line 449)
**Problem:**
Both functions inject player names into inline `onclick` attribute strings:
```js
onclick="castInsuranceVote('${escapeHtml(v.bj_player)}', ...)"
onclick="milestoneAdjust('${escapeHtml(name)}', -1)"
```
`escapeHtml` converts `'` → `&#39;`. Browsers decode HTML entities in attribute values before passing them to the JS engine, so `O&#39;Brien` becomes `O'Brien` in the executed JS, breaking the string literal and causing a syntax error. `sanitize_name` strips HTML tags but does not strip apostrophes, so any player named e.g. `O'Brien` silently breaks both the insurance modal and the milestone stepper.
**Fix:** Switch to `data-*` attributes and addEventListener, matching the pattern already used in `_renderBustGivePanel()`:
```js
// Instead of onclick="...", do:
btn.dataset.bjPlayer = v.bj_player;
btn.addEventListener("click", () => castInsuranceVote(btn.dataset.bjPlayer, ...));
```

---

## 🟠 HIGH (Frontend)

### FH-1 · `doNewRound()` decides dealer rotation — game logic in frontend
**File:** `static/js/ui/log.js` — `doNewRound()` (line 197)
**Problem:**
```js
const rotate = drinking && !!(switchType || roundsTD >= rotateEvery);
await sendCmd(rotate ? "newround rotate" : "newround");
```
The frontend reads `switch_this_round`, `rounds_this_dealer`, and `dealer_rotate_every` from state and decides whether to rotate the dealer. This is a game rule, not a rendering decision. If the logic ever needs changing, it must be found and changed in JS, not in the Python rules layer where all other rotation logic lives.
**Fix:** Remove the rotation decision from the frontend. Always send `"newround"`. Add a backend flag (e.g., `auto_rotate: true`) to `apply_queued_settings` or `_cmd_newround` that reads `rounds_this_dealer`, `dealer_rotate_every`, and `switch_this_round` and calls `rotate_dealer()` automatically. Frontend just calls `"newround"`.

---

### FH-2 · `canDouble` computed in frontend — backend already has this information
**File:** `static/js/ui/table.js` — `updateActionButtons()` (line 602)
**Problem:**
```js
const canDouble = (activeHand.cards || []).length === 2 && !activeHand.doubled;
```
The frontend re-implements the double-down eligibility rule. The backend already serializes `can_split` on each hand; it should serialize `can_double` too. If the double-down rule ever changes (e.g., allowing double after split), both the backend serializer AND this JS line must be updated — and the JS line will inevitably be missed.
**Fix:** Add `can_double` to each hand's serialized state in `serialize_state` (already computed in `game_engine.py`). Frontend reads `activeHand.can_double` directly.

---

### FH-3 · Extensive stats computation in `kpi.js` — belongs in backend
**File:** `static/js/ui/kpi.js` — `renderStats()` (lines 142-488)
**Problem:**
`renderStats()` recomputes 30+ derived metrics from raw server data on every state update: `avgPerRound`, `avg3`, `avg5`, `avg10`, `sipm`, `bustRatePct`, `winRatePct`, `pushRatePct`, `dealerBustPct`, per-player `wr`, `dblPct`, `spPct`, `hitRate`, `avgHV`, `sdPct`, `netPL`, rolling averages, benchmark z-scores (via `benchmarkColor()`), and leaderboard rankings. None of this is display-only — it's all derivation from `hand_stats`, `sip_totals`, `streaks`, etc. that the backend already has in full.
**Fix (phased):**
- Short term: add a `kpi_stats` block to the serialized state containing pre-computed per-player rows and session summary values. Frontend `renderStats()` becomes a pure renderer — it reads `state.kpi_stats` and produces HTML with no arithmetic.
- The benchmark z-score computation (`benchmarkColor`) can stay in JS since it depends on the static `benchmarks.js` file which the backend doesn't load — but the backend could pre-classify each stat as `"good"` / `"neutral"` / `"bad"` and send the CSS class name, removing JS z-score math entirely.

---

## 🟡 MEDIUM (Frontend)

### FM-1 · Insurance outcome text duplicated across two functions
**Files:** `static/js/ui/admin.js` — `showInsuranceToast()` (line 689); `static/js/ui/table-modals.js` — `_renderInsuranceBannerOutcome()` (line 220)
**Problem:** Both functions reconstruct the same insurance outcome descriptions from `r.insured` and `r.dealer_bj` using identical if/else chains:
```js
// In showInsuranceToast():
if (r.insured && dBJ)        outcome = `dealer had BJ — BJ holder drinks own bonus, group safe`;
else if (!r.insured && !dBJ) outcome = `no dealer BJ — normal BJ bonus`;
// ...
// Repeated verbatim in _renderInsuranceBannerOutcome()
```
**Fix (short term):** Have one call the other, or extract `_insuranceOutcomeText(r)`.
**Fix (long term):** Backend includes `outcome_text` in each insurance result object; both functions just render `r.outcome_text`. This also removes game-rule knowledge from JS entirely.

---

### FM-2 · `switchRefTab()` and `switchDigTab()` are identical
**File:** `static/js/ui/table-render.js` (lines 173-186)
**Problem:**
```js
function switchRefTab(name, el) {
  document.querySelectorAll("#ref-tabs .tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll("#ref-panel .pane").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  document.getElementById(`pane-${name}`).classList.add("active");
}
function switchDigTab(name, el) { /* identical body, #dig-tabs / #dig-panel */ }
```
Both functions do exactly the same thing with different container IDs. A third mode would require a third copy.
**Fix:** Merge into `switchTab(tabsId, panelId, name, el)` and call from `data-args`.

---

### FM-3 · Age gate has two separate, conflicting handler paths
**Files:** `static/js/app.js` (lines 19-26); `static/js/ui/lobby.js` (lines 3-11)
**Problem:**
`app.js` attaches direct `addEventListener` handlers to `[data-action="confirmAge"]` and `[data-action="declineAge"]`. `bootstrap.js` ALSO fires `window.confirmAge()` / `window.declineAge()` (defined in `lobby.js`) via event delegation on every `[data-action]` click. Both run on every click. The two `declineAge` implementations are different:
- `app.js`: removes `.active` from `#age-gate-card`, adds `.active` to `.underage-screen`
- `lobby.js`: sets `#age-gate-msg.textContent = "Sorry..."`

The lobby.js implementations are effectively dead — the app.js handler runs first and its DOM changes mask the lobby.js effects. `#age-gate-msg` may not even exist in the current template.
**Fix:** Remove the direct `addEventListener` calls from `app.js`. Let `bootstrap.js` delegation call the `lobby.js` globals. Reconcile the `declineAge()` logic so there is one path.

---

### FM-4 · Bust vote status text built in JS — duplicated and diverged from backend wording
**File:** `static/js/ui/admin.js` — `updateBustVoteUI()` (lines 526-561); `showBustVoteToast()` (lines 644-672)
**Problem:** The bust vote outcome label (who won, who lost, drinking vs normal mode amounts) is constructed in two places in JS from the same `bust_vote_result` object. The two renders are not identical — `showBustVoteToast()` includes drink amounts, `updateBustVoteUI()` shows a simpler label — but both independently reconstruct outcome strings that the backend already assembled when it applied penalties.
**Fix:** Backend includes `outcome_summary` and `outcome_lines: [str]` in `bust_vote_result`. Both functions render these strings rather than recomputing them.

---

## 🟢 LOW (Frontend — New)

### LF-4 · `RANKS` and `SUITS` defined in `setup.js` — should be in `config.js`
**File:** `static/js/ui/setup.js` lines 212-213
These are shared constants (card data, not setup logic) used in `table.js`'s `buildCardGrid()`. They belong in `config.js` alongside `PHASE`, `ROLE`, and `DEALER_SENTINEL`.
**Fix:** Move `RANKS` and `SUITS` to `config.js`.

---

### LF-5 · `_mobileSheet()` in `kpi.js` constructed entirely with inline CSS
**File:** `static/js/ui/kpi.js` — `_mobileSheet()` (lines 113-136)
The mobile bottom-sheet overlay is assembled with `element.style.cssText = [...]`. It has a distinct visual purpose (a reusable sheet component) and should have a CSS class.
**Fix:** Add `.mobile-sheet-overlay` and `.mobile-sheet` to `kpi.css` or `modals.css`. `_mobileSheet()` sets `className` instead of `style.cssText`.

---

### LF-6 · `sendCmd()` silently drops commands when a request is in flight
**File:** `static/js/ui/table.js` — `sendCmd()` (line 283)
```js
if (_requestsInFlight > 0) return;
```
If the dealer taps an action while a poll is finishing, the command is silently dropped with no feedback. The user sees nothing wrong.
**Fix:** Log a console warning, or re-queue the command with a short `setTimeout`. Alternatively, make the lock button visual feedback (`cmd-pending` class) conspicuous enough that the user knows to wait.

---

### LF-7 · `renderStats()` in `kpi.js` mixes computation and rendering in 350 lines
**File:** `static/js/ui/kpi.js` — `renderStats()` (lines 142-488)
The function computes derived stats, builds leaderboard rows, builds callout cards, and writes the final `innerHTML` — all in one monolithic block. Any change to a stat calculation requires reading through HTML template literals.
**Fix (incremental):** Split into `_computeKpiData(state)` → pure data object, and `_renderKpi(data)` → pure HTML builder. This is a prerequisite for FH-3 anyway.

---

## 🟢 LOW — Carried Forward from Audit17June (Frontend)

### LF-1 · Sip ticker clips on 4+ players  *(was Audit17 L4)*
**File:** `static/css/components/kpi.css`, `static/js/ui/log.js`
Header strip renders per-player sip counts inline with no overflow guard. On narrow screens with 5+ players the ticker row overflows/clips.
**Fix:** Add `overflow-x: auto; white-space: nowrap;` on the ticker container, or switch to a wrapping flex layout with a `min-width` per sip chip.

---

### LF-2 · Action buttons matched by `textContent` — fragile  *(was Audit17 L7)*
**File:** `static/js/ui/table.js`, `static/js/ui/admin.js`
`updateActionButtons`, `updateBestPlay`, `updateRoleUI`, and `updateHonorPrompt` all match buttons by `b.textContent.trim() === "SPLIT"` / `"HIT"` etc. A copy-change or i18n attempt would silently break the logic.
**Fix:** Add `data-action-code="split"` / `data-action-code="hit"` attributes on each button element and match by `b.dataset.actionCode` instead.

---

### LF-3 · Inline CSS strings in JS — widespread  *(was Audit17 L14)*
**File:** `static/js/ui/admin.js`, `static/js/ui/table.js`, `static/js/ui/log.js`
`element.style.cssText = "..."` and template-literal inline styles appear throughout dynamically constructed markup (`_renderBustVoteCards`, `_renderBustGivePanel`, `showLocalSeatPicker`, `renderDrinksDetail`, `updateRoundPane`, `showPeekedCard`, and others). Pattern has grown since June 16 audit.
**Fix:** Extract each inline style block into a named CSS class and toggle with `classList.add/remove`. Start with the hot-path elements (bust vote cards, drinks detail panel).

---

## Implementation Checklist (Priority Order)

Work top-to-bottom. Each item references the finding above.

```
CRITICAL — fix before next play session
[x] C-2  Fix is_soft_hand() in strategy.py for multi-ace hands

HIGH — fix before next public session
[X] H-5  Add _insurance_result = None to RefereeSession.__init__; remove hasattr guard
[X] H-1  Remove dead "protected" key from _ace_clubs_flag everywhere
[X] H-4  Delete empty _join_attempts keys after pruning in session_store.py
[x] H-3  Remove compute_dealer_role_sips (unused); simplify compute_sip_totals
[x] H-2  Add cross-reference comments to both bust-vote resolution functions

MEDIUM — address in next refactor pass
[X] M-2  Collapse three consecutive `if self.verbose` prints in print_round_summary
[x] M-4  Change apply_end_of_round(*msg_lists) to apply_end_of_round(msgs: list)
[x] M-1  Move lazy imports in _deal_card_to to module top level
[x] M-3  Skip shoe.reset() in _cmd_newround when apply_queued_settings created a new shoe
[x] M-5  Log warning in cmd_endround if _pending_bj_hands is non-empty unexpectedly
[x] M-6  Add explicit None-return guard for A♣ informational message in classify_rule

LOW — cleanup sprint
[x] L-1  Simplify is_dealer_client to return get_client_info(...)["is_dealer"]
[x] L-6  Use quiet=True in apply_queued_settings and _cmd_newround shoe shuffles
[x] L-3  Delete empty _waiting_clients[room_code] after all clients prune out
[ ] L-2  Add pytest.importorskip("flask") to Flask-dependent test files
[x] L-4  Move _BLUE/_RESET ANSI codes into the function that uses them
[x] L-5  Document RoundState._ace_drink_seq / round_count interaction in a comment
[ ] L-7  Audit reports.py CSV export for correctness
[x] L-8  Remove "blackjack" from DIGITAL_COMMANDS and digital help text (dead code)

Frontend — CRITICAL
[x] FC-1 Fix onclick string injection for player names with apostrophes (table-modals.js)

Frontend — HIGH (logic belongs in backend)
[x] FH-1 Move dealer-rotation decision out of doNewRound() into _cmd_newround backend
[x] FH-2 Serialize can_double on each hand; remove frontend recomputation
[x] FH-3 Move kpi stat derivation to backend; frontend renderStats() becomes a pure renderer

Frontend — MEDIUM
[x] FM-3 Reconcile age gate handlers — remove direct addEventListener from app.js
[x] FM-1 Extract _insuranceOutcomeText(); backend sends outcome_text on insurance results
[x] FM-2 Merge switchRefTab() / switchDigTab() into single switchTab(tabsId, panelId, name, el)
[x] FM-4 Backend sends outcome_summary on bust_vote_result; remove JS text construction

Frontend — LOW (cleanup)
[x] LF-3 Replace inline CSS strings in JS with toggled CSS classes (admin.js, table.js, log.js)
[x] LF-2 Switch action-button matching to data-action-code attributes (table.js, admin.js)
[x] LF-5 Add .mobile-sheet CSS class; remove inline style.cssText from _mobileSheet()
[x] LF-6 Add user feedback when sendCmd() drops a command (request in flight)
[x] LF-4 Move RANKS and SUITS from setup.js to config.js
[x] LF-7 Split renderStats() into _computeKpiData() + _renderKpi() (prerequisite for FH-3)
[x] LF-1 Add overflow guard on sip ticker row for 4+ players (kpi.css / log.js)
```

---

## Summary Table

| ID | File(s) | Severity | Type |
|---|---|---|---|
| L-8 | `game_commands.py` | 🟢 LOW | Dead code — _cmd_blackjack in DIGITAL_COMMANDS |
| C-2 | `strategy.py` | 🔴 CRITICAL | Bug — wrong strategy |
| H-1 | `referee.py`, `blackjack.py`, `game_room.py` | 🟠 HIGH | Dead code / confusion |
| H-2 | `drink_tracker.py`, `referee.py` | 🟠 HIGH | Maintenance hazard |
| H-3 | `serializer.py` | 🟠 HIGH | Redundancy |
| H-4 | `session_store.py` | 🟠 HIGH | Memory leak |
| H-5 | `referee.py` | 🟠 HIGH | Missing initializer |
| M-1 | `blackjack.py` | 🟡 MEDIUM | Lazy import in hot path |
| M-2 | `drinking_rules.py` | 🟡 MEDIUM | Redundant guards |
| M-3 | `game_commands.py` | 🟡 MEDIUM | Double shoe reset |
| M-4 | `drinking_rules.py` | 🟡 MEDIUM | Confusing API |
| M-5 | `referee.py` | 🟡 MEDIUM | Silent failure risk |
| M-6 | `utils.py` | 🟡 MEDIUM | Fragile string match |
| M-7 | `serializer.py` | 🟡 MEDIUM | Intent unclear (no action) |
| L-1 | `validators.py` | 🟢 LOW | Duplicate logic |
| L-2 | `tests/` | 🟢 LOW | Test infrastructure |
| L-3 | `session_store.py` | 🟢 LOW | Memory cleanup |
| L-4 | `blackjack.py` | 🟢 LOW | Style |
| L-5 | `game_room.py` | 🟢 LOW | Missing comment |
| L-6 | `blackjack.py`, `room_manager.py` | 🟢 LOW | Stdout leak |
| L-7 | `reports.py` | 🟢 LOW | Not yet audited |
| FC-1 | `table-modals.js` | 🔴 CRITICAL | onclick apostrophe injection |
| FH-1 | `log.js` | 🟠 HIGH | Rotation logic in frontend |
| FH-2 | `table.js`, `serializer.py` | 🟠 HIGH | canDouble computed in JS |
| FH-3 | `kpi.js`, `serializer.py` | 🟠 HIGH | Stats computed in JS |
| FM-1 | `admin.js`, `table-modals.js` | 🟡 MEDIUM | Duplicate outcome text |
| FM-2 | `table-render.js` | 🟡 MEDIUM | Duplicate tab functions |
| FM-3 | `app.js`, `lobby.js` | 🟡 MEDIUM | Duplicate age-gate handlers |
| FM-4 | `admin.js` | 🟡 MEDIUM | Bust vote text in JS |
| LF-1 | `kpi.css`, `log.js` | 🟢 LOW | UI overflow (carry-fwd) |
| LF-2 | `table.js`, `admin.js` | 🟢 LOW | Fragile button matching (carry-fwd) |
| LF-3 | `admin.js`, `table.js`, `log.js` | 🟢 LOW | Inline CSS in JS (carry-fwd) |
| LF-4 | `setup.js`, `config.js` | 🟢 LOW | Misplaced constants |
| LF-5 | `kpi.js` | 🟢 LOW | Inline CSS in mobileSheet |
| LF-6 | `table.js` | 🟢 LOW | Silent command drop |
| LF-7 | `kpi.js` | 🟢 LOW | Mixed compute+render |
