"""
rules_config.py
---------------
Drinking rules for Drinking BlackJack, sourced from:
https://github.com/robert-rjm/Drinking-BlackJack/blob/7e4b344dfe1ade7e047bdef96310619a0533d4cd/Rules.md

All sip values are in 'sips' (the agreed wager unit).
This file is intended to be imported by drinking.py, which calls
evaluate_event(event, context) to get a list of DrinkInstruction objects.

Context dict keys used throughout:
    player          str     - name of the acting player
    all_players     list    - list of all player names
    dealer          str     - name of the current dealer
    hand            list    - cards in the relevant hand, e.g. [('A','♠'), ('J','♠')]
    dealer_hand     list    - dealer's final hand
    num_hands       int     - number of hands each player is playing
    wager           int     - sips wagered per hand (agreed at game start)
    net_losses      dict    - {player_name: int} net hands lost this round
    player_results  dict    - {player_name: {'won': int, 'lost': int, 'push': int}}
    card_position   int     - 1-indexed position of card dealt (for Ace of Spades rule)
    doubled         bool    - whether the hand was doubled
    split           bool    - whether this hand came from a split
"""

__version__ = "1.0.0"
__rules_source__ = "https://github.com/robert-rjm/Drinking-BlackJack/blob/7e4b344dfe1ade7e047bdef96310619a0533d4cd/Rules.md"
__rules_last_verified__ = "2026-04-01"

from dataclasses import dataclass, field
from typing import Callable


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DrinkInstruction:
    """A single drinking outcome."""
    who: str | list        # player name, "dealer", "all", or list of names
    sips: int
    reason: str


@dataclass
class Rule:
    """A named rule with an evaluator function."""
    name: str
    description: str
    evaluate: Callable  # (context: dict) -> list[DrinkInstruction]


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _is_suited(hand: list) -> bool:
    """All cards in the hand share the same suit."""
    suits = [card[1] for card in hand]
    return len(set(suits)) == 1


def _is_blackjack(hand: list) -> bool:
    """First two cards form a blackjack (Ace + 10-value card)."""
    if len(hand) != 2:
        return False
    ranks = {card[0] for card in hand}
    ten_values = {'10', 'J', 'Q', 'K'}
    return 'A' in ranks and bool(ranks & ten_values)


def _blackjack_multiplier(hand: list) -> int:
    """
    Cumulative ×2 multiplier for blackjack bonus sips.
    Base = 1 sip. Multipliers stack:
        suited (same suit)      ×2
        Ace + Jack specifically ×2
        both cards black        ×2
    """
    multiplier = 1
    ranks  = [card[0] for card in hand]
    suits  = [card[1] for card in hand]

    if _is_suited(hand):
        multiplier *= 2

    if set(ranks) == {'A', 'J'}:
        multiplier *= 2

    black_suits = {'♠', '♣'}
    if all(s in black_suits for s in suits):
        multiplier *= 2

    return multiplier


def _card_value_rank(rank: str) -> int:
    """Return numeric value (for membership checks, not hand scoring)."""
    face = {'J': 10, 'Q': 10, 'K': 10, 'A': 11}
    return face.get(rank, int(rank))


# ---------------------------------------------------------------------------
# Individual rule evaluators
# ---------------------------------------------------------------------------

# --- Ace of Clubs dealt to Player ---
def _rule_ace_clubs_player(ctx: dict) -> list[DrinkInstruction]:
    """
    Player receives Ace of Clubs → subtract 1 sip from their net total
    at end of round (minimum 0). Modelled as a -1 sip credit.
    """
    card = ctx.get('card_dealt')
    if card and card == ('A', '♣') and ctx.get('recipient') == 'player':
        return [DrinkInstruction(
            who=ctx['player'],
            sips=-1,
            reason="Ace of Clubs dealt to player: -1 sip from net total (min 0)"
        )]
    return []


