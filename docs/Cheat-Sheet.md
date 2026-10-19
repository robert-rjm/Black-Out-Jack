# Black(Out)Jack — Cheat Sheet 🃏🍺

## Setup
- Hands: 2 per Player | Wager: 1 sip per hand (or as agreed)
- Only **net losses** result in sips (wins offset losses)
- Dealer rotates every n rounds (n = number of Players)

---

## Insurance

**Auto-Insurance (Ace up-card only)** — when Dealer shows an Ace and ends up with Blackjack, each Player's max penalty is capped at wager × hand count. Doubles/splits/suited don't push it higher. A Dealer Blackjack from a 10-value up-card (hidden Ace) never offered insurance, so normal net-loss rules apply instead.

**Player Blackjack Insurance (optional vote)** — Dealer shows an Ace + a Player has Blackjack → everyone else votes Insure/Decline (tie = Decline):

| Vote | Dealer has BJ | Dealer has no BJ |
|------|---------------|-------------------|
| Insure | BJ holder drinks own bonus, hand pushes, group drinks 0 | Group drinks **2×** normal BJ bonus |
| Decline | Normal auto-insurance (capped) | Normal BJ bonus |

---

## Ace Effects

| Ace | Dealt to Player | Dealt to Dealer |
|-----|----------------|-----------------|
| ♣ Clubs | −1× wager from your net sips | Dealer exempt from Hard Switch |
| ♠ Spades | Next Player(s) drink 1× wager | Odd card → Dealer drinks 1× wager. Even → all Players drink 1× wager |
| ♥ Hearts | You drink 1× wager | All Players drink 1× wager |
| ♦ Diamonds | Dealer drinks 1× wager | All Players (except Dealer) drink 1× wager |

---

## Side Bet: Dealer Bust Vote

Before the first deal, each Player can bet the Dealer busts (host can toggle this off):

