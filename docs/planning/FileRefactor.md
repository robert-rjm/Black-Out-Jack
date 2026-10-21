# File Refactor: Open Work

Merged from the old `FileSplitRefactor.md` (files that grew too big) and
`FilePlacementRefactor.md` (code in the wrong file or layer). Only work that is
still open is listed here; what is already finished is summarised at the bottom
so it is not redone.

**Pure moves only.** No behaviour changes. Every step leaves `pytest` green and
the game playable. One step per commit, and click through the affected UI after
each JS step.

## Ground rules

- **Python:** keep the old module path importable (thin explicit re-export)
  until every caller and test is migrated, then delete the shim. Resolve circular
  imports with leaf modules, not lazy imports.
- **JS:** classic scripts, concatenated by `app/services/asset_bundler.py`
  (`JS_SOURCES`). That list is the only place to edit: `templates/partials/index/_scripts.html`
  now loads just `bundle.js`. Top-level `const` / `class` declarations are
  load-order sensitive (TDZ): a new file must load after anything it uses at load
  time and before anything that uses it at load time. Function names must stay
  unique across files, so grep for collisions before moving.
- `static/js/bundle.js` and `static/css/bundle.css` are generated; never edit.
- Tests may patch `app.services.<mod>.<name>` or `app.routes.<mod>.<name>`; after a
  move, patch targets must point at the module where the name is *used*.
- Update `docs/Architecture.md` and `docs/DOM-Hooks.md` (and `Dev-Cheat-Sheet.md`
  if it names the file) in the same commit as each move.

## Open to-do (in suggested order)

### A. Verify what is already done (small)

- [ ] Play through lobby, a Normal round, a Drinking round and the BOJ switch
      vote, to confirm the finished JS and route moves (checklist at the bottom).
- [ ] Reload with the console open and confirm no `ReferenceError` on boot.

### B. Backend layering (high value, unblocks the route and service splits)

- [x] **B1. `routes/_auth.py`.** Move `_require_admin` and
      `_require_host_or_dealer` out of `routes/admin.py`.
      `routes/polling.py:33` still imports them from `admin.py` (route-to-route import).
- [x] **B2. `services/round_state.py` (leaf).** Move `play_order`, `hand_done`,
      `player_done`, `current_turn`, `round_phase`, `serialize_card`,
      `serialize_hand` out of `serializer.py` (still L312-348 area). Then migrate
      `afk.py`, `dealer_lottery.py`, `drink_rate.py`, `game_engine.py`,
      `targeted_drinking.py` and `tick.py`, which all import them from
      `serializer.py` today (domain services depending on the presentation layer).
- [x] **B3. Rest of `serializer.py` (1,260 lines).** `services/stats.py`
      (`_compute_live_drink_totals`, `compute_sip_totals`, `compute_payout_data`,
      `compute_best_play`, `compute_mandatory_split*`, `compute_trophy_holder`,
      `compute_kpi_stats`); a `services/serializers/` package
      (`milestone`, `dealer_lottery`, `targeted_drinking`, `insurance`,
      `bust_vote`, `drink_rate` / `admin_afk`); `serializer.py` keeps only
      `serialize_state`. **Deduped:** the serializer now uses `targeted_drinking_awaiting_start` from
      the service. The old serializer copy omitted the unclaimed-handout check, so
      it could show "Start Targeting Now" when the start request would be refused.

### C. Backend routes

- [x] **C1. Split `routes/polling.py` (1,259 lines).** It should hold `/state`
      only. New blueprints: `registration.py` (`/register`,
      `/request_local_seat`, `/handle_seat_transfer`, `/handle_registration`,
      `/reset_registration`), `suggestions.py` (`/preselect`, `/suggest_action`,
      `/respond_suggest`), `side_bets.py` (`/vote_insurance`, `/cast_bust_vote`,
      `/give_bust_sip`, `/set_player_bet`), `dealer_lottery.py`
      (`/dealer_lottery/*`), `targeted_drinking.py` (all `/targeted_drinking/*`
      from both `polling.py` and `admin.py`). Register each in `app/__init__.py`.
