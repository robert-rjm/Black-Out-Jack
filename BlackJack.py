"""
🃏 Drinking BlackJack
========================
Based on rules from: https://github.com/robert-rjm/Drinking-BlackJack  
Standard BlackJack with custom drinking mechanics layered on top.
For the full rule set, see Rules.md in the repository.
"""

__rules_source__ = "https://github.com/robert-rjm/Drinking-BlackJack/blob/main/Rules.md"
__rules_last_verified__ = "2026-04-01"
__rules_hash__ = "a6e545fcae4411ef4b901c27f62cafc2efd9376f86d89f5f0c66059518d64158"
__version__ = "1.0.0"


from datetime import datetime
print('Date last modified:', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

import random
from enum import Enum
from tabulate import tabulate
import hashlib

def verify_rules():
    if not __rules_hash__:
        return
    try:
        import urllib.request
        raw_url = __rules_source__.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        with urllib.request.urlopen(raw_url, timeout=5) as r:
            current_hash = hashlib.sha256(r.read()).hexdigest()
    except Exception:
        return
    if current_hash != __rules_hash__:
        print("⚠️  WARNING: Rules.md has changed since this version was last verified!")
        print(f"   Last verified: {__rules_last_verified__}")
        print(f"   Expected hash: {__rules_hash__[:16]}...")
        print(f"   Current hash:  {current_hash[:16]}...")
        print("   The game may not reflect the latest rules.")
        print(f"   Review changes at: {__rules_source__}")
        print("   Update __rules_hash__ and __rules_last_verified__ in BlackJack.py.\n")
        
class Suit(Enum):
    HEARTS   = 'hearts'
    DIAMONDS = 'diamonds'
    CLUBS    = 'clubs'
    SPADES   = 'spades'

    @property
    def symbol(self):
        return {'hearts': '\u2665', 'diamonds': '\u2666',
                'clubs': '\u2663', 'spades': '\u2660'}[self.value]

    @classmethod
    def from_input(cls, value):
        if isinstance(value, cls): return value
        if isinstance(value, str):
            v = value.strip().upper().removeprefix('SUIT.')
            try: return cls[v]
            except KeyError: raise ValueError(f'Invalid suit: {value}')
        raise TypeError('Input must be a string or Suit enum')


class Rank(Enum):
    TWO=2; THREE=3; FOUR=4; FIVE=5; SIX=6; SEVEN=7; EIGHT=8; NINE=9
    TEN=10; JACK=11; QUEEN=12; KING=13; ACE=14

    @classmethod
    def from_input(cls, value):
        if isinstance(value, cls): return value
        if isinstance(value, str):
            v = value.strip().upper().removeprefix('RANK.')
            try: return cls[v]
            except KeyError: raise ValueError(f'Invalid rank: {value}')
        raise TypeError('Input must be a string or Rank enum')

    @property
    def label(self):
        if self in (Rank.JACK, Rank.QUEEN, Rank.KING): return self.name[0]
        if self == Rank.ACE: return 'A'
        return str(self.value)

    @property
    def blackjack_value(self):
        if self in (Rank.JACK, Rank.QUEEN, Rank.KING): return 10
        if self == Rank.ACE: return 11
        return self.value


class Card:
    def __init__(self, rank: Rank, suit: Suit):
        if not isinstance(rank, Rank): raise ValueError('Invalid rank')
        if not isinstance(suit, Suit): raise ValueError('Invalid suit')
        self.rank = rank
        self.suit = suit

    def __str__(self):  return f'{self.rank.label}{self.suit.symbol}'
    def __repr__(self): return f'Card({self.rank.label}{self.suit.symbol})'
    def to_tuple(self): return (self.rank.label, self.suit.symbol)


class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for suit in Suit for rank in Rank]
    def __len__(self): return len(self.cards)


