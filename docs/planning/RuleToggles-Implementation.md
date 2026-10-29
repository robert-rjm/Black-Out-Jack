# Rule Toggles — Implementation Plan

Companion docs:
[Rules-Catalog.md](../Rules-Catalog.md) (rule IDs) ·
[RuleToggles-StarterSet.md](RuleToggles-StarterSet.md) (presets) ·
[RuleToggles-SettingsModal.md](RuleToggles-SettingsModal.md) (UI).

## 1. Summary

1. **One registry** (`engine/rules_registry.py`) declares every rule: ID,
   name, group, dependencies, presets, unlock step, doc anchor and CSV
   labels. Everything else reads from it: the engine, the app, the settings
   UI, the Rules popup, the catalog sync test and, later, the quiz.
2. **One `RuleSet` value** per room (`GameConfig.rules`) answers
   `rules.on("ace.hearts.player")`. It resolves dependencies, so a child
   whose parent is off reads as off.
3. **Gate at the source**, meaning inside the code that *decides* a rule
   fires, and never by filtering drink messages afterwards. Several rules
   have side effects beyond their message (Hard Switch replaces the
   dealer's other drinks, A♣ sets protection flags, dealer 5-card 21 doubles
   other rules), so dropping the message would leave the side effect behind.
4. **Default = Full = today's behaviour.** Every new parameter defaults to
   `FULL`, so existing tests, the regression snapshots and the
   terminal/referee scripts don't change until someone opts in.

## 2. Data model

### 2.1 Registry (`engine/rules_registry.py`, new)

It lives in `engine/` because the terminal and referee modes
(`engine/blackjack.py`, `engine/referee.py`) need it too, and `engine/` must
not import from `app/`.

```python
@dataclass(frozen=True)
class RuleDef:
    id: str                      # "ace.hearts.player" (stable, never renamed)
    name: str                    # "A♥ to a player"
    summary: str                 # "you drink 1"
    group: str                   # "aces" | "table" | "insurance" | ...
    kind: str                    # "core" | "table" | "drink" | "event" | "meta"
    timing: str                  # "instant" | "end-of-round" | "between-rounds" | "passive"
    preset: str                  # lowest preset: "locked" | "starter" | "standard" | "full"
    unlock_step: int | None      # order for "➕ Next rule" (StarterSet §5)
    depends_on: tuple[str, ...] = ()
    doc_anchor: str = ""         # Rules.md slug, e.g. "41-ace-effects"
    csv_labels: tuple[str, ...] = ()   # classify_rule() outputs this rule produces
    live: bool = False           # True → toggles apply immediately (bust vote, wild card)
    halvable: bool | None = None # informational, for badges and the quiz

RULES: tuple[RuleDef, ...] = (...)          # registry order = share-code bit order (append-only)
RULES_BY_ID: dict[str, RuleDef] = {r.id: r for r in RULES}
GROUPS: tuple[tuple[str, str], ...] = (("core", "Core"), ("table", "Table rules"), ...)
PRESETS = {"starter": frozenset(...), "standard": frozenset(...), "full": frozenset(RULES_BY_ID)}
```

An import-time `_validate()` checks that IDs are unique, every `depends_on`
entry exists, there are no cycles, presets are nested
(starter ⊆ standard ⊆ full), every locked rule is in every preset, and every
rule comes after its parents in the unlock order. If any check fails, import
fails.

### 2.2 RuleSet (`engine/rules_registry.py`)

```python
@dataclass(frozen=True)
class RuleSet:
    enabled: frozenset[str]      # what the admin toggled on (may include children of off parents)
    preset: str | None = None    # "starter" | "standard" | "full" | None (custom)

    def on(self, rule_id: str) -> bool:
        """Effective state: enabled AND all ancestors effective. Locked rules are always on."""

    def effective(self) -> frozenset[str]: ...
    def with_changes(self, on=(), off=()) -> "RuleSet": ...
    def to_code(self) -> str: ...        # share code (SettingsModal §10)
    @classmethod
    def from_preset(cls, name) -> "RuleSet": ...

FULL = RuleSet.from_preset("full")
```