# --- Ace of Spades dealt to Player ---
def _rule_ace_spades_player(ctx: dict) -> list[DrinkInstruction]:
    """
    Player receives Ace of Spades as Nth card →
    the Nth next Player (in turn order) drinks 1 sip.
    """
    card = ctx.get('card_dealt')
    if card and card == ('A', '♠') and ctx.get('recipient') == 'player':
        position = ctx.get('card_position', 1)  # 1-indexed card in hand
        players = ctx.get('all_players', [])
        current_idx = players.index(ctx['player'])
        target_idx = (current_idx + position) % len(players)
        target = players[target_idx]
        return [DrinkInstruction(
            who=target,
            sips=1,
            reason=f"Ace of Spades dealt to {ctx['player']} (card #{position}): "
                   f"{target} drinks 1 sip"
        )]
    return []


# --- Ace of Hearts dealt to Player ---
def _rule_ace_hearts_player(ctx: dict) -> list[DrinkInstruction]:
    """Player receives Ace of Hearts → that player drinks 1 sip."""
    card = ctx.get('card_dealt')
    if card and card == ('A', '♥') and ctx.get('recipient') == 'player':
        return [DrinkInstruction(
            who=ctx['player'],
            sips=1,
            reason="Ace of Hearts dealt to player: treat yourself to a sip"
        )]
    return []


# --- Ace of Diamonds dealt to Player ---
def _rule_ace_diamonds_player(ctx: dict) -> list[DrinkInstruction]:
    """Player receives Ace of Diamonds → Dealer drinks 1 sip."""
    card = ctx.get('card_dealt')
    if card and card == ('A', '♦') and ctx.get('recipient') == 'player':
        return [DrinkInstruction(
            who=ctx['dealer'],
            sips=1,
            reason=f"Ace of Diamonds dealt to {ctx['player']}: dealer drinks 1 sip"
        )]
    return []


# --- Ace of Clubs dealt to Dealer ---
def _rule_ace_clubs_dealer(ctx: dict) -> list[DrinkInstruction]:
    """
    Dealer receives Ace of Clubs → dealer is exempt from the Hard Dealer
    Switch drinking penalty. No sips now; this flag is checked elsewhere.
    """
    card = ctx.get('card_dealt')
    if card and card == ('A', '♣') and ctx.get('recipient') == 'dealer':
        # No sips directly — sets a protection flag used in hard_dealer_switch
        ctx['dealer_ace_clubs_protection'] = True
    return []


# --- Ace of Spades dealt to Dealer ---
def _rule_ace_spades_dealer(ctx: dict) -> list[DrinkInstruction]:
    """
    Dealer receives Ace of Spades:
      Odd-positioned card  → Dealer drinks 1 sip
      Even-positioned card → all Players drink 1 sip
    """
    card = ctx.get('card_dealt')
    if card and card == ('A', '♠') and ctx.get('recipient') == 'dealer':
        position = ctx.get('card_position', 1)
        if position % 2 == 1:
            return [DrinkInstruction(
                who=ctx['dealer'],
                sips=1,
                reason=f"Ace of Spades dealt to dealer (card #{position}, odd): dealer drinks 1"
            )]
        else:
            return [DrinkInstruction(
                who='all',
                sips=1,
                reason=f"Ace of Spades dealt to dealer (card #{position}, even): all players drink 1"
            )]
    return []


# --- Ace of Hearts dealt to Dealer ---
def _rule_ace_hearts_dealer(ctx: dict) -> list[DrinkInstruction]:
    """Dealer receives Ace of Hearts → all players drink 1 sip."""
    card = ctx.get('card_dealt')
    if card and card == ('A', '♥') and ctx.get('recipient') == 'dealer':
        return [DrinkInstruction(
            who='all',
            sips=1,
            reason="Ace of Hearts dealt to dealer: everyone drinks 1 sip"
        )]
    return []


# --- Ace of Diamonds dealt to Dealer ---
def _rule_ace_diamonds_dealer(ctx: dict) -> list[DrinkInstruction]:
    """Dealer receives Ace of Diamonds → all Players except dealer drink 1 sip."""
    card = ctx.get('card_dealt')
    if card and card == ('A', '♦') and ctx.get('recipient') == 'dealer':
        return [DrinkInstruction(
            who='players_only',
            sips=1,
            reason="Ace of Diamonds dealt to dealer: all players (not dealer) drink 1 sip"
        )]
    return []


