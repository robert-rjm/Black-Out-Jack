# Comprehensive Example
- Based on three Players (A, B, C), including the Dealer.
- Player A is Dealer, unless stated otherwise.
- Each Player plays two hands, with a wager of 1 sip respectively

## Basic Drinking

| Player   | First Hand                       | Result   | Second Hand                       | Result   |
|----------|----------------------------------|----------|-----------------------------------|----------|
| Player A | `8♣`, `7♠`                       | 15, lost | `Q♦`, `6♣`                        | 16, lost | 
| Player B | `5♥`, `5♠`, `J♣` _(double down)_ | 20, won  | `9♦`, `2♠`, `10♠` _(double down)_ | 21, won  |
| Player C | `A♥`, `J♠` _(Blackjack)_         | 21, won  | `7♣`, `3♦`, `8♠`                  | 18, push |
| Dealer   | `10♥`, `8♦`                      | 18       | —                                 |          |

### Penalties

| Player B                                                                                          | Penalties |
|---------------------------------------------------------------------------------------------------|-----------|
| Drinks _2 penalties_ for Player C's Blackjack with an Ace and Jack (Blackjack = 1, Ace+Jack = x2) | 2         |
| **Total Penalties**                                                                               | **2**     |

| Player C                                                                                                                  | Penalties |
|---------------------------------------------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for each of Player B's won doubles                                                                     | 2         |
| Drinks _1 penalty_ for Player B winning both hands while Player C only won one (Player B's 2 wins minus Player C's 1 win) | 1         |
| **Total Penalties**                                                                                                       | **3**     |

| Player A (not as Dealer)                                                                       | Penalties |
|------------------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for each of own lost hands                                                  | 2         |
| Drinks _2 penalties_ for Player C's Blackjack with Ace and Jack (Blackjack = 1, Ace+Jack = x2) | 2         |
| Drinks _1 penalty_ for each of Player B's won doubles                                          | 2         |
| Drinks _1 penalty_ for each of Player B's winning hands while Player A lost both               | 2         |
| **Total Penalties**                                                                            | **8**     |

| Player A (as Dealer)                   | Penalties |
|----------------------------------------|-----------|
| Dealer does not drink in this scenario | 0         |
| **Total Penalties**                    | **0**     |

## Dealer Switch Example

| Player   | First Hand                | Result   | Second Hand                      | Result   |
|----------|---------------------------|----------|----------------------------------|----------|
| Player A | `9♠`, `7♦`                | 17, won  | `A♠`, `6♥`, `3♠` _(double down)_ | 20, won  |
| Player B | `10♣`, `4♦`, `5♠`         | 19, won  | `K♦`, `8♣`                       | 18, won  |
| Player C | `A♣`, `9♦`                | 20, won  | `7♥`, `2♥`, `6♥` _(double down)_ | 15, won  |
| Dealer   | `Q♥`, `5♣`, `8♠` _(bust)_ | 23       | —                                |          |

### Penalties

| Player B                                                                                              | Penalties |
|-------------------------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for being the next Player after A♠ (Ace of Spades dealt to Player A as first card) | 1         |
| Drinks _1 penalty_ for Player A's won double                                                          | 1         |
| Drinks _1 penalty_ for Player C's won double                                                          | 1         |
| Drinks _1 penalty_ for Player C's suited Hearts hand                                                  | 1         |
| **Total Penalties**                                                                                   | **4**     |

| Player C                                     | Penalties |
|----------------------------------------------|-----------|
| Drinks _1 penalty_ for Player A's won double | 1         |
| **Total Penalties**                          | **1**     |

| Player A (not as Dealer)                                                            | Penalties |
|-------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for Player C's suited Hearts hand                                | 1         |
| _Does not drink for Player C's won double (already drinks as Dealer for that hand)_ | 0         |
| **Total Penalties**                                                                 | **1**     |

| Player A (as Dealer)                                                                   | Penalties |
|----------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for each lost hand against Player B (since Dealer lost all hands)   | 2         |
| Drinks _1 penalty_ for each lost hand against Player C (since Dealer lost all hands)   | 2         |
| Drinks _1 penalty_ for each lost hand against themselves (since Dealer lost all hands) | 2         |
| Drinks _1 penalty_ for Player C's won double                                           | 1         |
| Player B becomes Dealer.                                                               | 0         |
| **Total Penalties**                                                                    | **7**     |

## Blackjack scenario

| Player   | First Hand               | Result   | Second Hand                      | Result   |
|----------|--------------------------|----------|----------------------------------|----------|
| Player A | `Q♠`, `A♦` _(Blackjack)_ | 21, won  | `8♠`, `6♥`, `3♠`                 | 17, push |
| Player B | `A♥`, `K♥` _(Blackjack)_ | 21, won  | `9♦`, `8♣`                       | 17, push |
| Player C | `A♣`, `J♣` _(Blackjack)_ | 21, won  | `7♥`, `2♥`, `8♠` _(double down)_ | 17, push |
| Dealer   | `K♥`, `7♣`               | 17       | —                                |          |

### Penalties
| Player B                                                                                                                                | Penalties |
|-----------------------------------------------------------------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for Player A's normal Blackjack                                                                                      | 1         |
| Drinks _8 penalties_ for Player C's suited black Blackjack with an Ace and Jack (Blackjack = 1, suited = x2, Ace+Jack = x2, black = x2) | 8         |
| **Total Penalties**                                                                                                                     | **9**     |

| Player C                                                                          | Penalties |
|-----------------------------------------------------------------------------------|-----------|
| Drinks _1 penalty_ for Player A's normal Blackjack                                | 1         |
| Drinks _2 penalties_ for Player B's suited Blackjack (Blackjack = 1, suited = x2) | 2         |
| _does not drink for the pushed double down since not lost_                        | 0         |
| **Total Penalties**                                                               | **3**     |

| Player A (not as Dealer)                                                                                                                | Penalties |
|-----------------------------------------------------------------------------------------------------------------------------------------|-----------|
| Drinks _2 penalties_ for Player B's suited Blackjack (Blackjack = 1, suited = x2)                                                       | 2         |
| Drinks _8 penalties_ for Player C's suited black Blackjack with an Ace and Jack (Blackjack = 1, suited = x2, Ace+Jack = x2, black = x2) | 8         |
| **Total Penalties**                                                                                                                     | **10**    |

| Player A (as Dealer)                   | Penalties |
|----------------------------------------|-----------|
| Dealer does not drink in this scenario | 0         |
| **Total Penalties**                    | **0**     |

| Player A (as Dealer)                   | Penalties |
|----------------------------------------|-----------|
| Dealer does not drink in this scenario | 0         |
| **Total Penalties**                    | **0**     |