- `on()` raises `KeyError` on an unknown ID. A typo in a gate then fails
  every test instead of silently turning the rule off.
- Cache `effective()` on construction. `on()` is called a lot per round, so
  it should be a set lookup.
- **Planned extension:** `params: Mapping[str, int]` for per-rule
  intensity (SettingsModal §10). Not built now, but keep the frozen
  dataclass and the serializer shape (`{"enabled": [...], "params": {}}`)
  ready for it.

### 2.3 Room state (`app/models/game_room.py`)

```python
@dataclass
class GameConfig:
    ...
    rules: RuleSet = field(default_factory=lambda: FULL)
```

Migrating the two existing flags (to avoid having two sources of truth):

```python
# GameRoom: existing property names keep working for all current call sites
@property
def bust_vote_enabled(self): return self.config.rules.on("side.bust_vote")
@bust_vote_enabled.setter
def bust_vote_enabled(self, v): self.config.rules = self.config.rules.with_changes(**_flip("side.bust_vote", v))
# same for wild_card_enabled → "event.wild_card"
```

Then remove `GameConfig.bust_vote_enabled` / `wild_card_enabled`.
**Watch the default:** `bust_vote_enabled` defaults to `False` today, but
`FULL` would turn it on. Either keep `side.bust_vote` *out* of the room's
default set (a new-room default of "Full minus bust vote", which matches
today) or decide on purpose to change it. Recommendation: match today's
behaviour exactly, so the default room set is
`FULL.with_changes(off=["side.bust_vote"])`.

`easy_mode` stays separate. It's a modifier (catalog §10).

## 3. Gating: rule → code location

Each gate is a single `if not rules.on(...)` early return (or a skipped
branch) at the spot below. The engine gets `rules` through the event
objects. The app reads `session.rules` (the `GameRoom` property over
`config.rules`).

### 3.1 Engine (`engine/drinking_rules.py`, `engine/events.py`)

Add `rules: RuleSet = FULL` to every event dataclass in `engine/events.py`,
and to the two direct helpers (`check_four_aces`, `dealer_21_five_cards`)
as a keyword argument. `DrinkingRules.handle()` passes `event.rules`
through. `DrinkingRules` stays a stateless static class.

| Rule ID | Gate location |
|---|---|
| `ace.<suit>.player` / `ace.<suit>.dealer` | `on_card_dealt`: per-suit branch. For **A♣**, also skip setting `ace_clubs_flag["half_protected"]` / `["partial_protected"]` when the matching rule is off. |
| `four_aces.first_deal` / `.end_round` | `check_four_aces`, by `phase`. If `first_deal` is off, the flag that blocks `end_round` must not be set either. |
| `bonus.blackjack` | `on_blackjack` returns `[]` |
| `bonus.blackjack.multipliers` | `_bj_multiplier`: return 1 when off. Thread `rules` through `_bj_breakdown` callers, including `resolve_insurance_vote` and the Hard Switch BJ count. |
| `insurance.bj_vote` | `resolve_insurance_vote` is never reached. The gate sits in the app/engine code that *opens* the vote (§3.2), so no vote happens at all. |
| `insurance.auto_cap` | `_dealer_bj_drinks`: when off, fall through to the normal net-loss path. |
| `loss.doubled`, `loss.suited` | `_extra_loss_drinks`. The doubled + suited ×4 combo needs both; if only one is on, apply only that +1. |
| `others.wins_all` | `_wins_all_drinks` |
| `others.immunity.doubled` / `.suited` | `on_hand_resolved` immunity branches |
| `others.immunity.split` | `_split_win_drinks` |
| `five_card.player_win` | `on_hand_resolved` ("won with N cards") |
| `five_card.player_21` | Where the 5-card 21 handout is created (the call into `DrinkTracker._handle_handout(label="5-card 21")`) |
| `five_card.dealer_21` | `dealer_21_five_cards` returns False |
| `sweep.same_suit` / `sweep.all_21` | `check_all_hands_sweep`, per condition. The "Sweep credit" adjustment follows whichever one fired. |
| `dealer.suited_hand` | `on_dealer_hand_revealed` |
| `switch.hard` | `on_hard_dealer_switch` returns `[]`, **and** the callers must not treat the dealer as `hard_switch_dealer`. Otherwise the dealer's normal drinks are still suppressed and they drink nothing. Pass `hard_switch_dealer=None` into `RoundEndEvent` / `BlackjackEvent` / `AllHandsSweepEvent` when the rule is off. Rotation still happens (`core.dealer_rotation`). |