# --- Net hand losses ---
def _rule_net_hand_losses(ctx: dict) -> list[DrinkInstruction]:
    """
    Each player drinks 1 sip per net hand lost against the dealer.
    Wins and losses offset each other; only net negatives result in sips.
    """
    instructions = []
    results = ctx.get('player_results', {})
    wager = ctx.get('wager', 1)
    for player, res in results.items():
        net = res.get('won', 0) - res.get('lost', 0)
        if net < 0:
            instructions.append(DrinkInstruction(
                who=player,
                sips=abs(net) * wager,
                reason=f"{player} net {net} hands: drinks {abs(net) * wager} sip(s)"
            ))
    return instructions


# --- Other player wins ALL their hands ---
def _rule_other_player_wins_all(ctx: dict) -> list[DrinkInstruction]:
    """
    When a player wins ALL their hands, other players may drink:
      - Lost at least 1 hand → 1 sip per hand the winner won
      - Won all own hands    → 0 sips (immune)
      - No losses but ≥1 push → (winner's wins) - (own wins) sips, min 0
    """
    instructions = []
    results = ctx.get('player_results', {})

    for winner, w_res in results.items():
        w_won  = w_res.get('won', 0)
        w_lost = w_res.get('lost', 0)
        w_push = w_res.get('push', 0)
        if w_lost > 0 or w_push > 0:
            continue  # not a clean sweep

        for other, o_res in results.items():
            if other == winner:
                continue
            o_won  = o_res.get('won', 0)
            o_lost = o_res.get('lost', 0)
            o_push = o_res.get('push', 0)

            if o_lost == 0 and o_push == 0:
                sips = 0  # immune: won all own hands
            elif o_lost == 0 and o_push > 0:
                sips = max(0, w_won - o_won)
            else:
                sips = w_won

            if sips > 0:
                instructions.append(DrinkInstruction(
                    who=other,
                    sips=sips,
                    reason=f"{winner} won all hands → {other} drinks {sips} sip(s)"
                ))
    return instructions


# --- Blackjack bonus ---
def _rule_blackjack_bonus(ctx: dict) -> list[DrinkInstruction]:
    """
    Any player blackjack → everyone drinks 1 sip (base), multiplied by:
      ×2 if suited
      ×2 if Ace + Jack specifically
      ×2 if both cards are black (♠ or ♣)
    Insurance exemption: if player insured their blackjack, skip.
    """
    hand = ctx.get('hand', [])
    insured = ctx.get('insured', False)

    if not _is_blackjack(hand) or insured:
        return []

    multiplier = _blackjack_multiplier(hand)
    sips = 1 * multiplier

    return [DrinkInstruction(
        who='all_except_player',
        sips=sips,
        reason=f"Blackjack by {ctx['player']} (×{multiplier}): everyone drinks {sips} sip(s)"
    )]


# --- Double/Split exception to immunity ---
def _rule_doubles_splits_immunity_exception(ctx: dict) -> list[DrinkInstruction]:
    """
    If a player wins a doubled hand or wins both hands of a split,
    all other players drink 1 sip — even those who won all their hands.
    """
    instructions = []
    doubled = ctx.get('doubled', False)
    split_win_both = ctx.get('split_win_both', False)
    won = ctx.get('hand_won', False)

    if won and (doubled or split_win_both):
        all_players = ctx.get('all_players', [])
        for other in all_players:
            if other != ctx['player']:
                instructions.append(DrinkInstruction(
                    who=other,
                    sips=1,
                    reason=f"{ctx['player']} won a {'doubled' if doubled else 'split'} hand: "
                           f"{other} drinks 1 sip (immunity exception)"
                ))
    return instructions


# --- Suited winning hand ---
def _rule_suited_winning_hand(ctx: dict) -> list[DrinkInstruction]:
    """
    Player wins a hand where all cards are the same suit:
      Normal suited win    → 1 sip for all other players
      Doubled or split win → 4 sips for all other players
    """
    hand = ctx.get('hand', [])
    won  = ctx.get('hand_won', False)
    doubled = ctx.get('doubled', False)
    split   = ctx.get('split', False)

    if not (won and _is_suited(hand)):
        return []

    sips = 4 if (doubled or split) else 1
    all_players = ctx.get('all_players', [])
    instructions = []
    for other in all_players:
        if other != ctx['player']:
            instructions.append(DrinkInstruction(
                who=other,
                sips=sips,
                reason=f"{ctx['player']} won with a suited hand "
                       f"({'doubled/split, ' if doubled or split else ''}all {hand[0][1]}): "
                       f"{other} drinks {sips} sip(s)"
            ))
    return instructions


