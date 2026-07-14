# Code Audit — July 2026

> Quick pass looking for real bugs, inefficiencies, and dead code — as opposed
> to `Improvements.md`, which tracks larger architectural work. Everything
> below was traced through the actual code (file:line cited); nothing here is
> a speculative "could be nicer" suggestion.

---

## Drinking Mode — focused follow-up

Drinking Mode (sips, milestones, wild card, bust vote, insurance) is the
app's original core feature, so it got a second, deeper pass. Two of these
are genuine, previously-undocumented bugs I traced end-to-end myself; the
rest are drinking-mode-relevant items already listed below, pulled up here
so this section is a complete picture. Dead-code item D1 (`busfahrer.py`) is
excluded per instruction — that feature hasn't been built yet.

### DM1 · Milestone re-entrancy clobbers a second, legitimately-earned milestone
**Files:** `app/services/drink_tracker.py:562-630` (`check_and_set_milestone`), `:515-559` (`_apply_worst_player_streak`)

`check_and_set_milestone` guards against re-firing with
`if session.round._pending_milestone: return` (line 575) — but that guard
only protects against *external* re-entry. Internally:

1. It records `claimed[boundary] = winner` (line 608) for the milestone it just found.
2. It then calls `_apply_worst_player_streak(session, winner, ticker)` (line 615) — at this point `_pending_milestone` is **still `None`**.
3. That function can itself award a penalty via `award_sips()` (line 550), whose docstring confirms it calls `check_and_set_milestone()` again whenever sips > 0.
4. This **nested** call passes the still-empty guard, finds a *different* player/boundary newly crossed by the penalty sips, records `claimed[boundary2] = winner2` (line 608 again), and sets `_pending_milestone` for winner2.
5. Control returns to the **outer** call, which unconditionally overwrites `_pending_milestone` at line 625-630 with the *original* winner's data — clobbering winner2's milestone.

Because `claimed[boundary2]` was already permanently recorded in step 4, that
boundary can never fire again (line 591 skips already-claimed boundaries
forever). Its handout sips are never distributed or forfeited — they just
vanish from the sip economy, and the second player never sees their
milestone modal.

**Concrete trigger:** Player A crosses 95→105 sips (claims the 100
boundary) in a round where Player B has been "worst average" for the prior
milestone too. B's resulting penalty sips (`max(1, round(winner_avg))`) push
B from 46→51, crossing the still-unclaimed 50 boundary in the same call —
and B's milestone silently disappears.

**Fix:** small. Set/queue `_pending_milestone` before calling
`_apply_worst_player_streak`, or have `check_and_set_milestone` loop/retry
once more after the outer milestone is set, instead of unconditionally
overwriting.

---

### DM2 · Milestone handout never re-checks for a newly-crossed boundary
**File:** `app/routes/admin.py:655-687` (milestone-claim handler)

While distributing a claimed milestone's handout, `award_sips()` is called
per recipient (line 667-669) — each call's internal
`check_and_set_milestone()` is a guaranteed no-op, because
`_pending_milestone` is still populated with the milestone currently being
resolved (only cleared at line 685, *after* the loop). Nothing re-invokes
`check_and_set_milestone()` afterward. If a recipient's allocation (up to
`MILESTONE_HANDOUT_SIPS`) pushes them past the next 50-sip boundary, that
milestone goes undetected until some unrelated later event (next round's
harvest) happens to trigger it — a real delay, and if it collides with
another in-flight milestone, it can be lost entirely via DM1.

**Fix:** small. Call `check_and_set_milestone(session)` once explicitly
after line 685.

---

### DM3 · `/honor_resolve` missing seat-ownership check (= B2 below)
Drinking-mode-only feature (the docstring literally says so). See full
writeup below — any seated player can currently resolve another player's
mandatory-split prompt, choosing their sip penalty for them.

### ~~DM4~~ · Correction: B4 is Normal-mode money logic, not Drinking Mode
Originally listed here, but re-checked: `polling.py:634`'s side-bet code is
gated behind `if not session.drinking_mode and session.mode == "digital"`,
with an explicit comment — "Normal mode: side bet is opt-in via the 'bust'
vote... Drinking mode uses sips only." Bust *voting* itself is shared
infrastructure (`apply_bust_vote_penalties` handles the sip side for
drinking mode separately, in `drink_tracker.py`), but the specific bug in
B4 only ever fires in Normal mode. Moved to the general backlog below —
not a Drinking Mode item.

