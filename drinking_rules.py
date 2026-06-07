"""
drinking_rules.py
=================
Drinking layer for Blackjack.
Imported by blackjack.py (drinking mode) and referee.py.
Has no game logic of its own — purely reacts to events fired by the game.
"""

import hashlib
import math
import urllib.request
from blackjack import Rank, Suit, Hand, Player

_RULES_URL   = "https://raw.githubusercontent.com/robert-rjm/Black-Out-Jack/main/docs/Rules.md"
_RULES_HASH  = "CC092107596D44EE4068E5782E8663CF12EF360234FB8D39AE700756AEBF32CC"
_RULES_DATE  = "2026-05-22"


def verify_rules():
    """
    Fetch Rules.md from GitHub and compare its SHA256 to the known hash.
    If changed, warn that drinking_rules.py may be out of date.
    Silently skips on network failure.
    """
    try:
        with urllib.request.urlopen(_RULES_URL, timeout=5) as r:
            current_hash = hashlib.sha256(r.read()).hexdigest()
    except Exception:
        return

    if current_hash != _RULES_HASH:
        print("=" * 52)
        print("  WARNING: Rules.md has changed on GitHub!")
        print(f"  Last verified : {_RULES_DATE}")
        print(f"  Expected hash : {_RULES_HASH[:16]}...")
        print(f"  Current hash  : {current_hash[:16]}...")
        print("  drinking_rules.py may not reflect the latest rules.")
        review_url = (_RULES_URL
                      .replace('raw.githubusercontent.com', 'github.com')
                      .replace('/main/', '/blob/main/'))
        print(f"  Review changes at: {review_url}")
        print("  Update _RULES_HASH and _RULES_DATE in drinking_rules.py.")
        print("=" * 52 + "\n")


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
# Rule classifier — canonical name for a raw drink-reason string.
# Used by drink_tracker.py (CSV export) and simulation.py.
# =============================================================================

