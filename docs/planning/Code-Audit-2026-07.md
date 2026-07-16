# Code Audit — July 2026

> Fresh audit of the codebase, a status reconciliation of `Improvements.md`
> against current code, and a review of `Busfahrer-Plan.md`'s readiness.
> All findings below were independently spot-checked against the source
> (file:line) before being written down — this is not an unverified agent
> dump.

## Hosting context: Render free tier

This shapes which findings actually matter in production:

- The single web instance spins down after ~15 min idle and cold-starts in
  30-50s on the next request.
- **Ephemeral filesystem** — anything written to local disk is lost on every
  restart/redeploy.
- ~512MB RAM ceiling, shared CPU, one instance — no horizontal scaling.
- Free-tier idle HTTP connections get cut early, which is why SSE/websockets
  aren't viable here (already correctly called out in `Improvements.md`).
- All game state lives in one process's memory (`game_sessions` dict) — a
  restart wipes every active room. This makes **in-process concurrency and
  unbounded memory growth** the two risk categories that matter most, more
  than they would on a beefier always-on host.

---

## Part 1 — Fresh findings

Ranked by severity: correctness/money bugs first, then crash risks, then
deployment/concurrency risks, then memory, then perf/security/tests.

### 1. Bust-vote side-bet payout uses a different bet size than was deducted (money bug) — **confirmed**
- **Deduct side (vote time):** [`app/routes/polling.py:642`](../../app/routes/polling.py#L642) — `side_bet = _pbets.get(voter_name, session.bet_amount) / 2`, i.e. respects each player's **own custom bet** if they set one via `/set_player_bet`.
- **Settle side (round end):** [`app/services/drink_tracker.py:149`](../../app/services/drink_tracker.py#L149) — `side_bet_amount = session.bet_amount / 2`, using only the **table-wide global bet**, with no per-player lookup.
- [`app/services/payout_tracker.py:124-138`](../../app/services/payout_tracker.py#L124) then pays every winner/loser using that single global `side_bet_amount` for everyone.
- **Trigger:** any Normal-mode room where a player sets a custom per-hand bet different from the table default, then bets bust. The dollar amount withdrawn from their bankroll at vote time won't match what they're paid/charged at settlement — silently leaking or destroying bankroll balance.
- **Fix direction:** `apply_bust_vote_penalties` should look up each winner/loser's own `_pbets` entry (same fallback pattern already used at the deduct site) instead of a single table-wide figure, and `payout_tracker.py` should read a per-player stake rather than one shared `side_bet_amount`.
- **Test gap:** `tests/app/test_payout_tracker.py` has no `side_bet` coverage at all.

### 2. Dealer Lottery replay can exhaust its deck and crash (`IndexError`) — **plausible, unverified by simulation**
- [`app/services/dealer_lottery.py:200-203`](../../app/services/dealer_lottery.py#L200) deals from one fresh 52-card `Deck()`, shared across up to 10 hands (2 starting hands × up to 5-way re-split each, per the file's own docstring at lines 125-134).
- [`_deal_and_resolve_hand`](../../app/services/dealer_lottery.py#L125) (lines 138, 143) pops from that same deck for every second-card deal and every hit-to-17 draw, with **no check that the deck has cards left** before popping.
- **Trigger:** a long run of re-splits combined with several hands each needing many low-card hits to reach 17 can plausibly exceed 52 draws (e.g. 10 hands × ~6-7 low hits each ≈ 60-70 pops). Not simulated to confirm actual probability, but the code path has no guard, so it's a real latent crash risk, not just a style nit.
- **Blast radius:** `resolve_dealer_lottery()` is called both from the player-facing entry route and from **every `/state` poll** via `apply_dealer_lottery_entry_forfeit()` — an unhandled `IndexError` here would 500 the poll endpoint for the whole room, not just one request.
- **Fix direction:** either reshuffle-in-place when the deck runs low (simplest — the existing shoe's `Deck` likely already supports this pattern) or build the lottery's deck from 2+ standard decks up front to guarantee headroom for the worst case.
- **Test gap:** `tests/app/test_dealer_lottery.py` exists but should be checked for (and given, if missing) a forced-re-split case that exercises deck depth.

### 3. No process-model guarantee that Render runs a single worker — **deployment risk, unverifiable from repo alone**
- `app/services/session_store.py` keeps `game_sessions` as a plain module-level dict. Grep for `threading.Lock`/`RLock` across `app/` returns zero hits — there is no locking anywhere.
- `requirements.txt` lists `gunicorn`, but there is **no `Procfile` or `render.yaml`** committed, so the actual start command (worker/thread count) lives only in the Render dashboard, outside this repo.
- **Risk:** if the Render start command ever uses more than one gunicorn worker (a common default suggestion elsewhere), each worker is a separate process with its **own copy** of `game_sessions` — players would round-robin across workers and see their room vanish/reappear or desync entirely, since there is no shared store (e.g. Redis) backing the session dict.
- **Action (not a code fix):** confirm the Render dashboard start command is pinned to `--workers 1` (a `--threads N` value is fine — same process, shared memory). Consider committing a `Procfile` (`web: gunicorn --workers 1 --threads 4 server:app` or equivalent) so this is enforced in-repo rather than only in dashboard config that can drift.

### 4. Read-modify-write races on shared registration/seat-transfer lists — **plausible, needs threaded test to fully confirm**
- [`app/routes/polling.py:118-127, 160-161`](../../app/routes/polling.py#L118) and the equivalent approval path in [`app/routes/admin.py:341-350`](../../app/routes/admin.py#L341) follow a check-then-append pattern with no atomicity.
- **Trigger:** two concurrent `/register` calls for the same seat name (or two admins approving the same pending registration) can both pass the "not already claimed" check before either write lands — only exploitable if gunicorn/Flask is running with real thread concurrency (ties back to finding #3's open question about the actual deployment config).
- **Fix direction:** a single `threading.Lock` per `GameRoom` (or one global lock, given traffic is low) around registration/approval mutations would close this cheaply.

### 5. Three session-lifetime lists grow with no cap or rotation — **confirmed pattern, real but slow-burn**
- [`session.drinks.csv_rows`](../../app/models/game_room.py#L157) (appended on every sip event via `award_sips`), `session._decision_log`, and `session._dealer_lottery_decision_log` (`decision_log.py:110, 162`) all accumulate for the entire session lifetime.
- `session_store.py` allows sessions to live up to `ACTIVE_SESSION_TTL = 24h` of continuous play — a long, heavily-played room could accumulate tens of thousands of dict rows.
- **Given the 512MB Render ceiling** with potentially several concurrently active rooms, this is worth capping (keep last N rounds, or drop verbose per-decision fields like `visible_cards`/`hand_cards_before` once a round is exported) even though it's a slow-burn risk rather than an acute one.
- Session cleanup itself (`cleanup_stale_sessions()`) was checked and is fine — it runs on every `reserve_room()` and hourly from `/state`, so abandoned rooms don't leak indefinitely.

### 6. Every `/state` poll fully rebuilds and re-validates the entire snapshot — **confirmed, currently low-cost but worth flagging**
- [`serialize_state()`](../../app/services/serializer.py#L625) recomputes `play_order`, walks every player's drink log, rebuilds `compute_kpi_stats` (itself O(players) with several passes), and finally runs the whole dict through Pydantic's `AppState(**state).model_dump()` — a full validation pass — **on every poll, from every client, even when nothing changed**.
- There's no `state_seq`-gated short-circuit to skip re-serialization when state hasn't mutated since a client's last poll.
- At current table sizes (a handful of players) this is fine on Render's shared CPU, but it's the first thing to optimize if poll frequency or table size ever grows — cache the serialized dict, keyed by `state_seq`, and only rebuild when it changes.

### 7. Ephemeral disk — checked, no issue found
`/export_xlsx` and `/export_decisions` build workbooks entirely in an in-memory `io.BytesIO()` buffer and stream them straight back as the HTTP response ([`app/routes/reports.py:115-367`](../../app/routes/reports.py#L115)) — nothing touches local disk. This is a deliberate, correct design given Render's ephemeral filesystem, not an oversight. No action needed.

### 8. Frontend injection/XSS — checked, no issue found
Player-derived strings going into `onclick=` or `innerHTML` are either passed through `escapeHtml()` or attached via `dataset` rather than string-interpolated. Server-side, `sanitize_name()` ([`app/services/validators.py:27-43`](../../app/services/validators.py#L27)) strips `<>"'`\`` and bidi-control characters before a name is ever stored, so even a missed frontend escape site has limited exploitability. The `Improvements.md` FC-1 apostrophe-injection *code-smell* (building `onclick=` as strings at all) is still real as an architectural fragility — see Part 2, item 7 — but it is not currently an exploitable bug.

### 9. Admin-route auth — checked, no gaps found
Every admin-only route funnels through `_require_admin()` before mutating anything; no route was found that should gate on admin/seat-ownership but doesn't.

### 10. `client_id` is an unauthenticated bearer token — accepted tradeoff, worth documenting explicitly
Client-generated UUID, sent as a plain param, with no further proof of identity. Reasonable for a casual party game with no accounts, but anyone who obtains another player's `client_id` (e.g. inspecting traffic on a shared device) can act as them. Not a fix-it item — just worth writing down so it isn't rediscovered as a "vulnerability" later.

---

## Part 2 — `Improvements.md` status reconciliation

Each item was independently re-verified against current code rather than trusting the doc's own status label.

| # | Item | Doc's claimed status | **Verified status** | Evidence |
|---|---|---|---|---|
| 1 | `award_sips()` helper | DONE | **Confirmed done** | `drink_tracker.py:36` defines it; grep for the four raw accumulator names outside that file returns zero hits — no bypass writers remain. |
| 2 | SSE instead of polling | Blocked on Render | **Confirmed still accurate** | No `EventSource`/`text/event-stream` anywhere; frontend still polls `/state` on a timer. |
| 3 | Backend-first API | DONE | **Confirmed done** (spot check) | No score/arithmetic patterns found in `static/js/`. |
| 4 | Pydantic serialization | DONE | **Confirmed done** | `state_schema.py:340` defines `AppState`; `serializer.py:946` returns `AppState(**state).model_dump()` — actually constructed and validated, not just imported. |
| 5 | Unified game engine (merge referee + digital) | Large effort, not started | **STALE — needs rewrite, not just a status flip** | `app/services/game_engine.py` (626 lines) exists but is **not** the merge described — its own docstring says it's digital-path logic extracted out of `game_commands.py`. `engine/referee.py`'s `RefereeSession` is still a fully separate parallel implementation with its own `cmd_deal/cmd_action/...`, and does not call into `game_engine.py`. `game_commands.py` dispatches to **both** depending on mode. Real progress happened (digital logic is now its own testable module instead of living inline in the route file) but the actual merge — one engine, two thin adapters — has not happened. |
| 6 | Decompose `GameRoom` | DONE | **Confirmed done** | `game_room.py` defines `DrinkLedger`/`SessionStats`/`GameConfig` and `GameRoom.drinks/.stats/.config`; old flat drink-ledger shims are gone. (Minor: `GameConfig`-related backward-compat properties like `.mode`/`.drinking_mode` still exist as shims — not a contradiction of the doc's specific claim, just a residual detail.) |
| 7 | Frontend component architecture | Low urgency, not started | **Confirmed still accurate** | No component framework; 14 inline `onclick="..."` handlers remain across `admin.js`, `kpi.js`, `lobby.js`, `table.js`, `trivia.js` — the FC-1 fragility is still live (see Part 1, item 8). |
| 8 | Test directory split | DONE | **Confirmed done** | `tests/engine/` and `tests/app/` exist with the described split, plus `tests/conftest.py` and per-directory conftests. |

**Action needed on the doc itself:** update item 5's status line and the summary table row — the current text ("Large effort... not started") undersells what actually happened (digital-path extraction) and oversells what's still missing (the actual merge), which matters directly for the Busfahrer decision in Part 3.

---

## Part 3 — Busfahrer readiness

`engine/busfahrer.py` (593 lines) still exists exactly as `Busfahrer-Plan.md` describes it: `BusfahrerGame`, the `GamePhase`/`PlayerStatus` enums, the R1-4 `ROUNDS` table, `_evaluate_round`/`_check_guess` (including the "everyone correct → random unlucky stays active" rule), `_start_bus_ride`/`_bus_ride_guess`, `allocate_sips`, `player_finished_drink`. It's genuinely untouched: it imports `from blackjack import Card, Deck` (a bare, unqualified import — this **would fail to import** as part of the `engine` package today, confirming it's a dropped-in draft, not wired-up code), and `pyproject.toml:15` explicitly excludes it from test collection with the comment `# WIP, not ready hence excluded from testing`. There's also dead leftover prototype code at the bottom of the file (`play()`, `SoloBusfahrer`, references to undefined `os`/`time`) that should be deleted rather than ported.

**No integration work has started.** Grep for "busfahrer" across `app/`, `static/`, `templates/` turns up only a one-line comment in `dealer_lottery.py` citing it as a precedent, plus the `pyproject.toml` exclusion. No `GameRoom` field, no routes, no serializer block, no frontend module — everything in the plan's §4 is still greenfield.

**How this interacts with item 5 above:** the plan's intro and §6 open questions both flag that a unified engine is "a prerequisite for Busfahrer if Busfahrer should also work in referee mode." Item 5's real state — two parallel engines, not merged, just better organized — means that prerequisite is **still unmet**. But the plan's entire §4 integration section (GameRoom field, web serializer, web routes, frontend) already assumes a **web/digital-mode-only** feature; it never wires into `RefereeSession`/CLI. So:

- **If Busfahrer is web-mode-only** (my recommendation, and consistent with how the plan is actually written): the existing build order in `Busfahrer-Plan.md` §5 is still valid as-is and does **not** need to wait on item 5.
- **If Busfahrer must also work in referee/CLI mode**: the unified-engine prerequisite is still outstanding, and that decision — not item 5's partial refactor — is the actual blocker. This should be resolved as an explicit decision before starting, not discovered mid-build.

**Recommended implementation order for Busfahrer** (assuming web-mode-only, confirm this first): port the engine into `app/services/busfahrer.py` fixing the `Card`/`Deck` import to match the main app's card representation → add the `GameRoom._busfahrer` field + `_busfahrer_active` pause flag → admin start/cancel routes → player guess/allocate/finished routes → serializer block → hook every sip event through `award_sips()` (not the old scattered pattern — item 1 above already gives us the right primitive) → NPC auto-guess → frontend modal + admin controls → manual playtest matrix from the plan's step 7. This matches the plan's existing §5 almost exactly; the only new addition from this audit is "use `award_sips()`" being explicit, since the plan was written before confirming it's fully bypass-free (Part 2, item 1).

---

## Part 4 — Master checklist, in implementation order

Bug fixes first (cheap + high value), then deployment-safety confirmation (free/cheap), then the two flagged doc corrections, then remaining architectural work, then Busfahrer.

- [x] **1. Fix bust-vote side-bet mismatch** — `apply_bust_vote_penalties` ([drink_tracker.py](../../app/services/drink_tracker.py)) and `payout_tracker.py` now build/read a per-player `side_bets` dict (each player's own `_pbets` stake, falling back to the table default), matching the lookup already used at the deduct site (`polling.py:642`). `outcome_lines` grouped by distinct stake so mixed custom bets still display correctly. Schema field renamed `side_bet_amount` → `side_bets: dict[str, float]` in `state_schema.py`. Regression test added: `test_side_bet_settlement_uses_each_players_own_stake` in `tests/app/test_bust_vote.py`. Full suite (404 tests) passes.
- [x] **2. Guard Dealer Lottery deck exhaustion** — `resolve_dealer_lottery`'s draws now go through a new `_draw()` helper ([app/services/dealer_lottery.py](../../app/services/dealer_lottery.py)) that replenishes with a fresh shuffled deck if `deck.cards` runs empty, instead of raising `IndexError`. Regression test added: `test_resolve_survives_deck_exhaustion_from_long_hit_runs` in `tests/app/test_dealer_lottery.py`. Full suite (403 tests) passes.
- [x] **3. Confirm/pin Render worker count** — committed a [`Procfile`](../../Procfile): `gunicorn --workers 1 --threads 1 server:app`. `--workers 1` keeps `game_sessions` a single in-memory dict (multiple workers would be separate processes with separate copies). `--threads 1` is deliberately conservative beyond what item #4 fixed: only the registration/seat-transfer race class has an explicit lock so far — other check-then-mutate routes (`vote_kick`, bust-vote casting, hit/stand actions, etc.) haven't been individually audited for thread-safety, so full request serialization is the safe default until/unless those are reviewed too. Whatever the Render dashboard's start command was previously, Render respects a committed `Procfile` when present, so this is enforced in-repo regardless.
- [x] **4. Add a lock around registration/seat-transfer mutations** — `GameRoom._registry_lock` (a `threading.Lock`, [game_room.py](../../app/models/game_room.py)) now guards the full check-then-mutate body of `/register`, `/request_local_seat`, `/handle_registration`, and `/handle_seat_transfer` (all in `app/routes/polling.py`; the approval route lives there, not in `admin.py` as originally cited). Regression tests in `tests/app/test_registry_lock.py` prove mutual exclusion by wall-clock time (verified to fail without the lock, pass with it) and that two concurrent approvals for the same pending seat can never both succeed. Full suite (407 tests) passes.
- [~] **5. Cap/rotate session-lifetime lists** — declined. `session.drinks.csv_rows` / `_decision_log` / `_dealer_lottery_decision_log` are exactly the rows `/export_xlsx` and `/export_decisions` (`app/routes/reports.py`) read to build the full-session export — capping them would silently truncate exported data, which matters more than the slow-burn memory risk on a typical single-session party-game night. Left uncapped; revisit only if real sessions are observed running long enough for this to actually threaten the 512MB ceiling.
- [x] **6. Correct `Improvements.md` item 5's status** — updated in place to reflect the actual state (digital path extracted into `game_engine.py`; referee/digital still parallel; the merge itself not done), so the Busfahrer prerequisite question stays accurate for whoever picks it up next.
- [ ] **7. Decide Busfahrer's scope** — web-mode-only vs. must-also-work-in-referee-mode (`Busfahrer-Plan.md` §6). This gates whether item 5's unfinished merge blocks the work at all.
- [ ] **8. Build Busfahrer** per `Busfahrer-Plan.md` §5, using `award_sips()` throughout for every sip event (per Part 3 above).
- [ ] **9. (Optional, low urgency) Add a `state_seq`-gated cache** to `serialize_state()` so unchanged state isn't fully rebuilt/re-validated on every poll — only worth doing if table sizes or poll frequency grow.
- [~] **10. Frontend component architecture Option A** (class-based JS components, no framework) from `Improvements.md` item 7 — in progress. Converted so far, each as a `mount(el)`/`render(state)` class with one delegated click listener replacing per-render `onclick=`/`addEventListener`-on-every-rebuild patterns: `DrinksPanel` (round/drinks pane, [table.js](../../static/js/ui/table.js)), `BustGivePanel` and `DealerLotteryGivePanel` (handout give-panels), `PendingRegBanner` (registration accept/deny banner — the one site that had server data, `client_id`, interpolated directly into an `onclick=` string rather than via `dataset`), and `BustVotePanel` (the countdown-timer modal, per-player vote cards, tally, and post-round status indicator — all in [admin.js](../../static/js/ui/admin.js)). The vote-card buttons previously re-attached `addEventListener` on every rebuild of `#bust-vote-players-wrap`; `mount()` now attaches one delegated listener instead. Verified in-browser: modal open/close conditions, single- and multi-local-player vote cards, tally, auto-close on full vote, auto-close when the server reports the window closed externally, and post-round result text, all via real dispatched click events (not direct method calls). Also converted `InsurancePanel` ([table-modals.js](../../static/js/ui/table-modals.js)) — the full insurance-vote modal plus the compact banner it minimises into (two related surfaces sharing state, `modalKey`/`minimised`), replacing `updateInsuranceVisibility`/`renderInsuranceModal`/`_renderInsuranceBanner`/`_renderInsuranceBannerOutcome`/`_expandInsuranceModal` and the modal's ad-hoc `_wired`-flag guard on its minimize button. `mount(modalEl, bannerEl)` attaches one delegated listener per surface. Verified in-browser: vote-button rendering/click (modal and minimised-banner variants), minimize → banner, banner → expand → modal, resolved-outcome banner text, and the fully-hidden state — all via real dispatched click events. Remaining `onclick=` sites (`kpi.js`, `lobby.js`, `trivia.js`) carry no user/server-derived data, so they're lower priority and not yet converted.
