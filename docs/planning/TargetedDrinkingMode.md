# Subgame Targeted Drinking Mode — Implementation Plan

## general idea
- subgame that takes 1+ players into betting on whether dealer busts
- can be started by host at any time (maybe also via majority vote)
- participating/ selected players cannot obt out
- players must bet on whether Dealer hand will bust (separate from normal round, side game similar to Dealer Lottery)
- aim is to give players opportunity to catch up OR finish their drink depending on time
- player have choice to either bet bust or stand, if vote incorrect, drink 1 sip
- interface should look similar to the Dealer Lottery modal
- these accumulated sips get counted towards the sip counter and aggregate sips, also in csv as drinking rule
- if player is correct 3 times in a row (similar to game mechanics of busfahrer) this sub game ends and goes back to normal blackjack as before
- have a button that ends the subgame now, majority vote based
- have something if player goes afk (timer for bust/stand vote + if not answering twice in a row, player gets "kicked" and becomes local player of host)
- consider having a 3 round cooldown between subgames, 5 rounds if only one player is targeted both times (can be overwritten if targeted player agrees)
- losing streak, if 3 times wrong, drink extra sip(s), if 5 times wrong streak extra drink punishment

## open questions
- where to have begin sub game button within interface?
- side bets for spectators, to "join just for fun"?
- rescue mechanic, player can volunteer to sub in/ split drinks?
- how to implement?

## architecture brainstorming

SubgameState {
  isActive: boolean
  targetedPlayers: Player[]
  currentRound: number
  streaks: Map  // consecutive correct guesses
  votes: Map
  afkStrikes: Map
  voteTimer: number  // countdown in seconds
  endVotes: Set  // players voting to end early
}

Host triggers subgame (or majority vote)
  → Select target player(s)
  → Modal appears for targeted players (all others are spectators)
  → Dealer hand plays out normally
  → Each round:
      1. Timer starts (e.g., 15s)
      2. Players vote BUST or STAND (all players vote and play independently)
      3. Dealer resolves hand
      4. Compare: wrong = +1 sip, right = streak++
      5. If streak === 3 → player "graduates" out
      6. If AFK twice → kicked to host-local
  → Subgame ends when all players graduate OR end button majority
