"""
drinking_rules.py
=================
Drinking layer for Blackjack.
Imported by blackjack.py (drinking mode) and referee.py.
Has no game logic of its own — purely reacts to events fired by the game.
"""

import math
from engine.blackjack import Rank, Suit, Hand, Player


# =============================================================================
# Internal helpers
# =============================================================================

def _bj_breakdown(hand: Hand) -> tuple[int, list[str]]:
    """Return (multiplier, label_parts) for a blackjack bonus hand.

    Single source of truth for the suited/A+J/both-black x2 conditions so
    callers that need the breakdown (on_blackjack label) and callers that
    only need the multiplier (serializer, resolve_insurance_vote) both derive
    from the same computation.
    """
    mult  = 1
    parts: list[str] = []
    ranks = {c.rank for c in hand.cards}
    suits = {c.suit for c in hand.cards}
    black = {Suit.SPADES, Suit.CLUBS}
    if hand.is_suited():
        mult *= 2; parts.append("suited x2")
    if {Rank.ACE, Rank.JACK}.issubset(ranks):
        mult *= 2; parts.append("A+J x2")
    if suits.issubset(black):
        mult *= 2; parts.append("both black x2")
    return mult, parts


def _bj_multiplier(hand: Hand) -> int:
    """Cumulative x2 multiplier for blackjack bonus sips."""
    mult, _ = _bj_breakdown(hand)
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
                      ace_clubs_flag: dict,
                      is_dealer_hand: bool = False) -> list:
        """
        Called immediately after each card is physically dealt.
        card_pos: 1-indexed position of this card in the recipient's current hand.
        ace_clubs_flag: mutable {'protected': bool} shared for the whole round.
        is_dealer_hand: True only when the card goes to the dealer's *dealer hand*,
                        NOT when it goes to the dealer-player's own betting hands.
        Only fires on Aces — all other cards return [].
        """
        if card.rank != Rank.ACE:
            return []

        msgs      = []
        s         = card.suit
        is_dealer = is_dealer_hand   # explicit flag — not a name comparison

        if not is_dealer:
            if s == Suit.CLUBS:
                if recipient.lower() == dealer_name.lower():
                    # Dealer-player A♣ on a player hand:
                    # Always grants partial Hard Switch protection (own hand losses exempt).
                    # -1 sip credit is deferred — applied at endround ONLY if no hard switch fires.
                    # On a hard switch the protection IS the benefit; no double-dipping.
                    ace_clubs_flag["partial_protected"] = True
                    ace_clubs_flag["dealer_player_pending_credit"] = recipient
                    msgs.append((None, 0,
                        f"A{s.symbol} dealt to {recipient} (also dealer) "
                        f"=> partial Hard Switch protection; -1 sip credit applies only if no hard switch"))
                else:
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
                    f"A{s.symbol} dealt to {recipient} => {dealer_name} (dealer) drinks 1 sip",
                    "dealer"))
        else:
            if s == Suit.CLUBS:
                ace_clubs_flag["half_protected"] = True
                msgs.append((None, 0,
                    f"A{s.symbol} dealt to dealer ({dealer_name})"
                    " => half Hard Switch protection (drinks ceil of total/2)"))
            elif s == Suit.SPADES:
                if card_pos % 2 == 1:
                    msgs.append((dealer_name, 1,
                        f"A{s.symbol} to dealer (card #{card_pos}, odd) => {dealer_name} drinks 1 sip",
                        "dealer"))
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
                     all_player_names: list,
                     hard_switch_dealer: str = "") -> list:
        """
        Called for uninsured blackjacks only (no group vote, or vote was decline
        and dealer had no blackjack). Fires normal BJ bonus drinks.
        Multipliers: suited x2, A+J x2, both black x2 — cumulative.
        hard_switch_dealer: dealer-player is exempt on a Hard Dealer Switch.
        """
        mult, parts = _bj_breakdown(hand)
        sips   = mult
        detail = f" ({' '.join(parts)})" if parts else ""
        others = [p for p in all_player_names
                  if p != player_name and p != hard_switch_dealer]
        return [(p, sips,
                 f"Blackjack by {player_name}{detail} => {p} drinks {sips} sip(s)")
                for p in others]

    @staticmethod
    def resolve_insurance_vote(player_name: str, hand: Hand,
                               all_player_names: list,
                               insured: bool, dealer_bj: bool,
                               hard_switch_dealer: str = "") -> list:
        """
        Resolve a group-voted insurance decision at round end.

        insured:    True if majority voted to insure, False if decline (tie = decline).
        dealer_bj:  True if dealer has a natural blackjack.
        hard_switch_dealer: dealer-player name when a Hard Dealer Switch is active.

        Insurance rules are independent of who is the dealer.  The Hard Dealer Switch
        only modifies the dealer-player's share in Case 2 (see below).

        Case 1 — Insure + dealer BJ (group bet correctly):
            BJ holder drinks own BJ Bonus; hand pushes. Group drinks nothing.

        Case 2 — Insure + no dealer BJ (group gambled wrong):
            BJ holder drinks nothing.
            Group drinks double BJ Bonus.
            Hard switch, dealer is a group member (not the BJ holder):
              dealer drinks 1× BJ Bonus only (softened — Hard Switch is their main
              penalty); the rest of the group still drinks double.
            Hard switch, dealer IS the BJ holder:
              BJ holder/dealer drinks nothing from insurance; group drinks double.
              Calling code must exclude dealer's BJ hand from the Hard Switch penalty.

        Case 3 — Decline + dealer BJ:
            Auto-insurance already handles the net-loss cap; nothing extra here.

        Case 4 — Decline + no dealer BJ:
            Normal BJ bonus (group drinks as usual).
        """
        mult   = _bj_multiplier(hand)
        # others: everyone except the BJ holder and (on hard switch) the dealer-player.
        # When player_name == hard_switch_dealer they are the same person.
        others = [p for p in all_player_names
                  if p != player_name and p != hard_switch_dealer]

        # ---- Case 1: insured + dealer BJ — group bet correctly ----
        if insured and dealer_bj:
            return [
                (player_name, mult,
                 f"Insurance (group voted insure) + dealer BJ: "
                 f"{player_name} drinks own BJ bonus {mult} sip(s), hand pushes, "
                 f"group protected"),
                (None, 0, f"{player_name}'s blackjack pushes (insured vs dealer BJ)"),
            ]

        # ---- Case 2: insured + no dealer BJ — group gambled wrong ----
        if insured and not dealer_bj:
            sips = mult * 2
            # Group (excl. BJ holder and dealer-player when hard switch) drinks double.
            msgs = [(p, sips,
                     f"Insurance (group voted insure) + no dealer BJ: "
                     f"{p} drinks double BJ bonus {sips} sip(s)")
                    for p in others]
            if hard_switch_dealer and hard_switch_dealer.lower() != player_name.lower():
                # Sub-case A: dealer is in the group but not the BJ holder.
                # Soften their insurance share to 1× — Hard Switch is their main penalty.
                msgs.append((hard_switch_dealer, mult,
                             f"Insurance (insured + no dealer BJ) + Hard Dealer Switch: "
                             f"{hard_switch_dealer} drinks BJ bonus {mult} sip(s) "
                             f"(not doubled — hard switch penalty applies separately)"))
            # Sub-case B: dealer IS the BJ holder (hard_switch_dealer == player_name).
            # BJ holder drinks nothing; group (others) already drinks double above.
            # Calling code is responsible for excluding dealer's BJ from Hard Switch.
            return msgs

        # ---- Case 3: declined + dealer BJ ----
        if not insured and dealer_bj:
            return [(None, 0,
                     f"{player_name} blackjack: group declined insurance, dealer has BJ "
                     f"=> auto-insurance applies, normal max sips only")]

        # ---- Case 4: declined + no dealer BJ — normal BJ bonus ----
        return DrinkingRules.on_blackjack(player_name, hand, all_player_names,
                                          hard_switch_dealer=hard_switch_dealer)

    # ---------------------------------------------------------------- hand resolved

    @staticmethod
    def on_hand_resolved(player_name: str, hand: Hand,
                         all_player_names: list,
                         dealer_bj: bool = False,
                         dealer_name: str = "") -> list:
        """
        Called after each hand is evaluated. Fires rules for:
        - Doubles/splits (immunity exception)
        - Suited winning hand
        - 21 with 5+ cards (hand-out entitlement)
        - Win with 5+ cards

        dealer_bj: when True (dealer has a natural blackjack) all extras are
                   suppressed — players only pay net-loss sips via on_round_end.
        dealer_name: the dealer-player is exempt from bonus win drinks
                     (suited, doubled, 5-card wins) — they drink via dealer
                     role rules instead (Hard Switch, net losses).
        """
        msgs   = []
        others = [p for p in all_player_names if p != player_name]
        # Dealer is spared from other players' win-bonus drinks
        others_np = [p for p in others if p != dealer_name] if dealer_name else others

        # 21 with 5+ cards: suppress hand-out when dealer has blackjack
        if not dealer_bj and hand.score() == 21 and len(hand.cards) >= 5:
            msgs.append((player_name, -len(hand.cards),
                f"{player_name} hit 21 with {len(hand.cards)} cards => may hand out {len(hand.cards)} sips",
                "handout"))

        if hand.result != "win":
            return msgs

        # Doubled hand breaks immunity (splits aggregated in on_round_end; suited handled below)
        if hand.doubled and not hand.is_suited():
            for p in others_np:
                msgs.append((p, 1,
                    f"{player_name} won a doubled hand => {p} drinks 1 sip (immunity exception)"))

        # Suited winning hand: 1 sip normally, 4 sips if doubled (split does NOT multiply)
        # Skip for blackjack — the BJ bonus already incorporates the suited multiplier
        if hand.is_suited() and not hand.is_blackjack():
            sips = 4 if hand.doubled else 1
            sym  = hand.cards[0].suit.symbol
            for p in others_np:
                msgs.append((p, sips,
                    f"{player_name} won suited hand (all {sym}) => {p} drinks {sips} sip(s)"))

        # Win with 5+ cards (stacks with above if score is 21)
        if len(hand.cards) >= 5:
            for p in others_np:
                msgs.append((p, 1,
                    f"{player_name} won with {len(hand.cards)} cards => {p} drinks 1 sip"))

        return msgs

    # ---------------------------------------------------------------- all-hands sweep (player)

    @staticmethod
    def check_all_hands_sweep(player_name: str, player_hands: list,
                               all_player_names: list, wager: int,
                               dealer_name: str = "",
                               dealer_bj: bool = False) -> list:
        """
        Fires when a player has 2+ hands (starting hands or from a split) and EITHER:
          - Every card across every hand shares the same suit, OR
          - Every hand scores exactly 21 (BJ counts as 21).
        Win/push/loss outcome is irrelevant — only the cards matter.

        Payout: wager × 2 per condition met (both = wager × 4).
        Suppressed when dealer has BJ (consistent with auto-insurance).
        Stacks with all other win-bonus rules.
        """
        if dealer_bj:
            return []
        if len(player_hands) < 2:
            return []

        all_cards = [c for h in player_hands for c in h.cards]
        if not all_cards:
            return []

        first_suit    = all_cards[0].suit.value
        all_same_suit = all(c.suit.value == first_suit for c in all_cards)
        all_21 = all(h.score() == 21 for h in player_hands)

        if not (all_same_suit or all_21):
            return []

        # Stacking: both conditions together = wager * 4, each alone = wager * 2
        multiplier = 4 if (all_same_suit and all_21) else 2
        sips       = wager * multiplier

        if all_same_suit and all_21:
            reason = f"all {all_cards[0].suit.symbol} suited + all 21 (x{multiplier})"
        elif all_same_suit:
            reason = f"all {all_cards[0].suit.symbol} suited across all hands"
        else:
            reason = "all hands scored 21"

        others = [p for p in all_player_names
                  if p != player_name and p != dealer_name]
        msgs = [(p, sips,
                 f"{player_name} all-hands sweep ({reason}) => {p} drinks {sips} sip(s)")
                for p in others]

        # Cancel doubled-hand immunity drinks already applied in on_hand_resolved
        # for each winning doubled hand — the sweep covers them.
        for hand in player_hands:
            if hand.result == "win" and hand.doubled and not hand.is_suited():
                for p in others:
                    msgs.append((p, -1,
                        f"Sweep cancels doubled-hand drink for {p} (already covered by sweep)"))

        return msgs

    # ---------------------------------------------------------------- dealer 21 with 5+ cards

    @staticmethod
    def dealer_21_five_cards(dealer_hand: Hand) -> bool:
        """Returns True if the dealer hit exactly 21 with 5+ cards (wages doubled this round)."""
        return dealer_hand.score() == 21 and len(dealer_hand.cards) >= 5

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
    def _dealer_bj_drinks(players: list, wager: int, num_hands: int,
                           hard_switch_dealer: str) -> list:
        """Auto-insurance charge when dealer has a natural blackjack.

        Every player pays for starting hands lost (num_hands minus BJ pushes).
        Splits don't reduce the charge.  The new hard-switch dealer is exempt.
        """
        msgs = []
        for p in players:
            if bool(hard_switch_dealer) and p.name == hard_switch_dealer:
                continue
            bj_pushes = sum(
                1 for h in p.hands
                if not h.from_split and h.result == "push" and h.is_blackjack()
            )
            base = num_hands if num_hands > 0 else sum(
                1 for h in p.hands if not h.from_split
            )
            starting_losses = max(0, base - bj_pushes)
            if starting_losses > 0:
                msgs.append((p.name, starting_losses * wager,
                    f"{p.name} dealer BJ \u2014 {starting_losses} starting hand(s) lost "
                    f"=> drinks {starting_losses * wager} sip(s) (auto-insurance)"))
        return msgs

    @staticmethod
    def _net_loss_drinks(players: list, wager: int, hard_switch_dealer: str) -> list:
        """Sips for net hand losses.

        Wins offset losses; only a net negative total costs sips.
        Blackjack counts as 2 wins (house rule) -- it can offset two lost hands.
        """
        msgs = []
        for p in players:
            if bool(hard_switch_dealer) and p.name == hard_switch_dealer:
                continue
            # BJ = 2 wins: a natural offsets two net-loss hands (drinking house rule)
            effective_wins = sum(2 if h.is_blackjack() else 1
                                 for h in p.hands if h.result == "win")
            net = max(0, p.round_losses() - effective_wins)
            if net > 0:
                msgs.append((p.name, net * wager,
                    f"{p.name} net -{net} hand(s) => drinks {net * wager} sip(s) (net loss)"))
        return msgs

    @staticmethod
    def _extra_loss_drinks(players: list, wager: int, hard_switch_dealer: str) -> list:
        """Extra sip for each lost doubled or lost suited hand."""
        msgs = []
        for p in players:
            if bool(hard_switch_dealer) and p.name == hard_switch_dealer:
                continue
            for hand in p.hands:
                if hand.result != "loss":
                    continue
                if hand.doubled:
                    msgs.append((p.name, wager,
                        f"{p.name} lost a doubled hand => +{wager} sip(s)"))
                if hand.is_suited():
                    msgs.append((p.name, wager,
                        f"{p.name} lost a suited hand => +{wager} sip(s)"))
        return msgs

    @staticmethod
    def _split_win_drinks(players: list, hard_switch_dealer: str) -> list:
        """Split wins break immunity: sips = (winning split hands) - 1, charged to all others."""
        msgs = []
        for winner in players:
            split_wins = sum(1 for h in winner.hands if h.from_split and h.result == "win")
            sips = max(0, split_wins - 1)
            if sips == 0:
                continue
            for other in players:
                if other is winner:
                    continue
                if bool(hard_switch_dealer) and other.name == hard_switch_dealer:
                    continue
                msgs.append((other.name, sips,
                    f"{winner.name} won {split_wins} split hand(s) => {other.name} drinks {sips} sip(s)"))
        return msgs

    @staticmethod
    def _wins_all_drinks(players: list, hard_switch_dealer: str) -> list:
        """Other-player-wins-all rule with immunity tiers."""
        msgs = []
        for winner in players:
            if winner.round_losses() > 0 or winner.round_pushes() > 0:
                continue
            w_wins = winner.round_wins()
            for other in players:
                if other is winner:
                    continue
                if bool(hard_switch_dealer) and other.name == hard_switch_dealer:
                    continue
                o_wins   = other.round_wins()
                o_losses = other.round_losses()
                o_pushes = other.round_pushes()
                if o_losses == 0 and o_pushes == 0:
                    sips = 0          # fully immune
                elif o_losses == 0:
                    sips = max(0, w_wins - o_wins)
                else:
                    sips = w_wins
                if sips > 0:
                    msgs.append((other.name, sips,
                        f"{winner.name} swept all hands => {other.name} drinks {sips} sip(s)"))
        return msgs

    @staticmethod
    def on_round_end(players: list, wager: int,
                     dealer_bj: bool = False,
                     dealer_shows_ace: bool = False,
                     hard_switch_dealer: str = "",
                     num_hands: int = 0) -> list:
        """
        Called once all hands are resolved.
        Fires:
        - Net hand losses (wins offset losses; only net negative costs sips)
        - Extra sip for each lost double or lost suited hand
        - Split wins break immunity (aggregated as winning_split_hands - 1)
        - Other-player-wins-all rule (with immunity tiers)

        dealer_bj: when True (dealer natural blackjack) AND dealer_shows_ace is
                   True, players are charged for every starting hand (num_hands)
                   minus any BJ pushes x wager. Splits do not reduce the charge --
                   a player who started with 2 hands and split one still pays for
                   2 starting hands. All bonus/penalty extras are suppressed
                   (auto-insurance).
        dealer_shows_ace: whether the dealer's up-card (first card) was an Ace --
                   real insurance is only ever offered on an Ace up-card. When the
                   dealer's blackjack instead came from a 10-value up-card hiding
                   an Ace, the group never had a chance to insure, so the normal
                   (uncapped) net-loss rules apply instead of auto-insurance.
        num_hands: configured hands per player (used for dealer BJ charge).
                   Falls back to counting non-split hands if not supplied.
        hard_switch_dealer: name of the dealer-player on a hard switch -- they are
                            fully exempt from all player-role drinks this round
                            (they already drink via the Hard Switch dealer rule).
        """
        if dealer_bj and dealer_shows_ace:
            return DrinkingRules._dealer_bj_drinks(players, wager, num_hands, hard_switch_dealer)

        msgs = []
        msgs += DrinkingRules._net_loss_drinks(players, wager, hard_switch_dealer)
        msgs += DrinkingRules._extra_loss_drinks(players, wager, hard_switch_dealer)
        msgs += DrinkingRules._split_win_drinks(players, hard_switch_dealer)
        msgs += DrinkingRules._wins_all_drinks(players, hard_switch_dealer)
        return msgs

    # ---------------------------------------------------------------- hard dealer switch

    @staticmethod
    def on_hard_dealer_switch(dealer_name: str, winning_hands: list,
                               half_protected: bool = False) -> list:
        """
        Called when the dealer loses ALL hands (push != loss).
        winning_hands: list of (player_name, Hand) tuples — caller is responsible
          for filtering out the dealer's own player hands when partial A♣ protection
          applies (player-hand A♣: dealer exempt from own hands, drinks for all others).
        Dealer drinks per each winning hand type.
        half_protected=True (dealer-hand A♣): drinks ceil(total/2) instead of full.
        """
        total = 0
        lines = []
        for pname, hand in winning_hands:
            if hand.is_blackjack():
                if pname == dealer_name:
                    s = 1
                    lines.append(f"{pname} blackjack (own hand) => 1 sip (no multiplier)")
                else:
                    s = 2
                    lines.append(f"{pname} blackjack => 2 sips")
            elif hand.doubled:
                s = 2
                lines.append(f"{pname} doubled win => 2 sips")
            else:
                s = 1
                lines.append(f"{pname} regular win => 1 sip")
            total += s

        detail = "; ".join(lines)
        if half_protected and total > 0:
            reduced = math.ceil(total / 2)
            return [(dealer_name, reduced,
                f"Hard Dealer Switch (A♣ half protection): {dealer_name} drinks {reduced} sip(s) "
                f"(halved from {total}: {detail})",
                "dealer")]
        return [(dealer_name, total,
            f"Hard Dealer Switch: {dealer_name} drinks {total} sip(s) ({detail})",
            "dealer")]

    # ---------------------------------------------------------------- event dispatch

    @staticmethod
    def handle(event) -> list:
        """Dispatch a typed GameEvent to the correct rule handler.

        This is the single official entry point for the game engine to fire
        drinking rule events.  The match is exhaustive: an unhandled event type
        raises NotImplementedError immediately, so adding a new GameEvent
        subclass without wiring it up here fails loudly rather than silently
        returning an empty drink list.

        Two DrinkingRules helpers are intentionally NOT routed here because they
        have non-list return types:
          - check_four_aces()      → (list, bool)  call directly
          - dealer_21_five_cards() → bool           call directly
        """
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
        match event:
            case CardDealtEvent():
                return DrinkingRules.on_card_dealt(
                    event.card, event.recipient, event.card_pos,
                    event.all_names, event.dealer_name, event.ace_clubs_flag,
                    is_dealer_hand=event.is_dealer_hand,
                )
            case BlackjackEvent():
                return DrinkingRules.on_blackjack(
                    event.player_name, event.hand, event.all_names,
                    hard_switch_dealer=event.hard_switch_dealer,
                )
            case InsuranceResolvedEvent():
                return DrinkingRules.resolve_insurance_vote(
                    event.player_name, event.hand, event.all_names,
                    insured=event.insured, dealer_bj=event.dealer_bj,
                    hard_switch_dealer=event.hard_switch_dealer,
                )
            case HandResolvedEvent():
                return DrinkingRules.on_hand_resolved(
                    event.player_name, event.hand, event.all_names,
                    dealer_bj=event.dealer_bj, dealer_name=event.dealer_name,
                )
            case AllHandsSweepEvent():
                return DrinkingRules.check_all_hands_sweep(
                    event.player_name, event.player_hands, event.all_names,
                    event.wager, dealer_name=event.dealer_name,
                    dealer_bj=event.dealer_bj,
                )
            case DealerHandRevealedEvent():
                return DrinkingRules.on_dealer_hand_revealed(event.dealer_hand)
            case RoundEndEvent():
                return DrinkingRules.on_round_end(
                    event.players, event.wager,
                    dealer_bj=event.dealer_bj,
                    dealer_shows_ace=event.dealer_shows_ace,
                    hard_switch_dealer=event.hard_switch_dealer,
                    num_hands=event.num_hands,
                )
            case HardDealerSwitchEvent():
                return DrinkingRules.on_hard_dealer_switch(
                    event.dealer_name, event.winning_hands,
                    half_protected=event.half_protected,
                )
            case _:
                raise NotImplementedError(
                    f"DrinkingRules.handle() has no case for {type(event).__name__}. "
                    "Add a dataclass to engine/events.py and a matching case here."
                )


