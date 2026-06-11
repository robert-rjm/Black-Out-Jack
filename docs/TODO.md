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


## Bug fixes (this session)

- [X] `engine/blackjack.py` had 9 broken imports (`from drinking_rules import X` missing the
  `engine.` prefix) inside `RoundManager`/`BlackJackGame` methods. This crashed
  `RoundManager(drinking_mode=True)` (and the legacy CLI's drinking mode) on the very first
  card deal with `ModuleNotFoundError: No module named 'drinking_rules'`. Did NOT affect the
  live web app (uses `app/services/game_engine.py`, already correct). Fixed all 9 to
  `from engine.drinking_rules import ...`.
- [X] `scripts/simulation.py` imported a non-existent `drinking_rules` module and carried its
  own stale, drifted copy of `classify_rule()` (missing A♣ protect/credit cases, older Ace
  naming). Now imports `classify_rule`/`DrinkTracker` from `engine.drinking_rules`, the same
  source of truth `app/services/drink_tracker.py` uses for the live CSV export.
  - NOTE: Could not execute end-to-end this session due to a sandbox file-sync issue (the
    Linux sandbox's copy of `engine/blackjack.py` is a stale/truncated snapshot unrelated to
    these edits). Source-level fixes are verified correct via direct file read; please run
    `python scripts/simulation.py` locally to confirm a clean 10,000-round run and check
    `simulation_results.txt` / `simulation_log.csv` for any rule classified as "Other".

## Benchmark implementation (in progress)

- [X] `scripts/simulation.py` now also tallies hand outcomes (blackjacks, busts,
  wins/losses/pushes, dealer busts) during the run and writes `scripts/benchmarks.json`
  plus a generated `static/js/benchmarks.js` (`const BENCHMARKS = {...}`) with:
  blackjack/bust/win/loss/push/dealer-bust rates, avg sips/round, and sips/round per
  drinking rule.
- [X] `static/js/ui/kpi.js`: replaced `colorStyleByThreshold` (hand-picked 40%/25%
  dealer-bust thresholds) and the hardcoded "expected ~4.8%" / "casino avg ~28%" comments
  with a generic `benchmarkColor(value, benchmark, {lowerIsBetter})` that compares live
  session stats to `BENCHMARKS` (within 25% = neutral, 25-50% = yellow, >50% = green/red
  depending on direction). Applied to: blackjack rate callout, dealer-bust callout, and
  per-player avg sips/round (vs. `avg_sips_per_round / playerCount`).
- [X] Wired `static/js/benchmarks.js` into `templates/partials/index/_scripts.html`
  (loaded right after `utils.js`, before `state.js`, so `BENCHMARKS` is defined before
  any UI module needs it).
- [ ] **`static/js/benchmarks.js` is currently a PLACEHOLDER** — only `blackjack_rate_pct`
  (4.8) and `dealer_bust_pct` (28.0) are filled in (the old hardcoded values); everything
  else is `null`/`{}`. Could not run `python scripts/simulation.py` this session due to a
  sandbox file-sync issue (see "Bug fixes" section above). **Action needed**: run
  `python scripts/simulation.py` from the project root locally — it will overwrite
  `static/js/benchmarks.js` and `scripts/benchmarks.json` with real numbers for the
  current 3-player/2-deck config. `benchmarkColor()` degrades gracefully (no color) for
  any benchmark that's still `null`.
- [ ] Per-player avg-sips benchmark (`avg_sips_per_round / playerCount`) assumes an even
  split across seats, which drinking rules don't guarantee — fine for a wide-band
  "lucky/unlucky" signal, but worth revisiting if it feels noisy in practice.
- [ ] Benchmarks are generated for the hardcoded 3-player/2-deck sim config; revisit once
  the 4th-player handling (see Bugs) is sorted, since baselines shift with table size.

## Benchmark idea (from simulation.py)

- [ ] Use `simulation_results.txt` / `simulation_log.csv` as a regression baseline for the
  drinking-rules engine:
  - Run once on a known-good engine state, commit the output as a snapshot.
  - After any change to `engine/drinking_rules.py` or `engine/blackjack.py`, re-run and diff
    sips/session per rule against the snapshot — flags unintended balance shifts (e.g. a rule
    firing too often/rarely) that unit tests on individual rules might miss.
  - Same run also gives a rough perf baseline (10k-round wall time) for catching engine
    slowdowns.
  - Any reason classified as "Other" by `classify_rule` is a signal the classifier (and
    possibly the live CSV export) is missing a newer rule string — worth checking each run.
  - This pairs naturally with the planned `tests/` suite (see Features) as an integration-level
    check, complementing unit tests on individual `DrinkingRules` methods.

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