- [x] **C2. Split `routes/admin.py` (990 lines).** `moderation.py` (`/kick`,
      `/undo_kick`, `/vote_kick`, `/request_rejoin`, `/handle_rejoin`,
      `/leave_room`), `admin_transfer.py` (`/transfer_admin`, `/admin_afk/*`,
      `_hand_admin_to_voter`), `players.py` (`/make_bot`, `/make_human`,
      `/set_bot_personality`, `/take_back_seat`, `/rotate_dealer`). `admin.py`
      keeps `/update_settings`, `/set_hint`, `/set_anim_pref`,
      `/toggle_god_mode`, `/set_paused`, `/claim_milestone`. **Still open:**
      move the `/claim_milestone` body (~115 lines) into a milestone service
      and leave the route thin; that is part of D2.
      (`auto_transfer_admin` is already in `room_manager.py`.)
- [x] **C3. `routes/game_commands.py` (907 lines), light split.** Extract
      `_record_strategy_decision`, `_check_honor_house_rule`,
      `_penalize_unsplit_aces`, `_perform_action_without_honor`,
      `_after_player_action` to `services/player_actions.py`. Move the `_cmd_*`
      digital handlers, registries and `_print_digital_help` to
      `routes/commands/digital.py`, the referee ones to
      `routes/commands/referee.py`; keep `/command`, `/rebuy`, `/honor_resolve`
      and the dispatcher. (`deal_now` / `resolve_endround` are already in
      `game_engine.py`.)

### D. Backend services

- [ ] **D1. `drink_tracker.py` (1,020 lines).** Keep `award_sips` and rule
      classification. New: `bust_vote_penalties.py`
      (`apply_bust_vote_penalties`, `apply_bust_handout_forfeit`),
      `round_harvest.py` (`harvest_drink_log` and its `_record_*` / `_update_*` /
      `_snapshot_round` / `_with_raw` helpers).
- [ ] **D2. `services/milestones.py`.** Milestone check / assign / tie /
      round-robin / forfeit from `drink_tracker.py`, plus the `/claim_milestone`
      body (C2). `tests/app/test_harvest_helpers.py` and
      `test_milestone_win_streak.py` already map 1:1 to D1 / D2.
- [ ] **D3. `targeted_drinking.py` (788 lines), light.** Move the target-proposal
      sub-feature (`propose_targeted_drinking_target`,
      `submit_target_proposal_vote`, `_finish_target_proposal`,
      `_maybe_resolve_target_proposal`, `apply_target_proposal_vote_forfeit`) to
      `target_proposal.py`. Splitting the 210-line
      `resolve_targeted_drinking_round` into draw / score / payout is a later,
      separate pass.
- [ ] **D4. (optional) `models/state_schema.py` (706 lines).** If split:
      `schema/core.py`, `schema/kpi.py`, one file per feature mirroring
      `serializers/` (B3); `AppState` stays in `state_schema.py`.

### E. Frontend

- [ ] **E1. `table-modals.js` (1,948 lines, still unsplit; biggest remaining
      JS payoff).** Split by feature and delete the file when empty:
      `insurance.js` (`InsurancePanel`, `castInsuranceVote`), `milestone.js`
      (`MilestonePanel`, `milestoneAdjust`, `submitMilestoneHandout`),
      `targeted-drinking.js` (`TargetedDrinkingPanel`, `_tdRevealLine`,
      about 780 lines, so consider a further `target-proposal.js` for
      `TargetProposalPanel` and `proposeTargetedDrinkingTarget`),
      `boj-vote.js` (`BojPollPanel`, `BojSplitPanel`; **new**, not in the old
      plan), `admin-afk.js` (`AdminAfkPanel`, `_postAdminAfk`),
      `drink-rate.js` (`_rateName`, `DrinkRatePanel`, `_postDrinkRate`,
      `LateJoinPanel`). Each panel is instantiated at load time in its own
      file, so panel order is safe as long as the files stay together before
      `bootstrap.js`.
- [ ] **E2. `admin-settings.js` (897 lines).** Rules and summary are already out.
      Remaining: `settings-players.js` (settings subview, `openKickModal`, player
      actions, `renderKickVoteBanner`) and `settings-game.js`
      (`_populateSettingsUI`, queued banner, `queueSettings`, add / remove
      player, rotate dealer, `takeBackSeat`, Targeted Drinking admin controls).
      `openKickModal` alone is about 440 lines; extracting its row builders is
      the only non-mechanical change in the plan, so do it as its own commit.
