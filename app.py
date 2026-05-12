"""
app.py
======
Flask web server supporting two modes:

  referee — physical deck; you type cards as they are dealt; app tracks drinks.
  digital — virtual shoe; app deals cards automatically; full playable blackjack.

Run:
    python app.py

Then open http://<your-PC-IP>:5000 on any phone on the same WiFi.
"""

import io
import contextlib
import socket

from flask import Flask, request, jsonify, render_template

from referee import RefereeSession
from blackjack import Player, Hand, Shoe, HandEvaluator
from drinking_rules import DrinkingRules

app = Flask(__name__)
game_session: RefereeSession | None = None   # single-table, no auth needed


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------

def _patch_tracker(session: RefereeSession):
    """
    Replace the interactive sip-handout prompt with auto round-robin so the
    web version never blocks waiting for terminal input.
    """
    tracker = session.tracker

    def web_handout(giver: str, total: int, reason: str):
        print(f"    [drink] {reason}")
        others = [p for p in tracker.players if p.name.lower() != giver.lower()]
        if not others:
            return
        print(f"    {giver} auto-distributes {total} sip(s) round-robin")
        for i in range(total):
            t = others[i % len(others)]
            t.add_drink(1, f"{giver} handed 1 sip to {t.name} (5-card 21, auto)")
            print(f"    -> {t.name} +1 sip")

    tracker._handle_handout = web_handout


