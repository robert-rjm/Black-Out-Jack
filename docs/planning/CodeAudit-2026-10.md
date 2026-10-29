# Code Audit — October 2026

Scope: the whole repository at `cafddf2` (branch `update/Rob`). The main focus is
the RuleSet work from the last three commits:

- `d43a53a` feat: add rules registry and per-room RuleSet
- `a9774fd` feat: gate drinking rules by RuleSet (Phase 2)
- `cafddf2` feat: gate table split aces bj

Method: I read the three diffs in full and traced every `rules.on(...)` call
site and every event construction site. I checked them against
`RuleToggles-Implementation.md`, ran the test suite, and confirmed the
suspected bugs with a short probe script (results quoted where relevant). The
rest of the codebase got a lighter review, focused on input validation,
auth, state handling and deployment.

Test baseline: **901 passed** in about 20 s. `tests/app/test_mode_switch.py`
failed once in four runs (see B5).

Severity scale: **High** = wrong drinks or payouts in normal play, or a server
that can be knocked over · **Medium** = wrong behaviour in a reachable but
narrower case, or a trap for the next phase · **Low** = cosmetic, cleanup or
hardening · **Info** = observation, no action strictly needed.

---

## Summary

| # | Area | Severity | Finding |
|---|---|---|---|
| G1 | Gates | ✅ Fixed | The ruleset is stored twice (`config.rules` and `session.rules`), and the Phase 3 plan writes only one |
| G2 | Gates | ✅ Fixed | Switching to a BOJ table resets the new room to `DEFAULT_RULES` (the wild card toggle is lost today; a custom ruleset will be lost later) |
| G3 | Gates | ✅ Fixed | The insurance-vote modal shows the full BJ multiplier (`bj_mult`) even when multipliers are off |
| G4 | Gates | ✅ Fixed | Referee mode ignores `table.split_ace_bj` |
| G5 | Gates / Normal mode | Deferred (Normal-mode overhaul) | Normal (casino) mode inherits drinking table rules: a split A+10 pays 3:2 |
| G6 | Gates | ✅ Fixed | Turning off `insurance.auto_cap` also changes behaviour on a dealer BJ with a 10 up-card |
| G7 | Gates | ✅ Fixed | `milestone.back_to_back` has no gate |
| G8 | Gates | ✅ Fixed | The Wild Card "earn your milestone first" block still applies when milestones are off |
| G9 | Gates | ✅ Fixed | The UI and serializers don't know about rules yet (buttons for rules that are off still show) |
| G10 | Gates / tests | ✅ Fixed | The registry-driven "off means off" test from plan §6.2 is missing, so a new rule can ship without a gate |
| G11 | Gates | ✅ Fixed | `rules: RuleSet = FULL` defaults silently turn a missed call site into "everything on" (G3 is an example) |
| G12 | Gates | ✅ Fixed | `RuleSet` equality and preset detection quirks |
| G13 | Gates | Deferred (referee) | Referee `insurance` action is accepted, with a wrong log line, when `insurance.bj_vote` is off |
| B1 | Referee | Deferred (referee) | The BLACKJACK button followed by WIN pays the BJ bonus **twice** |
| B2 | Input validation | ✅ Fixed | `/setup` and `/update_settings` have no upper bounds, so a request with `num_hands=10^6` can lock up the server |
| B3 | Security | Medium | The join rate limit trusts `X-Forwarded-For`, and `/state` and the exports can be used to probe room codes with no limit |
| B4 | Security | Medium | Anyone who knows a reserved room code can run `/setup` before the host does |
| B5 | Tests | Medium | `test_mode_switch` is flaky (unseeded shoe) |
| B6–B11 | Misc | Low / Info | Rate-limit bookkeeping, runtime bundling, missing security headers, unpinned dependencies, personal data committed to the repo |
| P1–P10 | Production | — | Not production-ready as a standalone app: in-memory state, a single thread, no CI or monitoring, legal and age-gate issues (details in Part C) |

**Verdict on the gates:** Phase 2 does what it set out to do in the digital
engine. Every gate I traced sits at the source (it suppresses the message
instead of filtering it afterwards), the Hard Switch "mode vs. penalty" trap
from plan §3.1 is handled correctly in all three engines, and the default
room reproduces today's behaviour. The problems sit at the edges: a second
copy of the ruleset, a serializer that never receives the rules, the referee
path, Normal mode, and one semantic overreach (`auto_cap`). Fix G1, G2 and
G10 before starting Phase 3 (Admin UI). Once admins can change rules, these
latent issues show up in real games.

---

## Part A — RuleSet gates (priority)

### What was verified as correct

These were traced by hand and match the plan:

- **Aces** (`on_card_dealt`): the gate returns before any message *or*
  A♣ protection flag is produced. Dealer-player A♣ partial protection and the
  deferred credit both depend on `ace.clubs.player`. A♣ half protection
  depends on `ace.clubs.dealer`, which depends on `switch.hard`.
- **Four Aces**: when `first_deal` is off, the flag that blocks the
  end-of-round check is never set, so `end_round` can still fire.
