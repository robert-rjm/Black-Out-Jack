# Black-Out-Jack Code Audit

Date: 2026-06-15

## 1. Backend (`app/`)

### Security / input validation
- **Inconsistent name sanitization**: `app/services/validators.sanitize_name()` strips HTML/bidi characters and caps length, but many admin/polling routes bypass it with raw `.strip().capitalize()` — `app/routes/admin.py` (`kick` L44, `make_bot` L110, `make_human` L158, `transfer_admin` L223, `vote_kick` L349) and `app/routes/polling.py` (`/vote_insurance` L536). Standardize on `sanitize_name()` everywhere a player-supplied name is processed.
- `app/routes/game_commands.py` `/command` (L720-781) — no length limit on the raw command string before `.split()`, unlike the `raw[:40]` guard pattern in `validators.py`.

### Bugs / logic
- `app/services/drink_tracker.py` `_apply_worst_player_streak` (L399-450) — uses `len(session._round_sip_history)` as the divisor for a player's avg sips/round; if players join mid-session, their average is artificially deflated by rounds they didn't play.
- `app/services/drink_tracker.py` `check_and_set_milestone` (L453-519) — `handout_sips = 4 + boundary // MILESTONE_STEP` hardcodes a relationship to `MILESTONE_STEP=50` that breaks if the constant changes (e.g. to 25). Derive the "+4" from config or document the coupling.
- `app/services/room_manager.py` `rotate_dealer` (L195-203) — `all_names.index(session.dealer_name)` can raise an unhandled `ValueError` if `dealer_name` is ever not in `all_players`.
- `app/services/game_engine.py` `auto_play_npc_turns` (L429-509) — hardcoded 100-iteration safety cap could theoretically be too low with many NPCs and deep split chains.
- `app/services/decision_log.py` L181 — `getattr(session, "room_code", None)` always returns `""` because `GameRoom` has no `room_code` field; every decision-log row has an empty `session_id`.
- `app/routes/lobby.py` `/setup` L150 — `names[min(dealer_idx, len(names) - 1)]` doesn't validate `dealer_idx >= 0`; a negative index silently wraps via Python negative indexing instead of erroring.

### Inconsistencies
- **Error response shape**: `app/routes/lobby.py` `/setup` returns `{"ok": False, "output": ...}` while almost everywhere else uses `{"ok": False, "error": ...}` — frontend handlers need to check both keys, a likely source of "stuck UI" bugs.
- `sanitize_name()` already calls `.capitalize()` internally, yet many routes redundantly/partially duplicate this with raw `.capitalize()` (see security section above) — same root cause, two symptoms.
- `app/routes/admin.py` imports `sanitize_name` locally inside three function bodies (`request_rejoin`, `update_settings`, `take_back_seat`) instead of once at module level.

### Refactor opportunities
- **Repeated admin-check boilerplate** across nearly every route in `admin.py` (`kick`, `undo_kick`, `make_bot`, `make_human`, `transfer_admin`, `set_anim_pref`, `update_settings`, `rotate_dealer`, `toggle_god_mode`, `take_back_seat`, `handle_rejoin`, `handle_registration`), with inconsistent error text ("Not authorised." vs "Admin only." vs "Admin only"). Extract a `require_admin(session, client_id)` helper or decorator.
- `app/services/drink_tracker.py` `harvest_drink_log` (L159-384) is a 225-line function handling ~8 distinct responsibilities — split into smaller helpers for testability.
- `app/routes/polling.py` `/state` (L88-145) embeds a ~60-line block of sequential side-effecting "tick" logic (insurance auto-resolve, bust-vote pause, milestone pause, handout forfeit) directly in the route — extract into a `tick(session)` service function.

---

## 2. Game engine (`engine/`)

### Critical — `engine/busfahrer.py` appears non-functional against the current `engine/blackjack.py` API
- L21: `from blackjack import Card, Deck` — bare import, will raise `ModuleNotFoundError` (should be `from engine.blackjack import ...`).
- L130, 274, 335: `Deck(1)` — `Deck.__init__` takes no arguments; always builds a single 52-card deck. This raises `TypeError`.
- L288, 348: `self.deck.deal()` — `Deck` has no `deal()` method (dealing is done via `Shoe.deal_card()`). Guaranteed `AttributeError`.
- L334: `self.deck.remaining()` — no such method on `Deck`.
- L293-295, 406-407, 415-429, 435: code accesses `card.value`, `card.is_red`, `card.is_black`, and treats `card.suit` as a string — none of these exist on `Card` (which has `.rank` (enum) / `.suit` (enum), with `.rank.blackjack_value` and `.suit.symbol`).

**This module needs a full alignment pass (or rewrite) against the real `Card`/`Rank`/`Suit`/`Shoe` classes before Busfahrer can run at all.**

