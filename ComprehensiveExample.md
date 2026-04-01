# Drinking Blackjack — Comprehensive Examples

This file walks through complete example rounds to demonstrate how
multiple rules interact during real gameplay. Each round focuses on
different mechanics.

**Setup for all examples:**
- **Players:** Alice, Bob, Charlie
- **Seating order (clockwise):** Alice → Bob → Charlie
- **Hands per Player:** 2
- **Wager:** 1 sip per hand

> Refer to [Rules.md](Rules.md) for the full rule set.
> Rule section references are included in each step as
> (→ Rule: _section name_).

---

## Round 1: Standard Round

**Focus:** Basic hand scoring, hand outcome sips, other Players
winning all hands

**Charlie is the Dealer this round.**

### Deal

| | Hand 1 | Hand 2 |
|---|---|---|
| Dealer (Charlie) | `9♦` (face-up), `8♣` (face-down) | — |
| Alice | `K♥`, `Q♣` = 20 | `7♠`, `5♦` = 12 |
| Bob | `A♥`, `8♦` = 19 | `J♠`, `9♥` = 19 |
| Charlie | `6♣`, `7♥` = 13 | `10♦`, `4♣` = 14 |

### Card rules triggered on deal

→ Rule: _Drinking based on dealt cards_

| Card | Effect |
|---|---|
| `A♥` dealt to Bob (Hand 1) | Bob treats himself to 1 sip 🍺 |

### Player actions

| Player | Hand | Action | Result |
|---|---|---|---|
| Alice | Hand 1 (20) | Stand | 20 |
| Alice | Hand 2 (12) | Hit → `10♣` | 22 → **BUST** |
| Bob | Hand 1 (19) | Stand | 19 |
| Bob | Hand 2 (19) | Stand | 19 |
| Charlie | Hand 1 (13) | Hit → `5♠` | 18 |
| Charlie | Hand 2 (14) | Hit → `6♥` | 20 |

### Dealer plays

Dealer reveals: `9♦`, `8♣` = **17** → must stand
→ Rule: _Dealer must stand on all 17s, including soft 17_

### Results vs Dealer (17)

| Player | Hand 1 | Hand 2 | Net |
|---|---|---|---|
| Alice | 20 → **WIN** ✅ | BUST → **LOSS** ❌ | 0 |
| Bob | 19 → **WIN** ✅ | 19 → **WIN** ✅ | +2 |
| Charlie | 18 → **WIN** ✅ | 20 → **WIN** ✅ | +2 |

### Sip calculation

#### 1. Drinking based on cards

| Who | Sips | Reason |
|---|---|---|
| Bob | 1 | `A♥` treat yourself to a sip |

#### 2. Drinking based on hand outcome

→ Rule: _Drinking based on hand outcome_

| Player | Net | Sips |
|---|---|---|
| Alice | 0 (1W, 1L) | 0 — offsets cancel |
| Bob | +2 | 0 — positives disregarded |
| Charlie | +2 | 0 — positives disregarded |

#### 3. Drinking based on other Players

→ Rule: _Drinking based on other Players' hands_

**Bob won ALL his hands (2/2):**

| Player | Their result | Sips for Bob's wins |
|---|---|---|
| Alice | Lost at least 1 hand | 2 sips (1 per hand Bob won) |
| Charlie | Won all hands | 0 sips (immune) |

**Charlie won ALL hands (2/2):**

| Player | Their result | Sips for Charlie's wins |
|---|---|---|
| Alice | Lost at least 1 hand | 2 sips (1 per hand Charlie won) |
| Bob | Won all hands | 0 sips (immune) |

No Blackjacks, doubles, splits, or suited wins → no further sips.

#### 4. Dealer Switch check

→ Rule: _Dealer rules_

- Dealer won Alice's Hand 2 (bust) → Dealer did **not** lose all
  hands → ❌ No Hard Switch
- Dealer lost 5 of 6 hands → Dealer did **not** win all hands
  → ❌ No Soft Switch

### Round 1 — Final Totals 🍺

