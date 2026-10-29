# Rule Toggles — Settings Modal (UX Plan)

Companion docs:
[Rules-Catalog.md](../Rules-Catalog.md) (rule IDs) ·
[RuleToggles-StarterSet.md](RuleToggles-StarterSet.md) (presets) ·
[RuleToggles-Implementation.md](RuleToggles-Implementation.md) (code plan).

## 1. General idea

- The admin can switch each drinking rule on or off for their table.
- Rules are grouped (Aces, End of round, Events…). Each group has a master
  toggle, and each rule can still be toggled on its own.
- One tap picks a preset (Starter / Standard / Full), then the admin adjusts
  from there.
- Changes are **queued for the next round**, as the existing wager, hands
  and Easy Mode settings are, so a round never changes rules halfway
  through.
- Every player can see which rules are on (read-only). Disabled rules are
  marked in the Rules popup.

## 2. Where it lives

The settings overlay (`templates/partials/index/_modals.html`,
`#settings-main-view`) already has a row of `.settings-action` buttons
(Pause, 🍷 Drink rate, 👥 Players) and a sub-view pattern
(`showSettingsSubview("players")` in `static/js/ui/admin-settings.js`).

Add one button and one sub-view:

```
⚙️ Settings
┌──────────────────────────────────────────┐
│ [⏸ Pause] [🍷 Drink rate] [👥 Players]   │
│ [📜 House rules  Standard · 31/44]   NEW │
│ ── Game settings ──                      │
│ Wager / Hands / Decks / Rotate every …   │
└──────────────────────────────────────────┘
```

- Button: `data-action="showSettingsSubview" data-args='["rules"]'`,
  class `settings-action drink-only` (hidden in Normal mode, like Drink
  rate).
- The button label shows the current preset and the count of rules on, so
  the admin sees the table state without opening it.
- Non-admins see the same button, but it opens the **read-only** view
  (§6).

Rejected alternatives:
- *A separate top-level modal:* one more overlay to manage, and it breaks
  the "everything the admin controls is under ⚙️" habit.
- *A tab in the Rules popup:* the Rules popup is for reading. Mixing editing
  into it confuses non-admins.

## 3. Sub-view layout (admin)

```
┌─────────────────────────────────────────────┐
│ ← Back            📜 House rules            │
├─────────────────────────────────────────────┤
│ Preset                                      │
│ (🟢 Starter) (🟡 Standard●) (🔴 Full) (✏️)   │
│ ≈1.8 sips/rnd   ≈2.6          ≈3.0          │
│                                             │
│ [ ➕ Next rule: Ace of Hearts ]             │
│ 🔍 Search rules…                            │
├─────────────────────────────────────────────┤
│ ▾ Core                                 🔒   │
│     Net hand losses                    🔒   │
│     Dealer rotation                    🔒   │
│ ▾ Table rules                     [■■□] 2/3 │
│     Mandatory split 10s          ⓘ   [●━]   │
│     Mandatory split Aces         ⓘ   [●━]   │
│     Split-Ace Blackjack          ⓘ   [━○]   │
│ ▸ Insurance                       [■□]  1/2 │
│ ▸ Dealer switch                   [■]   1/1 │
│ ▾ Aces                            [■■■■□□□□]│
│     A♥ to player  · you drink 1  ⓘ   [●━]   │
│     A♣ to dealer  · half switch  ⓘ   [●━]   │
│       ↳ requires Hard Switch                │
│     …                                       │
│ ▸ Other instant rules                       │
│ ▸ End of round                              │
│ ▸ Session (milestones, streaks)             │
│ ▸ Events (lottery, targeted, wild card)     │
├─────────────────────────────────────────────┤
│ 3 changes queued for next round  [Undo all] │
│ [ Queue for next round ]                    │
└─────────────────────────────────────────────┘
```

### 3.1 Rows

Each rule row has:

| Element | Content |
|---|---|
| Name | `RuleDef.name` from the registry |
| Summary | `RuleDef.summary`, one short line ("you drink 1") |
| Badges | ⚡ instant · 🏁 end of round · ⏸ between rounds · ½ halvable (small, muted) |
| ⓘ | Opens the Rules popup scrolled to the rule's Rules.md section (`RuleDef.doc_anchor`), reusing `openRulesModal()` plus the in-page anchor scroll in `static/js/ui/rules.js` |
| Toggle | Same pill switch as the existing Easy Mode / Bust Vote toggles (`controls.css`) |
| Queued marker | A dot or "next round" tag when the row differs from the live state |

### 3.2 Groups

- Group order matches the catalog: Core, Table rules, Insurance, Dealer
  switch, Aces, Other instant, End of round, Session, Events.
- The group master toggle is **tri-state** (all on / mixed / all off).
  Tapping it while mixed turns all on.
- The collapsed group header shows `n/m on`, so the admin can scan
  everything without expanding.
- Groups that differ from the selected preset expand by default. The rest
  stay collapsed, which keeps the first view short on mobile.

### 3.3 Presets

- Chips: Starter / Standard / Full / Custom. The active one is filled.
- Tapping a preset when the current set is Custom asks first: "Replace your
  custom rules with Standard?" Switching between presets doesn't ask.
- The chip under each preset shows the simulated average sips/round
  (from `RuleToggles-StarterSet.md` §6). Leave it out until those numbers
  exist.
- Editing any row moves the selection to ✏️ Custom ("based on Standard,
  +2 / −1").

### 3.4 "➕ Next rule"

- Turns on the lowest-`unlock_step` rule that's off (with its pair, if it
  has one) and queues it.
- After it's applied at the next round, a toast goes to every player:
  "🆕 New rule unlocked: **Ace of Hearts**, you drink 1 when you're dealt
  A♥", with a "Read more" link to the rule's section. That toast is also a
  natural hook for a single quiz question later.
- Hidden once everything is on.

### 3.5 Dependencies

Dependencies come from `RuleDef.depends_on`:

- Turning a parent **off** keeps the children's own toggle state but greys
  them out with "↳ requires Hard Switch". Their *effective* state is off.
  Turning the parent back on restores them, so no state is lost.
- Turning a child **on** while its parent is off shows inline: "Also turn
  on Hard Switch?" [Turn on both] [Cancel].
- Rows are never hidden. Greyed-out rows teach the table how the rules
  connect.

### 3.6 Locked rows

`core.*` rows show 🔒 and no toggle. Tooltip: "This is the game itself. Use
Normal mode to play without drinking."

### 3.7 Search

A client-side filter over name, summary and ID. Matching groups
auto-expand. Useful once there are 40+ rows. Optional for v1.

## 4. When changes apply

| Situation | Behaviour |
|---|---|
| Between rounds (waiting) | Queued, then applied when the next round starts. This is the same path as `queueSettings()` → `/update_settings` → `_queued_settings`. |
| Mid-round | Allowed, still queued. The current round finishes on the old rules. |
| A **live event** for a rule being turned off (Dealer Lottery running, Targeted Drinking active, milestone handout open) | The event finishes normally. The rule stops triggering from the next round. The row shows "ends after the current event". |
| Room creation | Preset picker on the setup screen (`_setup.html`). Default **Full**. |
| Normal → Drinking switch (`boj_switch.py`) | Suggest Starter (open question in the starter-set doc). |

The existing **queued-settings banner** (`#queued-settings-banner`,
`_renderQueuedBanner()`) gets one compact line for rule changes:
`📜 Rules: +A♥ A♦, −Dealer Lottery`.

At round start, the round log posts a notice to everyone:
`📜 House rules changed: Aces ♥♦ on, Dealer Lottery off`.

## 5. Existing toggles that move in