### DM5 · Drink log double-scanned every poll (= I1 below)
**Status:** FIXED. Directly drinking-mode: `_compute_live_drink_totals` ran
twice per `/state` tick despite its own docstring claiming it was
deduplicated. `compute_kpi_stats` now accepts an optional pre-computed
`sip_ticker` so `serialize_state` only walks the drink log once and passes
the result through. Verified by instrumenting the call count directly
(1 call instead of 2) and confirming `sip_totals`/`kpi_stats.session.total_sips`
still agree.

### DM6 · Frontend command-queue drop affects 4 drinking-mode actions (= B7 below)
**Status:** FIXED for the drinking-mode call sites.
Of the six call sites sharing the broken queue-drain (see B7 below), four
are drinking-mode actions: `honorResolve`, `submitBustVote`, `giveBustSip`,
and `castInsuranceVote` — originally undercounted as 3; re-checked and
`/vote_insurance` turns out to be drinking-mode-only too (insurance slots
are only created `if ... and session.drinking_mode`, `game_engine.py`
first-deal setup). A player's queued Hit/Stand could be silently dropped if
it landed while one of these four was in flight. Fixed by extracting a
shared `_requestDone()` helper (`state.js`) that decrements
`_requestsInFlight` *and* drains `_pendingCmd`, used in all four instead of
a bare decrement. Verified live in the browser: staged an in-flight request,
queued a command, called `_requestDone()`, confirmed the queued command
replayed and both counters reset correctly. The other two call sites
(`sendPreselect`, `bankRebuy`) are confirmed **not** drinking-mode-specific
and are left for the general backlog (see B7 below).

### Checked, no action needed
- Sip-rule math in `engine/drinking_rules.py` (aces, blackjack multipliers,
  insurance, hard-switch, 4-player halving) — internally consistent, no
  off-by-one or double-fire found.
- Referee (CLI) vs. digital (web) paths both funnel through the same
  `DrinkingRules.handle()`/`DrinkTracker` — no divergent drink outcomes.
- Wild Card cooldown (`wild_card.py:100-107`) and milestone gate
  (`:110-119`) are correctly enforced server-side, so the frontend's
  missing double-tap guard on `triggerWildCard()`
  (`static/js/ui/log.js:389`) is cosmetic at worst — a wasted request that
  gets rejected, not a double-fire.
- Redundant `add_drink()` calls alongside `award_sips()` in a few spots
  (`polling.py`, `drink_tracker.py`) don't double-count sips — traced
  through the harvest gating and confirmed inert. Low-priority cleanup, not
  a bug.

---

## Bugs

### B1 · `/rebuy` has no seat-ownership check — security
**File:** `app/routes/game_commands.py:374-395`

The route checks that the caller is *some* registered, non-kicked client —
spectators included — but never checks that `player_name` belongs to the
caller's own seat (other routes like `/set_player_bet` do this check,
`polling.py:754-761`). Any connected client, including a spectator, can
re-buy any busted player's bankroll back to the starting amount.

**Fix:** add the same `player_name in info.get("local_names", [])` guard
`/set_player_bet` already uses. Trivial.

---

### B2 · `/honor_resolve` has no seat-ownership check — security
**Status:** FIXED (non-admin callers now restricted to their own seat(s); admin/dealer still exempt, matching the dealer-gate model on `/command`)
**File:** `app/routes/game_commands.py:398-458`

Requires the caller's role to be `admin` or `player`, but never checks that
the caller controls `pending["player"]`. Any seated player can resolve
*another* player's "mandatory split" house-rule prompt on their behalf —
choosing their action and whether they take the 1-sip penalty.

**Fix:** same pattern as B1. Small.

---

### B3 · `num_decks` is unvalidated on room setup — crash / memory DoS
**File:** `app/routes/lobby.py:218` vs. the clamp that already exists in
`app/routes/admin.py:515-518`

```python
num_decks = int(data.get("num_decks", default_decks))   # no bounds check, no try/except
```

`admin.py`'s `/update_settings` clamps `1 <= v <= 8`; `/setup` doesn't.
Consequences, traced through `engine/blackjack.py`:
- `num_decks=0` → `Shoe.total_cards = 0`, `needs_reshuffle()` (`len(cards) < (1-pen)*0`) is **always False**, and the initial `cards` list is empty (the `for _ in range(0)` loop never runs). The very first `deal_card()` call does `self.cards.pop()` on an empty list → unhandled `IndexError` → room permanently broken.
- A non-numeric string in the request body → uncaught `ValueError` from `int(...)`, surfaced as a generic 500.
- A very large value (e.g. `999999`) → allocates that many `Deck()` objects — a client can single-handedly exhaust server memory since this is unauthenticated JSON with no upper bound.

