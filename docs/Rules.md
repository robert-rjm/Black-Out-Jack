# <img src="../static/img/logo.png" alt="Logo-BlackOutJack" height="48" align="absmiddle"> Drinking Black(Out)Jack Rules

This document outlines the full set of rules for _**Black(Out)Jack**_: a fun, fast, and occasionally chaotic variation of classical BlackJack enhanced with custom drinking mechanics.

Standard BlackJack rules apply unless explicitly modified below. These custom rules are designed to add energy, unpredictability, and fun to the game, especially when played socially.

> [!NOTE]
> These rules are always evolving. Players are encouraged to propose new rules during gameplay if they make the experience better.

## Table of Contents

1. [Game Setup](#1-game-setup)
2. [Dealer Rotation](#2-dealer-rotation)
3. [Rule Modifications](#3-rule-modifications-from-standard-blackjack)
    - 3.1 [Splitting Aces](#31-splitting-aces)
    - 3.2 [Insurance](#32-insurance)
4. [Drinking Rules (Instant Effect)](#4-drinking-rules-instant-effect)
    - 4.1 [Ace Effects](#41-ace-effects)
    - 4.2 [Dealer Suited Hand](#42-dealer-suited-hand)
    - 4.3 [Four Aces](#43-four-aces-on-first-deal)
    - 4.4 [Side Bet Dealer Bust](#44-side-bet-dealer-bust)
    - 4.5 [Devil's Hand and Lucky Sevens](#45-devils-hand--46-lucky-sevens)
5. [Drinking Rules (End of Round)](#5-drinking-rules-end-of-round)
    - 5.1 [Net Hand Losses](#51-net-hand-losses)
    - 5.2 [Other Player's Results](#52-other-players-results)
    - 5.3 [Blackjack Bonus](#53-blackjack-bonus)
    - 5.4 [5+ Cards (Handouts)](#54-5-cards-handouts)
    - 5.5 [Player All-Hand Bonus](#55-player-all-hand-bonus)
    - 5.6 [Four Aces at End of Round](#56-four-aces-at-end-of-round)
    - 5.7 [Hard Dealer Switch Penalty](#57-hard-dealer-switch-penalty)
    - 5.8 [Milestone Handouts](#58-milestone-handouts)
6. [Relaxed Drinking Rules](#6-relaxed-drinking-rules)
    - 6.1 [Large Group Rules](#61-large-group-rules-4-players)
    - 6.2 [Easy Mode](#62-easy-mode)
7. [Potential Future Rules](#7-potential-future-rules)
8. [Glossary](#8-glossary)

---

## 1. Game Setup

Black(Out)Jack is played with a standard deck (or multiple decks), shuffled after each round. Unlike traditional BlackJack where chips are used, _**drinks act as the betting currency**_.

Every player must have a drink ready.

| Rule | Details |
|---|---|
| Hands per Player | 2 recommended (equal for all Players) |
| Wager | 1 recommended (equal for all Players) |
| Deck | Shuffled after each round |
| Hand scoring | Win = +1, Blackjack = +2, Loss = -1, Push = 0  |
| Net result | Only net negative scores result in sips |

*For fairness, all players must play with the same number of hands and wager.*



## 2. Dealer Rotation

There is no fixed Dealer. The role rotates every _n_ rounds.

> _Recommendation:_ switch Dealer every _n_ rounds,
> where _n_ = number of Players

Being Dealer carries higher drinking risk.

### Switches

| Type | Trigger | Effect |
|---|---|---|
| **Hard Switch** | Dealer loses **all** hands | Dealer drinks penalty (see [Hard Dealer Switch](#57-hard-dealer-switch-penalty)). Role passes. |
| **Soft Switch** | Dealer wins **all** hands | Normal drinking applies. Role passes. |

**Clarifications:**
- A push counts as neither a win nor a loss for switch purposes.
- Soft Switch does **not** trigger if any Player took insurance on Blackjack.
- _Play with Honor:_ intentionally sabotaging your own hand to avoid a Hard Switch is not allowed.



## 3. Rule Modifications (from standard BlackJack)

_Unless stated otherwise within these rules, traditional rules of BlackJack apply._

| Rule | Modification |
|---|---|
| Dealer stands on | All 17s (including soft 17) |
| Double down | Allowed on any two-card hand, including after any split |
| Splitting 10s | **Mandatory** unless suited (see [Suited Exception](#immunity-exceptions-doubles-splits-suited)). Deviating on an unsuited 10-pair instead ("without honor") costs 1 sip. Splitting a **suited** 10-pair (a 20) is **not** mandatory, choosing to split it anyway costs 1 sip. |
| Splitting | Maximum 5 splits per starting hand |


### 3.1 Splitting Aces:

| Rule | Details |
|---|---|
| Splits allowed | Up to the general maximum (5 per starting hand) |
| Wager | Counted per resulting hand |
| Blackjack on split Aces | Counts as Blackjack (not just 21) |
| After splitting | Player may hit, double, or split again |


### 3.2 Insurance

#### Auto-Insurance (Always Active)

When the Dealer has Blackjack, each Player's maximum penalty is **capped at wager × number of hands**. Doubles, splits, and suited bonuses do not increase it beyond this cap.

#### Player Blackjack Insurance (Optional)

When the Dealer shows an Ace and a Player has Blackjack, a group vote is held before play begins. Everyone except the Blackjack holder votes. Majority wins; a tie defaults to decline.

If multiple Players have Blackjack, a separate vote is held for each in deal order. The Dealer does **not** peek at the hole card.

| Vote | Dealer has Blackjack | Dealer has no Blackjack |
|---|---|---|
| **Insure** | BJ holder drinks their own bonus. Hand pushes. Group drinks nothing. | Group drinks double the normal BJ bonus. |
| **Decline** | Normal auto-insurance applies (max hands x wager, no extras). | Normal BJ bonus (group drinks as usual). |

> **Example:** PlayerA has A♠ + J♠ (suited, A+J, both black = 8 sips normally).
> Group votes insure + dealer has no BJ: group each drinks 16 sips.
> Group votes decline + dealer has BJ: auto-insurance, max 2 sips only.

**Hard Dealer Switch interaction (Insure + no dealer BJ only):**

When a Hard Switch is active and the vote result is Insure + no dealer BJ, the dealer's double-penalty is softened because the Hard Switch penalty already covers them:

| Dealer's role | Effect |
|---|---|
| Dealer is a group member (not the BJ holder) | Dealer drinks 1× BJ bonus (not doubled). Hard Switch penalty applies separately. Rest of group drinks 2×. |
| Dealer is the BJ holder | Dealer drinks nothing from insurance resolution. Their Blackjack hand is excluded from the Hard Switch penalty calculation. Rest of group drinks 2×. |



## 4. Drinking Rules (Instant Effect)

These effects fire **immediately** when they occur. They are **never halved** by the Large Group Rule or Easy Mode (see [Relaxed Drinking Rules](#6-relaxed-drinking-rules)).


### 4.1 Ace Effects

**Dealt to Player**

| Card | Effect |
|---|---|
| ♣ Ace of Clubs | -1 sip from end-of-round net total (minimum 0). If you are also the Dealer, your own player hands are excluded from the Hard Switch penalty. |
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


### 4.2 Dealer Suited Hand

If the Dealer's final hand is entirely one suit, all Players drink 2 sips (regardless of Dealer win/loss/bust).


### 4.3 Four Aces on First Deal

If all 4 Aces are visible after the first deal (before any hits), everyone drinks 2 sips. This includes all Player hands and the Dealer's face-up card.


### 4.4 Side Bet Dealer Bust

Before the first deal (before any hits), each Player can place a side bet on Dealer bust.

This feature can be toggled on or off by the host at any time

| Player's Vote | Effect |
| --- | --- |
| Correctly voted bust| -1 sip and 1 sip handout to any other player |
| Incorrectly voted bust | +1 sip penalty |
| Abstain / no bet | No effect |

- The sip credit and handout are separate, credit offsets own drinks while handout goes to someone else.
- Unassigned sips within handout timer return to you as penalty


### 4.5 Devil's Hand and Lucky Sevens

**Shared mechanics** — apply to both rules:

- Only face-up cards count. The dealer's hole card and any doubled card are counted at the moment they are revealed, not when dealt.
- Target is chosen by the triggering card's **position within its hand**: the circle advances that many seats clockwise from the recipient — `(recipient_index + card_position) % number_of_players`. If the 3rd six/seven was the 1st card in its hand (+1), the next player is the target; if it was the 2nd card (+2), the player two seats clockwise is the target; and so on.
- Each rule fires at most once per round. Both can fire in the same round.

**Devil's Hand** — when the **3rd six** becomes visible, the target drinks **1 sip** immediately.

**Lucky Sevens** — when the **3rd seven** becomes visible, the target receives a **−1 sip credit** (reduces end-of-round net total by 1, minimum 0).



## 5. Drinking Rules (End of Round)

These effects resolve after all hands are played (These can be halved by Easy Mode, see [Relaxed Drinking Rules](#6-relaxed-drinking-rules)).


### 5.1 Net Hand Losses

Each player's hands are scored against the Dealer:

| Outcome | Score |
| ------- | ----- |
| Win | +1 |
| Blackjack | +2 |
| Loss | −1 |
| Push | 0 |

Only **net negative** scores result in drinking. Positives are disregarded.

> **Example (2 hands):**
> - Won 1, lost 1 → net 0 → no sips
> - Lost both → net -2 → drink 2 sips
> - Won BlackJack, lost 1 → net +1 →  no sips
> - Won both → net +2 → no sips

**Additional penalties per lost hand:**

| Condition | Extra sips |
| --------- | ---------- |
| Lost hand was doubled | +1 sip |
| Lost hand was suited | +1 sip |


### 5.2 Other Player's Results

Other players' outcomes may cause you to drink.
Your own hand outcome determines how much you are affected.

#### When another Player wins ALL their hands:

| Your result | Sips you drink |
|---|---|
| You lost at least 1 hand | 1 sip per hand the other Player won |
| You won all your hands | 0 sips (immune: see exceptions below) |
| No losses, at least 1 push | Other Player's wins minus your wins |

> **Example (2 hands each):**
> - Other Player wins both. You won 1, pushed 1 → drink 2 - 1 = 1 sip
> - Other Player wins both. You lost 1, won 1 → drink 2 sips
> - Other Player wins both. You also won both → drink 0 sips

#### Immunity exceptions (doubles, splits, suited):

Even if you won all your hands, you still drink if another Player wins with:

| Winning Hand | Sips you drink |
|---|---|
| Double | 1 sip |
| Split (per successful split) | 1 sip each |
| Suited | 1 sip |
| Double **and** Suited | 4 sips (multiplicative penalty)|

> This is why suited 10s are the only exception to the mandatory split 10s rule.

> **Example:** Player splits twice (3 hands), wins 2 → 1 split won → others drink 1 sip

> [!NOTE]
> Blackjack bonus ([Blackjack Bonus](#53-blackjack-bonus)) also applies


### 5.3 Blackjack Bonus

When any Player gets a Blackjack, **all other Players** drinks 1 sip (regardless of own result).
This includes Blackjacks from split Aces.
No immunity applies.

The base 1 sip is **doubled cumulatively** for:

| Condition | Multiplier |
| --------- | ---------- |
| Suited (both cards same suit) | ×2 |
| Specifically an Ace + Jack | ×2 |
| Both cards are black (♠ or ♣) | ×2 |

> **Examples:**
> A♥ + K♦ → **1 sip**
> A♥ + J♥ → suited + A&J: 1×2×2 = **4 sips**
> A♠ + J♠ → suited + A&J + black: 1×2×2×2 = **8 sips**


### 5.4 5+ Cards (Handouts)

These rules trigger when a Player or Dealer holds 5 or more cards in a single hand.

| # | Who | Condition | Effect |
|---|-----|-----------|--------|
| 1 | Player | **Exactly 21** | Distribute sips equal to card count to other Players (e.g. 6 cards = 6 sips distributed) |
| 2 | Player | **Wins** | All other Players drink 1 sip |
| 3 | Dealer | **Exactly 21** | All Players' sip wagers doubled this round |

**Clarifications:**
- Rule 1 does not require a win.
- Rule 1 and 2 stack (win with 21 and 5 cards).
- Rule 2 does not trigger on a push.
- Rule 3 does not include Blackjack bonus or Ace effects.


### 5.5 Player All-Hand Bonus

If every card across all of a Player's final hands shares **entirely the same suit**, or every hand totals **exactly 21**, other Players drink:

| Condition | Penalty to others |
| --------- | ----------------- |
| All cards same suit | 2× wager |
| All hands total 21 | 2× wager |
| Both simultaneously | 4× wager |

> Triggers regardless of win, push, or loss.


### 5.6 Four Aces at End of Round

If all 4 Aces are visible at end of round (but were **not** all visible on first deal), everyone drinks 1 sip.

> Cannot stack with [Four Aces on First Deal](#43-four-aces-on-first-deal) (first-deal rule takes precedence).


### 5.7 Hard Dealer Switch Penalty

Triggered when the Dealer loses all hands. Dealer drinks based on all Players' winning hands, then the role passes.

| Hand type | Sips the Dealer drinks |
|---|---|
| Regular winning hand | 1 sip |
| Blackjack | 2 sips (Players also drink per [Blackjack Bonus](#53-blackjack-bonus)) |
| Doubled winning hand | 2 sips |
| Split hands | Each counted separately (no extra sip for the split itself) |
| Suited hands | No extra sips for Dealer |

**Dealer's own player hands:**

On a Hard Switch, the Dealer's player-role drinking is **replaced entirely** by the penalty above. They do **not** drink for:
- Their own net losses
- Other Players' Blackjack bonuses
- Bonus sips from others' suited, doubled, or split wins

**Exceptions within the Hard Switch calculation:**

- Dealer's own Blackjack counts as 1 sip (no multiplier)

**Ace of Clubs protections:**

| ♣A dealt to | Effect |
| ----------- | ------ |
| Dealer's **dealer hand** | Switch still occurs, but Dealer drinks **halved sips**. Other players drink normally. |
| Dealer's **player hand** | Dealer's own player hands excluded from penalty calculation. −1 sip credit only applies if no hard switch fires. |


### 5.8 Milestone Handouts

Every time a Player's cumulative sip total crosses a multiple of 50, they earn bonus sips to hand out to other Players (5 sips at 50, 6 at 100, 7 at 150, +1 per additional milestone). The winner has 60 seconds to distribute the sips; unassigned sips return to them. Only one milestone can be active at a time.

### "Worst Average" Penalty

At each milestone, the Player with the **lowest average sips/round overall** (total sips ÷ rounds played so far, excluding the milestone winner) is flagged as "worst."

If the **same Player** is flagged "worst" for **two milestones in a row**, they take a **one-time penalty**: drink sips equal to the milestone winner's average sips/round (rounded, minimum 1). The streak then resets.



## 6. Relaxed Drinking Rules


### 6.1 Large Group Rules (4+ Players)

When 4 or more players are in the game, **end-of-round drinks are halved (rounded up)**. ([Drinking Rules (Instant Effect)](#4-drinking-rules-instant-effect)) fire immediately and are never halved, only [Drinking Rules (End of Round)](#5-drinking-rules-end-of-round) are impacted.

| Halved (End of Round) | Not halved (Instant Effect) |
| --------------------- | ---------------------- |
| Net hand losses (incl. doubled +1, suited +1) | Ace suit effects ♣♠♥♦ |
| Blackjack bonus (player BJ) | Dealer suited hand (2 sips to all) |
| Hard Dealer Switch | Four aces on first deal |
| All-hands sweep | 5-card handouts |
| Insurance resolution | Bust vote penalty/credit (+1/−1) |
| Four aces at end of round | |
| RoundEndEvent drinks (wins-all, immunity breakers) | |


### 6.2 Easy Mode

Any group can opt into the same halving rule regardless of player count.

| Setting | Behaviour |
| ------- | --------- |
| **Toggle** | Setup screen or admin settings mid-game |
| **Applies** | From the next round |
| **4+ players** | Always on (toggle locked) |



## 7. Potential Future Rules

_Have a rule idea? Open an issue or suggest it mid-game!
The best rules often come from the chaos of gameplay._ 🍻



## 8. Glossary

| Term | Definition |
| ---- | ---------- |
| **Wager** | The agreed sip amount per hand (e.g. 1 sip) |
| **Suited** | All cards in a hand share the same suit |
| **Immunity** | When a Player wins all their hands, they are immune to "other player wins all" sips — unless broken by doubles, splits, or suited exceptions ([Immunity Exception](#immunity-exceptions-doubles-splits-suited)) |
| **Net total** | Sum of all hand scores; only negatives result in drinking |
| **Hard Switch** | Dealer loses all hands → penalty + role passes |
| **Soft Switch** | Dealer wins all hands → normal drinking, role passes |
| **Auto-insurance** | Passive cap on penalty when Dealer has Blackjack (wager × hands) |

----

For full round walkthroughs showing how multiple rules interact, see [`ComprehensiveExample.md`](ComprehensiveExample.md).