- [ ] **E3. `table.js` (1,166 lines), lower priority.** `table-build.js`,
      `table-commands.js`, `apply-state.js`, `table-prompts.js`,
      `drinks-panel.js` (`DrinksPanel`, `autoSwitchDigTab`, `activateDigTab`).
      `DrinkUI`, `sel`, `selRank`, `selSuit` currently sit at the top of
      `table.js`; keep them in the first file of this split.
- [ ] **E4. (optional) Split `drink-panels.js` (1,086 lines)** into
      `bust-vote.js`, `dealer-lottery.js`, `targeted-drinking-give.js` /
      `buyin.js` and `toasts-player.js` if it keeps growing. Not a placement
      error. If E1 creates `targeted-drinking.js`, move
      `TargetedDrinkingGivePanel` / `giveTargetedDrinkingSip` there.

### F. Engine (low priority)

- [ ] `engine/blackjack.py` (848): cards / shoe / hand / player classes ->
      `engine/cards.py` + `engine/players.py`; `HandEvaluator` and `RoundManager`
      stay. Keep `blackjack.py` re-exporting (scripts and profiles import from it).
- [ ] `engine/drinking_rules.py` (908): move `DrinkTracker` to
      `engine/drink_tracker.py`; leave `DrinkingRules`.
- `engine/referee.py` (820): leave.

### G. Tests and CSS (do alongside the matching source split)

- [ ] `tests/app/test_targeted_drinking.py` (2,365 lines) ->
      `tests/app/targeted_drinking/` with a `conftest.py` (`_ScriptedDeck` and
      helpers) and `test_trigger`, `test_voting`, `test_resolution`,
      `test_proposals`, `test_handouts`, `test_serializer`. Mirror D3.
- [ ] `tests/app/test_dealer_lottery.py` (1,286 lines): same treatment, now
      overdue (it was "optional" at 1,113 lines).
- [ ] `static/css/components/modals.css` (742): split by feature to match the JS
      panels from E1 and add to `CSS_SOURCES`; audit `utilities.css` (641) for
      feature-specific rules.

### H. Docs

- [ ] After each step above, update `Architecture.md` / `DOM-Hooks.md`.

## Risks

- Circular imports (`routes/polling` and `routes/admin`; services and
  `serializer`): fix with leaf modules (B1, B2) before the larger splits.
- No JS module system: name collisions and TDZ order are the main failure modes;
  a missing class shows up as a `ReferenceError` on boot.

## Already done (do not redo)

- Services no longer import from `app/routes/` (`auto_transfer_admin` /
  `transfer_local_names` in `room_manager.py`; `deal_now` / `resolve_endround` in
  `game_engine.py`).
- Routes: `routes/static_pages.py` (`/logo.png`, `/manifest.json`, `/rules`,
  `/beer`, `/beer_qr`); QR renderer in `services/qr.py`.
- Old `admin.js` split into `drink-panels.js`, `seats.js`, `bets.js` (and
  `admin.js` is now 330 lines of admin toggles plus `updateRoleUI`).
- `lobby.js` split into `poll.js` and `room-qr.js`; waiting room and
  `resetToSetup` live in `lobby.js`; `tip.js` holds the Tip-us code.
- `setup.js` split: idle watcher in `idle.js`; `DrinkUI` / `sel*` moved to the
  top of `table.js`.
- `admin-settings.js`: Rules modal in `rules.js`, session summary and exports in
  `summary.js`.
- Docs and data ownership notes corrected; `data/decisions/` is tracked on
  purpose, the dead `data/drinks/` entry is gone.

## Done when

- `grep -rn "from app.routes" app/services` is empty (met today) and no route
  module imports from another route module.
- No service imports from `serializer.py` except `serialize_state` consumers.
- No JS file owns functions unrelated to its name, and none is over about 1,000
  lines without a reason.
- `Architecture.md` and `DOM-Hooks.md` match the code.
- `pytest` is green and the game plays through lobby, a Normal round, a Drinking
  round and the BOJ switch vote.
