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
# Losing-streak "L" badge
# A player who racks up this many consecutive round losses (net hands lost
# > net hands won, tracked the same way session.stats.streaks already does)
# holds the L badge -- only one player at a time, whoever's active losing
# streak is currently the single longest at the table. If another player's
# streak overtakes them, the L transfers and the outgoing holder drinks 1
# sip as a hand-off penalty (earning it for the first time, or simply
# breaking your own streak with nobody else worse yet, never costs a sip).
# ---------------------------------------------------------------------------

WORST_STREAK_THRESHOLD = 5

# ---------------------------------------------------------------------------
# Side-bet / vote timing windows
# ---------------------------------------------------------------------------

BUST_VOTE_WINDOW_SECONDS     = 15.5  # how long the dealer-bust side-bet vote stays open
STAKE_WINDOW_SECONDS         = 15.5  # Normal mode: how long players can change/accept their stake after Deal (shows as 15)
                                   # (frontend countdown UI displays from 15)
BUST_HANDOUT_WINDOW_SECONDS  = 20  # window to claim a dealer-bust sip handout
INSURANCE_VOTE_TIMEOUT       = 60  # insurance vote auto-resolves (as decline) after this long

# ---------------------------------------------------------------------------
# Dealer Lottery — post-round bonus event on a paired 18/20 dealer hand
# (see Rules.md §5.9)
# ---------------------------------------------------------------------------

DEALER_LOTTERY_ENTRY_WINDOW_SECONDS = 20  # window to submit X (0-5); non-responders default to 0
DEALER_LOTTERY_REVEAL_MAX_WAIT_SECONDS = 30  # handout waits for everyone to close the reveal; starts anyway after this
DEALER_LOTTERY_REVEAL_PRESENCE_SECONDS = 10  # a client only holds the handout up if it polled this recently
DEALER_LOTTERY_ALL_IN_STAKE         = 5   # a stake of exactly this many wagers is "all-in"...
DEALER_LOTTERY_ALL_IN_BONUS         = 2   # ...and earns this many extra wagers of handout on a 2+ bust win
DEALER_LOTTERY_TOP_STAKE_BONUS      = 1   # wagers of extra handout for whoever staked the most (ties all get it), in any outcome
DEALER_LOTTERY_MAX_HANDS            = 5  # cap on total hands across both split branches combined
DEALER_LOTTERY_MAX_DRINK            = 10  # ceiling on the no-bust drink, however big the stake/redeal

# ---------------------------------------------------------------------------
# Targeted Drinking Mode — admin-started subgame targeting specific players
# (see Rules.md §5.10; MVP scope only)
# ---------------------------------------------------------------------------

TARGETED_DRINKING_VOTE_WINDOW_SECONDS = 15   # per-round bust/stand vote timer
TARGETED_DRINKING_STREAK_TO_GRADUATE  = 3    # consecutive correct guesses to opt out
TARGETED_DRINKING_COOLDOWN_ROUNDS     = 3    # rounds before a new subgame can start
TARGETED_DRINKING_WRONG_GUESS_SIPS    = 2    # flat sips for every wrong call
DRINK_RATE_PROTECTION_ROUNDS     = 3    # rounds a player who reset to 1.0 is shielded from rate votes (unless they vote Yes)
LATE_JOIN_MIN_AVG_SIPS          = 3    # no late-join boost is offered unless the other humans average at least this many sips
DRINK_RATE_REQUEST_FREEZE_ROUNDS = 3    # rounds a seat cannot ask for another discount after its own request was voted down
DRINK_RATE_VOTE_WINDOW_SECONDS   = 20   # admin-proposed drink-rate vote auto-fails after this long
AFK_DISCONNECT_SECONDS        = 60   # no /state poll for this long -> client counts as gone (closed tab, dead connection)
ADMIN_AFK_PROMPT_DELAY_SECONDS = 180  # the admin must have been holding the game up this long before the AFK vote can be started
ADMIN_AFK_VOTE_WINDOW_SECONDS = 30   # unanimous "admin is AFK" vote auto-fails after this long
TARGETED_DRINKING_MAX_AFK_STRIKES     = 2    # consecutive unanswered vote windows before a target's seat is absorbed by the host
TARGETED_DRINKING_REVEAL_PAUSE_SECONDS = 12  # safety-net breather after a mini-round's reveal before the
                                              # next one auto-opens -- the host/dealer can skip this early via
                                              # POST /targeted_drinking/continue (app/routes/targeted_drinking.py)
# Easter-egg-launched subgames only (Wild Card 🃏): total sips a target can
# drink before their run is force-ended as a loss (+1 penalty sip on top).
TARGETED_DRINKING_EASTER_EGG_SIP_CAP  = 5
# A target who graduates without ever missing (the minimum possible
# TARGETED_DRINKING_STREAK_TO_GRADUATE attempts, all correct) gets to hand
# out this many sips to another player -- mirrors the Dealer Lottery /
# Bust Vote give-sip pattern, including its claim window.
TARGETED_DRINKING_PERFECT_GRADUATION_HANDOUT_SIPS = 3
TARGETED_DRINKING_HANDOUT_WINDOW_SECONDS          = 20

# Majority-vote-to-target proposal (tapping a player's name at the table):
# a single Yes/No vote on one proposed target, open for this long -- passes
# early the instant strict majority says Yes, otherwise fails when the timer
# runs out. A failed vote freezes the proposer from opening another proposal
# for this many rounds (doesn't stop them voting on someone else's).
TARGETED_DRINKING_PROPOSAL_VOTE_WINDOW_SECONDS = 15

# "Switch to BOJ" table poll (services/boj_switch.py)
BOJ_POLL_WINDOW_SECONDS    = 30   # how long the Normal-table vote stays open
BOJ_SPLIT_GRACE_SECONDS    = 8    # cancel-modal countdown before movers are redirected
BOJ_SPLIT_PLAN_TTL_SECONDS = 120  # an unused split plan (nobody redirected) lapses after this
TARGETED_DRINKING_PROPOSE_FREEZE_ROUNDS        = 3

# ---------------------------------------------------------------------------
# Registration / connection limits
# ---------------------------------------------------------------------------

MAX_REG_DENIALS = 2   # times a client can be denied (re-)entry before being locked out

# ---------------------------------------------------------------------------
# Game defaults (used by /setup when the caller omits a field)
# ---------------------------------------------------------------------------

DEFAULT_WAGER     = 1
DEFAULT_NUM_HANDS = 2
DEFAULT_MODE      = "referee"   # "referee" | "digital"