def _capture(fn, *args):
    """Call fn(*args) and return everything it printed as a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


def _newround_rotate(session: RefereeSession):
    """Rotate the dealer role one seat clockwise."""
    all_names  = [p.name for p in session.all_players]
    cur_idx    = all_names.index(session.dealer_name)
    new_dealer = all_names[(cur_idx + 1) % len(all_names)]
    for p in session.all_players:
        p.is_dealer   = (p.name == new_dealer)
        p.dealer_hand = Hand() if p.is_dealer else None
    session.dealer_name = new_dealer
    print(f"  Dealer rotates => {new_dealer} is now dealer.")


# ---------------------------------------------------------------------------
# State serialization & turn tracking
# ---------------------------------------------------------------------------

def _play_order(session: RefereeSession):
    """
    Turn order: dealer's left clockwise, dealer-player goes last.
    Returns list of player names.
    """
    all_names = [p.name for p in session.all_players]
    if session.dealer_name not in all_names:
        return all_names
    d_idx = all_names.index(session.dealer_name)
    order = []
    for i in range(1, len(all_names)):
        order.append(all_names[(d_idx + i) % len(all_names)])
    order.append(session.dealer_name)  # dealer plays their player hands last
    return order


def _hand_done(hand: Hand) -> bool:
    """True if hand cannot/should not act anymore."""
    return hand.stood or hand.bust or hand.is_bust() or hand.is_blackjack()


def _player_done(player) -> bool:
    """True if every betting hand for this player is finished."""
    if not player.hands:
        return True
    return all(_hand_done(h) for h in player.hands)


def _current_turn(session: RefereeSession):
    """
    Whose turn is it right now?
    Returns the player name, or None if no one is up (pre-deal or dealer phase).
    Only meaningful when initial deal has happened.
    """
    # Any cards on the table?
    has_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_cards:
        return None

    for name in _play_order(session):
        p = session._get_player(name)
        if p and not _player_done(p):
            return name
    return None  # all player hands done -> dealer phase


def _round_phase(session: RefereeSession) -> str:
    """
    'pre-deal'     -> waiting for initial deal
    'playing'      -> at least one player still has an active hand
    'dealer-ready' -> all player hands done, dealer hand not yet fully revealed
    'round-over'   -> dealer has stood/busted, results assigned
    """
    dealer = session._get_dealer()
    has_player_cards = any(len(h.cards) > 0 for p in session.all_players for h in p.hands)
    if not has_player_cards:
        return "pre-deal"

    if _current_turn(session) is not None:
        return "playing"

    # Player hands all done. Has dealer hand finished?
    d_hand = dealer.dealer_hand if dealer else None
    if d_hand and (d_hand.stood or d_hand.is_bust() or d_hand.score() >= 17 or d_hand.is_blackjack()):
        # Look for any unresolved results — if all hands have a result, round is over.
        all_resolved = all(
            h.result is not None for p in session.all_players for h in p.hands
        )
        if all_resolved:
            return "round-over"
    return "dealer-ready"


def _serialize_card(card) -> dict:
    """Compact JSON for a single card."""
    return {
        "rank": card.rank.label,
        "suit": card.suit.value,   # 'hearts' | 'diamonds' | 'clubs' | 'spades'
        "symbol": card.suit.symbol,
    }


def _serialize_hand(hand: Hand) -> dict:
    return {
        "cards":       [_serialize_card(c) for c in hand.cards],
        "score":       hand.score() if hand.cards else 0,
        "stood":       hand.stood,
        "bust":        hand.bust or (hand.cards and hand.is_bust()),
        "doubled":     hand.doubled,
        "from_split":  hand.from_split,
        "insured":     hand.insured,
        "result":      hand.result,
        "blackjack":   bool(hand.cards) and hand.is_blackjack(),
        "done":        _hand_done(hand),
    }


def _serialize_state(session: RefereeSession | None) -> dict:
    """Full snapshot for the UI."""
    if not session:
        return {"ok": False}

    dealer = session._get_dealer()
    phase  = _round_phase(session)
    turn   = _current_turn(session)

    table = []
    for p in session.all_players:
        entry = {
            "name":      p.name,
            "is_dealer": p.is_dealer,
            "hands":     [_serialize_hand(h) for h in p.hands],
            "done":      _player_done(p),
            "is_turn":   (p.name == turn),
        }
        table.append(entry)

    # Dealer hand — hide hole card while players are still acting (digital only)
    mode = getattr(session, "mode", "referee")
    d_hand_state = None
    if dealer and dealer.dealer_hand:
        d_cards = dealer.dealer_hand.cards
        if mode == "digital" and phase in ("playing", "pre-deal") and len(d_cards) >= 2:
            d_hand_state = {
                "cards":     [_serialize_card(d_cards[0]),
                              {"rank": "?", "suit": "hidden", "symbol": "?"}]
                              + [_serialize_card(c) for c in d_cards[2:]],
                "score":     "?",
                "hidden":    True,
                "blackjack": False,
                "bust":      False,
                "done":      False,
            }
        else:
            d_hand_state = {
                "cards":     [_serialize_card(c) for c in d_cards],
                "score":     dealer.dealer_hand.score() if d_cards else 0,
                "hidden":    False,
                "blackjack": bool(d_cards) and dealer.dealer_hand.is_blackjack(),
                "bust":      bool(d_cards) and dealer.dealer_hand.is_bust(),
                "done":      bool(d_cards) and (
                    dealer.dealer_hand.stood
                    or dealer.dealer_hand.is_bust()
                    or dealer.dealer_hand.score() >= 17
                ),
            }

    return {
        "ok":           True,
        "round":        session.round_count,
        "dealer":       session.dealer_name,
        "players":      [p.name for p in session.all_players],
        "mode":         getattr(session, "mode", "referee"),
        "table":        table,
        "dealer_hand":  d_hand_state,
        "current_turn": turn,
        "play_order":   _play_order(session),
        "phase":        phase,
    }


# ---------------------------------------------------------------------------
# Digital mode helpers
# ---------------------------------------------------------------------------

def _digital_get_player_hand(player, hand_label: str):
    """
    Get a player's betting hand by label, always using player.hands[idx].
    Unlike RefereeSession._get_hand, this never redirects to dealer_hand,
    so the dealer-player can still play their own betting hands.
    """
    try:
        idx = int(hand_label.lower().replace("hand", "").strip()) - 1
    except (ValueError, AttributeError):
        idx = 0
    while len(player.hands) <= idx:
        player.hands.append(Hand())
    return player.hands[idx]


def _digital_deal_card(session: RefereeSession, hand: Hand, recipient_name: str):
    """Deal one card from shoe into hand and fire ace drinking rules."""
    card     = session.shoe.deal_card()
    card_pos = len(hand.cards) + 1
    hand.cards.append(card)

    all_names = [p.name for p in session.all_players]
    msgs = DrinkingRules.on_card_dealt(
        card, recipient_name, card_pos,
        all_names, session.dealer_name,
        session._ace_clubs_flag,
    )
    for r, s, reason in msgs:
        if s == -1:
            session._ace_credits.append(recipient_name)
            print(f"    (i) {reason}")
        else:
            session.tracker.apply([(r, s, reason)])
    return card


def _digital_initial_deal(session: RefereeSession):
    """Deal 2 cards to every player hand and the dealer hand from the shoe."""
    dealer    = session._get_dealer()
    all_names = [p.name for p in session.all_players]

    print("\n--- Dealing ---")
    for _ in range(2):
        for p in session.all_players:
            for hand in p.hands:
                _digital_deal_card(session, hand, p.name)
        _digital_deal_card(session, dealer.dealer_hand, dealer.name)

    print(f"\n  Dealer ({dealer.name}) shows: {dealer.dealer_hand.cards[0]}, ?")
    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            tag = " (also dealer)" if p.is_dealer else ""
            print(f"  {p.name}{tag} Hand {i+1}: {hand}")
            if hand.is_blackjack():
                print(f"  *** {p.name} Hand {i+1} — BLACKJACK! ***")

    # Four-aces check after first deal
    all_cards = [c for p in session.all_players for h in p.hands for c in h.cards]
    all_cards += dealer.dealer_hand.cards
    msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
        all_cards, "first_deal", session._four_aces_fd)
    session.tracker.apply(msgs)


def _digital_dealer_turn(session: RefereeSession):
    """
    Reveal dealer hole card, hit until 17+, then auto-evaluate all player
    hands and fire the relevant drinking rules.
    """
    dealer = session._get_dealer()
    d_hand = dealer.dealer_hand

    print(f"\n--- Dealer ({dealer.name}) reveals ---")
    print(f"  Full hand: {d_hand}")

    if d_hand.is_blackjack():
        print("  Dealer BLACKJACK!")
    else:
        while d_hand.score() < 17:
            card = _digital_deal_card(session, d_hand, dealer.name)
            print(f"  Dealer hits: {card}  -> {d_hand}")
        if d_hand.is_bust():
            print("  Dealer BUSTS!")
        else:
            print(f"  Dealer stands at {d_hand.score()}.")

    session.tracker.apply(DrinkingRules.on_dealer_hand_revealed(d_hand))

    # Auto-evaluate every player hand
    print("\n--- Results ---")
    winning_hds     = []
    dealer_lost_all = True
    all_names       = [p.name for p in session.all_players]

    for p in session.all_players:
        for i, hand in enumerate(p.hands):
            if not hand.result:
                hand.result = HandEvaluator.compare(hand, d_hand)
            icon = {"win": "WIN", "loss": "LOSS", "push": "PUSH"}[hand.result]
            print(f"  {p.name} Hand {i+1}: {hand}  => {icon}")
            if hand.result == "win":
                winning_hds.append((p.name, hand))
            else:
                dealer_lost_all = False
            session.tracker.apply(
                DrinkingRules.on_hand_resolved(p.name, hand, all_names))

    if dealer_lost_all and winning_hds:
        session.tracker.apply(
            DrinkingRules.on_hard_dealer_switch(
                session.dealer_name, winning_hds,
                session._ace_clubs_flag["protected"]))

    # Four-aces end-of-round check
    all_cards  = [c for p in session.all_players for h in p.hands for c in h.cards]
    all_cards += d_hand.cards
    msgs, session._four_aces_fd = DrinkingRules.check_four_aces(
        all_cards, "end_of_round", session._four_aces_fd)
    session.tracker.apply(msgs)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/setup", methods=["POST"])
def setup():
    global game_session
    data = request.json

    names = [n.strip().capitalize() for n in data["players"] if n.strip()]
    if not names:
        return jsonify({"ok": False, "output": "No player names provided."})

    mode        = data.get("mode", "referee")   # "referee" | "digital"
    dealer_idx  = int(data.get("dealer_index", 0))
    dealer_name = names[min(dealer_idx, len(names) - 1)]
    wager       = int(data.get("wager", 1))
    num_hands   = int(data.get("num_hands", 2))

    players = []
    for name in names:
        p           = Player(name)
        p.is_dealer = (name == dealer_name)
        if p.is_dealer:
            p.dealer_hand = Hand()
        players.append(p)

    game_session      = RefereeSession(players, dealer_name, wager, num_hands)
    game_session.mode = mode

    if mode == "digital":
        num_decks         = int(data.get("num_decks", 1))
        game_session.shoe = Shoe(num_decks)
        game_session.shoe.shuffle()

    _patch_tracker(game_session)

    output = _capture(game_session.start_round)
    state  = _serialize_state(game_session)
    state.update({"output": output})
    return jsonify(state)


@app.route("/command", methods=["POST"])
def command():
    global game_session
    if not game_session:
        return jsonify({"ok": False, "output": "No active session — set up a game first."})

    cmd_str = (request.json or {}).get("cmd", "").strip()
    if not cmd_str:
        return jsonify({"ok": False, "output": "Empty command."})

    parts = cmd_str.split()
    cmd   = parts[0].lower()
    mode  = getattr(game_session, "mode", "referee")

    # Turn-order gate: in digital mode, per-player actions must come from the
    # player whose turn it currently is. (deal/dealer/endround/newround/status/help
    # are session-wide and bypass the gate.)
    TURN_GATED = {"hit", "stand", "double", "split", "insurance", "blackjack"}
    if mode == "digital" and cmd in TURN_GATED and len(parts) >= 2:
        current = _current_turn(game_session)
        target  = parts[1].strip().capitalize()
        if current is None:
            return jsonify({
                **_serialize_state(game_session),
                "output": "  Not in play phase — deal cards or run dealer turn.\n",
            })
        if target.lower() != current.lower():
            return jsonify({
                **_serialize_state(game_session),
                "output": f"  Out of order — it's {current}'s turn (not {target}).\n",
            })

    # Gate the dealer-reveal command too: only allow when all players are done
    if mode == "digital" and cmd == "dealer":
        phase = _round_phase(game_session)
        if phase == "pre-deal":
            return jsonify({
                **_serialize_state(game_session),
                "output": "  Deal cards first.\n",
            })
        if phase == "playing":
            current = _current_turn(game_session) or "a player"
            return jsonify({
                **_serialize_state(game_session),
                "output": f"  Cannot reveal dealer — {current} still has hands to play.\n",
            })

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):

        # ── Digital-only commands ────────────────────────────────────────────
        if mode == "digital":

            if cmd == "deal":
                # Initial deal — no card args; shoe deals automatically
                _digital_initial_deal(game_session)

            elif cmd == "hit":
                # hit <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: hit <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            card = _digital_deal_card(game_session, hand, player.name)
                            print(f"  {player.name} {hand_label} hits {card}: {hand}")
                            if hand.is_bust():
                                hand.bust = hand.stood = True
                                hand.result = "loss"
                                print("  BUST!")

            elif cmd == "stand":
                # stand <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: stand <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label  = parts[2] if len(parts) > 2 else "hand1"
                        hand        = _digital_get_player_hand(player, hand_label)
                        hand.stood  = True
                        print(f"  {player.name} {hand_label}: stands at {hand.score()}.")

            elif cmd == "double":
                # double <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: double <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if len(hand.cards) != 2:
                            print("  Can only double on first two cards.")
                        elif hand.stood or hand.bust:
                            print(f"  {player.name} {hand_label} is already done.")
                        else:
                            hand.doubled = True
                            card         = _digital_deal_card(game_session, hand, player.name)
                            hand.stood   = True
                            print(f"  {player.name} {hand_label} doubles down ({card}): {hand}")
                            if hand.is_bust():
                                hand.bust = True
                                hand.result = "loss"
                                print("  BUST on double!")

            elif cmd == "split":
                # split <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: split <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        if not hand.can_split():
                            print("  Cannot split this hand.")
                        else:
                            # Move second card to new hand
                            new_hand = Hand(from_split=True)
                            new_hand.cards.append(hand.cards.pop())
                            hand.from_split   = True
                            hand.split_count += 1
                            idx       = int(hand_label.lower().replace("hand", "").strip() or "1") - 1
                            new_label = f"hand{idx + 2}"
                            player.hands.insert(idx + 1, new_hand)
                            # Deal one card to each split hand (fires drinking rules)
                            _digital_deal_card(game_session, hand, player.name)
                            _digital_deal_card(game_session, new_hand, player.name)
                            print(f"  {player.name} splits:")
                            print(f"    {hand_label}: {hand}")
                            print(f"    {new_label}: {new_hand}")

            elif cmd == "insurance":
                # insurance <player> [hand<n>]
                if len(parts) < 2:
                    print("  Usage: insurance <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label    = parts[2] if len(parts) > 2 else "hand1"
                        hand          = _digital_get_player_hand(player, hand_label)
                        hand.insured  = True
                        print(f"  {player.name} {hand_label}: insured.")

            elif cmd == "blackjack":
                # blackjack <player> [hand<n>] — confirm natural BJ, fire drink rules
                if len(parts) < 2:
                    print("  Usage: blackjack <player> [hand<n>]")
                else:
                    player = game_session._get_player(parts[1])
                    if not player:
                        print(f"  Unknown player '{parts[1]}'.")
                    else:
                        hand_label = parts[2] if len(parts) > 2 else "hand1"
                        hand       = _digital_get_player_hand(player, hand_label)
                        hand.stood = True
                        all_names  = [p.name for p in game_session.all_players]
                        game_session.tracker.apply(
                            DrinkingRules.on_blackjack(player.name, hand, all_names))
                        print(f"  {player.name} BLACKJACK confirmed.")

            elif cmd == "dealer":
                # Auto-run dealer turn + evaluate all hands
                _digital_dealer_turn(game_session)

            elif cmd == "endround":
                game_session.cmd_endround()

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                if rotate:
                    _newround_rotate(game_session)
                if game_session.shoe.needs_reshuffle():
                    game_session.shoe.reset()
                    print("  Shoe reshuffled.")
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                _print_digital_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

        # ── Referee mode (original behaviour, unchanged) ─────────────────────
        else:

            if cmd == "deal":
                game_session.cmd_deal(parts)

            elif cmd == "action":
                game_session.cmd_action(parts)

            elif cmd == "result":
                game_session.cmd_result(parts)

            elif cmd == "dealer":
                game_session.cmd_dealer(parts)

            elif cmd == "fouraces":
                game_session.cmd_fouraces(parts)

            elif cmd == "endround":
                game_session.cmd_endround()

            elif cmd == "newround":
                rotate = len(parts) > 1 and parts[1].lower() == "rotate"
                if rotate:
                    _newround_rotate(game_session)
                game_session.start_round()
                _patch_tracker(game_session)

            elif cmd in ("status", "st"):
                game_session.cmd_status()

            elif cmd == "help":
                RefereeSession.print_help()

            else:
                print(f"  Unknown command '{cmd}'. Type 'help' for reference.")

    state = _serialize_state(game_session)
    state["output"] = buf.getvalue()
    return jsonify(state)


@app.route("/state")
def state():
    return jsonify(_serialize_state(game_session))


# ---------------------------------------------------------------------------
# Digital help
# ---------------------------------------------------------------------------

def _print_digital_help():
    print("""
  DIGITAL MODE COMMANDS
  =====================
  deal
      Deal initial 2 cards to all hands from the shoe.

  hit <player> [hand<n>]
      Deal one card from the shoe to that hand.
      Example: hit Rob hand1

  stand <player> [hand<n>]
      Mark the hand as stood.
      Example: stand Alice hand2

  double <player> [hand<n>]
      Double down — deal one card then stand. Must be on first two cards.
      Example: double Rob hand1

  split <player> [hand<n>]
      Split the hand and deal one card to each resulting hand.
      Example: split Rob hand1

  insurance <player> [hand<n>]
      Mark the hand as insured (when dealer shows Ace).

  blackjack <player> [hand<n>]
      Confirm a natural blackjack and fire drinking rules.

  dealer
      Reveal the hole card, hit until 17+, then auto-evaluate all hands.

  endround
      Finalise the round — fire end-of-round drinking rules and print summary.

  newround [rotate]
      Start a new round. Add 'rotate' to pass the dealer role clockwise.

  status
      Show current state of all hands.
""")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"

    print("\n  Drinking Blackjack Referee — Web Mode")
    print(f"  Local:   http://localhost:5000")
    print(f"  iPhone:  http://{local_ip}:5000  (same WiFi)")
    print("  (Ctrl+C to stop)\n")

    app.run(host="0.0.0.0", port=5000, debug=False)