| Player | Cards | Hand Outcome | Other Players | Total |
|---|---|---|---|---|
| Alice | 0 | 0 | 2 (Bob) + 2 (Charlie) = 4 | **4 sips** |
| Bob | 1 (`A♥`) | 0 | 0 (immune) | **1 sip** |
| Charlie | 0 | 0 | 0 (immune) | **0 sips** |

> **Key takeaway:** Winning all your hands grants immunity from
> other Players' wins. Alice lost just one hand and paid heavily
> because both other Players swept.

---

## Round 2: Hard Dealer Switch with Ace of Clubs Protection

**Focus:** Hard Dealer Switch, Ace of Clubs protection, suited
winning hand

**Alice is the Dealer this round.**

### Deal

| | Hand 1 | Hand 2 |
|---|---|---|
| Dealer (Alice) | `5♥` (face-up), `A♣` (face-down) | — |
| Alice | `6♦`, `5♣` = 11 | `9♣`, `8♣` = 17 |
| Bob | `J♦`, `K♦` = 20 | `8♠`, `9♠` = 17 |
| Charlie | `A♠`, `7♥` = 18 | `10♣`, `Q♣` = 20 |

### Card rules triggered on deal

→ Rule: _Drinking based on dealt cards_

| Card | Effect |
|---|---|
| `A♣` dealt to Dealer (Alice) | Dealer is exempt from Hard Dealer Switch sips |
| `A♠` dealt to Charlie (Hand 1, 1st card) | Next Player clockwise (Alice) drinks 1 sip |

### Player actions

| Player | Hand | Action | Result |
|---|---|---|---|
| Alice | Hand 1 (11) | Double → `9♦` | 20 (doubled) |
| Alice | Hand 2 (17) | Stand | 17 |
| Bob | Hand 1 (20) | Stand | 20 |
| Bob | Hand 2 (17) | Hit → `2♠` | 19 |
| Charlie | Hand 1 (18) | Stand | 18 |
| Charlie | Hand 2 (20) | Stand | 20 |

### Dealer plays

Dealer reveals: `5♥`, `A♣` = 16 → must hit
→ Hit → `6♦` = 22 → **BUST**

### Results vs Dealer (BUST)

| Player | Hand 1 | Hand 2 | Net |
|---|---|---|---|
| Alice | 20 → **WIN** ✅ (doubled) | 17 → **WIN** ✅ | +2 |
| Bob | 20 → **WIN** ✅ | 19 → **WIN** ✅ | +2 |
| Charlie | 18 → **WIN** ✅ | 20 → **WIN** ✅ | +2 |

All Players won all hands → Dealer lost all hands
→ **Hard Dealer Switch triggered!**

### Sip calculation

#### 1. Drinking based on cards

| Who | Sips | Reason |
|---|---|---|
| Alice | 1 | `A♠` dealt to Charlie → next Player (Alice) drinks 1 sip |

#### 2. Drinking based on hand outcome

→ Rule: _Drinking based on hand outcome_

| Player | Net | Sips |
|---|---|---|
| Alice | +2 | 0 |
| Bob | +2 | 0 |
| Charlie | +2 | 0 |

#### 3. Drinking based on other Players

→ Rule: _Drinking based on other Players' hands_

All three Players won all their hands → everyone is **immune** from
rule 1 (winning all hands).

**However, exceptions still apply:**

**Alice doubled Hand 1 and won:**
→ Rule: _Doubles and splits (exception to immunity)_

| Player | Sips | Reason |
|---|---|---|
| Bob | 1 | Alice won a doubled hand |
| Charlie | 1 | Alice won a doubled hand |

**Alice's Hand 2 (`9♣`, `8♣`) is suited (both ♣):**
→ Rule: _Suited winning hand_

| Player | Sips | Reason |
|---|---|---|
| Bob | 1 | Alice won a suited hand |
| Charlie | 1 | Alice won a suited hand |

**Bob's Hand 2 (`8♠`, `9♠`, `2♠`) is suited (all ♠):**
→ Rule: _Suited winning hand_

| Player | Sips | Reason |
|---|---|---|
| Alice | 1 | Bob won a suited hand |
| Charlie | 1 | Bob won a suited hand |