That last row is the trap in this feature. **Hard Switch is a mode, not just
a message.** Write a dedicated test: rule off + dealer loses all hands →
dealer drinks their ordinary player-role sips, and the role still passes.

### 3.2 App services

| Rule ID | Gate location |
|---|---|
| `table.split_tens` | `app/services/stats.py` `compute_mandatory_split10` returns False. That one gate covers `check_honor_house_rule`, the frontend prompt (`honor_pending`) and the suited-split fee. |
| `table.split_aces` | `compute_mandatory_split_aces` returns False. That covers `penalize_unsplit_aces`. |
| `table.split_ace_bj` | Hand scoring in `engine/blackjack.py`. A split-ace 21 is a plain 21 when off. Needs `rules` on the `Hand`/`Player` scoring path. Biggest blast radius of the table rules, so do it last. |
| `insurance.bj_vote` | Where the round pipeline opens the insurance vote (search for `INSURANCE_VOTE_TIMEOUT` users). Skip the vote and treat it as "decline". |
| `side.bust_vote` | Already gated by `session.bust_vote_enabled`, which becomes the property from §2.3. No new code. |
| `cards.devils_hand` / `.lucky_sevens` | `app/services/game_engine.py` around `_six_curse_fired` |
| `milestone.handout` | `app/services/drink_tracker.py` `check_and_set_milestone`. When off, no milestone is set. The sip ticker still counts. |
| `milestone.back_to_back` | Milestone streak update (cosmetic) |
| `milestone.worst_average` | `_apply_worst_player_streak` |
| `streak.l_badge` | `_update_worst_streak_holder`. When off, clear `worst_streak_holder` so the badge disappears. |
| `event.dealer_lottery` | `app/services/dealer_lottery.py` `check_dealer_lottery_trigger` |
| `event.targeted` | `app/services/targeted_drinking.py` `start_targeted_drinking` returns False with a reason, and the proposal-vote entry point does the same. The serializer hides the start/propose UI. |
| `event.targeted.perfect_handout` | Graduation handler in `targeted_drinking.py` |
| `event.wild_card` | Already gated by `session.wild_card_enabled` (property from §2.3) |
| `event.wild_card.targeted` | `app/routes/wild_card.py`: when off (or `event.targeted` is off), the 15% slice re-rolls into the existing "random" fallback the route already uses when a start fails. |

### 3.3 Strategy and bots

- `engine/strategy.py` (basic-strategy hint) and `engine/style_strategy.py`
  (bots) assume 10-pairs get split in drinking mode. With `table.split_tens`
  off, the hint and the bots must play standard basic strategy (stand on
  20). Pass `rules` into `best_play(...)`, or a `split_tens_mandatory: bool`
  flag.
- Strategy-accuracy KPIs (`record_strategy_decision`) compare against that
  same hint, so they follow automatically.

### 3.4 Wiring `rules` into events

Events are built in `engine/blackjack.py`, `engine/referee.py` and
`app/services/game_engine.py`, roughly 90 call sites in total for
`DrinkingRules.*` / `tracker.apply` / `add_drink`. Steps:

