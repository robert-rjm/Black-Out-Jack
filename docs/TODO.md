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


## Audit suggestions

Backend
- [X] Magic numbers for timing windows (17s bust vote, 60s insurance, 20s handout, 5s pause, MAX_REG_DENIALS=2) — Currently scattered across game_commands.py, polling.py, drink_tracker.py. Move them all into app/config.py next to MILESTONE_STEP/MILESTONE_TTL. Low risk, mostly find-and-replace, but touches several files — good candidate for its own small commit. Side benefit: makes these tunable from one place if you ever want to adjust pacing for a livelier game.
- [ ] command() ~500-line monolith — Biggest structural item. Options: (a) a dict-based command registry mapping cmd -> handler_fn(session, parts, ...), each handler in its own function; (b) split into per-mode dispatcher functions (_handle_digital_command, _handle_referee_command) as an intermediate step before further splitting. Given how much shared post-action logic exists (split-card dealing, NPC auto-play, dealer-ready checks), I'd extract that "after any player action" block into its own helper first — that's lower risk and shrinks the function meaningfully on its own. Full registry refactor is higher effort/risk and worth doing only if you're adding more commands soon.
- [ ] serialize_state() ~80-key single dict — Mostly cosmetic/readability. Break into named locals: _kpi_data = {...}, _milestone_data = {...}, _bust_vote_data = {...}, then merge with {**a, **b, ...}. Easy, low-risk, makes each section independently testable. Good "while you're in there" cleanup whenever you touch serializer.py for something else — not worth a standalone commit.
- [X] sanitize_name bidi/unicode hardening — Add a strip for Unicode bidi-control chars (\u202A-\u202E, \u2066-\u2069) and other non-printable categories. Small, isolated, easy to unit test (assert sanitize_name("Bob\u202E") == "Bob"`). Worth doing as a quick security-hardening commit since it's self-contained.
- [X] verify_rules() network call on startup — Confirmed CLI-only (BlackJackGame.setup()), not reachable from the web app. I'd just leave a comment noting it's CLI-only and out of scope, unless you plan to deprecate the CLI entirely — then it could be deleted along with other CLI-only code in a future "drop legacy CLI" pass.
- [ ] Insurance votes_needed == 0 edge case (item 8) — Worth a quick manual test: start a round where the only other players are NPCs and one human gets blackjack. Confirm the insurance banner doesn't flash "0/0 → DECLINE" jarringly for a frame. If it's instant/imperceptible, no fix needed — just document the intentional fast-path in a comment.
- [X] round_phase() fragile inference (item 10) — Was inferring "dealer done" from dealer_hand.stood/bust/score>=17/blackjack before checking all_resolved; fragile (true from the initial deal alone, breaks if dealer_hand is None). Now checks `h.result is not None` across all hands directly — the definitive resolution signal.

Frontend
- [ ] Global state sprawl (state.js) — Largest frontend item. Full consolidation into a single AppState object touches nearly every UI file — high risk of subtle bugs from missed references. I'd treat this as "not now" unless you're doing a larger rewrite; the TDZ bug we just fixed is a symptom but a narrow one. If you want incremental progress, start by grouping related globals into small namespaced objects (e.g. _voteState = { lastSips, prevSips, lastMilestoneKey, ... }) one feature area at a time, rather than one big-bang refactor.
- [X] _openBustVoteModal off-by-one (secs-- after server resync, item 12) — Fixed: a `resynced` flag tracks whether `secs` was just set from `lastState.bust_vote_seconds_left` this tick; `secs--` now only runs when it wasn't, preventing the double-decrement/timer-skip.
- [ ] "Dealer" magic string sentinel (item 13) — Define a constant const DEALER_SENTINEL = "Dealer" and reference it everywhere instead of the literal, plus consider checking state.dealer_name server-side rather than the display string where the distinction matters. Mostly a rename/constant-extraction — safe, mechanical, but touches several files (table.js mainly). Edge case it protects against (a player naming themselves "Dealer") is unlikely but cheap to guard.
- [X] Repeated DOM queries every poll (items 7 & 14) — #dig-action-row1/2 .btn and #panel .btn, #bottom-nav .bnav-btn re-queried on every 800ms poll/command. Cache the NodeList once at startup (or recompute only when the DOM structure actually changes, e.g. on hand-count change) and reuse. Straightforward perf win, low risk since it's read-only caching — good candidate for a focused commit.
- [ ] Five "once-per-seq" trackers (item 9) — _lastRoundOverSeq, _lastAceSeq, _lastMilestoneKey, etc. A shared onceForSeq(tracker, key, seq, fn) utility would consolidate the pattern. Medium risk because each tracker has slightly different reset semantics — I'd audit each one's exact behavior before unifying, otherwise you risk changing when toasts/modals fire. Worth doing, but carefully and one tracker at a time with testing.
- [X] Ad-hoc color thresholds (item 10 frontend, kpi.js dealer-bust %) — >= 40 / >= 25 thresholds duplicated as inline styles, separate from wrClass's >=50/>=40. Either name these as constants (DEALER_BUST_GOOD/OK thresholds) or, if they're meant to represent the same "good/ok/bad" semantics, consider a generalized colorClass(value, thresholds) helper. Small, cosmetic, low risk.
- [ ] _milestoneAllocations stale entries (item 16) — Very low priority edge case (requires player roster to change between two milestones with identical boundary+winner). I'd just add a one-line reset of _milestoneAllocations = {} whenever _lastMilestoneKey changes, which is nearly free and closes the gap entirely.
- [X] seatMap index-based mapping (item 17) — Switch _collectNewCardEls's seatMap lookup from positional seatEls[i] to seat.dataset.player (already set). Small, robust improvement — removes a fragile coupling between renderPlayers() ordering and animation code for very little cost.

### Priority order for remaining items

1. Insurance votes_needed == 0 manual verification — Trivial (manual test + comment, no code change expected)
2. _milestoneAllocations stale entries (item 16) — Trivial (one-line reset)

7. serialize_state() ~80-key breakup — Low/Medium (cosmetic restructuring, easy but touches a large function)
8. "Dealer" magic string sentinel (item 13) — Medium (mechanical but spans several files)
9. Five "once-per-seq" trackers (item 9) — Medium (consolidation utility, but each tracker's reset semantics must be audited individually — risk of changing toast/modal timing)
10. command() ~500-line monolith — High (biggest structural item; recommend extracting the shared "after any player action" block first as a lower-risk intermediate step)
11. Global state sprawl (state.js) — High (defer; touches nearly every UI file — only tackle as part of a larger rewrite)