### Logic bugs
- `engine/busfahrer.py` `_bus_ride_guess` (L293/295) uses `>=`/`<=`, so an exact tie counts as correct for *both* "higher" and "lower" — a tie can't logically satisfy both. Meanwhile `_check_guess` (L409-417) for Round 2 uses strict `>`/`<`, making a tie unwinnable there. The two phases handle ties inconsistently.
- `engine/busfahrer.py` `_evaluate_round` (L355-398) — when the "everyone got it right" tiebreak re-demotes a winner back to ACTIVE, `winner.guess_correct` stays `True`, leaving a misleading flag for the API/UI.
- `engine/busfahrer.py` `advance_phase` (L172-203) — if called while already in `BUS_RIDE` with `len(remaining) > 1`, it deals another round but never updates `self.phase` (no guard against this state).
- `engine/busfahrer.py` L299 — `card.to_dict()` doesn't exist on `Card`; the `hasattr` fallback always fires and serializes raw enum objects (`rank`/`suit`), which are not JSON-serializable.

### `engine/blackjack.py`
- `Hand.split(self, shoe)` (L203-214) — the `shoe` parameter is never used; either dead code or an incomplete implementation (docstring suggests dealing should happen here).
- `Player.net_losses()` (L257-261) — bakes a drinking-game house rule (blackjack = "2 wins") into the supposedly-standalone `Player` class, mixing concerns that belong in `drinking_rules.py`.
- `RoundManager` insurance handling — two largely duplicated code paths for drinking-mode (group vote, L446-493) vs normal mode (single y/n, L515-526). Candidate for unification behind a shared strategy.