class Shoe:
    def __init__(self, num_decks: int = 1):
        self.num_decks   = num_decks
        self.cards       = []
        self.penetration = random.uniform(0.70, 0.85)
        self.total_cards = num_decks * 52
        for _ in range(num_decks):
            self.cards.extend(Deck().cards)

    def __len__(self):  return len(self.cards)
    def __str__(self):  return (f'Shoe({self.num_decks} deck(s), '
                                f'{len(self.cards)} remaining, '
                                f'pen {self.penetration:.0%})')
    def __repr__(self): return (f'Shoe(num_decks={self.num_decks}, '
                                f'cards_remaining={len(self.cards)}, '
                                f'penetration={self.penetration:.2%})')

    def shuffle(self):
        random.shuffle(self.cards)
        print(f'Shoe shuffled - {len(self.cards)} cards ready.')

    def reset(self, num_decks: int = None):
        self.__init__(num_decks or self.num_decks)
        self.shuffle()

    def needs_reshuffle(self) -> bool:
        return len(self.cards) < (1 - self.penetration) * self.total_cards

    def deal_card(self) -> Card:
        if self.needs_reshuffle():
            print('Reshuffling shoe...')
            self.reset()
        return self.cards.pop()


class Hand:
    """
    One blackjack hand. Players hold a list of Hands
    (2 initial hands per the drinking rules; splits add more).
    """
    def __init__(self, doubled: bool = False, from_split: bool = False):
        self.cards:     list = []
        self.doubled        = doubled
        self.from_split     = from_split
        self.split_count    = 0
        self.stood          = False
        self.bust           = False
        self.insured        = False
        self.result         = None   # 'win' | 'loss' | 'push'

    # --- scoring ---
    def score(self) -> int:
        total = sum(c.rank.blackjack_value for c in self.cards)
        aces  = sum(1 for c in self.cards if c.rank == Rank.ACE)
        while total > 21 and aces:
            total -= 10; aces -= 1
        return total

    def is_blackjack(self)              -> bool: return len(self.cards) == 2 and self.score() == 21
    def is_bust(self)                   -> bool: return self.score() > 21
    def is_suited(self)                 -> bool: return len(self.cards) >= 2 and len({c.suit for c in self.cards}) == 1
    def can_split(self, max_splits=5)   -> bool: return len(self.cards) == 2 and self.cards[0].rank.blackjack_value == self.cards[1].rank.blackjack_value and self.split_count < max_splits

    def split(self, shoe) -> 'Hand':
        """Remove second card into a new Hand, deal one card to each."""
        new_hand = Hand(from_split=True)
        new_hand.cards.append(self.cards.pop())
        self.from_split = True
        self.split_count += 1
        self.cards.append(shoe.deal_card())
        new_hand.cards.append(shoe.deal_card())
        return new_hand

    # --- display ---
    def __str__(self):
        tags = [t for flag, t in [(self.doubled,'DBL'),(self.from_split,'SPL'),(self.insured,'INS')] if flag]
        tag  = f'  [{", ".join(tags)}]' if tags else ''
        return f'{", ".join(str(c) for c in self.cards)}  [{self.score()}]{tag}'

    def __repr__(self): return f'Hand({self})'


class Player:
    """
    One human seat.
    When is_dealer=True, the player ALSO runs a separate dealer_hand
    (they play their own hands AND act as dealer for the round).
    In single-player mode a synthetic 'House' Player holds is_dealer=True
    but plays no player hands of its own.
    """
    def __init__(self, name: str):
        self.name         = name.strip().capitalize()
        self.hands:  list = []
        self.is_dealer    = False
        self.dealer_hand  = None   # set when is_dealer=True
        # drink_log: list of (sips, reason) — positive=drink, negative=credit
        self.drink_log:  list = []
        # cumulative across all rounds
        self.total_wins   = 0
        self.total_losses = 0
        self.total_pushes = 0
        self.total_drinks = 0

    def reset_round(self, num_hands: int = 2):
        self.hands       = [Hand() for _ in range(num_hands)]
        self.dealer_hand = Hand() if self.is_dealer else None
        self.drink_log   = []

    def round_wins(self)   -> int: return sum(1 for h in self.hands if h.result == 'win')
    def round_losses(self) -> int: return sum(1 for h in self.hands if h.result == 'loss')
    def round_pushes(self) -> int: return sum(1 for h in self.hands if h.result == 'push')
    def net_losses(self)   -> int: return max(0, self.round_losses() - self.round_wins())
    def drinks_owed(self)  -> int: return sum(s for s, _ in self.drink_log if s > 0)

    def add_drink(self, sips: int, reason: str):
        if sips != 0:
            self.drink_log.append((sips, reason))

    def __str__(self):  return self.name
    def __repr__(self): return f'Player({self.name})'


