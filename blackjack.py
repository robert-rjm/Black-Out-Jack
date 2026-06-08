"""
blackjack.py  (entry-point shim)
=================================
Game logic lives in engine/blackjack.py.
Run:
    python blackjack.py
"""
from engine.blackjack import *   # re-export for any direct imports of this shim

if __name__ == "__main__":
    game = BlackJackGame()
    game.play()
