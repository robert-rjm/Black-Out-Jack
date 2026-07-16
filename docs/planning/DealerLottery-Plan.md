# Dealer Lottery — Implementation Plan

A post-round bonus side event, separate from normal play: if the dealer's
final hand happens to be a rare paired 18 or 20, the table gets a chance to
double down on it — quite literally. This plan fixes the mechanic (worked
out via brainstorm) and lays out how to build it into the live app, in the
same format as `Busfahrer-Plan.md`.

## 1. Rules summary (target spec)

- **Trigger** — at end-of-round, after the round's own result, side bets,
  and milestone are all resolved: was the dealer's final hand exactly two
  cards of matching blackjack value, totaling either 18 (two 9s) or 20 (any
  two ten-value cards: 10/J/Q/K in any combination)?
  - Because the dealer always stands at 17+, a two-card final hand can
    *only* be one of these two pairs — any other starting total would have
    forced at least one more hit, meaning the final hand would no longer be
    those original two cards. No additional "didn't bust" check is needed;
    reaching this state already implies it.
  - This never overlaps with the Blackjack bonus (5.3): a two-card
    blackjack requires an Ace, which no 9-9 or ten-value pair contains.
- **Sequence** — runs strictly after bust-vote resolution and milestone
  handout are both fully settled (not merely computed — if a milestone
  handout is pending, the lottery prompt waits for it to clear), and
  strictly before players "cash in" and drink for the round. Doesn't touch
  the round's own recorded result/stats in any way — a pure bolt-on.
- **Entry** — every human player (dealer included) is prompted to pick
  X = 0-5, with a **20-second entry window** (new `DEALER_LOTTERY_ENTRY_
  WINDOW_SECONDS` config constant — between `BUST_VOTE_WINDOW_SECONDS`
  (15.5s, a simpler binary choice) and `MILESTONE_TTL` (60s, a multi-player
  allocation decision); picking one of 6 values warrants a bit more than
  the bust-vote's window but nowhere near the milestone's). A player who
  hasn't responded when the window closes defaults to `X = 0` — same
  "non-responder abstains" behavior as the bust vote, no new forfeit
  concept needed. Bots auto-submit 0 immediately. If everyone (who
  responds, plus every timed-out default) ends up at 0, the lottery is
  skipped entirely — no draw happens, nothing is logged.