def _bj_multiplier(hand: Hand) -> int:
    mult  = 1
    ranks = {c.rank for c in hand.cards}
    suits = {c.suit for c in hand.cards}
    black = {Suit.SPADES, Suit.CLUBS}
    if hand.is_suited():                                  mult *= 2
    if {Rank.ACE, Rank.JACK}.issubset(ranks):             mult *= 2
    if suits.issubset(black):                             mult *= 2
    return mult


class DrinkingRules:
    """
    All methods return list of (recipient, sips, reason).
    recipient: player name | 'all' | 'players_only'
    sips < 0  => recipient may HAND OUT that many sips.
    """

    @staticmethod
    def on_card_dealt(card, recipient, card_pos,
                      all_player_names, dealer_name, ace_clubs_flag):
        if card.rank != Rank.ACE:
            return []
        msgs = []
        s           = card.suit
        is_dealer   = (recipient == dealer_name)

        if not is_dealer:
            if s == Suit.CLUBS:
                msgs.append((recipient, -1,
                    f'A{s.symbol} dealt to {recipient} => -1 sip credit at round end'))
            elif s == Suit.SPADES:
                idx    = all_player_names.index(recipient)
                target = all_player_names[(idx + card_pos) % len(all_player_names)]
                msgs.append((target, 1,
                    f'A{s.symbol} dealt to {recipient} (card #{card_pos}) => {target} drinks 1 sip'))
            elif s == Suit.HEARTS:
                msgs.append((recipient, 1,
                    f'A{s.symbol} dealt to {recipient} => {recipient} drinks 1 sip'))
            elif s == Suit.DIAMONDS:
                msgs.append((dealer_name, 1,
                    f'A{s.symbol} dealt to {recipient} => {dealer_name} (dealer) drinks 1 sip'))
        else:
            if s == Suit.CLUBS:
                ace_clubs_flag['protected'] = True
                msgs.append((None, 0,
                    f'A{s.symbol} dealt to dealer ({dealer_name}) => exempt from Hard Switch drinking'))
            elif s == Suit.SPADES:
                if card_pos % 2 == 1:
                    msgs.append((dealer_name, 1,
                        f'A{s.symbol} to dealer (card #{card_pos}, odd) => {dealer_name} drinks 1 sip'))
                else:
                    msgs.append(('all', 1,
                        f'A{s.symbol} to dealer (card #{card_pos}, even) => everyone drinks 1 sip'))
            elif s == Suit.HEARTS:
                msgs.append(('all', 1,
                    f'A{s.symbol} dealt to dealer => everyone drinks 1 sip'))
            elif s == Suit.DIAMONDS:
                msgs.append(('players_only', 1,
                    f'A{s.symbol} dealt to dealer => all non-dealer players drink 1 sip'))
        return msgs

    @staticmethod
    def check_four_aces(all_cards, phase, triggered_first_deal):
        if sum(1 for c in all_cards if c.rank == Rank.ACE) < 4:
            return [], triggered_first_deal
        if phase == 'first_deal':
            return [('all', 2, 'All 4 Aces on table after first deal => everyone drinks 2 sips')], True
        if phase == 'end_of_round' and not triggered_first_deal:
            return [('all', 1, 'All 4 Aces visible at end of round => everyone drinks 1 sip')], False
        return [], triggered_first_deal

    @staticmethod
    def on_blackjack(player_name, hand, all_player_names):
        if hand.insured:
            return [(None, 0,
                f'{player_name} insured their blackjack => no bonus drinks')]
        mult   = _bj_multiplier(hand)
        sips   = mult
        parts  = []
        ranks  = {c.rank for c in hand.cards}
        suits  = {c.suit for c in hand.cards}
        if hand.is_suited():                               parts.append('suited x2')
        if {Rank.ACE, Rank.JACK}.issubset(ranks):          parts.append('A+J x2')
        if suits.issubset({Suit.SPADES, Suit.CLUBS}):      parts.append('both black x2')
        detail = f' ({" ".join(parts)})' if parts else ''
        others = [p for p in all_player_names if p != player_name]
        return [(p, sips,
                 f'Blackjack by {player_name}{detail} => {p} drinks {sips} sip(s)')
                for p in others]

    @staticmethod
    def on_hand_resolved(player_name, hand, all_player_names):
        if hand.result != 'win':
            return []
        msgs   = []
        others = [p for p in all_player_names if p != player_name]

        if hand.doubled or hand.from_split:
            label = 'doubled' if hand.doubled else 'split'
            for p in others:
                msgs.append((p, 1,
                    f'{player_name} won a {label} hand => {p} drinks 1 sip (immunity exception)'))

        if hand.is_suited():
            sips = 4 if (hand.doubled or hand.from_split) else 1
            sym  = hand.cards[0].suit.symbol
            for p in others:
                msgs.append((p, sips,
                    f'{player_name} won suited hand (all {sym}) => {p} drinks {sips} sip(s)'))

        if hand.score() == 21 and len(hand.cards) >= 5:
            msgs.append((player_name, -len(hand.cards),
                f'{player_name} hit 21 with {len(hand.cards)} cards => may hand out {len(hand.cards)} sips'))

        if len(hand.cards) >= 5:
            for p in others:
                msgs.append((p, 1,
                    f'{player_name} won with {len(hand.cards)} cards => {p} drinks 1 sip'))

        return msgs

    @staticmethod
    def on_dealer_hand_revealed(dealer_hand):
        if dealer_hand.is_suited() and len(dealer_hand.cards) >= 2:
            sym = dealer_hand.cards[0].suit.symbol
            return [('all', 2, f'Dealer hand is all {sym} => everyone drinks 2 sips')]
        return []

    @staticmethod
    def on_round_end(players, wager):
        msgs = []
        for p in players:
            net = p.net_losses()
            if net > 0:
                msgs.append((p.name, net * wager,
                    f'{p.name} net -{net} hand(s) => drinks {net * wager} sip(s) (net loss)'))

        for winner in players:
            if winner.round_losses() > 0 or winner.round_pushes() > 0:
                continue
            w_wins = winner.round_wins()
            for other in players:
                if other is winner: continue
                o_wins   = other.round_wins()
                o_losses = other.round_losses()
                o_pushes = other.round_pushes()
                if   o_losses == 0 and o_pushes == 0: sips = 0
                elif o_losses == 0:                   sips = max(0, w_wins - o_wins)
                else:                                 sips = w_wins
                if sips > 0:
                    msgs.append((other.name, sips,
                        f'{winner.name} swept all hands => {other.name} drinks {sips} sip(s)'))
        return msgs

    @staticmethod
    def on_hard_dealer_switch(dealer_name, winning_hands, protected):
        if protected:
            return [(None, 0,
                f'Hard Switch triggered - A clubs protects {dealer_name} from drinking')]
        total = 0
        lines = []
        for pname, hand in winning_hands:
            if hand.is_blackjack():  s = max(2, _bj_multiplier(hand)); lines.append(f'{pname} blackjack => {s} sip(s)')
            elif hand.doubled:       s = 2;                             lines.append(f'{pname} doubled win => 2 sips')
            else:                    s = 1;                             lines.append(f'{pname} regular win => 1 sip')
            total += s
        detail = '; '.join(lines)
        return [(dealer_name, total,
            f'Hard Dealer Switch: {dealer_name} drinks {total} sip(s) ({detail})')]


