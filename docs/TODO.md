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
- [ ] `game_room.py` bloat risk: split into `GameRoom` vs `RoundState` vs `MilestoneTracker` (not issue yet, for future with next feature)
