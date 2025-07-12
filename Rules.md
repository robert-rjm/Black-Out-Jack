# Drinking Blackjack Rules

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
- Each player is recommended to play with two hands per round
- Before starting, players must agree on a drinking wager (e.g. 1 sip per hand)
- Each hand is played individually, but rewards and penalties are based on combined outcome across all hands
- Any hand won against the Dealer counts as +1 while every hand lost counts as -1, a push counts as 0 (e.g. 1 hand won and 1 hand lost means no drink must be consumed (+1 -1 = 0))
- Any net positive score across hands played is disregarded, only negative scores result in penalties

*For fairness, all players must play with the same number of hands and wager.*

### Dealer:
- There is no fixed Dealer. Every _n_ rounds, the role of Dealer is shifted to the next Player
  - _Recommendation_: switch Dealer every _n_ rounds, where _n_ is the number of Players
- Being Dealer places you at a higher risk of penalties
- Hard Dealer switch:
  - Occurs when Dealer loses all hands (a tie is not a lost hand)
  - Dealer must drink penalties for each Player's hands as outlined below
  - Role of Dealer turns to next Player
- Soft Dealer switch:
  - Occurs when Dealer wins all hands (a tie is not a won hand)
  - Exemption when Player takes insurance on Blackjack
  - Each Player must drink their respective penalties
  - Dealer does not drink any penalty
  - Role of Dealer turns to next Player

_**Play with Honor:**_ You are not allowed to intentionally sabotage your own hand to reduce the risk of triggering a Hard dealer switch.


## General Rule Modifications
_Unless stated otherwise within these rules, traditional rules of BlackJack apply._

The following are notable adaptations to these traditional rules:
- Dealer must stand on all 17s, including soft 17
- Blackjack payouts are 2:1
  - The associated penalties are outlined below
  - If the Dealer shows an Ace, Player may insure their Blackjack
    - Insurance in this context treats Blackjack as a regular 21 and other Players do not have to drink for the Blackjack
- Splitting Aces
  - Player may split as many aces as they like, wager is counted per hand (increased with each split)
  - Blackjack treated as Blackjack on split aces
  - Player may hit/ double/ split on an ace split
- It is strongly recommended to split 10s
- Double down is allowed on any two-card hand (also after split)
- Special insurance rule when Dealer shows an ace
  - Dealer does not peek at bottom card if upcard is ace
  - Player's double downs and split are not counted if Dealer has a Blackjack
  - Max penalty is number of hands times wager per hand (e.g. two sips if playing recommended two hands and 1 sip wager)

## Drinking Rules
### Drinking based on own cards:
- Drink once for each net hand lost against the Dealer
  - _(e.g. if winning 1 hand and losing the other, penalties offset)_

### Drinking based on other Player(s) cards:
- If another Player wins all their hands:
  - If you lost at least one hand, drink once for each hand the other Player won
  - If you won all your hands, you do not drink for the other Player's wins (see exceptions below)
  - If you did not lose any hand but have at least one push (tie), drink once for each hand the other Player won, minus the number of your own hands that you won
- Drink once for each successfully won double or split (both hands) of another Player unless you must drink for all (see above)
- If another Player has a Blackjack (21 in two cards), you must drink 1 penalty.
  - This includes Blackjacks from split Aces.
  - The penalty is doubled for each of the following, and these are cumulative:
    - If the Blackjack is suited (both cards same suit), double the penalty
    - If the Blackjack is specifically an Ace and a Jack, double the penalty
    - If both cards are black (Spades or Clubs), double the penalty
    - _(e.g. a suited black Jack and Ace (Jack of Spades and Ace of Spades) results in 1 × 2 × 2 × 2 = 8 penalties)_
- Drink once if another Player wins a hand that is suited (both cards of the same suit)
  - The penalty is 4 instead of 1 if the hand was doubled or split
- Ace of Spades is dealt to Dealer:
  - Everyone drinks once if it's Dealers first card
  - Dealer drinks once if it's Dealers second card
  - No one drinks if it's Dealers 3+ card
- Ace of Spades is dealt to Player:
  - If first card dealt to Player, the next Player must take 1 penalty
  - If second card dealt to Player, the second next Player must take 1 penalty
  - If third card dealt to Player, the third next Player must take 1 penalty
  - etc.
  - (it is possible that a Player dealt the Ace of Spades must drink themselves, depending on number of Players)

### Drinking on behalf of the Dealer:
- Drink once if Ace of Spades dealt to Dealer as second card
- Drink for all hands if Dealer lost all hands (a tie is not a lost hand):
  - Each Players hand counts as 1 penalty
  - A Blackjack hand from another player counts as 2 penalties (Self and Dealer not punished twice)
  - If Self has Blackjack, Dealer (Self) only counts as 1 penalty
  - A double counts as 2 penalties (Self not punished twice)
  - If Self has doubled a hand, Dealer (Self) must drink twice
  - If a hand was split, treat as two separate hands (Self excluded from drinking extra for split)

## Potential future rules
- Everyone drinks, even if they beat the Dealer, if Dealer does not bust with 6+ cards
- Give out 3 penalties if winning your hand with 5 cards

---
## Example Scenarios

For practical examples illustrating how these rules are applied during gameplay, refer to the companion file [`Rules-Examples.md`](Rules-Examples.md). This file contains sample hands and outcomes to help clarify penalties, dealer switches, special cases, and more.