**Charlie's Hand 2 (`10♣`, `Q♣`) is suited (both ♣):**
→ Rule: _Suited winning hand_

| Player | Sips | Reason |
|---|---|---|
| Alice | 1 | Charlie won a suited hand |
| Bob | 1 | Charlie won a suited hand |

#### 4. Hard Dealer Switch

→ Rule: _Drinking on behalf of the Dealer (Hard Dealer Switch)_

Dealer (Alice) lost all hands → Hard Switch triggered!

**But:** `A♣` was dealt to the Dealer → **Ace of Clubs protection
activated!** Alice drinks **0 sips** for the Hard Switch.

Without `A♣` protection, Alice would have owed:

| Player | Hand 1 | Hand 2 | Sips |
|---|---|---|---|
| Alice (self) | Win (doubled) → 2 sips | Win → 1 sip | 3 |
| Bob | Win → 1 sip | Win → 1 sip | 2 |
| Charlie | Win → 1 sip | Win → 1 sip | 2 |
| **Total** | | | **7 sips** (saved!) |

Dealer role passes to Bob.

### Round 2 — Final Totals 🍺

| Player | Cards | Hand Outcome | Other Players | Hard Switch | Total |
|---|---|---|---|---|---|
| Alice | 1 (`A♠`) | 0 | 1 (Bob suited) + 1 (Charlie suited) = 2 | 0 (`A♣` protection) | **3 sips** |
| Bob | 0 | 0 | 1 (Alice double) + 1 (Alice suited) + 1 (Charlie suited) = 3 | — | **3 sips** |
| Charlie | 0 | 0 | 1 (Alice double) + 1 (Alice suited) + 1 (Bob suited) = 3 | — | **3 sips** |

> **Key takeaway:** The `A♣` saved Alice from **7 additional sips**
> on the Hard Dealer Switch — the most powerful card in the deck!
> Even when everyone wins all hands, suited wins and doubles still
> break through immunity.

---

## Round 3: Blackjack Chaos

**Focus:** Blackjack multipliers, insurance, split 10s, Ace of
Spades Dealer rule

**Bob is the Dealer this round.**

### Deal

| | Hand 1 | Hand 2 |
|---|---|---|
| Dealer (Bob) | `A♠` (face-up), `Q♥` (face-down) | — |
| Alice | `A♠`, `J♠` = **BJ** 🔥 | `10♥`, `10♦` = 20 |
| Bob | `K♣`, `9♣` = 19 | `7♦`, `6♠` = 13 |
| Charlie | `A♦`, `K♦` = **BJ** 🔥 | `5♥`, `5♣` = 10 |

### Card rules triggered on deal

→ Rule: _Drinking based on dealt cards_

| Card | Effect |
|---|---|
| `A♠` dealt to Dealer (1st card = odd) | Dealer (Bob) drinks 1 sip |
| `A♠` dealt to Alice (Hand 1, 1st card) | Next Player clockwise (Bob) drinks 1 sip |
| `A♦` dealt to Charlie (Hand 1, 1st card) | Dealer (Bob) drinks 1 sip |

### Blackjack check — Insurance decision

→ Rule: _Blackjack Insurance_

Dealer shows `A♠` → Players with Blackjack may insure.

| Player | Hand | Decision | Effect |
|---|---|---|---|
| Alice | Hand 1 — `A♠`, `J♠` = BJ | **No insurance** | Full Blackjack penalties apply to others |
| Charlie | Hand 1 — `A♦`, `K♦` = BJ | **Takes insurance** | Blackjack treated as regular 21 → no Blackjack sips for others |

### Blackjack multiplier — Alice's Hand 1

→ Rule: _Blackjack bonus (always applies)_

Alice's `A♠` + `J♠`:

| Condition | Applies? | Multiplier |
|---|---|---|
| Base Blackjack penalty | ✅ | 1 |
| Suited (both ♠) | ✅ | ×2 |
| Specifically Ace + Jack | ✅ | ×2 |
| Both cards black | ✅ | ×2 |
| **Total** | | **1 × 2 × 2 × 2 = 8 sips** 💀 |