- **The draw** — the dealer's pair is split into fresh hands for this
  event only: each keeps one of the original two cards and is dealt one new
  card, then plays out under the normal dealer-hits-to-17 rule (whatever
  soft-17 handling the real dealer already uses). This is a genuine split
  and deal — not a reuse of any already-known outcome — but scoped
  entirely to the lottery; it is not the canonical round result and isn't
  replayed if a player disconnects/reconnects mid-draw.
  - One shared draw for the whole table. Every participating player's
    payout is scaled by their *own* X against that same shared outcome —
    this is not N independent per-player draws.
  - **Re-splitting (revision)**: if a new hand's second card itself forms
    another matching pair, it re-splits instead of standing on the pair —
    exactly like a real player hand (`Hand.split()`/`can_split()`), sharing
    the same `MAX_SPLITS = 4` cap the main game already uses (5 hands max
    per original starting card, 10 total across both — a hot run of 9s or
    tens can't spin out an unbounded hand tree). The original plan fixed
    this at always-exactly-two-hands; see the Payout revision below for why
    that no longer needs to be a hard rule.
- **Payout**. Let `halving_active = easy_mode or len(players) >= 4` — the
  *exact* existing flag from `DrinkTracker.apply_end_of_round`
  (`engine/drinking_rules.py:723`), reused verbatim, not reinvented:
  - Every new hand busts → **credit** yourself `min(X, your current
    last_round_sips)` — floored at 0, you can never end a round owing
    negative sips from this — and **hand out** `ceil(X/2)` if
    `halving_active` else `X` to another player (picker: see §3's
    "Handout recipient picker" bullet). The self-credit is never halved
    (halving softens drinking, not credits); the handout *is* halved,
    since it's sips the recipient will actually drink.
  - No new hand busts → drink `ceil(X/2)` if `halving_active` else `X`.
  - Anything in between (some hands bust, some don't) → **nothing
    happens** (no drink, no credit).
  - Rounding is always **up** (`math.ceil`), matching every other halving
    in the codebase (4-player/Easy Mode batching, the A♣ hard-switch
    half-protection) — never introduce a different rounding rule here.
  - **Why this scales to re-splitting**: keying the payout on the two
    extremes (all hands bust / no hand busts) rather than a fixed hand
    count means re-splitting into 3+ hands needs no new payout cases —
    more hands only ever makes both extremes rarer (harder to bust every
    hand, harder to stand every hand), which makes the event gentler on
    average as the hand count grows, never harsher. This is also why
    re-splitting could safely be turned back on: the original "always
    exactly two hands" rule existed to keep the old *fixed* N=2 payout
    formula well-defined, not because more hands were unsafe.
  - **Revision (Proposal A)**: the original payout was `(2 − busted) × X`
    (0 busted → `2X`, 1 busted → `X`) before halving — i.e. drinking was
    the outcome ~95% of the time a stake was entered, and the worst case
    (double stake) hit ~60% of the time, per a 200k-trial simulation of
    the real dealt hands. Dropping the one-bust case to a wash and halving
    the double-stake ceiling to a single stake roughly halves the expected
    sips per point staked, while keeping the both-bust credit as the one
    genuinely good outcome.
- Applies to **Drinking mode only** (Normal mode has no sip economy for
  this to plug into).

## 2. What already exists

Nothing yet — this is a new mechanic. But three existing subsystems are
direct precedent and should be reused, not reinvented:

- **`app/services/round_pipeline.py`** — the exact hook point. The lottery
  trigger check belongs right after `check_and_set_milestone(session)`.
- **`app/services/tick.py`** — the per-poll pending-state pattern (see
  `apply_milestone_forfeit`, the bust-handout pause-while-milestone-pending
  logic). The lottery's "wait for milestone to clear, then prompt, with a
  forfeit-to-0 timeout" behavior is structurally identical to how the
  milestone-handout window already pauses the bust-handout countdown.
- **`app/services/drink_tracker.award_sips()`** — the single sip-writing
  helper (`docs/planning/Improvements.md` item 1). Every sip event this
  feature produces (drink penalty, credit, handout) should go through it,
  the same way `apply_bust_vote_penalties` does today. Negative values
  (the credit case) are already supported and correctly skip milestone
  triggering per its docstring.
  - **Checked, no issue: can a lottery credit un-cross an already-claimed
    milestone?** No — `award_sips()` only adds a negative (credit) delta to
    `session.drinks.last_round_sips` (this round's owed total); the
    cumulative `session.drinks.sip_ticker` that `check_and_set_milestone()`
    actually checks against is only ever *increased* (`if sips > 0:` gate
    around the ticker update) — "Session total never decreases — credits
    offset within the round only" per the comment right above it. A
    milestone is also a permanent one-way claim (`milestones_claimed[boundary]`
    is never unset once written) regardless. Both mechanisms independently
    guarantee a lottery credit can never retroactively invalidate an
    already-distributed milestone handout — as long as the lottery's sip
    effects go through `award_sips()` rather than mutating the ticker
    directly, this is already handled, no new guard needed.

`Hand.can_split()`'s definition of "pair" (`cards[0].rank.blackjack_value
== cards[1].rank.blackjack_value`) is the existing, already-consistent way
this codebase treats a "10-value pair" (10/J/Q/K all count as one another)
— reuse it verbatim for trigger detection rather than writing a new
same-rank check.

## 3. Design decisions locked in during brainstorm

- Dealer does **not** literally bust in this event — resolved: the bolt-on
  draw generates a fresh outcome instead of reusing the (impossible, since
  dealer stood) "did the dealer bust" question from the real round.
  Recorded here so the reasoning isn't rediscovered later:
  a dealer whose starting pair is 18/20 always stands immediately, so
  there is no dealer-bust event from the real hand to reuse — the draw has
  to actually happen.
- This is a **separate, standalone event**, not merged into the existing
  Dealer Bust side bet (4.4) and not affecting its stats.
- **Drinking mode only** — no Normal-mode cash equivalent for now.
- **Trigger is pair-only** — a non-paired 19 (e.g. K+9) never qualifies.
  (It couldn't anyway — see §1's note that only these two pairs can leave
  the dealer standing on exactly two cards.)
- **Entry window is 20 seconds, non-responders default to `X = 0`** —
  same "abstain" behavior as the bust vote's timeout, no new forfeit
  concept. Resolves what happens on disconnect mid-entry for free (same
  answer as every other timed window in this pipeline).
- **A lottery credit can never un-cross an already-claimed milestone** —
  confirmed safe by existing code, not something to guard against
  separately. See §2's `award_sips()` bullet for the exact mechanism
  (`sip_ticker` only increases; `milestones_claimed` is a permanent
  one-way ledger).
- **Dealer is eligible** — "acting as player" for the purposes of this
  event, same as the existing Dealer Bust vote (4.4) doesn't exclude the
  dealer either.
- **Nobody drinks negatively from this event** — a player may enter with
  `X = 5` even if their own `last_round_sips` for the round is only, say,
  3; the self-credit in the both-bust case is capped at
  `min(X, current last_round_sips)` so their own total floors at 0. This
  cap applies **only to the self-credit** — the handout to the recipient
  is always the full (possibly-halved) `X`, uncapped by whatever the
  giver personally owed. Entry itself isn't validated against current
  owed sips at all — `X` is a free choice 0-5 regardless.
- **Handout recipient picker reuses `/give_bust_sip`'s exact pattern** —
  timed picker, forfeit-to-self on timeout, same shape, new pending-list
  target. No second parallel UI pattern for "pick who gets my sip."
- **Easy Mode / 4-player halving applies**, via the *same* `halving_active`
  flag `apply_end_of_round` already uses (`easy_mode or players >= 4`) —
  see §1's payout formula for exactly which amounts get halved (the drink
  penalty and the handout; never the self-credit) and the round-up
  (`math.ceil`) convention, matching every other halving in the codebase.

## 4. Card source for the draw — decided: new single deck

**Decided: Option B — a fresh, isolated single deck, scoped only to this
draw.** Zero interaction with the real shoe — no reshuffle-timing edge
cases, no card-economy skew for the next real round. Directly precedented
in this exact codebase: `Busfahrer-Plan.md` §4.1 makes the identical call
for the identical reason ("a fresh deck scoped to the [event] so it
doesn't interact with the main game's shoe/penetration tracking").
Trivially unit-testable (inject a seeded deck).

Concretely: `engine.blackjack.Deck()` (a single 52-card deck, shuffled)
constructed fresh inside `resolve_dealer_lottery()`, used only to deal the
two new hands' extra cards, then discarded — never touches
`session.shoe`. The rejected alternative (drawing from the live shoe) had
a real correctness cost: it could tip the shoe under its penetration
threshold mid-lottery, forcing an awkward reshuffle right as the next
round is about to deal, and would make the trigger/resolution harder to
unit-test deterministically.

## 5. Integration with the live app

### 5.1 GameRoom / round state
- Add `session.round._pending_dealer_lottery: dict | None` — set once the
  trigger condition is confirmed *and* no milestone is pending, cleared
  when everyone has submitted X (or the entry window times out). Shape:
  `{"expires_at": float, "entries": {name: int | None}}`, where
  `expires_at = time.monotonic() + DEALER_LOTTERY_ENTRY_WINDOW_SECONDS`
  (new constant in `app/config.py`, value `20`, alongside
  `BUST_VOTE_WINDOW_SECONDS`/`MILESTONE_TTL`). A per-poll tick function
  (mirrors `apply_milestone_forfeit`) resolves any entry still `None` to
  `0` once `expires_at` passes.
- Add `session.round._dealer_lottery_result: dict | None` — set once the
  draw resolves, mirrors `_bust_vote_result`'s "last result, shown once,
  expires after ~90s" pattern (`_serialize_last_milestone` is the model to
  follow for the expiry window).

### 5.2 Trigger + resolution logic (new: `app/services/dealer_lottery.py`,
mirrors `payout_tracker.py`'s scope — one small focused module)
- `check_dealer_lottery_trigger(session)` — called from
  `round_pipeline.apply_endround_pipeline`, right after
  `check_and_set_milestone(session)`. No-ops unless: drinking mode, dealer's
  final hand is a two-card matching-value pair worth 18 or 20, and no
  lottery is already pending/resolved this round.
- `resolve_dealer_lottery(session)` — called once every entry is in (or the
  window times out). No-ops (skips the draw, clears pending state) if every
  submitted entry is 0. Otherwise: deals the two split hands from an
  isolated mini-deck (per §4 — mirrors `engine/busfahrer.py`'s deck),
  plays each out via the same dealer-hits-to-17 logic the real dealer
  uses, computes `busted ∈ {0, 1, 2}`, then for each participant with
  `X > 0` calls `award_sips()` with the signed delta per §1's payout
  table (negative for the "both busted" credit case), passing a literal
  rule string directly (`"Dealer Lottery drink"` / `"Dealer Lottery
  credit"` / `"Dealer Lottery handout"`) — **no `classify_rule()` changes
  needed**: that function only classifies raw `drink_log` reasons during
  harvest; every out-of-band `award_sips()` caller (bust-vote handout,
  milestone forfeit) already supplies its own canonical rule string
  directly, and this feature follows the same pattern.
- Gate the pending-state's *reveal* (not just its creation) behind "no
  milestone pending," matching `tick.py`'s existing pattern of pausing one
  window while another is open — implemented as a two-phase
  `_dealer_lottery_eligible` flag (set once, right after milestone check)
  promoted to a real `_pending_dealer_lottery` (with a fresh `expires_at`)
  only once `_pending_milestone` is `None`, so the entry window's 20s
  clock never starts ticking while the milestone modal is still up.

### 5.3 Player routes (new, in `app/routes/admin.py` or a new
`app/routes/dealer_lottery.py`)
- `POST /dealer_lottery/enter` — body `{room_code, client_id, x}` (0-5);
  records this client's local player(s)' entry, mirrors `/cast_bust_vote`'s
  local-player-override handling for shared-device seats.
- Reuse `/give_bust_sip`'s exact pattern for the handout-recipient step
  (per §3's "Handout recipient picker" bullet) rather than adding a new
  route shape.

### 5.4 NPC participation
- Bots submit their entry the moment the pending state is created (no
  waiting on a countdown, mirrors "NPCs auto-vote 'pass' at deal time" for
  the Dealer Bust vote) — but the stake itself is now a real per-personality
  decision, not a hardcoded 0.
- `NPC_Player.decide_dealer_lottery_stake(current_owed)`
  (`engine/blackjack.py`) delegates to
  `engine/style_strategy.py`'s `decide_dealer_lottery_stake(profile, current_owed)`,
  which looks up the profile's mined `lottery_stakes` for the bucket
  matching how many sips the player currently owes this round
  (`_owed_bucket`: none/low/high) and returns the rounded average stake,
  clamped 0-5. "basic" personality, or any profile with no mined data for
  that bucket, falls back to `0` — identical to the old behavior.
- Every entry (human or NPC) is recorded via
  `app.services.decision_log.record_dealer_lottery_entry` into
  `session._dealer_lottery_decision_log`, exported via `/export_decisions`
  as a second sheet ("Dealer Lottery Entries") in the same XLSX workbook as
  the hand-decision log ("Hand Decisions") — one download, not two (the row
  shape still doesn't fit `_DECISION_COLUMNS`, so it's a separate sheet
  rather than mixed into the same one). Auto-forfeited (timed-out, unset →
  0) entries are deliberately NOT logged — that's a non-choice, not a real
  decision, and would pollute the mined tendency.
- `scripts/build_player_profiles.py`'s `build_lottery_stakes()` mines the
  "Dealer Lottery Entries" sheet the same way hand decisions are mined from
  "Hand Decisions": human-only rows, grouped by owed-bucket, kept only when
  a bucket clears `--min-samples`. Written into the profile JSON as a new
  `lottery_stakes` key alongside `deviations`.

### 5.5 Polling / serializer
- Add a `dealer_lottery` block to `AppState`
  (`app/models/state_schema.py`) and `serialize_state()`'s output,
  containing: whether a lottery is pending (and its countdown), this
  client's own entry status, and the last resolved result (mirrors
  `pending_milestone` / `last_milestone_result`'s shape and the 90-second
  "still show the last result" window). **This is a schema change** — see
  `docs/planning/Improvements.md` item 4 / the Pydantic work already
  landed; a new field means updating `AppState` in the same commit, or
  `extra="forbid"` will catch the drift immediately (which is the point).

### 5.6 Frontend
- New section in `templates/partials/index/_modals.html` (or its own
  small overlay) for the entry prompt (X stepper, 0-5) and result reveal
  (two new hands, cards, bust/no-bust per hand, payout applied).
- New JS in `static/js/ui/admin-settings.js` or a small new
  `dealer-lottery.js`, following the milestone-modal's poll → render →
  submit → re-poll shape rather than inventing a new one.
- Update `docs/Rules.md` with a new subsection (adjacent to 4.4 Side Bet
  Dealer Bust) once the mechanic is final, and `docs/Comprehensive-Example.md`
  per the `Ruleset-Improvement.md` checklist (that doc doesn't currently
  list this feature since it predates this brainstorm — add it there too).

## 6. Suggested build order

1. [x] Trigger + pure resolution logic (`app/services/dealer_lottery.py`),
   fully unit-testable without Flask (mirrors `payout_tracker.py`'s
   scope) — `tests/app/test_dealer_lottery.py` (28 tests) covers: trigger
   fires only on 9-9/ten-pair two-card dealer hands, never on non-paired
   19, waits for milestone to clear, skip-if-all-zero, all four
   payout-table branches, halving at 4+ players and under Easy Mode, the
   handout picker + its forfeit, and confirms (per §3's locked-in
   decision) a credit never touches the cumulative `sip_ticker`.
2. [x] Wired into `round_pipeline.py` (trigger check, right after
   `check_and_set_milestone`) and `tick.py` (steps 6-8: start the entry
   window once milestone clears, entry-window forfeit, handout-window
   forfeit).
3. [x] `award_sips()` hookup — turned out to need **no** `classify_rule()`
   changes (see §5.2's note: out-of-band `award_sips()` callers pass their
   own literal rule string, they don't route through `classify_rule`).
4. [x] Player routes in `app/routes/polling.py`: `POST /dealer_lottery/enter`
   (mirrors `/cast_bust_vote`'s local-player-override handling; resolves
   immediately once every entrant has answered rather than waiting out
   the full window) and `POST /dealer_lottery/give_sip` (mirrors
   `/give_bust_sip` exactly). 9 route-level tests added.
5. [x] `AppState` schema fields (`DealerLotteryOut` / `DealerLotteryPendingOut`
   / `DealerLotteryResultOut` in `app/models/state_schema.py`) + the
   `dealer_lottery` block in `serialize_state()`. Also added
   `_dealer_lottery_result_seq` (bumped on every new draw) so the frontend
   can detect a fresh result the same way it does for
   `bust_handout_seq`/`round_over_seq` — not originally called out in
   §5.5, added once the toast-reveal design made the need concrete.
6. [x] NPC auto-entry — NPCs auto-submit `X = 0` the moment
   `maybe_start_dealer_lottery()` creates the pending window.
7. [x] Frontend: entry modal (`#dealer-lottery-modal-overlay`, per-local-player
   stake **slider** (0-5, live value display) + Enter button, countdown
   synced against the server the same way `_openBustVoteModal` does),
   handout picker (`#dealer-lottery-give-overlay`, reuses
   `#bust-give-card`'s CSS), and a **visual reveal modal**
   (`#dealer-lottery-reveal-overlay`, gated on `result_seq`) showing the
   dealer's pair actually splitting into two real hands via `handBlock()`/
   `cardEl()` — the exact same card-rendering functions the main table
   uses — with score/BUST/STAND tags and a payout summary line. Replaced
   an earlier plain-text toast (`showDealerLotteryToast`) once real card
   visuals were requested; the give-panel now also waits for the reveal
   modal to close (`_dealerLotteryRevealOpen`) so the two popups never
   stack. All wired into `_syncDigitalUI` / `_syncRoundEffects` in
   `table.js`, alongside the equivalent bust-vote hooks. Backend gained
   `hand_a_score`/`hand_b_score` on the result (added once the visual
   needed real totals, not just bust/stand booleans).
8. [x] Manual playtest: two layers now. (a) Live in-browser: ~20 real
   rounds played without the ~9.5%-per-round pair hitting naturally
   (see the probability note below — not a bug, just variance), so the
   render → submit → resolve → toast → handout chain was verified by
   injecting a synthetic `dealer_lottery` state into the live page and
   exercising every function directly (entry rendering, submit → real
   POST → real server-side rejection when no genuine lottery is open,
   result toast text/styling, handout panel → real POST). No console or
   server errors throughout. (b) The natural-trigger gap that left open
   is now closed properly, not by chance: `tests/app/test_dealer_lottery
   .py::test_dealer_lottery_triggers_through_a_real_dealt_round` rigs a
   real `Shoe` so `initial_deal()` genuinely deals the dealer K,Q, then
   drives the *entire* production path — `/command deal` → `stand` ×2 →
   `_after_player_action` → `dealer_turn` → `_resolve_endround` →
   `apply_endround_pipeline` → a real `/state` poll's `tick()` — and
   confirms the dealer really lands on 20 and the lottery opens with a
   real countdown. Passed first run.

**Trigger probability, for context on step 8:** a two-card 9-9 or
ten-value pair happens on ~9.5% of rounds (`C(4,2)/C(52,2)` for 9-9 plus
`C(16,2)/C(52,2)` for any ten-pair, per a single fresh deck — the ratio
holds for multi-deck shoes too). Over ~20 rounds that's roughly an 88%
chance of at least one trigger, so not hitting it live was within normal
variance, not a sign of a detection bug — confirmed separately by the
rigged-shoe integration test above.

**Still to build:** nothing — all 8 build-order steps and both
documentation follow-ups (§7) are done. This feature is complete.

## 7. Documentation follow-ups

- [x] `docs/Rules.md` — new **§5.9 Dealer Lottery**, not 4.6 as originally
  guessed: the mechanic runs after Milestone Handouts (5.8), so it
  belongs in "Drinking Rules (End of Round)" (§5), not the pre-deal Side
  Bets under §4. Also added a row to §6.1's halving table (drink/handout
  halved, self-credit never halved) and a ToC entry.
- [x] `docs/Comprehensive-Example.md` — standalone "Bonus illustration"
  section (matches the existing Milestone-Handouts-style treatment for
  mechanics that need specific dealt cards rather than fitting a full
  round), plus a Quick Reference table row. Also added the item to
  `Ruleset-Improvement.md`'s checklist (it postdates that checklist, so
  it wasn't on the original list).
- [x] `docs/.rules_sync.json` re-pinned via `python scripts/rules_sync.py
  update` — the drift checker correctly flagged that `Rules.md` changed
  without `drinking_rules.py` changing, since this mechanic lives in
  `dealer_lottery.py`/`round_pipeline.py`/`tick.py` instead; expected,
  not a real drift.
- [x] `docs/planning/TODO.md` — bullet removed now that the feature is
  fully built and tested, not just planned.
