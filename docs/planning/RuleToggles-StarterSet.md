# Rule Toggles — Simplified "Starter" Ruleset & Presets

Companion docs:
[Rules-Catalog.md](../Rules-Catalog.md) (rule IDs) ·
[RuleToggles-SettingsModal.md](RuleToggles-SettingsModal.md) (UI) ·
[RuleToggles-Implementation.md](RuleToggles-Implementation.md) (code plan).

Picks up the `TODO.md` feature item:

> - [ ] simplified ruleset
>   - [ ] reduced ruleset for beginners / introduction into the game
>   - [ ] have feature to select each additional rule (start with simplified
>     and then able to add 1 rule at a time)

## 1. Goal

A first-time table should be able to start playing after a **2-minute
explanation** and still feel that this is *Black(Out)Jack*, not plain
blackjack with sips. From there the admin adds rules one at a time until the
table is on the full ruleset.

## 2. How we judged each rule

Each rule in the catalog was scored on five questions:

| # | Question | Why it matters |
|---|---|---|
| 1 | **Can you explain it in one sentence?** | It's the beginner's first session. |
| 2 | **Does it come up often?** (fires in ≳10% of rounds) | A rare rule costs explanation time and pays back little. A beginner forgets it before it fires. |
| 3 | **Does it need table maths?** | In Referee mode (real cards) people calculate by hand. Multipliers, positional targeting and caps slow the table down. |
| 4 | **Does it stand on its own?** | A rule whose meaning depends on another rule (A♣-dealer → Hard Switch) can't be in a preset without its parent. |
| 5 | **Is it part of the identity?** | "Splitting 10s is mandatory", "the dealer seat is dangerous", "Blackjack makes everyone drink". |

Two more things push a rule toward the Starter set:

- **The app runs it for you.** Milestones pop a modal and explain
  themselves, so the *learning* cost is close to zero in digital mode.
- **It protects people.** The auto-insurance cap stops a runaway round. A
  safety net belongs in the beginner set even though nobody has to learn it.

## 3. Scoring (abridged)

✅ good · ⚠️ partial · ❌ poor

| Rule ID | 1-sentence | Frequent | No maths | Standalone | Identity | → Preset |
|---|---|---|---|---|---|---|
| `core.net_loss` | ✅ | ✅ | ✅ | ✅ | ✅ | **Locked** |
| `core.dealer_rotation` | ✅ | ✅ | ✅ | ✅ | ✅ | **Locked** |
| `table.split_tens` | ✅ | ⚠️ | ✅ | ✅ | ✅✅ (tagline) | **Starter** |
| `switch.hard` | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | **Starter** |
| `bonus.blackjack` (flat) | ✅ | ✅ | ✅ | ✅ | ✅ | **Starter** |
| `others.wins_all` | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | **Starter** |
| `loss.doubled` | ✅ | ✅ | ✅ | ✅ | ⚠️ | **Starter** |
| `insurance.auto_cap` | ⚠️ | ⚠️ | ✅ (passive) | ✅ | ❌ | **Starter** (safety net) |
| `milestone.handout` | ✅ | ⚠️ | ✅ (app-run) | ✅ | ✅ | **Starter** |
| `milestone.back_to_back` | ✅ | ❌ | ✅ | needs milestone | ❌ | **Starter** (cosmetic, free) |
| `ace.*` (8 rules) | ⚠️ each | ✅ | ⚠️ (positional ♠) | ✅ | ✅ | Standard |
| `bonus.blackjack.multipliers` | ⚠️ | ⚠️ | ❌ | needs BJ bonus | ✅ | Standard |
| `loss.suited` | ✅ | ✅ | ⚠️ (×4 combo) | ✅ | ⚠️ | Standard |
| `others.immunity.*` | ❌ | ✅ | ⚠️ | ✅ | ⚠️ | Standard |
| `side.bust_vote` | ✅ | ✅ | ✅ | ✅ | ⚠️ | Standard |
| `dealer.suited_hand` | ✅ | ⚠️ | ✅ | ✅ | ❌ | Standard |
| `four_aces.*` | ✅ | ❌ | ✅ | ✅ | ❌ | Standard |
| `five_card.player_21` / `player_win` | ✅ | ❌ | ✅ | ✅ | ⚠️ | Standard |
| `table.split_aces` / `split_ace_bj` | ✅ | ❌ | ✅ | ✅ | ❌ | Standard |
| `five_card.dealer_21` | ❌ (scope list) | ❌ | ❌ | ✅ | ❌ | Full |
| `insurance.bj_vote` | ❌ | ❌ | ❌ | needs BJ bonus | ⚠️ | Full |
| `cards.devils_hand` / `lucky_sevens` | ⚠️ | ❌ | ❌ (targeting) | ✅ | ⚠️ | Full |
| `sweep.*` | ✅ | ❌ | ✅ | ✅ | ❌ | Full |
| `milestone.worst_average` | ❌ | ❌ | ✅ (app) | needs milestone | ❌ | Full |
| `streak.l_badge` | ⚠️ | ❌ | ✅ (app) | ✅ | ⚠️ | Full |
| `event.dealer_lottery` | ❌ | ❌ | ✅ (app) | ✅ | ✅ | Full |
| `event.targeted` (+ handout) | ❌ | — (on demand) | ✅ (app) | ✅ | ✅ | Full |
| `event.wild_card` (+ targeted) | ✅ | — (on demand) | ✅ | ✅ | ⚠️ | Full |

