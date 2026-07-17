# Black(Out)Jack — Cheat Sheet 🃏🍺

## Setup
- Hands: 2 per Player | Wager: 1 sip per hand (or as agreed)
- Only **net losses** result in sips (wins offset losses)
- Dealer rotates every n rounds (n = number of Players)

---

## Insurance

**Auto-Insurance (always on)** — when Dealer has Blackjack, each Player's max penalty is capped at wager × hand count. Doubles/splits/suited don't push it higher.

**Player Blackjack Insurance (optional vote)** — Dealer shows an Ace + a Player has Blackjack → everyone else votes Insure/Decline (tie = Decline):

| Vote | Dealer has BJ | Dealer has no BJ |
|------|---------------|-------------------|
| Insure | BJ holder drinks own bonus, hand pushes, group drinks 0 | Group drinks **2×** normal BJ bonus |
| Decline | Normal auto-insurance (capped) | Normal BJ bonus |

---

## Ace Effects

| Ace | Dealt to Player | Dealt to Dealer |
|-----|----------------|-----------------|
| ♣ Clubs | −1 from your net sips | Dealer exempt from Hard Switch |
| ♠ Spades | Next Player(s) drink 1 | Odd card → Dealer drinks 1. Even → all Players drink 1 |
| ♥ Hearts | You drink 1 | All Players drink 1 |
| ♦ Diamonds | Dealer drinks 1 | All Players (except Dealer) drink 1 |

---

## Side Bet: Dealer Bust Vote

Before the first deal, each Player can bet the Dealer busts (host can toggle this off):

| Your vote | Effect |
|-----------|--------|
| Correct (Dealer busted) | −1 sip credit + hand 1 sip out to anyone |
| Wrong (Dealer didn't bust) | +1 sip penalty |
| Abstain | Nothing |

---

## Devil's Hand & Lucky Sevens

Only face-up cards count (hole card / doubled card count when revealed, not when dealt). Target = the triggering card's own position in its hand, counted clockwise from whoever was dealt it. Each fires at most once per round.

| Trigger | Effect |
|---------|--------|
| 3rd six becomes visible (Devil's Hand) | Target drinks 1 sip immediately |
| 3rd seven becomes visible (Lucky Sevens) | Target gets −1 sip credit |

---

## Losing a Hand

| Situation | Sips |
|-----------|------|
| Net hand lost | 1 (wager) |
| Lost hand was doubled | +1 |
| Lost hand was suited | +1 |

---

## Other Players' Wins

**Another Player wins ALL their hands:**

| Your result | You drink |
|-------------|-----------|
| You lost ≥1 hand | 1 per hand they won |
| You won all yours | 0 (immune) |
| No losses, ≥1 push | Their wins − your wins |

**Immunity breakers (drink even if you won all):**

| Their winning hand | You drink |
|--------------------|-----------|
| Doubled | 1 |
| Split (per split won) | 1 |
| Suited | 1 |
| Doubled + Suited | 4 |

---

## Blackjack Bonus (always applies)

Everyone drinks **1 sip** when any Player gets Blackjack. Multiplied:

| Condition | Multiplier |
|-----------|:----------:|
| Suited | ×2 |
| Ace + Jack specifically | ×2 |
| Both cards black (♠/♣) | ×2 |

> Max: A♠ + J♠ = 1×2×2×2 = **8 sips** 💀

---

## Player All-Hand Bonus

If **one Player's** hands (all of them, if split) are *entirely* one suit, or *all* total exactly 21 — everyone else drinks (regardless of that Player's win/loss/push):

| Condition | Others drink |
|-----------|:---:|
| All cards same suit | 2× wager |
| All hands total 21 | 2× wager |
| Both at once | 4× wager |

---

## Special Hands

| Event | Effect |
|-------|--------|
| Player hits 21 with 5+ cards | Hand out sips = number of cards |
| Player **wins** with 5+ cards | All others drink 1 |
| Dealer hits 21 with 5+ cards | All wagers doubled this round |
| Dealer's hand is suited | All Players drink 2 |
| All 4 Aces on first deal | Everyone drinks 2 |
| All 4 Aces at end of round | Everyone drinks 1 |

---

## Dealer Switches

**Hard Switch** — Dealer loses ALL hands:

| Players' winning hand type | Dealer drinks |
|----------------------------|:-------------:|
| Regular | 1 |
| Blackjack | 2 |
| Doubled | 2 |
| Split | Each hand separately |
| Suited | 0 extra |

♣ Ace dealt to Dealer → Switch still happens but Dealer drinks 0.

**Soft Switch** — Dealer wins ALL hands:
Players drink their sips. Dealer drinks nothing. Role passes.

---

## Milestone Handouts

Cross a multiple of **50 cumulative sips** → earn bonus sips to hand out (5 at 50, 6 at 100, 7 at 150, +1 per milestone after). 60-second window; unassigned sips return to you.

**Worst-average penalty**: the Player with the lowest average sips/round (excluding the winner) is flagged "worst." Flagged **two milestones in a row** → one-time penalty, drink the winner's average sips/round (rounded, min 1).

---

## Dealer Lottery

Dealer's final hand is a **paired 18** (two 9s) or **paired 20** (two ten-value cards) → everyone picks a stake **X = 0-5** and the pair redeals into fresh hands (re-splits again on another matching pair):

| Result | Effect |
|--------|--------|
| 2+ hands bust | Credit up to X sips off what you owe, hand X out to another Player |
| Exactly 1 busts | Nothing happens |
| No hand busts | Drink X × (hands − 1) sips (never halved) |

---

## Targeted Drinking Mode

Host targets one or more Players from **Settings → Players**. Once a normal round ends, anyone taps **Start Targeting Now** (lets the table finish drinking for that round first) — then a fresh isolated Dealer hand is dealt and targeted Players must call **BUST** or **STAND** on it before it's played out (15s window; no answer defaults to STAND):

| Outcome | Effect |
|---------|--------|
| Correct | Streak +1 — 3 in a row and you're released |
| Wrong | Streak resets to 0, +1 sip (counts toward your total, not toward "worst average/round") |

Still running after a mini-hand resolves? The next one starts right away, back-to-back — no normal round in between. 3-round cooldown once everyone's released or the host cancels.

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
