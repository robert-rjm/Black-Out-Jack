# Subgame Targeted Drinking Mode — Implementation Plan

## General idea
- subgame that takes 1+ players into betting on whether dealer busts
- can be started by host at any time (maybe also via majority vote)
- participating/ selected players cannot obt out
- players must bet on whether Dealer hand will bust (separate from normal round, side game similar to Dealer Lottery)
- aim is to give players opportunity to catch up OR finish their drink depending on time
- player have choice to either bet bust or stand, if vote incorrect, drink 1 sip
- interface should look similar to the Dealer Lottery modal
- these accumulated sips get counted towards the sip counter and aggregate sips, also in csv as drinking rule
- if player is correct 3 times in a row (similar to game mechanics of busfahrer) this sub game ends and goes back to normal blackjack as before
- have a button that ends the subgame now, majority vote based
- have something if player goes afk (timer for bust/stand vote + if not answering twice in a row, player gets "kicked" and becomes local player of host)
- consider having a 3 round cooldown between subgames, 5 rounds if only one player is targeted both times (can be overwritten if targeted player agrees)
- losing streak, if 3 times wrong, drink extra sip(s), if 5 times wrong streak extra drink punishment

## Open questions

Resolved (with reasoning), vs. still genuinely open:

- **Where to have the begin-subgame button within the interface?** —
  resolved: put it in the admin settings panel (`admin-settings.js`'s
  players/settings overlay), next to the existing kick-vote UI, since
  starting the subgame is conceptually "do something to another player's
  seat" just like kicking — reuses a UI area players already know to check.
  (A majority-vote variant of this button is deferred — see §8.1.)
- **Side bets for spectators, to "join just for fun"?** — still open.
  Deferred: adds real scope (a second betting surface, its own payout
  math) for a mechanic whose core loop isn't validated by playtesting yet.
  Revisit after the MVP ships and only if spectators specifically ask for
  a way to participate. Grouped with the other deferred items in §8.5.
- **Rescue mechanic, player can volunteer to sub in/split drinks?** —
  still open, but narrowed: the existing Bust Vote handout flow
  (`/give_bust_sip`) already lets a *winner* give a sip to someone else;
  the natural fit here is the mirror image — let a *non-targeted* player
  volunteer to absorb a targeted player's sip on a wrong guess. Deferred
  to §8.5, since it needs a UI affordance (a "take this sip for them"
  button) that doesn't exist yet anywhere in the codebase and isn't
  required for the mode to work.
- **How to implement?** — see the full plan below (§3 onward). Short
  answer: this is much closer to a *persistent, targeted variant of the
  existing Bust Vote mechanic* than a new game mode — it reuses the same
  "vote bust/stand against this round's real dealer hand" primitive
  (`apply_bust_vote_penalties`, `cast_bust_vote`), just scoped to a fixed
  player list that persists across multiple rounds instead of being
  opt-in per round, with its own streak/graduation state layered on top.
  It does **not** need Busfahrer's "pause all normal play" approach
  (`_busfahrer_active`) — normal blackjack rounds keep happening exactly
  as today; targeted players just also owe a mandatory bust/stand call
  each round until they graduate or the subgame ends.

**Scope note:** the first build deliberately ships a smaller slice than
the full brainstorm above. Four pieces of the original idea — majority
vote (start *and* end), the escalating 3-vs-5 loss-penalty tiers, the
cooldown consent-override, and the AFK → seat-reassignment mechanic — are
real, engineerable features, but each adds meaningful complexity on top
of a core loop ("does forcibly targeting a player to drink more actually
feel fun at the table, or does it feel like the group ganging up on
someone?") that hasn't been validated by an actual playtest yet. They're
fully specified in §8 so nothing is lost, but the MVP in §4-§7 covers just
the core loop: admin-only start/cancel, one flat per-round penalty, a
flat cooldown, and no AFK handling (unanswered votes just default to
"stand," matching the Dealer Lottery's own precedent of defaulting an
unset entry to a safe/neutral value on timeout).

## 3. Relationship to existing mechanics

Three existing systems are close cousins of this one — worth being
explicit about how Targeted Drinking Mode differs from each, since it
borrows real code from all three:

- **Bust Vote** (`app/services/drink_tracker.py`'s `apply_bust_vote_penalties`,
  `app/routes/polling.py`'s `cast_bust_vote`, frontend `BustVotePanel` in
  `admin.js`) — the closest relative. Same core question ("will the dealer
  bust this round?"), same wrong-guess-costs-a-sip mechanic. Differs in:
  opt-in per round (vs. mandatory once targeted), no streak/graduation, no
  persistence across rounds, no targeting concept at all.
- **Dealer Lottery** (`app/services/dealer_lottery.py`, triggered on a
  paired dealer 18/20) — cited in the brainstorm as the UI reference.
  Similar "modal with a timed decision" shape, but it's a one-off event
  tied to a rare server-triggered condition, not a persistent multi-round
  mode a human explicitly starts/stops.
- **Busfahrer** (`docs/planning/Busfahrer-Plan.md`) — the streak-to-graduate
  idea rhymes with Busfahrer's bus-ride mechanic (5 correct in a row to
  escape), but Busfahrer fully pauses normal blackjack play
  (`_busfahrer_active`) while it runs. Targeted Drinking Mode deliberately
  does **not** pause anything — it rides alongside the normal round.

**Conclusion:** build this as its own small subsystem
(`app/services/targeted_drinking.py`) that reuses `award_sips()` and the
`tick.py` forfeit-window pattern, rather than extending Bust Vote's own
code — the two are similar in spirit but different enough in persistence
and targeting semantics that bolting this onto `apply_bust_vote_penalties`
would make that function harder to reason about for both mechanics.

## 4. Refined architecture (MVP)

Mapping the brainstorm's `SubgameState` onto the app's real state layers
— MVP scope only (see §8 for the fields the deferred features would add).
One thing persists **across rounds** (session-lifetime, so it belongs on
`GameRoom` directly, not `RoundState` which is wiped every round):

```python
# app/models/game_room.py — new fields on GameRoom
_targeted_drinking_active: bool = False
_targeted_drinking_targets: list = field(default_factory=list)   # names, fixed for the subgame's lifetime
_targeted_drinking_streaks: dict = field(default_factory=dict)   # name -> consecutive correct guesses (graduation streak)
_targeted_drinking_cooldown_until_round: int = 0   # round_count below which a new subgame can't start
```

Everything else — the current round's votes and countdown — is exactly
the same shape as Bust Vote's own per-round fields, so it lives on
`RoundState` (reset every round is correct here, since a fresh vote is
owed every round anyway):

```python
# app/models/game_room.py — new fields on RoundState
_targeted_drinking_votes: dict = field(default_factory=dict)        # name -> "bust" | "stand" | None
_targeted_drinking_expires_at: float | None = None
```

`isActive`/`targetedPlayers`/`streaks` map to the `GameRoom` fields above;
`votes`/`voteTimer` map to the `RoundState` ones. `currentRound` doesn't
need its own counter — `session.round_count` already exists and is
exactly that. `afkStrikes`/`endVotes` from the original brainstorm belong
to the deferred features in §8 and aren't part of the MVP state.

## 5. Implementation plan (MVP)

### 5.1 Config constants (`app/config.py`)

```python
TARGETED_DRINKING_VOTE_WINDOW_SECONDS = 15   # per-round bust/stand vote timer
TARGETED_DRINKING_STREAK_TO_GRADUATE  = 3    # consecutive correct guesses to opt out
TARGETED_DRINKING_COOLDOWN_ROUNDS     = 3    # rounds before a new subgame can start
```

### 5.2 New service module (`app/services/targeted_drinking.py`)

Mirrors `dealer_lottery.py`'s structure (trigger check → vote window →
resolve → forfeit-on-timeout), reusing `award_sips()` for every sip event
instead of touching `_sip_ticker`/`_drink_csv_rows` by hand:

