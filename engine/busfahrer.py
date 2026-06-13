"""
busfahrer.py – Busfahrer Game Engine
==========================================
Admin-controlled end-of-night drinking game.

Flow:
  1. Admin selects participants (toggle ON/OFF)
  2. Elimination rounds (R1-R4): losers advance, winners exit
  3. Final loser rides the bus: 5 correct higher/lower in a row
  4. Players exit via "Finished my drink" button

Designed as add-on to Black-Out-Jack.
"""

import random
import time
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from blackjack import Card, Deck

# ─────────────────────────────────────────────
# ENUMS & DATA CLASSES
# ─────────────────────────────────────────────

class GamePhase(Enum):
    LOBBY = "lobby"              # Admin toggling players
    ROUND_1 = "round_1"         # Black or Red
    ROUND_2 = "round_2"         # Higher or Lower
    ROUND_3 = "round_3"         # Inside or Outside
    ROUND_4 = "round_4"         # Suit
    BUS_RIDE = "bus_ride"        # 5 in a row
    FINISHED = "finished"        # Game over


class PlayerStatus(Enum):
    ACTIVE = "active"            # Still in elimination
    ELIMINATED = "eliminated"    # Guessed correctly, out of elimination
    BUS_DRIVER = "bus_driver"    # Lost all rounds, riding the bus
    DONE = "done"                # Clicked "finished my drink"


@dataclass
class BusfahrerPlayer:
    """Player state in Busfahrer."""
    id: str
    name: str
    status: PlayerStatus = PlayerStatus.ACTIVE
    current_card: Optional[Card] = None
    last_guess: Optional[str] = None
    guess_correct: Optional[bool] = None
    sips_drunk: int = 0
    sips_allocated: int = 0
    has_guessed_this_round: bool = False
    cards_history: List[Card] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "current_card": str(self.current_card) if self.current_card else None,
            "last_guess": self.last_guess,
            "guess_correct": self.guess_correct,
            "sips_drunk": self.sips_drunk,
            "sips_allocated": self.sips_allocated,
            "has_guessed": self.has_guessed_this_round,
        }


# ─────────────────────────────────────────────
# ROUND DEFINITIONS
# ─────────────────────────────────────────────

ROUNDS = {
    GamePhase.ROUND_1: {
        "name": "Black or Red",
        "prompt": "Is the next card Black or Red?",
        "options": ["black", "red"],
        "sips": 1,
    },
    GamePhase.ROUND_2: {
        "name": "Higher or Lower",
        "prompt": "Is the next card Higher or Lower than your current card?",
        "options": ["higher", "lower"],
        "sips": 2,
    },
    GamePhase.ROUND_3: {
        "name": "Inside or Outside",
        "prompt": "Is the next card Inside or Outside your last two cards?",
        "options": ["inside", "outside"],
        "sips": 3,
    },
    GamePhase.ROUND_4: {
        "name": "Guess the Suit",
        "prompt": "What suit is the next card?",
        "options": ["spades", "clubs", "hearts", "diamonds"],
        "sips": 4,
    },
}


# ─────────────────────────────────────────────
# MAIN GAME CLASS
# ─────────────────────────────────────────────

