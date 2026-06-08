# TODO Checklist

## Bugs

- [ ] Brainstorm fix for Mobile UI
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
- [X] issue with 4th player joining mid round
  - ensure no issue with "late joiners"
  - game logic should not break
  - check if fixes work as intended
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
- [ ] `game_room.py` bloat risk: split into `GameRoom` vs `RoundState` vs `MilestoneTracker` (not issue yet, for future with next feature)
