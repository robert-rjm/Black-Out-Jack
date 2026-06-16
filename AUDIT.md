# Black-Out-Jack — Code Audit

_16 June 2026 · Busfahrer feature excluded_

---

## 1. Confirmed Bugs

### 1.1 `_cmd_blackjack` bypasses the event system - DONE
**File:** `app/routes/game_commands.py` line 593

```python
DrinkingRules.on_blackjack(player.name, hand, all_names)
```

Every other event (card dealt, round end, hand resolved, etc.) goes through `DrinkingRules.handle(SomeEvent(...))`, which uses match/case dispatch. The blackjack event calls `on_blackjack()` directly. If you add pre/post hooks or logging to `handle()`, the blackjack path is silently exempt.

**Fix:** Replace with `DrinkingRules.handle(BlackjackEvent(player_name=player.name, hand=hand, all_names=all_names))`.

---

### 1.2 `NullTracker` missing `easy_mode` attribute  - DONE
**File:** `app/services/room_manager.py`

`_cmd_newround` (via `apply_queued_settings`) does:
```python
session.tracker.easy_mode = session.easy_mode
```

`DrinkTracker` has `easy_mode`. `NullTracker` does not. In Normal (non-drinking) mode `session.tracker` is a `NullTracker`, so this raises `AttributeError` the first time a queued settings update includes `easy_mode`.

**Fix:** Add `easy_mode: bool = False` to `NullTracker`, or add `__setattr__` that silently ignores unknown attributes.

---

### 1.3 Post-round pipeline duplicated between `polling.py` and `game_commands.py` - DONE
**Files:** `app/routes/polling.py` lines 66–74, `app/routes/game_commands.py` lines 207–220

`_resolve_endround()` in game_commands.py correctly sequences:
1. `game_session.cmd_endround()`
2. `apply_bust_vote_penalties()`
3. `harvest_drink_log()`
4. `check_and_set_milestone()`
5. `apply_payouts()`
6. `backfill_hand_results()`

`_run_deferred_dealer_play()` in polling.py replicates the same five post-round steps inline, with `dealer_turn()` prepended. There is no shared abstraction. If the ordering or membership of the pipeline ever changes, one site will drift out of sync with the other. This is currently correct but is a maintenance bug waiting to happen.

**Fix:** Extract a `_do_endround_pipeline(session)` helper (called by both sites) into a shared service, or move `_resolve_endround` to a service module and import it from polling.py as well.

---

### 1.4 ~~`capture()` imported but never called in lobby.py~~ — RETRACTED

`capture` is called at `lobby.py` line 207 (`output = capture(raw_session.start_round)`). The import is live. This item was a false positive from an incomplete grep.

---

### 1.5 ~~`io.StringIO / redirect_stdout` in `command()` — output silently discarded~~ — RETRACTED

`buf.getvalue()` is read at line 817 and is actively used: the captured stdout is appended to `game_session._log_entries` and returned in the JSON response so all polling clients see referee-session print output. The pattern is intentional and mirrors `capture()` in `lobby.py`. False positive.

---

## 2. Inconsistencies

### 2.1 Four independent split implementations - DONE
**Files:**
- `engine/blackjack.py` line 212 — `Hand.split()` (canonical)
- `engine/blackjack.py` line 592 — `RoundManager._play_hand` (terminal play, calls `hand.split()`)
- `engine/referee.py` line 308 — inline copy (`_split_chain` sharing + increment)
- `app/routes/game_commands.py` line 512 — inline copy (web split command)
- `app/services/game_engine.py` line 506 — inline copy (NPC auto-play)

The canonical `Hand.split()` in `blackjack.py` handles chain-counter sharing and card manipulation. Three other sites replicate the `_split_chain`/`split_count` logic by hand. A bug in split behavior must be found and fixed in four places.

**Fix:** Move the post-split "insert into player.hands + deal second card" steps into a helper function (e.g., `perform_split(player, hand_label, shoe)`) that wraps `hand.split()`. Replace all three inline copies with a single call.

---

### 2.2 `get_player_hand()` vs `RefereeSession._get_hand()` — near-identical - DONE
**Files:** `app/services/game_engine.py`, `engine/referee.py`

Both resolve a `"handN"` label to a `Hand` object, extending `player.hands` if needed. The logic is copy-pasted. The web layer uses `get_player_hand`; the referee CLI uses `_get_hand`.

**Fix:** Keep one (suggest `get_player_hand` in `game_engine.py`) and have `_get_hand` delegate to it, or delete `_get_hand` entirely and update the two CLI callers.

---

### 2.3 ~~`RoundManager._round_end_drinks` bypasses `DrinkingRules.handle()`~~ — RETRACTED

`_round_end_drinks` already calls `DrinkingRules.handle(RoundEndEvent(...))` at line 770. The audit note was wrong — it was never bypassing the event system. False positive.

---

### 2.4 `_print_digital_help()` logs to `log.debug()`, referee help uses `self._log()` - DONE
**File:** `app/routes/game_commands.py`

The two help printers use different output channels. `log.debug()` never reaches the web client; `self._log()` appends to the room's message buffer which is returned to the frontend. Digital mode help is therefore silent in production.