Everyone (Bob, Charlie) drinks **8 sips** for Alice's Blackjack.

Charlie's Blackjack (`A♦`, `K♦`) is **insured** → treated as
regular 21 → **no Blackjack sips** for others.

### Player actions

→ Rule: _Splitting 10s is mandatory unless suited_

| Player | Hand | Action | Result |
|---|---|---|---|
| Alice | Hand 1 (BJ) | — | Blackjack stands |
| Alice | Hand 2 (`10♥`, `10♦`) | **Must split** (not suited) | Split into 2 hands |
| Alice | Hand 2a (`10♥`) | Hit → `8♦` | 18 |
| Alice | Hand 2b (`10♦`) | Hit → `A♣` | 21 |
| Bob | Hand 1 (19) | Stand | 19 |
| Bob | Hand 2 (13) | Hit → `3♦` | 16, Hit → `5♥` | 21 |
| Charlie | Hand 1 (BJ) | — | Blackjack stands (insured as 21) |
| Charlie | Hand 2 (10) | Double → `A♥` | 21 (doubled) |

### Card rules triggered on actions

| Card | Effect |
|---|---|
| `A♣` dealt to Alice (Hand 2b) | Subtract 1 sip from Alice's net total (minimum 0) |
| `A♥` dealt to Charlie (Hand 2, double) | Charlie treats himself to 1 sip — **doubled** because on a double → 2 sips |

### Dealer plays

→ Rule: _Dealer does not peek at bottom card if upcard is ace_

Dealer reveals: `A♠`, `Q♥` = **21** → not Blackjack (not first 2
cards dealt as BJ), Dealer stands on 21.

Wait — `A♠` + `Q♥` **is** a two-card 21 → this **is Dealer
Blackjack!**

→ Rule: _Special insurance rule — Player's doubles and splits
are not counted if Dealer has Blackjack_

| Player | Effect |
|---|---|
| Alice | Split on Hand 2 → **not counted**, reverts to original hand (`10♥`, `10♦` = 20) |
| Charlie | Double on Hand 2 → **not counted**, reverts to original hand (`5♥`, `5♣` = 10) |

### Results vs Dealer Blackjack (21)

| Player | Hand 1 | Hand 2 | Net |
|---|---|---|---|
| Alice | BJ → **PUSH** (BJ vs BJ) | 20 → **LOSS** ❌ | -1 |
| Bob | 19 → **LOSS** ❌ | 21 → **PUSH** | -1 |
| Charlie | 21 (insured) → **PUSH** | 10 → **LOSS** ❌ | -1 |

→ Rule: _Max sips are number of hands × wager (doubles/splits
not counted)_ → Max **2 sips** per Player.

### Sip calculation

#### 1. Drinking based on cards

| Who | Sips | Reason |
|---|---|---|
| Bob | 1 | `A♠` dealt to Dealer (odd card) |
| Bob | 1 | `A♠` dealt to Alice → next Player |
| Bob | 1 | `A♦` dealt to Charlie → Dealer drinks |
| Charlie | 2 | `A♥` on doubled hand (1 × 2) |
| Alice | -1 | `A♣` subtract 1 sip from net total |

#### 2. Drinking based on hand outcome

| Player | Net | Sips |
|---|---|---|
| Alice | -1 | 1 sip (with `A♣` reduction: max(1-1, 0) = **0 sips**) |
| Bob | -1 | 1 sip |
| Charlie | -1 | 1 sip |

#### 3. Drinking based on other Players

No Player won all their hands → rule 1 does not trigger.

Alice's Blackjack multiplier was already calculated above
(8 sips to Bob and Charlie).

Charlie's Blackjack was insured → no Blackjack sips.

Alice's split and Charlie's double are **not counted** due to Dealer
Blackjack → no doubles/splits sips.

#### 4. Dealer Switch check

- Dealer did not lose all hands → ❌ No Hard Switch
- Dealer did not win all hands (pushes exist) → ❌ No Soft Switch

### Round 3 — Final Totals 🍺