**Fix:** clamp the same way `admin.py` already does. Trivial.

---

### B4 · Bust-vote side bet ignores per-player custom bet — money bug
**File:** `app/routes/polling.py:634`, settled in `app/services/payout_tracker.py:122-138`

```python
side_bet = session.bet_amount / 2
```

Uses the table-wide default bet. But `/set_player_bet` lets a player set an
individual bet, and every *other* payout path (`deduct_bets`,
`deduct_split_bet`, `_hand_return`) respects it. A player who raised their
bet to $50 still stakes/wins only half of the $10 default on the bust side
bet — the two money paths silently disagree for the same player.

**Fix:** `session._player_bets.get(name, session.bet_amount)` instead of the
flat default. Small.

---

### B5 · Room-code reservation has a check-then-act race
**File:** `app/services/session_store.py:50-57` (`generate_room_code`) and
`:85-96` (`reserve_room`)

`generate_room_code()` checks `code not in game_sessions` and returns it;
`reserve_room()` writes `game_sessions[code] = None` several lines later with
nothing holding the slot in between. Two concurrent `/create_room` requests
can both pass the check for the same code before either writes, and the
second silently clobbers the first room.

**Caveat — not currently exploitable:** `server.py:48` calls
`app.run(host="0.0.0.0", port=5000, debug=False)` with no `threaded=True`,
so today's dev-server deployment handles one request at a time and this race
can't actually fire. It becomes live the moment the app moves to a
threaded/multi-worker WSGI server — which is exactly the direction
`Improvements.md` item 2 (SSE, off Render) is already pointing. Worth fixing
before that migration, not urgent before it.

**Fix:** wrap check+insert in a `threading.Lock`. Small.

---

### B6 · Unhandled `ValueError` from a malformed hand label
**File:** `app/routes/game_commands.py:536` (`_cmd_split`), duplicated at
`engine/blackjack.py:287` and `engine/referee.py:310`

```python
idx = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
```

Any `hand_label` that doesn't reduce to a digit raises an uncaught
`ValueError` → generic 500 instead of a graceful "Cannot split this hand"
response.

**Fix:** wrap in try/except, reject with a normal error response. Trivial.

---