| Your vote | Effect |
|-----------|--------|
| Correct (Dealer busted) | −1× wager credit + hand 1× wager out to anyone |
| Wrong (Dealer didn't bust) | +1× wager penalty |
| Abstain | Nothing |

---

## Devil's Hand & Lucky Sevens

Only face-up cards count (hole card / doubled card count when revealed, not when dealt). Target = the triggering card's own position in its hand, counted clockwise from whoever was dealt it. Each fires at most once per round.

| Trigger | Effect |
|---------|--------|
| 3rd six becomes visible (Devil's Hand) | Target drinks 1× wager immediately |
| 3rd seven becomes visible (Lucky Sevens) | Target gets −1× wager credit |

---

## Losing a Hand

| Situation | Sips |
|-----------|------|
| Net hand lost | 1 (wager) |
| Lost hand was doubled | +1× wager |
| Lost hand was suited | +1× wager |
| Lost hand was doubled + suited | +3× wager (4× total) |

---

## Other Players' Wins

**Another Player wins ALL their hands:**

| Your result | You drink |
|-------------|-----------|
| You lost ≥1 hand | 1× wager per hand they won |
| You won all yours | 0 (immune) |
| No losses, ≥1 push | Their wins − your wins |

**Immunity breakers (drink even if you won all):**

| Their winning hand | You drink |
|--------------------|-----------|
| Doubled | 1× wager |
| Split (per split won) | 1× wager |
| Suited | 1× wager |
| Doubled + Suited | 4× wager |

---

## Blackjack Bonus (always applies)

Everyone drinks **1× wager** when any Player gets Blackjack. Multiplied:

| Condition | Multiplier |
|-----------|:----------:|
| Suited | ×2 |
| Ace + Jack specifically | ×2 |
| Both cards black (♠/♣) | ×2 |

> Max: A♠ + J♠ = 1×2×2×2 = **8× wager** 💀

---

## Player All-Hand Bonus

If **one Player's** hands (all of them, if split) are *entirely* one suit, or *all* total exactly 21 — everyone else drinks (regardless of that Player's win/loss/push):

| Condition | Others drink |
|-----------|:---:|
| All cards same suit | 4× wager |
| All hands total 21 | 2× wager |
| Both at once | 6× wager |

---

## Special Hands

| Event | Effect |
|-------|--------|
| Player hits 21 with 5+ cards | Hand out cards × wager sips |
| Player **wins** with 5+ cards | All others drink 1× wager |
| Dealer hits 21 with 5+ cards | All wagers doubled this round |
| Dealer's hand is suited | All Players drink 2× wager |
| All 4 Aces on first deal | Everyone drinks 2× wager |
| All 4 Aces at end of round | Everyone drinks 1× wager |

---

## Dealer Switches

**Hard Switch** — Dealer loses ALL hands:

| Players' winning hand type | Dealer drinks |
|----------------------------|:-------------:|
| Regular | 1× wager |
| Blackjack | 2× wager |
| Doubled | 2× wager |
| Split | Each hand separately |
| Suited | 0 extra |

♣ Ace dealt to Dealer → Switch still happens but Dealer drinks 0.

**Soft Switch** — Dealer wins ALL hands:
Players drink their sips. Dealer drinks nothing. Role passes.

---

## Milestone Handouts

Cross a multiple of **50 cumulative sips** → earn bonus sips to hand out (5 at 50, 6 at 100, 7 at 150, +1 per milestone after). 60-second window; unassigned sips return to you.

**Back-to-back** 🔥: win *and* hand out two (or more) milestones in a row → a callout in the round log plus a 🔥 on your seat while the run lasts, no sips. A forfeited window, a win with nobody to give to, or anyone else winning in between breaks the run.

**Worst-average penalty**: the Player with the lowest average sips/round (excluding the winner) is flagged "worst." Flagged **two milestones in a row** → one-time penalty, drink the winner's average sips/round (always rounded up, min 1).

**"L" badge**: 5+ consecutive round losses → holds the L (only one Player at a time — whoever's losing streak is currently longest). Another Player's streak strictly overtaking the holder's transfers the L and costs the outgoing holder 1 sip; earning it or losing it to your own streak breaking never costs a sip, and ties don't dethrone.

---

## Dealer Lottery

Dealer's final hand is a **paired 18** (two 9s) or **paired 20** (two ten-value cards) → everyone picks a stake **X = 0-5 wagers** and the pair redeals into fresh hands (re-splits again on another matching pair, capped at 5 hands total across both branches):

| Result | Effect |
|--------|--------|
| 2+ hands bust | Credit = min(X × wager, what you owe) sips, hand ceil(credit/2) out to another Player (always halved) |
| Exactly 1 busts | Nothing happens |
| No hand busts | Drink X × (hands − 1) × wager sips, max 10 × wager (never halved) |

---

## Targeted Drinking Mode

Starts three ways: **host** picks target(s) from Settings → Players and force-starts; tapping a Player's **name at the table** to **propose** them opens a 15s table-wide Yes/No vote (proposer auto-votes Yes; passes past 50%, or fails and freezes the proposer from proposing again for 3 rounds); or the **Wild Card 🃏** easter egg picks a random target. Once a normal round ends, the **host or current dealer** taps **Start Targeting Now** (lets the table finish drinking for that round first) — then a fresh isolated Dealer hand is dealt and targeted Players must call **BUST** or **STAND** on it before it's played out (15s window; no answer defaults to STAND):

| Outcome | Effect |
|---------|--------|
| Correct | Graduation streak +1 — 3 in a row **including at least one BUST and one STAND** and you're released |
| Wrong | Graduation streak resets to 0. Drink a flat **2 sips** — counts toward your total, not toward "worst average/round" |

A live stats table (correct/wrong per Player, dealer bust %) runs the whole time so you can call it smarter, not blind. Still running after a mini-hand resolves? The host/dealer taps **Continue** to open the next one right away, back-to-back (or a 12s safety-net timeout does it automatically) — no normal round in between. 3-round cooldown once everyone's released or it's cancelled.

**Perfect run bonus:** graduate without ever missing (3 attempts, 3 corrects — the fastest possible) and you get to hand out **3 sips** to anyone (20s to pick, or you keep them) — blocks the next mini-hand until claimed.

---

## Group Size & Easy Mode

| Situation | Effect |
|-----------|--------|
| 4+ players | All end-of-round drinks halved automatically (rounded up) |
| Easy Mode ON | Same halving, any group size — toggle in setup or admin settings |

---

## Key Reminders
- Splitting 10s is **mandatory** (unless suited)
- Dealer stands on all 17s
- Max 5 splits per starting hand
- Split Aces → can hit/double/split again; BJ counts as BJ
- Insurance → your BJ treated as regular 21

---

_Full rules: see [Rules.md](Rules.md)_ 🍻