1. As built: `GameConfig.rules` is the **only** copy of a room's rules.
   `RefereeSession.rules` is a property. In the web app, `GameRoom` sets
   `session.rules_source`, so the engine reads the room's current rules
   live, and assigning `session.rules` directly raises. Standalone engines
   (`RoundManager`, terminal referee) keep their own `rules` attribute
   (default `FULL`). There is no `tracker.rules`.
2. Event construction sites pass `rules=self.rules` / `rules=session.rules`
   explicitly. Missed sites default to `FULL`. A test should catch that
   (§6.3, audit G11).

## 4. API and state

### 4.1 `/update_settings` (`app/routes/admin.py`)

New optional payload keys:

```jsonc
{ "rules_preset": "starter" }                       // replace the set with a preset
{ "rules_on": ["ace.hearts.player"], "rules_off": ["event.dealer_lottery"] }   // incremental
{ "rules_next": true }                               // "➕ Next rule"
```

Validation: IDs must be in `RULES_BY_ID`, locked IDs are rejected, and
unknown keys are ignored. That matches how the route already handles bad
input. Then:

- Rules with `live=True` (`side.bust_vote`, `event.wild_card`) apply
  immediately, as their old flags did. Also clear
  `session.round._bust_votes` when the bust vote changes.
- Everything else goes into `queued["rules"]` as the *full target set*
  (a list of IDs), not as a diff. Repeated edits then collapse naturally,
  and the banner can diff target against live.

### 4.2 Applying at round start (`app/services/room_manager.py`)

Next to the existing `easy_mode` block:

```python
if "rules" in queued:
    old = session.rules
    # One write is enough: the engine session reads room.rules live (§3.4).
    # RuleSet derives its preset label from the content (audit G12).
    session.rules = RuleSet(frozenset(queued["rules"]))
    changes.append(_describe_rule_diff(old, session.rules))   # "📜 Aces ♥♦ on, Dealer Lottery off"
```

Live events that are already running (lottery, targeted, a milestone
claim window) are not cancelled. Their gates only run at *trigger* time, so
an event that has already started finishes on its own.

### 4.3 Setup (`/setup`)

Accept an optional `rules_preset` (default `"full"`). The terminal and
referee scripts get a `--preset` CLI flag in `scripts/_cli.py`.

### 4.4 Serializer and schema

`app/services/serializer.py` adds:

```jsonc
"rules": {
  "preset": "standard",          // null = custom
  "enabled": ["..."],            // admin's toggles
  "effective": ["..."],          // after dependency resolution (what the UI greys out)
  "queued": ["..."] | null       // target set waiting for next round
}
```

Update `app/models/state_schema.py` to match. The serializer validates
against it, and `docs/DOM-Hooks.md` lists the new elements.

Static registry data (names, groups, summaries, anchors) is **not** sent on
every `/state` poll. Add `GET /rules_registry` in
`app/routes/static_pages.py`, next to `/rules`: cacheable JSON that the
frontend fetches once. The quiz will use the same endpoint.

### 4.5 Exports

- The xlsx export (`/export_xlsx`) gets a **RULES** sheet listing the
  preset, the effective IDs and the round number of each change. Without it,
  drinks summaries from different rulesets aren't comparable.
- Each CSV/decision-log row gets a `ruleset` column (share code or preset
  name).

## 5. Frontend

