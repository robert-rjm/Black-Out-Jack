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
  A majority-vote variant can live in the same kick-vote-style banner
  pattern (see below) rather than needing new screen real estate.
- **Side bets for spectators, to "join just for fun"?** — still open.
  Deferred: adds real scope (a second betting surface, its own payout
  math) for a mechanic whose core loop isn't validated by playtesting yet.
  Revisit after the core targeted-vote loop ships and only if spectators
  specifically ask for a way to participate.
- **Rescue mechanic, player can volunteer to sub in/split drinks?** —
  still open, but narrowed: the existing Bust Vote handout flow
  (`/give_bust_sip`) already lets a *winner* give a sip to someone else;
  the natural fit here is the mirror image — let a *non-targeted* player
  volunteer to absorb a targeted player's sip on a wrong guess. Left as a
  fast-follow, not in the initial build (see build-order step 7 in §6),
  since it needs a UI affordance (a "take this sip for them" button) that
  doesn't exist yet anywhere in the codebase and isn't required for the
  mode to work.
- **How to implement?** — see the full plan below (§3 onward). Short
  answer: this is much closer to a *persistent, targeted variant of the
  existing Bust Vote mechanic* than a new game mode — it reuses the same
  "vote bust/stand against this round's real dealer hand" primitive
  (`apply_bust_vote_penalties`, `cast_bust_vote`), just scoped to a fixed
  player list that persists across multiple rounds instead of being
  opt-in per round, with its own streak/graduation/AFK state layered on
  top. It does **not** need Busfahrer's "pause all normal play" approach
  (`_busfahrer_active`) — normal blackjack rounds keep happening exactly
  as today; targeted players just also owe a mandatory bust/stand call
  each round until they graduate or the subgame ends.

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
  and AFK/timeout ideas rhyme with Busfahrer's bus-ride mechanic (5 correct
  in a row to escape), but Busfahrer fully pauses normal blackjack play
  (`_busfahrer_active`) while it runs. Targeted Drinking Mode deliberately
  does **not** pause anything — it rides alongside the normal round.

**Conclusion:** build this as its own small subsystem
(`app/services/targeted_drinking.py`) that reuses `award_sips()` and the
`tick.py` forfeit-window pattern, rather than extending Bust Vote's own
code — the two are similar in spirit but different enough in persistence
and targeting semantics that bolting this onto `apply_bust_vote_penalties`
would make that function harder to reason about for both mechanics.

## 4. Refined architecture

Mapping the brainstorm's `SubgameState` onto the app's real state layers.
Two things persist **across rounds** (session-lifetime, so they belong on
`GameRoom` directly, not `RoundState` which is wiped every round):

```python
# app/models/game_room.py — new fields on GameRoom
_targeted_drinking_active: bool = False
_targeted_drinking_targets: list = field(default_factory=list)   # names, fixed for the subgame's lifetime
_targeted_drinking_streaks: dict = field(default_factory=dict)   # name -> consecutive correct guesses
_targeted_drinking_afk_strikes: dict = field(default_factory=dict)  # name -> missed-vote count
_targeted_drinking_cooldown_until_round: int = 0   # round_count below which a new subgame can't start
_targeted_drinking_last_targets: list = field(default_factory=list)  # for the "same player both times" cooldown rule
```

Everything else — the current round's votes and countdown — is exactly
the same shape as Bust Vote's own per-round fields, so it lives on
`RoundState` (reset every round is correct here, since a fresh vote is
owed every round anyway):

```python
# app/models/game_room.py — new fields on RoundState
_targeted_drinking_votes: dict = field(default_factory=dict)        # name -> "bust" | "stand" | None
_targeted_drinking_expires_at: float | None = None
_targeted_drinking_end_votes: set = field(default_factory=set)      # players voting to end early this round
```

`isActive`/`targetedPlayers`/`streaks`/`afkStrikes` map to the `GameRoom`
fields above; `votes`/`voteTimer`/`endVotes` map to the `RoundState` ones.
`currentRound` doesn't need its own counter — `session.round_count`
already exists and is exactly that.

## 5. Implementation plan

### 5.1 Config constants (`app/config.py`)

```python
TARGETED_DRINKING_VOTE_WINDOW_SECONDS = 15   # per-round bust/stand vote timer
TARGETED_DRINKING_STREAK_TO_GRADUATE  = 3    # consecutive correct guesses to opt out
TARGETED_DRINKING_MAX_AFK_STRIKES     = 2    # missed votes before seat reassignment
TARGETED_DRINKING_LOSS_PENALTY_AT     = 3    # consecutive wrong guesses -> extra sip
TARGETED_DRINKING_LOSS_PENALTY_AT_5   = 5    # consecutive wrong guesses -> bigger extra penalty
TARGETED_DRINKING_COOLDOWN_ROUNDS         = 3   # rounds before a new subgame can start
TARGETED_DRINKING_COOLDOWN_ROUNDS_REPEAT  = 5   # cooldown if the same single player is targeted twice in a row
```

