# Drink Type Mode ("Wine Mode")

Status: **brainstorm only, nothing implemented.** Captures the concept and the open design decisions so we can decide whether and how to build it.

Origin: the idea was a "wine mode" where the dealer can set all players, or a single player, to take fewer sips, to reflect that a sip of wine is not equal to a sip of beer. The first sketch was a flat factor such as 0.6, rounded up. This doc replaces that with an ABV-derived model, for the reasons below.

---

## 1. The concept

### What does "fair" mean?

Two readings, and this feature only makes sense under the first:

1. **Equal alcohol intake.** A sip of ~12% wine carries about 2.4x the ethanol of the same sip of ~5% beer. Everyone takes the same number of sips, but the wine drinker gets drunker. That is a fairness problem and a safety problem.
2. **Equal participation.** Everyone takes the same number of sips regardless of drink. This is how the game works today: simple and social.

Wine mode picks reading 1. That changes the game's contract from "N sips" to "N beer-equivalents", so it should be a deliberate decision.

### Why a hand-picked 0.6 is the wrong number

- For equal sip volume, the ethanol ratio is about 5/12, roughly **0.42**, not 0.6.
- With round-up (ceil) on a typical 1-2 sip event, the real discount ends up closer to 20%, so it is not a faithful representation either.
- A number someone picks by hand is still mental maths ("I'm drinking wine so I need to drink less"), just done once at setup.

### The principled alternative

- Each player picks what they are drinking at setup: beer (~5%), cider (~5%), wine (~12%), spirits/shots (~40%), or a custom ABV.
- The app computes `factor = reference ABV / drink ABV`, with beer as the reference.
- The player sees something like "wine = 0.4x beer sips" and can check the working. Nobody picks a number to be kind to themselves.

### Reasons not to build it

- Sip size varies far more between people than between drinks. The ABV ratio assumes a standard sip, so it is a fair approximation, not a measurement.
- The game's appeal is simplicity. One more setup question and one more number on screen has a cost.
- Mixed drink types make end-of-session stats harder to read.

### Verdict

Worth building if it stays small: the fairness gain, and the safety gain for anyone who would otherwise drink wine at beer pace, outweigh the cost.

---

## 2. Design decisions

| # | Topic | Decision / recommendation |
|---|-------|---------------------------|
| 1 | **Who sets it** | Only the player, for their own seat. A dealer override defeats the purpose and lets a dealer quietly discount themselves. A table-wide default is fine if each player confirms their own glass. |
| 2 | **Effective vs raw sips** | Store both. **Effective** sips drive everything that makes someone drink: sip ticker, milestones, handouts, "worst average" penalty, Drinks panel. **Raw** sips drive luck and strategy stats: decision log, strategy accuracy, KPI, simulation benchmarks. Effective-only makes wine players look luckier than they are; raw-only makes milestones and handouts unfair. |
| 3 | **Rounding** | Matters more than the factor. Per-event ceil leaves small penalties unchanged and defeats the feature. Preferred: carry a fractional remainder per player (round the running total, not each event). Show the carry in the UI so it never feels hidden. Fallback: round per round. |
| 4 | **Giver vs receiver** | Scale by who *drinks*. Sips a wine player hands out are not scaled (handing out is a choice, not an intake). Sips handed to a wine player are scaled. |
| 5 | **Caps and paybacks** | Anything compared to a threshold (easter-egg 5-sip cap, milestone boundaries, graduation payback) uses one defined unit, preferably beer-equivalents, so rules behave the same for everyone. Effective sips are only for what is actually poured. |
| 6 | **Display** | Effective number prominent, raw value small, e.g. "1 sip (3 beer-sips)". One-line explainer of how the factor was derived. |
| 7 | **Defaults and safety** | Default factor 1.0 (beer) so existing snapshots and benchmarks don't change. Clamp the factor to a sane range (e.g. 0.1-2.0). Short note that this is a game aid, not medical or driving advice. |
| 8 | **Generalisation** | Nothing needs to be wine-specific. A per-player `drink_factor` plus a drink-type preset list (beer, cider, wine, spirits, custom) is the same code. |

### Where it plugs in

Sips reach the ledger through two paths: `player.add_drink()` (before the harvest) and `award_sips()` (after it, in `app/services/drink_tracker.py`). The wager scaling already touches these, so apply the factor at the same choke points, **after** the wager multiplier, at the receiver. Applying it earlier lets rules that bypass those paths (Dealer Lottery, Targeted Drinking, milestones) leak full-value sips.

CSV rows and `drink_log` tuples gain raw and factor information alongside the effective `sips`.

---

## 3. Suggested first version

- [ ] Per-player drink type with ABV-derived factor, plus a custom ABV option
- [ ] Fractional carry per player, applied at the receiver inside `add_drink` / `award_sips`
- [ ] Effective and raw sips both stored (ledger, CSV export, serializer)
- [ ] Setup UI: pick drink type, show the derived factor and how it was computed
- [ ] Drinks panel shows effective sips with raw in small text
- [ ] Factor clamped to a safe range; default 1.0 leaves all existing tests and snapshots unchanged
- [ ] Tests: carry maths, receiver-vs-giver, thresholds in beer-equivalents, default 1.0 no-op

Deferred until the first version has been played:

- [ ] Per-event display of the carry
- [ ] Sip-size calibration per player
- [ ] Mixed-drink session summary
- [ ] Table-wide default drink type

---

## 4. Open questions

- Is the reference always beer at ~5%, or should it be configurable per room?
- Does the carry reset between sessions, or persist for the room's lifetime?
- Should a player be able to change drink type mid-session (queued to next round, like other settings)?
- Do the Rules.md and Terms.md need a note that sip counts are in beer-equivalents when this is on?
