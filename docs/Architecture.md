# Architecture

Technical documentation for **Black(Out)Jack**: project structure, file dependencies, simulation, and development guide

---

## Table of Contents
- [Project Structure](#project-structure)
- [File Dependencies](#file-dependencies)
- [Separation of Concerns](#separation-of-concerns)
- [Rules Verification](#rules-verification)
- [Simulation & Statistics](#simulation--statistics)
- [Common Issues](#common-issues)
- [Development Guide](#development-guide)

---

## Project Structure

```
Black-Out-Jack/
├── app/
│   ├── config.py                # App-wide constants and feature flags
│   ├── models/
│   │   └── game_room.py         # Typed room-state container
│   ├── routes/
│   │   ├── lobby.py             # Room creation, joining, setup
│   │   ├── polling.py           # Long-poll state sync + milestone forfeit
│   │   ├── game_commands.py     # Referee & digital game commands
│   │   └── admin.py             # Dealer rotation, milestone claim, kick
│   └── services/
│       ├── game_engine.py       # Digital mode card/turn logic
│       ├── drink_tracker.py     # Sip harvesting, milestones, bust votes
│       ├── room_manager.py      # Tracker patching, dealer rotation helpers
│       └── session_store.py     # In-memory room store
├── docs/
│   ├── Rules.md                 # Drinking Rules
│   ├── Cheat-Sheet.md           # One-page quick reference for gameplay
│   ├── Comprehensive-Example.md # Example for Drinking Rules
│   ├── Architecture.md          # This file
│   ├── Multiplayer.md           # Full multiplayer documentation
│   ├── DOM-Hooks.md             # Frontend element IDs and JS hook reference
│   ├── TODO.md                  # Known issues and planned features
│   ├── backend_refactor_map.svg # Backend dependency diagram
│   └── frontend_refactor_map.svg# Frontend dependency diagram
├── static/
│   ├── css/
│   │   ├── main.css             # Variables, reset, layout, bottom nav
│   │   └── components/          # controls.css, kpi.css, lobby.css, log.css, modals.css, table.css, tabs.css, utilities.css
│   ├── js/
│   │   ├── utils.js             # Shared helpers
│   │   ├── state.js             # Global state variables
│   │   ├── app.js               # Init entry point
│   │   └── ui/                  # lobby.js, setup.js, animation.js, config.js, bootstrap.js
│   │                            # table.js, table-modals.js, table-render.js
│   │                            # log.js, kpi.js, admin.js, admin-settings.js
│   └── Logo-BlackOutJack.png    # App logo and home screen icon (iOS & Android)
├── templates/
│   ├── index.html               # Mobile-first browser UI
│   └── partials/index/*.html    # Composable UI sections
│
├── engine/                      # Core game library
│   ├── __init__.py
│   ├── blackjack.py             # Card/hand/deck classes, game loop, NPC logic
│   ├── strategy.py              # Basic strategy lookup tables + best_play()
│   ├── drinking_rules.py        # Drinking layer — reacts to game events
│   └── referee.py               # RefereeSession class for real-life play
├── scripts/                     # Standalone CLI tools
│   ├── __init__.py
│   └── simulation.py            # 10,000-round NPC simulation, outputs CSV + txt
├── server.py                    # Flask entry point
├── blackjack.py                 # Entry-point shim → engine/blackjack.py (START HERE)
├── referee.py                   # Entry-point shim → engine/referee.py
├── simulation.py                # Entry-point shim → scripts/simulation.py
├── requirements.txt             # Python dependencies for deployment
├── .gitignore
├── .flake8                      # Flake8 linting config (max-line-length 120)
├── README.md
└── LICENSE
```

## File Dependencies

The main files are intentionally decoupled:

| File | Depends on | Purpose |
|---|---|---|
| `engine/strategy.py` | nothing | Basic strategy lookup tables + `best_play()` resolver |
| `engine/blackjack.py` | `engine/strategy.py` | Core game logic, card/hand/deck classes, game loop |
| `engine/drinking_rules.py` | `engine/blackjack.py` | Drinking layer only, no game logic |
| `engine/referee.py` | `engine/blackjack.py`, `engine/drinking_rules.py` | RefereeSession for real-life play |
| `scripts/simulation.py` | `engine/blackjack.py`, `engine/drinking_rules.py` | 10,000-round NPC simulation, outputs CSV + txt |
| `server.py` | `app/` package | Flask entry point; creates the app and registers blueprints |
| `app/` | `engine/` | Routes, models, and services for the web UI |
| `blackjack.py` / `referee.py` / `simulation.py` | `engine/` or `scripts/` | Thin root shims — preserve `python <name>.py` CLI ergonomics |
| `templates/index.html` + `templates/partials/index/*` | served by `server.py` | Mobile-first browser UI (responsive, PWA) |
| `static/css/` | — | `main.css` (layout, variables) + `components/` (cards, controls, log…) |
| `static/js/` | — | `utils.js`, `state.js`, `app.js` + `ui/` (lobby, log, setup, table, table-modals, table-render, kpi, trivia, admin, admin-settings) |

## Separation of Concerns
- **Changing a drinking rule** → edit only `engine/drinking_rules.py`
- **Changing core game logic** → edit only `engine/blackjack.py`
- **Changing basic strategy** → edit only `engine/strategy.py`
- **Adding a referee command** → edit only `engine/referee.py`
- **Changing web routes or server logic** → edit `app/routes/` or `app/services/`
- **Changing web UI behaviour** → edit `static/js/ui/` and/or `templates/index.html`
- **Changing styles** → edit `static/css/main.css` or the relevant `static/css/components/` file


## Rules Verification

`engine/drinking_rules.py` contains a SHA256 hash and date pinned to the version of `Rules.md` the implementation was verified against:

```python
_RULES_HASH  = "1d0d65ff..."
_RULES_DATE  = "2026-05-15"
```

**How it works:**

1. On startup the script fetches `Rules.md` from GitHub and compares hashes
2. If they differ, a warning is printed to the console.
3. When the rules change, update `_RULES_HASH` and `_RULES_DATE` in `engine/drinking_rules.py`.

This ensures the code and documentation never silently drift apart.


## Simulation & Statistics

Curious whether the rules are balanced or which rule is responsible for most of the drinking?

Track every drink event from start to finish in a simulation (3 players, 2 hands each, rotating dealer). Frequency and rule breakdown are output in `simulation_results.txt` and `simulation_log.csv` respectively.

```bash
python simulation.py
```

## Common Issues

| **Problem** | **Cause** | **Solution** |
|---|---|---|
| **Insufficient Cards** | Multiple players splitting aggressively | Use multiple decks (auto enabled for 4+ players) |
| **Large groups** | More players trigger more rules, sips add up | Games with 4 or more players automatically halve all end-of-round sip totals |


## Development Guide

### Prerequisites
- Python 3.10+
- `flask` (for web UI)
- No other dependencies for terminal play
- Consult [requirements.txt](requirements.txt)

### Running locally
```bash
# Web UI
python server.py                 # → http://localhost:5000

# Terminal game
python blackjack.py              # No extra dependencies (shim calls engine/)

# Referee mode
python referee.py                # Physical deck, digital tracking

# Simulation
python simulation.py             # Outputs to simulation_results.txt
```

### Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

Rule ideas are especially welcome — if it made the game more fun, it probably belongs here!
