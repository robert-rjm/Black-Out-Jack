"""
engine/referee.py
==========
Real-life referee for Drinking Blackjack.

Use when playing with a physical deck. You deal real cards and make real
decisions — this module acts as a scorekeeper and drink tracker. Tell it
what cards were dealt and what happened, and it fires all the drinking rules
in real time.

`RefereeSession` is the shared library used by both the web app's referee
mode (see app/routes/lobby.py) and the standalone terminal CLI.

Run the standalone CLI:
    python scripts/play_referee.py

Commands (type 'help' in-session for full reference):
    deal <player> <card> [hand<n>]   — register a card dealt
    action <player> <action> [hand<n>] — register an action (double/split/insurance)
    result <player> <result> [hand<n>] — set hand outcome (win/loss/push)
    endround                          — finalise round, print drink summary
    newround                          — start next round
    status                            — show current round state
    help                              — show command reference
    quit                              — exit

Card format:   <rank><suit>
    rank:  2-9, 10, J, Q, K, A
    suit:  h=hearts  d=diamonds  c=clubs  s=spades
    e.g.:  Ah  10s  Kd  3c

Examples:
    deal Rob Ah hand1          — Rob's hand 1 receives Ace of Hearts
    deal dealer 7d             — dealer receives 7 of Diamonds
    action Rob double hand1    — Rob doubles down on hand 1
    result Rob win hand1       — Rob's hand 1 wins
    result dealer bust         — dealer busts (all non-busted players win)
"""

from engine.blackjack import (
    Rank, Suit, Card, Hand, Player
)
from engine.drinking_rules import DrinkingRules, DrinkTracker
from engine.events import (
    CardDealtEvent,
    BlackjackEvent,
    InsuranceResolvedEvent,
    HandResolvedEvent,
    AllHandsSweepEvent,
    DealerHandRevealedEvent,
    RoundEndEvent,
    HardDealerSwitchEvent,
)
from tabulate import tabulate


# =============================================================================
# Card parsing
# =============================================================================

RANK_MAP = {
    "2": Rank.TWO,   "3": Rank.THREE, "4": Rank.FOUR,  "5": Rank.FIVE,
    "6": Rank.SIX,   "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE,
    "10": Rank.TEN,  "j": Rank.JACK,  "q": Rank.QUEEN, "k": Rank.KING,
    "a": Rank.ACE,
}
SUIT_MAP = {
    "h": Suit.HEARTS, "d": Suit.DIAMONDS,
    "c": Suit.CLUBS,  "s": Suit.SPADES,
}


def parse_card(token: str) -> Card:
    """
    Parse a card string like 'Ah', '10s', 'Kd', '3c'.
    Raises ValueError with a helpful message on bad input.
    """
    token = token.strip().lower()
    if len(token) < 2:
        raise ValueError(f"Cannot parse card '{token}' — use format like Ah, 10s, Kd")

    suit_char = token[-1]
    rank_str  = token[:-1]

    if suit_char not in SUIT_MAP:
        raise ValueError(f"Unknown suit '{suit_char}' — use h/d/c/s")
    if rank_str not in RANK_MAP:
        raise ValueError(f"Unknown rank '{rank_str}' — use 2-9, 10, J, Q, K, A")

    return Card(RANK_MAP[rank_str], SUIT_MAP[suit_char])


# =============================================================================
# RefereeSession
# =============================================================================

