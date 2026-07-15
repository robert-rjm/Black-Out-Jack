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
- **The draw** — the dealer's pair is split into two fresh hands for this
  event only: each keeps one of the original two cards and is dealt one new
  card, then plays out under the normal dealer-hits-to-17 rule (whatever
  soft-17 handling the real dealer already uses). This is a genuine split
  and deal — not a reuse of any already-known outcome — but scoped
  entirely to the lottery; it is not the canonical round result and isn't
  replayed if a player disconnects/reconnects mid-draw.
  - One shared draw for the whole table. Every participating player's
    payout is scaled by their *own* X against that same shared outcome —
    this is not N independent per-player draws.
  - No re-splitting even if one of the two new hands itself draws a
    matching pair — always exactly two hands, one draw, done.
- **Payout** (`N = 2`, fixed, since there's no re-splitting). Let
  `halving_active = easy_mode or len(players) >= 4` — the *exact* existing
  flag from `DrinkTracker.apply_end_of_round` (`engine/drinking_rules.py:723`),
  reused verbatim, not reinvented:
  - Both new hands bust → **credit** yourself `min(X, your current
    last_round_sips)` — floored at 0, you can never end a round owing
    negative sips from this — and **hand out** `ceil(X/2)` if
    `halving_active` else `X` to another player (picker: see §3's
    "Handout recipient picker" bullet). The self-credit is never halved
    (halving softens drinking, not credits); the handout *is* halved,
    since it's sips the recipient will actually drink.
  - Otherwise → drink `ceil(((2 − busted) × X) / 2)` if `halving_active`
    else `(2 − busted) × X` (0 busted → `2X` before halving, 1 busted →
    `X` before halving).
  - Rounding is always **up** (`math.ceil`), matching every other halving
    in the codebase (4-player/Easy Mode batching, the A♣ hard-switch
    half-protection) — never introduce a different rounding rule here.
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
- Bots auto-submit `X = 0` the moment the pending state is created —
  mirrors "NPCs auto-vote 'pass' at deal time" for the Dealer Bust vote.

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
4. [ ] Player route(s) + reuse of the bust-vote-handout recipient flow —
   `submit_dealer_lottery_entry()` / `give_dealer_lottery_sip()` exist as
   pure functions; still need the Flask routes calling them
   (`POST /dealer_lottery/enter`, handout picker per §5.3).
5. [ ] `AppState` schema fields + `serialize_state()` block (§5.5).
6. [x] NPC auto-entry — NPCs auto-submit `X = 0` the moment
   `maybe_start_dealer_lottery()` creates the pending window.
7. [ ] Frontend prompt + result reveal (§5.6).
8. [ ] Manual playtest: force a 9-9 and a ten-pair dealer hand (via a
   debug hook, once routes/frontend exist) with 2-4 players, covering:
   all-zero skip, mixed X values, both-bust credit + handout picker,
   partial-bust drink amounts, a pending milestone delaying the prompt
   correctly, a disconnected player timing out to 0.

**Still to build:** steps 4, 5, 7, 8 — the engine core (steps 1-3, 6) is
done and tested, but nothing is reachable from the UI yet.

## 7. Open documentation follow-ups

- `docs/Rules.md` — new subsection under §4 (Side Bets), likely 4.6.
- `docs/Comprehensive-Example.md` — add per `Ruleset-Improvement.md`'s
  existing checklist format.
- `docs/planning/TODO.md` — already updated to point at this plan doc;
  check it back off entirely (remove the bullet) once this ships.