- **Hard Switch**: in `game_engine.dealer_turn` the role still rotates
  (`switch_this_round = "hard"`), but `exempt_dealer` is empty, so the dealer
  drinks their ordinary player sips. `cmd_endround`, `RoundManager` and
  `RefereeSession` all gate `hard_switch` itself. In those three paths
  `hard_switch` only drives the penalty and exemptions (rotation lives
  elsewhere), so this is consistent. The dealer-player's deferred A♣ credit
  then applies, which is correct (no hard switch means no double-dipping).
- **Loss extras**: the ×4 combo only applies when both rules are on, and a
  single rule adds +1.
- **Sweep**: the cancellation of the doubled-hand drink is skipped when
  `others.immunity.doubled` is off, so nobody gets back a sip they never drank.
- **BJ multipliers**: `_bj_breakdown` returns a flat 1× when the rule is off,
  and that flows through `on_blackjack` and `resolve_insurance_vote`.
- **Split-ace BJ** (digital): the flag is captured on the `Hand` at split time
  and passed on through re-splits. A split-ace 21 that isn't a BJ still
  auto-stands (`deal_pending_split_cards` and `cmd_split` both check
  `score() == 21`), so players are never asked to act on a 21.
- **Strategy / bots / hints / decision log**: all pass
  `split_tens=rules.on("table.split_tens")`.
- **App services**: lottery, targeted (start, proposal, perfect handout),
  milestones, worst-average and L badge all gate at trigger time, so a running
  event finishes on its own (as plan §4.2 intends).
- **Registry**: import-time validation (unique IDs, groups, presets, parent
  preset ≤ child preset, unlock order, cycles, nested presets) is solid.

---

### G1 — The ruleset is stored twice · ✅ Fixed

> **Fixed (2026-10-29).** `GameConfig.rules` is now the only copy.
> `RefereeSession.rules` is a property that reads `rules_source` (set by
> `GameRoom.__post_init__`), so writing `room.rules` or `config.rules` reaches
> the engine at once. Assigning `session.rules` inside a room raises
> `AttributeError`. The Phase 3 snippet in `RuleToggles-Implementation.md`
> §3.4 / §4.2 is corrected. Tests: `test_a_direct_config_write_reaches_the_engine`,
> `test_the_engine_session_refuses_its_own_copy_inside_a_room`.

**Issue.** `GameRoom.config.rules` and `GameRoom.session.rules` (on
`RefereeSession`) are two separate references. They are synced in
`GameRoom.__post_init__` and in the `GameRoom.rules` setter
(`app/models/game_room.py:451`, `:629`). Anything that assigns
`session.config.rules = ...` directly leaves the engine on the old rules. Two
things make this likely to happen:

1. `RuleToggles-Implementation.md` §4.2, which is the Phase 3 plan, has sample
   code that does exactly that:
   ```python
   session.config.rules = RuleSet(...)
   session.tracker.rules = session.config.rules   # tracker has no .rules
   ```
   Following the plan as written would desync the engine (aces, four aces,
   hard switch, BJ bonus, every end-of-round rule) while app-side gates
   (lottery, milestones, split prompts) use the new set. The result is a
   half-applied ruleset.
2. `GameConfig` is a plain dataclass, so nothing stops a direct write.

**Solution brainstorm.**
- *Best:* keep **one** store. Drop `rules` from `GameConfig` and let
  `GameRoom.rules` proxy to `self.session.rules`, the same way the other
  `RefereeSession` delegations work. `__post_init__` then sets the initial
  value on the session only.
- *Alternative:* keep `GameConfig.rules` as the only store and give
  `RefereeSession` a `rules_provider` callable (`lambda: room.config.rules`),
  so the engine reads live instead of holding a copy.
- *Minimum:* rename the field to `_rules` so direct writes stand out, and fix
  the §4.2 snippet to `session.rules = ...` (removing the `tracker.rules` line).
- Add a test: set `room.rules = X`, then assert `room.session.rules is X`. Also
  grep in a test that no code outside `game_room.py` writes `config.rules`.

---

### G2 — BOJ table split resets the rules · ✅ Fixed

> **Fixed (2026-10-29).** `build_game_room` takes `rules=` (full `RuleSet`)
> instead of `bust_vote_enabled`. `/setup` passes
> `DEFAULT_RULES.with_rule("side.bust_vote", ...)`, and the BOJ split passes
> `session.rules`. The open question below (which rules a Normal→Drinking split
> should start with) is still open: today the new table copies the old one's.
> Test: `test_split_table_keeps_the_old_tables_rules`.

**Issue.** `app/services/boj_switch.py:220` builds the new Drinking table with
`build_game_room(..., bust_vote_enabled=session.bust_vote_enabled, ...)`, and
`room_factory.py:50` starts from `DEFAULT_RULES`. Everything else in the old
room's `RuleSet` is dropped. **Today** this means an admin who switched the
Wild Card off finds it back on at the new table. **After Phase 3** every
house rule will be lost on a BOJ split.

**Solution brainstorm.**
- Replace the `bust_vote_enabled` parameter of `build_game_room` with
  `rules: RuleSet = DEFAULT_RULES`. `/setup` passes
  `DEFAULT_RULES.with_rule("side.bust_vote", ...)` and the BOJ switch passes
  `session.rules`.
