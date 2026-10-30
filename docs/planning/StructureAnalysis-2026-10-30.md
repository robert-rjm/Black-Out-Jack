# Structure & Logic Analysis — 30 October 2026

An in-depth look at how the code actually runs: game logic holes, module
dependencies, missing pieces, and what to improve. It complements
[CodeAudit-2026-10-30.md](CodeAudit-2026-10-30.md) (security and route-level
findings N1–N13) and doesn't repeat those findings.

Branch `update/Rob` at `8366759`. Python 3.14, Flask 3.1, pydantic 2.13.

**How the findings were checked.** **Probed** means reproduced against the
real app with the Flask test client (scripts kept outside the repo). The
rest come from reading the code.

## Summary

| # | Severity | Kind | Finding |
|---|---|---|---|
| L1 | High | Logic | The dealer client can add empty "phantom" hands in digital mode, and they are scored as wins or losses · Probed |
| L2 | High | Logic | NEW ROUND throws away open post-round events; a milestone is lost for good · Probed |
| L3 | Medium | Logic | A late milestone claim deletes the milestone without the forfeit |
| L4 | High (local play) | Concurrency | No per-room lock; the threaded dev server can run the dealer twice · Probed |
| L5 | Medium | Logic | Pause is enforced only on `/command`; other routes keep changing state |
| L6 | Low | Logic | Removing a seat leaves a ghost client, and can rotate the deal twice |
| L7 | Low | Logic | A mid-round reshuffle puts cards already on the table back into the shoe |
| L8 | Low | Frontend | The one-slot command queue drops the earlier of two queued commands |
| S1 | High | Structure | Round rules are written three times (simulation, web, referee) |
| S2 | Medium | Dependencies | Hidden import cycles behind function-level imports; the model imports a service |
| S3 | Medium | Structure | `GameRoom` is a ~100-field god object and cross-round cleanup is done by hand |
| S4 | Medium | Structure | The timed-window pattern is copied about 12 times, which is where L2, L3 and L5 come from |
| S5 | Medium | Structure | Auth checks are copied into every route (root cause of audit N4) |
| S6 | Medium | Structure | The engine reports through `print`, which the app captures with a process-wide `redirect_stdout` |
| S7 | Low | Structure | Game progress lives in a GET (`/state` → `tick`) |
| S8 | Medium | Frontend | 26 classic scripts share global state; no JS tests |
| S9 | Medium | Tooling | No CI, unpinned dependencies, ruff not enforced, stale entry-point docstring |
| S10 | Low | Tests | 1030 green tests, but none cover L1–L6; many tests reach into private state |

---

## Part A — Holes in the logic

### L1 — Phantom hands in digital mode · High · Probed

**What happens.** `get_player_hand()` (`engine/blackjack.py:300`) adds empty
`Hand()` objects to reach any label up to `MAX_HAND_INDEX` (20). That is right
for referee mode, where the referee types in hands. In digital mode the
`/command` turn gate (`routes/game_commands.py:200`) checks only the **player
name**, never the hand label. The probe sent `stand Amy hand6` on Amy's turn.
Amy then had 6 hands (`[2, 0, 0, 0, 0, 0]` cards), and at round end all five
empty hands were scored **win** (score 0 against a dealer bust). If the dealer
had stood, they would have scored **loss**, which adds net-loss sips.

**Who can do it.** Whichever client is the dealer, which is an ordinary
player most rounds, so they can rig other players' results. In Normal mode
the phantom hands likely pay out from the bankroll without a stake (not
verified).

**Fix.** In digital mode, reject any label outside `player.hands`: add
`get_player_hand(..., create=False)` and use it in every digital handler and
in `/preselect`, `/suggest_action` and `/respond_suggest`. Add a test that
`stand X hand6` leaves `len(hands)` unchanged.

### L2 — NEW ROUND discards open post-round events · High · Probed

**What happens.** `cmd_newround` → `reset_round_state()`
(`services/room_manager.py:83`) replaces `RoundState` wholesale. Before that
it settles exactly one open event, the comeback handout
(`apply_l_handout_forfeit(force=True)`). Everything else open at that moment
silently disappears:

| Open event | What is lost |
|---|---|
| Milestone handout (`_pending_milestone`) | **Probed:** pending → `None`, nobody drinks, and the boundary stays in `milestones_claimed`, so that milestone never fires again |
| Bust-vote handout window | The winners' unassigned sips |
| Dealer Lottery entry / reveal / handout | The draw or its handouts (handouts cleared explicitly in `reset_round_state`) |
| Targeted Drinking mini-round | The frontend warns (`log.js:186`), the server doesn't care |
| Targeted perfect-graduation handout | Cleared explicitly |

The server never refuses `newround`, and the dealer's NEW ROUND button stays
on screen while these windows are open.

**Fix.** Give every post-round feature a `settle(session)` hook (forfeit
rules exactly as when its window expires) and call them all, in order, at the
top of `cmd_newround`, the same way the comeback handout already works. Or
refuse `newround` while any window is open (an "N things still open" error),
with an admin override. S4 makes either option easy.

### L3 — Late milestone claim deletes the milestone · Medium

`/claim_milestone` (`routes/admin.py:252`) handles an expired window like
this: `session.round._pending_milestone = None` → error. It doesn't apply the
forfeit penalty, doesn't log anything, and doesn't run
`check_and_set_milestone`. `apply_milestone_forfeit` would have charged the
winner the full handout. Without a pause, a claim has to land between the
expiry and the next `/state` poll (about a second). With a pause (L5) it is
deterministic: pause with 10 s left, wait 30 s, submit. The winner escapes the
forfeit and the milestone disappears. **Fix:** on expiry, call
`apply_milestone_forfeit(session)` and return its result.

### L4 — No per-room lock: the dealer can run twice · High for local play · Probed

