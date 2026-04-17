"""
drinking_rules.py
=================
Drinking layer for Blackjack.
Imported by blackjack.py (drinking mode) and referee.py.
Has no game logic of its own — purely reacts to events fired by the game.

Rules sourced from:
https://github.com/robert-rjm/Drinking-BlackJack/blob/7e4b344dfe1ade7e047bdef96310619a0533d4cd/Rules.md

__rules_source_commit__  = "7e4b344dfe1ade7e047bdef96310619a0533d4cd"
__rules_source_url__     = "https://github.com/robert-rjm/Drinking-BlackJack/blob/7e4b344/Rules.md"
__rules_last_verified__  = "2026-04-11"
"""

from blackjack import Rank, Suit, Hand, Player


# =============================================================================
# Internal helpers
# =============================================================================

def _bj_multiplier(hand: Hand) -> int:
    """Cumulative x2 multiplier for blackjack bonus sips."""
    mult  = 1
    ranks = {c.rank for c in hand.cards}
    suits = {c.suit for c in hand.cards}
    black = {Suit.SPADES, Suit.CLUBS}
    if hand.is_suited():                          mult *= 2
    if {Rank.ACE, Rank.JACK}.issubset(ranks):     mult *= 2
    if suits.issubset(black):                     mult *= 2
    return mult


# =============================================================================
# DrinkingRules
# =============================================================================

