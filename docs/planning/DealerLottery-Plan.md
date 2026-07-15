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
  X = 0-5. Bots auto-submit 0. If everyone (who responds) picks 0, the
  lottery is skipped entirely — no draw happens, nothing is logged.
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
- **Payout** (`N = 2`, fixed, since there's no re-splitting):
  - Both new hands bust → reduce your own sips owed by `X`, and hand out
    `X` to another player (via the existing bust-vote-handout-style
    picker — see §4.3).
  - Otherwise → drink `(2 − busted) × X` (0 busted → `2X`, 1 busted → `X`).
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

## 4. Open questions (need decisions before/while building)

- **Dealer's own eligibility** — can the player who dealt this round also
  enter the lottery against their own hand's pair? Recommend yes, matching
  how the existing Dealer Bust vote (4.4) doesn't exclude the dealer
  either — but confirm.
- **Card source for the draw** — draw the two lottery cards from the live
  `session.shoe`, or from an isolated one-off mini-deck that doesn't touch
  shoe/penetration tracking? Recommend the isolated mini-deck, mirroring
  `Busfahrer-Plan.md` §4.1's identical call ("a fresh deck scoped to the
  [event] so it doesn't interact with the main game's shoe/penetration
  tracking") — this event shouldn't skew the real shoe's card economy for
  the next round.
- **Easy Mode / 4-player halving interaction** — should lottery sips be
  subject to the existing "halve all end-of-round sip totals" halving
  (Easy Mode toggle, or automatic at 4+ players)? Recommend yes, for
  consistency with every other end-of-round sip source — needs confirming
  where exactly that halving is applied today so the lottery's
  `award_sips()` calls land on the correct side of it.
- **Handout recipient picker** — reuse the existing bust-vote-handout flow
  verbatim (winner picks a recipient via a timed `/give_bust_sip`-style
  window, forfeits to self after timeout) or build a lighter-weight
  variant? Recommend reusing the existing flow's shape exactly, just
  pointed at a new pending-handout list, to avoid a second parallel UI
  pattern for the same "pick who gets my credited sip" interaction.
- **What if a player disconnects mid-entry** — same question the bust-vote
  window already answers (non-responders default to their existing
  behavior at timeout). Recommend the same default-to-0-on-timeout used
  everywhere else in this pipeline, no new special case.

## 5. Integration with the live app

### 5.1 GameRoom / round state
- Add `session.round._pending_dealer_lottery: dict | None` — set once the
  trigger condition is confirmed *and* no milestone is pending, cleared
  when everyone has submitted X (or the entry window times out). Shape:
  `{"expires_at": float, "entries": {name: int | None}}`.
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
  isolated mini-deck (see open question above), plays each out via the
  same dealer-hits-to-17 logic the real dealer uses, computes
  `busted ∈ {0, 1, 2}`, then for each participant with `X > 0` calls
  `award_sips()` with the signed delta per §1's payout table (negative for
  the "both busted" credit case) tagged with a new rule string, e.g.
  `"Dealer Lottery"` / `"Dealer Lottery credit"`, added to
  `classify_rule()` in `app/services/utils.py`.
- Gate the pending-state's *reveal* (not just its creation) behind "no
  milestone pending," matching `tick.py`'s existing pattern of pausing one
  window while another is open — add this alongside steps 3-4 of `tick()`.

### 5.3 Player routes (new, in `app/routes/admin.py` or a new
`app/routes/dealer_lottery.py`)
- `POST /dealer_lottery/enter` — body `{room_code, client_id, x}` (0-5);
  records this client's local player(s)' entry, mirrors `/cast_bust_vote`'s
  local-player-override handling for shared-device seats.
- Reuse `/give_bust_sip`'s exact pattern for the handout-recipient step
  (per §4's open question) rather than adding a new route shape.

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

1. Trigger + pure resolution logic (`app/services/dealer_lottery.py`),
   fully unit-testable without Flask (mirrors `payout_tracker.py`'s
   testing style) — cover: trigger fires only on 9-9/ten-pair two-card
   dealer hands, never on non-paired 19, never when a milestone is
   pending, skip-if-all-zero, and the four payout-table branches.
2. Wire into `round_pipeline.py` + `tick.py`'s pending/forfeit gating.
3. `award_sips()` hookup + new `classify_rule()` entries + CSV categories.
4. Player route(s) + reuse of the bust-vote-handout recipient flow.
5. `AppState` schema fields + `serialize_state()` block.
6. NPC auto-entry.
7. Frontend prompt + result reveal.
8. Manual playtest: force a 9-9 and a ten-pair dealer hand (via seeded
   shoe or a debug hook) with 2-4 players, covering: all-zero skip, mixed
   X values, both-bust credit + handout picker, partial-bust drink amounts,
   a pending milestone delaying the prompt correctly, a disconnected
   player timing out to 0.

## 7. Open documentation follow-ups

- `docs/Rules.md` — new subsection under §4 (Side Bets), likely 4.6.
- `docs/Comprehensive-Example.md` — add per `Ruleset-Improvement.md`'s
  existing checklist format.
- `docs/planning/TODO.md` — replace the two old draft bullets (lines
  33-45) with a pointer to this plan doc once built.
