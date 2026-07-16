# Subgame Targeted Drinking Mode — Implementation Plan

## general idea
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

## open questions

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

## architecture brainstorming

SubgameState {
  isActive: boolean
  targetedPlayers: Player[]
  currentRound: number
  streaks: Map  // consecutive correct guesses
  votes: Map
  afkStrikes: Map
  voteTimer: number  // countdown in seconds
  endVotes: Set  // players voting to end early
}

Host triggers subgame (or majority vote)
  → Select target player(s)
  → Modal appears for targeted players (all others are spectators)
  → Dealer hand plays out normally
  → Each round:
      1. Timer starts (e.g., 15s)
      2. Players vote BUST or STAND (all players vote and play independently)
      3. Dealer resolves hand
      4. Compare: wrong = +1 sip, right = streak++
      5. If streak === 3 → player "graduates" out
      6. If AFK twice → kicked to host-local
  → Subgame ends when all players graduate OR end button majority

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
  stake to 0) — and resolves. No AFK tracking in the MVP (§8.4).
- `resolve_targeted_drinking_round(session)` — called once the round's
  real dealer hand is known resolved (hook: same point `tick.py`'s
  `_run_deferred_dealer_play` already determines `dealer.dealer_hand.is_bust()`
  for Bust Vote). For each target:
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
- [ ] **3. Player vote route + `tick.py` hook + serializer block**
  (§5.4, §5.6, §5.5).
- [ ] **4. Frontend modal** (§5.7), verified in-browser the same way
  every panel this session was: real dispatched click events, not direct
  method calls, covering vote submission and graduation.
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

### 8.1 [ ] Majority-vote start/end (`app/routes/admin.py`, mirrors `vote_kick`)

Reuse `vote_kick`'s exact majority math (`admin.py`, strict majority:
`len(votes) > len(eligible) / 2`) for two new votes:

- `POST /targeted_drinking/vote_start` — body: proposed target name(s).
  Toggles a vote in a new `session.round._targeted_drinking_start_votes`
  dict (keyed by proposed target set, so different simultaneous proposals
  don't collide); auto-starts once a majority of eligible (non-spectator,
  non-target) voters agree.
- `POST /targeted_drinking/vote_end` — toggles a vote in a new
  `RoundState._targeted_drinking_end_votes` set; auto-ends once a strict
  majority of *all* connected non-spectator players agree — matches the
  brainstorm's "have a button that ends the subgame now, majority vote
  based."

Frontend: a majority-vote banner reusing the kick-vote banner's visual
style (`renderKickVoteBanner`, `admin.js`) for both the vote-to-start and
vote-to-end flows.

### 8.2 [ ] Staggered loss-penalty tiers

Track a separate *losing*-streak counter (consecutive wrong guesses,
distinct from the graduation streak) on `GameRoom` — at 3 wrong in a row,
award 1 extra sip; at 5 wrong in a row, award a bigger extra penalty.
Reuse the milestone-repeat-offender pattern in `_apply_worst_player_streak`
(`drink_tracker.py:515`) as the style reference for "streak-gated bonus
penalty, logged with its own reason string." New config constants:
`TARGETED_DRINKING_LOSS_PENALTY_AT = 3`, `TARGETED_DRINKING_LOSS_PENALTY_AT_5 = 5`.

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

## 9. Testing plan additions for §8

If/when any of §8 ships: majority-vote start with a mixed set of proposed
targets and majority-vote end (mirrors `tests/app/test_registry_lock.py`'s
concurrency-adjacent conventions for the vote-counting logic), the loss-
penalty tier thresholds (3 and 5 in a row), the repeat-target 5-round
cooldown and consent-override path, and AFK-strike counting plus the
seat-reassignment side effects on `_room_clients`/`local_names`.

## 10. Ensure accurracy across md files

Ensure that any and all newly added files etc are correctly documented
in README, Architecture, Rules, and any other doc that may be impacted.