class DrinkTracker:
    """
    Resolves recipient tokens to Player objects,
    logs each drink with its reason,
    and prints a full breakdown at round end.
    """

    def __init__(self, players: list, dealer_player):
        self.players       = players
        self.dealer_player = dealer_player
        self._map          = {p.name.lower(): p for p in players}

    def _resolve(self, recipient: str) -> list:
        if recipient == 'all':          return list(self.players)
        if recipient == 'players_only': return [p for p in self.players if not p.is_dealer]
        p = self._map.get(str(recipient).lower())
        return [p] if p else []

    def apply(self, msgs: list):
        for recipient, sips, reason in msgs:
            if recipient is None or sips == 0:
                if reason: print(f'    (i) {reason}')
                continue
            if sips < 0:
                self._handle_handout(recipient, abs(sips), reason)
                continue
            for t in self._resolve(recipient):
                t.add_drink(sips, reason)
            print(f'    [drink] {reason}')

    def apply_ace_clubs_credit(self, player):
        if player.drinks_owed() > 0:
            player.add_drink(-1, f'{player.name} A clubs credit: -1 sip')
            print(f'    (i) {player.name} A clubs credit applied: -1 sip')

    def _handle_handout(self, giver: str, total: int, reason: str):
        print(f'    [drink] {reason}')
        others = [p.name for p in self.players if p.name.lower() != giver.lower()]
        if not others: return
        remaining = total
        print(f'    {giver}, hand out {remaining} sip(s) among: {", ".join(others)}')
        while remaining > 0:
            raw = input(f'    Who gets a sip? ({remaining} left): ').strip().capitalize()
            t   = self._map.get(raw.lower())
            if t and t.name.lower() != giver.lower():
                t.add_drink(1, f'{giver} handed 1 sip to {t.name} (5-card 21)')
                remaining -= 1
                print(f'    -> {t.name} +1 sip')
            else:
                print(f'    Invalid. Choose from: {", ".join(others)}')

    def print_round_summary(self):
        print('\n' + '='*52)
        print('  DRINK SUMMARY')
        print('='*52)
        any_drinks = False
        for p in self.players:
            if p.name == 'House': continue
            net = p.drinks_owed()
            if not p.drink_log: continue
            any_drinks = True
            print(f'\n  {p.name}  =>  {net} sip(s) this round')
            for sips, reason in p.drink_log:
                sign = f'+{sips}' if sips > 0 else str(sips)
                print(f'    {sign:>4}  {reason}')
            p.total_drinks += max(0, net)
        if not any_drinks:
            print('  No drinks this round!')
        print('\n' + '='*52 + '\n')