- `start_targeted_drinking(session, target_names, started_by) -> bool` —
  admin-only entry point. Validates: not already active,
  `session.round_count >= session._targeted_drinking_cooldown_until_round`,
  every name is a connected non-kicked player. Sets
  `_targeted_drinking_active = True`, `_targeted_drinking_targets =
  target_names`, resets streaks to 0 for those names.
- `maybe_open_targeted_drinking_vote(session)` — called from `tick.py`
  once per poll (mirrors `maybe_start_dealer_lottery`): if active and no
  vote is currently open for this round, opens one
  (`_targeted_drinking_expires_at = now + TARGETED_DRINKING_VOTE_WINDOW_SECONDS`),
  gated behind the same milestone/insurance-pending checks `tick.py`
  already uses for other windows, so prompts don't stack.
- `submit_targeted_drinking_vote(session, player_name, vote: str) -> bool`
  — records `"bust"`/`"stand"` in `RoundState._targeted_drinking_votes`.
- `apply_targeted_drinking_vote_forfeit(session)` — called every tick
  (mirrors `apply_dealer_lottery_entry_forfeit`): if the window expired
  with unanswered targets, defaults their vote to `"stand"` — the same
  "default the unset value to something safe/neutral" precedent the
  Dealer Lottery entry-window forfeit already uses (defaults an unset
  stake to 0). **Does not itself resolve** — see the correctness note
  below. No AFK tracking in the MVP (§8.4).
- `resolve_targeted_drinking_round(session)` — called **only** from
  `app/services/round_pipeline.py`'s `apply_endround_pipeline`, once the
  round has genuinely ended (same single trigger point `apply_bust_vote_penalties`
  already uses — one call per real `cmd_endround()`, never an independent
  timer). Also must run *after* `harvest_drink_log()` in that pipeline, not
  before — see §6 step 3's note on why. For each target:
  - Correct guess: `streak += 1`. If `streak >= TARGETED_DRINKING_STREAK_TO_GRADUATE`,
    remove them from `_targeted_drinking_targets` (they "graduate").
  - Wrong guess: `streak = 0`, `award_sips(session, name, 1, "Targeted Drinking wrong guess", reason=...)`.
    Flat one-sip penalty — no escalating tiers in the MVP (§8.2).
  - If `_targeted_drinking_targets` is now empty, call
    `end_targeted_drinking(session, reason="all_graduated")`.
- `end_targeted_drinking(session, reason)` — clears active/targets/streaks,
  sets `_targeted_drinking_cooldown_until_round = session.round_count +
  TARGETED_DRINKING_COOLDOWN_ROUNDS` (flat cooldown, no repeat-target
  special case in the MVP — §8.3).

**Correctness note (found during §6 step 4's in-browser verification, not
part of the original design):** the first implementation had
`apply_targeted_drinking_vote_forfeit` call `resolve_targeted_drinking_round`
directly once its own 15s window expired. That's wrong, because — unlike
Bust Vote, whose countdown *blocks* dealer play until it closes, keeping
vote-close and dealer-resolve in lockstep — this window deliberately never
pauses anything (§3). A round routinely outlasts 15s, so the window can
expire while `dealer.dealer_hand` is still either the *previous* round's
stale result or an empty pre-deal `Hand()` that reads as "not bust" —
neither is this round's real outcome. Worse, nothing re-armed the window
after it fired once, so every following tick (every `/state` poll, ~every
2s) re-ran the resolve against that same stale hand — graduating a target
within seconds of the game sitting in the pre-deal waiting room. Fixed by
making the forfeit function only lock in the "stand" default (cosmetic —
`resolve_targeted_drinking_round`'s own `votes.get(name) or "stand"`
fallback would apply the same default regardless) and leaving all
resolution to the single `apply_endround_pipeline` call site. A second,
related gap: `RoundState` is never replaced wholesale between rounds (only
individual mechanics reset their own fields, e.g. `_cmd_deal_digital`'s
own `_bust_votes = {}`), so `_cmd_deal_digital` now also resets
`_targeted_drinking_votes`/`_targeted_drinking_expires_at` each deal —
without it, a new round would inherit the previous round's already-expired
window and stale votes.

### 5.3 Admin routes (`app/routes/admin.py`)

Follow the existing `make_bot`/`toggle_god_mode`/kick pattern:

- `POST /targeted_drinking/start` — admin-only; body: list of target
  names. Calls `start_targeted_drinking`.
- `POST /targeted_drinking/cancel` — admin-only immediate stop — calls
  `end_targeted_drinking(reason="admin_cancelled")`.

No majority-vote routes in the MVP — see §8.1.

### 5.4 Player routes (`app/routes/polling.py`, mirrors `cast_bust_vote`)

- `POST /targeted_drinking/vote` — body: `vote: "bust" | "stand"`,
  optional `player_name` for local multiplayer (identical shape to
  `cast_bust_vote`). Calls `submit_targeted_drinking_vote`.

### 5.5 Serializer / schema (`app/services/serializer.py`, `app/models/state_schema.py`)

New `targeted_drinking` block on `AppState`, mirroring `DealerLotteryOut`'s
shape:

```python
class TargetedDrinkingOut(_StrictModel):
    active:        bool
    targets:       list[str]
    streaks:       dict[str, int]          # graduation streak, per target
    my_vote:       Optional[str]           # this client's own pending vote, if targeted
    votes_cast:    dict[str, str]          # revealed only for names who have voted / after resolve
    seconds_left:  int
    cooldown_until_round: int
```

### 5.6 `tick.py` hook

Add exactly two calls, in the same style as the Dealer Lottery entries
already there (`tick.py:116-123`):

```python
# Start/refresh the targeted-drinking vote window (gated behind milestone/insurance, like Dealer Lottery)
maybe_open_targeted_drinking_vote(session)
# Forfeit unanswered votes when the window expires
apply_targeted_drinking_vote_forfeit(session)
```

Placed after the Dealer Lottery block and before the bust-vote-closed
dealer-play trigger, so a targeted-drinking prompt never blocks the
normal round from advancing (it rides alongside, per §3's design goal).

### 5.7 Frontend (`static/js/ui/table-modals.js` or a new
`static/js/ui/targeted-drinking.js`)

Build this as a class-based component from the start — no reason to
write it the old imperative way and convert it later, given the six
panels already converted this way this session
(`BustVotePanel`/`DealerLotteryEntryPanel`/`InsurancePanel`/`MilestonePanel`
etc., all in `admin.js`/`table-modals.js`, all following the same
`mount(el)` + `render(state)` shape from `Improvements.md` item 7 /
Option A):

```js
class TargetedDrinkingPanel {
  mount(el) {
    if (this.el) return;
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest("[data-td-vote]");
      if (btn) submitTargetedDrinkingVote(btn.dataset.tdVote);
    });
  }
  render(state) { /* modal reusing Dealer Lottery's CSS classes per the
                      brainstorm's own "interface should look similar to
                      the Dealer Lottery modal" note */ }
}
const targetedDrinkingPanel = new TargetedDrinkingPanel();
```

Admin-side: a "Target players…" multi-select + start button in
`admin-settings.js`'s players panel (per §2's resolved placement
question). No majority-vote banner in the MVP — see §8.1.

## 6. Build order checklist (MVP)

- [x] **1. Backend service module + config constants** (§5.1-§5.2), fully
  unit tested against a bare `GameRoom` (no Flask), following the exact
  test style already used in `tests/app/test_dealer_lottery.py` and
  `tests/app/test_bust_vote.py` — scripted deck / scripted vote inputs,
  assert on `award_sips` outcomes and streak state.
  `app/services/targeted_drinking.py` + config constants in
  `app/config.py` + new fields on `GameRoom`/`RoundState` in
  `app/models/game_room.py`; 25 tests in
  `tests/app/test_targeted_drinking.py`, full suite (433 tests) passing.