# --- 21 with 5+ cards (hand out sips) ---
def _rule_21_five_plus_cards(ctx: dict) -> list[DrinkInstruction]:
    """
    Player reaches exactly 21 with 5+ cards → may hand out N sips total
    (where N = number of cards). Distribution is player's choice.
    This evaluator just announces the entitlement; the game loop handles
    the player's distribution decision.
    """
    hand    = ctx.get('hand', [])
    total   = ctx.get('hand_total', 0)

    if total == 21 and len(hand) >= 5:
        return [DrinkInstruction(
            who=ctx['player'],   # who gets to GIVE OUT sips
            sips=-len(hand),     # negative = sips to distribute (convention)
            reason=f"{ctx['player']} hit 21 with {len(hand)} cards: "
                   f"may hand out {len(hand)} sips to others"
        )]
    return []


# --- Winning with 5+ cards ---
def _rule_win_five_plus_cards(ctx: dict) -> list[DrinkInstruction]:
    """
    Player wins a hand with 5+ cards → all other players drink 1 sip.
    Stacks with the 21-with-5+-cards rule if the total is exactly 21.
    A push does not trigger this.
    """
    hand = ctx.get('hand', [])
    won  = ctx.get('hand_won', False)

    if won and len(hand) >= 5:
        all_players = ctx.get('all_players', [])
        return [
            DrinkInstruction(
                who=other,
                sips=1,
                reason=f"{ctx['player']} won with {len(hand)} cards: {other} drinks 1 sip"
            )
            for other in all_players if other != ctx['player']
        ]
    return []


# --- Dealer suited hand ---
def _rule_dealer_suited_hand(ctx: dict) -> list[DrinkInstruction]:
    """
    Dealer's final hand is suited → all players drink 2 sips.
    Applies regardless of win/loss/bust.
    """
    dealer_hand = ctx.get('dealer_hand', [])
    if _is_suited(dealer_hand) and len(dealer_hand) >= 2:
        return [DrinkInstruction(
            who='all',
            sips=2,
            reason=f"Dealer's hand is suited (all {dealer_hand[0][1]}): everyone drinks 2 sips"
        )]
    return []


# --- Four Aces on the table ---
def _rule_four_aces(ctx: dict) -> list[DrinkInstruction]:
    """
    All 4 Aces visible after first deal  → everyone drinks 2 sips.
    All 4 Aces visible at end of round   → everyone drinks 1 sip.
    These two cannot stack (first-deal rule takes priority if both apply).
    """
    phase     = ctx.get('ace_check_phase')   # 'first_deal' or 'end_of_round'
    ace_count = ctx.get('visible_ace_count', 0)

    if ace_count < 4:
        return []

    if phase == 'first_deal':
        return [DrinkInstruction(
            who='all',
            sips=2,
            reason="All 4 Aces on the table after first deal: everyone drinks 2 sips"
        )]
    elif phase == 'end_of_round':
        # Only trigger if they weren't all present at first deal
        if not ctx.get('four_aces_triggered_first_deal', False):
            return [DrinkInstruction(
                who='all',
                sips=1,
                reason="All 4 Aces visible at end of round: everyone drinks 1 sip"
            )]
    return []


