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

- [ ] trained "custom" BOTs, selectable and reflect actual player behavior deviation from basic strategy
- [ ] simplified rule set for beginners
- [ ] csv addition
  - potentially .pdf file output with graphs
  - show in Dealer who drank most for each ace
  - show luckiest hits
  - for Milestone show Deltas to next best players
- [ ] side bet on Dealer pair (18-20):
  - player "buy in", 1 penalty sip each
  - if dealer bust both: players drink nothing
  - if dealer bust one: players drink normal amount
  - if dealer bust none (17-21): drink double
  - if dealer has BJ, drink 2 regardless
  - details to brainstorm
- [ ] side bet on Dealer pair (18-20):
  - cost X = 0-5 sips (each player free choice)
  - if dealer bust both: players hand X and hands out X
  - if dealer bust one: players drink X
  - if dealer bust none (both 17-21): drink double X
  - automatic split if same numbers again
- [ ] `game_room.py` bloat risk: split into `GameRoom` vs `RoundState` vs `MilestoneTracker` (not issue yet, for future with next feature)
- [ ] Global state sprawl (state.js) — Full consolidation into single AppState object touches nearly every UI file — high risk of subtle bugs from missed references
  - remaining state.js globals (players, lastState, roomCode, clientId, myRole, myName, myNames, etc.) each have ~30-76 usages across 7-12 files (several hundred call sites total). The leftover setup.js singletons (_rowIdCtr, _lastActivityAt, _idleWatcherID) are unrelated to each other and not worth grouping. Per the original assessment, the core session/identity consolidation stays deferred — only worth doing as part of a larger rewrite, not as an incremental step.

## Audit Findings open tasks

- [ ] Audit17June.md file bugs and fixes
