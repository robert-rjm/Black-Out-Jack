# TODO Checklist

## Bugs

- [ ] Brainstorm fix for Mobile UI
  - respect safe area (iphone notch)
  - big wasted space with play panel
  - big wasted space in action bar
  - remove other dead space
  - trivia / stats section
    - too big, not readable
    - not optimized for mobile
    - trivia show maybe max 1 fact
    - trivia not visible (currently with leaderboard)
    - consider trivia as web only feature
    - reduce stats for mobile optimized UX
- [ ] Brainstorm fix for Web UI
  - difficult to see on standard computer (without monitor)
  - potentially collapsible stats/trivia section
  - eliminate dead space
- [ ] issues with 4th player
  - ensure no issue with "late joiners"
  - ensure drink sips are halved automatically (round up)
  - check if fixes work as intended
  - check if maximum number of players in game logic
  - check for # decks needed per extra players. {Player:deck = (2,1), (3,1), (4,2),(5,?), etc}
- [ ] test "easy mode" working as intended
- [ ] Trivia Panel
  - fact check
  - add / edits facts
  - add Black(Out)Jack specific fun facts


## Features

- [ ] Normal mode complete overwork (remove "sip" reference and all other drinking references)
- [ ] simplified rule set for beginners
- [ ] csv addition
  - potentially .pdf file output with graphs
  - show in Dealer who drank most for each ace
- [ ] implement test suite (`tests/` directory)
  - have way to compare simulation results with own game performance
  - use simulation to change bot behavior (possibility to have a "Marko bot" or "David bot" that replicates the respetive way of playing)
- [ ] `game_room.py` bloat risk: split into `GameRoom` vs `RoundState` vs `MilestoneTracker` (not issue yet, for future with next feature)
- [ ] Audit Suggestion Frontend
  - [ ] Global state sprawl (state.js) — Largest frontend item. Full consolidation into a single AppState object touches nearly every UI file — high risk of subtle bugs from missed references. I'd treat this as "not now" unless you're doing a larger rewrite; the TDZ bug we just fixed is a symptom but a narrow one. If you want incremental progress, start by grouping related globals into small namespaced objects (e.g. _voteState = { lastSips, prevSips, lastMilestoneKey, ... }) one feature area at a time, rather than one big-bang refactor.
    - [X] Step 1: Drink/milestone tracker group — consolidated the 10 globals originally declared together in setup.js (lastRoundSips, lastRoundDrinks, prevRoundSips, prevRoundDrinks, drinksPaneSelected, lastRoundOverSeq, lastMilestoneKey, lastMilestoneResultKey, milestoneModalOpened, milestoneAllocations) into a single `const DrinkUI = {...}` object in setup.js, and updated all read/write sites in table.js and table-modals.js. Other global groups (trivia state, toast-timer handles, setup-screen state, core session/identity) remain as separate future steps.
    - [X] Step 2: Trivia panel state group — consolidated the 5 globals in trivia.js (_triviaFilter, _triviaIndex, _triviaList, _triviaRendered, _triviaLastRound) into a single `const TriviaUI = {...}` object, all usages local to trivia.js. Remaining groups (toast-timer handles, setup-screen state, core session/identity) still pending.
    - [X] Step 3: Toast state group — consolidated the 4 globals in log.js (_toastQueue, _dealerToastTimer, _playerToastTimer, _switchToastTimer) into a single `const ToastUI = {...}` object; updated the one cross-file usage in table-modals.js. Also dropped a now-unnecessary `typeof ... !== "undefined"` guard around the player toast timer (the old `let` could theoretically be read in TDZ; `const ToastUI` cannot). Remaining groups (setup-screen state, core session/identity in state.js) still pending.
    - [X] Stopping here — the remaining state.js globals (players, lastState, roomCode, clientId, myRole, myName, myNames, etc.) each have ~30-76 usages across 7-12 files (several hundred call sites total), a different scale of change from the three completed groups (each confined to 1-3 files). The leftover setup.js singletons (_rowIdCtr, _lastActivityAt, _idleWatcherID) are unrelated to each other and not worth grouping. Per the original assessment, the core session/identity consolidation stays deferred — only worth doing as part of a larger rewrite, not as an incremental step.