# --- Hard Dealer Switch ---
def _rule_hard_dealer_switch(ctx: dict) -> list[DrinkInstruction]:
    """
    Triggered when the dealer loses ALL hands (push ≠ loss).
    Dealer drinks sips based on all players' winning hands:
      Regular win      → 1 sip
      Blackjack        → 2+ sips (uses blackjack multiplier)
      Doubled win      → 2 sips
      Split hands      → counted separately
    Ace of Clubs protection: if dealer was dealt Ace of Clubs, skip drinking.
    """
    if not ctx.get('hard_dealer_switch', False):
        return []

    if ctx.get('dealer_ace_clubs_protection', False):
        return [DrinkInstruction(
            who=ctx['dealer'],
            sips=0,
            reason="Hard Dealer Switch triggered but Ace of Clubs protects dealer from drinking"
        )]

    results   = ctx.get('player_results', {})
    hand_details = ctx.get('all_winning_hands', [])
    # hand_details: list of dicts with keys: player, blackjack, doubled, split, hand
    total_sips = 0
    reasons    = []

    for hd in hand_details:
        if hd.get('blackjack'):
            mult = _blackjack_multiplier(hd.get('hand', []))
            s = max(2, mult)
            total_sips += s
            reasons.append(f"  {hd['player']} blackjack → {s} sip(s)")
        elif hd.get('doubled'):
            total_sips += 2
            reasons.append(f"  {hd['player']} doubled win → 2 sips")
        else:
            total_sips += 1
            reasons.append(f"  {hd['player']} regular win → 1 sip")

    reason_str = "Hard Dealer Switch — dealer drinks:\n" + "\n".join(reasons)
    return [DrinkInstruction(
        who=ctx['dealer'],
        sips=total_sips,
        reason=reason_str
    )]


# ---------------------------------------------------------------------------
# Master rule registry
# ---------------------------------------------------------------------------

