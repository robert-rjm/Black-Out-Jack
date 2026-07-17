# Multiplayer Rooms

**Black(Out)Jack** supports real-time multiplayer sessions, where friends play together on their own devices. This document covers every multiplayer feature in detail.

---

## Table of Contents
- [Getting Started](#getting-started)
- [Room Codes & Joining](#room-codes--joining)
- [Role System & Dealer Rotation](#role-system--dealer-rotation)
- [Action Voting](#action-voting)
- [Dealer Suggestions](#dealer-suggestions)
- [Live Sip Tracking](#live-sip-tracking)
- [Milestone Handouts](#milestone-handouts)
- [Dealer Bust Vote](#dealer-bust-vote)
- [Dealer Lottery](#dealer-lottery)
- [Targeted Drinking Mode](#targeted-drinking-mode)
- [Easy Mode](#easy-mode)
- [KPI Panel](#kpi-panel)
- [Strategy Accuracy](#strategy-accuracy)
- [Clean-Round Crown](#clean-round-crown)
- [NPC Players](#npc-players)
- [Spectator Mode](#spectator-mode)
- [Player Management](#player-management)
- [UI & Layout](#ui--layout)

---

## Getting Started

1. **Host** opens the app and creates a room — a short code (e.g. `Jack-21`) is displayed
2. **Players** open the same URL on their phone and enter the code to join
3. Everyone **claims their seat** by tapping their name
4. The host (dealer) **starts the game** and controls the flow
5. Other players **vote their actions**; the dealer executes them

---

## Room Codes & Joining

- The host creates a room and receives a shareable room code
- Any player on the same network (or online) can join by entering the code
- No accounts or sign-ups required
- Session persists across page reloads — reconnecting restores your seat

---

## Role System & Dealer Rotation

- One player holds the **dealer role** at any time
- The dealer controls the pace: dealing cards, advancing turns, and ending rounds
- The dealer role **rotates** after each round
- When an **NPC** holds the dealer role, cards are dealt and turns are resolved automatically

---

## Action Voting

Non-dealer players don't directly control the game — instead they **signal their intent**:

- Each player taps **HIT**, **STAND**, **DOUBLE**, or **SPLIT** on their device
- The dealer sees all votes in real-time
- The dealer then executes the chosen action on behalf of each player
- This keeps one person in control of pacing while everyone participates actively

---


## Dealer Suggestions

The dealer can **suggest a different action** to any player before executing their voted move.

- The player sees the suggestion and can **Accept** or **Decline**
- Useful when the dealer spots a better play (e.g. suggesting STAND when a player voted HIT on a 18)
- If declined, the player's original vote stands and the dealer executes it
- Suggestions are per-hand — a split hand can receive a different suggestion for each sub-hand

---

## Live Sip Tracking

- A **header strip** displays the session's total sip count
- Each **player seat** shows their individual running sip total
- Updates happen in real-time as drinking rules trigger

---

## Milestone Handouts

When a player's cumulative sip total crosses a **multiple of 50**, they earn bonus sips to distribute:

| Milestone | Sips to hand out |
|-----------|-----------------|
| 50 sips | 5 |
| 100 sips | 6 |
| 150 sips | 7 |
| 200 sips | 8 |
| … | +1 per additional milestone |

### Rules
- The winner has **60 seconds** to distribute the sips among other players
- **Unassigned sips** come back to the winner
- If the **timer expires** without a submission, the full handout becomes the winner's own drink
- Only **one milestone** can be active at a time — a new boundary won't fire until the current handout is resolved

### "Worst Average" Penalty

At each milestone, the player with the **lowest average sips/round overall** (total sips ÷ rounds played, excluding the milestone winner) is flagged as the "worst" player.

- If the **same player** is flagged as worst for **two milestones in a row**, they take a **one-time penalty**: drink a number of sips equal to the milestone **winner's average sips/round** (rounded, minimum 1).
- After the penalty fires, the streak resets — they need to be "worst" two more times in a row to trigger it again.

---

## Dealer Bust Vote

Before the dealer reveals their hand, players can predict whether the dealer will **bust**.

### How it works
- Each player taps **Bust** or abstains — abstaining has no consequence
- Once the dealer plays out their hand, votes are resolved:
  - **Correct** (dealer busted): −1 sip credit + 1 sip to hand out to another player (20-second window)
  - **Wrong** (dealer didn't bust): +1 sip penalty

### Rules
- Only players who voted are affected — abstainers skip the round entirely
- The −1 credit offsets one of your own sips from that round (net result of a correct call is 0 or positive)
- Bust voting can be toggled on or off by the admin in settings

---

## Dealer Lottery

If the Dealer's final hand happens to be a **paired 18** (two 9s) or **paired 20** (any two ten-value cards), every player gets a shot at a bonus split redeal.

### How it works
- Each player picks a stake **X = 0-5** (20-second window; no answer defaults to 0)
- If everyone picks 0, nothing happens — no draw, nothing logged
- Otherwise the dealer's pair splits into fresh hands from a new shuffled deck, played out under the normal dealer-hits-to-17 rule — shown as a real card-by-card reveal animation. If a new card itself forms another matching pair, that hand splits again the same way a player's hand would (same 4-splits cap), so a hot run of 9s or tens can turn this into three or more hands
- **2 or more hands bust** (not necessarily all of them): credit yourself up to X sips off what you owe this round, and hand X sips out to another player (picker window mirrors the Bust Vote's)
- **Exactly 1 hand busts**: nothing happens
- **No hand busts**: drink X × (hands − 1) — scales with how many hands the redeal produced, so a re-split costs more to stand clean through, not just easier to credit off of. Never halved regardless of player count or Easy Mode (only the bust handout scales with those)

### Rules
- The dealer is eligible to enter too, same as the Bust Vote
- Every entry (yours or an NPC's) is recorded and can be mined into that player's bot profile — see [Architecture.md](Architecture.md) for `scripts/build_player_profiles.py`

---

## Targeted Drinking Mode

The host can single out one or more players and drop them into their own standalone mini-game, played between normal rounds, until they clear it or the host cancels it.

### How it works
- Host picks target(s) from **Settings → Players** and taps **Start Targeted Drinking** — or ends it early any time with the ✕ in the corner of the mini-game modal itself, no trip through Settings required
- Once a normal round ends, the mini-game deals a fresh, isolated dealer-only hand — a new shuffled deck, unrelated to the real table — and every targeted player gets a 15-second window to call **BUST** or **STAND** on it before it's dealt; no answer defaults to STAND
- The moment every targeted player has voted, the round resolves immediately — it never waits out the rest of the timer
- One modal covers the whole mini-round: it opens on the vote and turns straight into the card-by-card reveal in place once voting's done, the same way a Dealer Lottery redeal plays out. Targeted players see BUST/STAND buttons; everyone else watches a read-only view of who's targeted and what they called, live, as votes come in and cards land
- Call it right 3 times in a row and you're released; call it wrong and your streak resets to 0, plus a 1-sip penalty
- If the mode is still running once a mini-hand resolves, the next one starts right away (back-to-back) after a short pause — it does **not** wait for another normal round to be played first
- Once every targeted player has been released, a 3-round cooldown starts before the host can start it again

### Rules
- Admin-only to start or cancel — see [Rules.md](Rules.md#510-targeted-drinking-mode) for the full rule. The host's ✕ in the mini-game modal ends the whole thing on the spot; anyone else's ✕ just dismisses their own view of the current mini-round
- Starting it mid-round never interrupts play — the first mini-round waits for the current round to end
- Between mini-rounds (mode active but no vote/reveal in progress), everyone sees a small status banner instead of the modal

---

## Easy Mode

**Easy Mode** halves all end-of-round drinks (rounded up) for every player, every round — the same mechanic as the automatic [Large Group Rule](Rules.md#large-group-rule-4-players) but available to any group size.

- **Setup:** toggle it on in the setup screen before starting the game
- **Mid-game:** the host can toggle it in admin settings; takes effect from the next round
- **4+ players:** Easy Mode is locked ON — the Large Group Rule already covers it

---

## KPI Panel

The right-column panel contains three tabs:

### 📊 Leaderboard
- Win rate
- W / L / P record
- Current streak
- Sips per player

### 📈 Stats
**Session banner:**
- Average sips/round with L3 / L5 / L10 rolling trend
- Total sips
- Sips per minute
- Session duration

**Per-player table:**
- Blackjacks
- Double/split win rate
- Hit rate
- Busts
- Suited hands
- Strategy accuracy (see below)
- Average and peak sips
- Streak records

### 🎲 Trivia
- Rotating blackjack & drinking facts
- "Next fact" button to cycle through
- *(Coming soon: reactive mode — facts triggered by game events like aces dealt, dealer busts, or player blackjacks)*

---

## Strategy Accuracy

Every **hit/stand/double/split** decision by a human player is compared against basic strategy:

- Accuracy % is shown in the Stats tab after **3+ decisions**
- Colour coding:
  - 🟢 Green: ≥ 80%
  - 🟡 Yellow: ≥ 60%
  - 🔴 Red: < 60%

This helps players learn optimal play over time without being prescriptive during the game.

---

## Clean-Round Crown 👑

Players who took **0 sips** in the previous round display a 👑 next to their name for the following round. A small badge of honour (or target on their back).

---

## NPC Players

Computer-controlled seats using standard basic strategy. NPCs:

- Never take insurance
- Follow basic strategy for split/hit/stand/double decisions
- Fully participate in all drinking rules
- Auto-distribute sip handouts (round-robin)
- Can hold the dealer role — when they do, cards are dealt and turns resolve automatically

---

## Spectator Mode

- Join a session **without claiming a seat** to watch the game unfold
- Spectators see the full game state, log, and KPI panel
- Useful for latecomers or people who want to watch before jumping in

---

## Player Management

- The **admin** (host) can kick players from the session
- Kicked players can rejoin with the room code unless blocked

---

## UI & Layout

### Mobile-First Design
- Optimised for phone screens (touch targets, readable text, minimal scrolling)
- **Bottom navigation bar** on mobile (≤ 640 px) for one-thumb reach
- Tap-friendly controls throughout

### PWA Support
- Add to home screen on **iOS** (Share → "Add to Home Screen") and **Android** (menu → "Add to Home Screen" or "Install app")
- Launches in standalone mode for a native app feel

### Collapsible Round Log
- The log panel can be minimised to free screen space for the KPI panel
- Colour-coded entries by event type
