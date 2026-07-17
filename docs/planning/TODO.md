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
- [x] Full code sweep for "dead comments" or useless / outdated references (eg to docs/planning/TargetedDrinkingModes.md)
  - Both known cases fixed: Targeted Drinking Mode's own references were pointed at `Rules.md §5.10` before the plan doc's eventual deletion. Dealer Lottery's plan doc had already been deleted with 8 stale `DealerLottery-Plan.md` citations left behind across `app/config.py`, `app/services/dealer_lottery.py` (x2), `app/routes/polling.py`, `app/models/state_schema.py`, `static/js/ui/admin.js`, `tests/app/test_dealer_lottery.py` (x3), and `docs/Architecture.md`'s directory-tree listing — all repointed to `Rules.md §5.9`.

## Features

- [ ] simplified ruleset
  - [ ] reduced ruleset for beginners / introduction into the game (remove complex rules for simplicity)
- [ ] csv addition
  - potentially .pdf file output with graphs
  - show in Dealer who drank most for each ace
  - show luckiest hits
  - for Milestone show Deltas to next best players
- [ ] Busfahrer - see docs/planning/Busfahrer-Plan.md
- [ ] Targeted Drinking: target individual players to drink
- [ ] Global state sprawl (state.js) — Full consolidation into single AppState object touches nearly every UI file — high risk of subtle bugs from missed references
  - remaining state.js globals (players, lastState, roomCode, clientId, myRole, myName, myNames, etc.) each have ~30-76 usages across 7-12 files (several hundred call sites total). The leftover setup.js singletons (_rowIdCtr, _lastActivityAt, _idleWatcherID) are unrelated to each other and not worth grouping. Per the original assessment, the core session/identity consolidation stays deferred — only worth doing as part of a larger rewrite, not as an incremental step.


## Backend / Infra (deferred)

- [ ] Cap/rotate session-lifetime accumulator lists — declined for now (from July 2026 code audit)
  - `session.drinks.csv_rows` / `_decision_log` / `_dealer_lottery_decision_log` grow for the whole session; these are exactly the rows `/export_xlsx` and `/export_decisions` read, so capping them would silently truncate exported data
  - only revisit if a real session is observed running long enough to threaten the 512MB Render ceiling
- [ ] `state_seq`-gated cache for `serialize_state()` — optional, low urgency (from July 2026 code audit)
  - every `/state` poll fully rebuilds and re-validates the whole snapshot, even when nothing changed since the client's last poll
  - only worth doing if table sizes or poll frequency grow
- [ ] SSE (Server-Sent Events) instead of polling — blocked on Render free tier (from architectural improvements review)
  - Render's free tier kills idle HTTP connections after ~30s, which breaks SSE streams
  - viable on a paid Render plan or any VPS (Hetzner, DigitalOcean, Fly.io, Railway) — revisit if hosting ever changes