class HandEvaluator:
    @staticmethod
    def compare(player_hand: Hand, dealer_hand: Hand) -> str:
        p_bj = player_hand.is_blackjack()
        d_bj = dealer_hand.is_blackjack()
        if player_hand.is_bust():   return 'loss'
        if dealer_hand.is_bust():   return 'win'
        if p_bj and d_bj:           return 'push'
        if p_bj:                    return 'win'
        if d_bj:                    return 'loss'
        p, d = player_hand.score(), dealer_hand.score()
        return 'win' if p > d else 'loss' if p < d else 'push'


class RoundManager:
    """
    Manages one full round.

    Multi-player:  ALL players (including the dealer-player) play their own
                   hands first, then the dealer-player reveals and plays the
                   dealer hand. 3 players x 2 hands + 1 dealer hand = 7 hands.

    Single-player: Only the human plays; House runs the dealer hand silently.
    """

    def __init__(self, players, dealer_player, shoe, tracker,
                 wager=1, num_hands=2):
        self.players        = players        # players who play their own hands
        self.dealer_player  = dealer_player  # also plays dealer hand
        self.shoe           = shoe
        self.tracker        = tracker
        self.wager          = wager
        self.num_hands      = num_hands
        self._all_names     = [p.name for p in players]
        self._ace_credits   = []             # names who got A-clubs credit
        self._ace_clubs_flag = {'protected': False}
        self._four_aces_fd  = False

    # ============================================================ main flow

    def play_round(self):
        self._reset()
        self._deal_initial()
        self._check_four_aces('first_deal')
        self._player_turns()
        self._dealer_turn()
        self._check_four_aces('end_of_round')
        self._evaluate()
        self._round_end_drinks()
        self._show_results()
        self.tracker.print_round_summary()

    # ============================================================ reset

    def _reset(self):
        for p in self.players:
            p.reset_round(self.num_hands)
        # Dealer hand reset (may or may not be in self.players)
        if self.dealer_player not in self.players:
            self.dealer_player.reset_round(0)
            self.dealer_player.dealer_hand = Hand()
        self._ace_credits    = []
        self._ace_clubs_flag = {'protected': False}
        self._four_aces_fd   = False

    # ============================================================ dealing

    def _deal_card_to(self, hand, recipient_name):
        card     = self.shoe.deal_card()
        card_pos = len(hand.cards) + 1
        hand.cards.append(card)
        msgs = DrinkingRules.on_card_dealt(
            card, recipient_name, card_pos,
            self._all_names, self.dealer_player.name,
            self._ace_clubs_flag
        )
        for r, s, reason in msgs:
            if s == -1:
                self._ace_credits.append(recipient_name)
                print(f'    (i) {reason}')
            else:
                self.tracker.apply([(r, s, reason)])
        return card

    def _deal_initial(self):
        print('\n--- Dealing ---')
        dp = self.dealer_player
        for _ in range(2):
            for p in self.players:
                for hand in p.hands:
                    self._deal_card_to(hand, p.name)
            self._deal_card_to(dp.dealer_hand, dp.name)
        print(f'  Dealer ({dp.name}) shows: {dp.dealer_hand.cards[0]}, ?')
        for p in self.players:
            for i, h in enumerate(p.hands):
                tag = ' (also dealer)' if p.is_dealer else ''
                print(f'  {p.name}{tag} Hand {i+1}: {h}')

    # ============================================================ four aces

    def _check_four_aces(self, phase):
        all_cards = ([c for p in self.players for h in p.hands for c in h.cards]
                     + self.dealer_player.dealer_hand.cards)
        msgs, self._four_aces_fd = DrinkingRules.check_four_aces(
            all_cards, phase, self._four_aces_fd)
        self.tracker.apply(msgs)

    # ============================================================ player turns

    def _player_turns(self):
        ordered = sorted(self.players, key=lambda p: p.is_dealer)
        for p in ordered:
            idx = 0
            while idx < len(p.hands):
                print(f'\n--- {p.name} Hand {idx+1} ---')
                self._play_hand(p, p.hands[idx], idx)
                idx += 1

    def _play_hand(self, player, hand, hand_idx):
        dealer_up = self.dealer_player.dealer_hand.cards[0]

        # Insurance offer
        if dealer_up.rank == Rank.ACE and not hand.from_split and len(hand.cards) == 2:
            raw = input(f'  Dealer shows A. {player.name}: take insurance? [y/n]: ').strip().lower()
            if raw == 'y':
                hand.insured = True
                print(f'  {player.name} insures - hand treated as regular 21 if blackjack.')

        # Natural blackjack
        if hand.is_blackjack():
            hand.stood = True
            print(f'  BLACKJACK! {hand}')
            self.tracker.apply(
                DrinkingRules.on_blackjack(player.name, hand, self._all_names))
            return

        # Normal loop
        while not hand.stood and not hand.bust:
            print(f'  Hand: {hand}  |  Dealer shows: {dealer_up}')
            valid = ['h', 's']
            if len(hand.cards) == 2 and not hand.doubled: valid.append('d')
            if hand.can_split():                          valid.append('sp')

            # Mandatory split warning: 10-value pair that is not suited
            if (hand.can_split()
                    and hand.cards[0].rank.blackjack_value == 10
                    and not hand.is_suited()):
                print(f'  ⚠️  {player.name}: rules require you to split {hand.cards[0]}, {hand.cards[1]} (mandatory unless suited)')
                confirm = input('  Do you want to Split? [y/n]: ').strip().lower()
                if confirm == 'y':
                    action = 'sp'
                else:
                    print(f'  {player.name} overrides the mandatory split rule. Play with honor!')
                    action = self._get_input(valid)
            else:
                action = self._get_input(valid)

            if action == 's':
                hand.stood = True
                print(f'  {player.name} stands.')

            elif action == 'h':
                self._deal_card_to(hand, player.name)
                print(f'  Hit: {hand.cards[-1]}  -> {hand}')
                if hand.is_bust():
                    hand.bust = hand.stood = True
                    print(f'  BUST!')

            elif action == 'd':
                hand.doubled = True
                self._deal_card_to(hand, player.name)
                hand.stood = True
                print(f'  Double down: {hand.cards[-1]}  -> {hand}')
                if hand.is_bust():
                    hand.bust = True
                    print(f'  BUST on double!')

            elif action == 'sp':
                new_hand = hand.split(self.shoe)
                player.hands.insert(hand_idx + 1, new_hand)
                print(f'  Split! This hand: {hand}  |  New hand: {new_hand}')
                for h in (hand, new_hand):
                    if h.is_blackjack():
                        hand.stood = True
                        print(f'  Split BLACKJACK! {h}')
                        self.tracker.apply(
                            DrinkingRules.on_blackjack(player.name, h, self._all_names))
                return  # let the while loop in _player_turns advance to new hand

    @staticmethod
    def _get_input(valid):
        labels = {'h': 'hit', 's': 'stand', 'd': 'double', 'sp': 'split'}
        opts   = ', '.join(f'{k}={labels[k]}' for k in valid)
        while True:
            raw = input(f'  Action [{opts}]: ').strip().lower()
            if raw in valid: return raw
            print(f'  Invalid. Choose: {", ".join(valid)}')

    # ============================================================ dealer turn

    def _dealer_turn(self):
        dp     = self.dealer_player
        d_hand = dp.dealer_hand
        print(f'\n--- Dealer ({dp.name}) ---')
        print(f'  Reveals: {d_hand}')

        if d_hand.is_blackjack():
            print('  Dealer BLACKJACK!')
        else:
            while d_hand.score() < 17:
                self._deal_card_to(d_hand, dp.name)
                print(f'  Dealer hits: {d_hand.cards[-1]}  -> {d_hand}')
            if d_hand.is_bust():
                print('  Dealer BUSTS!')
            else:
                print(f'  Dealer stands at {d_hand.score()}.')

        self.tracker.apply(DrinkingRules.on_dealer_hand_revealed(d_hand))

    # ============================================================ evaluation

    def _evaluate(self):
        print('\n--- Results ---')
        d_hand          = self.dealer_player.dealer_hand
        winning_hds     = []
        dealer_lost_all = True

        for p in self.players:
            for i, hand in enumerate(p.hands):
                result     = HandEvaluator.compare(hand, d_hand)
                hand.result = result
                icon = {'win': 'WIN', 'loss': 'LOSS', 'push': 'PUSH'}[result]
                print(f'  {p.name} H{i+1}: {hand}  => {icon}')
                if result == 'win':
                    winning_hds.append((p.name, hand))
                else:
                    dealer_lost_all = False
                self.tracker.apply(
                    DrinkingRules.on_hand_resolved(p.name, hand, self._all_names))

            p.total_wins   += p.round_wins()
            p.total_losses += p.round_losses()
            p.total_pushes += p.round_pushes()

        if dealer_lost_all and winning_hds:
            self.tracker.apply(
                DrinkingRules.on_hard_dealer_switch(
                    self.dealer_player.name, winning_hds,
                    self._ace_clubs_flag['protected']))

    def _round_end_drinks(self):
        self.tracker.apply(DrinkingRules.on_round_end(self.players, self.wager))
        for name in self._ace_credits:
            p = next((x for x in self.players if x.name.lower() == name.lower()), None)
            if p: self.tracker.apply_ace_clubs_credit(p)

    # ============================================================ display

    def _show_results(self):
        print('\n' + '='*52)
        rows = []
        for p in self.players:
            for i, h in enumerate(p.hands):
                rows.append([f'{p.name} H{i+1}', str(h),
                             h.result.upper() if h.result else '-'])
        dh = self.dealer_player.dealer_hand
        rows.append([f'Dealer ({self.dealer_player.name})', str(dh),
                     'BJ' if dh.is_blackjack() else 'BUST' if dh.is_bust() else str(dh.score())])
        print(tabulate(rows, headers=['Seat', 'Hand', 'Result'], tablefmt='pretty'))
        print('='*52)