---

### 2.5 `/setup` route hardcodes defaults rather than using `app/config.py` - DONE
**File:** `app/routes/lobby.py` line 144–145, `app/config.py` lines 63–66

`config.py` defines `DEFAULT_WAGER = 1`, `DEFAULT_NUM_HANDS = 2`, etc., but the setup route hardcodes the same values inline with `data.get("wager", 1)`. If you change a default in config, setup doesn't pick it up.

**Fix:** Import and use the `DEFAULT_*` constants.

---

### 2.6 `_hard_switch_drinking_applied` read via `getattr` with a default - DONE
**File:** `app/models/game_room.py`

```python
getattr(self.session, '_hard_switch_drinking_applied', False)
```

This exists because the attribute isn't guaranteed to be present on all `RefereeSession` instances. The fragility suggests the attribute was added after the fact. It should be initialized in `RefereeSession.__init__` and accessed normally.

---

### 2.7 `GameRoom` state vs `RefereeSession` state boundary is blurry - DONE
**File:** `app/models/game_room.py`

`GameRoom` has 50+ fields and delegates ~15 of them directly to `self.session` via properties. Per-round transient state (`bust_vote_open`, `insurance_vote`, `_pending_resolved`, etc.) lives partly in `GameRoom` and partly in `RefereeSession`, with `reset_round_state()` responsible for clearing the `GameRoom` side. There's no clear contract about which layer owns what.

**Suggestion:** Document (with a comment block) which fields are "session-lifetime" vs "per-round transient" and which layer is authoritative for each.

---

## 3. Dead Code

| Item | Location | Notes |
|------|----------|-------|
| ~~`GameEventType` enum~~ | `engine/events.py` | DONE — deleted; enum was never imported or used anywhere. |
| ~~`DEFAULT_NUM_DECKS`~~ | `app/config.py` | DONE — deleted; `DEFAULT_WAGER`, `DEFAULT_NUM_HANDS`, `DEFAULT_MODE` are used. `DEFAULT_NUM_DECKS` was not. |
| `cmd_bustvotetoggle`, `cmd_bustvote` | `engine/referee.py` | DONE — marked with "Terminal-CLI only" docstring note; kept because `play_referee.py` calls them. |
| ~~Root `__pycache__/`~~ | Project root | Already in `.gitignore`; OS permissions prevent deletion but it won't be tracked. |

---

## 4. Refactor Opportunities

### 4.1 Extract the 5-step post-round pipeline - DONE
See bug 1.3. The sequence `cmd_endround → bust_vote_penalties → harvest → milestone → payouts → backfill` should live in one place and be called from both `game_commands.py` and `polling.py`.

### 4.2 `classify_rule()` is in the wrong module - DONE
**File:** `engine/drinking_rules.py`