| File | Change |
|---|---|
| `templates/partials/index/_modals.html` | New `#settings-rules-view` sub-view and the 📜 button in `.settings-actions` |
| `static/js/ui/rules-settings.js` (**new**) | Fetch and cache `/rules_registry`, render groups/rows/presets, tri-state group toggles, dependency greying, search, "Next rule", read-only mode. Kept out of `admin-settings.js`, which is already about 900 lines (see `FileRefactor.md`). |
| `static/js/ui/admin-settings.js` | `showSettingsSubview("rules")` case, button badge text, and the rules line in `_renderQueuedBanner()`. Remove the Bust Vote / Wild Card row checkbox sync in `_populateSettingsUI` once they're registry-driven. |
| `static/js/ui/rules.js` | After `_decorateRules()`: "OFF AT THIS TABLE" badges by `doc_anchor`, top banner, and the "show active rules only" toggle |
| `static/js/ui/setup.js` + `_setup.html` | Preset chips on room creation |
| `static/js/ui/drink-panels.js` / `admin.js` | Hide the Bust Vote panel, lottery and targeted entry points when their rules are off. The serializer flags should already drive most of this. |
| `templates/partials/index/_scripts.html` | Load `rules-settings.js` |
| `static/css/components/modals.css` | Row, badge and greyed-dependency styles. Reuse the pill toggles from `controls.css`. |
| `static/js/ui/log.js` | Render the "📜 House rules changed" round notice |

Send UI actions through `/update_settings` with the same
`data-action`/`data-args` delegation that the other settings buttons use.

## 6. Testing

### 6.1 Registry and docs

- `tests/engine/test_rules_registry.py`: `_validate()` passes, presets are
  nested, every `csv_labels` entry is a real `classify_rule` output, and
  every `doc_anchor` is a heading slug in `docs/Rules.md` (use the same slug
  function as `rules.js` `_ruleSlug`).
- `tests/engine/test_rules_catalog_sync.py`: every registry ID has an
  `<a id="...">` anchor in `docs/Rules-Catalog.md` and vice versa, plus the
  preset column matches. This replaces hand-maintaining the catalog.
- The existing `rules_sync.py` hash test fires whenever `Rules.md` or
  `drinking_rules.py` changes. That's expected. Re-pin with
  `python scripts/rules_sync.py update` after reviewing.

### 6.2 One "off means off" test per rule

Parametrized over every non-locked rule:

1. Build a scripted round (rigged `Shoe`, the same as the existing
   `tests/engine/test_drinking_rules_*` fixtures) that makes that rule fire
   under `FULL`. Assert that a row with one of its `csv_labels` appears.
2. Run the same round with `FULL.with_changes(off=[rule_id])`. Assert that
   no row has those labels, **and** that every other row is identical
   (no collateral changes).

Rules that need extra cases:
- `switch.hard` off: the dealer drinks their normal player sips (the §3.1
  trap).
- `ace.clubs.dealer` on but `switch.hard` off: no effect, and no crash.
- `loss.suited` on but `loss.doubled` off: a doubled suited loss is +1, not
  +3.
- `bonus.blackjack.multipliers` off: A♠ J♠ = 1×. Insurance double-bonus
  uses 1× as well.
- `event.wild_card.targeted` off: the 15% roll falls back to "random"
  (seed `random`).

The `classify_rule` gaps listed in catalog §"Gaps" (split-10s and
split-aces labels) are fixed. `five_card.dealer_21` has no label by design
(zero-sip notices never reach the CSV), so its test compares sip totals
instead: core penalties exactly doubled when on, normal when off.

### 6.3 No-regression proof

- `tests/engine/test_regression_snapshots.py` must pass **unchanged**. The
  default (`FULL` minus bust vote) must reproduce today's numbers exactly.
- A test that builds every event type with no `rules=` argument and checks
  it equals `FULL`, so a forgotten construction site behaves like today.
- A simulation smoke test: `--preset starter` runs N rounds without errors,
  and its average sips/round is lower than Full's.

### 6.4 App and route tests

- `/update_settings`: presets, incremental changes, a rejected locked ID, a
  non-admin rejected, live rules applying immediately, queued rules applying
  at `newround` with a round-log notice.
- Turning off a rule during a live lottery or targeted run doesn't cancel
  it, and the rule doesn't trigger the next round.
- Serializer output validates against `state_schema`.

## 7. Phasing

Each phase can ship on its own, and the app behaves as today until Phase 3
exposes the UI.

