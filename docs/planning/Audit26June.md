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

### C-1 · `_cmd_blackjack` in digital mode double-fires BJ drinks  
**File:** `app/routes/game_commands.py` — `_cmd_blackjack` (line 577)  
**Problem:**  
`_cmd_blackjack` is registered in `DIGITAL_COMMANDS` and applies `BlackjackEvent` drinks immediately via `session.tracker.apply()`. In digital mode, `dealer_turn()` in `game_engine.py` (line 420-424) already buffers and fires the exact same `BlackjackEvent` for every winning blackjack via `eor_msgs`. If anyone calls `blackjack <player>` in digital mode (possible with god_mode on), that player's opponents are charged twice. It also bypasses the 4-player EOR halving because it goes through `tracker.apply()` not the `eor_msgs` buffer.  
**Fix:** Remove `"blackjack"` from `DIGITAL_COMMANDS`. It is only meaningful in referee mode where natural BJs must be manually declared. In digital mode, blackjacks are detected automatically.

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

## Implementation Checklist (Priority Order)

Work top-to-bottom. Each item references the finding above.

```
CRITICAL — fix before next play session
[ ] C-1  Remove "blackjack" from DIGITAL_COMMANDS in game_commands.py
[ ] C-2  Fix is_soft_hand() in strategy.py for multi-ace hands

HIGH — fix before next public session
[ ] H-5  Add _insurance_result = None to RefereeSession.__init__; remove hasattr guard
[ ] H-1  Remove dead "protected" key from _ace_clubs_flag everywhere
[ ] H-4  Delete empty _join_attempts keys after pruning in session_store.py
[ ] H-3  Remove compute_dealer_role_sips (unused); simplify compute_sip_totals
[ ] H-2  Add cross-reference comments to both bust-vote resolution functions

MEDIUM — address in next refactor pass
[ ] M-2  Collapse three consecutive `if self.verbose` prints in print_round_summary
[ ] M-4  Change apply_end_of_round(*msg_lists) to apply_end_of_round(msgs: list)
[ ] M-1  Move lazy imports in _deal_card_to to module top level
[ ] M-3  Skip shoe.reset() in _cmd_newround when apply_queued_settings created a new shoe
[ ] M-5  Log warning in cmd_endround if _pending_bj_hands is non-empty unexpectedly
[ ] M-6  Add explicit None-return guard for A♣ informational message in classify_rule

LOW — cleanup sprint
[ ] L-1  Simplify is_dealer_client to return get_client_info(...)["is_dealer"]
[ ] L-6  Use quiet=True in apply_queued_settings and _cmd_newround shoe shuffles
[ ] L-3  Delete empty _waiting_clients[room_code] after all clients prune out
[ ] L-2  Add pytest.importorskip("flask") to Flask-dependent test files
[ ] L-4  Move _BLUE/_RESET ANSI codes into the function that uses them
[ ] L-5  Document RoundState._ace_drink_seq / round_count interaction in a comment
[ ] L-7  Audit reports.py CSV export for correctness
```

---

## Summary Table

| ID | File(s) | Severity | Type |
|---|---|---|---|
| C-1 | `game_commands.py` | 🔴 CRITICAL | Bug — double drink |
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