- [x] **2. Admin start/cancel routes** (§5.3) — playable end-to-end via
  direct admin action. `POST /targeted_drinking/start` (body:
  `target_names: [str]`) and `POST /targeted_drinking/cancel` added to
  `app/routes/admin.py`, following the existing `_require_admin` /
  `sanitize_name` / `jsonify({**serialize_state(...), "ok": True})`
  pattern used by every other admin route (`rotate_dealer`,
  `take_back_seat`, etc.). 8 new Flask-test-client route tests added to
  `tests/app/test_targeted_drinking.py` (admin-only gating, empty/unknown
  target rejection, already-active rejection, cancel idempotency); full
  suite now 441 tests passing.
- [x] **3. Player vote route + `tick.py` hook + serializer block**
  (§5.4, §5.6, §5.5). `POST /targeted_drinking/vote` added to
  `app/routes/polling.py` (mirrors `/cast_bust_vote`: window-closed check,
  optional `player_name` for local multiplayer). `tick.py` gained steps 9-10
  (`maybe_open_targeted_drinking_vote` / `apply_targeted_drinking_vote_forfeit`),
  placed after the Dealer Lottery block and before the bust-vote-closed
  dealer-play trigger per §5.6. `resolve_targeted_drinking_round` wired into
  `app/services/round_pipeline.py`'s `apply_endround_pipeline` — **placed
  after `harvest_drink_log()`, not before**: `award_sips()` writes directly
  to the post-harvest accumulators (`last_round_sips`/`last_round_drinks`),
  which `harvest_drink_log`'s own snapshot step overwrites wholesale from
  each player's `drink_log`, so resolving before harvest would silently
  drop the sip event. A full-stack regression test (real dealt round
  through `/command` + `/state`) locks this ordering in — verified it
  actually fails if the two calls are swapped. New `TargetedDrinkingOut`
  schema block in `app/models/state_schema.py` + matching serializer block
  in `app/services/serializer.py` (`active`, `targets`, `streaks`,
  `my_vote`, `votes_cast`, `seconds_left`, `cooldown_until_round`). 10 new
  tests (vote route + serializer + full-stack integration) in
  `tests/app/test_targeted_drinking.py`; full suite now 451 tests passing.