- Open question for the BOJ case: the old table is *Normal* mode. Should the
  new Drinking table use the old table's (mostly meaningless) ruleset, the
  default, or the Starter preset (StarterSet open question 3)? Pick one on
  purpose instead of by accident.

---

### G3 — Insurance modal shows the wrong multiplier · ✅ Fixed

> **Fixed (2026-10-29).** `serialize_hand(hand, *, rules, ...)` now requires
> the room's rules (no default, on purpose) and passes them to `_bj_multiplier`.
> Test: `test_bj_mult_in_the_state_follows_the_multiplier_rule`.

**Issue.** `app/services/round_state.py:137` serializes
`"bj_mult": _bj_multiplier(hand)` with no rules, so it uses the `FULL`
default. `static/js/ui/table-modals.js:141` uses this to tell players how many
sips the insurance vote is worth. With `bonus.blackjack.multipliers` off, a
suited A♠ J♠ shows **×8** in the vote modal, but resolution uses ×1.
Confirmed with the probe: `bj_mult serialized: 8`.

**Solution brainstorm.**
- Give `serialize_hand` a `rules` parameter (callers in `serializer.py`
  already have `session`) and pass it to `_bj_multiplier`.
- Better: compute `bj_mult` once in the insurance serializer
  (`serializers/insurance.py`) for the BJ hand being voted on, instead of for
  every hand on every poll.
- This bug is the reason for G11.

---

### G4 — Referee mode ignores `table.split_ace_bj` · ✅ Fixed

> **Fixed (2026-10-29).** The referee `action ... split` path sets
> `split_ace_bj` on both hands from `self.rules`, as `Hand.split()` does in
> digital mode. The shared `split_slot()` helper idea below is not done.
> Tests: `test_referee_split_ace_21_is_a_blackjack_by_default`,
> `test_referee_split_ace_21_is_a_plain_21_when_the_rule_is_off`.

**Issue.** `engine/referee.py:304` (the `action ... split` path) creates
`Hand(from_split=True)` and never sets `split_ace_bj`, so both hands keep the
default `True`. Confirmed with the probe: with the rule off, a referee split
A + K still reports `is_blackjack() == True`. Plan §9 lists "two engines
drift" as a risk and asks for the referee path to be in the parametrized
test, but it isn't.

**Solution brainstorm.**
- In `cmd_action` split, set
  `hand.split_ace_bj = new_hand.split_ace_bj = self.rules.on("table.split_ace_bj")`.
- Longer term, move split bookkeeping (flags, chain counter, `split_count`)
  into one `Hand.split_slot()` helper that both the digital and referee paths
  call. Only the card moving differs between them.

---

### G5 — Normal (casino) mode uses drinking table rules · Medium

**Issue.** Every room starts from `DEFAULT_RULES`, Normal mode included. The
`table.*` rules aren't gated on `drinking_mode` at the scoring level, so in a
Normal table:

- A split Ace + 10 is a Blackjack and `payout_tracker.py:202` pays it
  **2.5×** (3:2). Casino rules, and the intent of `Rules-Normal.md`, treat it
  as a plain 21 paid 1:1.
- `Rules-Normal.md` says "Split aces: one card each, then both hands stand",
  but nothing enforces that. Players can hit, double and re-split split Aces.

This existed before the gates. The new rule now makes it easy to fix.

**Solution brainstorm.**
- Add an effective-rules concept: `GameRoom.rules` returns `NORMAL_RULES`
  (`table.*` off, drinking rules irrelevant) when `drinking_mode` is False.
  Alternatively, gate in `perform_split`:
  `hand.split_ace_bj = session.drinking_mode and session.rules.on(...)`.
- Enforce "split aces: one card, then stand" in Normal mode. In
  `deal_pending_split_cards` and `cmd_split`, set `hand.stood = True` after the
  second card when the hand is a split-Ace hand and the table isn't drinking.
- Add a Normal-mode payout test: split A+10 → 2.0× return.

---

### G6 — `insurance.auto_cap` reaches further than the rule · ✅ Fixed

> **Fixed (2026-10-29).** Decision: a dealer Blackjack never cancels a rule that doesn't need a win. Nobody beats it, so the win-only bonuses can't fire anyway, but the 5-card-21 handout and the all-hand bonus now always fire, whatever `insurance.auto_cap` says. Before the gates they were suppressed on every dealer Blackjack, so this is a deliberate rule change. `insurance.auto_cap` only switches the net-loss cap. The Case 3 log line follows the rule. Rules.md §5.4 / §5.5 and the catalog entry say so, and `rules_sync` is re-pinned. Tests: `test_dealer_blackjack_keeps_the_five_card_handout_whatever_the_cap`, `test_dealer_blackjack_keeps_the_sweep_whatever_the_cap`, `test_dealer_bj_keeps_21_five_card_handout`, `test_sweep_still_fires_against_a_dealer_bj`.

**Issue.** The rule is "Auto-insurance cap (**Ace up-card**)". Plan §3.1 only
specified gating `_dealer_bj_drinks` in `on_round_end`. The implementation
also changes two other places:

- `on_hand_resolved`: `dealer_bj = dealer_bj and rules.on("insurance.auto_cap")`
- `check_all_hands_sweep`: `if dealer_bj and rules.on("insurance.auto_cap")`

