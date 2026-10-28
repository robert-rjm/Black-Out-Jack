# Black(Out)Jack — Rules Catalog

A structured, **one-entry-per-rule** index of every drinking rule in
Black(Out)Jack. It does not replace [Rules.md](Rules.md), which stays the
readable, narrative rulebook. This file exists so other features can point at
a single rule by a **stable ID**:

- **Rule toggles** ([planning/RuleToggles-SettingsModal.md](planning/RuleToggles-SettingsModal.md)):
  every toggle row maps to exactly one ID below.
- **Starter / preset rulesets** ([planning/RuleToggles-StarterSet.md](planning/RuleToggles-StarterSet.md)):
  presets are just lists of IDs.
- **Rules quiz** (future): each entry has quiz seeds, keyed by ID, so a quiz
  can ask only about the rules that are on at the current table.
- **Stats / exports**: each entry lists the `classify_rule()` CSV label(s)
  it produces (`app/services/utils.py`), so a drinks-summary row can link back
  to its rule.

> [!NOTE]
> This catalog is a planning artifact for now. Once the rule registry exists
> (`engine/rules_registry.py`, see
> [planning/RuleToggles-Implementation.md](planning/RuleToggles-Implementation.md)),
> the registry becomes the source of truth and a sync test keeps this file and
> the registry aligned (same pattern as `scripts/rules_sync.py`).

---

## Conventions

