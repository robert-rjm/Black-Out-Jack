# Drinking Blackjack Rules

This document outlines the full set of rules for _**Drinking BlackJack**_: a fun, fast, and occasionally chaotic variation of classical BlackJack enhanced with custom drinking mechanics.

Unless explicitly stated here, standard BlackJack rules apply. These custom rules are designed to add energy, unpredictability, and fun to the game, especially when played socially.

**Note:** This rule set is always evolving. Players are encouraged to propose new rules during gameplay if they make the experience better.

---
## Game Setup
Drinking BlackJack is played with a standard deck of cards (or multiple decks), which is shuffled after each round. Unlike traditional BlackJack where chips are used, _**drinks act as the betting currency**_.

Every player is required to have a drink ready.

### Gameplay Rules:
- Each player is recommended to play with two hands per round
- Before starting, players must agree on a drinking wager (e.g. 1 sip per hand)
- Each hand is played individually, but rewards and penalties are based on combined outcome across all hands
- Any hand won against the Dealer counts as +1 while every hand lost counts as -1, a push counts as 0 (e.g. 1 hand won and 1 hand lost means no drink must be consumed (+1 -1 = 0))
- Any net positive score across hands played is disregarded, only negative scores result in penalties

For fairness, all players must play with the same number of hands and wager.

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

_**Play with Honor:**_ As Self, you are not allowed to intentionally sabotage your own hand to reduce the risk of triggering a Hard dealer switch.

---
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

---
## Drinking Rules
### Drinking based on own cards:
- Drink once for each net hand lost against the Dealer

### Drinking based on other Player(s) cards:
- Other won all their hands + you lost at least 1 hand, then drink for each hand of Other
- Other won all their hands + you did not win all hands (tied but no lost hand), then drink for each hand of Other minus your hands that you won
- Drink once for each successfully won double or split (both hands) of Other unless you must drink for all (see above)
- If Other has a Blackjack (21 in two cards), drink once
  - Also counts as Blackjack if splitting Aces
  - Drink double if Blackjack is suited (cumulative)
  - Drink double if Blackjack consists of a Jack and an Ace (cumulative)
  - Drink double if Blackjack with both black cards (cumulative)
  - _(e.g. black Jack of Spades with black Ace of Spades result in 1*2*2*2 = 8 penalties)_
- Drink once if Other won any hand that is suited
  - Drink 4 penalties if Player wins a hand suited that they doubled or split
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

---
## Potential future rules
- Everyone drinks, even if they beat the Dealer, if Dealer does not bust with 6+ cards
- Give out 3 penalties if winning your hand with 5 cards


## Comprehensive Example
- Based on three Players (A, B, C), including the Dealer.
- Player A is Dealer, unless stated otherwise.
- Each Player plays two hands, with a wager of 1 sip respectively

### Basic Drinking

| Player   | First Hand                               | Second Hand                              |
|----------|------------------------------------------|------------------------------------------|
| Player A | 8♣, 7♠                     | 15, lost    | Q♦, 6♣                      | 16, lost   | 
| Player B | 5♥, 5♠, J♣ _(double down)_ | 20, won     | 9♦, 2♠, 10♠ _(double down)_ | 21, won    |
| Player C | A♥, J♠ _(Blackjack)_       | 21, won     | 7♣, 3♦, 8♠                  | 18, push   |
| Dealer   | 10♥, 8♦                    | 18          | —                           |            |

#### Penalties

- Player B:
  - Drinks _2 penalties_ for Player C's ace and jack Blackjack

- Player C:
  - Drinks _1 penalty_ for each of Player B's won doubles
  - Drinks _1 penalty_ for both hands of Player B's minus their own won hand
  - Hence total penalties of 3

- Player A (not as Dealer):
  - Drinks _4 penalties_ for Player B's hand
  - Drinks _2 penalties_ for Player C's ace and jack Blackjack
  - Drinks _2 penalties_ for own lost hands

- Player A (as Dealer):
  - Dealer does not drink

### Dealer Switch Example

| Player   | First Hand                               | Second Hand                              |
|----------|------------------------------------------|------------------------------------------|
| Player A | 9♠, 7♦                     | 17, won     | A♠, 6♥, 3♠ _(double down)_  | 20, won    |
| Player B | 10♣, 4♦, 5♠                | 19, won     | K♦, 8♣                      | 18, won    |
| Player C | A♣, 9♦                     | 20, won     | 7♥, 2♥, 6♥ _(double down)_  | 15, won    |
| Dealer   | Q♥, 5♣, 8♠ _(bust)_        | 23          | —                           |            |

#### Penalties

- Player B:
  - Drinks _1 penalty_ for being next Player after A♠
  - Drinks _1 penalty_ for Player A's won double
  - Drinks _1 penalty_ for Player C's won double
  - Drinks _1 penalty_ for Player C's suited Hearts hand

- Player C:
  - Drinks _1 penalty_ for Player A's won double

- Player A (not as Dealer):
  - Drinks _1 penalty_ for Player C's suited Hearts hand
  - _Does not drink for Player C's won double (already drinks as Dealer for that hand)_

- Player A (as Dealer):
  - Drinks _3 penalties_ for Player A's own hands
  - Drinks _2 penalties_ for Player B's hands
  - Drinks _3 penalties_ for Player C's hands

Player B becomes Dealer.

### Blackjack scenario

| Player   | First Hand                               | Second Hand                              |
|----------|------------------------------------------|------------------------------------------|
| Player A | Q♠, A♦ _(Blackjack)_       | 21, won     | 8♠, 6♥, 3♠                  | 17, push   |
| Player B | A♥, K♥ _(Blackjack)_       | 21, won     | 9♦, 8♣                      | 17, push   |
| Player C | A♣, J♣ _(Blackjack)_       | 21, won     | 7♥, 2♥, 8♠ _(double down)_  | 17, push   |
| Dealer   | K♥, 7♣                     | 17          | —                           |            |

#### Penalties

- Player B:
  - Drinks _1 penalty_ for Player A's normal Blackjack
  - Drinks _8 penalties_ for Player C's suited black ace jack Blackjack

- Player C:
  - Drinks _1 penalty_ for Player A's normal Blackjack
  - Drinks _2 penalties_ for Player B's suited Blackjack
  - _does not drink for the pushed double down since not lost_

- Player A (not as Dealer):
  - Drinks _2 penalties_ for Player B's suited Blackjack
  - Drinks _8 penalties_ for Player C's suited black ace jack Blackjack

- Player A (as Dealer):
  - Dealer does not drink