class RefereeSession:
    """
    Manages one or more rounds of a real-life Drinking Blackjack game.
    Receives card/action/result events via text commands and fires
    DrinkingRules hooks in response.
    """

    def __init__(self, players: list, dealer_name: str,
                 wager: int = 1, num_hands: int = 2, verbose: bool = True,
                 bust_vote_enabled: bool = False):
        self.all_players   = players           # list of Player objects (includes dealer-player)
        self.dealer_name   = dealer_name
        self.wager         = wager
        self.num_hands     = num_hands
        self.verbose       = verbose  # set False by web layer to silence terminal output
        self.round_count   = 0
        self._all_names    = [p.name for p in players]
        self._player_map   = {p.name.lower(): p for p in players}

        # Round state
        self._ace_clubs_flag  = {
            "protected": False, "partial_protected": False,
            "half_protected": False, "dealer_player_pending_credit": None,
        }
        self._four_aces_fd    = False
        self._ace_credits     = []    # player names who received A-clubs
        self._initial_dealt   = False  # True once all first-deal cards are entered
        self._pending_resolved = []  # buffered (player_name, hand, dealer_bj) — fired at endround
        self._pending_eor_msgs = []  # BJ bonuses + four-aces-endround — buffered for halving

        # Bust vote side bet (Rules.md §4.4) — host-togglable, reset every round
        self.bust_vote_enabled = bust_vote_enabled
        self._bust_votes       = {}   # player name -> "bust" (abstain = not present)
        self._bust_vote_result = None  # set by _resolve_bust_votes() for summary display

        # Tracker — resolves recipients and logs drinks
        self.tracker = DrinkTracker(players, self._get_dealer())

    # ---------------------------------------------------------------- helpers

    def _log(self, *args, **kwargs):
        """print() that respects self.verbose — silenced by the web layer
        so the terminal stays clean while playing online, but preserved
        for the interactive CLI session."""
        if self.verbose:
            print(*args, **kwargs)

    def _get_dealer(self) -> Player:
        return self._player_map.get(self.dealer_name.lower())

    def _get_player(self, name: str) -> Player:
        return self._player_map.get(name.strip().lower())

    def _get_hand(self, player: Player, hand_label: str) -> Hand:
        """
        Resolve a player's betting hand by label ('hand1', 'hand2', ...).

        Note: the dealer-player also has their own player hands. To target
        the dealer's *dealer hand*, use the literal 'dealer' keyword (handled
        explicitly in cmd_deal / cmd_result / cmd_dealer); never via this
        helper. That way clicking the "Player1" button still routes to
        Player1's own player hands when Player1 happens to be the dealer.
        """
        try:
            idx = int(hand_label.lower().replace("hand", "").strip()) - 1
        except (ValueError, AttributeError):
            idx = 0
        while len(player.hands) <= idx:
            player.hands.append(Hand())
        return player.hands[idx]

    # ---------------------------------------------------------------- setup round

    def start_round(self, digital=False):
        self.round_count += 1
        # Rebuild index to pick up any players added after __init__
        self._player_map = {p.name.lower(): p for p in self.all_players}
        self._all_names  = [p.name for p in self.all_players]
        self._log(f"\n{'='*52}")
        self._log(f"  ROUND {self.round_count}  |  Dealer: {self.dealer_name}")
        self._log("="*52)
        if not digital:
            self._log("  Enter cards as they are dealt. Type 'help' for commands.\n")

        # Reset all player hands and drink logs
        for p in self.all_players:
            if p.is_dealer:
                p.dealer_hand = Hand()
                p.drink_log   = []
                # Also reset player hands for dealer-player
                p.hands = [Hand() for _ in range(self.num_hands)]
            else:
                p.hands     = [Hand() for _ in range(self.num_hands)]
                p.drink_log = []

        self._ace_clubs_flag  = {
            "protected": False, "partial_protected": False,
            "half_protected": False, "dealer_player_pending_credit": None,
        }
        self._four_aces_fd    = False
        self._ace_credits     = []
        self._initial_dealt   = False
        self._pending_resolved = []
        self._pending_eor_msgs = []
        self._bust_votes        = {}
        self._bust_vote_result  = None
        self.tracker = DrinkTracker(self.all_players, self._get_dealer())

    # ---------------------------------------------------------------- command: deal

    def cmd_deal(self, parts: list):
        """deal <player> <card> [hand<n>]"""
        if len(parts) < 3:
            self._log("  Usage: deal <player> <card> [hand<n>]")
            self._log("  Example: deal Rob Ah hand1   |   deal dealer 7d")
            return

        player_name = parts[1]
        card_str    = parts[2]
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        # Resolve player. The literal keyword "dealer" targets the dealer hand;
        # using the dealer-player's own name (e.g. "deal Rob ah hand1" when Rob
        # is the dealer) targets that player's regular betting hands so the
        # dealer can still play their own seat.
        is_dealer_seat = (player_name.lower() == "dealer")
        if is_dealer_seat:
            player = self._get_dealer()
        else:
            player = self._get_player(player_name)

        if not player:
            self._log(f"  Unknown player '{player_name}'. Known: {', '.join(self._all_names)}")
            return

        # Parse card
        try:
            card = parse_card(card_str)
        except ValueError as e:
            self._log(f"  {e}")
            return

        # Get hand
        if is_dealer_seat:
            hand = player.dealer_hand
            recipient_name = self.dealer_name
        else:
            hand = self._get_hand(player, hand_label)
            recipient_name = player.name

        # First card of the round locks in any bust-vote side bets (Rules.md §4.4
        # — votes are placed "before the first deal").
        self._initial_dealt = True

        # Add card to hand
        card_pos = len(hand.cards) + 1
        hand.cards.append(card)
        self._log(f"  {recipient_name} {'(dealer) ' if is_dealer_seat else ''}"
              f"{hand_label if not is_dealer_seat else ''}: dealt {card}  "
              f"-> {hand}")

        # Fire ace rules immediately
        msgs = DrinkingRules.handle(CardDealtEvent(
            card=card, recipient=recipient_name, card_pos=card_pos,
            all_names=self._all_names, dealer_name=self.dealer_name,
            ace_clubs_flag=self._ace_clubs_flag,
            is_dealer_hand=is_dealer_seat,   # True only for the dealer hand, not betting hands
        ))
        for msg in msgs:
            _, s, reason = msg[0], msg[1], msg[2]
            if s == -1:
                self._ace_credits.append(recipient_name)
                self._log(f"    (i) {reason}")
            else:
                self.tracker.apply([msg])   # pass full tuple; apply() extracts optional role

        # Check for blackjack on first two cards
        if len(hand.cards) == 2 and hand.is_blackjack() and not is_dealer_seat:
            self._log(f"  *** {recipient_name} has BLACKJACK! ***")
            self._log(
                f"  (Use 'action {recipient_name} insurance {hand_label}' "
                f"if dealer shows A and they want to insure)")

    # ---------------------------------------------------------------- command: action

    def cmd_action(self, parts: list):
        """action <player> <action> [hand<n>]"""
        if len(parts) < 3:
            self._log("  Usage: action <player> <action> [hand<n>]")
            self._log("  Actions: double, split, insurance, blackjack")
            return

        player_name = parts[1]
        action      = parts[2].lower()
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        player = self._get_player(player_name)
        if not player:
            self._log(f"  Unknown player '{player_name}'.")
            return

        hand = self._get_hand(player, hand_label)

        if action == "double":
            hand.doubled = True
            self._log(f"  {player.name} {hand_label}: marked as doubled.")

        elif action == "split":
            # Create a new hand for the split
            new_hand = Hand(from_split=True)
            hand.from_split   = True
            new_hand._split_chain = hand._split_chain  # share counter across the whole chain
            hand.split_count += 1
            idx = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
            player.hands.insert(idx + 1, new_hand)
            new_label = f"hand{idx + 2}"
            self._log(f"  {player.name} splits {hand_label} -> {hand_label} + {new_label}")
            self._log(f"  Now deal one card each to {hand_label} and {new_label}.")

        elif action == "insurance":
            if not hand.is_blackjack():
                self._log("  Insurance only applies when the player has a Blackjack (dealer shows Ace).")
                return
            hand.insured = True
            self._log(f"  {player.name} {hand_label}: insured — Blackjack plays as regular 21, no bonus drinks.")

        elif action in ("blackjack", "bj"):
            hand.stood = True
            self._log(f"  {player.name} {hand_label}: BLACKJACK confirmed.")
            self._pending_eor_msgs.extend(DrinkingRules.handle(BlackjackEvent(
                player_name=player.name, hand=hand, all_names=self._all_names,
            )))

        else:
            self._log(f"  Unknown action '{action}'. Use: double, split, insurance, blackjack")

    # ---------------------------------------------------------------- command: result

    def cmd_result(self, parts: list):
        """result <player> <win|loss|push|bust> [hand<n>]"""
        if len(parts) < 3:
            self._log("  Usage: result <player> <win|loss|push|bust> [hand<n>]")
            self._log("  Special: 'result dealer bust' marks dealer bust (all non-bust players win)")
            return

        player_name = parts[1]
        outcome     = parts[2].lower()
        hand_label  = parts[3] if len(parts) > 3 else "hand1"

        # Special case: dealer bust (only via the literal "dealer" keyword —
        # the dealer-player's own name is reserved for their player hands).
        if player_name.lower() == "dealer" and outcome == "bust":
            dealer = self._get_dealer()
            dealer.dealer_hand.bust = True
            self._log("  Dealer busts. Mark each non-busted player hand as 'win'.")
            # Check dealer suited hand
            self.tracker.apply(DrinkingRules.handle(
                DealerHandRevealedEvent(dealer_hand=dealer.dealer_hand)))
            return

        player = self._get_player(player_name)
        if not player:
            self._log(f"  Unknown player '{player_name}'.")
            return

        hand = self._get_hand(player, hand_label)

        if outcome in ("win", "loss", "push"):
            hand.result = outcome
            self._log(f"  {player.name} {hand_label}: {outcome.upper()}")
            dealer    = self._get_dealer()
            dealer_bj = bool(dealer and dealer.dealer_hand and dealer.dealer_hand.is_blackjack())
            if hand.is_blackjack() and outcome == "win" and not hand.insured:
                self._pending_eor_msgs.extend(DrinkingRules.handle(BlackjackEvent(
                    player_name=player.name, hand=hand, all_names=self._all_names,
                )))
            # Buffer on_hand_resolved — fired at endround once hard_switch is known
            self._pending_resolved.append((player.name, hand, dealer_bj))
        elif outcome == "bust":
            hand.result = "loss"
            hand.bust   = True
            self._log(f"  {player.name} {hand_label}: BUST => LOSS")
        else:
            self._log(f"  Unknown outcome '{outcome}'. Use: win, loss, push, bust")

    # ---------------------------------------------------------------- command: dealer reveal

    def cmd_dealer(self, parts: list):
        """dealer <final|suited|bust|blackjack> — mark the dealer's final state"""
        if len(parts) < 2:
            self._log("  Usage: dealer <final|suited|bust|blackjack>")
            return

        sub = parts[1].lower()
        dealer = self._get_dealer()

        if sub == "final":
            # Trigger dealer-suited-hand check
            self.tracker.apply(DrinkingRules.handle(
                DealerHandRevealedEvent(dealer_hand=dealer.dealer_hand)))
            self._log(f"  Dealer final hand checked: {dealer.dealer_hand}")

        elif sub == "bust":
            dealer.dealer_hand.bust = True
            self.tracker.apply(DrinkingRules.handle(
                DealerHandRevealedEvent(dealer_hand=dealer.dealer_hand)))
            self._log("  Dealer bust registered.")

        elif sub == "blackjack":
            dealer.dealer_hand.stood = True
            self._log("  Dealer blackjack registered.")

        else:
            self._log(f"  Unknown dealer command '{sub}'. Use: final, bust, blackjack")

    # ---------------------------------------------------------------- command: four aces

    def cmd_fouraces(self, parts: list):
        """fouraces <firstdeal|endround> — manually trigger four-aces check"""
        phase_map = {"firstdeal": "first_deal", "endround": "end_of_round"}
        phase = phase_map.get(parts[1].lower() if len(parts) > 1 else "", "")
        if not phase:
            self._log("  Usage: fouraces <firstdeal|endround>")
            return
        all_cards = [c for p in self.all_players for h in p.hands for c in h.cards]
        if self._get_dealer():
            all_cards += self._get_dealer().dealer_hand.cards
        msgs, self._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, phase, self._four_aces_fd)
        if phase == "first_deal":
            self.tracker.apply(msgs)   # mid-round, not halved
        else:
            self._pending_eor_msgs.extend(msgs)  # end-of-round, halved

    # ---------------------------------------------------------------- command: bust vote

    def cmd_bustvotetoggle(self, parts: list):
        """bustvotetoggle <on|off> — host toggles the dealer-bust side bet (Rules.md §4.4)."""
        if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
            self._log("  Usage: bustvotetoggle <on|off>")
            return
        self.bust_vote_enabled = (parts[1].lower() == "on")
        state = "enabled" if self.bust_vote_enabled else "disabled"
        self._log(f"  Bust vote side bet {state}.")
        if not self.bust_vote_enabled:
            self._bust_votes = {}

    def cmd_bustvote(self, parts: list):
        """bustvote <player> <bust|skip> — side bet on dealer bust, before the first deal."""
        if not self.bust_vote_enabled:
            self._log("  Bust vote side bet is disabled. Use 'bustvotetoggle on' first.")
            return
        if len(parts) < 3:
            self._log("  Usage: bustvote <player> <bust|skip>")
            return
        if self._initial_dealt:
            self._log("  Bust votes must be placed before the first deal.")
            return

        player_name = parts[1]
        vote        = parts[2].lower()
        player      = self._get_player(player_name)
        if not player:
            self._log(f"  Unknown player '{player_name}'. Known: {', '.join(self._all_names)}")
            return

        if vote in ("bust", "b"):
            self._bust_votes[player.name] = "bust"
            self._log(f"  {player.name} bets the Dealer will bust this round.")
        elif vote in ("skip", "no", "n", "abstain"):
            self._bust_votes.pop(player.name, None)
            self._log(f"  {player.name} skips the bust side bet.")
        else:
            self._log("  Vote must be 'bust' or 'skip'.")

    def _resolve_bust_votes(self):
        """
        Resolve Rules.md §4.4 — fires once per round, called from cmd_endround
        after the dealer's final hand is known.

        Correct 'bust' voters: -1 sip credit, then hand out 1 sip to another
        player (interactive for humans, round-robin for NPCs).
        Incorrect 'bust' voters: +1 sip penalty.
        Never halved (Instant Effect rule — see Rules.md §6.1).
        """
        self._bust_vote_result = None
        if not self.bust_vote_enabled or not self._bust_votes:
            return

        dealer = self._get_dealer()
        if not dealer or not dealer.dealer_hand:
            return

        dealer_busted = dealer.dealer_hand.bust or dealer.dealer_hand.is_bust()
        winners, losers = [], []

        for name in list(self._bust_votes):
            p = self._get_player(name)
            if not p:
                continue
            if dealer_busted:
                p.add_drink(-1, f"{name} bust vote correct: -1 sip credit", "player")
                winners.append(name)
                if self.verbose:
                    print(f"    (i) {name} called the Dealer bust correctly "
                          f"— -1 sip credit, hands out 1 sip")
            else:
                p.add_drink(1, "Bust vote wrong — dealer didn't bust: +1 sip", "player")
                losers.append(name)
                if self.verbose:
                    print(f"    [drink] {name}: Bust vote wrong — dealer didn't bust: +1 sip")

        self._bust_vote_result = {
            "dealer_busted": dealer_busted,
            "winners":       winners,
            "losers":        losers,
        }

        for name in winners:
            self.tracker._handle_handout(
                name, 1, f"{name} won the bust vote — hands out 1 sip", label="bust vote")

    # ---------------------------------------------------------------- command: endround

    def cmd_endround(self, skip_sweep: bool = False, extra_eor_msgs=None):
        """Finalise the round — fire end-of-round rules and print summary.
        skip_sweep: pass True in digital mode (dealer_turn already fired it).
        extra_eor_msgs: msgs buffered by dealer_turn (digital mode) that must
        be combined with this round's msgs before halving is applied."""
        self._log("\n--- End of Round ---")

        # Bust vote side bet (instant effect, never halved) — resolved first so
        # it appears in each player's drink_log alongside the round's other drinks.
        self._resolve_bust_votes()

        # Hard dealer switch check
        dealer  = self._get_dealer()
        players = [p for p in self.all_players if not p.is_dealer or p.hands]
        winning = []
        dealer_lost_all = True
        for p in players:
            for hand in p.hands:
                if hand.result == "win":
                    winning.append((p.name, hand))
                elif hand.result in ("loss", "push"):
                    dealer_lost_all = False

        hard_switch   = dealer_lost_all and bool(winning)
        exempt_dealer = self.dealer_name if hard_switch else ""

        # Collect all end-of-round drink messages so 4-player halving
        # operates on each player's total for the round, not per event.
        # Start with any msgs buffered by dealer_turn (digital mode bonuses).
        eor_msgs = list(extra_eor_msgs or []) + list(self._pending_eor_msgs)
        self._pending_eor_msgs = []

        # Fire buffered on_hand_resolved calls — now we know if it's a hard switch
        for p_name, hand, dealer_bj_at_time in self._pending_resolved:
            eor_msgs.extend(DrinkingRules.handle(HandResolvedEvent(
                player_name=p_name, hand=hand, all_names=self._all_names,
                dealer_bj=dealer_bj_at_time, dealer_name=exempt_dealer,
            )))
        self._pending_resolved = []
        # _pending_eor_msgs already drained above when building eor_msgs

        if hard_switch and not getattr(self, "_hard_switch_drinking_applied", False):
            partial_protected = self._ace_clubs_flag.get("partial_protected", False)
            half_protected    = self._ace_clubs_flag.get("half_protected", False)
            # Partial protection (player-hand A♣): exclude dealer's own hands
            hs_for_penalty = (
                [h for h in winning if h[0].lower() != self.dealer_name.lower()]
                if partial_protected else winning
            )
            # Insurance Case 2, sub-case B: dealer-player IS the BJ holder,
            # group voted insure, no dealer BJ → exclude their BJ from Hard Switch
            # (insurance rule covers it; they drink nothing from insurance and the
            # group drinks double instead).
            dealer_bj_insured = (
                not dealer_bj
                and any(
                    pn.lower() == self.dealer_name.lower()
                    and h.is_blackjack() and getattr(h, "insured", False)
                    for (pn, h) in winning
                )
            )
            if dealer_bj_insured:
                hs_for_penalty = [
                    (pn, h) for (pn, h) in hs_for_penalty
                    if not (pn.lower() == self.dealer_name.lower() and h.is_blackjack())
                ]
            eor_msgs.extend(DrinkingRules.handle(HardDealerSwitchEvent(
                dealer_name=self.dealer_name, winning_hands=hs_for_penalty,
                half_protected=half_protected,
            )))

        # Round-end rules (net losses, sweeps)
        w         = self.wager
        dealer    = self._get_dealer()
        dealer_bj = bool(dealer and dealer.dealer_hand and dealer.dealer_hand.is_blackjack())

        # Insurance resolution — for hands marked insured via the INSURANCE button
        if not hasattr(self, "_insurance_result") or self._insurance_result is None:
            self._insurance_result = []
        for p in players:
            if p.is_dealer:
                continue
            for hand in p.hands:
                if hand.is_blackjack() and getattr(hand, "insured", False):
                    eor_msgs.extend(DrinkingRules.handle(InsuranceResolvedEvent(
                        player_name=p.name, hand=hand, all_names=self._all_names,
                        insured=True, dealer_bj=dealer_bj,
                        hard_switch_dealer=exempt_dealer,
                    )))
                    self._insurance_result.append({
                        "player":    p.name,
                        "insured":   True,
                        "dealer_bj": dealer_bj,
                        "group_won": dealer_bj,  # insure+BJ = group protected (won)
                    })

        # All-hands sweep (same suit or all-21 across split hands).
        # Skipped in digital mode — dealer_turn() already fired it before cmd_endround().
        if not skip_sweep:
            for p in players:
                if p.is_dealer:
                    continue
                try:
                    eor_msgs.extend(DrinkingRules.handle(AllHandsSweepEvent(
                        player_name=p.name, player_hands=p.hands, all_names=self._all_names,
                        wager=self.wager, dealer_name=self.dealer_name if hard_switch else "",
                        dealer_bj=dealer_bj,
                    )))
                except Exception as e:
                    self._log(f"  Error occurred while checking all-hands sweep for {p.name}: {e}")
        if dealer and dealer.dealer_hand and DrinkingRules.dealer_21_five_cards(dealer.dealer_hand):
            w *= 2
            self._log(
                f"\n  ★ Dealer 21 with {len(dealer.dealer_hand.cards)} cards "
                f"— wager doubled to {w} sip(s) this round!"
                )
        if dealer_bj:
            self._log("\n  ★ Dealer blackjack — auto-insurance: only net-loss sips apply.")
        eor_msgs.extend(DrinkingRules.handle(RoundEndEvent(
            players=players, wager=w, dealer_bj=dealer_bj,
            hard_switch_dealer=self.dealer_name if hard_switch else "",
            num_hands=self.num_hands,
        )))

        # Apply all end-of-round drinks together so 4-player halving
        # operates on each player's total for the round, not per event.
        self.tracker.apply_end_of_round(eor_msgs)

        # Ace-of-clubs credits applied AFTER halving — post-round adjustments, not subject to halving.
        for name in self._ace_credits:
            p = self._get_player(name)
            if p: self.tracker.apply_ace_clubs_credit(p)

        # Dealer-player A♣ deferred credit: apply only if no hard switch fired.
        # On a hard switch the partial protection IS the benefit — no double-dipping.
        pending_credit = self._ace_clubs_flag.get("dealer_player_pending_credit")
        if pending_credit and not hard_switch:
            p = self._get_player(pending_credit)
            if p:
                self.tracker.apply_ace_clubs_credit(p)
                self._log(f"    (i) A♣ credit applied to {pending_credit} (no hard switch this round)")

        # Update cumulative stats
        for p in players:
            p.total_wins   += p.round_wins()
            p.total_losses += p.round_losses()
            p.total_pushes += p.round_pushes()

        # Print
        self._show_results()
        self.tracker.print_round_summary()

    # ---------------------------------------------------------------- command: status

    def cmd_status(self):
        """Show the current state of all hands this round."""
        self._log("\n--- Current Round State ---")
        rows = []
        for p in self.all_players:
            for i, h in enumerate(p.hands):
                tag = " (dealer)" if p.is_dealer else ""
                rows.append([
                    f"{p.name}{tag} H{i+1}",
                    str(h),
                    h.result.upper() if h.result else "-"
                ])
            if p.is_dealer and p.dealer_hand:
                rows.append([
                    f"{p.name} (dealer hand)",
                    str(p.dealer_hand),
                    "BUST" if p.dealer_hand.bust else "-"
                ])
        self._log(tabulate(rows, headers=["Seat", "Hand", "Result"], tablefmt="pretty"))

    # ---------------------------------------------------------------- show results

    def _show_results(self):
        self._log("\n" + "="*52)
        self._log("  ROUND RESULTS")
        self._log("="*52)
        rows = []
        for p in self.all_players:
            for i, h in enumerate(p.hands):
                rows.append([f"{p.name} H{i+1}", str(h),
                             h.result.upper() if h.result else "-"])
        dealer = self._get_dealer()
        if dealer and dealer.dealer_hand:
            dh = dealer.dealer_hand
            rows.append([f"Dealer ({self.dealer_name})", str(dh),
                         "BJ" if dh.is_blackjack() else
                         "BUST" if dh.is_bust() else str(dh.score())])
        self._log(tabulate(rows, headers=["Seat", "Hand", "Result"], tablefmt="pretty"))
        self._log("="*52)

    # ---------------------------------------------------------------- help

    @staticmethod
    def print_help():
        help_text = """
  REFEREE COMMANDS
  ================
  deal <player> <card> [hand<n>]
      Register a card dealt to a player or the dealer.
      Card format: <rank><suit>  e.g. Ah  10s  Kd  3c
      Suit: h=hearts d=diamonds c=clubs s=spades
      Example: deal Rob Ah hand1
               deal dealer 7d

  action <player> <action> [hand<n>]
      Register a player action.
      Actions: double  split  insurance  blackjack
      Example: action Rob double hand1
               action Markoi split hand2
               action David insurance hand1
               action Rob blackjack hand1

  result <player> <outcome> [hand<n>]
      Set the outcome of a hand.
      Outcomes: win  loss  push  bust
      Special:  result dealer bust
      Example: result Rob win hand1
               result Markoi push hand2
               result dealer bust

  dealer <sub>
      Mark the dealer's final state.
      Sub-commands: final  bust  blackjack
      Example: dealer final
               dealer bust

  fouraces <firstdeal|endround>
      Manually trigger the four-aces check.

  bustvotetoggle <on|off>
      Host toggles the dealer-bust side bet on/off (can change any time).

  bustvote <player> <bust|skip>
      Before the first deal: Player bets the Dealer will bust this round.
      Correct => -1 sip + hand out 1 sip. Wrong => +1 sip. (Rules.md §4.4)
      Example: bustvote Rob bust
               bustvote Markoi skip

  endround
      Finalise the round — fires all end-of-round drink rules
      and prints the full drink summary.

  newround
      Start a new round (resets all hands).

  status
      Show the current state of all hands.

  quit / exit
      Exit the referee session.
"""
        print(help_text)
