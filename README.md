# BlackJack Game 🃏
_an AdHoc creation_

Welcome to _**Black(Out)Jack**_, a multiplayer browser-based blackjack card game with a drinking party game twist. It includes custom drinking game rules designed to add extra motivation and excitement to the traditional game of BlackJack.

Play it digitally in your browser, use it as a real-life referee, or run it via a local web UI. No account needed. It supports human and NPC players across **Referee** mode (physical deck, digital scorecard) and **Digital** mode (fully playable in-browser blackjack).

## Quick Start
**Play online instantly, no install or account needed:** [Black-Out-Jack.onrender.com](https://black-out-jack.onrender.com)

**Or run locally:**
Requires Python 3.10+
```bash
git clone https://github.com/robert-rjm/Black-Out-Jack.git
cd Black-Out-Jack
pip install flask                # only needed for the web UI
python server.py                 # Web UI → http://localhost:5000
python engine/blackjack.py       # Terminal game (no extra dependencies)
python engine/referee.py         # Terminal referee for real-life play
```

## Table of Contents
- [Quick Start](#quick-start)
- [Features](#features)
- [Drink Responsibly](#drink-responsibly)
- [Installation & Setup](#installation--setup)
- [Running the Game](#running-the-game)
- [Simulation & Statistics](#simulation--statistics)
- [File Architecture](#file-architecture)
- [Contributing](#contributing)
- [License](#license)
- [Credits](#credits)

---

## Features

### **Core Gameplay**
- **Classic BlackJack rules** with proper hand evaluation
  - **Goal**: Get as close to 21 as possible without going over
  - **Card Values**: Number cards = face value, Face cards = 10, Ace = 1 or 11
  - **Blackjack**: Ace + 10-value card in first 2 cards
  - **Bust**: Hand total exceeds 21 (automatic loss)
  - **Dealer Rules**: Must hit on 16 or less, stand on 17+ (also soft-17)
- **Player actions**: Hit, Stand, Double Down, Split
- **Player drinking incentives**: Beneficial deviations from optimal strategy
- **Smart dealer** that follows standard casino rules (hits until 17+)

### **Special Rules**
- **Always split 10s** drinking motivation incentivizes this behavior
- **Ace split** simplification

### **Extensive Drink Rules**

The full drinking ruleset is documented in [Rules.md](docs/Rules.md).

For a one-page reference during gameplay, see [Cheat-Sheet.md](docs/Cheat-Sheet.md).

To see how all these rules play out together in practice, check out [Comprehensive-Example.md](docs/Comprehensive-Example.md).

> [!TIP]
> These rules are not set in stone, the best rules often come mid-game!
>
> Players are encouraged to come up with new rule ideas as they play. If they make the game more fun, they are probably worth keeping!

#### Highlights
| Rule | Details |
|---|---|
| **Ace dealt rules** | each suit triggers a different drinking effect (immediate) |
| **Blackjack bonus** | cumulative ×2 multipliers for suited / Ace+Jack / both black |
| **Net hand losses** | wins offset losses; only net negatives cost sips |
| **Other-player sweeps** | tiered immunity system |
| **Suited winning hand** | 1 sip (4 if doubled/split) |
| **5+ card hands** | hand out sips for 21 with 5+ cards; all others drink for a 5+ card win |
| **Four Aces** | 2 sips after first deal, 1 sip at end of round (non-stacking) |
| **Dealer suited hand** | 2 sips for all players |
| **Hard Dealer Switch** | dealer drinks per each winning hand when they lose all |
| **Mandatory 10 splits** | warning issued when a player tries to keep 10-value pairs (unless suited) |

#### Ace of Clubs — Dealer-Player Special Case

When the **dealer-player** (the player currently holding the dealer role) receives A♣ on one of their own **player hands** (not their dealer hand), the effect depends on whether a Hard Switch fires that round:

- **Hard Switch fires** → partial protection only: the dealer-player's own hand losses are exempt from the Hard Switch dealer penalty. No -1 sip credit is awarded (protection IS the benefit — no double-dipping).
- **No Hard Switch** → standard A♣ treatment: the dealer-player receives the normal -1 sip credit at end of round, same as any other player.

This replaces the previous behaviour where both benefits applied simultaneously.

### **Multiplayer Rooms**
- **Room codes** — host creates a room and shares the code (e.g. `Jack-21`) with friends
- **Player registration** — each person joins on their own phone and claims their seat
- **Role system** — rotating dealer (controls the game); others vote their intended action and the dealer executes it
- **Action voting** — non-dealer players tap HIT/STAND/DOUBLE/SPLIT to signal their intention; the dealer sees the vote and carries it out
- **Live sip ticker** — header strip shows the session total; each player seat shows their running sip count
- **Milestone handouts** — when a player's cumulative sip total crosses a multiple of 50, they hand out bonus sips to others (5 sips at the 50-sip boundary, 6 at 100, 7 at 150, and so on — +1 per additional milestone).
- **KPI panel** — right-column panel with three tabs:
  - **Leaderboard** — win rate, W/L/P, current streak, sips per player
  - **Stats** — session banner (avg sips/round with L3/L5/L10 rolling trend, total sips, sips/min, duration), per-player table (blackjacks, double/split win rate, hit rate, busts, suited hands, strategy accuracy, avg and peak sips, streak records)
  - **Trivia** — rotating blackjack & drinking facts with a "Next fact" button; planned phase 2 will surface reactive facts based on game events (ace dealt, dealer busts, player blackjack, etc.) *(coming soon: reactive mode)*
- **Strategy accuracy tracking** — every hit/stand/double/split by a human player is compared against basic strategy; accuracy % shown in the Stats tab after 3+ decisions (green ≥80%, yellow ≥60%, red below)
- **Clean-round crown** — players who took 0 sips in the previous round display a 👑 next to their name for the following round
- **Collapsible round log** — log panel can be minimised to free screen space for the KPI panel
- **Spectator mode** — join a session without a seat to watch
- **Player management** — admin can kick players from the session

### **NPC Players**
Computer-controlled seats using standard basic strategy. NPCs:
- Never take insurance
- Follow basic strategy split/hit/stand/double decisions
- Fully participate in drinking rules
- Auto-distribute sip handouts round-robin
- Can hold the dealer role, cards are dealt automatically when an NPC is dealer

### **Mobile & PWA**
- Mobile-first layout optimised for phone screens
- Bottom navigation bar on mobile (≤640 px) for one-thumb reach
- Add to home screen on iOS and Android for a native app feel
- Tap-friendly controls throughout

## Drink Responsibly
> [!IMPORTANT]
> This game is best enjoyed in good company and with good judgment.
> **Drink responsibly and know your limits**.
>
> _The goal is to have fun, not regrets._ 🍻

## Installation & Setup

### **Project Structure**
```
Black-Out-Jack/
├── app/
│   ├── models/
│   │   └── game_room.py         # Typed room-state container
│   ├── routes/                  # Flask blueprints (commands, events, rooms…)
│   └── services/                # Game engine, drink logic, NPC, etc.
├── docs/
│   ├── Rules.md                 # Drinking Rules
│   ├── Cheat-Sheet.md           # One-page quick reference for gameplay
│   ├── Comprehensive-Example.md # Example for Drinking Rules
│   └── Multiplayer.md           # Full multiplayer documentation
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
│   └── logo.png                 # Home screen icon (iOS & Android)
├── templates/
│   ├── index.html               # Mobile-first browser UI
│   └── partials/index/*.html    # Composable UI sections
│
├── server.py                    # Flask entry point
├── blackjack.py                 # Core game logic + terminal game (START HERE)
├── strategy.py                  # Basic strategy tables + best_play() resolver
├── drinking_rules.py            # Drinking Rules
├── referee.py                   # Terminal referee for real-life play
├── simulation.py                # Round simulation with stats output
├── requirements.txt             # Python dependencies for deployment
├── .gitignore
├── README.md
└── LICENSE
```

### Rules Verification

`drinking_rules.py` contains a SHA256 hash and date pinned to the version of `Rules.md` the implementation was verified against:

```python
_RULES_HASH  = "1d0d65ff..."
_RULES_DATE  = "2026-05-15"
```

On startup the script fetches `Rules.md` from GitHub and compares hashes. If they differ, a warning is printed. When the rules change, update `_RULES_HASH` and `_RULES_DATE` in `drinking_rules.py` after re-verifying the implementation.

### Common Issues
1. **Insufficient Cards**: With multiple players splitting aggressively, it is recommended to use multiple decks (the game defaults to 2 decks for 4+ players automatically).
2. **Large groups**: Games with 4 or more players automatically halve all end-of-round drink totals per player to keep the game at a reasonable pace.

## Running the Game

| Mode | Command | Description |
|------|---------|-------------|
| Digital Game | `python engine/blackjack.py` | Fully playable in terminal (normal or drinking) |
| Terminal Referee | `python engine/referee.py` | Physical deck, digital scorecard |
| Web UI | `python server.py` or [play online](https://black-out-jack.onrender.com)| Browser-based (referee or digital mode) |

### 1. Digital Game (Normal or Drinking)
Play Blackjack fully on your computer, deals cards, manages turns, and tracks drinks automatically.

```bash
python engine/blackjack.py
```

Choose between **Normal Blackjack** (standard game, no drinking rules) or **Drinking Blackjack** (full game with all drinking rules active). Supports 1-4 human or NPC players with rotating dealer.

### 2. Terminal Referee (Real-Life Play)
Playing with a physical deck? The referee script tracks drinks while you play in real life. You deal real cards, make real decisions, just tell the script what happened.

```bash
python engine/referee.py
```

**Commands:** `deal`, `action`, `result`, `endround`, `newround`, `status`, `help`

**Card format:** `<rank><suit>`: e.g. `Ah` `10s` `Kd` `3c`. Type `help` in-game for full reference.

### 3. Web UI (Browser / Online)
Run it locally or play online.

**Play online:** [Black-Out-Jack.onrender.com](https://black-out-jack.onrender.com)

**Or run locally**
```bash
python server.py
```

Then open `http://<your-PC-IP>:5000` on your phone. The terminal will print the exact URL on startup.

> [!WARNING]
> The Flask dev server is not secure for public networks.
> Only use on trusted WiFi or deploy behind a proper web server.

| Mode | Description |
|------|-------------|
| **Referee** | Tap-friendly scorecard for physical deck play. Register deals, actions, and results. |
| **Digital** | Fully playable browser blackjack with virtual shoe (1–8 decks). |

Both modes share the same drink-rule engine, live drink log (colour-coded by event type), and session persistence, reloading the page reconnects to the active session.

#### Multiplayer setup
1. Host opens the app and creates a room, a short code (e.g. `Jack-21`) is shown
2. Each player opens the same URL on their phone and enters the code to join
3. Everyone claims their seat by tapping their name
4. The host (dealer) starts the game and controls the flow; other players vote their actions and the dealer executes them
5. When an NPC holds the dealer role, cards are dealt and turns are resolved automatically

#### Installing to home screen
On **iOS**: tap the Share button in Safari → "Add to Home Screen"
On **Android**: tap the browser menu → "Add to Home Screen" or "Install app"

## Simulation & Statistics

Curious whether the rules are balanced or which rule is responsible for most of the drinking?

Track every drink event from start to finish in a simulation (3 players, 2 hands each, rotating dealer). Frequency and rule breakdown are output in `simulation_results.txt` and `simulation_log.csv` respectively.

```bash
python scripts/simulation.py
```

## File Architecture

The three main files are intentionally decoupled:

| File | Depends on | Purpose |
|---|---|---|
| `strategy.py` | nothing | Basic strategy lookup tables + `best_play()` resolver |
| `blackjack.py` | `strategy.py` | Core game logic, card/hand/deck classes, terminal game |
| `drinking_rules.py` | `blackjack.py` | Drinking layer only, no game logic |
| `referee.py` | `blackjack.py`, `drinking_rules.py` | Terminal referee command parser for real-life play |
| `server.py` | `app/` package | Flask entry point; creates the app and registers blueprints |
| `app/` | `referee.py`, `blackjack.py`, `drinking_rules.py` | Routes, models, and services for the web UI |
|  `templates/index.html` + `templates/partials/index/*` | served by `server.py` | Mobile-first browser UI (responsive, PWA) |
| `static/css/` | — | `main.css` (layout, variables) + `components/` (cards, controls, log…) |
| `static/js/` | — | `utils.js`, `state.js`, `app.js` + `ui/` (lobby, log, setup, table, table-modals, table-render, kpi, trivia, admin, admin-settings) |
| `simulation.py` | `blackjack.py`, `drinking_rules.py` | 10,000-round NPC simulation, outputs drink statistics |

**Separation of concerns:**
- **Changing a drinking rule** → edit only `drinking_rules.py`
- **Changing core game logic** → edit only `blackjack.py`
- **Changing basic strategy** → edit only `strategy.py`
- **Adding a referee command** → edit only `referee.py`
- **Changing web routes or server logic** → edit `app/routes/` or `app/services/`
- **Changing web UI behaviour** → edit `static/js/ui/` and/or `templates/index.html`
- **Changing styles** → edit `static/css/main.css` or the relevant `static/css/components/` file

## Contributing

Rule ideas are especially welcome — if it made the game more fun, it probably belongs here! Please:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

## License

[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc-sa/4.0/)

This project is licensed under CC BY-NC-SA 4.0. See [LICENSE](LICENSE) for details.

## Credits

Game concept & rules: R. Michels, D. Irrgang, M. Cvijic
Development: R. Michels

---

*Happy Gaming! 🎰 May the cards be in your favor!*
                                                                                                                                                                                                                                      