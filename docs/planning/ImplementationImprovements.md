# Implementation Improvements

Findings from a "what would we do differently if we restarted" review. These cover the **implementation**, not the game rules. Based on a sampled read of the structure, session store, polling/tick, room manager and JS layout, not a full audit.

Items are ordered roughly by impact. Each has: **Finding**, **Description**, **How to fix**.

---

## Architecture

### 1. In-memory state pins deployment to one worker
**Description:** `app/services/session_store.py` keeps all rooms in module-level dicts, and the `Procfile` runs `gunicorn --workers 1 --threads 1`. A restart or deploy wipes every live game, and the app cannot scale past one process.

**How to fix:** Add a persistence layer, such as SQLite or Redis, holding a serialized room snapshot. Write after each command and load on demand. Rooms then survive restarts and can run on several workers. Keep the dict as a cache in front of it if latency matters.

### 2. Polling with side effects (`tick`) drives the game loop
**Description:** Every `/state` poll runs `tick(session)` (`app/services/tick.py`), which advances timers, applies forfeits and runs the dealer. A GET mutates state, game progress depends on someone polling, and two simultaneous polls can trigger the same transition.

**How to fix:** Make `/state` a pure read. Move timed transitions to a scheduler or to deadline checks run inside the command path. Optionally push updates over SSE or WebSocket instead of polling.

### 3. Concurrency protection is thin
**Description:** Only the client registry has a lock (`_registry_lock`, used in `app/routes/polling.py`). Game commands, votes and handouts rely on the single-thread gunicorn setting. Changing that setting makes double-award races (for example `/dealer_lottery/give_sip`) real.

**How to fix:** Use one lock per room, or a single command queue per room, and run every mutating route through it. Add a test that fires concurrent requests at the same room.

### 4. The engine was written for a terminal and adapted for the web
**Description:** The engine prints to stdout, and the web layer swallows it with `capture()` and `redirect_stdout(io.StringIO())`. `patch_tracker` monkey-patches `tracker._handle_handout` to avoid a blocking prompt. Commands such as `cmd_deal(parts)` and `cmd_action(parts)` take string tokens.

**How to fix:** Refactor `engine/` into a pure core that takes typed commands and returns typed events, with no I/O. The CLI and the web become thin adapters. Interactive prompts become an injected strategy or callback. The stdout capture and monkey-patching can then be deleted.

---

## Code structure

### 5. `GameRoom` is a god object with a large compatibility façade
**Description:** `app/models/game_room.py` has about 60 trivial property getters and setters that delegate to `config`, `round` or `ledger` (`mode`, `wager`, `_ace_clubs_flag`, `_god_mode`, and so on). There are also roughly 318 references to underscored `session._...` attributes from outside the class, including `_require_admin` reading `session._room_clients`.

**How to fix:** Migrate callers to `room.config.x`, `room.round.x` and `room.ledger.x`, then delete the delegating properties. Expose public methods for the few private fields that routes genuinely need.

### 6. Oversized files with repeated subgame patterns
**Description:** Large files include `serializer.py` (~1,170 lines), `polling.py` (~1,080), `drink_tracker.py` (~960), `admin.py` (~920), `game_commands.py` (~900) and `drinking_rules.py` (~900). `polling.py` also holds the lottery, targeted-drinking, bust-vote and insurance endpoints. Each subgame repeats the same shape: start trigger, vote window, forfeit on timeout, handout, give-sip route.

**How to fix:** Split routes by feature, with one blueprint per subgame. Extract a shared "timed phase" abstraction (open, collect, forfeit, resolve) and implement the subgames on it. This also shrinks the per-subgame forfeit functions that `tick` calls.

### 7. Round phase is derived on demand from many flags
**Description:** `round_phase()` computes a string from many fields in `RoundState`, so impossible flag combinations can exist and transitions are implicit.

**How to fix:** Store an explicit phase enum on `RoundState` with a table of allowed transitions. Reject commands that are invalid for the current phase in one place.

---

## API and security

### 8. Ad hoc request validation
**Description:** About 46 handlers use `request.json or {}` and parse fields by hand. Room and client lookups are repeated through `_require_admin` and `_require_host_or_dealer`. Pydantic is a dependency but only used for outbound state (`state_schema.py`).

**How to fix:** Define Pydantic request models per route. Add a decorator that resolves room, client and role and passes validated objects to the handler, returning a consistent error shape.

