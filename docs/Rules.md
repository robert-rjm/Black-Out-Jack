# Drinking Blackjack Rules 🃏

This document outlines the full set of rules for _**Black(Out)Jack**_: a fun, fast, and occasionally chaotic variation of classical BlackJack enhanced with custom drinking mechanics.

Standard BlackJack rules apply unless explicitly modified below. These custom rules are designed to add energy, unpredictability, and fun to the game, especially when played socially.

**Note:** This rule set is always evolving. Players are encouraged to propose new rules during gameplay if they make the experience better.

## Table of Contents
- [Game Setup](#game-setup)
- [General Rule Modifications](#general-rule-modifications)
- [Drinking Rules](#drinking-rules)
- [Potential future rules](#potential-future-rules)

---

## Game Setup
Black(Out)Jack is played with a standard deck of cards (or multiple decks), shuffled after each round. Unlike traditional BlackJack where chips are used, _**drinks act as the betting currency**_.

Every player is required to have a drink ready.

### Gameplay Rules:
| Rule | Details |
|---|---|
| Hands per Player | 2 recommended (must be equal for all Players) |
| Wager | Agreed before starting (e.g. 1 sip per hand) |
| Hand scoring | Win = +1, Blackjack = +2, Loss = -1, Push = 0  |
| Net result | Only net negative scores result in sips |

> **Example (2 hands):**
> - Won 1, lost 1 → net 0 → no sips
> - Lost both → net -2 → drink 2 sips
> - Won BlackJack, lost 1 → net +1 →  no sips (positives are disregarded)
> - Won both → net +2 → no sips (positives are disregarded)

*For fairness, all players must play with the same number of hands and wager.*

### Dealer Rotation

There is no fixed Dealer. The role rotates every _n_ rounds.

> _Recommendation:_ switch Dealer every _n_ rounds,
> where _n_ = number of Players

Being Dealer carries higher drinking risk.

| Switch Type | Trigger | Effect |
|---|---|---|
| **Hard Switch** | Dealer loses **all** hands | Dealer drinks sips for all Players' hands (see [Hard Dealer Switch](#drinking-on-behalf-of-the-dealer-hard-dealer-switch)). Role passes. |
| **Soft Switch** | Dealer wins **all** hands | Each Player drinks their sips. Dealer drinks nothing. Role passes. |

- A push counts as neither a win nor a loss for switch purposes.
- Soft Switch does **not** trigger if any Player took insurance on Blackjack.
- _**Play with Honor:**_ Intentionally sabotaging your own hand to avoid a Hard Switch is not allowed.

---

## Large Group Rule (4+ Players)

When 4 or more players are in the game, all drink amounts are halved (rounded up) each round. This applies to every drink rule — net losses, BJ bonuses, sweeps, aces, and the Hard Switch.

---

## General Rule Modifications

_Unless stated otherwise within these rules, traditional rules of BlackJack apply._

| Rule | Modification |
|---|---|
| Dealer stands on | All 17s (including soft 17) |
| Blackjack payout | 2:1 (see [Drinking Rules](#drinking-rules)) |
| Double down | Allowed on any two-card hand, including after any split |
| Splitting 10s | **Mandatory** unless suited (see [Suited Exception](#2-doubles-splits-and-suited-exception-to-immunity)) |
| Splitting | Maximum 5 splits per starting hand |

### Splitting Aces:

| Rule | Details |
|---|---|
| Splits allowed | Up to the general maximum (5 per starting hand) |
| Wager | Counted per resulting hand |
| Blackjack on split Aces | Counts as Blackjack (not just 21) |
| After splitting | Player may hit, double, or split again |

### Blackjack Insurance:

When the Dealer shows an Ace and a Player has a Blackjack, a group vote is held before play begins. Everyone except the Blackjack holder votes to insure or decline. Majority wins; a tie defaults to decline. If multiple Players have Blackjack, a separate vote is held for each in deal order.

The Dealer does **not** peek at the hole card. The outcome is revealed at the end of the round with all other drinks.

| Vote | Dealer has Blackjack | Dealer has no Blackjack |
|---|---|---|
| **Insure** | BJ holder drinks their own bonus. Hand pushes. Group drinks nothing. | Group drinks double the normal BJ bonus. |
| **Decline** | Normal auto-insurance applies (max hands x wager, no extras). | Normal BJ bonus (group drinks as usual). |

> **Example:** PlayerA has A♠ + J♠ (suited, A+J, both black = 8 sips normally).
> Group votes insure + dealer has no BJ: group each drinks 16 sips.
> Group votes decline + dealer has BJ: auto-insurance, max 2 sips only.

---

## Drinking Rules

### Ace Effects (by suit)

**Dealt to Player**

| Card | Effect |
|---|---|
| ♣ Ace of Clubs | Subtract 1 sip from your net total (minimum 0). If you are also the Dealer, your own player hands are excluded from the Hard Switch penalty (see below). |
| ♠ Ace of Spades | If dealt as 1st card, next Player drinks 1 sip. 2nd card → 2nd Player, etc. |
| ♥ Ace of Hearts | Treat yourself to a sip (drink 1 sip) |
| ♦ Ace of Diamonds | Dealer drinks 1 sip |

**Dealt to Dealer**
| Card | Effect |
|---|---|
| ♣ Ace of Clubs | Dealer drinks only half the Hard Dealer Switch penalty (rounded up). |
| ♠ Ace of Spades | Odd card (1st, 3rd, ...) → Dealer drinks 1 sip. Even card (2nd, 4th, ...) → all Players drink 1 sip |
| ♥ Ace of Hearts | All Players treat themselves to a sip (everyone drinks 1 sip) |
| ♦ Ace of Diamonds | All Players except Dealer drink 1 sip |

### Hand Outcome Drinking

For each **net hand lost** against the Dealer, drink 1 sip (wager). Additional penalties:

| Condition | Extra sips |
|---|---|
| Lost hand was doubled | +1 sip |
| Lost hand was suited | +1 sip |

### Other Players' Hands

Other Players' results may cause you to drink additional sips. Your own hand outcome determines how much you are affected.

#### 1. When another Player wins ALL their hands:

| Your result | Sips you drink |
|---|---|
| You lost at least 1 hand | 1 sip per hand the other Player won |
| You won all your hands | 0 sips (immune: see exceptions below) |
| No losses but at least 1 push | Other Player's wins minus your own wins |

> **Example (2 hands each):**
> - Other Player wins both. You won 1, pushed 1 → drink 2 - 1 = 1 sip
> - Other Player wins both. You lost 1, won 1 → drink 2 sips
> - Other Player wins both. You also won both → drink 0 sips

#### 2. Doubles, Splits, and Suited (exception to immunity):

Even if you won all your hands, you still drink if another Player wins with:

| Winning Hand | Sips you drink |
|---|---|
| Double | 1 sip |
| Split (per successful split) | 1 sip each |
| Suited | 1 sip |
| Double and Suited | 4 sips |

> This is why suited 10s are the only exception to the mandatory split 10s rule.

> **Example:** Player splits twice (3 hands), wins 2 → 1 split won → others drink 1 sip

#### 3. Blackjack bonus (exception to immunity):

When any Player gets a Blackjack, **everyone** drinks 1 sip (regardless of own result).

This includes Blackjacks from split Aces.

This base sip is **doubled cumulatively**:

| Condition | Multiplier |
|---|---|
| Suited (both cards same suit) | ×2 |
| Specifically an Ace + Jack | ×2 |
| Both cards are black (Spades or Clubs) | ×2 |

> **Examples:**
> A♥ + K♦ → **1 sip**
> A♥ + J♥ → suited + A&J: 1×2×2 = **4 sips**
> A♠ + J♠ → suited + A&J + black: 1×2×2×2 = **8 sips**

### Special hand rules

These rules apply based on specific card combinations during gameplay.

#### 1. 5+ Cards

These rules trigger when a Player or Dealer holds 5 or more cards in a single hand.

| # | Who | Condition | Effect |
|---|-----|-----------|--------|
| 1 | Player | **Exactly 21** | Distribute sips equal to card count to other Players (e.g. 6 cards = 6 sips) |
| 2 | Player | **Wins** | All other Players drink 1 sip |
| 3 | Dealer | **Exactly 21** | All Players' wagers doubled |

> **Key clarifications:**
> - Rule 1 does not require a win.
> - Rule 1 and 2 stack (win with 21 and 5 cards).
> - Rule 2 does not trigger on a push.
> - Rule 3 does not include wages for Blackjack bonus or Aces.

#### 2. Player all hand bonus

If every card across all of a Player's final hands share **entirely the same suit**, or every hand totals **exactly 21**, other Players each drink double their wager. If both conditions are met simultaneously, other Players drink quadruple their wager.

> - Triggers regardless of win or push or loss.

#### 3. Dealer suited hand:

If the Dealer's final hand is entirely one suit, all Players drink 2 sips (regardless of Dealer win/loss/bust).

#### 4. Four Aces on the table:

| Timing | Sips |
|---|---|
| All 4 Aces visible after first deal (before hits) | Everyone drinks 2 |
| All 4 Aces visible at end of round | Everyone drinks 1 |

- Includes all Player hands and the Dealer's face-up card.
- These two cannot stack (first-deal rule takes precedence).

---

### Drinking on behalf of the Dealer (Hard Dealer Switch):

Triggered when the Dealer loses all hands. Dealer drinks based on all Players' winning hands, then the role passes.

| Hand type | Sips the Dealer drinks |
|---|---|
| Regular winning hand | 1 sip |
| Blackjack | 2 sip (Players also drink per Blackjack bonus) |
| Doubled winning hand | 2 sips |
| Split hands | Each hand counted separately (no extra sip for the split itself) |
| Suited hands | No extra sips for Dealer |

**Dealer's own Player hands:** The Dealer also plays as a Player, but on a Hard Switch their player-role drinking is replaced entirely by the dealer calculation above. They do not drink for their own net losses, other Players' Blackjack bonuses, or bonus sips from others' suited, doubled, or split wins.

Ace effects still apply normally. Two exceptions specific to the Hard Switch calculation:
- Dealer's own Blackjack counts as 1 sip (no multiplier)
- Dealer's own Ace of Clubs subtracts 1 sip from the Dealer's total

**Ace of Clubs protection (dealer hand):** If ♣A is dealt to the Dealer's dealer hand, the switch still occurs but the Dealer drinks 0 sips. Players still drink normally.

**Ace of Clubs protection (player hand, dealer-player only):** If ♣A is dealt to the Dealer's own player hand, they receive reduced protection: their own player hands are excluded from the Hard Switch penalty calculation, but they still drink for all other players' winning hands. The -1 sip credit still applies.

---

## Potential future rules
_These rules are under consideration and may be added in future versions.
Playtest feedback is welcome!_

- **Mirror Hands**: Two Players with same total and same card count → both drink 1
- **Perfect Split**:  Split with both hands winning at same total → others drink 2
- **Bust Chain**: 3+ Players bust → last to bust drinks 1 extra per earlier bust

_Have a rule idea? Open a pull request or suggest it mid-game!
The best rules often come from the chaos of gameplay._ 🍻

---

For full round walkthroughs showing how multiple rules interact, see [`ComprehensiveExample.md`](ComprehensiveExample.md).