| Player | Cards | Hand Outcome | Other Players | Total |
|---|---|---|---|---|
| Alice | -1 (`A♣`) | 0 (reduced from 1) | 8 (BJ from Alice? No — own BJ) → 0 | **0 sips** 🍀 |
| Bob | 3 (`A♠` Dealer + `A♠` Alice + `A♦` Charlie) | 1 | 8 (Alice BJ) | **12 sips** 💀 |
| Charlie | 2 (`A♥` doubled) | 1 | 8 (Alice BJ) | **11 sips** 😵 |

> **Key takeaway:** Alice's suited black Ace-Jack Blackjack was
> devastating — 8 sips to every other Player! But the `A♣` reduction
> saved Alice from her own hand outcome sip. Insurance on Charlie's
> Blackjack shielded everyone from additional Blackjack multiplier
> sips. Bob had a rough round as Dealer, absorbing 3 card-based
> sips from Aces alone.

---

## Round 4: Edge Cases Extravaganza

**Focus:** 5+ card 21, Four Aces, Dealer suited hand, multiple
rules stacking

**Charlie is the Dealer this round.**

### Deal

| | Hand 1 | Hand 2 |
|---|---|---|
| Dealer (Charlie) | `4♦` (face-up), `3♦` (face-down) | — |
| Alice | `A♦`, `3♦` = 14 | `A♣`, `4♣` = 15 |
| Bob | `A♥`, `A♠` = 12 | `6♦`, `5♦` = 11 |
| Charlie | `7♣`, `8♣` = 15 | `K♠`, `Q♠` = 20 |

### Card rules triggered on deal

| Card | Effect |
|---|---|
| `A♦` dealt to Alice (Hand 1, 1st card) | Dealer (Charlie) drinks 1 sip |
| `A♣` dealt to Alice (Hand 2, 1st card) | Subtract 1 sip from Alice's net total |
| `A♥` dealt to Bob (Hand 1, 1st card) | Bob treats himself to 1 sip |
| `A♠` dealt to Bob (Hand 1, 2nd card) | 2nd next Player clockwise from Bob (Bob → Charlie → Alice) → Alice drinks 1 sip |

**Four Aces check:**
→ Rule: _Four Aces on the table_

All 4 Aces (`A♦`, `A♣`, `A♥`, `A♠`) are visible after first
deal → **Everyone drinks 2 sips!** 🎉

### Player actions

| Player | Hand | Action | Result |
|---|---|---|---|
| Alice | Hand 1 (14) | Hit → `2♦` = 16 | Hit → `3♣` = 19 | 19 |
| Alice | Hand 2 (15) | Hit → `2♣` = 17 | Hit → `A♣`... |  |

Wait — there's only one `A♣` in a single deck. Let me correct:

| Player | Hand | Action | Result |
|---|---|---|---|
| Alice | Hand 1 (`A♦`, `3♦`) | Hit → `2♦` = 16, Hit → `2♣` = 18, Hit → `3♣` = **21** 🎯 | **21 with 5 cards!** |
| Alice | Hand 2 (`A♣`, `4♣`) | Hit → `5♣` = 20 | Stand → 20 |
| Bob | Hand 1 (`A♥`, `A♠`) | Split → two hands | |
| Bob | Hand 1a (`A♥`) | Hit → `10♥` = **BJ** 🔥 | Blackjack from split Aces! |
| Bob | Hand 1b (`A♠`) | Hit → `7♦` = 18 | Stand → 18 |
| Bob | Hand 2 (`6♦`, `5♦`) | Double → `10♦` = **21** (doubled) | Suited (all ♦)! |
| Charlie | Hand 1 (`7♣`, `8♣`) | Hit → `6♣` = **21** | Suited (all ♣)! |
| Charlie | Hand 2 (`K♠`, `Q♠`) | Stand (suited — exception to mandatory split) | 20 |

### Special hand rules triggered

→ Rule: _Special hand rules_

**Alice Hand 1 — 21 with 5 cards:**
Alice may hand out **5 sips** to Players of her choice.
Alice chooses: 3 sips to Bob, 2 sips to Charlie.

### Dealer plays