### B7 · Frontend command queue silently drops actions under overlap
**Status:** FIXED for the 4 drinking-mode call sites (`honorResolve`,
`castInsuranceVote`, `submitBustVote`, `giveBustSip`) plus `sendCmd` itself.
`sendPreselect` and `bankRebuy` are confirmed not drinking-mode-specific and
are still open (general backlog).
**Files:** `static/js/state.js:31-34` (the queue), drained only in
`static/js/ui/table.js:283-319` (`sendCmd`'s `finally` block)

The one-slot "last intent wins" queue (`_pendingCmd`) was only ever drained
inside `sendCmd`'s own `finally`. But six other functions increment the same
`_requestsInFlight` counter and never drained the queue when *they*
finished:

- `sendPreselect` — `table.js:257-276` — **open**, not drinking-mode-specific
- `castInsuranceVote` — `table-modals.js:276-293` — **fixed** (insurance is drinking-mode-only, `game_engine.py`'s first-deal setup)
- `honorResolve` — `table.js:702-716` — **fixed**
- `bankRebuy` — `table.js:746-759` — **open**, Normal-mode-only ("Bank Run" modal)
- `submitBustVote` — `admin.js:198-214` — **fixed**
- `giveBustSip` — `admin.js:580-597` — **fixed**

**Failure scenario:** a player taps "Insure" on the insurance modal (slow
network, request takes 500ms) and then taps "Hit" before it resolves.
`sendCmd("hit ...")` sees `_requestsInFlight > 0`, queues itself into
`_pendingCmd`, and returns — no visual lock is even applied since it bailed
before `cmdLockButtons()`. When `castInsuranceVote`'s fetch resolves, its
`finally` block only did `_requestsInFlight--`; it never checked
`_pendingCmd`. The queued Hit was silently dropped — the state.js comment's
claim that "last intent wins" was only true when the in-flight request
happened to be a `sendCmd` call.

**Fix:** extracted a shared `_requestDone()` helper (`state.js`) that
decrements the counter *and* drains `_pendingCmd`. Applied to `sendCmd`,
`honorResolve`, `castInsuranceVote`, `submitBustVote`, and `giveBustSip`.
Remaining: `sendPreselect` and `bankRebuy` — same one-line fix, left for the
general backlog since neither is drinking-mode-specific.

---

### B8 · Milestone re-entrancy clobbers a second, legitimately-earned milestone
**Status:** FIXED
**Files:** `app/services/drink_tracker.py:562-630` (`check_and_set_milestone`),
`:515-559` (`_apply_worst_player_streak`)

Full writeup in the Drinking Mode section above (DM1). Short version:
`check_and_set_milestone`'s re-entry guard is empty at the exact moment its
own call to `_apply_worst_player_streak` can trigger a *nested* milestone
for a different player — the nested milestone gets permanently marked
`claimed` and then immediately overwritten/lost when the outer call finishes.
The handout sips for that second milestone vanish; the second player never
sees their handout modal.

**Fix:** small — set/queue `_pending_milestone` before calling
`_apply_worst_player_streak`, or retry once more after the outer milestone
is set instead of unconditionally overwriting.

---

### B9 · Milestone handout never re-checks for a newly-crossed boundary
**Status:** FIXED (also found and fixed the same gap in the forfeit path, `drink_tracker.py:apply_milestone_forfeit`)
**File:** `app/routes/admin.py:655-687`

Full writeup in the Drinking Mode section above (DM2). Short version: every
`award_sips()` call inside the handout-distribution loop is a guaranteed
no-op for milestone detection, because `_pending_milestone` is still set
until after the loop — so a recipient's allocation crossing the *next*
boundary goes undetected until an unrelated later event happens to trigger
it (and can be lost entirely if it collides with B8).

**Fix:** small — call `check_and_set_milestone(session)` once explicitly
after the handout loop clears `_pending_milestone`.

---

## Inefficiencies

### I1 · Drink log is walked twice per `/state` poll — contradicts its own docstring
**Status:** FIXED (`compute_kpi_stats` now takes an optional pre-computed `sip_ticker`; `serialize_state` passes through the one it already computed instead of triggering a second scan)
**File:** `app/services/serializer.py:206-212, 233-241, 645-647`

`_compute_live_drink_totals`'s docstring says it exists specifically "so the
live drink_log is only walked once per poll instead of twice." In practice
`serialize_state` calls it directly (`:646`) for `sip_totals`, and separately
`compute_kpi_stats` (called at `:833`) calls `compute_sip_totals` (`:241`),
which calls the same function again — a second full
O(players × drink_log_length) scan on every single `/state` request,
defeating the optimization the comment claims exists.

**Fix:** compute once in `serialize_state`, pass the result into
`compute_kpi_stats`. Small.

---

### I2 · `play_order` / `current_turn` / `round_phase` recomputed repeatedly per poll
**File:** `app/services/serializer.py` (`play_order` :62, `current_turn` :93,
`round_phase` :109) and `app/services/tick.py:37,108,112`

`round_phase()` calls `current_turn()`, which calls `play_order()`.
`serialize_state` then calls `current_turn()` again directly (`:573`) and
`play_order()` again for the `"play_order"` response field (`:810`), and
`compute_kpi_stats` calls `play_order()` a fourth time internally (`:426`).
`tick()` — which runs immediately before `serialize_state` on every
`/state` hit (`polling.py:62-63,75`) — calls `round_phase()` 1-2 more times
on top of that. None of these are individually O(n²), but a single poll
(fired every 1-3s per connected client) ends up doing 6+ redundant O(players)
passes over the same data.

**Fix:** compute `phase`/`turn`/`order` once at the top of `serialize_state`
and thread the values through instead of recomputing. Small.

---

### I3 · 26 unbundled static asset requests, no HTTP/2, on a dev server
**Files:** `templates/partials/index/_head.html` (9 CSS `<link>` tags),
`templates/partials/index/_scripts.html` (17 `<script>` tags)

Every page load fires 9 render-blocking CSS requests plus 17 more JS
requests (2 deferred vendor scripts + 17 app scripts) — 26 total. `server.py`
runs the plain Werkzeug dev server (`app.run(...)`, no gunicorn/nginx in the
repo), which serves HTTP/1.1 only, so browsers cap concurrent connections
per host at ~6 — the requests queue in batches rather than truly
parallelizing. This is a real cost specifically because the app's actual
deployment context (per its own docstring) is "open on any phone on the same
WiFi" at a party/bar — exactly the kind of shared, often-flaky wifi where
serialized round trips are most noticeable, and it delays time-to-interactive
(buttons, room-code generation) even though the HTML itself paints fine.

**Fix:** concatenate the 17 app JS files into one bundle (order matters —
they rely on load-order-defined globals, so a straight concatenation in
current `<script>` order works with no other changes) and the 9 CSS files
into one. No build tooling required — a small script that cats the files in
order at deploy time is enough, or Flask-Assets if more automation is
wanted. Medium (mostly deciding on a bundling approach; the concatenation
itself is trivial).

---

## Dead code

### D1 · `engine/busfahrer.py` is entirely unused, and its one import is broken
**File:** `engine/busfahrer.py:21`

Not imported anywhere else in the repo (verified via full-repo grep). Its
own import is wrong for this package layout:

```python
from blackjack import Card, Deck   # should be: from engine.blackjack import Card, Deck
```

This proves the module has never actually been run — it's speculative
scaffolding for the Busfahrer feature tracked in `Improvements.md` item 5,
sitting in `engine/` as broken, dead code today.

**Fix:** either delete it, or fix the import and start wiring it up if
Busfahrer work begins. Trivial either way.

---

### D2 · Dead no-op arithmetic (minor)
**File:** `static/js/ui/admin.js:1087`

```js
_syncBetStepperLimits(row, val, (lastState ? lastState.bet_amount : 5) * 20 / 20);
```

The `* 20 / 20` is a no-op — almost certainly a copy-paste artifact from the
`max = defaultBet * 20` calculation a few lines up. Harmless but confusing.

**Fix:** `_syncBetStepperLimits(row, val, lastState ? lastState.bet_amount : 5);`. Trivial.

---

## Next tasks

### Drinking Mode — do these first

- [x] **B8** — fix milestone re-entrancy clobbering a second milestone (`drink_tracker.py:562-630`) — highest severity: sips silently vanish from the economy
- [x] **B9** — re-check for a newly-crossed milestone boundary after a handout finishes distributing (`admin.py:655-687`, and the same gap in the forfeit path, `drink_tracker.py:718`) — compounds with B8
- [x] **B2** — add seat-ownership check to `/honor_resolve` (`game_commands.py:398`)
- [x] **I1** — stop double-computing drink totals per poll; compute once in `serialize_state`
- [x] **B7 (drinking-mode sites)** — `_requestDone()` helper now used by `sendCmd`, `honorResolve`, `castInsuranceVote`, `submitBustVote`, `giveBustSip`

### Everything else

- [ ] **B4** — settle bust-vote side bet against the player's actual bet, not the table default (`polling.py:634`) — Normal-mode money logic, not Drinking Mode (see correction in the Drinking Mode section above)
- [ ] **B1** — add seat-ownership check to `/rebuy` (`game_commands.py:374`)
- [ ] **B3** — clamp `num_decks` in `/setup` the same way `/update_settings` does (`lobby.py:218`)
- [ ] **B6** — wrap `_cmd_split`'s hand-label parsing in try/except (`game_commands.py:536`, `blackjack.py:287`, `referee.py:310`)
- [ ] **B7 (rest)** — apply the same `_requestDone()` fix to `sendPreselect` and `bankRebuy`
- [ ] **D2** — delete the dead `* 20 / 20` in `admin.js:1087`
- [ ] **I2** — compute `phase`/`turn`/`play_order` once per poll instead of up to 6 times
- [ ] **D1** — delete `engine/busfahrer.py` or fix its import and pick the work back up (deferred — not built yet)
- [ ] **B5** — add a lock around room-code check+reserve (do before any move to a threaded/multi-worker server — see `Improvements.md` item 2)
- [ ] **I3** — bundle the 17 JS files and 9 CSS files into one request each

Within Drinking Mode: B8 and B9 first since they compound (a milestone lost
to B8 is unrecoverable — actual sips silently disappear from the game, not
just a display glitch), then the two access-control/money bugs (B2, B4),
then the inefficiency (I1) and the queue-drop fix (B7) since both touch
drinking-mode actions specifically. Everything else is unchanged from
before — do B1/B3/B6 next regardless (all trivial-to-small), the rest as
time allows.