### `engine/referee.py`
- `_get_hand()` (L150-166) — silently appends empty `Hand()` objects until `idx` is in range; a typo like `hand9` quietly creates 8 empty hands and pollutes downstream stats instead of raising an error.
- `cmd_action` "split" (L304-314) — reimplements `Hand.split()`'s split-chain-sharing logic inline instead of calling it; two implementations that must be kept in sync manually.
- `cmd_result` (L369-372) — the blackjack-insurance bonus event fires immediately into `_pending_eor_msgs`, while `on_hand_resolved` is deferred to `cmd_endround`, and (unlike `blackjack.py`'s equivalent path at L696) doesn't pass `hard_switch_dealer` — an inconsistency that could cause the dealer-switch exemption to be missed for this bonus.

### `engine/drinking_rules.py`
- `classify_rule()` (L34-74) — long if/return ladder doing substring matching on human-readable log strings to categorize CSV rows. Any wording change elsewhere silently breaks categorization. High-priority refactor: tag rules with explicit IDs instead of parsing text.
- `_bj_multiplier()` vs the inline `parts` construction in `on_blackjack()` (L17-26 vs ~L202-209) — the suited/A+J/both-black multiplier conditions are computed twice with separate variable names.
- `on_round_end` (L405-514) — ~110-line function doing 5 distinct rule computations; split into named helpers.

### `engine/strategy.py`
- `_BS_PAIR[(5, d)]` (L49) doubles as both the split table and the hard-total fallback for 5-5 — works correctly but is easy to misread without a comment.
- The drinking-mode override for `rv == 5` (L92-102) is partially redundant with the normal `_BS_PAIR` entry for 5-5.
- `d_val = min(dealer_up_card.rank.blackjack_value, 10)` (L88) lumps dealer Ace into the "10" column with no separate Ace column — verify against `docs/Rules.md` that this matches intended basic-strategy deviations.

### Cross-cutting
- `blackjack.py` (~L400-417) and `referee.py` (~L259-271) both fire near-identical `DrinkingRules.handle(...)` card-dealt/blackjack/hand-resolved event sequences — extract a shared helper to avoid drift.

---

## 3. Frontend (`static/js/`)

### High priority
- **`static/js/ui/kpi.js`**: `renderLeaderboard()` (L110-196) and `wrClass()` (L6-11) are fully implemented but never called — `updateKpiPanel` only calls `renderStats`. Either this is dead code that should be removed (along with associated `.lb-*` CSS), or a leaderboard feature was disconnected and needs rewiring.
- **Inconsistent XSS defenses**: only `admin.js`'s `openRulesModal` (L433-437) uses `DOMPurify.sanitize`; everywhere else relies solely on manual `escapeHtml()`. This mostly works for currently-escaped fields, but there's no defense-in-depth — a single missed `escapeHtml()` on a future user-controlled field becomes an XSS vector.

### Bugs
- **`static/js/ui/setup.js` `startGame`** (L409-473) — no `.catch` around the fetch; a network failure throws an uncaught rejection and leaves the Start button permanently disabled with no recovery.
- **`static/js/app.js`** reconnect IIFE (L38-62) — outer `catch (_) {}` silently swallows errors; on failure the user is stuck on the lobby with no message.

### Refactor opportunities
- **`static/js/ui/table.js` `applyState`** (L335-575) is a ~240-line function handling identity sync, toasts, log sync, tab switching, modal sync, and animation dispatch — split into named phases.
- Phase strings (`"pre-deal"`, `"playing"`, `"round-over"`, `"dealer-ready"`) and role strings (`"admin"/"player"/"spectator"/"kicked"`) are repeated as raw literals across `table.js`/`admin.js`/`lobby.js` — centralize into shared constants/enum to avoid typo-driven silent failures.
- Action-button dispatch in `table.js` (`updateActionButtons`, `updateHonorPrompt`) and `admin.js` (L134-146, 171-179) matches buttons by `textContent` ("SPLIT", "DOUBLE", ...) — fragile; use a `data-action-code` attribute instead.
- `admin.js`'s `showBustVoteToast`/`showBustHandoutToast`/`showInsuranceToast` (L621-708) share ~80% identical toast-display boilerplate — extract a shared `_fireToast()` helper.
- `lobby.js`'s `startPolling`, `setup.js`'s `startWaiting`, and the `visibilitychange` handler all reimplement the same fetch-`/state`-then-`applyState` pattern — share a helper.
- `log.js` `appendLog` (L52-71) classifies log lines via substring matching (`includes("drink")`, `"win"`, `"bust"`, etc.) on display text — a player name containing "win" could mis-tag a log entry. Use structured log-entry types from the server instead.
- Inconsistent event-wiring style: `admin.js` mixes `el.onclick = () => ...` with `addEventListener` — pick one convention.
- Magic numbers scattered across `kpi.js` (z-score thresholds), `animation.js` (`CARD_MS = 300` vs CSS `.22s` transitions, which can drift out of sync), and `setup.js` (inline `30_000`/`2000` poll intervals repeated 3x).

### Minor / dead code
- `state.js`'s `currentTurn` (L21) appears to be an unused mirror of `lastState.current_turn`.
- Mixed naming conventions for "module-private" helpers (`_prefixed` vs not) across `kpi.js`/`table.js`.

---

## 4. Entry point, scripts, and config

### `server.py`
- L39: `socket.gethostbyname(socket.gethostname())` to find the LAN IP for the printed "scan this on your phone" URL often returns `127.0.0.1` on Linux/WSL when `/etc/hosts` isn't set up for the hostname — consider the `connect-to-external-then-getsockname()` trick for a reliable LAN IP.
- Binding `0.0.0.0` with `debug=False` and no auth is presumably intentional for a LAN party app — worth a comment so nobody "fixes" it.

### Dependencies
- `requirements.txt` lists `gunicorn`, but `server.py` only ever runs via Flask's dev server (`app.run`) — no `wsgi.py`/Procfile found. Either remove the dependency or document the production entrypoint.
- No version pins on `flask`, `gunicorn`, `tabulate`, `pytest` — given the project has snapshot/benchmark regression tests, an unpinned major-version bump (esp. Flask) could silently break routes.

### `scripts/`
- `load_decision_logs.py` `summarize()` L58 uses `r["player"]` (raises `KeyError` on missing column) while the rest of the file uses `.get()` with defaults — inconsistent error handling.
- `load_decision_logs.py` `write_combined()` L120 — `os.makedirs(os.path.dirname(out_path), exist_ok=True)` throws `FileNotFoundError` if `out_path` has no directory component (e.g. `--out combined.csv`); guard with `if os.path.dirname(out_path):`.
- `rules_sync.py` L39 — `json.load` on `docs/.rules_sync.json` has no try/except; a corrupted file crashes with a raw `JSONDecodeError` instead of a friendly message.
- `simulation.py` — CLI args are parsed into module-level globals (`NUM_PLAYERS`, `NUM_DECKS`, `PLAYER_NAMES`, `CONFIG_KEY`, etc.), but `write_summary`/`write_benchmarks` (L176, 266) read those globals directly rather than parameters passed to `run_simulation()`. Calling `run_simulation(num_players=5, ...)` programmatically and then `write_summary(...)` would silently write under the wrong config key — latent bug for any test/reuse path.
- `play_terminal.py`/`play_referee.py`/`simulation.py` each duplicate: (a) the same 2-line `sys.path` bootstrap, (b) name-normalization (`raw.capitalize()`), and (c) "prompt for int with default/bounds" helpers (`_safe_int`/`_ask_int`/`_yes_no`). Consolidate into a shared `scripts/_cli.py` or make the package installable.
- `play_referee.py` L55 — redundant `.strip()` on an already-stripped variable (harmless, but dead code).
- `play_terminal.py` L71 — `num_npcs += 1` for the synthetic "House" NPC is never read afterward; dead increment.
- `run_all_configs.py` — doesn't de-duplicate overlapping `--players`/`--decks` combinations, which could cause duplicate simulation runs and a snapshot-label collision in `snapshot.py` (L62-64 errors on duplicate labels).
- Hardcoded defaults (`wager=1`, `num_hands=2`) are duplicated across `play_terminal.py`, `simulation.py`, and `app/config.py` rather than imported from one source.

---

## Suggested priority order

1. Fix the four truncated/corrupted files (`payout_tracker.py`, `game_room.py`, `game_commands.py`, missing `apply_milestone_forfeit`) — **the app cannot run without this**.
2. Rewrite/realign `engine/busfahrer.py` against the current `Card`/`Shoe`/`Deck` API — currently non-functional.
3. Standardize name sanitization (`sanitize_name()` everywhere) and the `{"ok": False, "error"/"output"}` response shape.
4. Investigate `kpi.js`'s dead `renderLeaderboard` — restore or remove.
5. Address the refactor items (admin-check helper, `applyState` split, `harvest_drink_log` split, shared toast/poll helpers) as ongoing cleanup.