Before this change, those two suppressions ran on *every* dealer Blackjack,
including one built from a 10 up-card, which has nothing to do with
insurance. With the cap off, a 10-up dealer BJ now also allows the 5-card-21
handout and sweeps. `test_dealer_blackjack_no_longer_suppresses_five_card_handout_when_cap_is_off`
locks this in, so it may be intended, but nothing documents it.

Also, `resolve_insurance_vote` Case 3 logs "auto-insurance applies, normal max
sips only" even when the cap is off.

**Solution brainstorm.**
- Decide and write down the rule: "Dealer BJ suppresses win bonuses" is
  either part of `insurance.auto_cap` (rename or re-describe it) or a separate
  always-on core behaviour.
- If it's separate, pass `dealer_shows_ace` into `HandResolvedEvent` /
  `AllHandsSweepEvent` and only drop the suppression when
  `dealer_shows_ace and not auto_cap`.
- Make the Case 3 message depend on `rules.on("insurance.auto_cap")`.
- Update the Rules-Catalog entry so the quiz (Part E) can ask about it
  correctly.

---

### G7 — `milestone.back_to_back` is not gated · ✅ Fixed

> **Fixed (2026-10-29).** The log callout and the `milestone_run_holder` / `milestone_run_length` badge are gated. The run is still counted, so turning the rule back on mid-session is accurate. Test: `test_back_to_back_callout_off`.

**Issue.** The registry declares it toggleable, but no code checks it
(`drink_tracker.note_milestone_assigned` always logs the callout, and the
serializer always shows it). Turning it off alone does nothing. It is only
"off" in practice because its parent `milestone.handout` stops milestones
entirely.

**Solution brainstorm.** Gate the log line in `note_milestone_assigned` and
the serializer field. Alternatively, if it's too cosmetic to deserve a toggle,
fold it into `milestone.handout` and drop the ID. That's allowed while the
registry is pre-release; after share codes exist IDs are append-only, so
decide now.

---

### G8 — Wild Card milestone block ignores the milestone rule · ✅ Fixed

> **Fixed (2026-10-29).** The block only runs with `milestone.handout` on. Test: `test_milestone_block_only_applies_when_milestones_are_on`.

**Issue.** `app/routes/wild_card.py:121` refuses a press when the player is
≤10 sips from a milestone ("earn it first!"). With `milestone.handout` off
there is nothing to earn, but the press is still blocked.

**Solution brainstorm.** Wrap the block in
`if session.rules.on("milestone.handout"):`. Add a test next to
`test_milestone_handout_off`.

---

### G9 — Serializers and UI don't know about rules yet · ✅ Fixed

> **Fixed (2026-10-29, Phase 3).** `/state` carries `rules` (`preset`, `enabled`, `effective`, `queued`; ID lists only), and `GET /rules_registry` serves names and groups once. The frontend checks `rulesOn(id)`: the Targeted Drinking start section and the name-tap proposal hide when `event.targeted` is off (a run already going still shows, so it can be cancelled). Bust vote and Wild Card were already driven by their state flags. Tests: `tests/app/test_house_rules.py`.

**Issue.** Nothing under `app/services/serializers/` reads `rules`. With a rule
off, its UI still shows: Targeted start/propose buttons (the server refuses
with a message), milestone progress, lottery hints, the Split-10s honor
copy, and so on. Plan §3.2 says "The serializer hides the start/propose UI".
That is fine while Phase 3 doesn't exist, but it should go on the Phase 3
checklist.

**Solution brainstorm.** Send `rules.effective` (ID list) in `/state` once (or
on `state_seq` change), as the plan suggests, and have the frontend check
`rulesOn(id)` before rendering each feature's entry point. Prefer this to
adding a boolean per feature to the serializer.

---

### G10 — No registry-driven coverage test · ✅ Fixed

> **Fixed (2026-10-29).** `tests/engine/test_rules_gate_coverage.py` maps every toggleable rule ID to the test that switches it off, and fails when a rule is missing from the map or the named test doesn't exist. Writing the map turned up four rules with no gate test: `milestone.worst_average`, `event.targeted.perfect_handout`, `event.wild_card` and `event.wild_card.targeted`. Those tests are added. Not done: running the engine tests through the referee path, and the Starter simulation smoke test (needs Phase 4's `--preset`).

**Issue.** Plan §6.2 / §9 says the "off means off" test is *parametrized over
the registry*, so that "a new rule without a test fails the registry-coverage
check". The tests that exist (`tests/engine/test_rules_gates.py`,
`tests/app/test_rules_gates_app.py`) are good but hand-written per rule.
Nothing fails when a rule is added to `RULES` without a gate. G7 shows this
already happened. Plan §6.3's "every event constructed without `rules=`
equals FULL" test and the Starter-vs-Full simulation smoke test are also
missing, and the referee path has no gate tests (see G4).

**Solution brainstorm.**
- Add a `GATE_TESTS: dict[str, Callable]` map in a test module, keyed by rule
  ID, and a test asserting `set(GATE_TESTS) == {r.id for r in RULES if r.preset != "locked"}`.
  Each entry runs the scenario under `FULL` and `FULL.with_changes(off=[id])`
  and checks the rule's `csv_labels` appear and then disappear.
