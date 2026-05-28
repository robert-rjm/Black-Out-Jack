"""
app/config.py
=============
All application-wide constants, defaults, and feature flags.
Nothing here should import from other app modules.
"""

# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------

ROOM_WORDS = [
    "Ace", "Bets", "Bluff", "Bust", "Cards", "Club", "Deal", "Diamond",
    "Double", "Flush", "Heart", "Hit", "Jack", "Joker", "King", "Luck",
    "Queen", "Spade", "Split", "Stand", "Suit", "Table",
]

# ---------------------------------------------------------------------------
# Join rate-limiter — applied to /join_room only, keyed by source IP
# ---------------------------------------------------------------------------

JOIN_RATE_LIMIT  = 5    # max failed attempts before lockout
JOIN_RATE_WINDOW = 30   # sliding window in seconds

# ---------------------------------------------------------------------------
# Room / session lifecycle
# ---------------------------------------------------------------------------

SESSION_TTL = 12 * 3600   # seconds — uninitialised rooms older than this are cleaned up

# ---------------------------------------------------------------------------
# Milestone feature
# First player to cross each MILESTONE_STEP sip boundary wins MILESTONE_HANDOUT_SIPS
# sips to distribute however they like (cannot keep them / give to self).
# The claim window closes after MILESTONE_TTL seconds.
# ---------------------------------------------------------------------------

MILESTONE_STEP         = 50   # sip-count multiples that trigger a milestone
MILESTONE_HANDOUT_SIPS = 5    # sips the winner gets to hand out
MILESTONE_TTL          = 60   # seconds before an unclaimed handout is forfeited

# ---------------------------------------------------------------------------
# Game defaults (used by /setup when the caller omits a field)
# ---------------------------------------------------------------------------

DEFAULT_WAGER     = 1
DEFAULT_NUM_HANDS = 2
DEFAULT_NUM_DECKS = 1
DEFAULT_MODE      = "referee"   # "referee" | "digital"