### 5.2 New service module (`app/services/targeted_drinking.py`)

Mirrors `dealer_lottery.py`'s structure (trigger check → entry/vote
window → resolve → forfeit-on-timeout), reusing `award_sips()` for every
sip event instead of touching `_sip_ticker`/`_drink_csv_rows` by hand:

- `start_targeted_drinking(session, target_names, started_by, override_cooldown=False) -> bool` —
  admin-only entry point. Validates: not already active, cooldown
  respected (`session.round_count >= session._targeted_drinking_cooldown_until_round`)
  unless `override_cooldown=True`, which the route only honors if every
  proposed target has explicitly agreed (per the brainstorm's "can be
  overwritten if targeted player agrees" — implemented as a required
  per-target consent flag in the `/targeted_drinking/start` request body
  when a cooldown is still active, not a separate vote). Also validates
  every name is a connected non-kicked player. Sets
  `_targeted_drinking_active = True`, `_targeted_drinking_targets =
  target_names`, resets streaks/AFK strikes to 0 for those names.
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
  with unanswered targets, defaults them to a missed vote. This counts as
  an AFK strike but deliberately **not** as a wrong guess (doesn't reset
  the graduation streak or trip the losing-streak penalty tiers) — a
  missed vote is a connectivity/attention problem, not a guess the player
  actually got wrong, so it shouldn't compound with the guess-based
  penalties; it only ever leads to the separate AFK → seat-reassignment
  path in §5.6.
- `resolve_targeted_drinking_round(session)` — called once the round's
  real dealer hand is known resolved (hook: same point `tick.py`'s
  `_run_deferred_dealer_play` already determines `dealer.dealer_hand.is_bust()`
  for Bust Vote). For each target:
  - Correct guess: `streak += 1`. If `streak >= TARGETED_DRINKING_STREAK_TO_GRADUATE`,
    remove them from `_targeted_drinking_targets` (they "graduate").
  - Wrong guess: `streak = 0`, `award_sips(session, name, 1, "Targeted Drinking wrong guess", reason=...)`.
    Track a separate *losing*-streak counter (consecutive wrong guesses,
    distinct from the graduation streak) — at
    `TARGETED_DRINKING_LOSS_PENALTY_AT` wrong in a row, award 1 extra sip;
    at `TARGETED_DRINKING_LOSS_PENALTY_AT_5`, award a bigger extra penalty
    (reuse the milestone-repeat-offender pattern in
    `_apply_worst_player_streak`, `drink_tracker.py:515`, as the style
    reference for "streak-gated bonus penalty, logged with its own reason
    string").
  - If `_targeted_drinking_targets` is now empty, call
    `end_targeted_drinking(session, reason="all_graduated")`.
- `end_targeted_drinking(session, reason)` — clears active/targets/streaks,
  sets `_targeted_drinking_cooldown_until_round = session.round_count +
  (TARGETED_DRINKING_COOLDOWN_ROUNDS_REPEAT if len(targets_at_end) == 1
  and targets_at_end == session._targeted_drinking_last_targets else
  TARGETED_DRINKING_COOLDOWN_ROUNDS)`, records `_targeted_drinking_last_targets`.

### 5.3 Admin routes (`app/routes/admin.py`)

Follow the existing `make_bot`/`toggle_god_mode`/kick pattern:

- `POST /targeted_drinking/start` — admin-only; body: list of target
  names. Calls `start_targeted_drinking`.
- `POST /targeted_drinking/cancel` — admin-only immediate stop (host
  override, no vote needed) — calls `end_targeted_drinking(reason="admin_cancelled")`.

### 5.4 Majority-vote start/end (`app/routes/admin.py`, mirrors `vote_kick`)

Reuse `vote_kick`'s exact majority math (`admin.py`, strict majority:
`len(votes) > len(eligible) / 2`) for two new votes:

- `POST /targeted_drinking/vote_start` — body: proposed target name(s).
  Toggles a vote in a new `session.round._targeted_drinking_start_votes`
  dict (keyed by proposed target set, so different simultaneous proposals
  don't collide); auto-starts once a majority of eligible (non-spectator,
  non-target) voters agree.