- Run the engine-level entries through `RefereeSession` as well (a
  `@pytest.mark.parametrize("engine", ["digital", "referee"])`).
- Add the plan's `--preset starter` simulation smoke test once Phase 4 adds
  the flag.

---

### G11 — `rules=FULL` defaults hide missed call sites · ✅ Fixed

> **Fixed (2026-10-29).** The same test file walks the AST of `app/` and `engine/` and fails on any call to an event class or `DrinkingRules` helper that takes `rules` but isn't given it. The list of targets is read from the signatures, so new helpers are covered automatically. The defaults stay. Checked: putting back the old G3 call makes the test fail.

**Issue.** Every event dataclass and helper defaults to `rules=FULL`, by design
(plan §6.3), so old call sites keep today's behaviour. The downside: forgetting
to pass `rules` is silent and means "everything on". G3 is exactly this bug.

**Solution brainstorm.**
- Keep the defaults for engine and unit-test convenience, but add a static
  test: parse `app/**/*.py` and `engine/referee.py` / `engine/blackjack.py`
  with `ast`, and fail if any `*Event(` call or any call to `_bj_multiplier`,
  `_bj_breakdown`, `check_four_aces` or `dealer_21_five_cards` lacks a
  `rules=` keyword.
- Or make `rules` keyword-only with no default in the event classes, and
  give tests a `make_event(**kw)` helper that fills in `FULL`.

---

### G12 — `RuleSet` equality and preset quirks · ✅ Fixed