- [x] **4. Frontend modal** (§5.7). `TargetedDrinkingPanel` (class-based,
  `mount(el)`/`render(state)`) added to `table-modals.js`, wired into
  `table.js`'s `buildDigitalUI()`/`_syncDigitalUI()`: a per-local-target
  vote card (BUST/STAND) inside `#targeted-drinking-modal-overlay`, reusing
  Dealer Lottery's CSS classes/shape per the brainstorm's own UI note, plus
  a compact `#td-status-banner` for players who aren't currently targeted
  (mirrors `MilestonePanel`'s non-winner waiting banner). Admin-side
  "Target players…" checkbox multi-select + Start/Cancel added to
  `admin-settings.js`'s players screen (`_renderTargetedDrinkingAdmin`,
  next to the kick-list per §2's resolved placement question).

  Verified in-browser (real dev server, real fetch calls through the
  actual routes) — and this surfaced two real backend bugs the unit tests
  hadn't caught, now fixed with regression tests added:
  - The admin's target checkboxes rendered at 0×0 and were unclickable:
    `main.css`'s global `input { appearance: none }` reset collapses an
    unstyled checkbox with no fallback box. Fixed with an explicit
    `#targeted-drinking-admin-section input[type="checkbox"]` rule
    (`modals.css`) restoring native sizing/appearance.
  - `apply_targeted_drinking_vote_forfeit` was itself calling
    `resolve_targeted_drinking_round` once its independent 15s timer
    expired — but this window (unlike Bust Vote's) never pauses the round,
    so it can expire mid-round against a stale/empty `dealer.dealer_hand`,
    and nothing re-armed it afterward, so it re-resolved on *every*
    following tick — graduating a target within seconds while the table
    was still sitting in the pre-deal waiting room. Fixed by having the
    forfeit only lock in the "stand" default; only `apply_endround_pipeline`
    (after harvest, once per real round-end) may resolve. Separately,
    `_cmd_deal_digital` now also resets `_targeted_drinking_votes`/
    `_targeted_drinking_expires_at` each deal (RoundState isn't replaced
    wholesale between rounds), matching its own `_bust_votes` reset — see
    §5.2's correctness note for the full writeup.

  10 new/updated tests in `tests/app/test_targeted_drinking.py`; full
  suite now 452 tests passing.

  **Post-review bug reports (4), all fixed:**
  1. *"should queue for in-between rounds, not during active round"* —
     the vote window opened via a lazy tick-based `maybe_open_targeted_drinking_vote`
     call, so admin-starting the subgame mid-round could pop the vote
     prompt mid-hand. Fixed by moving the window-open call to
     `_cmd_deal_digital` (deal time, exactly mirroring how Bust Vote's own
     window is opened) instead of ticking it every poll — starting the
     subgame mid-round now leaves `_targeted_drinking_expires_at` unset
     until the *next* deal. `maybe_open_targeted_drinking_vote`'s own logic
     is unchanged (still idempotent/safe to call more than once), only its
     call site moved.
  2. *"the targeted drinks froze after selecting bust"* — the vote modal
     is a full-viewport overlay that never auto-closed after voting (only
     `!td.active` or losing local-target status closed it), so it sat
     blocking hit/stand for the rest of the round. Fixed by closing it once
     every locally-targeted seat has voted this round, mirroring
     `BustVotePanel`'s own `if (!anyUnvoted) this.close()`. Also found and
     fixed the frontend's missing check that a window is *actually* open
     server-side (`seconds_left > 0`) before trying to show the modal at
     all — without it, a subgame that's `active` but hasn't reached its
     first deal yet (see bug 1) would still try to pop the modal client-side
     with nothing to vote on.
  3. *"should it say something like 'targeting Rob'?"* — `#td-status-banner`
     copy reworked: non-targeted players now see "🎯 Targeting **Rob**",
     a targeted-but-not-yet-prompted player sees "🎯 You've been targeted —
     starts next round", and a locked-in target sees "🎯 You called
     **BUST** — waiting for the dealer" (ordering bug caught here too: the
     "not yet prompted" branch was checked before the "already voted"
     branch, so a player who *had* voted but whose window had since expired
     saw the wrong message).
  4. *"how can the admin prematurely exit without 3 in a row correct?"* —
     the Cancel button was always reachable via Settings → Players, but
     `#kick-overlay` shared the same `z-index: 500` as the vote modal and
     appeared earlier in `_modals.html`'s DOM order, so the vote modal
     painted on top and blocked the click when both were open (e.g. an
     admin who is also a live target). Bumped `#kick-overlay`/`#summary-overlay`
     to `z-index: 550` (still below `#rules-overlay`'s 600) so Settings
     always stacks above any game-event modal. Combined with fix 2, this
     is now rarely even needed — voting once gets the modal out of the way.

  3 new regression tests added; full suite now 453 tests passing.
- [ ] **5. Playtest the MVP with a real group** before touching anything
  in §8 — this is the actual point of shipping a smaller slice first.

## 7. Testing plan (MVP)

- Engine-level (no Flask): streak-to-graduate math, flat cooldown
  calculation, forfeit-defaults-to-stand behavior on timeout.
- Route-level (Flask test client, mirrors `tests/app/test_bust_vote.py`
  conventions): admin start/cancel, player vote submission (including
  local-multiplayer `player_name` variant).
- In-browser (per this session's established verification standard —
  real dispatched click events, not direct method calls, checked against
  a running dev server): modal open/vote/graduate flow.

## 8. Future features (not in MVP)

Each of these is a real, engineerable feature — deferred because they
add complexity on top of a core loop that hasn't been validated by an
actual playtest yet (see the scope note in §2). Build only the ones that
turn out to matter once the MVP has been played for real.

### 8.1 [x] Majority-vote start/end (`app/routes/admin.py`, mirrors `vote_kick`)

**Done, start half only** — see §12. Shipped `POST /targeted_drinking/vote_target`
(`polling.py`, not `admin.py` — grouped with the other player-facing
Targeted Drinking routes instead) using `vote_kick`'s exact majority math.
`vote_end` was **not** built — the brainstorm's "button that ends the
subgame now" instead became a straight host/dealer permission (§8.9), not
a vote; nobody asked for a vote-to-end and it would have added a second
majority-math surface for no clear benefit yet. Revisit if it's requested.

### 8.2 [x] Staggered loss-penalty tiers

**Done, the streak-scaled variant (the "OR" option below)** — see §12.
Wrong-guess sips now equal the current losing-streak length (1st miss = 1,
2nd = 2, 3rd = 3, ...) instead of the flat-threshold design originally
sketched (`TARGETED_DRINKING_LOSS_PENALTY_AT`/`_AT_5`) — those constants
were never added; the streak-scaled approach doesn't need fixed
thresholds.

### 8.3 [ ] Cooldown consent-override + repeat-target cooldown

Two related refinements to the flat §5.2 cooldown:

- **Repeat-target cooldown**: if the same single player is targeted twice
  in a row, use a longer cooldown (5 rounds instead of 3) after the
  second subgame ends. Needs a `_targeted_drinking_last_targets` field on
  `GameRoom` to compare against. New config constant:
  `TARGETED_DRINKING_COOLDOWN_ROUNDS_REPEAT = 5`.
- **Consent override**: let the admin start a new subgame before the
  cooldown expires if every proposed target explicitly agrees — implement
  as a required per-target consent flag in the `/targeted_drinking/start`
  request body when a cooldown is still active (`start_targeted_drinking(...,
  override_cooldown=False)`), not a separate vote.

### 8.4 [ ] AFK → seat reassignment ("becomes local player of host")

This reuses machinery that already exists for a *different* purpose —
`local_names` already lets one client control multiple seats (see the
existing `/request_local_seat` flow, `polling.py`). Needs a
`_targeted_drinking_afk_strikes: dict` field on `GameRoom` and a new
`TARGETED_DRINKING_MAX_AFK_STRIKES = 2` config constant. When a target
hits the strike limit (two missed votes in a row — requires the §5.2
forfeit path to distinguish "defaulted to stand" from "explicitly voted
stand," which the MVP doesn't track):

1. Find the current admin's `_room_clients` entry.
2. Append the AFK player's name to the admin's `local_names` (same
   mutation `handle_registration`'s approve branch already does at
   `polling.py`, `admin.js`'s equivalent — reuse, don't reinvent).
3. Clear that name's own primary registration/role so their original
   client (if still connected) reverts to spectator — matches how a
   normal seat transfer resolves today.
4. Remove them from `_targeted_drinking_targets` (an absorbed seat can't
   meaningfully keep playing the subgame).
5. Log a line (`session.round._log_entries`) so everyone sees why a seat
   changed hands, mirroring the existing kick-vote log line style.

Open question carried forward: should the *reason* differ from a normal
seat transfer in the served state (so the frontend can show "Bob went AFK
and X is now playing for them" instead of the generic transfer-request
UI)? Recommend yes — a distinct `reason: "afk_absorbed"` field alongside
the existing transfer bookkeeping, purely for frontend copy, no
behavioral difference.

### 8.5 [ ] Rescue/volunteer mechanic + spectator side bets

From §2's still-open questions: a "take this sip for them" button
mirroring the existing Bust Vote give-sip flow (`/give_bust_sip`), and a
separate spectator side-bet surface. Neither has a concrete design yet —
revisit only if the MVP earns its keep and players specifically ask for
either.

### 8.6 [x] Statistics Table

Table that tracks how often each targeted player was correct / incorrect
(total number of sips drank during this mini game). And also tracks how
often the Dealer Bust%. **Done** -- see the follow-up entry near the end
of this doc for the implementation writeup.

### 8.7 [ ] Dealer Aces

Could consider to have Ace of:
- Clubs count as -1 sip (no sips if incorrect vote)
- Hearts everyone drinks (also spectators)
- Diamond only targeted players drink

### 8.8 [x] Easter Egg integration

Linked the Easter Egg "dud" outcome to Targeted Drinking Mini-Game --
see `app/routes/wild_card.py`. Split is now 35% self / 15% targeted /
50% random (was 45/5/50); within the 15% targeted roll, 1/3 targets the
presser and 2/3 targets a random player. If the subgame can't actually
start (already running, or on its post-subgame cooldown), that falls
back to a dud for the press rather than stacking a second subgame.

Still open: no cap on how many mini-rounds a single subgame can chain
through before ending on its own (only ends via graduation or admin
cancel) -- "limit of 10 mini-rounds" from the original note is not
implemented.

### 8.9 [x] Admin controls

**Done** — see §12. `/targeted_drinking/begin` (open each mini-round) and
`/targeted_drinking/cancel` (end the subgame) now require host **or**
current dealer (`_require_host_or_dealer`, `admin.py`). The host's own
direct target-pick-and-launch override (`/targeted_drinking/start`)
deliberately stayed host-only — picking targets and force-launching is a
stronger power than just operating an already-running subgame's windows.

## 9. Testing plan additions for §8

If/when any of §8 ships: majority-vote start with a mixed set of proposed
targets and majority-vote end (mirrors `tests/app/test_registry_lock.py`'s
concurrency-adjacent conventions for the vote-counting logic), the loss-
penalty tier thresholds (3 and 5 in a row), the repeat-target 5-round
cooldown and consent-override path, and AFK-strike counting plus the
seat-reassignment side effects on `_room_clients`/`local_names`.

## 10. [x] Ensure accurracy across md files

Ensure that any and all newly added files etc are correctly documented
in README, Architecture, Rules, and any other doc that may be impacted.
Also remove any mention of docs/planning/TargetedDrinkingMode.md file
name from any file, this file will be deleted after implementation and
remains only in git log

Done: added **Rules.md §5.10** (new numbered rule, TOC entry, halving
table row), **Multiplayer.md** (new section + TOC entry), **Cheat-Sheet.md**
(new section), and **Architecture.md** (directory tree, file-dependency
table rows for `targeted_drinking.py`/`tick.py`/`round_pipeline.py`, test
list, docs index). Re-pinned `docs/.rules_sync.json` via
`python scripts/rules_sync.py update` (Rules.md changed, `drinking_rules.py`
didn't — expected, since this logic lives in `app/services/`, same as
Dealer Lottery). README.md needed no change — it doesn't name individual
subgames.

Every in-code/in-doc reference to this plan file's own filename was
replaced with a `Rules.md §5.10` citation (10 files: `app/config.py`,
`app/models/game_room.py`, `app/models/state_schema.py`,
`app/routes/admin.py`, `app/routes/polling.py`,
`app/services/targeted_drinking.py`, `docs/DOM-Hooks.md`,
`static/js/ui/admin-settings.js`, `static/js/ui/table-modals.js`,
`tests/app/test_targeted_drinking.py`) so this file can be deleted later
without leaving dangling references — the same cleanup was done for the
already-deleted `DealerLottery-Plan.md`'s 8 stale citations (see
`docs/planning/TODO.md`).


## 11. [x] Post-review rearchitecture: standalone mini-game

After the MVP shipped and got real hands-on use, feedback was that the
mode felt wrong: it reused the real round's own dealer hand and rode
alongside normal play (§3/§4's original design), which is functionally
identical to Bust Vote just made mandatory and persistent — not
distinct enough to read as its own subgame. This is actually a course
*correction* back toward the original brainstorm at the top of this
doc ("separate from normal round, side game similar to Dealer Lottery",
"interface should look similar to the Dealer Lottery modal") — the first
implementation had drifted from that.

Reworked to fully mirror Dealer Lottery's shape instead of Bust Vote's:

- **Separate mini-game, played between rounds, never during one.**
  `check_targeted_drinking_trigger` (round-end, mirrors
  `check_dealer_lottery_trigger`) flags the subgame eligible;
  `maybe_start_targeted_drinking_round` (ticked, mirrors
  `maybe_start_dealer_lottery`) opens the vote window once any pending
  milestone AND Dealer Lottery draw have cleared, so at most one of the
  three post-round modals is ever open. Starting the subgame mid-round
  no longer even has a "wait for the next deal" special case to get
  right — it just naturally can't trigger until a round genuinely ends.
- **A fresh, isolated dealer-only hand** (`Deck()` + shuffle + hit-to-17,
  never touching `session.shoe` — same isolation Dealer Lottery's redeal
  uses) is dealt only *after* the vote window closes, so nobody could
  vote with foreknowledge of the outcome. This replaced every reference
  to the round's real `dealer.dealer_hand`.
- **Serializer/schema** rewritten to Dealer Lottery's `pending`/
  `last_result`/`result_seq` shape (`TargetedDrinkingPendingOut`,
  `TargetedDrinkingResultOut`) instead of flat `my_vote`/`votes_cast`/
  `seconds_left` fields.
- **Frontend**: the entry modal's data source moved to `pending`; a new
  `#targeted-drinking-reveal-overlay` (reusing the Dealer Lottery reveal
  modal's shell/CSS classes and `handBlock()`/`cardEl()` card-reveal
  technique) plays the isolated hand out card-by-card, then lists each
  target's correct/wrong/graduated outcome — mirrors
  `_showDealerLotteryRevealModal` almost exactly, just for one hand
  instead of a split tree.
- `_cmd_deal_digital`'s deal-time window-open (added during the earlier
  bug-fix round, since removed) is no longer needed at all: RoundState is
  replaced wholesale on `newround` (`room_manager.reset_round_state`),
  which already clears `_pending_targeted_drinking`/`_targeted_drinking_eligible`
  between rounds -- this was misdiagnosed the first time around as "never
  reset", which is why that deal-time patch existed in the first place.

Test suite fully rewritten for the new trigger/pending/resolve flow
(55 tests, `_ScriptedDeck`-based hand control mirroring
`test_dealer_lottery.py`'s own pattern). Rules.md §5.10, Multiplayer.md,
Cheat-Sheet.md, DOM-Hooks.md, and Architecture.md all updated. Full
suite: 464 passing.

**Follow-up: back-to-back mini-rounds.** The first pass of this
rearchitecture still required a *whole normal round* to play out between
each mini-round (only `check_targeted_drinking_trigger`, called from
round-end, ever set `_targeted_drinking_eligible`). Feedback was that the
mini-game should instead play back-to-back until it ends — matching the
original brainstorm's own framing of a standalone session, not one
occasional bonus event per normal round. Fixed:

- `resolve_targeted_drinking_round` now re-arms `_targeted_drinking_eligible`
  itself immediately whenever the subgame is still running (not everyone's
  graduated yet), instead of only `check_targeted_drinking_trigger` being
  able to set it.
- A new `TARGETED_DRINKING_REVEAL_PAUSE_SECONDS` (4s) config constant gates
  `maybe_start_targeted_drinking_round` for a short breather after each
  result (checked against `last_targeted_drinking_result["set_at"]`), so
  the next vote prompt doesn't pop in before anyone's had a chance to see
  the previous reveal.
- Frontend: a `_targetedDrinkingRevealOpen` flag (mirrors
  `_dealerLotteryRevealOpen`, which Dealer Lottery itself never needed
  since it never repeats) additionally blocks the vote modal from opening
  while the reveal is still showing client-side, with an 8s auto-dismiss
  so an AFK/slow player can't block their own next prompt indefinitely.

Verified in-browser end-to-end: started the subgame, played one real
round to completion, then watched `result_seq` advance from 2 → 3 and a
full open → countdown → resolve cycle play out while `phase` stayed
`"round-over"` the entire time -- confirming zero additional normal
rounds were dealt between mini-rounds. Rules.md §5.10, Multiplayer.md,
and Cheat-Sheet.md updated; 3 new tests. Full suite: 467 passing.

**Follow-up: UI overhaul -- one continuous modal, role-aware views,
direct host cancel.** User feedback after using the back-to-back version:
the vote and reveal were two separate overlays that visibly closed and
reopened; the vote modal still felt like it "waited out the timer" even
though the backend already resolved on the last vote; spectators only
got a small status banner instead of any real view of what was
happening; and cancelling the subgame required navigating into
Settings → Players every time. Fixed entirely in the frontend --
`app/services/targeted_drinking.py` needed no changes at all, since
`submit_targeted_drinking_vote` already resolves the mini-round
synchronously the moment every target has voted (confirmed by direct
API testing: the same HTTP response that submits the deciding vote comes
back with `pending: null` and a bumped `result_seq`/populated
`last_result` -- there never was a server-side timer wait once every
target answers, so the "waits for the countdown" complaint was purely a
frontend perception problem):

- `#targeted-drinking-modal-overlay` in `_modals.html` now contains BOTH
  phases as sibling divs (`#td-vote-phase`, `#td-reveal-phase`) inside one
  `.td-modal-card`, toggled by `TargetedDrinkingPanel._showPhase()` via
  plain show/hide rather than swapping between two separate overlay
  elements -- `#targeted-drinking-reveal-overlay` was deleted outright.
  The reveal's own "Got it" button was dropped in favor of a single
  top-corner ✕ that works in both phases.
- `TargetedDrinkingPanel` (table-modals.js) absorbed the old
  `_showTargetedDrinkingRevealModal`/`closeTargetedDrinkingRevealModal`
  globals as `_enterRevealPhase`/`_exitRevealPhase` methods, and now also
  owns the `result_seq` bump-detection that used to live duplicated in
  `table.js`'s `_syncRoundEffects` -- one place decides whether to show
  vote buttons, the read-only view, or the reveal, so there's no window
  where two different code paths could show contradictory UI.
- **Role-aware vote-phase view**: targets who still need to vote get the
  existing BUST/STAND button cards (`_renderTargetVoteView`); everyone
  else -- spectators, the host, and targets who already voted --
  see a read-only live list of every target's name and vote as it's cast
  (`_renderSpectatorVoteView`), reading the same `pending.votes_cast` data
  the serializer already exposed (it was never hidden from non-targets,
  just never rendered for them before).
- **Reveal subtitle** now names every target and their vote up front
  (`<name> called BUST/STAND`) and keeps that line up through the whole
  card-dealing animation, instead of only listing the vote in the
  post-animation payout list -- this is what lets spectators see who
  called what "as the cards are dealt" rather than only after.
- **Direct host cancel**: the modal's ✕ calls `cancelTargetedDrinking()`
  for an admin (ending the whole subgame on the spot, no Settings trip),
  or just locally dismisses the current mini-round's view for anyone
  else (doesn't touch server state -- an unvoted target who dismisses
  still defaults to STAND at the timer, same as ignoring the app
  entirely). `cancelTargetedDrinking()` gained a `reopenSettings` option
  so calling it from the mini-game modal doesn't also pop open the
  Settings modal behind it (the existing Settings button still gets the
  reopen, since it's already looking at that modal). The idle status
  banner (shown between mini-rounds, when no modal is open at all) got
  its own small ✕ for the same admin-cancel affordance, so "cancel
  without going through Settings" holds in every state, not just while a
  mini-round happens to be live.

Verified via direct API calls (bypassing the UI) that a target's vote
response carries the fully-resolved state instantly, then verified in
the browser (using `becomeClient()`, a small test harness that swaps the
page's live `clientId`/state without a reload, added because the
Browser pane's tabs share one origin's localStorage so two "separate"
tabs kept clobbering each other's saved `client_id`) that: the admin/
spectator view shows the read-only "watching" list with live vote
status; the target's view shows working BUST/STAND buttons; clicking a
vote transitions the *same* modal straight into the reveal with the
correct name+vote in the subtitle; and the admin ✕ ends the subgame
immediately. Updated 5 backend tests that had implicitly assumed a
single-target vote would leave the round pending (it now resolves
immediately, which was already the actual behavior -- the tests were
just stale) to use two targets so the "still pending after one vote"
scenarios they're actually testing still exercise real intermediate
state. Multiplayer.md's Targeted Drinking section updated for the merged
UI and direct-cancel note. Full suite: 467 passing.

**Follow-up: no more flicker, color-coded outcomes, end-of-subgame
recap, confirm before cancelling.** Feedback on the merged-modal version:
it still visibly closed and reopened between chained mini-rounds (the
8s reveal auto-dismiss closed the modal outright, then it popped back
open once the next vote window opened after the reveal-pause breather);
the "Name called STAND" line used the flat purple `.dl-reveal-payout
strong` color regardless of whether the call was right; ending the
subgame gave no indication of how much anyone actually drank over the
whole run; and cancelling had no confirmation despite discarding every
target's progress. All four addressed:

- **No more close/reopen.** `TargetedDrinkingPanel` gained a `"waiting"`
  phase: between mini-rounds (subgame still active, current round
  already over), the modal stays open and reuses `#td-vote-phase`'s
  shell to show a plain "waiting for the next mini-round…" message
  instead of calling `close()`. The reveal's auto-dismiss became
  `_onContinueClick()` (also wired to a new `#td-continue-btn`) which
  just resets `phase = null` and immediately re-renders from the latest
  `lastState` -- render() re-derives whatever should show next (queued
  recap, waiting filler, or a real close) itself, so there's exactly one
  decision point instead of a timer that hard-closes and a separate poll
  that reopens moments later. A `_dismissed` flag is now edge-triggered
  (cleared only when `pending` transitions from absent to present, not
  on every tick it's absent) so dismissing the ✕ during the "waiting"
  filler actually sticks instead of un-dismissing itself the very next
  poll.
- **Blocking modal vs. banner boundary made explicit.** Before this pass
  the "between mini-rounds" and "subgame just started, current round
  still live" cases were handled by the same fallback branch (close +
  banner). They're genuinely different: a live round must never get a
  blocking overlay dropped on it. Now gated explicitly on
  `state.phase === PHASE.ROUND_OVER` -- the banner only ever appears
  before the very first mini-round of a run opens; every other "nothing
  pending right now" moment shows the modal's waiting filler instead.
- **Color-coded calls.** `_enterRevealPhase`'s subtitle and
  `_tdRevealLine`'s payout bullets both now pick `var(--green)` /
  `var(--red)` per target from `result.correct[name]` (known the instant
  the mini-round resolves, before any card animates) via an inline
  `style` override, replacing the generic `.dl-reveal-payout strong`
  purple.
- **End-of-subgame recap.** New session-lifetime state:
  `GameRoom._targeted_drinking_total_sips` (name → cumulative sips this
  run, seeded in `start_targeted_drinking`, incremented alongside the
  existing per-mini-round `sips[name] = 1` in `resolve_targeted_drinking_round`,
  survives a target graduating out since it's independent of
  `_targeted_drinking_targets`) and `DrinkLedger.last_targeted_drinking_summary`
  / `_targeted_drinking_summary_seq` (same one-shot seq pattern as
  `last_targeted_drinking_result`). `end_targeted_drinking` snapshots
  `{reason, totals, set_at}` into the summary *before* clearing
  everything else, whether it's reached via graduation
  (`resolve_targeted_drinking_round` → `end_targeted_drinking(reason="all_graduated")`)
  or an admin cancel (`reason="admin_cancelled"`). Serializer/schema
  gained `_serialize_targeted_drinking_summary` /
  `TargetedDrinkingSummaryOut` / `last_summary` / `summary_seq` on the
  `targeted_drinking` state block. Frontend: a new `#td-summary-phase`
  section (`_enterSummaryPhase`) lists each target's total sips, shown
  via a `_queuedSummary` handoff so it always appears *after* any reveal
  already in front of it, and *before* the modal is allowed to fully
  close -- covers both the graduation case (arrives bundled with the
  final mini-round's result) and the cancel-outside-a-mini-round case
  (arrives on its own, no reveal to wait behind).
- **Confirm before cancelling.** A single `confirm()` added inside
  `cancelTargetedDrinking()` in admin-settings.js guards every path that
  reaches it -- the mini-game modal's ✕, the idle status banner's ✕, and
  the pre-existing Settings → Players button -- since all three ultimately
  call this one function.

Verified via a single-tab `becomeClient()`-driven pass: starting the
subgame while the round was still live showed only the banner (no
modal); ending the round opened the modal straight into the vote phase;
casting the deciding vote transitioned in place into a reveal with the
vote color-coded green for a correct call; tapping Continue moved the
still-open modal into the "waiting" filler state; ending the subgame via
the admin ✕ (confirmed) produced a summary phase listing each target's
total sips, which closed the modal on Close; and declining the
`confirm()` prompt aborted before any request was sent. Backend: 3 new
tests (`test_end_snapshots_summary_with_totals_and_bumps_seq`,
`test_end_summary_reflects_reason_when_graduation_ends_it`,
`test_serialize_state_last_summary_after_end`) plus a fix to
`test_end_discards_an_in_flight_mini_round_without_scoring`, which had
gone flaky the same way the earlier stale tests had -- its single-target
setup meant the explicit vote it submitted now auto-resolved against a
real random deck instead of staying pending for the cancel to discard;
switched to two targets like the other fixes. Full suite: 470 passing.

**Follow-up: "Start Targeting Now" gate, and penalties excluded from
round statistics.** Two more requests: (1) the mini-game was popping up
the instant a round ended, which didn't give the table a chance to
finish drinking for the round that had just resolved first -- wanted a
button instead, in the same spot the other in-round status messages
appear, so people can settle up before the mini-game takes the screen;
(2) Targeted Drinking's wrong-guess sip was quietly inflating "worst
average sips/round" (the milestone streak penalty) and the Last-Round
summary, since it resolves *during* the just-ended round's still-current
`last_round_sips` snapshot -- a between-round mini-game penalty
shouldn't make someone look bad at actually playing blackjack, or
misattribute to a round it wasn't part of.

- **Start gate.** New `RoundState._targeted_drinking_start_requested`
  (per-round, so it resets naturally on `newround` same as everything
  else in that dataclass). `maybe_start_targeted_drinking_round` now
  requires this flag in addition to every existing gate (milestone,
  Dealer Lottery, reveal-pause) -- refactored the shared "everything
  except the start gate" check into `_targeted_drinking_ready_to_open()`
  so it can't drift between `maybe_start_targeted_drinking_round` and the
  new `targeted_drinking_awaiting_start()` (the frontend-facing "should I
  show the button" query) and `request_targeted_drinking_start()` (sets
  the flag; any registered player can call it, not admin-only -- new
  `POST /targeted_drinking/begin` route in polling.py). Critically, the
  gate only ever applies to the *first* mini-round after a normal round
  ends: `resolve_targeted_drinking_round`'s existing back-to-back re-arm
  now also re-sets `_targeted_drinking_start_requested = True` for
  itself, so chained mini-rounds never need a repeat tap. Serializer
  gained `targeted_drinking.awaiting_start` -- computed by a duplicated
  (not imported -- `targeted_drinking.py` imports `serializer.py` for
  `serialize_card`, so the reverse import would be circular)
  `_targeted_drinking_awaiting_start()` mirroring the same gates.
  Frontend: `TargetedDrinkingPanel.render()` gained a branch, checked
  before the existing "waiting between mini-rounds" modal branch, that
  shows a **Start Targeting Now** button in `#td-status-banner` (the same
  slot the idle "Targeting X" message already used) instead of opening
  the blocking modal when `awaiting_start` is true.
- **Excluded from round statistics.** `award_sips()` gained a
  `count_toward_round: bool = True` parameter -- when `False`, the sip
  still updates `sip_ticker` (session total, milestone boundary
  crossing) and a new parallel `sip_ticker_excl_round_avg` tracker, but
  skips `last_round_sips`/`last_round_drinks` entirely. `targeted_drinking.py`'s
  wrong-guess `award_sips()` call now passes `count_toward_round=False`.
  `_apply_worst_player_streak()` (the milestone "worst average
  sips/round" penalty) now subtracts `sip_ticker_excl_round_avg` back out
  of `sip_ticker` before dividing by rounds played, for both the
  candidate-ranking pass and the winner's-average penalty calculation --
  factored into a small `round_avg()` closure so both call sites can't
  drift out of sync with each other.

Verified in-browser: ending a round with the subgame active showed the
**Start Targeting Now** button (not the modal) in the status banner;
tapping it opened the mini-round's vote phase on the next poll; and a
live wrong-guess vote left `last_round_sips` byte-for-byte identical
before and after (session sip total still climbed). New tests: this
repo had no dedicated drink_tracker test module at all, so added
`tests/app/test_award_sips_round_avg.py` (named to avoid a pytest
basename collision with the existing `tests/engine/test_drink_tracker.py`)
covering `award_sips`'s `count_toward_round` flag and
`_apply_worst_player_streak`'s exclusion math directly; plus new
targeted_drinking.py-side tests for the start gate itself
(`test_maybe_start_waits_for_start_request`,
`test_request_start_noop_when_nothing_waiting`), the `/targeted_drinking/begin`
route (admin not required, no-op when nothing's waiting), and the
serializer's `awaiting_start` field, and updated every existing test that
built a pending mini-round directly (rather than through
`_active_room_with_pending`, which now requests the start itself) to call
`request_targeted_drinking_start()` first. Full suite: 482 passing.

**Follow-up: warn before a premature "new round" discards a mini-round.**
Asked whether starting a new normal round while Targeted Drinking hadn't
started (or was mid-vote) already warned anyone. It didn't — checked
`_cmd_newround` (game_commands.py) and found it unconditionally calls
`reset_round_state()`, which wholesale-replaces `RoundState` (by design,
so every per-round field defined there is automatically cleared on
`newround` — see the dataclass's own docstring). That silently wipes
`_targeted_drinking_eligible`/`_targeted_drinking_start_requested`/
`_pending_targeted_drinking` along with everything else. The subgame
itself (`_targeted_drinking_active`, targets, streaks) lives on `GameRoom`
rather than `RoundState`, so it isn't lost outright -- `check_targeted_drinking_trigger`
just re-arms it at the *next* round's end -- but that round's own
mini-hand (started or not) is silently skipped. Also confirmed via
`admin.js`'s `updateRoleUI()` that the NEW ROUND button's visibility is
gated only on `isMyDealerClient && isRoundOver` -- nothing already checks
pending milestone/Dealer Lottery/Targeted Drinking state before showing
it, so this isn't a new gap introduced by the Start Targeting Now button,
just one it made much easier to hit in practice (previously the mini-round
opened instantly at round-end, leaving almost no window to deal into it
by mistake; now there's a deliberate pause during which a dealer might
reach for NEW ROUND instead).

Fixed narrowly for Targeted Drinking (the other two mechanics have the
same underlying gap but weren't in scope here): `doNewRound()` in log.js
now checks `lastState.targeted_drinking` before doing anything, and if
`active && (awaiting_start || pending)`, shows a `confirm()` with a
message specific to which case it is ("hasn't started this mini-round
yet" vs. "still being voted on") -- declining aborts before `sendCmd`
is ever called, matching the same confirm-then-proceed pattern already
used by `cancelTargetedDrinking()`/`resetToSetup()`. This is a soft
warning, not a hard block, since a host might legitimately want to skip
a mini-round on purpose.

Verified in the browser: with the subgame `awaiting_start`, calling
`doNewRound()` with `confirm` mocked to decline correctly aborted before
`sendCmd` ran and left state untouched; same with a `pending` vote
window open, with the other message; accepting the confirm let the
round advance normally (subgame stayed active, ready to re-trigger next
round-end). No backend changes, so no new backend tests -- this is a
client-side-only guard. Full suite still 482 passing.

**§8.6 Statistics Table -- implemented, live in the modal and in the
end-of-run recap.** Asked for exactly what §8.6 originally scoped: a
running tally of each target's correct/wrong calls, plus the isolated
dealer hand's own bust rate across the run -- but explicitly *live*
inside the mini-round modal (not just a post-hoc report), so a targeted
player can factor "the dealer's busted 40% of hands so far" into their
next call, and *also* folded into the existing end-of-subgame recap
alongside the sip totals that already lived there.

- **Backend**: two new session-lifetime `GameRoom` fields alongside
  `_targeted_drinking_total_sips` (same "never loses a name on
  graduation" reasoning) -- `_targeted_drinking_correct_counts` /
  `_targeted_drinking_wrong_counts` (per target), plus plain counters
  `_targeted_drinking_dealer_hands` / `_targeted_drinking_dealer_busts`
  for the run as a whole. All four: seeded in `start_targeted_drinking`
  (correct/wrong dicts zeroed per target, counters at 0), updated in
  `resolve_targeted_drinking_round` right alongside the existing
  streak/sip bookkeeping, snapshotted into `last_targeted_drinking_summary`
  and cleared in `end_targeted_drinking` -- exactly mirroring
  `_targeted_drinking_total_sips`'s own lifecycle.
- **Live exposure, not seq-gated**: unlike `last_result`/`last_summary`
  (one-shot events gated behind `result_seq`/`summary_seq` so the
  frontend fires a reveal/recap exactly once), the statistics table is
  just *current state* -- serializer exposes it as `targeted_drinking.stats`
  every poll, always present (all-zero when inactive), no seq needed
  since there's nothing to "fire once," only to keep in sync. New
  `TargetedDrinkingStatsOut` schema model (`correct`, `wrong`,
  `dealer_hands`, `dealer_busts`), reused both at the top level and
  nested inside `TargetedDrinkingSummaryOut.stats` for the final recap.
- **Frontend**: new `#td-stats-panel` (`#td-stats-dealer-bust` +
  `#td-stats-targets`) as a sibling of `#td-vote-phase`/`#td-reveal-phase`
  inside the same `.td-modal-card` -- `_showPhase()` keeps it visible
  through vote/waiting/reveal and hides it only for the summary phase
  (which shows its own richer final version instead of the live one).
  `TargetedDrinkingPanel._renderStatsPanel(targets, stats)` builds a
  ✓/✗ row per target plus a "Dealer this run: X/Y busted (Z%)" line;
  called from the vote branch, the waiting-between-mini-rounds branch,
  and `_enterRevealPhase` (which now also takes `targets`/`stats` params
  from `render()`, since `result` alone only has *that* mini-round's
  outcome, not the running tally). `_enterSummaryPhase` extends the
  existing per-target sip list with the same ✓/✗ counts plus an overall
  dealer-bust-rate line at the top.

Verified in the browser end-to-end: the stats panel showed correctly
during the vote phase (zeroed for a fresh run), updated in place through
the reveal phase after a mini-round resolved (1✓/0✗, dealer 0/1 busted),
and the same numbers carried through into the summary screen alongside
the sip total once the subgame was cancelled. Backend: extended the
existing wrong-guess/graduation/summary tests with stats assertions
(learned partway through that `correct`/`wrong` dicts are zero-seeded
per target at `start_targeted_drinking`, same as `total_sips` -- so
"never resolved" reads as `{"Bob": 0}`, not `{}`, and adjusted the new
assertions to match rather than assume empty), plus a new
`test_stats_table_accumulates_across_mini_rounds` driving two mini-rounds
with a mixed bust/stand dealer outcome to confirm the tally is additive
across resolves, not reset each time. Full suite: 483 passing.

**Bug fix: starting the subgame while already between rounds stranded
it.** Reported as "stuck on 'Waiting for the next mini-round…' forever,
with 0 mini-rounds ever resolved (dealer_hands: 0), right after starting
Targeted Drinking in between rounds." Root cause:
`check_targeted_drinking_trigger` only ever fires *once*, at the moment
a round transitions *into* round-over (called from the end-round
pipeline) -- `start_targeted_drinking` itself never armed
`_targeted_drinking_eligible`. So starting the subgame while the room
was already sitting in round-over (rather than exactly as a round
ended) meant that trigger had already come and gone for this round-over
period; nothing would arm eligibility again until an entire *new* round
completed. Compounding it, the frontend's "waiting" branch
(`isRoundOver && !dismissed`) didn't check whether anything was actually
armed -- it fired on `isRoundOver` alone, so instead of showing nothing
useful (or the fallback banner), it displayed a message implying a
mini-round was imminent when nothing would ever come.

Fixed both ends:
- **Backend**: `start_targeted_drinking` now calls the already-imported
  `round_phase()` (from `serializer.py`, imported alongside
  `serialize_card`) and arms `session.round._targeted_drinking_eligible = True`
  immediately if the room is already in `"round-over"` when the subgame
  starts. Doesn't touch `_targeted_drinking_start_requested` -- the
  Start Targeting Now gate still applies normally from there.
- **Frontend defense-in-depth**: added a raw `targeted_drinking.eligible`
  field to the serializer/schema (mirrors `awaiting_start`'s own gates
  but without the "and not start_requested" bit) so the frontend can
  distinguish "genuinely armed, just temporarily gated by the
  reveal-pause/milestone/Dealer-Lottery/button" from "nothing queued at
  all." `TargetedDrinkingPanel`'s "waiting" branch now additionally
  requires `td.eligible` -- if a similar gap ever recurs for an
  unrelated reason, it now degrades to the plain "Targeting X" banner
  (still cancellable) instead of promising a mini-round that isn't coming.

Verified in the browser: played a round to completion with Targeted
Drinking *not yet* started, then started it -- confirmed `eligible: true`
immediately (no extra round needed). A Dealer Lottery draw happened to
also trigger on the same round-end by chance, which correctly held
`awaiting_start` at `false` until resolved (proving the fix distinguishes
"armed but gated" from "not armed at all"); once resolved, `awaiting_start`
flipped to `true` and the banner correctly showed the Start Targeting Now
button instead of a stuck waiting screen. New regression test
`test_start_while_already_between_rounds_arms_eligibility_immediately`
(full-stack, via `/command` + `/targeted_drinking/start`) plus an
assertion added to the existing pre-deal `start_targeted_drinking` test
confirming eligibility is *not* armed when a round is still in progress
(the original "never interrupts a round already in progress" guarantee).
Full suite: 484 passing.


## 12. [x] Majority-vote start, host/dealer lockdown, streak-scaled loss, perfect-graduation handout

Four features shipped in one session, closing out §8.1 (start half), §8.2,
and §8.9, plus one mechanic not scoped anywhere in this doc (the reveal
pacing fix) and one genuinely new feature (perfect-graduation handout).

**Majority vote to target someone (§8.1 start half).** A third way to
start a subgame, alongside the host's direct override and the Wild Card
easter egg — `POST /targeted_drinking/vote_target` (`polling.py`), any
non-spectator player, toggles a vote in `GameRoom._targeted_drinking_start_votes`
(`dict[target_lower, set[voter_lower]]`), auto-starts at strict majority
via `vote_kick`'s exact math. Deliberately placed on `GameRoom` (session-
lifetime) rather than `RoundState` like `_kick_votes` — a proposal should
survive across rounds until it hits majority, not reset every round. Votes
clear on any successful start (whichever path) or on `end_targeted_drinking`,
so a stale pre-cooldown vote can't instantly re-fire once cooldown lifts.
Frontend: a new always-visible banner (`#targeted-drinking-vote-banner`,
`renderTargetedDrinkingVoteBanner` in `admin-settings.js`) with a
per-player vote pill and live tally — deliberately *not* the kick-vote
pattern (cast button buried in Settings, only the tally banner on the main
table); this one puts the actual vote button on the main table too, so
it's reachable during normal play.

**Host/dealer-only flow controls (§8.9).** New `_require_host_or_dealer`
helper (`admin.py`, mirrors `_require_admin`'s shape, OR's in
`is_dealer_client`). Applied to `/targeted_drinking/begin` (previously
*any* registered player — now host or dealer) and `/targeted_drinking/cancel`
(previously admin-only — now also allows the dealer). `/targeted_drinking/start`
(the host's target-pick override) intentionally kept admin-only — see the
§8.9 note above.

**Reveal pacing fix (not scoped in this doc).** Investigating "continue"
surfaced a real bug: the server's flat 4s reveal-pause and each client's
independent 8s local auto-dismiss timer weren't synced, so a laggy client's
poll could fall behind while the server had already opened the next
mini-round — some players could get swept past a hand they never actually
saw. Fixed by giving the host/dealer's "Continue" tap a real backend hook:
`POST /targeted_drinking/continue` rewinds
`last_targeted_drinking_result["set_at"]` far enough into the past that
the existing `_targeted_drinking_ready_to_open` wait check passes
immediately — zero changes to the eligibility state machine itself. The
flat timeout (bumped 4s → 12s, `TARGETED_DRINKING_REVEAL_PAUSE_SECONDS`)
becomes a safety net instead of the only mechanism. Everyone else's
"Continue" stays exactly what it was: a personal, ungated local dismiss.

**Streak-scaled wrong-guess penalty (§8.2, the "OR" variant).** New
`GameRoom._targeted_drinking_losing_streaks` dict (consecutive wrong
guesses, independent of the graduation streak — each resets only on the
other's outcome). Wrong-guess sips now equal the current losing-streak
length: 1st consecutive miss = 1 sip, 2nd = 2, 3rd = 3. Interacts with the
existing easter-egg 5-sip cap (§8.8) faster than before: three consecutive
misses alone total 1+2+3=6, already past a cap of 5, where the old flat-1
rule needed five actual misses to get there.

**Perfect-graduation handout (new, not scoped here).** Since 3-in-a-row is
the minimum possible graduation, a target who never misses on the way
there (checked via `wrong_counts == 0` at the graduation moment) gets to
hand out `TARGETED_DRINKING_PERFECT_GRADUATION_HANDOUT_SIPS` (3) sips to
another player — any start path, not just easter-egg. Built by mirroring
Dealer Lottery's own handout almost line-for-line: `give_targeted_drinking_sip`
/ `apply_targeted_drinking_handout_forfeit` (`targeted_drinking.py`), new
`RoundState` tracking fields, a new `POST /targeted_drinking/give_sip`
route, wired into `tick.py`, and a new `TargetedDrinkingGivePanel`
frontend class reusing the existing shared `.bgp-*` give-panel CSS/markup
(`#targeted-drinking-give-overlay`, added to the same selector group as
`#bust-give-overlay`/`#dealer-lottery-give-overlay`). Blocks the next
mini-round from opening (`_targeted_drinking_ready_to_open` gates on
`_targeted_drinking_handout_expires_at`) until claimed or forfeited, same
as the reveal-pause gate above. Unlike Dealer Lottery's own handout, this
one is never halved — a flat 3, not `ceil(x/2)`.

All four changes propagated to `docs/Rules.md` §5.10 (rewritten: three
start paths, host/dealer-only controls, streak-scaled table + example,
perfect-graduation subsection) and `docs/Cheat-Sheet.md`'s Targeted
Drinking section, plus `docs/Architecture.md` where relevant. Re-pinned
`docs/.rules_sync.json` each time (Rules.md changed, `drinking_rules.py`
didn't — expected, same reasoning as §10 above).

Verified via `preview_start`/browser JS execution for every frontend
piece (vote banner render/hide across all four gating conditions, correct
fetch payload shapes, the give-panel's render/defer logic, the loss-streak
warning badge) plus a live end-to-end majority vote and a scripted
3-correct-in-a-row perfect graduation run through the real serializer
pipeline. Full suite: 555 passing (up from 484).