class DrinkingRules:
    """
    All methods return list of (recipient, sips, reason) tuples.

    recipient:
        player name   — that specific player drinks
        'all'         — every player at the table (including dealer-player)
        'players_only'— everyone except the dealer-role player
        None          — informational only, no drink assigned

    sips:
        > 0  — drinks to assign
        = 0  — informational message only
        < 0  — recipient may HAND OUT that many sips to others
    """

    # ---------------------------------------------------------------- card dealt

    @staticmethod
    def on_card_dealt(card, recipient: str, card_pos: int,
                      all_player_names: list, dealer_name: str,
                      ace_clubs_flag: dict) -> list:
        """
        Called immediately after each card is physically dealt.
        card_pos: 1-indexed position of this card in the recipient's current hand.
        ace_clubs_flag: mutable {'protected': bool} shared for the whole round.
        Only fires on Aces — all other cards return [].
        """
        if card.rank != Rank.ACE:
            return []

        msgs      = []
        s         = card.suit
        is_dealer = (recipient == dealer_name)

        if not is_dealer:
            if s == Suit.CLUBS:
                msgs.append((recipient, -1,
                    f"A{s.symbol} dealt to {recipient} => -1 sip credit at round end"))
            elif s == Suit.SPADES:
                idx    = all_player_names.index(recipient)
                target = all_player_names[(idx + card_pos) % len(all_player_names)]
                msgs.append((target, 1,
                    f"A{s.symbol} dealt to {recipient} (card #{card_pos}) => {target} drinks 1 sip"))
            elif s == Suit.HEARTS:
                msgs.append((recipient, 1,
                    f"A{s.symbol} dealt to {recipient} => {recipient} drinks 1 sip"))
            elif s == Suit.DIAMONDS:
                msgs.append((dealer_name, 1,
                    f"A{s.symbol} dealt to {recipient} => {dealer_name} (dealer) drinks 1 sip"))
        else:
            if s == Suit.CLUBS:
                ace_clubs_flag["protected"] = True
                msgs.append((None, 0,
                    f"A{s.symbol} dealt to dealer ({dealer_name}) => exempt from Hard Switch drinking"))
            elif s == Suit.SPADES:
                if card_pos % 2 == 1:
                    msgs.append((dealer_name, 1,
                        f"A{s.symbol} to dealer (card #{card_pos}, odd) => {dealer_name} drinks 1 sip"))
                else:
                    msgs.append(("all", 1,
                        f"A{s.symbol} to dealer (card #{card_pos}, even) => everyone drinks 1 sip"))
            elif s == Suit.HEARTS:
                msgs.append(("all", 1,
                    f"A{s.symbol} dealt to dealer => everyone drinks 1 sip"))
            elif s == Suit.DIAMONDS:
                msgs.append(("players_only", 1,
                    f"A{s.symbol} dealt to dealer => all non-dealer players drink 1 sip"))

        return msgs

    # ---------------------------------------------------------------- four aces

    @staticmethod
    def check_four_aces(all_cards: list, phase: str,
                        triggered_first_deal: bool) -> tuple:
        """
        Check if all 4 aces are visible.
        phase: 'first_deal' | 'end_of_round'
        Returns (msgs, triggered_first_deal).
        These two phases cannot stack — first deal takes priority.
        """
        if sum(1 for c in all_cards if c.rank == Rank.ACE) < 4:
            return [], triggered_first_deal
        if phase == "first_deal":
            return [("all", 2,
                "All 4 Aces on table after first deal => everyone drinks 2 sips")], True
        if phase == "end_of_round" and not triggered_first_deal:
            return [("all", 1,
                "All 4 Aces visible at end of round => everyone drinks 1 sip")], False
        return [], triggered_first_deal

    # ---------------------------------------------------------------- blackjack bonus

    @staticmethod
    def on_blackjack(player_name: str, hand: Hand,
                     all_player_names: list) -> list:
        """
        Called when any player gets a natural blackjack.
        If insured, bonus drinks are suppressed (hand treated as regular 21).
        Multipliers: suited x2, A+J x2, both black x2 — cumulative.
        """
        if hand.insured:
            return [(None, 0,
                f"{player_name} insured their blackjack => no bonus drinks")]

        mult   = _bj_multiplier(hand)
        sips   = mult
        parts  = []
        ranks  = {c.rank for c in hand.cards}
        suits  = {c.suit for c in hand.cards}
        if hand.is_suited():                                parts.append("suited x2")
        if {Rank.ACE, Rank.JACK}.issubset(ranks):           parts.append("A+J x2")
        if suits.issubset({Suit.SPADES, Suit.CLUBS}):       parts.append("both black x2")
        detail = f" ({' '.join(parts)})" if parts else ""
        others = [p for p in all_player_names if p != player_name]
        return [(p, sips,
                 f"Blackjack by {player_name}{detail} => {p} drinks {sips} sip(s)")
                for p in others]

    # ---------------------------------------------------------------- hand resolved

    @staticmethod
    def on_hand_resolved(player_name: str, hand: Hand,
                         all_player_names: list) -> list:
        """
        Called after each hand is evaluated. Fires rules for:
        - Doubles/splits (immunity exception)
        - Suited winning hand
        - 21 with 5+ cards (hand-out entitlement)
        - Win with 5+ cards
        """
        if hand.result != "win":
            return []

        msgs   = []
        others = [p for p in all_player_names if p != player_name]

        # Doubles / splits break immunity
        if hand.doubled or hand.from_split:
            label = "doubled" if hand.doubled else "split"
            for p in others:
                msgs.append((p, 1,
                    f"{player_name} won a {label} hand => {p} drinks 1 sip (immunity exception)"))

        # Suited winning hand
        if hand.is_suited():
            sips = 4 if (hand.doubled or hand.from_split) else 1
            sym  = hand.cards[0].suit.symbol
            for p in others:
                msgs.append((p, sips,
                    f"{player_name} won suited hand (all {sym}) => {p} drinks {sips} sip(s)"))

        # 21 with 5+ cards: player hands out sips
        if hand.score() == 21 and len(hand.cards) >= 5:
            msgs.append((player_name, -len(hand.cards),
                f"{player_name} hit 21 with {len(hand.cards)} cards => may hand out {len(hand.cards)} sips"))

        # Win with 5+ cards (stacks with above if score is 21)
        if len(hand.cards) >= 5:
            for p in others:
                msgs.append((p, 1,
                    f"{player_name} won with {len(hand.cards)} cards => {p} drinks 1 sip"))

        return msgs

    # ---------------------------------------------------------------- dealer suited hand

    @staticmethod
    def on_dealer_hand_revealed(dealer_hand: Hand) -> list:
        """
        Called once the dealer's full hand is visible.
        Fires regardless of win/loss/bust.
        """
        if dealer_hand.is_suited() and len(dealer_hand.cards) >= 2:
            sym = dealer_hand.cards[0].suit.symbol
            return [("all", 2, f"Dealer hand is all {sym} => everyone drinks 2 sips")]
        return []

    # ---------------------------------------------------------------- round end

    @staticmethod
    def on_round_end(players: list, wager: int) -> list:
        """
        Called once all hands are resolved.
        Fires:
        - Net hand losses (wins offset losses; only net negative costs sips)
        - Other-player-wins-all rule (with immunity tiers)
        """
        msgs = []

        # Net losses
        for p in players:
            net = p.net_losses()
            if net > 0:
                msgs.append((p.name, net * wager,
                    f"{p.name} net -{net} hand(s) => drinks {net * wager} sip(s) (net loss)"))

        # Other-player-wins-all
        for winner in players:
            if winner.round_losses() > 0 or winner.round_pushes() > 0:
                continue
            w_wins = winner.round_wins()
            for other in players:
                if other is winner: continue
                o_wins   = other.round_wins()
                o_losses = other.round_losses()
                o_pushes = other.round_pushes()
                if   o_losses == 0 and o_pushes == 0: sips = 0       # immune
                elif o_losses == 0:                   sips = max(0, w_wins - o_wins)
                else:                                 sips = w_wins
                if sips > 0:
                    msgs.append((other.name, sips,
                        f"{winner.name} swept all hands => {other.name} drinks {sips} sip(s)"))

        return msgs

    # ---------------------------------------------------------------- hard dealer switch

    @staticmethod
    def on_hard_dealer_switch(dealer_name: str, winning_hands: list,
                               protected: bool) -> list:
        """
        Called when the dealer loses ALL hands (push != loss).
        winning_hands: list of (player_name, Hand) tuples.
        Dealer drinks per each winning hand type.
        Ace of Clubs protection skips the drinking (switch still happens).
        """
        if protected:
            return [(None, 0,
                f"Hard Switch triggered — A♣ protects {dealer_name} from drinking")]

        total = 0
        lines = []
        for pname, hand in winning_hands:
            if hand.is_blackjack():
                s = max(2, _bj_multiplier(hand))
                lines.append(f"{pname} blackjack => {s} sip(s)")
            elif hand.doubled:
                s = 2
                lines.append(f"{pname} doubled win => 2 sips")
            else:
                s = 1
                lines.append(f"{pname} regular win => 1 sip")
            total += s

        detail = "; ".join(lines)
        return [(dealer_name, total,
            f"Hard Dealer Switch: {dealer_name} drinks {total} sip(s) ({detail})")]