| Today | After |
|---|---|
| Bust vote pill toggle (live, `bust_vote_enabled`) | `side.bust_vote` row. **Keep it live, not queued.** It's a pre-deal vote, so toggling between rounds is harmless, and people are used to it working immediately. The quick pill on the table (`BustVotePanel`) stays and drives the same rule. |
| Wild Card toggle (`wild_card_enabled`) | `event.wild_card` row, live as well. |
| Easy Mode toggle | **Stays where it is.** It's a modifier, not a rule (catalog §10). The rules sub-view links to it in its footer: "Want fewer sips overall? → Easy Mode / Drink rate". |
| Targeted Drinking admin start/cancel (`_renderTargetedDrinkingAdmin`) | Stays in the Players view. If `event.targeted` is off, the start button is hidden and the name-tap proposal is disabled. |

## 6. Read-only view (non-admins and spectators)

Same layout, without toggles. Rows that are off show muted with "Off at this
table". The preset name and count sit at the top. ⓘ links work the same.

This matters because **players need to know what they're playing**, both
for fairness and because a disabled rule that still shows in the Rules popup
causes arguments.

## 7. Rules popup integration

`static/js/ui/rules.js` already gives every heading a GitHub-style slug in
`_decorateRules()`. After rendering:

- For each rule that's off, find its heading by `doc_anchor` and add an
  "OFF AT THIS TABLE" badge. Mute the section (lower opacity, keep it
  readable).
- Add a banner at the top: "This table plays **Standard** (31/44 rules).
  Rules marked OFF don't apply."
- Add a toggle in the popup: **Show active rules only**, which collapses the
  disabled sections.

Several rules share one Rules.md section (all eight Aces are under §4.1). A
section is only muted when **all** of its rules are off. Otherwise each rule
that's off gets a small inline badge on its table row, where one exists. This
needs per-rule anchors in Rules.md (see the implementation plan, Phase 4).

## 8. Mobile & accessibility

- Rows are at least 44 px tall. The whole row toggles; ⓘ is a separate tap
  target.
- Groups use `<details>`/`<summary>` for keyboard and screen-reader support.
- Each toggle is a real `<input type="checkbox" role="switch">` with
  `aria-describedby` pointing at the summary line.
- The tri-state group toggle uses `aria-checked="mixed"`.
- No horizontal scroll at 320 px, which also addresses the existing mobile
  TODO.
- The sticky footer (queued count + Queue button) stays visible while
  scrolling a long list.

## 9. Copy (draft)

| Place | Text |
|---|---|
| Button | 📜 House rules |
| Sub-view title | 📜 House rules |
| Preset helper | "Start simple and add rules as the table learns them." |
| Next rule | ➕ Next rule: *{name}* |
| Dependency | ↳ requires *{parent}* |
| Locked tooltip | "This is the game itself." |
| Queue confirm | "Rules update when the next round starts." |
| Live event | "Ends after the current {event}." |
| Read-only header | "This table plays *{preset}* · {n}/{m} rules on" |

## 10. Nice-to-haves (later)

- **Save as my house rules:** keep the admin's custom set in `localStorage`
  (per-viewer convenience only) and offer it as a preset chip next time.
- **Share code:** encode the enabled set as a short string (bitset over
  registry order, base32), e.g. `BOJ-R-7Q3K`. Paste it on the setup screen
  to load the same rules. Safe, because the registry is fixed and IDs are
  stable.
- ~~**Majority vote to add or remove a rule**~~ Built (2026-10-29,
  `services/rule_votes.py`): players suggest changes to the admin, or, once
  the table has voted for it, put each change to a table vote directly.
  Bust vote and Wild Card moved out of the main view into a "Quick
  switches" block at the top of the sub-view.
- **Per-rule intensity** (for example the Blackjack bonus at 1× / 2×, or
  the milestone step at 25/50/100). That's a different feature from on/off.
  Keep the data model open to it (see the implementation plan, §2.2) but
  don't build it now.

## 11. Open questions

- Should **live toggles** (bust vote, wild card) stay live, or should
  everything queue so the rule is simple to state? Recommendation: keep
  those two live, because that's what users already expect.
- Should the read-only view be visible to **spectators**? Recommendation:
  yes. It costs nothing and helps people decide to join.
- Should non-admins be able to **propose** a change (opening a vote)?
  Deferred, see §10.