| Phase | Scope | Done when |
|---|---|---|
| **0. Groundwork** | Fix the catalog "Gaps" (Rules.md split-Aces text, Cheat-Sheet A♣ wording, new `classify_rule` labels, suited-split wager unit). Re-pin `rules_sync`. | Docs and labels consistent, tests green |
| **1. Registry** | `engine/rules_registry.py`, `RuleSet`, `GameConfig.rules`, migrate `bust_vote_enabled` / `wild_card_enabled` to properties, registry and catalog sync tests | No behaviour change, snapshots identical |
| **2. Gates** | Engine gates (§3.1), app gates (§3.2), strategy (§3.3), event wiring (§3.4), the per-rule "off means off" tests | Every rule can be switched off in tests |
| **3. Admin UI** | `/update_settings` keys, queue/apply, serializer, `/rules_registry`, settings sub-view, read-only view, queued banner, round-log notice | Admin can toggle rules in a live room |
| **4. Presets & docs** | Simulation `--preset` and measured numbers, preset chips on setup and settings, "➕ Next rule", Rules popup badges, a per-rule anchor pass in Rules.md, Rules.md / Multiplayer.md / Cheat-Sheet sections on house rules | Starter set playable from room creation |
| **5. Follow-ups** | xlsx RULES sheet, share codes, "save my house rules", quiz hooks (`/rules_registry` + catalog quiz seeds), majority vote on rule changes | — |

## 8. Hooks for the rules quiz

The quiz isn't part of this plan, but these choices keep it cheap later:

- **Stable IDs plus anchors**, from the catalog and registry. A question
  links to `Rules-Catalog.md#<id>` or to the Rules popup at `doc_anchor`.
- **Quiz seeds** sit in the catalog per rule. Later they move to
  `data/rules_quiz.json` keyed by rule ID (several questions per rule,
  multiple-choice distractors).
- **"Quiz me on tonight's rules"**: filter questions to
  `state.rules.effective`.
- **Unlock moments**: the "🆕 New rule unlocked" toast (SettingsModal §3.4)
  can offer one question about that rule.
- **Stats link-back**: `csv_labels` maps a drinks-summary row back to a
  rule. That makes post-game questions possible ("Which rule cost you the
  most tonight?").

## 9. Risks

| Risk | Mitigation |
|---|---|
| Hidden coupling: Hard Switch ↔ A♣ ↔ insurance ↔ BJ bonus, and dealer 5-card 21's scope list | Source gating (not message filtering), the dedicated coupling tests in §6.2, and `depends_on` in the registry |
| A missed gate leaves a rule half-on | The "off means off" test runs on *every* rule, driven by the registry, so a new rule without a test fails the registry-coverage check |
| Two engines (digital `game_engine`/`blackjack.py` vs `referee.py`) drift | Gates live in `DrinkingRules` and shared services wherever possible. Run the referee path in the parametrized test as well. |
| Comparing stats across rulesets (KPI benchmarks, `static/js/benchmarks.js`, player profiles) | Tag rows with the ruleset, and only compare or benchmark against Full-preset data |
| The bust-vote default changes by accident | §2.3: the default room set is `FULL` minus `side.bust_vote`, with a test for it |
| Toggling mid-session confuses players | Changes only apply at round start, plus a round-log notice, the read-only view and badges in the Rules popup |
| The state payload grows | The registry is a separate cached endpoint; `/state` only carries ID lists |

## 10. Open questions

1. **Should the room's ruleset survive an admin transfer?** Yes. It lives
   on `GameConfig`, not on the admin client.
2. **Should a Hard Switch with `switch.hard` off still be a "Hard Switch"
   (rotate early)?** Recommendation: yes, rotation stays. Only the penalty
   is a rule.
3. **Should Normal → Drinking graduation default to Starter?** See the
   StarterSet open questions.
4. **Should locked rules ever be unlockable** (for example a
   "dealer-only" variant)? No. That would be a different game mode, not a
   toggle.