### 9. `client_id` is the only credential
**Description:** Authorization trusts a client-supplied `client_id`. Anyone who learns the admin's ID is the admin. Acceptable for a party game, but cheap to harden.

**How to fix:** Issue a server-generated secret (httpOnly cookie or signed token) at join time and verify it on every request. Keep `client_id` as a public identifier only.

---

## Frontend

### 10. No module system; very large JS files
**Description:** Shared globals live in `state.js` (`pollTimer`, `_disconnectedTimer`) and a custom `asset_bundler.py` concatenates files into `bundle.js`, so load order matters. Large files include `admin.js` (~1,730 lines), `table-modals.js` (~1,360), `admin-settings.js` (~1,080) and `table.js` (~1,070). `marked.min.js` and `purify.min.js` are vendored.

**How to fix:** Convert to ES modules and use a standard bundler (Vite or esbuild). Install `marked` and `dompurify` as packages. Split the big UI files by feature. Consider a small reactive library for table and modal rendering.

### 11. Full-state polling on every request
**Description:** The client re-fetches and re-renders the full serialized state each poll, which costs bandwidth and server CPU.

**How to fix:** Add a state version counter and return "unchanged" (304 or a small payload) when it matches. Better, push deltas over SSE or WebSocket. Make the UI diff against the previous state before rendering.

---

## Data, tests and tooling

### 12. Generated and data artifacts committed to the repo
**Description:** `scripts/snapshots/` holds 20+ near-identical 441-line `benchmarks.json` files with baseline and dated copies per config. `data/decisions/*.xlsx`, `data/profile_backups` and large `engine/player_profiles/*.json` files are tracked. `static/js/bundle.js` is generated at startup.

**How to fix:** Keep one baseline per config in the repo, and store dated runs as CI artifacts or in external storage. Move decision logs out of git. Generate the bundle in a build step rather than at app startup.

### 13. Tests mirror the monolith and depend on private state
**Description:** `test_targeted_drinking.py` is ~2,160 lines and `test_dealer_lottery.py` ~1,110. Tests reach into private attributes and heavy fixtures, which makes refactors expensive.

**How to fix:** Once the engine is pure (item 4), write table-driven rule tests that need no Flask and no room. Keep a thinner set of route-level integration tests. Prefer public APIs in assertions.

### 14. Rules live in several places
**Description:** `docs/.rules_sync.json`, `scripts/rules_sync.py`, `scripts/terms_sync.py` and doc-sync tests exist because drink amounts, multipliers and triggers are duplicated across engine constants, docs and UI text.

**How to fix:** Keep one machine-readable rules spec (for example `rules.yaml`) and generate the engine constants, docs and UI strings from it. Drop the sync scripts and tests that become redundant.

### 15. Smaller items
**Description:** `NullTracker` is a duck-typed stand-in rather than a declared interface. Rate-limit and cleanup state (`_join_attempts`, `_last_cleanup`) are module globals that reset on restart. Player profiles are read and written as ad hoc JSON in several places.

**How to fix:** Define a `Tracker` protocol with real and no-op implementations. Move rate-limit state into the same store as rooms (or use a rate-limit library). Put profile reads and writes behind one repository module.

---

## Suggested priority

If only three get done: **(4)** a pure, typed engine with no stdout, **(2)** an explicit phase state machine so GET requests don't mutate state, and **(10)** ES modules with a standard bundler.

---

## Implementation checklist

Nothing here has been implemented yet. Tick items as they land.

- [ ] 1. Persistent room storage / multi-worker support
- [ ] 2. `/state` is a pure read; timed transitions moved out of `tick`
- [ ] 3. Per-room locking or command queue
- [ ] 4. Pure typed engine, no stdout capture or monkey-patching
- [ ] 5. `GameRoom` façade properties removed; no external private access
- [ ] 6. Large files split by feature; shared timed-phase abstraction
- [ ] 7. Explicit phase enum with allowed transitions
- [ ] 8. Typed request models and a room/client/role decorator
- [ ] 9. Server-issued credential instead of bare `client_id`
- [ ] 10. ES modules and a standard bundler
- [ ] 11. Versioned or push-based state updates
- [ ] 12. Snapshots, decision logs and generated bundle removed from git
- [ ] 13. Table-driven engine tests; fewer private-state tests
- [ ] 14. Single machine-readable rules spec
- [ ] 15. Tracker protocol, rate-limit state and profile repository cleanup
