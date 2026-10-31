# Architecture

Technical documentation for **Black(Out)Jack**: project structure, layering rules, simulation, and development guide

---

## Table of Contents
- [Project Structure](#project-structure)
- [Layering Rules](#layering-rules)
- [Normal ⇄ Drinking switching](#normal--drinking-switching)
- [House rules (rule toggles)](#house-rules-rule-toggles)
- [Separation of Concerns](#separation-of-concerns)
- [Simulation & Statistics](#simulation--statistics)
- [Rules/Code Sync Check](#rulescode-sync-check)
- [Terms Doc Sync Check](#terms-doc-sync-check)
- [Common Issues](#common-issues)
- [Development Guide](#development-guide)

---

## Project Structure

One line per folder, with files grouped by job. Every module opens with a
docstring that says what it owns, so this section stays at overview level.

```
Black-Out-Jack/
├── server.py                 # Flask entry point
├── app/                      # Web layer (Flask)
│   ├── __init__.py           # App factory: registers blueprints, builds bundles, serves / and /terms
│   ├── config.py             # App-wide constants, defaults, feature flags
│   ├── models/               # game_room.py (GameRoom, RoundState, DrinkLedger, GameConfig, SessionStats),
│   │                         #   state_schema.py (Pydantic AppState, validates serialize_state())
│   ├── routes/               # HTTP endpoints, one blueprint per area (see "Routes" below)
│   └── services/             # Game logic that needs a session (see "Services" below)
├── engine/                   # Core game library, no Flask (START HERE)
│   ├── blackjack.py          #   cards, hands, deck, NPC players, round loop
│   ├── strategy.py           #   basic-strategy tables + best_play()
│   ├── style_strategy.py     #   player-mimicry bot resolver (reads player_profiles/*.json)
│   ├── events.py             #   typed events dispatched to DrinkingRules.handle()
│   ├── rules_registry.py     #   every toggleable rule (stable IDs) and the per-room RuleSet
│   ├── drinking_rules.py     #   the drinking layer, reacts to events
│   ├── drink_rate.py         #   pure Drink Rate maths (presets, scale_sips, exempt_rate)
│   ├── referee.py            #   RefereeSession for real-life play
│   └── player_profiles/      #   mined per-player deviation tables (built by scripts/build_player_profiles.py)
├── static/
│   ├── css/                  # main.css + components/*.css, bundled into bundle.css (generated, gitignored)
│   ├── js/                   # utils, state, app, benchmarks (generated) + ui/*.js, bundled into bundle.js
│   │                         #   (generated, gitignored); vendor marked/purify for the Rules modal,
│   │                         #   html2canvas/jspdf for the recap PDF (loaded on demand)
│   └── img/                  # Logos and icons
├── templates/                # index.html + partials/index/* (the page loads only the bundles);
│                             #   terms.html is a standalone styled copy of docs/Terms.md
├── scripts/                  # Standalone CLI tools (see "Scripts" below)
├── tests/                    # pytest: app/ (web layer), engine/, scripts/; mirrors the source layout,
│                             #   one test_<feature>.py per feature, shared fixtures in conftest.py
├── data/                     # decisions/ (tracked session exports used to mine bot profiles),
│                             #   profile_backups/ (copies taken before a profile rebuild),
│                             #   recaps/ (sample recap decks from scripts/build_recap_deck.py)
├── docs/                     # Rules.md, Rules-Normal.md, Rules-Catalog.md (stable rule IDs, one per toggle),
│                             #   Cheat-Sheet.md, Dev-Cheat-Sheet.md, Comprehensive-Example.md,
│                             #   Multiplayer.md, DOM-Hooks.md, Terms.md, this file; .rules_sync.json /
│                             #   .terms_sync.json (sync-check pins); planning/ (plans and TODOs,
│                             #   including the RuleToggles-*.md set)
└── manifest.json, requirements*.txt, pyproject.toml (ruff + pytest markers), README.md, LICENSE
```

### Routes (`app/routes/`)

| Area | Modules |
|---|---|
| Lobby, pages | `lobby.py` (rooms, setup incl. `rules_preset`, `/room_invite`), `static_pages.py` (logo, manifest, `/rules`, `/rules_registry`, tip links), `reports.py` (XLSX exports, `/summary_json`, `/recap_html`) |
| Polling | `polling.py` (`GET /state` only; per-poll side effects run in `services/tick.py`) |
| Game commands | `game_commands.py` (`/command` dispatcher, `/rebuy`, `/honor_resolve`), `commands/` (`digital.py`, `referee.py`, `common.py`: the handler registries) |
| Player actions | `registration.py` (seats, registration), `suggestions.py` (preselect, suggest), `side_bets.py` (insurance, bust vote, buy-in and comeback handouts, stakes), `dealer_lottery.py`, `boj.py` ("Switch to BOJ" poll), `targeted_drinking.py` (player and admin routes), `drink_rate.py`, `rule_votes.py` (rule suggestions and table votes) |
| Admin | `admin.py` (settings incl. house-rule edits, milestone claim, pause), `moderation.py` (kick, rejoin, leave), `admin_transfer.py` (handover, admin-AFK vote), `players.py` (bots, seats, dealer rotation) |
| Shared | `_auth.py` (`_require_admin`, `_require_host_or_dealer`), `wild_card.py` (easter egg) |

### Services (`app/services/`)

| Job | Modules |
|---|---|
| Round flow | `game_engine.py` (dealing, dealer turn, `resolve_endround`, NPC auto-play), `player_actions.py` (helpers shared by `/command` handlers), `round_pipeline.py` (the post-round sequence), `tick.py` (per-poll side effects) |
| Room and session | `session_store.py` (in-memory rooms, single source of truth), `room_factory.py` (build a room), `room_manager.py` (queued settings, dealer rotation, admin transfer), `pause.py`, `afk.py` |
| Drinks and money | `drink_tracker.py` (sip ledger, milestones, bust-vote penalties, L badge and comeback handout), `payout_tracker.py` (bankrolls, stake window), `buyin_handout.py`, `decision_log.py` |
| House rules | `house_rules.py` (validate, queue and apply rule changes, the `rules` block of `/state`, `/rules_registry` data), `rule_votes.py` (players' suggestions, table votes) |
| Feature modes | `dealer_lottery.py`, `targeted_drinking.py`, `drink_rate.py`, `boj_switch.py` |
| Reports | `recap_deck.py` (the session recap deck: numbers, slides, HTML; see "Session recap deck" below) |
| Snapshot (`GET /state`) | `serializer.py` (`serialize_state` only), `round_state.py` (leaf: turn order and phase), `stats.py` (derived numbers, KPI), `serializers/` (one module per feature block) |
| Infrastructure | `asset_bundler.py` (JS/CSS bundles), `validators.py`, `utils.py`, `qr.py` |

### Frontend (`static/js/ui/`)

Classic scripts, concatenated in the order of `JS_SOURCES` in
`app/services/asset_bundler.py` (that list is the only place to edit).

| Area | Files |
|---|---|
| Boot and connection | `config.js` (constants), `poll.js` (`/state` loop, connection-lost screen), `bootstrap.js` (click delegation), `lobby.js`, `room-qr.js`, `tip.js`, `idle.js` |
| Setup and seats | `setup.js`, `seats.js` (registration, local seats, transfers), `bets.js` (Normal-mode stakes) |
| Table | `table.js` (`applyState` and `_sync*`), `table-render.js`, `table-modals.js` (feature panels), `drink-panels.js` (bust vote, Dealer Lottery, handouts, toasts), `animation.js`, `log.js`, `kpi.js`, `trivia.js` |
| Admin and summary | `admin.js` (role UI, toggles), `admin-settings.js` (settings and players modals), `rules-settings.js` (📜 House rules view, preset chips, rule-vote modal), `rules.js` (Rules popup, OFF badges), `summary.js` (summary and exports), `recap-pdf.js` (recap deck to PDF) |

Element IDs and which file owns them are in [DOM-Hooks.md](DOM-Hooks.md).

### Scripts (`scripts/`)

| Job | Files |
|---|---|
| Play in a terminal | `play_terminal.py`, `play_referee.py`, `_cli.py` (shared input helpers, `--preset`) |
| Simulation | `simulation.py`, `run_all_configs.py`, `compare_configs.py`, `compare_bot_styles.py`, `snapshot.py` (saves to `snapshots/<label>/`) |
| Bot profiles | `load_decision_logs.py`, `build_player_profiles.py` (mines `data/decisions/` into `engine/player_profiles/`) |
| Doc sync | `rules_sync.py`, `terms_sync.py` |
| Reports | `build_recap_deck.py` (recap deck as a vector PDF from two saved exports, via local Edge/Chrome; its `print_pdf` is shared), `build_pitch_deck.py` (the README's pitch deck in two looks, `docs/Pitch-Deck.pdf` in the app's colours and `docs/Pitch-Deck-Finance.pdf` in the same dark colours as a sober report: no emojis, square corners, numbered blocks; the typical night is modelled from the logged rounds in `data/decisions/`, balance comes from `scripts/benchmarks.json`, rule counts from the rules registry) |

## Layering Rules

The main files are intentionally decoupled. These rules are what keeps it so:

- **`engine/` knows nothing about `app/`.** `strategy.py`, `events.py` and `drink_rate.py` import nothing; `blackjack.py` imports `strategy.py`; `drinking_rules.py` and `referee.py` build on `blackjack.py` and `events.py`.
- **`app/services/` never imports `app/routes/`.** Anything a service and a route both need lives in a service.
- **Routes never import each other.** Shared request auth is in `routes/_auth.py`.
- **`round_state.py` is a leaf.** It imports no serializer, so domain services (`afk`, `tick`, `game_engine`, the feature modes) can read turn and phase without depending on the presentation layer. `serializer.py` sits on top and only assembles the snapshot.
- **`AppState` is strict.** Every field `serialize_state` returns must exist in `models/state_schema.py` (`extra="forbid"`), so a serializer and schema mismatch fails immediately instead of reaching the frontend.
- **Generated files are never edited:** `static/js/bundle.js`, `static/css/bundle.css`, `static/js/benchmarks.js` (from `scripts/simulation.py`).
- **Sync-checked docs:** `Rules.md` against `drinking_rules.py` and `Terms.md` against `terms.html` (see the sync checks below).

## Normal ⇄ Drinking switching

A table is created in one mode, but a **Normal** table can become **Drinking** later without going through the lobby (the switch is one-way; a Drinking table can't go back):

- **Admin toggle** — `POST /update_settings {drinking_mode: true}` queues the switch in `_queued_settings`; `room_manager.apply_queued_settings` applies it at the next `newround`, just before `start_round` builds a `DrinkTracker` (a `NullTracker` is installed in Normal mode). Same room, same seats, bankrolls kept.
- **Table poll** — `POST /boj/propose` → `/boj/vote` (see `services/boj_switch.py`). A majority queues the same switch for everyone; a minority leaves for a new Drinking room via `POST /boj/split/cancel` (back out during the cancel modal) and `POST /boj/split/go` (redirect; the client stores the new room code and reloads, resuming into a room it is already registered in).
- The state payload carries it all in `AppState.boj` (`poll`, `last_result`, `my_split`, `can_propose`); the UI lives in `static/js/ui/table-modals.js` (`BojPollPanel`, `BojSplitPanel`).

## House rules (rule toggles)

Each room picks which drinking rules it plays. The design docs are
`docs/planning/RuleToggles-*.md`; the player-facing list is
`docs/Rules-Catalog.md`.

- **Registry.** `engine/rules_registry.py` declares every rule once (stable
  ID, group, dependencies, lowest preset, unlock step, Rules.md anchor, CSV
  labels, `live` flag). A room's choice is a `RuleSet`;
  `rules.on("ace.hearts.player")` answers with dependencies resolved.
- **One copy.** `GameConfig.rules` is the only store. The engine session
  reads it live through `rules_source`, so a write reaches every gate at once.
- **Gates at the source.** Each rule is checked where it decides to fire
  (`drinking_rules.py` for card and round rules, app services for events),
  never by filtering messages afterwards. `tests/engine/test_rules_gate_coverage.py`
  maps every toggleable rule to its "off means off" test and fails when one
  is missing; it also fails on any event or helper call that doesn't pass
  `rules=`.
- **Changes.** The admin edits through `/update_settings`
  (`house_rules.update_rules`): live rules (bust vote, wild card) apply at
  once, the rest queue as the full target set and apply at the next
  `newround` with a round-log notice. Players suggest changes, or vote them
  in once the table has voted to allow that (`rule_votes.py`).
- **State.** `/state` carries ID lists only (`rules`, `rule_votes`); names and
  groups come from `GET /rules_registry`, fetched once by `rules-settings.js`.

## Session recap deck

The summary modal's **📊 Download Recap (PDF)** button gives a
consulting-style story of the session, about 15 pages plus one per player.
The cover comes first, then the executive summary, race, league table, sip
bridge, drivers, tempo, decision quality, the house, side games, player
comparables and awards. Then comes a recap page for each player, in
finishing order: their running total against a typical seat, top sip
sources, headline numbers, hands, doubles and splits, basic-strategy match,
dealer record, Drink Rate factor, awards and a takeaway. An appendix covers
the table setup and house rules, then the definitions, and a thank-you page
with the tip QR code closes the deck.

- **One builder.** `app/services/recap_deck.py` turns the export rows
  (`drinks.csv_rows`, `_decision_log`, `_dealer_lottery_decision_log`) into
  numbers (`analyse`) and then into one HTML page of 1280×720 slides
  (`build_html`). The slides use the app's colours (the `:root` tokens in
  `main.css`) and logo. Slide titles are full-sentence takeaways worded from
  the data. Slides without data drop out (decision quality, the house, side
  games), and page numbers follow.
- **Drink Rate.** Each drink row carries `sips_raw` (before the factor) and
  `rate`. When any seat played off 1.0×, the bridge starts from the sips owed
  at 1.0× with a "Drink Rate factors" step. The league table, comparables and
  player pages show each seat's average factor. Two extra awards appear:
  Booster and Sipping smart. Rounds per factor come from
  `stats.rate_rounds` in the app. From an xlsx export they are read off the
  rows, so a round whose only sips skipped boosters reads as 1.0×.
- **House rules.** `/recap_html` passes the room's `RuleSet`, sips per hand,
  hands per player and Easy Mode as `setup`. The setup slide lists the rules
  that were off, grouped by `GROUPS`, with the preset. A side game shows when
  its rule is on or when it left any sips, so a rule turned off mid-session
  still counts. The deck shows the rules as they were at export, because rule
  changes aren't recorded. The xlsx exports carry no rules, so the script's
  setup slide says so.
- **PDF in the browser.** Render has no browser to print with, so
  `GET /recap_html` returns the HTML and `static/js/ui/recap-pdf.js` lays it
  out in an off-screen iframe. It draws each slide with html2canvas, adds it
  as a jsPDF page, and puts the tip link back as a clickable area. Both
  libraries are vendored in `static/js/` and load on the first tap only.
  The pages are images, about 3 MB per deck.
- **Saving.** Desktops download the file. Phones (a coarse pointer, plus Web
  Share with files) get the share sheet instead: iOS can't download a blob,
  and opening it would take the home-screen app away from the game. iOS
  only opens the sheet from a tap, so a "Recap ready" bar offers one once
  the PDF is built.
- **PDF on a dev machine.** `scripts/build_recap_deck.py <day>` reads
  `data/decisions/drinks_summary_<day>.xlsx` and `decision_log_<day>.xlsx`,
  builds the same HTML and prints it to a vector PDF through headless
  Edge/Chrome, written to `data/recaps/`.

## Separation of Concerns
- **Changing a drinking rule** → edit only `engine/drinking_rules.py`
- **Adding a toggleable rule** → declare it in `engine/rules_registry.py`, gate it at the source, add its "off means off" test to `GATE_TESTS`, and give it an entry in `Rules-Catalog.md` and an anchor in `Rules.md` (tests check all four)
- **Changing core game logic** → edit only `engine/blackjack.py`
- **Changing basic strategy** → edit only `engine/strategy.py`
- **Adding a referee command** → edit only `engine/referee.py`
- **Changing web routes or server logic** → edit `app/routes/` or `app/services/`
- **Changing web UI behaviour** → edit `static/js/ui/` and/or `templates/index.html`
- **Changing styles** → edit `static/css/main.css` or the relevant `static/css/components/` file
- **Changing the recap deck** (slides, wording, colours) → edit only `app/services/recap_deck.py`; the app and `scripts/build_recap_deck.py` both pick it up
- **Adding/renaming a game phase or client role** → update `PHASE` / `ROLE` in `static/js/ui/config.js` (consumed by all other UI scripts)


## Simulation & Statistics

Curious whether the rules are balanced or which rule is responsible for most of the drinking?

Track every drink event from start to finish in a simulation (100,000 rounds, 2 hands per
player, rotating dealer). Frequency and rule breakdown are output in `simulation_results.txt`
and `simulation_log.csv` respectively.

```bash
python scripts/simulation.py
```

The script prompts for player count (2-6, default 3) and deck count (1-8, default 1);
players are named `Player1..N`. `--preset starter|standard|full` (default full) plays a
house-rule preset; a non-Full run writes `simulation_results_<preset>.txt` and leaves
the benchmarks alone, since they are the Full baseline.

The same run also tallies hand outcomes (blackjack/bust/win/loss/push rates, dealer-bust rate),
average sips/round, and the standard deviation of sips/round (`std_sips_per_round`), merging
them into `scripts/benchmarks.json` and `static/js/benchmarks.js`
(`const BENCHMARKS_BY_CONFIG = {...}`), keyed by `"<players>p_<decks>d"` (e.g. `"3p_1d"`) —
each config's results accumulate across runs rather than overwriting other configs.
`static/js/ui/kpi.js` picks the table matching the live session's player/deck count
(`_benchmarkTable()`, falling back to same-player-count or any available config) and compares
live stats against it using a z-score / standard-error calculation that scales with the live
round count — `benchmarkColor()` colors a stat yellow at |z| > 1 and green/red at |z| > 2,
depending on whether the deviation is favorable. Re-run `simulation.py` after any change to
`engine/drinking_rules.py` or `engine/blackjack.py` to refresh the benchmarks for a given
config.

### Committing regenerated benchmarks

`scripts/benchmarks.json` and `static/js/benchmarks.js` are **generated, but
checked into git** — they're committed so `kpi.js` has benchmark data to
compare against without requiring every dev/deploy to run a 100k-round
simulation first.

- Run `python scripts/simulation.py` and commit the resulting changes to
  `scripts/benchmarks.json` + `static/js/benchmarks.js` whenever
  `engine/drinking_rules.py` or `engine/blackjack.py` changes in a way that
  could shift sip frequencies (new/changed rule, probability tweak, etc.).
  Purely cosmetic or non-engine changes don't need a regeneration.
- Because `run_simulation` is unseeded by default, every regeneration
  produces a full-file diff (every numeric field shifts slightly) even when
  nothing meaningful changed. This is expected — review the diff for
  *direction/magnitude* of change in the relevant config(s)/rule(s), not for
  an exact match.
- Only the config(s) you actually ran get a new `"generated"` timestamp and
  updated stats; other configs in the file are left untouched (results
  accumulate per-config rather than being overwritten wholesale — see above).
- If you only touched docs/UI/tests and didn't change engine behavior, leave
  `benchmarks.json`/`benchmarks.js` alone — don't regenerate just to "freshen"
  the timestamp.
- CI does **not** verify `benchmarks.js` is in sync with the engine; this is
  a manual step for now.

### Regression snapshots

To check whether an engine change shifted the drinking-rule balance, save the current
simulation output as a labeled snapshot:

```bash
python scripts/simulation.py
python scripts/snapshot.py baseline   # or omit label for a timestamp
```

This copies `simulation_results.txt` and `benchmarks.json` into
`scripts/snapshots/<players>p/<decks>deck/<label>/` (config taken from the most recently
generated entry in `benchmarks.json`). After future engine changes, re-run the simulation
and diff the new output against the snapshot to spot unintended balance shifts.

## Rules/Code Sync Check

`docs/Rules.md` (what players read) and `engine/drinking_rules.py` (what
the code actually does) can drift apart silently — someone edits the
rules doc without updating the logic, or vice versa. `scripts/rules_sync.py`
guards against this by pinning SHA256 hashes of both files in
`docs/.rules_sync.json`.

`tests/engine/test_rules_doc_sync.py` runs this check as part of the normal
test suite and fails with one of:

- **in sync** — pass, nothing to do
- **docs changed, code didn't** — review whether `drinking_rules.py` needs
  updating to match the new rule text
- **code changed, docs didn't** — review whether `Rules.md` (and
  `Cheat-Sheet.md` / `Comprehensive-Example.md`) need updating to describe
  the new behavior
- **both changed** — review that the two are still consistent with each
  other
- **no baseline recorded** — `docs/.rules_sync.json` is missing

Once you've confirmed the doc and code are aligned (after editing one,
the other, or both), re-pin the hashes:

```bash
python scripts/rules_sync.py update
```

Commit the updated `docs/.rules_sync.json` alongside your change. This
check only covers `Rules.md` + `drinking_rules.py` — it doesn't replace the
benchmark regeneration step above, which covers behavioral/statistical
drift in `engine/blackjack.py` as well.

## Terms Doc Sync Check

Same idea, for the Terms & Disclaimer page. `docs/Terms.md` is the single
point of truth (readable directly on GitHub, linked from the README); it's
mirrored as a styled standalone page at `templates/terms.html`, served at
`/terms` and linked from the age gate and lobby footer. The two are
different formats (Markdown vs. HTML) so this can't diff their content
directly — `scripts/terms_sync.py` pins SHA256 hashes of both files in
`docs/.terms_sync.json`, the same tripwire pattern as `rules_sync.py`.

`tests/app/test_terms_doc_sync.py` runs this check as part of the normal
test suite and fails with one of the same four outcomes (in sync / docs
changed only / HTML changed only / both changed — review, then re-pin) as
the Rules/Code check above. After editing either file, re-pin with:

```bash
python scripts/terms_sync.py update
```

Commit the updated `docs/.terms_sync.json` alongside your change.

## Common Issues

| **Problem** | **Cause** | **Solution** |
|---|---|---|
| **Insufficient Cards** | Multiple players splitting aggressively | Use multiple decks (auto enabled for 4+ players) |
| **Large groups** | More players trigger more rules, sips add up | Games with 4 or more players automatically halve all end-of-round sip totals |


## Development Guide

### Prerequisites
- Python 3.10+
- `flask` (for web UI)
- `pydantic` (for web UI — validates the state payload the web UI polls; see `app/models/state_schema.py`)
- `segno` (pure Python, no dependencies — renders QR codes as SVG: the room's join link for `GET /room_invite`, the tip link for `/beer_qr` and the recap deck)
- `openpyxl` (for web UI — `/export_xlsx` and `/export_decisions`; also used by `scripts/build_player_profiles.py` and `scripts/load_decision_logs.py` to read exported logs back in)
- `pytest` (for running the test suite)
- No other dependencies for terminal play
- Vendored browser libraries (in `static/js/`, no install step): `purify.min.js`, `marked.min.js` (Rules modal), `html2canvas.min.js` 1.4.1, `jspdf.umd.min.js` 2.5.2 (recap PDF)
- `scripts/build_recap_deck.py` also needs Microsoft Edge or Google Chrome installed locally (headless PDF printing)
- Consult [requirements.txt](requirements.txt) (deployment) or
  [requirements-dev.txt](requirements-dev.txt) (adds `pytest` for local
  development: `pip install -r requirements-dev.txt`)

### Running locally
```bash
# Web UI
python server.py                 # → http://localhost:5000

# Terminal game
python scripts/play_terminal.py  # No extra dependencies; --preset starter|standard|full

# Referee mode
python scripts/play_referee.py   # Physical deck, digital tracking; --preset as above

# Simulation
python scripts/simulation.py     # Outputs to simulation_results.txt

# Tests
pytest -m "not slow"             # Fast unit + regression suite (CI default)
pytest -m slow                   # Full 100k-round snapshot diff (manual/release)
```


### Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

Rule ideas are especially welcome — if it made the game more fun, it probably belongs here!