def classify_rule(reason: str) -> str | None:
    """
    Normalise a raw drink-reason string to a short canonical rule name.
    Returns None for bookkeeping entries that should not appear in the CSV.
    """
    r = reason
    if "A\u2663" in r and "credit" in r:           return None   # A♣ credit
    if "A\u2663 protected" in r:                   return None   # display-only waived entry
    if "A\u2663 protection credit" in r:           return None   # display-only waived credit
    if "bust vote correct" in r:                    return None   # bust vote credit
    if "protects" in r:                              return None
    if "exempt" in r:                                return None
    if "Bust vote" in r and "wrong" in r:           return "Bust vote wrong call"
    if "Insurance" in r and "dealer BJ" in r and "own bonus" in r: return "Insurance: BJ holder drinks own bonus"
    if "Insurance" in r and "no dealer BJ" in r:                   return "Insurance: group drinks double BJ bonus"
    if "Hard Dealer Switch (A\u2663 half protection)" in r: return "Hard Dealer Switch (half, A\u2663)"
    if "Hard Dealer Switch" in r:                   return "Hard Dealer Switch"
    if "net loss" in r:                             return "Net hand losses"
    if "lost a doubled hand" in r:                  return "Lost doubled hand"
    if "lost a suited hand" in r:                   return "Lost suited hand"
    if "immunity exception" in r:                   return "Doubled win (immunity break)"
    if "won suited hand" in r:                      return "Suited winning hand"
    if "split hand" in r:                           return "Split win (immunity break)"
    if "swept all hands" in r:                      return "Other-player sweep"
    if "all-hands sweep" in r:                      return "All-hands sweep"
    if "auto-insurance" in r:                       return "Dealer BJ (auto-insurance)"
    if "Blackjack by" in r:                         return "Blackjack bonus"
    if "4 Aces" in r and "first deal" in r:         return "Four Aces (first deal)"
    if "4 Aces" in r and "end of round" in r:       return "Four Aces (end of round)"
    if "Dealer hand is all" in r:                   return "Dealer suited hand"
    if "handed" in r and "5-card 21" in r:          return "5-card 21 handout received"
    if "won with" in r and "cards" in r:            return "5+ card win"
    if "A\u2660" in r and "to dealer" in r:        return "Ace dealt: Ace of Spades (dealer hand)"
    if "A\u2665" in r and "dealer" in r:           return "Ace dealt: Ace of Hearts (dealer hand)"
    if "A\u2666" in r and "dealer" in r:           return "Ace dealt: Ace of Diamonds (dealer hand)"
    if "A\u2660" in r:                             return "Ace dealt: Ace of Spades (player hand)"
    if "A\u2665" in r:                             return "Ace dealt: Ace of Hearts (player hand)"
    if "A\u2666" in r:                             return "Ace dealt: Ace of Diamonds (player hand)"
    return "Other"


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
                    f"A{s.symbol} dealt to dealer ({dealer_name}) => half Hard Switch protection (drinks ceil of total/2)"))
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
        mult   = _bj_multiplier(hand)
        sips   = mult
        parts  = []
        ranks  = {c.rank for c in hand.cards}
        suits  = {c.suit for c in hand.cards}
        if hand.is_suited():                                parts.append("suited x2")
        if {Rank.ACE, Rank.JACK}.issubset(ranks):           parts.append("A+J x2")
        if suits.issubset({Suit.SPADES, Suit.CLUBS}):       parts.append("both black x2")
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

        Outcomes:
          Insure + dealer BJ:    BJ holder drinks own bonus, hand pushes, group drinks nothing.
          Insure + dealer no BJ: Group drinks double the normal BJ bonus.
          Decline + dealer BJ:   Existing auto-insurance handles it; no extra drinks here.
          Decline + dealer no BJ: Normal BJ bonus (group drinks as usual).
        """
        mult   = _bj_multiplier(hand)
        others = [p for p in all_player_names
                  if p != player_name and p != hard_switch_dealer]

        if insured and dealer_bj:
            # BJ holder drinks their own bonus; group is protected
            sips = mult
            msgs = [(player_name, sips,
                     f"Insurance (group voted insure) + dealer BJ: "
                     f"{player_name} drinks own bonus {sips} sip(s), group protected")]
            msgs.append((None, 0, f"{player_name}'s blackjack pushes (insured vs dealer BJ)"))
            return msgs

        if insured and not dealer_bj:
            # Group gambled wrong — drinks double
            sips = mult * 2
            return [(p, sips,
                     f"Insurance (group voted insure) + no dealer BJ: "
                     f"{p} drinks double BJ bonus {sips} sip(s)")
                    for p in others]

        if not insured and dealer_bj:
            # Decline + dealer BJ: auto-insurance already handles net-loss cap
            return [(None, 0,
                     f"{player_name} blackjack: group declined insurance, dealer has BJ "
                     f"=> auto-insurance applies, normal max sips only")]

        # Decline + no dealer BJ: normal BJ bonus
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
    def on_round_end(players: list, wager: int,
                     dealer_bj: bool = False,
                     hard_switch_dealer: str = "",
                     num_hands: int = 0) -> list:
        """
        Called once all hands are resolved.
        Fires:
        - Net hand losses (wins offset losses; only net negative costs sips)
        - Extra sip for each lost double or lost suited hand
        - Split wins break immunity (aggregated as winning_split_hands - 1)
        - Other-player-wins-all rule (with immunity tiers)

        dealer_bj: when True (dealer natural blackjack) players are charged for
                   every starting hand (num_hands) minus any BJ pushes × wager.
                   Splits do not reduce the charge — a player who started with 2
                   hands and split one still pays for 2 starting hands.
                   All bonus/penalty extras are suppressed (auto-insurance).
        num_hands: configured hands per player (used for dealer BJ charge).
                   Falls back to counting non-split hands if not supplied.
        hard_switch_dealer: name of the dealer-player on a hard switch — they are
                            fully exempt from all player-role drinks this round
                            (they already drink via the Hard Switch dealer rule).
        """
        msgs = []

        # On a hard switch the dealer drinks via the Hard Switch rule only —
        # skip all player-role charges for them.
        def _excluded(player_name: str) -> bool:
            return bool(hard_switch_dealer) and player_name == hard_switch_dealer

        # Dealer blackjack = auto-insurance:
        # charge num_hands × wager minus any BJ pushes (player BJ vs dealer BJ).
        # Splits do not reduce the charge — starting hand count is always num_hands.
        if dealer_bj:
            for p in players:
                if _excluded(p.name):
                    continue
                # BJ pushes: player had BJ on a starting hand → pushes vs dealer BJ
                bj_pushes = sum(
                    1 for h in p.hands
                    if not h.from_split and h.result == "push" and h.is_blackjack()
                )
                # Base = num_hands if supplied; otherwise count non-split hands
                base = num_hands if num_hands > 0 else sum(
                    1 for h in p.hands if not h.from_split
                )
                starting_losses = max(0, base - bj_pushes)
                if starting_losses > 0:
                    msgs.append((p.name, starting_losses * wager,
                        f"{p.name} dealer BJ — {starting_losses} starting hand(s) lost "
                        f"=> drinks {starting_losses * wager} sip(s) (auto-insurance)"))
            return msgs

        # Net losses — always fire (skip dealer on hard switch)
        for p in players:
            if _excluded(p.name):
                continue
            net = p.net_losses()
            if net > 0:
                msgs.append((p.name, net * wager,
                    f"{p.name} net -{net} hand(s) => drinks {net * wager} sip(s) (net loss)"))

        # Extra sip for each lost double or lost suited hand (skip dealer on hard switch)
        for p in players:
            if _excluded(p.name):
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

        # Split wins break immunity: sips = (winning split hands) - 1, per winner
        for winner in players:
            split_wins = sum(1 for h in winner.hands if h.from_split and h.result == "win")
            sips = max(0, split_wins - 1)
            if sips == 0:
                continue
            for other in players:
                if other is winner:
                    continue
                if _excluded(other.name):   # dealer exempt on hard switch
                    continue
                msgs.append((other.name, sips,
                    f"{winner.name} won {split_wins} split hand(s) => {other.name} drinks {sips} sip(s)"))

        # Other-player-wins-all
        for winner in players:
            if winner.round_losses() > 0 or winner.round_pushes() > 0:
                continue
            w_wins = winner.round_wins()
            for other in players:
                if other is winner: continue
                if _excluded(other.name):   # dealer exempt on hard switch
                    continue
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
                               protected: bool, half_protected: bool = False) -> list:
        """
        Called when the dealer loses ALL hands (push != loss).
        winning_hands: list of (player_name, Hand) tuples — caller is responsible
          for filtering out the dealer's own player hands when partial A♣ protection
          applies (player-hand A♣: dealer exempt from own hands, drinks for all others).
        Dealer drinks per each winning hand type.
        protected=True (dealer-hand A♣): full protection — skips all drinking.
        half_protected=True (dealer-hand A♠): drinks ceil(total/2) instead of full.
        Full protection takes precedence over half protection.
        """
        if protected:
            return [(None, 0,
                f"Hard Switch triggered — A♣ protects {dealer_name} from drinking")]

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
            print(f"    [drink] {reason}")

    def apply_end_of_round(self, *msg_lists):
        """Apply all end-of-round drink messages.
        4-player rule (4+ players): sum positive sips per player across the
        entire round, then apply a halving credit so net = ceil(total/2).
        Mid-round events (aces, first-deal four-aces) use apply() -- NOT halved."""
        all_msgs = [msg for msgs in msg_lists for msg in msgs]
        four_player_mode = len(self.players) >= 4

        if not four_player_mode:
            self.apply(all_msgs)
            return

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
                                f"4-player halving: -{credit} sip(s) ({gained} -> {halved})",
                                "player")
                    print(f"    (i) 4-player halving for {p.name}: {gained} -> {halved}")

    # ---------------------------------------------------------------- ace of clubs credit

    def apply_ace_clubs_credit(self, player: Player):
        """
        Apply -1 sip credit from Ace of Clubs AFTER net losses are calculated.
        Minimum net result is 0 (credit cannot go negative).
        """
        if player.drinks_owed() > 0:
            player.add_drink(-1, f"{player.name} A♣ credit: -1 sip", "player")
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
                t.add_drink(1, f"{giver} (NPC) handed 1 sip to {t.name} (5-card 21)", "player")
                print(f"    -> {t.name} +1 sip (NPC auto-distributed)")
            return

        other_names = [p.name for p in others]
        print(f"    {giver}, hand out {remaining} sip(s) among: {', '.join(other_names)}")
        while remaining > 0:
            raw = input(f"    Who gets a sip? ({remaining} left): ").strip().capitalize()
            t   = self._map.get(raw.lower())
            if t and t.name.lower() != giver.lower():
                t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21)", "player")
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

            # Split entries by role
            dealer_log = [(e[0], e[1]) for e in p.drink_log if e[2] == "dealer"]
            player_log = [(e[0], e[1]) for e in p.drink_log if e[2] != "dealer"]

            if not dealer_log and not player_log:
                continue

            any_drinks = True

            # Dealer-role section (only relevant when this player holds the dealer seat)
            if p.is_dealer and dealer_log:
                dealer_net = sum(s for s, _ in dealer_log)
                print(f"\n  Dealer ({p.name})  =>  {dealer_net} sip(s) this round")
                for sips, reason in dealer_log:
                    sign = f"+{sips}" if sips > 0 else str(sips)
                    print(f"    {sign:>4}  {reason}")

            # Player-role section
            if player_log:
                player_net = sum(s for s, _ in player_log)
                print(f"\n  {p.name}  =>  {player_net} sip(s) this round")
                for sips, reason in player_log:
                    sign = f"+{sips}" if sips > 0 else str(sips)
                    print(f"    {sign:>4}  {reason}")

            p.total_drinks += max(0, sum(e[0] for e in p.drink_log))

        if not any_drinks:
            print("  No drinks this round!")
        print("\n" + "="*52 + "\n")
