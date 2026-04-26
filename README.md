# BlackJack Game 🃏
_an AdHoc creation_

Welcome to _**Drinking BlackJack**_, a fun twist on classic BlackJack. It includes custom drinking game rules designed to add extra motivation and excitement to the traditional game of BlackJack. 

Play it digitally with an implementation in Python, use it as a real-life referee, or run it from your phone via a local web UI. You can choose between either **Referee** mode (physical deck, digital scorecard) or **Digital** mode (fully playable in-browser blackjack with a virtual shoe).

## <a id="quick-start"></a> ⚡ Quick Start
Requires Python 3.10+
```bash
git clone https://github.com/robert-rjm/Drinking-BlackJack.git && cd Drinking-BlackJack
pip install flask                # only needed for the web UI
python app.py                    # Web UI → http://localhost:5000
python blackjack.py              # Terminal game (no extra dependencies)
python referee.py                # Terminal referee for real-life play
```

## 📑 Table of Contents
- [Quick Start](#quick-start)
- [Features](#features)
- [Drink Responsibly](#drink-responsibly)
- [Installation & Setup](#installation)
- [Running the Game](#running-the-game)
- [File Architecture](#file-architecture)
- [Contributing](#contributing)
- [Development Status](#development-status)
- [License](#license)

---

## <a id="features"></a> ✨ Features

### 🎮 **Core Gameplay**
- **Classic BlackJack rules** with proper hand evaluation
  - **Goal**: Get as close to 21 as possible without going over
  - **Card Values**: Number cards = face value, Face cards = 10, Ace = 1 or 11
  - **Blackjack**: Ace + 10-value card in first 2 cards
  - **Bust**: Hand total exceeds 21 (automatic loss)
  - **Dealer Rules**: Must hit on 16 or less, stand on 17+
- **Player actions**: Hit, Stand, Double Down, Split
- **Player drinking incentives**: Beneficial deviations from optimal strategy
- **Smart dealer** that follows standard casino rules (hits until 17+)

### 🛠 **Special Rules**
- **Always split 10s** drinking motivation incentivizes this behavior
- **Ace split** simplification

### 🍺 **Extensive Drink Rules**
The full drinking ruleset is documented in [Rules.md](Rules.md).

To see how all these rules play out together in practice, check out [ComprehensiveExample.md](ComprehensiveExample.md). It walks through a full round step by step, covering ace deals, blackjack bonuses, net hand losses, sweeps, and suited-hand interactions.
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

### 🤖 NPC Players
Computer-controlled seats using standard basic strategy. NPCs:
- Never take insurance
- Follow basic strategy split/hit/stand/double decisions
- Fully participate in drinking rules
- Auto-distribute sip handouts round-robin
- Can hold the dealer role

## <a id="drink-responsibly"></a> ⚠️ Drink Responsibly
> [!IMPORTANT]
> This game is best enjoyed in good company and with good judgment.
> **Drink responsibly and know your limits**.
>
> _The goal is to have fun, not regrets._ 🍻

## <a id="installation"></a> 🚀 Installation & Setup

### 📁 **Project Structure**
```
Drinking-BlackJack/
├── blackjack.py             # Core game logic + terminal game (START HERE)
├── Rules.md                 # Drinking Rules
├── drinking_rules.py        # Drinking Rules
├── referee.py               # Terminal referee for real-life play
├── app.py                   # Flask web server (Referee & Digital modes)
├── templates/
│   └── index.html           # Web UI served by app.py
├── ComprehensiveExample.md  # Example for Drinking Rules
├── README.md
└── LICENSE
```

### 🔒 Rules Verification

`drinking_rules.py` contains a commit SHA and hash pinned to the version of `Rules.md` the implementation was verified against:

```python
__rules_source_commit__  = "7e4b344dfe1ade7e047bdef96310619a0533d4cd"
__rules_last_verified__  = "2026-04-11"
```

When the rules change, update these values after re-verifying the implementation.

### 🐛 Troubleshooting

**Common Issues**
1. **Inadequate Drinking Rules**: With too many players, excessive drinking may occur per round
2. **Insufficient Cards**: With multiple Players splitting aggressively, a single deck may run out. Consider using multiple decks for 4+ Players.

## <a id="running-the-game"></a> 🎮 Running the Game

### 1. Digital Game (Normal or Drinking)
Play Blackjack fully on your computer — the game deals cards, manages turns, and tracks drinks automatically.

```bash
python blackjack.py
```

At startup you choose:
- **Normal Blackjack** — standard game, no drinking rules
- **Drinking Blackjack** — full game with all drinking rules active

Supports 1–4 human/NPC players. One seat rotates as dealer every n rounds (where n = number of players). In single-player mode, the House acts as dealer.

### 2. Terminal Referee (Real-Life Play)
Playing with a physical deck? The referee script tracks drinks while you play in real life. You deal real cards, make real decisions — just tell the script what happened.

```bash
python referee.py
```

**Commands:**
```
deal <player> <card> [hand<n>]       deal Rob Ah hand1
action <player> <action> [hand<n>]   action Rob double hand1
result <player> <outcome> [hand<n>]  result Rob win hand1
result dealer bust
endround                             finalise round, print drink summary
newround [rotate]                    start next round
status                               show current hands
help                                 full command reference
```

**Card format:** `<rank><suit>` — e.g. `Ah` `10s` `Kd` `3c`

### 3. Web Referee (iPhone / Browser)
Run the Flask server and open it on any phone on the same WiFi network, or deploy it online for remote access.

```bash
python app.py
```

Then open `http://<your-PC-IP>:5000` on your phone. The terminal will print the exact URL on startup.

> [!WARNING]
> The Flask dev server is not secure for public networks.
> Only use on trusted WiFi or deploy behind a proper web server.

#### 🟦 Referee Mode
Use when playing with a **physical deck**. The app is a tap-friendly scorecard and drink tracker — you deal the real cards and tap in what happened.

**Setup fields:** players, dealer, sips/hand, hands/player.

**Tabs during play:**

| Tab | What it does |
|---|---|
| **Deal** | Select player + hand + rank + suit to register a card dealt |
| **Result** | Mark a hand WIN / LOSS / PUSH / BUST, or Dealer BUST |
| **Action** | Register DOUBLE, SPLIT, INSURANCE, BLACKJACK, or dealer final state |
| **Round** | END ROUND, NEW ROUND, STATUS, HELP, manual 4-Aces triggers |

#### 🟩 Digital Mode
A **fully playable** browser blackjack game — no physical deck needed. The app deals cards from a virtual shoe, manages all player turns, runs the dealer automatically, and fires all drinking rules.

**Setup fields:** players, dealer, sips/hand, hands/player, decks in shoe (1–8).

**Tabs during play:**

| Tab | What it does |
|---|---|
| **Deal** | Tap **DEAL CARDS** to deal opening cards to all hands from the shoe |
| **Play** | Select player + hand, then tap HIT / STAND / DOUBLE / SPLIT / INSURANCE / BLACKJACK |
| **Dealer** | Tap **RUN DEALER TURN** — reveals hole card, hits until 17+, evaluates all hands automatically |
| **Round** | END ROUND (fires drink summary), NEW ROUND (keep or rotate dealer), STATUS, HELP |

**Digital mode commands reference:**

```
deal                          Deal opening cards to all hands from the shoe
hit <player> [hand<n>]        Deal one card to that hand
stand <player> [hand<n>]      Mark the hand as stood
double <player> [hand<n>]     Double down — deal one card then stand
split <player> [hand<n>]      Split the hand, deal one card to each
insurance <player> [hand<n>]  Mark the hand as insured (when dealer shows Ace)
blackjack <player> [hand<n>]  Confirm a natural blackjack, fire drink rules
dealer                        Run the full dealer turn + auto-evaluate all hands
endround                      Fire end-of-round drink rules, print summary
newround [rotate]             Start a new round; 'rotate' passes the dealer role
status                        Show current state of all hands
help                          Full command reference
```

The shoe reshuffles automatically at the start of a new round if penetration is reached.

Both modes share the same drink-rule engine, live drink log (colour-coded by event type), and session persistence, reloading the page reconnects to the active session.

## <a id="file-architecture"></a> 🏗️ File Architecture

The three main files are intentionally decoupled:

| File | Depends on | Purpose |
|---|---|---|
| `blackjack.py` | nothing | Core game logic, card/hand/deck classes, terminal game |
| `drinking_rules.py` | `blackjack.py` | Drinking layer only, no game logic |
| `referee.py` | `blackjack.py`, `drinking_rules.py` | Terminal referee command parser for real-life play |
| `app.py` | `referee.py`, `blackjack.py`, `drinking_rules.py` | Flask server, Referee mode and Digital mode web UI |
| `templates/index.html` | served by `app.py` | Mobile-first browser UI for both modes |

**Separation of concerns:**
- **Changing a drinking rule** → edit only `drinking_rules.py`
- **Changing core game logic** → edit only `blackjack.py`
- **Adding a referee command** → edit only `referee.py`
- **Changing web UI behaviour or adding a digital command** → edit `app.py` and/or `templates/index.html`

---

## <a id="contributing"></a> 🤝 Contributing

Rule ideas are especially welcome — if it made the game more fun, it probably belongs here! Please:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

## <a id="development-status"></a> 🚧 Development Status

### **✅ Implemented**
- Basic BlackJack game structure
- Comprehensive drinking rules documentation
- Terminal game with normal and drinking modes
- Terminal referee for real-life play
- Web UI with Referee mode (physical deck scorecard)
- Web UI with Digital mode (full in-browser blackjack with virtual shoe)

### **🔄 Planned Features**
- Adjusted ruling to reward pushes more
- Adjusted game mechanics for a better fit for numerous players (n>4)

## <a id="license"></a> 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Happy Gaming! 🎰 May the cards be in your favor!*