# =============================================================================
# DrinkTracker
# =============================================================================

class DrinkTracker:
    """
    Resolves recipient tokens to Player objects, logs each drink with its
    full reason, and prints a detailed breakdown at round end.

    Used by both blackjack.py (digital game) and referee.py (real-life session).
    """

    def __init__(self, players: list, dealer_player, verbose: bool = True):
        self.players       = players
        self.dealer_player = dealer_player
        self._map          = {p.name.lower(): p for p in players}
        self.verbose       = verbose  # set False by web layer to silence terminal output
        self.easy_mode     = False    # halve drinks every round regardless of player count

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
        """Apply a list of (recipient, sips, reason[, role]) tuples.
        role defaults to 'player'; use 'dealer' for dealer-seat drinks.
        role == 'handout' means the recipient hands out abs(sips) to others.
        Any other negative sips value is a direct credit applied to the recipient.
        No halving here -- use apply_end_of_round for end-of-round events."""
        for msg in msgs:
            recipient, sips, reason = msg[0], msg[1], msg[2]
            role = msg[3] if len(msg) > 3 else "player"
            if recipient is None or sips == 0:
                if reason: print(f"    (i) {reason}")
                continue
            if sips < 0:
                if role == "handout":
                    self._handle_handout(recipient, abs(sips), reason)
                else:
                    # Direct credit — e.g. sweep cancellation undoing a prior drink
                    for t in self._resolve(recipient):
                        t.add_drink(sips, reason, "player")
                    if reason: print(f"    (i) {reason}")
                continue
            for t in self._resolve(recipient):
                t.add_drink(sips, reason, role)
            if self.verbose:
                print(f"    [drink] {reason}")

    def apply_end_of_round(self, msgs: list):
        """Apply all end-of-round drink messages.
        4-player rule (4+ players): sum positive sips per player across the
        entire round, then apply a halving credit so net = ceil(total/2).
        Mid-round events (aces, first-deal four-aces) use apply() -- NOT halved."""
        all_msgs = list(msgs)
        halving_active = self.easy_mode or len(self.players) >= 4

        if not halving_active:
            self.apply(all_msgs)
            return

        label = "Easy mode" if self.easy_mode and len(self.players) < 4 else "4-player"

        # Snapshot pre-batch sips so we measure exactly what this batch adds
        pre_sips = {p.name: p.drinks_owed() for p in self.players}

        # Apply all messages at full value (individual reasons preserved in log)
        self.apply(all_msgs)

        # Add a halving credit for each player who gained sips this batch
        for p in self.players:
            gained = p.drinks_owed() - pre_sips.get(p.name, 0)
            if gained > 0:
                credit = gained - math.ceil(gained / 2)
                if credit > 0:
                    halved = math.ceil(gained / 2)
                    p.add_drink(-credit,
                                f"{label} halving: -{credit} sip(s) ({gained} -> {halved})",
                                "player")
                    if self.verbose:
                        print(f"    (i) {label} halving for {p.name}: {gained} -> {halved}")

    # ---------------------------------------------------------------- ace of clubs credit

    def apply_ace_clubs_credit(self, player: Player):
        """
        Apply -1 sip credit from Ace of Clubs AFTER net losses are calculated.
        Minimum net result is 0 (credit cannot go negative).
        """
        if player.drinks_owed() > 0:
            player.add_drink(-1, f"{player.name} A♣ credit: -1 sip", "player")
            if self.verbose:
                print(f"    (i) {player.name} A♣ credit applied: -1 sip")

    # ---------------------------------------------------------------- handout

    def _handle_handout(self, giver: str, total: int, reason: str, label: str = "5-card 21"):
        """
        Handle a sip handout (5-card-21 win, or a bust-vote reward).
        NPC givers distribute round-robin automatically.
        Human givers are prompted interactively.

        label: short tag appended to each per-sip reason string, e.g.
               "5-card 21" or "bust vote".
               distinguish handout sources in the CSV export.
        """
        if self.verbose:
            print(f"    [drink] {reason}")
        others = [p for p in self.players if p.name.lower() != giver.lower()]
        if not others: return

        giver_player = self._map.get(giver.lower())
        remaining    = total

        if getattr(giver_player, "is_npc", False):
            for i in range(remaining):
                t = others[i % len(others)]
                t.add_drink(1, f"{giver} (NPC) handed 1 sip to {t.name} ({label})", "player")
                if self.verbose:
                    print(f"    -> {t.name} +1 sip (NPC auto-distributed)")
            return

        other_names   = [p.name for p in others]
        max_attempts  = 5  # consecutive invalid/blank entries before auto-distributing the rest
        bad_attempts  = 0
        if self.verbose:
            print(f"    {giver}, hand out {remaining} sip(s) among: {', '.join(other_names)}")
        i = 0
        while remaining > 0:
            try:
                raw = input(f"    Who gets a sip? ({remaining} left): ").strip().capitalize()
            except EOFError:
                raw = ""
                bad_attempts = max_attempts  # no terminal to read from — stop asking

            t = self._map.get(raw.lower())
            if t and t.name.lower() != giver.lower():
                t.add_drink(1, f"{giver} handed 1 sip to {t.name} ({label})", "player")
                remaining -= 1
                bad_attempts = 0
                if self.verbose:
                    print(f"    -> {t.name} +1 sip")
            else:
                bad_attempts += 1
                if bad_attempts >= max_attempts:
                    if self.verbose:
                        print(f"    No valid choice after {max_attempts} tries — "
                              f"auto-distributing remaining {remaining} sip(s) round-robin.")
                    for j in range(remaining):
                        t = others[(i + j) % len(others)]
                        t.add_drink(1, f"{giver} handed 1 sip to {t.name} ({label}, auto)", "player")
                        if self.verbose:
                            print(f"    -> {t.name} +1 sip (auto-distributed)")
                    remaining = 0
                else:
                    if self.verbose:
                        print(f"    Invalid. Choose from: {', '.join(other_names)}")
            i += 1

    # ---------------------------------------------------------------- summary

    def print_round_summary(self):
        if self.verbose:
            print("\n" + "="*52)
            print("  DRINK SUMMARY")
            print("="*52)
        for p in self.players:
            if p.name == "House": continue
            if not p.drink_log:   continue

            # Split entries by role
            dealer_log = [(e[0], e[1]) for e in p.drink_log if e[2] == "dealer"]
            player_log = [(e[0], e[1]) for e in p.drink_log if e[2] != "dealer"]

            if not dealer_log and not player_log:
                continue

            # Dealer-role section (only relevant when this player holds the dealer seat)
            if p.is_dealer and dealer_log:
                dealer_net = sum(s for s, _ in dealer_log)
                if self.verbose:
                    print(f"\n  Dealer ({p.name})  =>  {dealer_net} sip(s) this round")
                for sips, reason in dealer_log:
                    if self.verbose:
                        sign = f"+{sips}" if sips > 0 else str(sips)
                        print(f"      {sign}  {reason}")
