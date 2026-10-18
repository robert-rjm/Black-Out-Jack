# Drink Rate Mode ("Wine Mode")

Status: **implemented** (engine, service, routes, serializer, UI, tests). Rules.md section 6.3 is written; Terms.md is untouched.

Origin: a "wine mode" so that someone drinking wine (or a cocktail) takes fewer sips than someone drinking beer, plus an opt-in way to drink *more* (late joiners catching up). An earlier draft derived the factor from ABV; that was dropped as too complex (see section 6).

---

## 1. The concept

Each **seat** has a **rate** (multiplier). Default `1.0`. For any sip event, the seat drinks `ceil(rate x sips)`, applied to the receiver, after the wager multiplier.

- Rates below 1.0 are a **discount** (wine, cocktails, anything stronger than beer).
- Rates above 1.0 are a **booster** (late joiners catching up, or anyone who wants a handicap). Maximum 1.5.
- The game stays a penalty game: rounding is always up, so a 1-sip event is never discounted at any rate.

### Fairness principle

> **Anyone can always choose to drink more. Drinking less needs the table's approval.**

This is what keeps the feature from being "I'm drinking wine, so I'll just drink less".

---

## 2. Rates and presets

- **Default: 1.0 (beer).** Everyone starts here.
- Built-in presets: **Wine 0.6**, **Cocktail 0.4**.
- Discounts: any value from **0.2 to 1.0** in steps of **0.2** (0.2, 0.4, 0.6, 0.8, 1.0). Rounding up makes 0.1 steps pointless: 0.1 and 0.2 give the same result for anything up to 5 sips.
- Boosters: **1.2, 1.4 and 1.5** (0.2 steps, with 1.5 as the allowed maximum).
- When proposing, show a live preview of what the rate means after rounding (e.g. "1->1, 2->1, 3->2, 4->2...").

### Effect of rounding up

- A discount never takes a 1-sip event below 1, so 1-sip events and 1-sip handouts are unchanged at every rate.
- The real saving shows on larger events (doubles, wager-scaled penalties, streak-scaled Targeted Drinking). See the table in section 6.

---

## 3. Who can change a rate

| Change | Who decides |
|---|---|
| Raise your own rate (toward 1.0, or above 1.0) | **The player, any time, no vote** |
| Reset to 1.0 ("normalize") | **The player, any time, no vote.** Starts the protection window below. |
| Lower a rate (more discount), own or someone else's | Admin proposes, **strict majority** of connected seated players. The beneficiary **does** vote. |
| Booster (above 1.0) imposed on someone | Admin proposes, **strict majority**, same as a discount, **unless the player is protected** (below). |

- The proposer's own vote is pre-filled Yes, same as the target-proposal vote.
- Because the beneficiary votes, a 3-player table passes any single-player proposal as soon as the admin and the beneficiary agree (2 of 3). The vote only really protects tables of 4+ or "everyone" proposals. Accepted trade-off.
- Changes take effect from the next round. Each change adds a log line and a marker on the seat (e.g. a wine glass and the rate).

### Protection window after normalizing

- When a player resets their own rate to 1.0, they cannot be given **any new rate** by majority vote for **X = 3 rounds** **unless they explicitly vote Yes themselves**.
- For a protected player a proposal needs **both** the majority **and** their own Yes. Their No is a veto.
- This stops a table from repeatedly voting a booster onto someone right after they dropped out of one.
- Players can always drop back down, so a booster is never a trap.

### Late-joiner catch-up (booster use case)

- A late joiner is behind the table average in effective sips.
- The table can propose a booster for them, or they can take one themselves (always allowed). The app can suggest a rate by showing the gap.
- Boosters have no automatic expiry. The player can drop to 1.0 at any time.

---

## 4. Tracking and milestones

- **Effective sips** (after the rate) drive everything that makes someone drink: sip ticker, milestone boundaries, the "worst average" penalty, the Drinks panel.
- **Raw sips** drive luck and strategy stats: decision log, strategy accuracy, KPIs, simulation benchmarks. Exports carry both columns.
- Display: "1 sip (2 raw)" so players see that nothing was lost.
- Check the milestone rules (Rules.md) before building, to confirm they really should use effective totals.

### Handouts