# =============================================================================
# DrinkTracker
# =============================================================================

class DrinkTracker:
    """
    Resolves recipient tokens to Player objects, logs each drink with its
    full reason, and prints a detailed breakdown at round end.

    Used by both blackjack.py (digital game) and referee.py (real-life session).
    """

    def __init__(self, players: list, dealer_player):
        self.players       = players
        self.dealer_player = dealer_player
        self._map          = {p.name.lower(): p for p in players}

    # ---------------------------------------------------------------- resolution

    def _resolve(self, recipient: str) -> list:
        if recipient == "all":
            return list(self.players)
        if recipient == "players_only":
            return [p for p in self.players if not p.is_dealer]
        p = self._map.get(str(recipient).lower())
        return [p] if p else []

    # ---------------------------------------------------------------- apply

    def apply(self, msgs: list):
        """Apply a list of (recipient, sips, reason) tuples."""
        for recipient, sips, reason in msgs:
            if recipient is None or sips == 0:
                if reason: print(f"    (i) {reason}")
                continue
            if sips < 0:
                self._handle_handout(recipient, abs(sips), reason)
                continue
            for t in self._resolve(recipient):
                t.add_drink(sips, reason)
            print(f"    [drink] {reason}")

    # ---------------------------------------------------------------- ace of clubs credit

    def apply_ace_clubs_credit(self, player: Player):
        """
        Apply -1 sip credit from Ace of Clubs AFTER net losses are calculated.
        Minimum net result is 0 (credit cannot go negative).
        """
        if player.drinks_owed() > 0:
            player.add_drink(-1, f"{player.name} A♣ credit: -1 sip")
            print(f"    (i) {player.name} A♣ credit applied: -1 sip")

    # ---------------------------------------------------------------- handout

    def _handle_handout(self, giver: str, total: int, reason: str):
        """
        Handle 5-card-21 sip handout.
        NPC givers distribute round-robin automatically.
        Human givers are prompted interactively.
        """
        print(f"    [drink] {reason}")
        others = [p for p in self.players if p.name.lower() != giver.lower()]
        if not others: return

        giver_player = self._map.get(giver.lower())
        remaining    = total

        if getattr(giver_player, "is_npc", False):
            for i in range(remaining):
                t = others[i % len(others)]
                t.add_drink(1, f"{giver} (NPC) handed 1 sip to {t.name} (5-card 21)")
                print(f"    -> {t.name} +1 sip (NPC auto-distributed)")
            return

        other_names = [p.name for p in others]
        print(f"    {giver}, hand out {remaining} sip(s) among: {', '.join(other_names)}")
        while remaining > 0:
            raw = input(f"    Who gets a sip? ({remaining} left): ").strip().capitalize()
            t   = self._map.get(raw.lower())
            if t and t.name.lower() != giver.lower():
                t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21)")
                remaining -= 1
                print(f"    -> {t.name} +1 sip")
            else:
                print(f"    Invalid. Choose from: {', '.join(other_names)}")

    # ---------------------------------------------------------------- summary

    def print_round_summary(self):
        print("\n" + "="*52)
        print("  DRINK SUMMARY")
        print("="*52)
        any_drinks = False
        for p in self.players:
            if p.name == "House": continue
            if not p.drink_log:   continue
            any_drinks = True
            net = p.drinks_owed()
            print(f"\n  {p.name}  =>  {net} sip(s) this round")
            for sips, reason in p.drink_log:
                sign = f"+{sips}" if sips > 0 else str(sips)
                print(f"    {sign:>4}  {reason}")
            p.total_drinks += max(0, net)
        if not any_drinks:
            print("  No drinks this round!")
        print("\n" + "="*52 + "\n")
