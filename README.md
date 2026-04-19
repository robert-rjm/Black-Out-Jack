# BlackJack Game 🃏
_an AdHoc creation_

Welcome to _**Drinking BlackJack**_, a fun twist on classic BlackJack. It includes custom drinking game rules designed to add extra motivation and excitement to the traditional game of BlackJack. 

Play it digitally with an implementation in Python, use it as a real-life referee, or run it from your phone via a local web UI.

## 📑 Table of Contents
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
A worked example showing how multiple rules interact in one round is in [ComprehensiveExample.md](ComprehensiveExample.md).
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
This game is best enjoyed in good company and with good judgment. **Drink responsibly and know your limits**.

> _The goal is to have fun, not regrets._ 🍻

## <a id="installation"></a> 🚀 Installation & Setup

### 📁 **Project Structure**
```
Drinking-BlackJack/
├── BlackJack.py             # Main Game (START HERE)
├── Rules.md                 # Drinking Rules
├── drinking_rules.py        # Drinking rules layer
├── ComprehensiveExample.md  # Example for Drinking Rules
├── referee.py               # Terminal referee for real-life play
├── app.py                   # Flask web server (phone-friendly UI)
├── templates/
│   └── index.html           # Web UI served by app.py
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
python BlackJack.py
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
deal <player> <card> [hand<n>]        deal Rob Ah hand1
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
Run the web server and open it on any phone on the same WiFi network — or deploy it online for remote access.

```bash
python app.py
```

Then open `http://<your-PC-IP>:5000` on your phone. The terminal will print the exact URL on startup.

> ⚠️ The Flask dev server is not secure for public networks.
> Only use on trusted WiFi or deploy behind a proper web server.

Features tap-friendly modals for dealing cards, setting actions and results, plus a live drink log that highlights drinking events in real time.

## <a id="file-architecture"></a> 🏗️ File Architecture

The three main files are intentionally decoupled:

| File | Depends on | Purpose |
|---|---|---|
| `Blackjack.py` | nothing | Core game logic, standalone for normal BJ |
| `drinking_rules.py` | `Blackjack.py` | Drinking layer only, no game logic |
| `referee.py` | both | Real-life command parser |
| `app.py` | `referee.py`, `Blackjack.py` | Flask wrapper for web UI |

This means:
- **Changing a drinking rule** → edit only `drinking_rules.py`
- **Adding a game feature** → edit only `blackjack.py`
- **Adding a referee command** → edit only `referee.py`

---

## <a id="contributing"></a> 🤝 Contributing

Rule ideas are especially welcome — the best rules often come mid-game! Please:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

## <a id="development-status"></a> 🚧 Development Status

### **✅ Implemented**
- Basic BlackJack game structure
- Comprehensive drinking rules documentation
- Game setup and basic gameplay mechanics

### **🔄 Planned Features**
- Adjusted ruling to reward pushes more
- Adjusted game mechanics for a better fit for numerous players (n>4)

## <a id="license"></a> 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

*Happy Gaming! 🎰 May the cards be in your favor!*