- `POST /targeted_drinking/vote_end` — toggles a vote in
  `RoundState._targeted_drinking_end_votes` (defined in §4); auto-ends
  once a strict majority of *all* connected non-spectator players agree
  — matches the brainstorm's "have a button that ends the subgame now,
  majority vote based."

### 5.5 Player routes (`app/routes/polling.py`, mirrors `cast_bust_vote`)

- `POST /targeted_drinking/vote` — body: `vote: "bust" | "stand"`,
  optional `player_name` for local multiplayer (identical shape to
  `cast_bust_vote`). Calls `submit_targeted_drinking_vote`.

### 5.6 AFK → seat reassignment ("becomes local player of host")

This reuses machinery that already exists for a *different* purpose —
`local_names` already lets one client control multiple seats (see the
existing `/request_local_seat` flow, `polling.py`). When a target hits
`TARGETED_DRINKING_MAX_AFK_STRIKES`:

1. Find the current admin's `_room_clients` entry.
2. Append the AFK player's name to the admin's `local_names` (same
   mutation `handle_registration`'s approve branch already does at
   `polling.py`, `admin.js`'s equivalent — reuse, don't reinvent).
3. Clear that name's own primary registration/role so their original
   client (if still connected) reverts to spectator — matches how a
   normal seat transfer resolves today.
4. Remove them from `_targeted_drinking_targets` (an absorbed seat can't
   meaningfully keep playing the subgame) but do **not** reset their
   losing-streak state — the point is the group keeps drinking on their
   behalf via the host, not that missing votes erases penalties.
5. Log a line (`session.round._log_entries`) so everyone sees why a seat
   changed hands, mirroring the existing kick-vote log line style.

**Open question carried forward:** should the *reason* differ from a
normal seat transfer in the served state (so the frontend can show
"Bob went AFK and X is now playing for them" instead of the generic
transfer-request UI)? Recommend yes — a distinct `reason: "afk_absorbed"`
field alongside the existing transfer bookkeeping, purely for frontend
copy, no behavioral difference.

### 5.7 Serializer / schema (`app/services/serializer.py`, `app/models/state_schema.py`)

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
    start_votes:   dict[str, int]          # proposed-target-set -> vote count (for the majority-start banner)
    end_votes:     int                     # current count toward majority-end
    cooldown_until_round: int
```

### 5.8 `tick.py` hook

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

### 5.9 Frontend (`static/js/ui/table-modals.js` or a new
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
question), plus a majority-vote banner reusing the kick-vote banner's
visual style (`renderKickVoteBanner`, `admin.js`) for the vote-to-start
and vote-to-end flows.

## 6. Suggested build order

1. Backend service module (§5.2) + config constants (§5.1), fully unit
   tested against a bare `GameRoom` (no Flask), following the exact test
   style already used in `tests/app/test_dealer_lottery.py` and
   `tests/app/test_bust_vote.py` — scripted deck / scripted vote inputs,
   assert on `award_sips` outcomes and streak state.
2. Admin start/cancel routes (§5.3) — the simplest path first (no
   majority-vote yet), so the mechanic is playable end-to-end via direct
   admin action before layering voting on top.
3. Player vote route (§5.5) + `tick.py` hook (§5.8) + serializer block
   (§5.7).
4. Frontend modal (§5.9), verified in-browser the same way every panel
   this session was: real dispatched click events, not direct method
   calls, covering vote submission, graduation, and the losing-streak
   penalty tiers.
5. Majority-vote start/end (§5.4) — additive on top of the working
   admin-only flow.
6. AFK → seat-reassignment mechanic (§5.6) — genuinely new machinery
   (no existing "N missed actions -> reassign seat" pattern anywhere in
   the codebase), so build and test it last and in isolation.
7. **Fast-follow, not in the initial build:** the rescue/volunteer
   mechanic and spectator side bets from §2's still-open questions.

## 7. Testing plan

- Engine-level (no Flask): streak-to-graduate math, losing-streak
  penalty tiers (3 and 5 in a row), cooldown calculation (including the
  "same single player targeted twice" 5-round variant), AFK-strike
  counting and the seat-reassignment side effects on `_room_clients` /
  `local_names`.
- Route-level (Flask test client, mirrors `tests/app/test_bust_vote.py` /
  `tests/app/test_registry_lock.py` conventions): admin start/cancel,
  player vote submission (including local-multiplayer `player_name`
  variant), majority-vote start with a mixed set of proposed targets,
  majority-vote end.
- In-browser (per this session's established verification standard —
  real dispatched click events, not direct method calls, checked against
  a running dev server): modal open/vote/graduate/lose flow, majority-vote
  banners, and the AFK-absorption UI copy.