`classify_rule()` is a pure lookup function that maps rule names to categories. Its only meaningful consumer is in `app/services/drink_tracker.py`. Having it in `engine/` creates an `engine→app` knowledge coupling that goes in the wrong direction (engine shouldn't know about app-layer classifications).

**Fix:** Move to `app/services/drink_tracker.py` or a new `app/utils.py`.

### 4.3 Serializer's milestone lambda - DONE
**File:** `app/services/serializer.py`

`serialize_state()` contains a multi-expression inline lambda for milestone progress. It's untestable in isolation. Extract it as a named function.

### 4.4 `compute_sip_totals()` and `compute_dealer_role_sips()` both iterate `drink_log` separately
**File:** `app/services/serializer.py`

Called in the same `serialize_state()` pass, they do two full iterations over the same log. A single pass accumulating both would halve the work. Not performance-critical at current scale, but worth cleaning up.

### 4.5 Large inline CSS strings in JS
**Files:** `static/js/ui/table.js`, `static/js/app.js`

`updateRoundPane()`, `renderDrinksDetail()`, and `selectDrinksPlayer()` build style strings inline in JavaScript (e.g., `element.style.cssText = "font-size:11px; color:..."`). These should be CSS classes toggled by JS, not style strings generated by JS. This makes visual changes require JS edits and breaks theming.

---

## 5. UI / Dead Space Issues

### 5.1 Bottom nav labels always hidden (accessibility)
**File:** `static/css/main.css`

`.bnav-label { display: none }` hides text labels permanently on all breakpoints. Icon-only navigation fails accessibility guidelines and is confusing for first-time players. Add visible labels on desktop (≥640px) or add tooltip/title attributes.

### 5.2 `.bnav-btn` has duplicate `min-height` - DONE
**File:** `static/css/main.css` around line 194

```css
.bnav-btn {
  min-height: 44px;   /* ← immediately overridden */
  ...
  min-height: 52px;
}
```

The first value is dead. Remove it.

### 5.3 `.bust-vote-status` defined twice - DONE
**File:** `static/css/components/controls.css` lines 230 and 233

Two separate rule blocks for `.bust-vote-status` with different properties. The first (just `margin-top: 8px`) is likely a survivor of a refactor. Merge into one block.

### 5.4 Card overflow on long hands
**Files:** `static/css/components/table.css`

`.cards-row` has no `overflow-x` property. When a player hits to 5+ cards the row overflows its container without a scrollbar (`.hands-row` has `overflow-x: auto` but the inner `.cards-row` does not clip or scroll). After splits this is especially visible.

**Fix:** Add `overflow-x: auto` to `.cards-row`, or allow cards to wrap with `flex-wrap: wrap`.

### 5.5 Done seats fade too aggressively
**File:** `static/css/components/table.css`

`.seat.done { opacity: .55 }` dims all finished players. With 3+ seats the table turns into a collection of grey boxes making it hard to find who is still active. The active-player highlight should increase rather than all others decreasing.

**Fix:** Reduce the dimming to `opacity: .75`, or use a colored left-border accent on the active seat instead.

### 5.6 Sip ticker overflows on 4+ players
**Files:** `static/css/components/kpi.css`, header layout

The sip ticker in the header uses `overflow-x: auto` but the header row has fixed height and no room to show the scrollbar. On mobile with 4+ players, the rightmost players' sip counts are clipped.

**Suggestion:** Move the sip ticker out of the header and into a collapsible panel, or use a horizontal scroll container with visible scroll indicators.

### 5.7 No loading / reconnection state
**Files:** `static/js/state.js`, `static/js/app.js`

When the `/state` poll fails or is slow, the UI stays frozen with no visual feedback. Users have no way to distinguish "server is thinking" from "the connection dropped."

**Fix:** Add a `data-loading` attribute or CSS class on the root element that triggers a subtle indicator (e.g., a pulsing top bar) when a fetch is in flight and clears when it resolves.

### 5.8 Magic number in admin nav icon offset
**File:** `static/css/main.css`

```css
#btn-admin-nav .bnav-icon { transform: translateY(12px); }
```

No comment explaining why this specific offset is needed. Likely compensating for the admin icon being shorter than others. Add a comment or fix the icon sizing so the offset isn't needed.

---

## 6. Prioritized Action Plan

Items are ordered by impact × effort ratio. Work left to right through the tiers.

### Tier 1 — Fix before next session (correctness)

- [X] **Fix `NullTracker` missing `easy_mode`** (Bug 1.2) — one-liner, prevents AttributeError in Normal mode.
- [X] **Fix `_cmd_blackjack` event bypass** (Bug 1.1) — one-liner, brings blackjack into the event system.
- [X] **Fix `capture` dead import in lobby.py** (Bug 1.4) — cleanup, avoids confusion.
- [X] **Remove `io.StringIO` redirect in `command()`** (Bug 1.5) — remove or actually use the captured output.

### Tier 2 — Refactor soon (prevent future bugs)

- [X] **Extract shared post-round pipeline** (Bug 1.3, Refactor 4.1) — prevents the two sites from drifting. Create `do_endround_pipeline(session)` in a service module and call it from both `game_commands.py` and `polling.py`.
- [X] **Extract shared split helper** (Inconsistency 2.1) — three inline copies → one function. Highest deduplication ROI in the codebase.
- [X] **Consolidate `get_player_hand` / `_get_hand`** (Inconsistency 2.2) — remove the duplicate.

### Tier 3 — Cleanup (maintainability)

- [X] **Delete `GameEventType` enum** (Dead Code) — deleted from `engine/events.py`.
- [X] **Delete `DEFAULT_NUM_DECKS`** (Dead Code) — removed from `app/config.py`.
- [X] **Mark terminal-only CLI commands** (Dead Code) — `cmd_bustvotetoggle`/`cmd_bustvote` docstrings clarified.
- [X] **Wire `/setup` to `DEFAULT_*` constants** (Inconsistency 2.5) — one place to change defaults.
- [X] **Move `classify_rule()` to `app/services/utils.py`** (Refactor 4.2) — right module, right direction.
- [X] **Initialize `_hard_switch_drinking_applied` in `RefereeSession.__init__`** (Inconsistency 2.6) — remove the `getattr` guard.
- [X] **Extract `RoundState` dataclass** (Inconsistency 2.7) — 23 per-round fields moved out of `GameRoom`; `reset_round_state()` simplified to a single wholesale replacement.
- [X] **Extract serializer milestone lambda** (Refactor 4.3) — testability.
- [X] **Clean root `__pycache__/`** (Dead Code) — one-time housekeeping, add to `.gitignore`.

### Tier 4 — UI polish

- [X] **Fix duplicate `min-height` in `.bnav-btn`** (UI 5.2) — trivial.
- [X] **Merge duplicate `.bust-vote-status` rules** (UI 5.3) — trivial.
- [ ] **Add `overflow-x: auto` to `.cards-row`** (UI 5.4) — prevents card overflow on long hands.
- [ ] **Soften done-seat dimming** (UI 5.5) — `opacity: .55` → `.80`, or switch to active-seat accent.
- [ ] **Add bottom nav text labels on desktop** (UI 5.1) — accessibility win.
- [ ] **Add reconnection/loading indicator** (UI 5.7) — polish for multi-player sessions.
- [ ] **Fix sip ticker overflow on 4+ players** (UI 5.6) — move out of header or add proper scroll.