**What happens.** `server.py` runs `app.run(...)`, and Flask's dev server is
**threaded** by default. That is the documented way to play ("open on any
phone on the same WiFi"). Production uses `gunicorn --threads 1`, so it is
safe today. Every `/state` poll runs `tick()`, and `_run_deferred_dealer_play`
(`services/tick.py:54`) checks `round_phase == "dealer-ready"` and only then
acts. Nothing stops a second thread in between. The probe ran six polls
together at dealer-ready: the dealer sequence (`dealer_turn` + `cmd_endround`
+ end-round pipeline) ran more than once in **20 of 20** trials. The timing
window was widened with short sleeps, so real play hits it less often, but
nothing prevents it. Results: double dealer hits, drinks fired twice,
bankrolls paid twice.

On top of that, `contextlib.redirect_stdout` (used in `/command`, `tick` and
`capture()`) swaps the **process-wide** `sys.stdout`. Concurrent requests
capture each other's output, and an unlucky restore order can leave
`sys.stdout` pointing at a dead buffer.

`_registry_lock` only protects the seat registry. The comment in `GameRoom`
says it is "not used for other GameRoom fields".

**Fix (cheap and complete).** Give each room one `RLock`. Take it in a
`before_request`/decorator around every route that loads a room, including
`/state`, since `tick` changes state. Then drop `_registry_lock`. Until that
lands, set `threaded=False` in `server.py`. Longer term, S6 removes the stdout
problem.

### L5 — Pause only half applies · Medium

`tick()` is skipped while paused, and `/command` is refused
(`game_commands.py:185`). Every other mutating route still works: Wild Card,
bust votes, handouts, lottery entries, rule votes, kicks, drink-rate votes.
Routes that check a deadline compare with **unshifted** deadlines (they are
only shifted on resume), so after a long pause a still-open vote is refused
as "closed". Routes without a deadline check (`/give_bust_sip`,
`/l_handout/give`) go through. The list of deadline fields that `resume_game`
shifts (`services/pause.py:15`) is maintained by hand. Today it covers every
`expires_at` on `RoundState` and `GameRoom`, but nothing guarantees a new
feature adds itself.

**Fix.** Decide the rule ("paused = read-only"), then enforce it in the
per-room decorator from L4 with a small allow-list (`/set_paused`, `/state`,
`/leave_room`). Add a test that walks `RoundState`/`GameRoom` fields named
`*_expires_at` / `*_deadline` and dicts with `expires_at`, and fails when
`pause.py` doesn't cover one.

### L6 — Removing a seat · Low

- `apply_queued_settings` (`room_manager.py:216`) removes the player and prunes
  only the **admin's** `local_names`. A remote client holding that seat keeps
  `name = "Amy"` and `role = "player"` for a seat that no longer exists. Routes
  that trust `info["name"]` (bust vote, wild card) then act for a ghost: the
  bust vote, for example, writes `_bust_votes["Amy"]`. Set that client to
  spectator.
- When the leaving player is the dealer, the removal loop rotates the deal.
  `cmd_newround` worked out `rotate` before that, and rotates **again** when
  auto-rotation is due, which skips a seat. Recompute `rotate` after
  `apply_queued_settings`, or skip the second rotation if the dealer already
  changed.

### L7 — Mid-round reshuffle duplicates cards · Low

`Shoe.deal_card()` (`engine/blackjack.py:145`) calls `reset()` when the shoe
runs low mid-deal. That rebuilds all decks, including cards that are on the
table right now, so the same card can show up twice in one round. Real
casinos finish the round with the cut card. **Fix:** reshuffle only the
discards (keep the cards in play out of the new shoe), or keep the reserve big
enough that a reshuffle only ever happens between rounds.

### L8 — Command queue drops intent · Low

`state.js` keeps one `_pendingCmd` ("last intent wins"). Two quick taps while
a request is in flight (STAND on hand 1, then HIT on hand 2) drop the first.
A queued command can also be replayed after the state has changed (the server
rejects it, so nothing breaks, but the user sees an error toast). Use a FIFO
queue, or disable the action buttons while a request is in flight.

---

## Part B — Structure and dependencies

### Module map (as built)

```
routes/*  ──►  services/*  ──►  models/game_room  ──►  engine/*
   │              │  ▲                   │
   │              │  └─ serializers/*    └─(lazy)─► services/room_manager   ✗ upward
   └─ _auth       └─ tick / round_pipeline / session_store
```

Measured with an AST pass over `app/` and `engine/`. **No import cycles at
module level**, `engine` never imports `app`, and no route imports another
route (except the shared `commands/common.py`). The layering is basically
healthy. The problems hide behind **function-level imports**, which exist to
break cycles:

| Hidden cycle | Where |
|---|---|
| `models.game_room` → `services.room_manager` (`NullTracker`) | The only upward import; a model depends on a service |
| `services.room_manager` ↔ `services.drink_rate` | `reset_round_state` |
| `services.serializer` ↔ `dealer_lottery`, `payout_tracker` | Inside `serialize_state` |
| `services.stats` → `payout_tracker`, `serializers.*` → `afk`, `drink_rate` | Same reason |
| `services.boj_switch` → `room_factory` | Table split |
| `engine.blackjack` ↔ `engine.events` / `drinking_rules` / `style_strategy` | `RoundManager`, `NPC_Player` |

### S1 — Round rules exist three times · High

| Copy | Used by | Lines |
|---|---|---|
| `engine.blackjack.RoundManager` (`_dealer_turn`, `_evaluate`, `_round_end_drinks`) | `scripts/simulation.py` (the preset "≈ sips/round" numbers and the regression snapshots), `scripts/play_terminal.py` | ~450 |
| `app.services.game_engine` (`dealer_turn`, switch detection, pass-1/2 evaluation) | The web app, digital mode | ~730 |
| `engine.referee.RefereeSession` (`cmd_result`, `cmd_endround`) | The web app, referee mode | ~840 |

All three repeat "dealer hits to 17", hand comparison, hard/soft switch
detection, insurance handling and the end-of-round drink order. The drinking
*rules* are shared (`DrinkingRules.handle`), but deciding *when* and with
*what* to call them is not. Consequences:
- The simulation measures the engine copy, so the preset sip numbers and the
  snapshot tests don't prove anything about the web flow.
- Fixes land in one copy only: the referee Blackjack double bonus (audit N2/B1)
  and the referee `split_ace_bj` gap (G4) were both copy drift.

**Improve.** Pull the pure parts into `engine/round_logic.py`:
`play_dealer(hand, draw)`, `evaluate(hands, dealer_hand)`,
`detect_switch(results, insured_bj)` and `end_of_round_events(...) -> [Event]`.
Have all three call them. Then run the 100k-round simulation through the
**app** path too (the earlier audit already noted this was missing).

### S2 — Dependency fixes · Medium

- Move `NullTracker` into `engine/drinking_rules.py` (next to `DrinkTracker`,
  the protocol it mirrors) and remove the upward import.
- Most service cycles exist because `serialize_state` and `reset_round_state`
  know every feature. With per-feature modules (S3/S4), each feature exposes
  `serialize(session, client)` and `reset(session)`, and the serializer and
  `reset_round_state` just walk a registry. The cycles disappear.

### S3 — `GameRoom` god object · Medium

`GameRoom` (`app/models/game_room.py`) has about 100 fields across `GameRoom`,
`RoundState`, `DrinkLedger`, `SessionStats` and `GameConfig`, most of them
`_private` but read and written from routes and services everywhere.
Replacing `RoundState` wholesale was a good call (nothing can be forgotten at
newround), but it caused L2, and `reset_round_state` already carries two
hand-written patches for state that lives across rounds (the
`pending_handouts` clearing).

**Improve.** One state object per feature (`MilestoneState`,
`DealerLotteryState`, `TargetedDrinkingState`, `RuleVoteState`, `BojState`,
`DrinkRateState`), each owning its round-scoped and session-scoped fields
plus `settle()` / `reset()`. `GameRoom` becomes a container plus the seat
registry. This is also the precondition for persistence (Part D): one feature
= one serialisable block.

### S4 — The timed window is copied everywhere · Medium

About 12 features hand-roll the same lifecycle: write `expires_at`, check it
in a `tick` forfeit, shift it in `pause.py`, compute `seconds_left` in a
serializer, compare it again in the route, and (sometimes) settle it at
newround. Each copy decides these differently, and L2, L3 and L5 are three
examples of that. **Improve:** one `TimedWindow` helper (`open(seconds)`,
`is_open(now)`, `seconds_left`, `shift(delta)`, `on_expire` callback) plus a
registry the tick, pause, serializer and newround all iterate. New features
then get the right behaviour for free.

### S5 — Auth copied into every route · Medium

Most of the 78 routes start with the same block: parse `room_code` /
`client_id`, look up the session, read `_room_clients`, check role, kicked
flag and seat. They have drifted (audit N4: kicked checks; N8: `None` names;
`escape()` used in some places and not others). **Improve:** decorators such
as `@room_route(require="seated" | "dealer" | "admin")` that inject
`(session, client)` and also take the per-room lock (L4) and enforce the pause
rule (L5). A typed request model per route (pydantic is already a
dependency) replaces the hand-written `.get()` / `int()` parsing.

### S6 — The engine reports through `print` · Medium

`engine/referee.py` and `engine/blackjack.py` report through `print()`
(`tabulate` tables, log lines). The app captures that with
`contextlib.redirect_stdout` into the round log, and swaps in the web
handout with `patch_tracker()` (monkey-patching `tracker._handle_handout`).
The engine is a CLI program that the web app wraps. Problems:
- `redirect_stdout` is process-wide (L4).
- Log text works as an API: the round log is built from captured prints, so
  changing a message's wording changes what players see, and tests that
  check output text break.
- Monkey-patching hides the real handout behaviour from readers and type
  checkers.

**Improve.** The engine returns events (`list[Event]`, already partly there
in `engine/events.py`), and a renderer turns them into text for the terminal
or the round log. Pass the handout strategy in through the constructor
instead of patching it.

### S7 — Game progress lives in a GET · Low

`/state` runs `tick()`, which forfeits windows, auto-plays bots and runs the
dealer. A GET changes state, nothing moves unless someone polls, and every
poll from every phone repeats the work (cheap today: `serialize_state` takes
about 0.7 ms for 6 seats). Fine for this scale. With L4's lock it is also
safe. Revisit together with persistence and SSE (Part D).

### S8 — Frontend structure · Medium

- 26 classic `<script>` files concatenated into one bundle by
  `asset_bundler.py` (the list matches the files on disk, checked), all
  sharing about 30 globals from `state.js`. Load order is the only module
  system.
- The big files: `table-modals.js` 1,948 lines, `drink-panels.js` 1,158,
  `table.js` 1,173, `admin-settings.js` 900. Almost every UI render is a
  full-panel `innerHTML` rebuild per poll.
- **No JavaScript tests at all.** Every frontend rule (e.g. the L-handout
  `_blocked` list, the newround confirm) is checked only by hand.
- Game decisions still leak into the client: the newround warning lives only
  in `log.js`, and `_blocked()` in `drink-panels.js` repeats the server's
  ordering of post-round modals. If the server sent one
  `post_round_queue: ["milestone", "bust_handout", …]` list, the client
  would only render it.

**Improve.** ES modules (no bundler needed: `<script type="module">` works
everywhere the app runs), one module per panel exporting `render(state)`,
`state.js` as one store object. Add a small Vitest or Playwright smoke suite
for the lobby → round → round-over flow. `FileRefactor.md` E1–E4 already
plans the file splits.

### S9 — Tooling and project hygiene · Medium

- **No CI** (`.github/` doesn't exist). The 1030 tests and ruff run only when
  someone remembers.
- `requirements.txt` has no versions (Flask 3.1.3 and pydantic 2.13.4 are
  installed locally). Pin them, or add a lock file.
- `ruff`: 37 errors on `main`. Add it to CI so the count can't grow.
- The `server.py` docstring is out of date: it lists `/register` and
  `/preselect` under `polling.py` and `/export_csv` under `reports.py`, all of
  which moved or were renamed.
- `pyproject.toml` has only tool config. No project metadata, no Python
  version, no dependency list. One source of truth for dependencies would
  help.

### S10 — Tests · Low

The suite is large and green (1030 passed, 57 s) and has strong pieces: the
registry-driven rule-gate coverage test and the AST check for missing
`rules=` arguments. Gaps:
- None of L1–L6 is covered, and there is no test that runs two requests at
  once.
- Many tests set and assert private fields (`room.round._…`) instead of going
  through routes. They break on every refactor, which makes S3/S4 more
  expensive (also `ImplementationImprovements.md` #13).
- The simulation snapshots cover only the engine copy (S1).

---

## Part C — Missing pieces

| Piece | State |
|---|---|
| Digital `blackjack` command | `_cmd_blackjack` exists (`commands/digital.py:309`) but isn't in `DIGITAL_COMMANDS`. Either wire it up or delete it |
| G5: Normal mode ruleset | Normal (casino) mode still runs on the drinking table rules |
| Rule Toggles Phase 5 | xlsx RULES sheet, share codes, "save my house rules", quiz hooks, Normal→Drinking lands on Starter |
| Per-room lock | Only `_registry_lock` exists (L4) |
| Settle-on-newround for every post-round event | Only the comeback handout has it (L2) |
| Persistence | All rooms live in memory; a restart ends every game (audit P1) |
| Health check / monitoring | No `/healthz`, no error tracking (audit P4) |
| CI pipeline | None (S9) |
| Privacy policy page | Only Terms (audit P8) |
| Frontend tests | None (S8) |

---

## Part D — What could and should be improved

**Should, soon (correctness):**
1. **L4 per-room lock** (plus `threaded=False` as a stop-gap). It is small,
   and it removes a whole class of double-fire bugs in local play.
2. **L1:** in digital mode, reject hand labels that don't exist.
3. **L2 + L3:** settle (or block) open post-round events at newround, and send
   late claims through the forfeit.
4. Audit N1–N6 (server freeze, path traversal, kicked clients, room takeover).

**Should, next (structure that stops the bugs coming back):**
5. **S5:** a `@room_route` decorator (auth, lock, pause rule, typed body).
6. **S4:** a `TimedWindow` helper and registry, which also makes the L5 pause
   rule simple.
7. **S1:** shared `engine/round_logic.py`, and run the simulation through the
   app path.
8. **S9:** a CI workflow (pytest + ruff) and pinned dependencies.

**Could, later (bigger investments):**
9. **S3:** a state object per feature, then persistence (SQLite or Redis
   snapshot per room) and more workers. That unlocks SSE instead of polling.
10. **S6:** an event-returning engine with no stdout capture.
11. **S8:** ES modules, a store object, and a frontend smoke-test suite.

Items 5–7 overlap with `ImplementationImprovements.md` (#3, #6, #7, #8) and
`FileRefactor.md` (D, E). When this plan is picked up, link those docs here
rather than tracking the same work in three places.