- A discounted player hands out sips exactly like everyone else (handing out is not scaled).
- The receiver's rate applies. With round-up, a **1-sip handout is always 1 sip** to a discounted player; multi-sip handouts (e.g. the 3-sip perfect-graduation handout) shrink.

### Caps and paybacks

- Thresholds such as the Targeted Drinking easter-egg 5-sip cap and its payback compare on **raw** sips, so rules behave the same for everyone.

---

## 5. Seats and bots

- The rate belongs to the **seat**, not the client. If the admin absorbs an AFK seat, the rate stays with it.
- **Bots** use a rate only when **every human seat shares the same rate**; then bots use it too. If any human differs, bots drop to 1.0. This is derived, never stored, so it updates automatically when someone changes.

---

## 6. Rounding

- **Rates below 1.0 (discounts): always round up** (`ceil`). Never below 1 sip.
- **Rates above 1.0 (boosters): a fraction of 0.25 or more rounds up to the next sip; below 0.25 rounds down.**

Why boosters get their own rule: plain `ceil` turns every 1-sip event into 2 at any rate above 1.0 (1.1 already does), which makes a catch-up booster brutal.

| sips owed | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| 1.2 | 1 | 3 | 4 | 5 | 6 |
| 1.4 | 2 | 3 | 4 | 6 | 7 |
| 1.5 | 2 | 3 | 5 | 6 | 8 |

- 1.2 leaves 1-sip events alone; 1.4 and 1.5 double them.
- Note 1.4 x 3 = 4.2 stays at 4, while 1.5 x 3 = 4.5 goes to 5.

### Discount levels on the 0.2 grid

| sips owed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 0.2 | 1 | 1 | 1 | 1 | 1 | 2 | 2 | 2 |
| 0.4 | 1 | 1 | 2 | 2 | 2 | 3 | 3 | 4 |
| 0.6 | 1 | 2 | 2 | 3 | 3 | 4 | 5 | 5 |
| 0.8 | 1 | 2 | 3 | 4 | 4 | 5 | 6 | 7 |

Five levels that are each clearly different. The wine (0.6) and cocktail (0.4) presets sit on the grid.

---

## 7. Rejected: ABV-derived factor

An earlier draft computed `rate = beer ABV / drink ABV` from a drink type. Dropped: too much machinery, and sip size varies more between people than between drinks, so the precision was false. Kept here so we remember why.

---

## 8. Implementation outline

- Per-seat `drink_rate` on `GameRoom` (default 1.0), plus a `protected_until_round` set when a player normalizes to 1.0.
- Apply once, at the receiver, in `player.add_drink()` and `award_sips()` (`app/services/drink_tracker.py`), after the wager multiplier.
- Store raw and effective on CSV rows and `drink_log` tuples; serialize rate and raw/effective to the frontend.
- Majority vote: reuse the target-proposal pattern (timed Yes/No window, forfeit on expiry).
- Self-service route: raise or reset your own rate; accept or decline an offered booster.
- Default 1.0 everywhere, so existing tests, snapshots and benchmarks are unchanged.

### Checklist

- [x] Per-seat rate, derived bot rate, protection window after normalizing
- [x] Rounding rules (ceil below 1.0; fraction of 0.25 or more rounds up above 1.0)
- [x] Apply at the receiver in `add_drink` / `award_sips`; raw + effective stored
- [x] Admin proposal + majority vote (beneficiary votes); self-service raise/reset
- [x] Booster proposal flow; protected player needs own Yes
- [x] Late-joiner catch-up suggestion: one-time recommended-booster modal when a human takes over a bot seat (`offer_late_join_boost`)
- [x] UI: seat marker, preview, "(N raw)" display
- [x] Exports: raw and effective columns (`sips_raw` on the Raw Rows sheet)
- [ ] Rules.md / Terms.md note that sip counts are adjusted when a rate is active
- [x] Tests: rounding table, receiver-vs-giver, bots follow the shared rate, self-increase without a vote, protected player needs own Yes, majority alone can impose a booster otherwise

---

## 9. Open questions

None outstanding.

### Resolved

- Default 1.0 (beer), Wine 0.6, Cocktail 0.4.
- Protection window X = 3 rounds, **fixed** (the admin cannot change it).
- The protection window covers **any new rate, discounts included**: a protected player needs both the majority and their own Yes.
- Boosters allowed up to 1.5; rounding for boosters: a fraction of 0.25 or more rounds up.
- 0.2 steps for the rate grid.
