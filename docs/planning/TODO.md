# TODO Checklist

## Bugs

- [ ] Brainstorm fix for UI
  - [ ] Mobile / Standalone PWA
    - Big wasted space in action "play" panel
    - remove other dead space / optimize UI
    - remove horizontal scroll
  - [ ] Web UI
    - difficult to see on standard screen size (zoom issue)
    - potentially collapsible stats / trivia section
    - eliminate dead space / optimize UI
- [ ] Trivia Panel
  - could move into "contextual trivia" instead of tab, show trivia inline between rounds and hide when round is active
  - check if needed / desired
  - fact check
  - add / edits facts
  - add Black(Out)Jack specific fun facts


## Features

- [x] trained "custom" BOTs, selectable and reflect actual player behavior deviation from basic strategy (see `docs/planning/PlayerStyleBots.md`)
- [ ] simplified ruleset
  - [ ] reduced ruleset for beginners / introduction into the game (remove complex rules for simplicity)
  - [ ] improved comprehensive example for more clarity (link rules explicitly to which rule in `docs/Rules.md`)
- [ ] csv addition
  - potentially .pdf file output with graphs
  - show in Dealer who drank most for each ace
  - show luckiest hits
  - for Milestone show Deltas to next best players
- [ ] Dealer Lottery — post-round bonus event when the dealer's final hand
  is a paired 18/20; superseded these two earlier drafts once the mechanic
  was fully brainstormed and reconciled. See `docs/planning/DealerLottery-Plan.md`
  for the finalized rules, open questions, and build order.
- [ ] Global state sprawl (state.js) — Full consolidation into single AppState object touches nearly every UI file — high risk of subtle bugs from missed references
  - remaining state.js globals (players, lastState, roomCode, clientId, myRole, myName, myNames, etc.) each have ~30-76 usages across 7-12 files (several hundred call sites total). The leftover setup.js singletons (_rowIdCtr, _lastActivityAt, _idleWatcherID) are unrelated to each other and not worth grouping. Per the original assessment, the core session/identity consolidation stays deferred — only worth doing as part of a larger rewrite, not as an incremental step.