Dealer reveals: `4♦`, `3♦` = 7
→ Hit → `5♦` = 12 → Hit → `4♦`...

Again, single deck conflict. Correcting:
→ Hit → `6♠` = 13 → Hit → `2♥` = 15 → Hit → `3♠` = 18

Dealer's final hand: `4♦`, `3♦`, `6♠`, `2♥`, `3♠` = **18**

Dealer hand is **not suited** (mixed suits).

### Results vs Dealer (18)

| Player | Hand 1 | Hand 2 | Extra Hands | Net |
|---|---|---|---|---|
| Alice | 21 (5 cards) → **WIN** ✅ | 20 → **WIN** ✅ | — | +2 |
| Bob | BJ → **WIN** ✅ | 21 doubled → **WIN** ✅ | 18 (split) → **PUSH** | +2 (push ignored) |
| Charlie | 21 → **WIN** ✅ | 20 → **WIN** ✅ | — | +2 |

All Players won all hands → Dealer lost all hands (push ≠ win for
Dealer, but push ≠ loss either)

**Wait:** Bob's split hand pushed → Dealer did **not** lose ALL
hands → ❌ No Hard Switch

Correction: The push means the Dealer didn't lose that hand. Did
Dealer lose all other hands? Yes, but since one hand is a push,
Hard Switch is **not triggered**.

- Dealer lost 5 of 6 hands, pushed 1 → ❌ No Hard Switch
- Dealer did not win all hands → ❌ No Soft Switch

### Sip calculation

#### 1. Drinking based on cards

| Who | Sips | Reason |
|---|---|---|
| Charlie (Dealer) | 1 | `A♦` dealt to Alice → Dealer drinks |
| Alice | -1 | `A♣` subtract 1 from net total |
| Bob | 1 | `A♥` treat yourself |
| Alice | 1 | `A♠` dealt to Bob (2nd card) → 2nd next Player |
| Everyone | 2 | Four Aces on the table after first deal |

#### 2. Drinking based on hand outcome

| Player | Net | Sips |
|---|---|---|
| Alice | +2 | 0 |
| Bob | +2 | 0 |
| Charlie | +2 | 0 |

#### 3. Drinking based on other Players

All Players won all hands → everyone is **immune** from rule 1.

**But exceptions still apply:**

**Bob's Blackjack from split Aces (`A♥`, `10♥`):**
→ Rule: _Blackjack bonus (always applies)_

| Condition | Applies? | Multiplier |
|---|---|---|
| Base Blackjack | ✅ | 1 |
| Suited (both ♥) | ✅ | ×2 |
| Ace + Jack? | ❌ (Ace + 10) | — |
| Both black? | ❌ (both red) | — |
| **Total** | | **1 × 2 = 2 sips** |

Alice and Charlie each drink **2 sips** for Bob's Blackjack.

**Bob's doubled Hand 2 — won and suited (all ♦):**
→ Rule: _Doubles and splits (exception to immunity)_ → 1 sip each
→ Rule: _Suited winning hand (doubled)_ → 4 sips each

| Player | Sips | Reason |
|---|---|---|
| Alice | 1 + 4 = 5 | Bob's doubled suited win |
| Charlie | 1 + 4 = 5 | Bob's doubled suited win |

**Alice won Hand 1 with 5+ cards:**
→ Rule: _Winning with 5+ cards_ → all others drink 1 sip

| Player | Sips | Reason |
|---|---|---|
| Bob | 1 | Alice won with 5 cards |
| Charlie | 1 | Alice won with 5 cards |

**Alice's Hand 2 (`A♣`, `4♣`, `5♣`) is suited (all ♣):**
→ Rule: _Suited winning hand_ → 1 sip each

| Player | Sips | Reason |
|---|---|---|
| Bob | 1 | Alice's suited win |
| Charlie | 1 | Alice's suited win |

**Charlie's Hand 1 (`7♣`, `8♣`, `6♣`) is suited (all ♣):**
→ Rule: _Suited winning hand_ → 1 sip each

| Player | Sips | Reason |
|---|---|---|
| Alice | 1 | Charlie's suited win |
| Bob | 1 | Charlie's suited win |