| Field | Meaning |
|---|---|
| **ID** | Stable, dotted, lowercase: `<group>.<rule>[.<variant>]`. Never renamed once shipped; retired IDs are kept in a "Retired" list. |
| **Anchor** | `#` + the ID with dots replaced by hyphens, e.g. `ace.clubs.player` → `#ace-clubs-player`. Link as `Rules-Catalog.md#ace-clubs-player`. |
| **Rules.md** | The section of the narrative rulebook that explains it. |
| **Kind** | `core` (the game itself, locked on) · `table` (blackjack-mechanic change) · `drink` (produces sips) · `event` (multi-step mini-game / vote) · `meta` (session-level: milestones, streaks) · `modifier` (scales other rules; not a toggle in the rule list) |
| **Timing** | `instant` · `end-of-round` · `between-rounds` · `passive` (always shaping the result, e.g. a cap) |
| **Halved** | Whether the Large Group Rule / Easy Mode halves it ([§6.1](Rules.md#61-large-group-rules-4-players)). |
| **Booster** | Whether a Drink Rate booster (>1.0×) applies. Discounts (<1.0×) apply to everything ([§6.3](Rules.md#63-drink-rate-mode)). |
| **Depends on** | Rule IDs that must be on for this rule to mean anything. The toggle UI greys this rule out if a parent is off. |
| **Preset** | Lowest preset that includes it: `Starter` ⊂ `Standard` ⊂ `Full`. `Locked` = always on. See the starter-set doc. |
| **Code** | Where it fires today. |
| **CSV label** | Output of `classify_rule()` for its drink rows. |
| **Quiz** | One or two seed questions with answers. |

---

## Summary table

| ID | Name | Kind | Timing | Preset |
|---|---|---|---|---|
| [`core.net_loss`](#core-net_loss) | Net hand losses | core | end-of-round | Locked |
| [`core.dealer_rotation`](#core-dealer_rotation) | Dealer rotation / Soft Switch | core | end-of-round | Locked |
| [`table.split_tens`](#table-split_tens) | Mandatory split 10s (play with honor) | table | instant | Starter |
| [`table.split_aces`](#table-split_aces) | Mandatory split Aces | table | instant | Standard |
| [`table.split_ace_bj`](#table-split_ace_bj) | Blackjack on split Aces counts as Blackjack | table | passive | Standard |
| [`insurance.auto_cap`](#insurance-auto_cap) | Auto-insurance cap (Ace up-card) | drink | passive | Starter |
| [`insurance.bj_vote`](#insurance-bj_vote) | Player Blackjack insurance vote | event | instant | Full |
| [`switch.hard`](#switch-hard) | Hard Dealer Switch penalty | drink | end-of-round | Starter |
| [`ace.clubs.player`](#ace-clubs-player) | A♣ to a player: −1 credit | drink | instant | Standard |
| [`ace.spades.player`](#ace-spades-player) | A♠ to a player: pass a sip by position | drink | instant | Standard |
| [`ace.hearts.player`](#ace-hearts-player) | A♥ to a player: treat yourself | drink | instant | Standard |
| [`ace.diamonds.player`](#ace-diamonds-player) | A♦ to a player: dealer drinks | drink | instant | Standard |
| [`ace.clubs.dealer`](#ace-clubs-dealer) | A♣ to the dealer: half Hard Switch | drink | passive | Standard |
| [`ace.spades.dealer`](#ace-spades-dealer) | A♠ to the dealer: odd/even | drink | instant | Standard |
| [`ace.hearts.dealer`](#ace-hearts-dealer) | A♥ to the dealer: everyone drinks | drink | instant | Standard |
| [`ace.diamonds.dealer`](#ace-diamonds-dealer) | A♦ to the dealer: players drink | drink | instant | Standard |
| [`dealer.suited_hand`](#dealer-suited_hand) | Dealer suited hand | drink | instant | Standard |
| [`four_aces.first_deal`](#four_aces-first_deal) | Four Aces on first deal | drink | instant | Standard |
| [`four_aces.end_round`](#four_aces-end_round) | Four Aces at end of round | drink | end-of-round | Standard |
| [`side.bust_vote`](#side-bust_vote) | Side bet: dealer bust vote | event | instant | Standard |
| [`cards.devils_hand`](#cards-devils_hand) | Devil's Hand (third 6) | drink | instant | Full |
| [`cards.lucky_sevens`](#cards-lucky_sevens) | Lucky Sevens (third 7) | drink | instant | Full |
| [`loss.doubled`](#loss-doubled) | Lost doubled hand +1 | drink | end-of-round | Starter |
| [`loss.suited`](#loss-suited) | Lost suited hand +1 (×4 if doubled too) | drink | end-of-round | Standard |
| [`others.wins_all`](#others-wins_all) | Another player wins all hands | drink | end-of-round | Starter |
| [`others.immunity.doubled`](#others-immunity-doubled) | Immunity break: doubled win | drink | end-of-round | Standard |
| [`others.immunity.split`](#others-immunity-split) | Immunity break: split win | drink | end-of-round | Standard |
| [`others.immunity.suited`](#others-immunity-suited) | Immunity break: suited win | drink | end-of-round | Standard |
| [`bonus.blackjack`](#bonus-blackjack) | Blackjack bonus (flat 1×) | drink | end-of-round | Starter |
| [`bonus.blackjack.multipliers`](#bonus-blackjack-multipliers) | Blackjack bonus ×2 multipliers | drink | end-of-round | Standard |
| [`five_card.player_21`](#five_card-player_21) | 5+ cards to exactly 21: handout | drink | end-of-round | Standard |
| [`five_card.player_win`](#five_card-player_win) | 5+ card win: others drink | drink | end-of-round | Standard |
| [`five_card.dealer_21`](#five_card-dealer_21) | Dealer 5+ cards to 21: core penalties doubled | drink | end-of-round | Full |
| [`sweep.same_suit`](#sweep-same_suit) | All-hand bonus: every card one suit | drink | end-of-round | Full |
| [`sweep.all_21`](#sweep-all_21) | All-hand bonus: every hand 21 | drink | end-of-round | Full |
| [`milestone.handout`](#milestone-handout) | Milestone handouts (every 50 sips) | meta | between-rounds | Starter |
| [`milestone.back_to_back`](#milestone-back_to_back) | Back-to-back milestone 🔥 callout | meta | passive | Starter |
| [`milestone.worst_average`](#milestone-worst_average) | "Worst average" penalty | meta | between-rounds | Full |
| [`streak.l_badge`](#streak-l_badge) | Losing streak "L" badge hand-off | meta | end-of-round | Full |
| [`event.dealer_lottery`](#event-dealer_lottery) | Dealer Lottery | event | between-rounds | Full |
| [`event.targeted`](#event-targeted) | Targeted Drinking Mode | event | between-rounds | Full |
| [`event.targeted.perfect_handout`](#event-targeted-perfect_handout) | Targeted: perfect-graduation handout | event | between-rounds | Full |
| [`event.wild_card`](#event-wild_card) | Wild Card 🃏 easter egg | event | instant | Full |
| [`event.wild_card.targeted`](#event-wild_card-targeted) | Wild Card launches Targeted Drinking | event | between-rounds | Full |

**Modifiers** (listed for completeness, *not* part of the rule toggle list;
they keep their own controls in Settings):
[`mod.large_group`](#mod-large_group) · [`mod.easy_mode`](#mod-easy_mode) ·
[`mod.drink_rate`](#mod-drink_rate) · [`mod.wager`](#mod-wager)

---

## 1. Core (locked)

These *are* the game. Turning them off would leave a blackjack game with no
drinking currency, so they are shown in the toggle UI with a 🔒 and can't be
switched off. (Normal Mode is the "everything off" version.)

### <a id="core-net_loss"></a>Net hand losses — `core.net_loss`
- **Rules.md:** [§5.1](Rules.md#51-net-hand-losses) · **Kind:** core · **Timing:** end-of-round · **Preset:** Locked
- **Trigger:** End of every round.
- **Effect:** Each hand scores Win +1, Blackjack +2, Loss −1, Push 0. A negative net total is drunk as `|net| × wager` sips; positive totals are ignored.
- **Halved:** Yes · **Booster:** Yes
- **Depends on:** — · **Interacts with:** `insurance.auto_cap`, `five_card.dealer_21`, `switch.hard` (replaces the dealer's own net loss)
- **Code:** `engine/drinking_rules.py` `DrinkingRules._net_loss_drinks` (via `on_round_end`)
- **CSV label:** `Net hand losses`
- **Quiz:** Q: You play 2 hands: one Blackjack, one loss. How many sips? **A:** 0 (net +1). · Q: Do positive net scores give you sips to hand out? **A:** No, they're disregarded.

### <a id="core-dealer_rotation"></a>Dealer rotation / Soft Switch — `core.dealer_rotation`
- **Rules.md:** [§2](Rules.md#2-dealer-rotation) · **Kind:** core · **Timing:** end-of-round · **Preset:** Locked
- **Trigger:** Every *n* rounds (setting `dealer_rotate_every`), or early on a Soft Switch (dealer wins all hands) / Hard Switch (dealer loses all hands).
- **Effect:** Dealer role passes. Soft Switch has no drink effect of its own. Soft Switch is skipped if any player took insurance on Blackjack.
- **Halved:** n/a · **Booster:** n/a
- **Depends on:** — · **Interacts with:** `switch.hard` (if Hard Switch is off, losing all hands still rotates the dealer, just without the penalty)
- **Code:** `app/services/room_manager.py` / `engine/blackjack.py` rotation logic
- **CSV label:** `Hard Switch notice` (zero-sip notice)
- **Quiz:** Q: Does a push count as a win or a loss for switch purposes? **A:** Neither.

---

## 2. Table rules (blackjack mechanics)

### <a id="table-split_tens"></a>Mandatory split 10s — `table.split_tens`
- **Rules.md:** [§3](Rules.md#3-rule-modifications-from-standard-blackjack) · **Kind:** table · **Timing:** instant · **Preset:** Starter
- **Trigger:** A player's active hand is an **unsuited** 10-value pair and they try to hit, stand or double.
- **Effect:** Blocked by the "Play with honor" prompt; playing it anyway ("without honor") costs 1× wager. Splitting a **suited** 10-pair is optional, but splitting it costs 1× wager.
- **Halved:** No · **Booster:** No
- **Depends on:** — · **Interacts with:** `others.immunity.suited` (the reason suited 10s are exempt), basic-strategy hints and bot strategy (`engine/strategy.py`, `engine/style_strategy.py`)
- **Code:** `app/services/stats.py` `compute_mandatory_split10`, `app/services/player_actions.py` `check_honor_house_rule` / `perform_action_without_honor`
- **CSV label:** `Split 10s without honor` (declined split) · `Split suited 10s` (suited split)
- **Quiz:** Q: You hold J♥ Q♥. Must you split? **A:** No: suited 10s are the exception, and splitting them costs 1× wager.

### <a id="table-split_aces"></a>Mandatory split Aces — `table.split_aces`
- **Rules.md:** [§3.1](Rules.md#31-splitting-aces) · **Kind:** table · **Timing:** instant · **Preset:** Standard
- **Trigger:** A human player takes any action other than split on an original A-A pair.
- **Effect:** 1 sip immediately, no prompt.
- **Halved:** No · **Booster:** No
- **Depends on:** —
- **Code:** `app/services/stats.py` `compute_mandatory_split_aces`, `app/services/player_actions.py` `penalize_unsplit_aces`
- **CSV label:** `Didn't split Aces`
- **Quiz:** Q: What happens if you stand on A-A? **A:** You drink 1 sip on the spot.

### <a id="table-split_ace_bj"></a>Blackjack on split Aces — `table.split_ace_bj`
- **Rules.md:** [§3.1](Rules.md#31-splitting-aces) · **Kind:** table · **Timing:** passive · **Preset:** Standard
- **Trigger:** A split Ace hand makes 21 with two cards.
- **Effect:** Counts as a Blackjack (+2 score, triggers `bonus.blackjack`) instead of a plain 21. Off = standard casino rule (a plain 21).
- **Halved:** n/a · **Booster:** n/a
- **Depends on:** — · **Interacts with:** `bonus.blackjack`
- **Code:** `engine/blackjack.py` hand scoring (`Hand.is_blackjack` path)
- **CSV label:** via `Blackjack bonus`
- **Quiz:** Q: You split Aces and get A♥ 10♥. Blackjack or 21? **A:** Blackjack.

---

## 3. Insurance

### <a id="insurance-auto_cap"></a>Auto-insurance cap — `insurance.auto_cap`
- **Rules.md:** [§3.2](Rules.md#32-insurance) · **Kind:** drink · **Timing:** passive · **Preset:** Starter
- **Trigger:** Dealer's **up-card is an Ace** and the dealer has Blackjack.
- **Effect:** Each player's penalty is capped at `wager × hands`; doubles, splits and suited extras can't push it higher. A dealer Blackjack from a 10 up-card gets no cap.
- **Halved:** Yes · **Booster:** Yes
- **Depends on:** —
- **Code:** `engine/drinking_rules.py` `DrinkingRules._dealer_bj_drinks`
- **CSV label:** `Dealer BJ (auto-insurance)`
- **Quiz:** Q: Dealer shows 10, flips an Ace for Blackjack. Is your loss capped? **A:** No, the cap only applies to an Ace up-card.

### <a id="insurance-bj_vote"></a>Player Blackjack insurance vote — `insurance.bj_vote`
- **Rules.md:** [§3.2](Rules.md#32-insurance) · **Kind:** event · **Timing:** instant · **Preset:** Full
- **Trigger:** Dealer shows an Ace **and** a player has Blackjack. Everyone else votes Insure / Decline (tie = decline, timeout 60 s).
- **Effect:** Insure + dealer BJ → BJ holder drinks their own bonus, group drinks nothing. Insure + no dealer BJ → group drinks double the BJ bonus. Decline → normal rules.
- **Halved:** Yes · **Booster:** Yes
- **Depends on:** `bonus.blackjack` · **Interacts with:** `switch.hard` (softened dealer penalty), `core.dealer_rotation` (blocks Soft Switch)
- **Code:** `engine/drinking_rules.py` `DrinkingRules.resolve_insurance_vote`; vote flow in the app round pipeline
- **CSV label:** `Insurance: BJ holder drinks own bonus`, `Insurance: group drinks double BJ bonus`
- **Quiz:** Q: The vote is tied. What happens? **A:** Decline.

---

## 4. Dealer switches

### <a id="switch-hard"></a>Hard Dealer Switch penalty — `switch.hard`
- **Rules.md:** [§5.7](Rules.md#57-hard-dealer-switch-penalty) · **Kind:** drink · **Timing:** end-of-round · **Preset:** Starter
- **Trigger:** Dealer loses **all** hands.
- **Effect:** Dealer drinks per players' winning hands: regular 1×, Blackjack 2×, doubled 2×, split hands counted separately, suited no extra. This **replaces** the dealer's own player-role drinking for the round. Dealer's own Blackjack counts 1×.
- **Halved:** Yes · **Booster:** Yes
- **Depends on:** — · **Interacts with:** `ace.clubs.dealer`, `ace.clubs.player` (dealer-player exclusion), `insurance.bj_vote`
- **Code:** `engine/drinking_rules.py` `DrinkingRules.on_hard_dealer_switch`, `HardDealerSwitchEvent`
- **CSV label:** `Hard Dealer Switch`, `Hard Dealer Switch (half, A♣)`
- **Quiz:** Q: Two players win: one regular hand and one doubled hand. What does the dealer drink? **A:** 1× + 2× = 3× wager.

---

## 5. Ace effects (instant)

Group toggle: **Ace effects** (all eight). Each suit can also be toggled
on its own. Ace sips are never halved and boosters never apply (discounts do).

### <a id="ace-clubs-player"></a>A♣ to a player — `ace.clubs.player`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant (credit settles at end of round) · **Preset:** Standard
- **Effect:** −1× wager from the end-of-round net (min 0). If the recipient is also the dealer, their own player hands are excluded from the Hard Switch penalty instead, and the credit only applies if no Hard Switch fires.
- **Halved:** No · **Booster:** No
- **Depends on:** — (the dealer-player part needs `switch.hard`)
- **Code:** `DrinkingRules.on_card_dealt`, `DrinkTracker.apply_ace_clubs_credit`
- **CSV label:** `A♣ protection credit`, `A♣ waived`
- **Quiz:** Q: You owe 0 sips and were dealt A♣. Do you get a sip to hand out? **A:** No, the credit can't go below 0.

### <a id="ace-spades-player"></a>A♠ to a player — `ace.spades.player`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** The player *n* seats onward drinks 1× wager, where *n* is the card's position in the hand (1st card → next player, 2nd card → two along…).
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Spades (player hand)`
- **Quiz:** Q: A♠ is the 2nd card of your hand. Who drinks? **A:** The player two seats onward.

### <a id="ace-hearts-player"></a>A♥ to a player — `ace.hearts.player`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** You drink 1× wager ("treat yourself").
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Hearts (player hand)`
- **Quiz:** Q: Who drinks when you're dealt A♥? **A:** You do.

### <a id="ace-diamonds-player"></a>A♦ to a player — `ace.diamonds.player`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** The dealer drinks 1× wager.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Diamonds (player hand)`
- **Quiz:** Q: A♦ lands in a player's hand. Who drinks? **A:** The dealer.

### <a id="ace-clubs-dealer"></a>A♣ to the dealer — `ace.clubs.dealer`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects), [§5.7](Rules.md#57-hard-dealer-switch-penalty) · **Timing:** passive · **Preset:** Standard
- **Effect:** If a Hard Switch fires, the dealer drinks only half the penalty (rounded up).
- **Halved:** n/a · **Booster:** n/a
- **Depends on:** `switch.hard`
- **Code:** `DrinkingRules.on_card_dealt` (sets `half_protected`), `on_hard_dealer_switch`
- **CSV label:** `Hard Dealer Switch (half, A♣)`
- **Quiz:** Q: Dealer was dealt A♣ and owes a 5-sip Hard Switch. How many do they drink? **A:** 3 (half, rounded up).

### <a id="ace-spades-dealer"></a>A♠ to the dealer — `ace.spades.dealer`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** Odd card position (1st, 3rd…) → dealer drinks 1×. Even position → every player drinks 1×.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Spades (dealer hand)`
- **Quiz:** Q: A♠ is the dealer's 2nd card. Who drinks? **A:** All players.

### <a id="ace-hearts-dealer"></a>A♥ to the dealer — `ace.hearts.dealer`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** Everyone drinks 1× wager.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Hearts (dealer hand)`
- **Quiz:** Q: Dealer is dealt A♥. Who drinks? **A:** Everyone.

### <a id="ace-diamonds-dealer"></a>A♦ to the dealer — `ace.diamonds.dealer`
- **Rules.md:** [§4.1](Rules.md#41-ace-effects) · **Timing:** instant · **Preset:** Standard
- **Effect:** Every player except the dealer drinks 1× wager.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.on_card_dealt` · **CSV label:** `Ace dealt: Ace of Diamonds (dealer hand)`
- **Quiz:** Q: Does the dealer drink on their own A♦? **A:** No, everyone else does.

---

## 6. Other instant rules

### <a id="dealer-suited_hand"></a>Dealer suited hand — `dealer.suited_hand`
- **Rules.md:** [§4.2](Rules.md#42-dealer-suited-hand) · **Kind:** drink · **Timing:** instant · **Preset:** Standard
- **Effect:** Dealer's final hand is all one suit → all players drink 2× wager, whatever the result.
- **Halved:** No · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.on_dealer_hand_revealed` · **CSV label:** `Dealer suited hand`
- **Quiz:** Q: The dealer busts with 3 hearts. Do players drink? **A:** Yes, 2× wager (result doesn't matter).

### <a id="four_aces-first_deal"></a>Four Aces on first deal — `four_aces.first_deal`
- **Rules.md:** [§4.3](Rules.md#43-four-aces-on-first-deal) · **Timing:** instant · **Preset:** Standard
- **Effect:** All 4 Aces visible after the first deal (player hands + dealer up-card) → everyone drinks 2× wager.
- **Halved:** No · **Booster:** No · **Depends on:** — · **Interacts with:** `four_aces.end_round` (takes precedence)
- **Code:** `DrinkingRules.check_four_aces` (phase `first_deal`) · **CSV label:** `Four Aces (first deal)`
- **Quiz:** Q: Does the dealer's hole card count for Four Aces on first deal? **A:** No, only the face-up card.

### <a id="four_aces-end_round"></a>Four Aces at end of round — `four_aces.end_round`
- **Rules.md:** [§5.6](Rules.md#56-four-aces-at-end-of-round) · **Timing:** end-of-round · **Preset:** Standard
- **Effect:** All 4 Aces visible at end of round, but not on first deal → everyone drinks 1×.
- **Halved:** Yes · **Booster:** No · **Depends on:** —
- **Code:** `DrinkingRules.check_four_aces` (phase `end_round`) · **CSV label:** `Four Aces (end of round)`
- **Quiz:** Q: Can both Four Aces rules fire in one round? **A:** No, first deal takes precedence.

### <a id="side-bust_vote"></a>Side bet: dealer bust vote — `side.bust_vote`
- **Rules.md:** [§4.4](Rules.md#44-side-bet-dealer-bust) · **Kind:** event · **Timing:** instant (vote before the deal) · **Preset:** Standard
- **Effect:** Correct "bust" call → −1× credit **and** a 1× handout. Wrong call → +1×. Abstain → nothing. Unassigned handout returns to you.
- **Halved:** No · **Booster:** No
- **Depends on:** — · **Existing toggle:** `GameConfig.bust_vote_enabled` (migrates into this rule)
- **Code:** `app/services/drink_tracker.py` `apply_bust_vote_penalties`, `app/routes/polling.py`
- **CSV label:** `Bust vote credit`, `Bust vote wrong call`, `Bust vote handout received`, `Bust vote handout forfeited`
- **Quiz:** Q: You called bust correctly. What two things do you get? **A:** A 1× credit and a 1× handout.

### <a id="cards-devils_hand"></a>Devil's Hand — `cards.devils_hand`
- **Rules.md:** [§4.5](Rules.md#45-devils-hand-and-lucky-sevens) · **Timing:** instant · **Preset:** Full
- **Effect:** When the **3rd six** becomes visible, the target (counted clockwise from the recipient by the card's position in its hand) drinks 1×. Once per round.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `app/services/game_engine.py` (`_six_curse_fired`) · **CSV label:** `Devil's Hand`
- **Quiz:** Q: Does the dealer's hole card count toward Devil's Hand when dealt? **A:** No, only when it's revealed.

### <a id="cards-lucky_sevens"></a>Lucky Sevens — `cards.lucky_sevens`
- **Rules.md:** [§4.5](Rules.md#45-devils-hand-and-lucky-sevens) · **Timing:** instant · **Preset:** Full
- **Effect:** When the **3rd seven** becomes visible, the target gets a −1× credit (min 0). Once per round.
- **Halved:** No · **Booster:** No · **Depends on:** —
- **Code:** `app/services/game_engine.py` · **CSV label:** `Lucky Sevens`
- **Quiz:** Q: Is Lucky Sevens a drink or a credit? **A:** A −1× credit.

---

## 7. End-of-round rules

### <a id="loss-doubled"></a>Lost doubled hand — `loss.doubled`
- **Rules.md:** [§5.1](Rules.md#51-net-hand-losses) · **Timing:** end-of-round · **Preset:** Starter
- **Effect:** +1× wager per lost doubled hand.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** `core.net_loss`
- **Code:** `DrinkingRules._extra_loss_drinks` · **CSV label:** `Lost doubled hand`
- **Quiz:** Q: You lose a doubled hand at wager 1 (no other hands). How many sips? **A:** 2 (1 base + 1 doubled).

### <a id="loss-suited"></a>Lost suited hand — `loss.suited`
- **Rules.md:** [§5.1](Rules.md#51-net-hand-losses) · **Timing:** end-of-round · **Preset:** Standard
- **Effect:** +1× per lost suited hand. Doubled **and** suited → +3× (4× total with the base loss).
- **Halved:** Yes · **Booster:** Yes · **Depends on:** `core.net_loss` · **Interacts with:** `loss.doubled` (the ×4 combo needs both on; with `loss.doubled` off, a doubled suited loss is +1× only)
- **Code:** `DrinkingRules._extra_loss_drinks` · **CSV label:** `Lost suited hand`
- **Quiz:** Q: Total sips for losing a doubled, suited hand? **A:** 4× wager.

### <a id="others-wins_all"></a>Another player wins all hands — `others.wins_all`
- **Rules.md:** [§5.2](Rules.md#52-other-players-results) · **Timing:** end-of-round · **Preset:** Starter
- **Effect:** When someone wins all their hands: if you lost ≥1 hand, drink 1× per hand they won; if you won all, drink 0 (immune); if no losses but ≥1 push, drink their wins minus your wins.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules._wins_all_drinks` · **CSV label:** `Other-player sweep`
- **Quiz:** Q: Other player wins both. You won 1 and pushed 1. Sips? **A:** 1 (2 − 1).

### <a id="others-immunity-doubled"></a>Immunity break: doubled win — `others.immunity.doubled`
- **Rules.md:** [§5.2](Rules.md#52-other-players-results) · **Preset:** Standard
- **Effect:** Even if you won all hands, you drink 1× when another player wins a doubled hand. Doubled **and** suited → 4×.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.on_hand_resolved` · **CSV label:** `Doubled win (immunity break)`
- **Quiz:** Q: You won every hand. Can you still drink? **A:** Yes, if someone else won a double, a split or a suited hand.

### <a id="others-immunity-split"></a>Immunity break: split win — `others.immunity.split`
- **Rules.md:** [§5.2](Rules.md#52-other-players-results) · **Preset:** Standard
- **Effect:** Others drink 1× per successful split win.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules._split_win_drinks` · **CSV label:** `Split win (immunity break)`
- **Quiz:** Q: A player splits twice (3 hands) and wins 2. What do others drink? **A:** 1× (one split won).

### <a id="others-immunity-suited"></a>Immunity break: suited win — `others.immunity.suited`
- **Rules.md:** [§5.2](Rules.md#52-other-players-results) · **Preset:** Standard
- **Effect:** Others drink 1× when a player wins with a suited hand (4× if also doubled).
- **Halved:** Yes · **Booster:** Yes · **Depends on:** — · **Interacts with:** `table.split_tens` (why suited 10s are exempt from the split)
- **Code:** `DrinkingRules.on_hand_resolved` · **CSV label:** `Suited winning hand`
- **Quiz:** Q: Why are suited 10s exempt from the mandatory split? **A:** A suited 20 already threatens everyone with the suited-win penalty.

### <a id="bonus-blackjack"></a>Blackjack bonus — `bonus.blackjack`
- **Rules.md:** [§5.3](Rules.md#53-blackjack-bonus) · **Timing:** end-of-round · **Preset:** Starter
- **Effect:** When any player gets a Blackjack, all other players drink 1×, whatever their own result. No immunity.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.on_blackjack` · **CSV label:** `Blackjack bonus`
- **Quiz:** Q: You won all your hands. Do you drink for someone else's Blackjack? **A:** Yes, no immunity.

### <a id="bonus-blackjack-multipliers"></a>Blackjack bonus multipliers — `bonus.blackjack.multipliers`
- **Rules.md:** [§5.3](Rules.md#53-blackjack-bonus) · **Preset:** Standard
- **Effect:** Cumulative ×2 each for suited, Ace + Jack, both black. Max A♠ J♠ = 8×. Off = flat 1× for every Blackjack.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** `bonus.blackjack`
- **Code:** `engine/drinking_rules.py` `_bj_breakdown` / `_bj_multiplier`
- **CSV label:** `Blackjack bonus`
- **Quiz:** Q: A♥ J♥: how many wagers? **A:** 4× (suited ×2, A+J ×2).

### <a id="five_card-player_21"></a>5+ cards to exactly 21 — `five_card.player_21`
- **Rules.md:** [§5.4](Rules.md#54-5-cards-handouts) · **Preset:** Standard
- **Effect:** Player with 5+ cards totalling exactly 21 hands out `card count × wager` sips. No win required.
- **Halved:** No (handouts) · **Booster:** Yes (on received sips)
- **Depends on:** —
- **Code:** `DrinkTracker._handle_handout` (label `5-card 21`) · **CSV label:** `5-card 21 handout received`
- **Quiz:** Q: 6-card 21 at wager 1. How many sips to hand out? **A:** 6.

### <a id="five_card-player_win"></a>5+ card win — `five_card.player_win`
- **Rules.md:** [§5.4](Rules.md#54-5-cards-handouts) · **Preset:** Standard
- **Effect:** Player wins with 5+ cards → all other players drink 1×. Not on a push. Stacks with `five_card.player_21`.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.on_hand_resolved` · **CSV label:** `5+ card win`
- **Quiz:** Q: Does a 5-card push trigger the win rule? **A:** No.

### <a id="five_card-dealer_21"></a>Dealer 5+ cards to 21 — `five_card.dealer_21`
- **Rules.md:** [§5.4](Rules.md#54-5-cards-handouts) · **Preset:** Full
- **Effect:** Dealer makes 21 with 5+ cards → all players' **core** penalties are doubled this round (net losses, lost-hand extras, wins-all, split wins, auto-insurance). Extras (BJ bonus, aces, sweeps, bust vote, lottery) are not doubled.
- **Halved:** Yes (after doubling) · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.dealer_21_five_cards` (called directly, not via `handle()`)
- **CSV label:** none of its own (shows up as the doubled core labels; tested by sip totals, see [Gaps](#gaps-found-while-cataloguing))
- **Quiz:** Q: Dealer makes a 5-card 21. Is the Blackjack bonus doubled? **A:** No, only core penalties.

### <a id="sweep-same_suit"></a>All-hand bonus: one suit — `sweep.same_suit`
- **Rules.md:** [§5.5](Rules.md#55-player-all-hand-bonus) · **Preset:** Full
- **Effect:** Every card across all of a player's final hands is one suit → others drink 4×. Both this and `sweep.all_21` → 6×. Any result.
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.check_all_hands_sweep` · **CSV label:** `All-hands sweep` (and `Sweep credit`)
- **Quiz:** Q: Does the all-suit bonus need a win? **A:** No, any result.

### <a id="sweep-all_21"></a>All-hand bonus: every hand 21 — `sweep.all_21`
- **Rules.md:** [§5.5](Rules.md#55-player-all-hand-bonus) · **Preset:** Full
- **Effect:** Every hand totals exactly 21 → others drink 2× (6× if also all one suit).
- **Halved:** Yes · **Booster:** Yes · **Depends on:** —
- **Code:** `DrinkingRules.check_all_hands_sweep` · **CSV label:** `All-hands sweep`
- **Quiz:** Q: Both all-hand bonuses at once: how many wagers? **A:** 6×.

---

## 8. Session-level (meta) rules

### <a id="milestone-handout"></a>Milestone handouts — `milestone.handout`
- **Rules.md:** [§5.8](Rules.md#58-milestone-handouts) · **Kind:** meta · **Timing:** between-rounds · **Preset:** Starter
- **Effect:** Crossing each multiple of 50 cumulative sips earns 5 / 6 / 7 … sips to hand out within 60 s; unassigned sips return to you. Ties: fewest sips this round, then the previous round, then random.
- **Halved:** No · **Booster:** Yes (on received sips)
- **Depends on:** — · **Config:** `MILESTONE_STEP`, `MILESTONE_HANDOUT_SIPS`, `MILESTONE_TTL`
- **Code:** `app/services/drink_tracker.py` `check_and_set_milestone`, `app/routes/admin.py` `/claim_milestone`
- **CSV label:** milestone handout rows
- **Quiz:** Q: How many sips do you hand out at the 100-sip milestone? **A:** 6.

### <a id="milestone-back_to_back"></a>Back-to-back milestone callout — `milestone.back_to_back`
- **Rules.md:** [§5.8](Rules.md#back-to-back-milestones) · **Kind:** meta · **Timing:** passive · **Preset:** Starter
- **Effect:** Cosmetic 🔥 callout when the same player completes consecutive milestone handouts. No sips.
- **Depends on:** `milestone.handout`
- **Code:** milestone streak tracking in `drink_tracker.py`; 🔥 rendering in `static/js/ui/seats.js`
- **CSV label:** none
- **Quiz:** Q: Does a forfeited handout keep a back-to-back run alive? **A:** No.

### <a id="milestone-worst_average"></a>"Worst average" penalty — `milestone.worst_average`
- **Rules.md:** [§5.8](Rules.md#worst-average-penalty) · **Kind:** meta · **Preset:** Full
- **Effect:** At each milestone, the lowest average sips/round (excluding the winner) is flagged "worst". Flagged two milestones running → drink the winner's average sips/round (rounded up, min 1), then the streak resets.
- **Halved:** No · **Booster:** Yes
- **Depends on:** `milestone.handout`
- **Code:** `app/services/drink_tracker.py` `_apply_worst_player_streak`
- **CSV label:** worst-average penalty rows
- **Quiz:** Q: How many milestones in a row must you be "worst" to pay? **A:** Two.

### <a id="streak-l_badge"></a>Losing streak "L" badge — `streak.l_badge`
- **Rules.md:** [§5.8](Rules.md#losing-streak-l-badge) · **Kind:** meta · **Timing:** end-of-round · **Preset:** Full
- **Effect:** 5+ consecutive round losses → hold the L. If someone's streak becomes strictly longer, the L moves and the outgoing holder drinks 1 sip. Earning it, or losing it because your own streak broke, is free.
- **Halved:** No · **Booster:** No · **Config:** `WORST_STREAK_THRESHOLD`
- **Depends on:** —
- **Code:** `app/services/drink_tracker.py` `_update_worst_streak_holder`
- **CSV label:** L-badge hand-off rows
- **Quiz:** Q: Does a tie take the L from the current holder? **A:** No.

---

## 9. Events (mini-games)

### <a id="event-dealer_lottery"></a>Dealer Lottery — `event.dealer_lottery`
- **Rules.md:** [§5.9](Rules.md#59-dealer-lottery) · **Kind:** event · **Timing:** between-rounds · **Preset:** Full
- **Trigger:** Dealer's final hand is a paired 18 (9-9) or paired 20 (two 10-values).
- **Effect:** Players stake 0–5 wagers; the pair is redealt split from a fresh deck. 2+ busts pay the full stake (+2 all-in bonus at stake 5); 1 bust pays half; no bust → drink stake × hands ÷ 2 (cap 10×). Payouts clear this round's debt first, then become handouts. Top staker always hands out +1.
- **Halved:** Handouts and no-bust drink never halved · **Booster:** Yes (on received sips)
- **Depends on:** —
- **Code:** `app/services/dealer_lottery.py` (`check_dealer_lottery_trigger`, `maybe_start_dealer_lottery`, `resolve_dealer_lottery`)
- **CSV label:** Dealer Lottery rows
- **Quiz:** Q: Which dealer hands trigger the lottery? **A:** A paired 18 or a paired 20.

### <a id="event-targeted"></a>Targeted Drinking Mode — `event.targeted`
- **Rules.md:** [§5.10](Rules.md#510-targeted-drinking-mode) · **Kind:** event · **Timing:** between-rounds · **Preset:** Full
- **Effect:** Targeted players call BUST/STAND on isolated dealer mini-hands between rounds. Wrong call: 2 sips and the streak resets. Released after 3 correct in a row that include at least one BUST and one STAND. 3-round cooldown after. Started by the host, a majority vote, or the Wild Card.
- **Halved:** No · **Booster:** Yes
- **Depends on:** —
- **Code:** `app/services/targeted_drinking.py`, `app/routes/targeted_drinking.py`
- **CSV label:** Targeted Drinking rows (`count_toward_round=False`)
- **Quiz:** Q: Three correct STAND calls in a row: are you released? **A:** No, you need at least one BUST and one STAND in the streak.

### <a id="event-targeted-perfect_handout"></a>Perfect-graduation handout — `event.targeted.perfect_handout`
- **Rules.md:** [§5.10](Rules.md#510-targeted-drinking-mode) · **Preset:** Full
- **Effect:** Graduating in exactly 3 attempts with no misses → hand out 3 sips (20 s window, never halved).
- **Depends on:** `event.targeted`
- **Code:** `app/services/targeted_drinking.py` · **Config:** `TARGETED_DRINKING_PERFECT_GRADUATION_HANDOUT_SIPS`
- **Quiz:** Q: How many sips does a perfect graduation hand out? **A:** 3.

### <a id="event-wild_card"></a>Wild Card 🃏 — `event.wild_card`
- **Rules.md:** referenced in [§5.10](Rules.md#easter-egg-launch-wild-card-) · **Kind:** event · **Timing:** instant · **Preset:** Full
- **Effect:** Pressing the logo: 35% the presser drinks 1, 50% a random other player drinks 1, 15% launches Targeted Drinking. 3-round per-player cooldown; blocked within 10 sips of an open milestone.
- **Halved:** No · **Booster:** No
- **Depends on:** — · **Existing toggle:** `GameConfig.wild_card_enabled` (migrates into this rule)
- **Code:** `app/routes/wild_card.py` · **CSV label:** `Wild Card`
- **Quiz:** Q: What's the most likely Wild Card outcome? **A:** A random other player drinks 1 (50%).

### <a id="event-wild_card-targeted"></a>Wild Card → Targeted Drinking — `event.wild_card.targeted`
- **Rules.md:** [§5.10 Easter Egg](Rules.md#easter-egg-launch-wild-card-) · **Preset:** Full
- **Effect:** The 15% roll launches Targeted Drinking with a 5-sip cap (+1 penalty on crossing it). If the target graduates first, the presser drinks what the target drank.
- **Depends on:** `event.wild_card`, `event.targeted` (with either off, the 15% slice falls back to a "random" drink)
- **Code:** `app/routes/wild_card.py`, `app/services/targeted_drinking.py`
- **Quiz:** Q: A Wild Card target graduates after 1 miss. What does the presser drink? **A:** 2 sips (what the target drank).

---

## 10. Modifiers (not rule toggles)

These scale other rules rather than adding their own. They keep their
existing controls and are listed here so a quiz and the rules modal can still
link to them.

| ID | Name | Rules.md | Control today |
|---|---|---|---|
| <a id="mod-large_group"></a>`mod.large_group` | Halve end-of-round drinks at 4+ players | [§6.1](Rules.md#61-large-group-rules-4-players) | Automatic |
| <a id="mod-easy_mode"></a>`mod.easy_mode` | Halving at any player count | [§6.2](Rules.md#62-easy-mode) | `easy_mode` (setup and settings) |
| <a id="mod-drink_rate"></a>`mod.drink_rate` | Per-seat drink rate 0.2×–1.5× | [§6.3](Rules.md#63-drink-rate-mode) | Settings → 🍷 Drink rate |
| <a id="mod-wager"></a>`mod.wager` | Wager and hands per player | [§1](Rules.md#1-game-setup) | Settings (queued) |

---

## Gaps found while cataloguing

Worth fixing alongside the toggle work (each fix touches `Rules.md`, so it
goes through `python scripts/rules_sync.py update`):

1. ~~**`table.split_aces` isn't in Rules.md.**~~ Fixed: Rules.md §3.1 and the
   Cheat Sheet now document the flat 1-sip penalty.
2. ~~**A♣-to-dealer wording differs.**~~ Fixed: Cheat-Sheet.md now says the
   dealer drinks half (rounded up), matching Rules.md and the code.
3. ~~**Split-10s and split-Aces penalties land in CSV as `Other`.**~~ Fixed:
   `classify_rule` now emits `Split 10s without honor`, `Split suited 10s`
   and `Didn't split Aces`.
4. **`five_card.dealer_21` has no label of its own.** The doubling is folded
   into the core rows, and zero-sip notices never reach `drink_log` or the CSV
   (`DrinkTracker.apply` only prints them). Decision: no notice row. The rule
   is tested by sip totals (core penalties exactly doubled when on, normal
   when off) rather than by label.
5. ~~**Split-10s penalty unit.**~~ Fixed: the suited-split penalty was a flat
   1 sip; it is now 1× wager like the "without honor" penalty.

## Retired IDs

_None yet._