## 4. The presets

Presets are nested: **Starter ⊂ Standard ⊂ Full**. **Full** is exactly
today's behaviour, so existing rooms, tests and simulation snapshots don't
change.

### 4.1 🟢 Starter: "Learn the game" (8 rules + 2 locked)

| Rule | One-line pitch for the table |
|---|---|
| 🔒 `core.net_loss` | "Lose more hands than you win → drink the difference." |
| 🔒 `core.dealer_rotation` | "The dealer seat rotates, and it's the dangerous one." |
| `table.split_tens` | "Two unsuited 10s? You **must** split, or drink to chicken out." |
| `loss.doubled` | "Lose a double → one extra." |
| `bonus.blackjack` (flat 1×) | "Anyone hits Blackjack → everyone else drinks one." |
| `others.wins_all` | "Someone wins every hand → if you lost one, drink per hand they won." |
| `switch.hard` | "Dealer loses every hand → dealer drinks for each winning hand." |
| `insurance.auto_cap` | *(nobody needs to learn it)* dealer Blackjack on an Ace never costs more than one per hand. |
| `milestone.handout` + `milestone.back_to_back` | *(the app explains it when it happens)* every 50 sips you get sips to hand out. |

Why this set:

- **The three identity pillars are in:** mandatory 10s, a dangerous dealer
  seat, and Blackjack hitting everyone.
- **There are no multipliers** except the obvious one (double loss +1). No
  suits, no positions, no exceptions to exceptions.
- **The table can still react to someone else's run** (`others.wins_all`).
  Without it, the game is solitary.
- **Volume is lower but still a drinking game.** See §6 for how to measure
  it before shipping the numbers in the UI.

What's deliberately missing, and the one-liner for a curious player:

- *Aces:* "Each Ace does something. We'll turn them on next game."
- *Suited:* "Suits matter later. For now, ignore them."
- *Immunity breakers:* the hardest rule to explain. Leave them for last in
  Standard.

### 4.2 🟡 Standard: "House rules" (Starter + 21)

Adds everything that's frequent or fun but needs a bit more explaining:
all eight Ace effects, `bonus.blackjack.multipliers`, `loss.suited`,
`others.immunity.{doubled,split,suited}`, `side.bust_vote`,
`dealer.suited_hand`, `four_aces.*`, `five_card.player_21`,
`five_card.player_win`, `table.split_aces`, `table.split_ace_bj`.

Suggested for a group's second session, or a mixed table where some players
already know the game.

### 4.3 🔴 Full: "Black(Out)Jack" (everything)

Standard plus the rare, complex or event rules: `five_card.dealer_21`,
`insurance.bj_vote`, Devil's Hand / Lucky Sevens, `sweep.*`,
`milestone.worst_average`, `streak.l_badge`, Dealer Lottery, Targeted
Drinking (+ perfect handout), and the Wild Card (+ its Targeted launch).

**This is the default for new rooms**, so nothing changes for current
players. The setup screen offers Starter / Standard as an explicit choice.

### 4.4 ✏️ Custom

Any set that doesn't match a preset. The modal shows "Custom (based on
Standard)": the nearest preset plus a diff count.

## 5. "Add one rule at a time": the unlock path

The TODO asks to start simple and add rules one by one. Rather than leaving
the admin to guess, the modal offers a **"➕ Next rule"** button that turns on
the next rule from a fixed **recommended unlock order**. The order goes from
cheap and frequent to rare and complex, and every rule comes after its
parents:

| Step | Rule | Why at this point |
|---:|---|---|
| 1 | `ace.hearts.player` + `ace.hearts.dealer` | Easiest Aces: "A♥ = drink". Teaches that Aces do things. |
| 2 | `ace.diamonds.player` + `ace.diamonds.dealer` | "A♦ = the other side drinks". |
| 3 | `ace.clubs.player` + `ace.clubs.dealer` | "A♣ = protection". Builds on Hard Switch, which they know already. |
| 4 | `ace.spades.player` + `ace.spades.dealer` | The positional one, once they're used to the other Aces. |
| 5 | `side.bust_vote` | An interactive side bet: something to do on every deal. |
| 6 | `bonus.blackjack.multipliers` | Makes Blackjacks exciting. |
| 7 | `loss.suited` | Introduces suits as a risk factor. |
| 8 | `others.immunity.suited` | Explains *why* suited 10s don't have to be split. |
| 9 | `others.immunity.doubled` + `others.immunity.split` | Finishes the immunity story. |
| 10 | `dealer.suited_hand` | Cheap and fun. |
| 11 | `five_card.player_21` + `five_card.player_win` | Rare but a crowd-pleaser. |
| 12 | `four_aces.first_deal` + `four_aces.end_round` | Rare, one sentence. |
| 13 | `table.split_aces` + `table.split_ace_bj` | Completes the split story. |
| — | **= Standard** | |
| 14 | `event.dealer_lottery` | The app runs it, and it's a big moment. |
| 15 | `cards.devils_hand` + `cards.lucky_sevens` | Fun flavour, but the targeting needs explaining. |
| 16 | `sweep.same_suit` + `sweep.all_21` | Rare. |
| 17 | `streak.l_badge` | Social pressure, app-run. |
| 18 | `milestone.worst_average` | Punishes the slowest drinker. Only for groups that want it. |
| 19 | `insurance.bj_vote` | Complex vote, rare trigger. |
| 20 | `five_card.dealer_21` | The rule with the longest scope list. |
| 21 | `event.wild_card` (+ `.targeted`) | Chaos button. |
| 22 | `event.targeted` (+ `.perfect_handout`) | The heaviest mechanic, kept for last. |
| — | **= Full** | |

The unlock order belongs in the registry (`unlock_step` per rule), not in
the frontend, so the quiz can use it too ("you just unlocked A♥: quick
question!").

Pairs share a step because they're the same idea from two seats. The toggle
UI can still split them.

## 6. Validate the presets before shipping

These presets are educated guesses. Check them with the existing simulation
tooling before the UI quotes numbers:

1. Add `--preset {starter,standard,full}` to `scripts/simulation.py` and
   `scripts/run_all_configs.py`.
2. Run 2p/3p/4p × 1–4 decks, just as the existing snapshots do.
3. Compare **average sips/round per player** and **variance**. Targets:
   - Starter ≈ 50–65% of Full sips/round, so it clearly feels gentler but is
     still a drinking game.
   - Standard ≈ 80–90% of Full.
   - Dealer seat still the riskiest in every preset (identity pillar).
4. If Starter comes in too low, the first candidates to promote are
   `ace.hearts.*` (frequent, trivial). If it's too high, demote
   `others.wins_all`.
5. Put the measured numbers in the modal's preset chips ("≈ 2.1 sips/round")
   and in Rules.md.

**Measured (2026-10-29).** `run_simulation(..., preset=...)`, 20,000
rounds each, seed 7, 2 hands, wager 1, basic-strategy bots. Average sips
per player per round:

| Config | Starter | Standard | Full | Starter / Full | Standard / Full |
|---|---|---|---|---|---|
| 2p, 1 deck | 1.86 | 3.26 | 3.27 | 57% | 100% |
| 3p, 1 deck | 2.20 | 4.35 | 4.36 | 50% | 100% |
| 4p, 2 decks | 2.57 | 5.55 | 5.56 | 46% | 100% |

- Starter lands at the bottom of the 50–65% target at 3 players and just
  under it at 4 (where the large-group halving already applies). If
  playtests say it feels too tame, promote `ace.hearts.*` first, as
  planned above.
- Standard measures the same as Full. That's a limit of the simulation,
  not of the presets: the engine doesn't play the between-round events
  (Dealer Lottery, Targeted Drinking, Wild Card, milestones, "worst
  average", the L badge), and the engine-level Full-only rules (Devil's
  Hand / Lucky Sevens, all-hand bonus, dealer 5-card 21, insurance vote)
  are rare. The 80–90% target can't be checked this way.
- The dealer-seat check isn't possible from this output: the dealer also
  plays player hands, and the drink log splits sips by role, not by seat.
- The chips quote the 3-player numbers for Starter and Standard (≈2.2 /
  ≈4.3), as does Rules.md §6.4. Full shows its rule count only: a sips
  number would read the same as Standard's for the reason above.

Keep the Full-preset snapshots identical to today's. That doubles as the
regression proof that the gating code is a no-op when everything is on.

## 7. Open questions

- **Should Starter be the default for brand-new rooms?** Recommendation:
  no. Keep Full as the default and show the preset choice on the setup
  screen. Revisit if analytics or feedback say new tables bounce.
- **Should Normal → Drinking "graduation" (`boj_switch.py`) land on
  Starter?** A table coming from Normal mode is by definition new to the
  drinking rules. Probably yes.
- **Referee mode** (physical cards, hand maths) may want an even smaller
  "Pub" preset with Aces but no multipliers. Wait for playtest feedback.
- **Is `others.wins_all` too complex for Starter?** It's the one ⚠️ on
  "one sentence". Playtest it, and demote it if beginners ask about it.