> **Fixed (2026-10-29).** Locked IDs are always added to `enabled`, `preset` is derived from the content (it is no longer a constructor argument and isn't part of equality), and `waiting_on_parent()` lists rules switched on whose parent is off, for the settings UI. The Phase 3 snippet is updated. Tests: `test_a_set_built_from_ids_matches_its_preset`, `test_waiting_on_parent_lists_children_of_off_parents`.

**Issue.**
- `preset` takes part in `__eq__`/`__hash__`, so `RuleSet(PRESETS["full"])`
  (preset `None`) != `FULL` (preset `"full"`) even though they're identical.
  This will matter for "is anything queued?" comparisons in Phase 3.
- `_preset_for(enabled)` compares the raw `enabled` set with presets that
  include locked IDs. A set built without the locked IDs (they're implicit)
  never gets a preset label.
- `with_changes(on=[child])` while the parent is off stores the child as
  enabled but not effective. That's correct, but the settings UI must show it
  as "on, waiting for parent", or admins will be confused.

**Solution brainstorm.** Normalise `enabled |= LOCKED` in `__post_init__`,
derive `preset` from content (`field(compare=False)` or a property via
`_preset_for`), and expose `pending_children()` for the UI.

---

### G13 — Referee `insurance` action with the vote rule off · Low

**Issue.** `engine/referee.py:321` accepts `action <p> insurance` and logs
"insured — Blackjack plays as regular 21, no bonus drinks". With
`insurance.bj_vote` off, resolution coerces `insured=False` and pays the
normal BJ bonus, so the log is wrong. It also means the hand is excluded from
`_pending_bj_hands`, and the bonus only arrives through the insurance path.
That works, but by accident.

**Solution brainstorm.** Reject the action when the rule is off ("Insurance
votes are switched off at this table"), and hide the INSURANCE button in the
referee UI.

---

## Part B — General code audit

### B1 — Referee mode pays the Blackjack bonus twice · High

**Issue.** In referee mode the UI has a **BLACKJACK** action button
(`_game.html:106` → `action <p> blackjack`) and a **WIN** result button
(`result <p> win`). Both append the same hand to `_pending_bj_hands`
(`referee.py:332` and `:375`; the second only checks `not hand.insured`).
A referee who presses BLACKJACK and then records the WIN fires the bonus
twice, so every other player drinks double. Confirmed with the probe:
`pending bj entries: 2`.

**Solution brainstorm.**
- Dedupe in `cmd_result`: skip the append if any queued entry already holds
  this `hand` (by identity).
- Or make `_pending_bj_hands` a dict keyed by `id(hand)`.
- Add a regression test that runs BLACKJACK → WIN → endround and asserts one
  "Blackjack bonus" row per other player.

---

### B2 — Unbounded numeric inputs (DoS) · ✅ Fixed

> **Fixed (2026-10-29).** Limits live in `app/config.py` (`MAX_WAGER` 20, `MAX_NUM_HANDS` 10, `MAX_NUM_DECKS` 8, `MAX_PLAYERS` 12, bet 2.5–1000, bankroll ≤ 100 000). They are at least as high as anything the UI offers. `/setup` clamps with the new `validators.clamp_int` / `clamp_float` (which also reject nan/inf), caps the player count, validates `mode`, and rejects a non-list `npcs` or a non-dict `personalities`. `/update_settings` ignores out-of-range values, as it already did for decks, and refuses to queue seats past `MAX_PLAYERS`. Found along the way: a bot personality named a file path (`engine/player_profiles/<name>.json`), so `../..` could load any `.json` file on the server. Only plain names (`[A-Za-z0-9_-]`) get through now. Tests: `tests/app/test_setup_limits.py`.

**Issue.** `/setup` (`lobby.py:160–165`) clamps only the lower bound of
`wager`, `num_hands`, `bet_amount` and `starting_bankroll`.
`/update_settings` (`admin.py:101–109`) does the same. The player list length
isn't capped. `num_hands=1000000` makes `start_round` allocate a million
`Hand`s per player on the **only** worker thread (Procfile:
`--workers 1 --threads 1`), which freezes every room on the server. A huge
`wager` creates absurd sip counts that overflow the UI. Also, non-string
entries in `npcs` (`n.strip()`) or `personalities` values crash with a 500.

**Solution brainstorm.**
- Add config constants `MAX_WAGER` (e.g. 5), `MAX_NUM_HANDS` (e.g. 4, matching
  the UI), `MAX_PLAYERS` (e.g. 8), `MAX_BET`, `MAX_BANKROLL`, and clamp both
  ends in one shared `validators.parse_game_settings(data)` used by both
  routes.
- Type-check `npcs` / `personalities` (`isinstance(n, str)`) and validate
  `mode in {"digital", "referee"}` and the personality against the known
  profile names.
- Consider a request-size limit (`MAX_CONTENT_LENGTH`).

---

### B3 — Room-code probing and rate-limit bypass · Medium

**Issue.**
- `lobby.py:102` takes the client IP from the first `X-Forwarded-For` value,
  which the client controls, so the join rate limit can be bypassed by sending
  a random header per request.
- `/state`, `/summary_json`, `/export_xlsx` and `/export_decisions` aren't
  rate-limited at all, and each one tells you whether a room code exists.
  `/state` also returns the full spectator state.
- The code space is about 22 words × 999 numbers ≈ 22k codes, matched
  case-insensitively, so it's small enough to enumerate.
- The exports need only the room code, not a member `client_id`. Anyone who
  guesses a code can download the room's full drink log and decision history,
  including player names.

**Solution brainstorm.**
- Wrap the app in `werkzeug.middleware.proxy_fix.ProxyFix(x_for=1)` (Render
  adds exactly one proxy hop) and use `request.remote_addr`.
- Apply the rate limiter to *misses* on every room-code endpoint, not just
  `/join_room`.
- Require a registered `client_id` for exports and `/summary_json`.
- Enlarge the code space (word + 4 digits, or 2 words + 2 digits). It stays
  readable aloud and on a QR code.

---

### B4 — Reserved rooms can be claimed by anyone · Medium

**Issue.** `/create_room` reserves a code, and `/setup` lets *any* client
configure a room whose value is still `None` (`lobby.py:142` only checks
admin when a game already exists). Players join the lobby before setup, so
anyone in the waiting room (or anyone who probed the code, see B3) can send
`/setup` first and become admin.

**Solution brainstorm.** Store the creator's `client_id` with the reservation
(`_room_creator[code]`) and require it in `/setup`. Return a clear "only the
host can start this table" error.

---

### B5 — Flaky test · Medium

**Issue.** `tests/app/test_mode_switch.py::test_drinking_table_cannot_switch_to_normal`
failed once in four runs (`assert 'playing' == 'round-over'`). `_play_round`
uses a real shuffled shoe and only sends `stand`. A dealt A-A, a 10-10 honor
prompt, or an insurance vote (dealer Ace plus player BJ in drinking mode) can
leave the round in `playing` after six loops.

**Solution brainstorm.** Rig the shoe (the engine tests already have a rigged
`Shoe` fixture) or seed `random` in a fixture. Optionally add a
`pytest-randomly`-style repeat run in CI to catch more of these.

---

### B6–B11 — Smaller items

| # | Severity | Issue | Solution |
|---|---|---|---|
| B6 | Low | `_join_attempts` is only pruned for an IP when that IP comes back, so it grows with every unique IP. Successful joins are also counted, though the comment says "failed attempts". | Prune all keys in `cleanup_stale_sessions`. Record the attempt only on a miss. |
| B7 | Low | `create_app()` rewrites `static/js/bundle.js` and `bundle.css` on every start. This fails on a read-only filesystem and races if more than one worker ever runs. | Build the bundle in a build step (Render "build command") and only verify it at startup. |
| B8 | Info | About 180 `innerHTML` assignments depend on remembering `escapeHtml`. Server-side `sanitize_name` strips `<>"'\``, so this is safe today but fragile. | Add a CSP (see B9). Prefer `textContent` or a small `html\`\`` tagged template that escapes by default. |
| B9 | Low | No security headers. | In the existing `after_request`: `Content-Security-Policy` (self and inline styles only), `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `frame-ancestors 'none'`. |
| B10 | Info | `requirements.txt` has no version pins, so deploys aren't reproducible (a `pydantic` or `flask` major bump would break silently). | Pin with `pip-compile` / `uv lock`. Add Dependabot. |
| B11 | Info (privacy) | `data/decisions/*.xlsx`, `data/profile_backups/*.json` and `engine/player_profiles/*.json` hold real first names and their drinking and decision history, committed to a public repo. | Pseudonymise them (`player_a`…), or move them out of the repo and load them at build time. Mention it in Terms §4. |

---

## Part C — Production readiness as a standalone app

Short answer: **not production-ready as a standalone (store-listed) app**. It is
a solid hobby web app for a known group of friends. These are the blockers,
roughly in priority order:

| # | Blocker | Why it matters | Brainstormed fix |
|---|---|---|---|
| P1 | **All state is in memory** (`session_store.game_sessions`), and the host is Render's free tier | Spin-down after idle, any redeploy, or a crash ends every running game with no recovery. Store users expect a game to survive a backgrounded phone and a server restart. | Snapshot each `GameRoom` (pydantic `state_schema` already exists) to Redis or SQLite on every `state_seq` bump and rehydrate on miss. Move to a paid always-on instance. |
| P2 | **One process, one thread** (`gunicorn --workers 1 --threads 1`) with polling | Every poll from every phone in every room is served one at a time, so throughput caps at a few dozen concurrent tables. More workers can't be added while state is in memory. | P1's external store unlocks more workers. Then use SSE or WebSockets (TODO already lists SSE) or at least the `state_seq` cache from TODO. |
| P3 | No CI | Nothing runs the 901 tests or ruff before a deploy. | GitHub Actions: `pytest` + `ruff` on every push, and require it before Render auto-deploys. |
| P4 | No monitoring | Errors only reach `app.logger`. There are no metrics and no health endpoint. | Sentry (free tier) for exceptions, a `/healthz` route, and basic counters (rooms, players, rounds) for capacity planning. |
| P5 | **Age gate and legal** | The gate says "18+ or legal drinking age" but the button reads "I am 18 or older", which is wrong for the US (21). A self-declared click is weak for store review. There is no responsible-drinking messaging or limit tooling beyond Drink Rate. | Make the button text locale-aware ("I am of legal drinking age"). Show a responsible-drinking notice and helpline link. Offer a "sips → water" or non-alcoholic mode up front. Get a legal review of Terms for liability. |
| P6 | **App store policy** | Apple (Guideline 1.4.3 / 17+ rating) and Google Play (alcohol policy) restrict apps that encourage excessive drinking. A drinking game built around a "Black Out" theme is at real risk of rejection. | Position it as "party blackjack with custom penalties" (sips are one option), rate it 17+/18+, keep Normal mode prominent, and soften the store copy. A PWA install (no store) avoids review entirely. |
| P7 | **Not a real standalone app yet** | `manifest.json` exists but there is no service worker, only one icon size (1024, `any maskable`), and no offline page. A broken connection just shows the "disconnected" overlay. | Add a service worker with a cache-first app shell and an offline page, proper 192/512 and maskable icons, and a splash screen. For a store build: TWA (Android) or Capacitor (iOS). |
| P8 | Privacy and consent | `clientId` is stored in `localStorage`. Terms §4 covers in-memory state, but there is no privacy policy page. Ads (Part D) will require a GDPR/ePrivacy consent banner. | Write a separate privacy policy. Add a consent-management platform before any ad SDK. Keep the zero-account model, which is a strength. |
| P9 | Security basics | B2, B3, B4 and B9 above. | Fix before any public promotion. |
| P10 | UX polish known in TODO | Mobile wasted space, horizontal scroll, desktop zoom (TODO "Bugs"). | Already tracked. Store reviewers will flag horizontal scroll. |

---

## Part D — Brainstorm: advertisement spaces

Constraints that shape every option:
- **Alcohol-adjacent content.** Most ad networks (AdMob, AdSense) classify
  drinking games as restricted. Expect 18+/21+ geo-targeting, lower fill and
  lower eCPM, and no ads to users who haven't passed the age gate. Some
  networks will refuse outright, so check AdMob's "alcohol" policy first.
- **Gameplay must stay clean.** The existing Donate plan rule ("nothing
  appears during active gameplay") is the right rule for ads too. A banner
  that shifts the action panel causes mis-taps on Hit/Stand, which would be
  infuriating at a party.
- **Shared screens.** One phone often controls several seats, so ads should
  appear on natural pauses, not per player.

| Placement | Moment | Format | Fit | Notes |
|---|---|---|---|---|
| Lobby, under room code / QR | Before the game, while waiting for friends | Static banner (320×50 / 300×250) | ★★★ | Dead time: everyone is waiting for the host. Lowest risk. |
| Waiting room (`_waiting.html`) | Joined, host still setting up | Banner or native card | ★★★ | Same reasoning. Pairs well with "Learn the rules" (Part E). |
| Session Summary modal | End of night | Native card under the stats | ★★★ | High attention and a natural break. Already a Donate surface, so use one or the other. |
| Between-round "trivia" slot | Round over, before next deal | Native ad styled as a trivia card, clearly labelled "Sponsored" | ★★ | The trivia panel already rotates content here. Cap it at one ad every N rounds. |
| Dealer Lottery / Targeted / Milestone results | Post-event reveal | — | ✗ | Too close to gameplay. Every player is watching the result. |
| Rules & Cheat Sheet modal | Reference | Small banner at the bottom | ★ | Low traffic. People open it mid-game, so it may feel intrusive. |
| Rewarded video | Opt-in | "Watch an ad → +1 Wild Card press" or "skip a sip" | ★★ (careful) | High eCPM, but rewarding *drink avoidance* with an ad, or giving extra presses, mixes money into a drinking mechanic. "Watch → unlock a cosmetic card back or table theme" is the safest version. |
| Sponsored table themes / card backs | Settings | Brand partnership (e.g. a non-alcoholic drinks brand, mixers, bar chains) | ★★ | Fits the "sips" theme without pushing alcohol. Needs a sales effort, so it's a later stage. |
| Interstitial | Between rounds | Full-screen | ✗ | Breaks the table flow for everyone, and store policies discourage interstitials at unexpected moments. |

Alternatives worth weighing against ads:
- **Ad-free "host pass"** (one-off purchase or per night): the host pays and the
  whole table is ad-free. This fits the "one phone runs the table" pattern.
- **Premium rule packs / themes** (ties into Part E and the rules registry):
  extra presets, custom rule editor, share codes.
- Keep the Donate link as the zero-friction baseline.

Implementation hooks: add one `<div class="ad-slot" data-slot="lobby">`
partial in `_macros.html`, render it only when `ads_enabled` (server config +
age gate passed + consent given), and keep every slot out of the
`_game.html` gameplay panels. A feature flag in `app/config.py` lets you turn
ads off per deployment (self-hosters, Normal-only builds).

---

## Part E — Brainstorm: rules quiz feature

The registry already lays the groundwork (plan §8): stable IDs, `doc_anchor`,
`summary`, `halvable`, `csv_labels`, presets and unlock steps. A quiz fits
naturally.

### Goals
1. Teach new players the house rules *before* they cost sips.
2. Use the dead time in the lobby and waiting room (the same slots as Part D).
3. Settle "is that a rule?" arguments at the table.

### Question sources
- **Generated from the registry** (no hand-written content needed):
  - "When **A♥** is dealt to a *player*, who drinks?" → options built from
    the `summary` of the four `ace.*.player` rules.
  - "Is *Lost suited hand +1* halved at a 4-player table?" → from `halvable`.
  - "Which rule needs *Blackjack bonus* to be on?" → from `depends_on`.
  - "Is *Dealer Lottery* on at this table?" → from the room's `RuleSet`. This
    is a good first-round icebreaker.
- **Scenario questions** that use the real engine: build a small hand set
  (rigged cards), run `DrinkingRules` with the table's `RuleSet`, and ask
  "How many sips does Ann drink?" The answer is computed by the engine, so it
  can never drift from the actual rules. Distractors are generated by flipping
  one rule off (`rules.with_rule(id, False)`) and recomputing.
- **Hand-written seeds** in `data/rules_quiz.json` keyed by rule ID, as plan §8
  proposes, for nuance the generator can't express (Hard Switch vs Soft Switch,
  insurance cases).
- **Trivia merge**: the existing `trivia.js` facts could become a "Blackjack
  knowledge" category in the same quiz engine (and fix the TODO "fact check"
  item along the way).

### Modes
| Mode | Where | Stakes |
|---|---|---|
| **Solo practice** | Lobby / waiting room, Rules modal "Quiz me" button | None. Explain the answer with a link to `doc_anchor` |
| **"Tonight's rules" warm-up** | Before round 1, optional, host-started | Filter to `rules.effective()`. A wrong answer earns a 1-sip "tuition fee" (opt-in, flat, never scaled) |
| **New rule unlocked** | Toast when "➕ Next rule" adds a rule (SettingsModal §3.4) | One question about the new rule |
| **Between-round pop quiz** | Same slot as trivia, every N rounds | The first correct answer hands out 1 sip, reusing the milestone handout UI |
| **Post-game "Which rule cost you the most?"** | Session Summary | Built from `csv_labels` → rule mapping on `drinks.csv_rows` |

### Architecture sketch
- `engine/rules_quiz.py`: pure question generators that take a `RuleSet` and
  return `Question(id, rule_id, prompt, options, answer_idx, explanation)`.
  Lives in `engine/`, so the terminal client can use it too.
- `GET /rules_registry` (planned in Phase 3) plus `GET /quiz?room_code=&n=5`,
  which returns generated questions for the table's effective rules.
- Frontend: `static/js/ui/quiz.js`, a modal reusing the trivia carousel
  styles. Answers checked client-side for solo mode and server-side for any
  mode with sips.
- Tests: every generated question's answer must match a real `DrinkingRules`
  run, plus a registry-coverage test so each toggleable rule has at least one
  question generator (same idea as G10).

### Monetisation tie-in (optional)
- Premium "rule packs" with their own quiz sets.
- A sponsored "quiz of the week" card in the lobby. It's labelled, it's
  outside gameplay, and it fits the Part D constraints.

---

## Suggested order of work

1. ~~**B2**~~: fixed 2026-10-29. **B1** is deferred with the other referee items (G13).
2. ~~**G1, G2, G3, G4**~~: fixed 2026-10-29.
3. ~~**G6, G7, G8, G10, G11, G12**~~: fixed 2026-10-29.
4. **G5**: deferred to the Normal-mode overhaul.
5. **B3, B4, B5, B9** and **P3** (CI): hardening before any public promotion.
6. **P1, P2**: only if the app is meant to go beyond friends-and-family scale.
7. Parts D and E: after the above. The quiz can start right after Phase 3,
   since it reuses `/rules_registry`.
