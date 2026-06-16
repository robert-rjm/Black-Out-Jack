"""
app/services/utils.py
======================
Cross-cutting utility functions for the app layer.

Functions here are pure (no side effects, no imports from app state)
and may be used by multiple app services.
"""


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
    if "handed" in r and "bust vote" in r:          return "Bust vote handout received"
    if "Bust vote forfeited" in r:                  return "Bust vote handout forfeited"
    if "won with" in r and "cards" in r:            return "5+ card win"
    if "A\u2660" in r and "to dealer" in r:        return "Ace dealt: Ace of Spades (dealer hand)"
    if "A\u2665" in r and "dealer" in r:           return "Ace dealt: Ace of Hearts (dealer hand)"
    if "A\u2666" in r and "dealer" in r:           return "Ace dealt: Ace of Diamonds (dealer hand)"
    if "A\u2660" in r:                             return "Ace dealt: Ace of Spades (player hand)"
    if "A\u2665" in r:                             return "Ace dealt: Ace of Hearts (player hand)"
    if "A\u2666" in r:                             return "Ace dealt: Ace of Diamonds (player hand)"
    return "Other"