class DrinkingBlackJack:
    """
    Multi-player (2-4 seats):
      One seat rotates as dealer every n rounds (n = number of seats).
      The dealer-seat plays their own 2 hands AND runs the dealer hand.
      With 3 players: 3 x 2 player hands + 1 dealer hand = 7 hands total.

    Single-player (1 seat):
      House is always dealer. Human always plays. No rotation.
    """

    def __init__(self):
        self.all_seats    = []
        self.players      = []
        self.dealer_player = None
        self.shoe         = None
        self.wager        = 1
        self.num_hands    = 2
        self.round_count  = 0
        self._dealer_idx  = 0
        self._house_mode  = False

    # =========================================================== setup

    def setup(self):
        print('\n' + '='*52)
        #print('  DRINKING BLACKJACK')
        print("Welcome to Drinking BlackJack! 🃏🍻")
        print(f"Rules: {__rules_source__}")
        print(f"Rules last verified: {__rules_last_verified__}")
        print(f"Version: {__version__}")
        print('='*52)
        verify_rules()

        n = self._ask_int('Number of players (1-4): ', 1, 4)
        names = []
        for i in range(n):
            name = input(f'  Name for player {i+1}: ').strip() or f'Player {i+1}'
            names.append(name)

        self.wager       = self._ask_int('  Wager sips per hand (default 1): ', 1, 20, default=1)
        num_decks        = self._ask_int('  Number of decks 1-8 (default 1): ', 1, 8,  default=1)
        self.all_seats   = names
        self._house_mode = (n == 1)
        self._dealer_idx = 0
        self._assign_dealer()

        self.shoe = Shoe(num_decks)
        self.shoe.shuffle()

        if self._house_mode:
            print(f'  Single-player mode: you vs the House')
        else:
            print(f'  {n} players | dealer rotates every {n} round(s)')
            print(f'  First dealer: {self.dealer_player.name}')
            print(f'  Hands per round: {n} x {self.num_hands} player + 1 dealer = {n*self.num_hands + 1}')

    def _assign_dealer(self):
        if self._house_mode:
            human           = Player(self.all_seats[0])
            house           = Player('House')
            house.is_dealer = True
            self.players       = [human]
            self.dealer_player = house
            house.dealer_hand  = Hand()
        else:
            prev_stats = {p.name: (p.total_wins, p.total_losses,
                                   p.total_pushes, p.total_drinks)
                         for p in self.players}
            dealer_name = self.all_seats[self._dealer_idx]
            self.players = [Player(n) for n in self.all_seats]
            for p in self.players:
                if p.name in prev_stats:
                    (p.total_wins, p.total_losses,
                     p.total_pushes, p.total_drinks) = prev_stats[p.name]
                if p.name.lower() == dealer_name.lower():
                    p.is_dealer        = True
                    self.dealer_player = p

    def _rotate_dealer(self):
        if self._house_mode: return
        self._dealer_idx = (self._dealer_idx + 1) % len(self.all_seats)
        self._assign_dealer()
        print(f'  Dealer rotates => {self.dealer_player.name} is now dealer.')

    # =========================================================== main loop

    def play(self):
        self.setup()

        while True:
            self.round_count += 1
            dealer_label = 'House' if self._house_mode else self.dealer_player.name
            print(f'\n{"="*52}')
            print(f'  ROUND {self.round_count}  |  Dealer: {dealer_label}')
            print('='*52)

            tracker = DrinkTracker(
                self.players + ([self.dealer_player] if self._house_mode else []),
                self.dealer_player
            )

            rm = RoundManager(
                self.players, self.dealer_player,
                self.shoe, tracker, self.wager, self.num_hands
            )
            rm.play_round()

            if (not self._house_mode and
                    self.round_count % len(self.all_seats) == 0):
                self._rotate_dealer()

            if input('\nPlay another round? [y/n]: ').strip().lower() != 'y':
                self._final_summary()
                break

    # =========================================================== summary

    def _final_summary(self):
        print('\n' + '='*52)
        print('  FINAL SUMMARY')
        print('='*52)
        rows = [(p.name, p.total_wins, p.total_losses,
                 p.total_pushes, p.total_drinks)
                for p in self.players]
        print(tabulate(rows,
            headers=['Player','Wins','Losses','Pushes','Total Drinks'],
            tablefmt='pretty'))
        print('\nThanks for playing!')

    @staticmethod
    def _ask_int(prompt, lo, hi, default=None):
        while True:
            try:
                raw = input(f'  {prompt}').strip()
                if raw == '' and default is not None: return default
                val = int(raw)
                if lo <= val <= hi: return val
                print(f'  Enter a number between {lo} and {hi}.')
            except ValueError:
                print('  Invalid input.')


game = DrinkingBlackJack()
game.play()
