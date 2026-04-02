# Drinking Blackjack Rules 🃏

This document outlines the full set of rules for _**Drinking BlackJack**_: a fun, fast, and occasionally chaotic variation of classical BlackJack enhanced with custom drinking mechanics.

Unless explicitly stated here, standard BlackJack rules apply. These custom rules are designed to add energy, unpredictability, and fun to the game, especially when played socially.

**Note:** This rule set is always evolving. Players are encouraged to propose new rules during gameplay if they make the experience better.

## Table of Contents
- [Game Setup](#game-setup)
- [General Rule Modifications](#general-rule-modifications)
- [Drinking Rules](#drinking-rules)
- [Potential future rules](#potential-future-rules)
- [Example Scenarios](#example-scenarios)

## Game Setup
Drinking BlackJack is played with a standard deck of cards (or multiple decks), which is shuffled after each round. Unlike traditional BlackJack where chips are used, _**drinks act as the betting currency**_.

Every player is required to have a drink ready.

### Gameplay Rules:
| Rule | Details |
|---|---|
| Hands per Player | 2 recommended (all Players must play the same number) |
| Wager | Agreed before starting (e.g. 1 sip per hand) |
| Hand scoring | Win = +1, Loss = -1, Push = 0 |
| Net result | Only net negative scores result in sips |

> **Example (2 hands):**
> - Won 1, lost 1 → net 0 → no sips
> - Lost both → net -2 → drink 2 sips
> - Won both → net +2 → no sips (positives are disregarded)

*For fairness, all players must play with the same number of hands and wager.*

### Dealer Rules:

There is no fixed Dealer. The role rotates every _n_ rounds.

> _Recommendation:_ switch Dealer every _n_ rounds,
> where _n_ = number of Players

Being Dealer places you at a higher risk of drinking.

| Switch Type | Trigger | What Happens |
|---|---|---|
| **Hard Switch** | Dealer loses **all** hands (push ≠ loss) | Dealer drinks sips for each Player's hands (see [Drinking on behalf of the Dealer](#drinking-on-behalf-of-the-dealer-hard-dealer-switch)). Role passes to next Player. |
| **Soft Switch** | Dealer wins **all** hands (push ≠ win) | Each Player drinks their respective sips. Dealer drinks nothing. Role passes to next Player. |

- Soft Switch exemption: does not trigger if a Player takes insurance on Blackjack

_**Play with Honor:**_ You are not allowed to intentionally sabotage your own hand to reduce the risk of triggering a Hard dealer switch.


## General Rule Modifications

_Unless stated otherwise within these rules, traditional rules
of BlackJack apply._

### Core Modifications:

| Rule | Modification |
|---|---|
| Dealer stands on | All 17s, including soft 17 |
| Blackjack payout | 2:1 (sip rules outlined in [Drinking Rules](#drinking-rules)) |
| Double down | Allowed on any two-card hand, including after a split |
| Splitting 10s | **Mandatory** — the only exception is suited 10s (see [Suited winning hand](#4-suited-winning-hand)) |
| Splitting | Maximum of 5 splits per starting hand (up to 6 hands from one original hand). |

### Splitting Aces:

| Rule | Details |
|---|---|
| Number of splits | Up to the general maximum of 5 splits per starting hand |
| Wager | Counted per hand (increases with each split) |
| Blackjack on split Aces | Counts as Blackjack (not just 21) |
| After splitting | Player may hit, double, or split again |

### Blackjack Insurance:

When the Dealer shows an Ace:

| Rule | Details |
|---|---|
| Dealer peek | Dealer does **not** peek at face-down card |
| Player insurance | Player may insure their Blackjack |
| Insurance effect | Blackjack treated as regular 21 — other Players do not drink for the Blackjack |
| Dealer has Blackjack | Player's doubles and splits are not counted |
| Max sips | Number of hands × wager per hand (e.g. 2 sips with 2 hands and 1 sip wager) |

## Drinking Rules
### Drinking based on dealt cards
_If any of the below occur on a doubled hand, the sips are doubled._

#### Cards dealt to Player:
| Card | Effect |
|---|---|
| ♣ Ace of Clubs | Subtract 1 sip from your net total at the end of the round (minimum 0) |
| ♠ Ace of Spades | If dealt as 1st card, next Player drinks 1 sip. 2nd card → 2nd Player, etc. |
| ♥ Ace of Hearts | Treat yourself to a sip (drink 1 sip) |
| ♦ Ace of Diamonds | Dealer drinks 1 sip |

#### Cards dealt to Dealer:
| Card | Effect |
|---|---|
| ♣ Ace of Clubs | Dealer is exempt from drinking for a Hard Dealer Switch |
| ♠ Ace of Spades | Odd card (1st, 3rd, ...) → Dealer drinks 1 sip. Even card (2nd, 4th, ...) → all Players drink 1 sip |
| ♥ Ace of Hearts | All Players treat themselves to a sip (everyone drinks 1 sip) |
| ♦ Ace of Diamonds | All Players except Dealer drink 1 sip |

### Drinking based on hand outcome:
- Drink once for each net hand lost against the Dealer
  - _(e.g. if winning 1 hand and losing the other, penalties offset)_

### Drinking based on other Player(s) cards:
Other Players' results may cause you to drink additional sips. Your own hand outcome determines how much you are affected.

#### 1. When another Player wins ALL their hands:
| Your result | Sips you drink |
|---|---|
| You lost at least 1 hand | 1 sip per hand the other Player won |
| You won all your hands | 0 sips (immune — see exceptions below) |
| You have no losses but at least 1 push | 1 sip per hand the other Player won, minus the number of your own won hands |

> **Example (2 hands each):**
> - Other Player wins both hands. You won 1, pushed 1 → drink 2 - 1 = 1 sip
> - Other Player wins both hands. You lost 1, won 1 → drink 2 sips
> - Other Player wins both hands. You also won both → drink 0 sips

#### 2. Blackjack bonus (always applies):
If another Player gets a Blackjack (21 in first two cards), **everyone** drinks 1 sip,
regardless of your own hand result.

This includes Blackjacks from split Aces.

The base sip is **doubled cumulatively** for each of the following that applies:

| Condition | Multiplier |
|---|---|
| Suited (both cards same suit) | ×2 |
| Specifically an Ace + Jack | ×2 |
| Both cards are black (Spades or Clubs) | ×2 |

> **Examples:**
> - Ace of Hearts + King of Diamonds → base: **1 sip**
> - Ace of Hearts + Jack of Hearts → suited + Ace & Jack: 1 × 2 × 2 = **4 sips**
> - Ace of Spades + Jack of Spades → suited + Ace & Jack + both black:
>   1 × 2 × 2 × 2 = **8 sips** 💀

#### 3. Doubles and splits (exception to immunity):
If another Player wins a **doubled hand** or wins **both hands of a split**,
drink 1 sip — even if you won all your hands.

#### 4. Suited winning hand:
If another Player wins a hand where **all cards are the same suit**,
drink 1 sip.

- If the suited hand was **doubled or split**, drink **4 sips** instead of 1.
- **Note:** This is the reason suited 10s are the only acceptable
  exception to the mandatory split 10s rule
  (see [General Rule Modifications](#general-rule-modifications)).

### Special hand rules
These rules apply based on specific card combinations during gameplay.

#### 1. 21 with 5+ cards (Player):
If a Player reaches exactly **21 with 5 or more cards**, that Player may
**hand out sips** to other Players of their choice.

| Number of cards | Sips to hand out |
|---|---|
| 5 cards | 5 sips |
| 6 cards | 6 sips |
| 7+ cards | etc. |

- Sips may be distributed among multiple Players in any way the Player chooses
- The hand does **not** need to win against the Dealer for this rule to apply

> **Example:** Player hits to 21 with 6 cards → hands out 3 sips to
> Player A and 3 sips to Player B

#### 2. Winning with 5+ cards (Player):
If a Player **wins** a hand consisting of **5 or more cards**,
all other Players drink 1 sip.

- This stacks with rule 1 if the 5+ card hand is exactly 21
- A push does **not** trigger this rule — the hand must win

#### 3. Dealer suited hand:
If the Dealer's final hand is **suited** (all cards the same suit),
all Players drink 2 sips.

- This applies regardless of whether the Dealer wins or loses
- If the Dealer busts with a suited hand, Players still drink 2 sips

#### 4. Four Aces on the table:

| When | Who drinks | Sips |
|---|---|---|
| All 4 Aces are visible after the **first deal** (before any hits) | Everyone | 2 sips |
| All 4 Aces are visible at the **end of the round** (after all hits) | Everyone | 1 sip |

- "On the table" includes all Player hands and the Dealer's face-up card
- These two rules **cannot stack**: if all 4 Aces appear on the first deal
  and are still visible at the end, everyone drinks 2 sips

### Drinking on behalf of the Dealer (Hard Dealer Switch):

When the Dealer **loses all hands** (a push does NOT count as a loss),
a **Hard Dealer Switch** is triggered:
- The Dealer must drink sips based on **all Players' hands**
- The role of Dealer passes to the next Player

#### How to count sips:

Each Player's hand contributes sips to the Dealer's total:

| Hand type | Sips the Dealer drinks |
|---|---|
| Regular winning hand | 1 sip per hand |
| Blackjack (21 in first two cards) | 2 sips or more |
| Doubled winning hand | 2 sips |
| Split hands | Count each hand separately |

#### Dealer's own hands as a Player:

The Dealer is also a Player and has their own hands.
To avoid double punishment, the following exceptions apply:

| Dealer's own hand | Sips the Dealer drinks |
|---|---|
| Regular winning hand | 1 sip (same as any Player) |
| Doubled winning hand | 2 sips (double penalty still applies) |
| Split hands | Count each hand separately (no extra sip for the split itself) |

#### Ace of Clubs protection:
If the **Ace of Clubs** is dealt to the Dealer, the Dealer is
**exempt** from drinking for the Hard Dealer Switch.
The switch still occurs — the Dealer role passes to the next
Player — but the outgoing Dealer drinks 0 sips.

## Potential future rules
_These rules are under consideration and may be added in future versions.
Playtest feedback is welcome!_

### Under Review:
- **Dealer Survivor**: Everyone drinks 1 sip (even winners) if the
  Dealer does not bust with 6+ cards
- **Lucky 7s**: If a Player's hand totals exactly 21 with three 7s,
  all other Players drink 7 sips
- **Mirror Hands**: If two Players have the same hand total with the
  same number of cards, they both drink 1 sip
- **Dealer Blackjack Toast**: If the Dealer gets a Blackjack,
  everyone raises their drink and takes 2 sips together
- **Perfect Split**: If a Player splits and wins both hands with the
  same total, all other Players drink 2 sips
- **Bust Chain**: If 3 or more Players bust in the same round,
  the last Player to bust drinks 1 extra sip for each Player
  who busted before them

### Community Ideas:
_Have a rule idea? Open a pull request or suggest it mid-game!
The best rules often come from the chaos of gameplay._ 🍻

---
## Example Scenarios
Inline examples are provided throughout this document within each rule section. For quick reference:

- [Hand scoring example](#gameplay-rules)
- [Other Players' wins example](#1-when-another-player-wins-all-their-hands)
- [Blackjack multiplier examples](#2-blackjack-bonus-always-applies)
- [5+ card hand example](#1-21-with-5-cards-player)
- [Hard Dealer Switch example](#drinking-on-behalf-of-the-dealer-hard-dealer-switch)

For full round walkthroughs showing how multiple rules interact,
see [`ComprehensiveExample.md`](ComprehensiveExample.md).