RULES: list[Rule] = [
    Rule(
        name="ace_clubs_player",
        description="Player gets Ace of Clubs: -1 sip from net total (min 0)",
        evaluate=_rule_ace_clubs_player,
    ),
    Rule(
        name="ace_spades_player",
        description="Player gets Ace of Spades: Nth next player drinks 1 sip",
        evaluate=_rule_ace_spades_player,
    ),
    Rule(
        name="ace_hearts_player",
        description="Player gets Ace of Hearts: that player drinks 1 sip",
        evaluate=_rule_ace_hearts_player,
    ),
    Rule(
        name="ace_diamonds_player",
        description="Player gets Ace of Diamonds: dealer drinks 1 sip",
        evaluate=_rule_ace_diamonds_player,
    ),
    Rule(
        name="ace_clubs_dealer",
        description="Dealer gets Ace of Clubs: dealer exempt from Hard Switch drinking",
        evaluate=_rule_ace_clubs_dealer,
    ),
    Rule(
        name="ace_spades_dealer",
        description="Dealer gets Ace of Spades: odd position→dealer drinks, even→all drink",
        evaluate=_rule_ace_spades_dealer,
    ),
    Rule(
        name="ace_hearts_dealer",
        description="Dealer gets Ace of Hearts: all players drink 1 sip",
        evaluate=_rule_ace_hearts_dealer,
    ),
    Rule(
        name="ace_diamonds_dealer",
        description="Dealer gets Ace of Diamonds: all players except dealer drink 1 sip",
        evaluate=_rule_ace_diamonds_dealer,
    ),
    Rule(
        name="net_hand_losses",
        description="Each player drinks 1 sip per net hand lost (wins offset losses)",
        evaluate=_rule_net_hand_losses,
    ),
    Rule(
        name="other_player_wins_all",
        description="When a player sweeps all hands, others may drink based on their results",
        evaluate=_rule_other_player_wins_all,
    ),
    Rule(
        name="blackjack_bonus",
        description="Player blackjack: everyone drinks 1 sip, multiplied for suited/AJ/black",
        evaluate=_rule_blackjack_bonus,
    ),
    Rule(
        name="doubles_splits_immunity_exception",
        description="Winning a doubled/split hand: all others drink 1 sip even if immune",
        evaluate=_rule_doubles_splits_immunity_exception,
    ),
    Rule(
        name="suited_winning_hand",
        description="Winning a suited hand: others drink 1 sip (4 if doubled/split)",
        evaluate=_rule_suited_winning_hand,
    ),
    Rule(
        name="21_five_plus_cards",
        description="Hitting exactly 21 with 5+ cards: player hands out N sips",
        evaluate=_rule_21_five_plus_cards,
    ),
    Rule(
        name="win_five_plus_cards",
        description="Winning with 5+ cards: all other players drink 1 sip",
        evaluate=_rule_win_five_plus_cards,
    ),
    Rule(
        name="dealer_suited_hand",
        description="Dealer's final hand is suited: all players drink 2 sips",
        evaluate=_rule_dealer_suited_hand,
    ),
    Rule(
        name="four_aces",
        description="All 4 Aces visible: 2 sips after first deal, 1 sip at end of round",
        evaluate=_rule_four_aces,
    ),
    Rule(
        name="hard_dealer_switch",
        description="Dealer loses all hands: dealer drinks for each player's winning hand",
        evaluate=_rule_hard_dealer_switch,
    ),
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_event(event_name: str, context: dict) -> list[DrinkInstruction]:
    """
    Entry point for drinking.py.
    Pass the event name and a populated context dict.
    Returns a list of DrinkInstructions to apply.

    Recognised event_name values:
        'card_dealt'            - a card was just dealt (set ctx['card_dealt'] and ctx['recipient'])
        'round_end'             - all hands played, compute net outcomes
        'hand_resolved'         - a single hand just finished (set ctx['hand_won'] etc.)
        'blackjack'             - a player has blackjack
        'dealer_hand_revealed'  - dealer's final hand is set
        'ace_check'             - check for 4 aces on the table
        'hard_dealer_switch'    - dealer lost all hands
    """
    context.setdefault('dealer_ace_clubs_protection', False)

    EVENT_RULE_MAP: dict[str, list[str]] = {
        'card_dealt': [
            'ace_clubs_player', 'ace_spades_player',
            'ace_hearts_player', 'ace_diamonds_player',
            'ace_clubs_dealer', 'ace_spades_dealer',
            'ace_hearts_dealer', 'ace_diamonds_dealer',
        ],
        'round_end': [
            'net_hand_losses',
            'other_player_wins_all',
        ],
        'hand_resolved': [
            'doubles_splits_immunity_exception',
            'suited_winning_hand',
            '21_five_plus_cards',
            'win_five_plus_cards',
        ],
        'blackjack': [
            'blackjack_bonus',
        ],
        'dealer_hand_revealed': [
            'dealer_suited_hand',
        ],
        'ace_check': [
            'four_aces',
        ],
        'hard_dealer_switch': [
            'hard_dealer_switch',
        ],
    }

    rule_names = EVENT_RULE_MAP.get(event_name, [])
    rule_lookup = {r.name: r for r in RULES}
    instructions: list[DrinkInstruction] = []

    for name in rule_names:
        rule = rule_lookup.get(name)
        if rule:
            instructions.extend(rule.evaluate(context))

    return instructions


# ---------------------------------------------------------------------------
# Game setup constants (from the Rules.md Game Setup section)
# ---------------------------------------------------------------------------

GAME_SETUP = {
    'recommended_hands_per_player': 2,      # all players play the same number
    'default_wager_sips': 1,                # sips per hand (agreed before start)
    'dealer_stands_on': 'all_17s',          # including soft 17
    'blackjack_payout': '2:1',
    'double_down': 'any_two_card_hand',     # including after split
    'split_tens': 'mandatory',              # except suited 10s
    'split_aces_limit': 'unlimited',
    'blackjack_on_split_aces': True,        # counts as blackjack, not just 21
    'dealer_role_rotation': 'every_n_rounds_where_n_equals_num_players',
    'reshuffle': 'after_each_round',
}

# ---------------------------------------------------------------------------
# Potential future rules (not yet active — for reference)
# ---------------------------------------------------------------------------

FUTURE_RULES = [
    "Dealer Survivor: Everyone drinks 1 sip if dealer does not bust with 6+ cards",
    "Lucky 7s: Hand totalling 21 with three 7s → all others drink 7 sips",
    "Mirror Hands: Two players same total and same card count → both drink 1 sip",
    "Dealer Blackjack Toast: Dealer blackjack → everyone raises and drinks 2 sips",
    "Perfect Split: Split and win both hands with same total → others drink 2 sips",
    "Bust Chain: 3+ players bust in same round → last to bust drinks extra per prior bust",
]