class BusfahrerGame:
    """
    Busfahrer state machine.

    Admin controls phase transitions.
    Players submit guesses via their client.
    """

    PHASE_ORDER = [
        GamePhase.ROUND_1,
        GamePhase.ROUND_2,
        GamePhase.ROUND_3,
        GamePhase.ROUND_4,
        GamePhase.BUS_RIDE,
    ]

    BUS_RIDE_TARGET = 5  # Correct guesses in a row to escape

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.phase = GamePhase.LOBBY
        self.deck = Deck(1)
        self.players: Dict[str, BusfahrerPlayer] = {}
        self.bus_driver: Optional[BusfahrerPlayer] = None
        self.bus_ride_streak: int = 0
        self.bus_ride_attempts: int = 0
        self.bus_ride_anchor_card: Optional[Card] = None
        self.bus_ride_revealed: List[Card] = []
        self.event_log: List[dict] = []

    # ─── LOBBY ───

    def add_player(self, player_id: str, name: str):
        """Admin toggles a player ON."""
        if self.phase != GamePhase.LOBBY:
            return False
        self.players[player_id] = BusfahrerPlayer(id=player_id, name=name)
        self._log("player_joined", player_id=player_id, name=name)
        return True

    def remove_player(self, player_id: str):
        """Admin toggles a player OFF."""
        if self.phase != GamePhase.LOBBY:
            return False
        self.players.pop(player_id, None)
        self._log("player_removed", player_id=player_id)
        return True

    def get_active_players(self) -> List[BusfahrerPlayer]:
        """Players still in the elimination."""
        return [p for p in self.players.values() if p.status == PlayerStatus.ACTIVE]

    # ─── ADMIN CONTROLS ───

    def start_game(self) -> bool:
        """Admin starts the game. Needs >= 2 active players."""
        if len(self.players) < 2:
            return False
        self.phase = GamePhase.ROUND_1
        self._deal_round()
        self._log("game_started", players=[p.name for p in self.players.values()])
        return True

    def advance_phase(self) -> bool:
        """
        Admin advances to next phase after all active players guessed.
        Evaluates guesses, eliminates winners, losers continue.
        """
        active = self.get_active_players()

        # Check all have guessed
        if not all(p.has_guessed_this_round for p in active):
            return False

        # Evaluate round
        self._evaluate_round()

        # Determine who's left
        remaining = self.get_active_players()

        if len(remaining) <= 1:
            # We have our bus driver
            self._start_bus_ride(remaining[0] if remaining else active[-1])
            return True

        # Move to next elimination round
        current_idx = self.PHASE_ORDER.index(self.phase)
        if current_idx < 3:  # R1-R4
            self.phase = self.PHASE_ORDER[current_idx + 1]
            self._deal_round()
        else:
            # If still multiple after R4, repeat R4 until 1 remains
            self._deal_round()

        return True

    # ─── PLAYER ACTIONS ───

    def submit_guess(self, player_id: str, guess: str) -> Optional[dict]:
        """
        Player submits their guess for the current round.
        Returns result dict or None if invalid.
        """
        player = self.players.get(player_id)
        if not player or player.status != PlayerStatus.ACTIVE:
            return None
        if player.has_guessed_this_round:
            return None
        if self.phase == GamePhase.BUS_RIDE:
            return self._bus_ride_guess(guess)

        # Validate guess against round options
        round_info = ROUNDS.get(self.phase)
        if not round_info or guess not in round_info["options"]:
            return None

        player.last_guess = guess
        player.has_guessed_this_round = True

        self._log("guess_submitted", player_id=player_id,
                  round=self.phase.value, guess=guess)

        return {"status": "submitted", "guess": guess}

    def allocate_sips(self, from_player_id: str, to_player_id: str,
                      sips: int) -> bool:
        """Loser can allocate their sips to another player instead."""
        from_p = self.players.get(from_player_id)
        to_p = self.players.get(to_player_id)

        if not from_p or not to_p:
            return False
        if from_p.id == to_p.id:
            return False

        to_p.sips_drunk += sips
        from_p.sips_allocated += sips

        self._log("sips_allocated", from_player=from_p.name,
                  to_player=to_p.name, sips=sips)
        return True

    def player_finished_drink(self, player_id: str) -> bool:
        """Player clicks 'Finished my drink' to exit."""
        player = self.players.get(player_id)
        if not player:
            return False
        player.status = PlayerStatus.DONE
        self._log("finished_drink", player_id=player_id, name=player.name,
                  total_sips=player.sips_drunk)
        return True

    # ─── BUS RIDE ───

    def _start_bus_ride(self, loser: BusfahrerPlayer):
        """Initialize bus ride for the loser."""
        loser.status = PlayerStatus.BUS_DRIVER
        self.bus_driver = loser
        self.phase = GamePhase.BUS_RIDE

        # Keep loser's last card as anchor, shuffle rest back
        self.bus_ride_anchor_card = loser.current_card
        self.bus_ride_revealed = [self.bus_ride_anchor_card]
        self.bus_ride_streak = 0
        self.bus_ride_attempts = 1
        self.deck = Deck(1)  # Fresh shuffle

        self._log("bus_ride_started", driver=loser.name,
                  anchor_card=str(self.bus_ride_anchor_card))

    def _bus_ride_guess(self, guess: str) -> dict:
        """
        Bus ride: guess higher or lower than current anchor.
        5 correct in a row = escape.
        Wrong = restart from anchor card.
        """
        if guess not in ["higher", "lower"]:
            return {"error": "invalid_guess"}

        card = self.deck.deal()
        anchor = self.bus_ride_revealed[-1]

        # Evaluate
        if guess == "higher":
            correct = card.value >= anchor.value
        else:
            correct = card.value <= anchor.value

        result = {
            "card": str(card),
            "card_data": card.to_dict() if hasattr(card, 'to_dict') else {"rank": card.rank, "suit": card.suit},
            "guess": guess,
            "anchor": str(anchor),
            "correct": correct,
            "streak": 0,
            "attempts": self.bus_ride_attempts,
        }

        if correct:
            self.bus_ride_streak += 1
            self.bus_ride_revealed.append(card)
            result["streak"] = self.bus_ride_streak

            if self.bus_ride_streak >= self.BUS_RIDE_TARGET:
                # ESCAPED!
                self.phase = GamePhase.FINISHED
                result["escaped"] = True
                self._log("bus_ride_escaped",
                          driver=self.bus_driver.name,
                          attempts=self.bus_ride_attempts)
            else:
                result["escaped"] = False
        else:
            # Wrong! Drink and restart
            sips = self.bus_ride_streak + 1  # More pain for longer streaks broken
            self.bus_driver.sips_drunk += sips
            result["sips"] = sips
            result["escaped"] = False

            # Reset: keep original anchor card
            self.bus_ride_streak = 0
            self.bus_ride_revealed = [self.bus_ride_anchor_card]
            self.bus_ride_attempts += 1

            # Reshuffle
            if self.deck.remaining() < 10:
                self.deck = Deck(1)

            self._log("bus_ride_fail", driver=self.bus_driver.name,
                      card=str(card), sips=sips,
                      attempt=self.bus_ride_attempts)

        return result

    # ─── INTERNAL HELPERS ───

    def _deal_round(self):
        """Deal a card to each active player and reset guess state."""
        for player in self.get_active_players():
            card = self.deck.deal()
            player.current_card = card
            player.cards_history.append(card)
            player.has_guessed_this_round = False
            player.last_guess = None
            player.guess_correct = None

    def _evaluate_round(self):
        """
        Evaluate all guesses for current round.
        CORRECT guessers are ELIMINATED (they're safe).
        WRONG guessers stay ACTIVE (losers advance).
        """
        active = self.get_active_players()
        round_info = ROUNDS[self.phase]
        sips = round_info["sips"]

        losers = []
        winners = []

        for player in active:
            card = player.current_card
            guess = player.last_guess
            correct = self._check_guess(player, guess, card)
            player.guess_correct = correct

            if correct:
                winners.append(player)
            else:
                losers.append(player)
                player.sips_drunk += sips  # Drink for losing

        # Winners are eliminated (safe!)
        for winner in winners:
            winner.status = PlayerStatus.ELIMINATED

        # If EVERYONE got it wrong, all stay active
        # If EVERYONE got it right, random one stays (bad luck!)
        if not losers and winners:
            unlucky = random.choice(winners)
            unlucky.status = PlayerStatus.ACTIVE
            losers = [unlucky]
            # Re-eliminate the rest
            for w in winners:
                if w != unlucky:
                    w.status = PlayerStatus.ELIMINATED

        self._log("round_evaluated", round=self.phase.value,
                  losers=[p.name for p in losers],
                  winners=[w.name for w in winners],
                  sips=sips)

    def _check_guess(self, player: BusfahrerPlayer, guess: str,
                     card: Card) -> bool:
        """Evaluate a single guess against the dealt card."""

        if self.phase == GamePhase.ROUND_1:
            # Black or Red
            return (guess == "red" and card.is_red) or \
                   (guess == "black" and card.is_black)

        elif self.phase == GamePhase.ROUND_2:
            # Higher or Lower (compared to R1 card)
            prev = player.cards_history[-2] if len(player.cards_history) >= 2 else None
            if not prev:
                return False
            if guess == "higher":
                return card.value > prev.value
            else:
                return card.value < prev.value

        elif self.phase == GamePhase.ROUND_3:
            # Inside or Outside (between last two cards)
            if len(player.cards_history) < 3:
                return False
            val1 = player.cards_history[-3].value  # R1 card
            val2 = player.cards_history[-2].value  # R2 card
            low, high = min(val1, val2), max(val1, val2)
            if guess == "inside":
                return low < card.value < high
            else:
                return card.value < low or card.value > high

        elif self.phase == GamePhase.ROUND_4:
            # Guess the suit
            suit_map = {"spades": "♠", "clubs": "♣",
                        "hearts": "♥", "diamonds": "♦"}
            return suit_map.get(guess, "") == card.suit

        return False

    def _log(self, event_type: str, **kwargs):
        """Append to event log."""
        self.event_log.append({
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            **kwargs
        })

    # ─── STATE FOR API ───

    def get_state(self) -> dict:
        """Full game state for API responses."""
        return {
            "session_id": self.session_id,
            "phase": self.phase.value,
            "players": {pid: p.to_dict() for pid, p in self.players.items()},
            "active_count": len(self.get_active_players()),
            "round_info": ROUNDS.get(self.phase, {}).get("name", ""),
            "round_prompt": ROUNDS.get(self.phase, {}).get("prompt", ""),
            "round_options": ROUNDS.get(self.phase, {}).get("options", []),
            "bus_driver": self.bus_driver.name if self.bus_driver else None,
            "bus_ride": {
                "anchor": str(self.bus_ride_anchor_card) if self.bus_ride_anchor_card else None,
                "revealed": [str(c) for c in self.bus_ride_revealed],
                "streak": self.bus_ride_streak,
                "target": self.BUS_RIDE_TARGET,
                "attempts": self.bus_ride_attempts,
            } if self.phase == GamePhase.BUS_RIDE else None,
        }

    def get_player_view(self, player_id: str) -> dict:
        """State filtered for a specific player's client."""
        player = self.players.get(player_id)
        if not player:
            return {"error": "not_found"}

        view = {
            "phase": self.phase.value,
            "you": player.to_dict(),
            "your_card": str(player.current_card) if player.current_card else None,
            "your_history": [str(c) for c in player.cards_history],
            "sips_total": player.sips_drunk,
            "can_guess": (player.status == PlayerStatus.ACTIVE and
                          not player.has_guessed_this_round),
        }

        if self.phase in ROUNDS:
            view["prompt"] = ROUNDS[self.phase]["prompt"]
            view["options"] = ROUNDS[self.phase]["options"]

        if self.phase == GamePhase.BUS_RIDE:
            view["is_bus_driver"] = (player.id == self.bus_driver.id) if self.bus_driver else False
            view["bus_ride"] = {
                "revealed": [str(c) for c in self.bus_ride_revealed],
                "streak": self.bus_ride_streak,
                "target": self.BUS_RIDE_TARGET,
                "attempts": self.bus_ride_attempts,
            }

        return view
