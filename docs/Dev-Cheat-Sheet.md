# Dev Cheat Sheet

Quick reference for CLI commands used during development. For gameplay rules, see
[Cheat-Sheet.md](Cheat-Sheet.md). For the full picture of what each script does and why,
see [Architecture.md](Architecture.md).

---

## Play the game

```bash
python server.py                 # Web UI → http://localhost:5000
python scripts/play_terminal.py  # Terminal game (solo or local multiplayer)
python scripts/play_referee.py   # Referee mode (physical deck, digital scorecard)
```

## Tests

```bash
pytest -m "not slow"             # Fast suite (CI default) — unit + regression
pytest -m slow                   # Full 100k-round snapshot diff (manual/release)
pytest                           # Everything
pytest tests/engine/test_style_strategy.py   # One file
```

## Simulation & benchmarks

```bash
python scripts/simulation.py                 # Prompts for player count (2-6) / deck count (1-8)
python scripts/simulation.py 4 2              # Non-interactive: 4 players, 2 decks
```
Outputs `simulation_results.txt`, `simulation_log.csv`, merges into `scripts/benchmarks.json`
and `static/js/benchmarks.js`. Re-run and commit the diff whenever `engine/drinking_rules.py`
or `engine/blackjack.py` changes in a way that could shift sip frequencies.

```bash
python scripts/run_all_configs.py                          # All configs, no prompts
python scripts/run_all_configs.py --players 2 3 4 --decks 1 2 3 4
python scripts/run_all_configs.py --snapshot baseline        # + save a snapshot per config
python scripts/run_all_configs.py --compare baseline         # + flag deviations vs. a snapshot
```

```bash
python scripts/compare_configs.py            # Table comparing all simulated configs
```

## Regression snapshots

```bash
python scripts/simulation.py
python scripts/snapshot.py baseline          # or omit label for a timestamp
```
Saves `simulation_results.txt` + `benchmarks.json` into
`scripts/snapshots/<players>p/<decks>deck/<label>/` for later diffing
(compared automatically by `tests/engine/test_regression_snapshots.py`).

## Rules/code sync check

```bash
python scripts/rules_sync.py check           # same check tests/engine/test_rules_doc_sync.py runs
python scripts/rules_sync.py update          # re-pin hashes after confirming Rules.md/drinking_rules.py align
```

## Player-mimicry bots (rob.json / marko.json / david.json)

1. Play sessions and download the session workbook with the summary modal's "Developer data"
   button (`GET /export_session?room_code=<code>&player=<name optional>` →
   `session_data_<day>.xlsx`, one file with the drinks and decision sheets). Save it into
   `data/decisions/` (tracked in git, so these can't be silently lost the way a local-only
   folder can be). The scripts also still read the older formats from the same directory:
   `drinks_summary_*` + `decision_log_*` xlsx pairs and `decision_log_*.csv` files. When a day
   has a `session_data_*` file, that day's legacy files are ignored (`scripts/session_files.py`).
2. (Optional) Take a first look at what's been collected:
   ```bash
   python scripts/load_decision_logs.py                    # summary across all logs
   python scripts/load_decision_logs.py --player Rob        # one player only
   python scripts/load_decision_logs.py --out data/decisions/combined.csv
   ```
3. Mine the logs into per-player deviation tables:
   ```bash
   python scripts/build_player_profiles.py                  # rebuild EXISTING profiles only (new names are listed, skipped)
   python scripts/build_player_profiles.py --player Rob      # just rob.json
   python scripts/build_player_profiles.py --player NewGuy   # new player: asks "create bot?" (add --yes to skip the prompt)
   python scripts/build_player_profiles.py --min-samples 3 --min-majority 0.60   # tune thresholds
   python scripts/build_player_profiles.py --merge           # fold in each player's EXISTING
                                                                # profile instead of overwriting —
                                                                # use this for a normal incremental
                                                                # update so past sessions aren't lost
   ```
   Writes/updates `engine/player_profiles/rob.json` (etc.), consumed by
   `engine/style_strategy.py`. Without `--merge`, a rebuild only reflects whatever raw
   `session_data_*` (or legacy `decision_log_*`) files are currently in `--dir` (default `data/decisions/`) — `--merge`
   combines that with the target file's already-recorded deviations instead.
4. Simulate with those profiles instead of generic basic-strategy bots, and compare:
   ```bash
   python scripts/simulation.py --personalities rob marko david   # 1 deck; full 100k-round run
   python scripts/simulation.py 3 2 --personalities rob marko david   # explicit players/decks
   ```
   Player count is taken from the number of names given (must match `<players>` if that's
   also passed). Writes `simulation_results_personas.txt` / `simulation_log_personas.csv`
   and deliberately does **not** touch `benchmarks.json`/`benchmarks.js` — those are the
   basic-strategy baseline `kpi.js` compares live sessions against.
   ```bash
   python scripts/compare_bot_styles.py                              # all mined profiles vs. basic
   python scripts/compare_bot_styles.py --personalities rob marko
   python scripts/compare_bot_styles.py --decks 2 --rounds 100000 --seed 7
   ```
   Runs basic-strategy bots and named personas on the **same seed** (identical shoes/cards),
   then prints a side-by-side stats table (avg sips/round, bust/blackjack/win rates, etc.)
   plus a per-seat sips/round breakdown — isolating the effect of the mined profile from
   ordinary card-luck variance.

## Other exports (web UI)

```
GET /export_session?room_code=<code>    # The one session workbook: drinks + decision sheets (recap, profiles)
GET /export_xlsx?room_code=<code>       # Legacy: drinks sheets only
GET /export_decisions?room_code=<code>  # Legacy: decision sheets only
GET /summary_json?room_code=<code>      # Drink summary as JSON
GET /recap_html?room_code=<code>        # Recap deck as HTML slides (the browser turns it into the PDF)
```

Recap deck as a vector PDF from a session's saved export, `session_data_<day>.xlsx` or the legacy pair (needs local Edge/Chrome):

```bash
python scripts/build_recap_deck.py 2026-10-19          # -> data/recaps/recap_2026-10-19.pdf
python scripts/build_recap_deck.py 2026-10-19 --html   # also keep the HTML next to it
python scripts/build_recap_deck.py 2026-10-19 --dir path/to/exports --out path/to/pdfs
```

"How it works" deck for the README, refreshed from the latest game nights, benchmarks and rule counts:

```bash
python scripts/build_pitch_deck.py                     # -> docs/Pitch-Deck.pdf + docs/Pitch-Deck-Finance.pdf
python scripts/build_pitch_deck.py --theme finance     # one look only
```
The app serves them at `/how-it-works` and `/how-it-works/finance` (the lobby's "How It Works" button opens `/how-it-works` in a popup), so the short URL
stays valid when the PDFs are rebuilt.

## Linting

```bash
ruff check .
```
