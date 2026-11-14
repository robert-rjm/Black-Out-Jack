# Dev Cheat Sheet

Dev commands. Game rules are in [Cheat-Sheet.md](Cheat-Sheet.md), script internals in
[Architecture.md](Architecture.md).

## Run the game

```bash
python server.py                             # web UI at http://localhost:5000
python scripts/play_terminal.py              # Terminal game
python scripts/play_referee.py               # Referee mode (real deck, digital scorecard)
```

## Tests and lint

```bash
pytest                                       # everything
pytest -m "not slow"                         # Fast suite
pytest -m slow                               # Full 100k-round snapshot diff
pytest tests/engine/test_style_strategy.py   # specific file
ruff check .
```

## After changing something

| You changed | Run |
|---|---|
| Sip rules (`engine/drinking_rules.py`, `engine/blackjack.py`) and `test_regression_snapshots` fails | `python scripts/run_all_configs.py --snapshot baseline`, then `pytest` |
| `docs/Rules.md` or `engine/drinking_rules.py` and `test_rules_doc_sync` fails | `python scripts/rules_sync.py update` (only after checking doc and code agree) |

## Simulations and baselines

The simulation plays 100k rounds and records how often each sip rule fires.

- **Benchmarks** (`scripts/benchmarks.json`, `static/js/benchmarks.js`): the latest results. The app compares live games to them.
- **Baseline** (`scripts/snapshots/<N>p/<D>deck/baseline_<N>p_<D>d/`): a saved copy of the benchmarks. The regression test checks a short simulation against it.

Change the rules on purpose and the test fails, because the baseline is stale. Refresh it:

```bash
python scripts/run_all_configs.py --snapshot baseline
```

That runs every config (2-4 players, 1-4 decks, 12 runs, slow) and overwrites the baselines.
To refresh only the three the test uses:

```bash
python scripts/run_all_configs.py --snapshot baseline --players 2 3 --decks 1
python scripts/run_all_configs.py --snapshot baseline --players 4 --decks 2
```

Other commands:

```bash
python scripts/simulation.py 4 2                       # one config (4 players, 2 decks); updates benchmarks only, not baselines
python scripts/simulation.py                           # same, but asks for players/decks
python scripts/run_all_configs.py                      # all configs, no baselines
python scripts/run_all_configs.py --compare baseline   # report what moved vs. the baseline, changes nothing
python scripts/compare_configs.py                      # table of all simulated configs
python scripts/simulation.py 2 1 && python scripts/snapshot.py baseline_2p_1d --overwrite   # one baseline by hand
```

Baseline folders must be named `baseline_<N>p_<D>d` or the test won't find them.

## Player bots (rob, marko, david)

Bots that copy how real players deviate from basic strategy.

1. Play, then download the session workbook from the summary modal ("Developer data").
   It's `session_data_<day>.xlsx`; save it in `data/decisions/`. Older `drinks_summary_*` /
   `decision_log_*` files in the same folder still work, but are ignored for any day that has a
   `session_data_*` file.
2. Optional, peek at the data:
   ```bash
   python scripts/load_decision_logs.py [--player Rob] [--out data/decisions/combined.csv]
   ```
3. Build the profiles (written to `engine/player_profiles/`):
   ```bash
   python scripts/build_player_profiles.py --merge                               # normal update; keeps earlier sessions
   python scripts/build_player_profiles.py                                       # rebuild existing profiles from the files in the folder only
   python scripts/build_player_profiles.py --player NewGuy                       # new player (asks first, --yes skips)
   python scripts/build_player_profiles.py --min-samples 3 --min-majority 0.60   # tune thresholds
   ```
4. Simulate with them:
   ```bash
   python scripts/simulation.py --personalities rob marko david
   python scripts/simulation.py 3 2 --personalities rob marko david
   ```
   Player count comes from the number of names. Output goes to `simulation_results_personas.txt`
   and leaves the benchmarks alone.
5. Compare against basic strategy on identical shoes:
   ```bash
   python scripts/compare_bot_styles.py [--personalities rob marko] [--decks 2] [--rounds 100000] [--seed 7]
   ```

## Exports

```
GET /export_session?room_code=<code>    # session workbook (drinks + decisions)
GET /export_xlsx?room_code=<code>       # old: drinks only
GET /export_decisions?room_code=<code>  # old: decisions only
GET /summary_json?room_code=<code>      # drink summary as JSON
GET /recap_html?room_code=<code>        # recap deck as HTML slides
```

Recap deck as PDF from a saved export (needs Edge or Chrome):

```bash
python scripts/build_recap_deck.py 2026-10-19          # -> data/recaps/recap_2026-10-19.pdf
python scripts/build_recap_deck.py 2026-10-19 --html   # keep the HTML too
python scripts/build_recap_deck.py 2026-10-19 --dir path/to/exports --out path/to/pdfs
```

"How it works" decks (pull in the latest game nights, benchmarks and rule counts):

```bash
python scripts/build_pitch_deck.py                  # docs/Pitch-Deck.pdf + docs/Pitch-Deck-Finance.pdf
python scripts/build_pitch_deck.py --theme finance  # one theme only
```

Served at `/how-it-works` and `/how-it-works/finance`, so the URLs survive a rebuild.