**Charlie's Hand 2 (`K♠`, `Q♠`) is suited (both ♠):**
→ Rule: _Suited winning hand_ → 1 sip each

| Player | Sips | Reason |
|---|---|---|
| Alice | 1 | Charlie's suited win |
| Bob | 1 | Charlie's suited win |

#### 4. Special hand rules

| Who | Sips | Reason |
|---|---|---|
| Bob | 3 | Alice's 5-card 21 — Alice chose to give 3 to Bob |
| Charlie | 2 | Alice's 5-card 21 — Alice chose to give 2 to Charlie |

#### 5. Four Aces — end of round check

All 4 Aces are still visible at end of round → but this **cannot
stack** with the first-deal rule → no additional sips.

### Round 4 — Final Totals 🍺

| Player | Cards | 4 Aces | Hand Outcome | Other Players | Special Hands | Total |
|---|---|---|---|---|---|---|
| Alice | 1 (`A♠`) - 1 (`A♣`) = 0 | 2 | 0 | 2 (Bob BJ) + 5 (Bob double suited) + 1 (Charlie suited) + 1 (Charlie suited) = 9 | 0 | **11 sips** |
| Bob | 1 (`A♥`) | 2 | 0 | 1 (Alice 5-card win) + 1 (Alice suited) + 1 (Charlie suited) + 1 (Charlie suited) = 4 | 3 (Alice's handout) | **10 sips** |
| Charlie (Dealer) | 1 (`A♦`) | 2 | 0 | 2 (Bob BJ) + 5 (Bob double suited) + 1 (Alice 5-card win) + 1 (Alice suited) = 9 | 2 (Alice's handout) | **14 sips** 😵 |

> **Key takeaway:** This round had everything — Four Aces on the
> first deal, a 5-card 21, Blackjack from split Aces, suited hands
> everywhere, and a doubled suited win. Even with everyone winning
> all their hands, the exception rules (Blackjack, doubles, suited)
> created massive sip totals. Nobody escaped unscathed!

---

## Quick Reference — Rules Triggered in These Examples

| Rule | Round 1 | Round 2 | Round 3 | Round 4 |
|---|---|---|---|---|
| Hand outcome sips | ✅ | — | ✅ | — |
| Other Players win all hands | ✅ | — | — | — |
| Immunity (won all hands) | ✅ | ✅ | — | ✅ |
| Blackjack multiplier | — | — | ✅ | ✅ |
| Blackjack insurance | — | — | ✅ | — |
| Doubles (exception to immunity) | — | ✅ | — | ✅ |
| Suited winning hand | — | ✅ | — | ✅ |
| Suited doubled hand | — | — | — | ✅ |
| Mandatory split 10s | — | — | ✅ | — |
| Suited 10s exception | — | — | — | ✅ |
| Split Aces | — | — | — | ✅ |
| 21 with 5+ cards (hand out sips) | — | — | — | ✅ |
| Win with 5+ cards (all drink) | — | — | — | ✅ |
| Hard Dealer Switch | — | ✅ | — | — |
| Ace of Clubs protection | — | ✅ | — | — |
| `A♠` Player card rule | — | ✅ | — | ✅ |
| `A♠` Dealer card rule | — | — | ✅ | — |
| `A♥` treat yourself | ✅ | — | ✅ | ✅ |
| `A♦` Dealer drinks | — | — | ✅ | ✅ |
| `A♣` subtract 1 sip | — | — | ✅ | ✅ |
| Four Aces on first deal | — | — | — | ✅ |
| Four Aces end of round (no stack) | — | — | — | ✅ |
| Dealer Blackjack (doubles/splits voided) | — | — | ✅ | — |
| Soft Dealer Switch | — | — | — | — |
| Dealer suited hand | — | — | — | — |

> **Note:** Soft Dealer Switch and Dealer suited hand did not occur
> in these examples. See [Rules.md](Rules.md) for full details on
> these rules.

---

*For the full rule set, see [Rules.md](Rules.md).*
*Happy Gaming! 🎰 May the cards be in your favor!*
