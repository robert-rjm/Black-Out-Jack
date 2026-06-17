window.UI_TEXT = Object.freeze({
  tagline: "Drinking Blackjack with friends",
  setupSub: "Virtual Drinking Blackjack",
});

// Game phase identifiers — match server round_phase() return values.
// Use these constants instead of raw strings to catch typos at review time.
const PHASE = Object.freeze({
  PRE_DEAL:     "pre-deal",
  PLAYING:      "playing",
  ROUND_OVER:   "round-over",
  DEALER_READY: "dealer-ready",
});

// Client role identifiers — match server my_role values.
const ROLE = Object.freeze({
  ADMIN:     "admin",
  PLAYER:    "player",
  SPECTATOR: "spectator",
  KICKED:    "kicked",
  DEALER:    "dealer",
});

// Sentinel value used in referee-mode player-selector lists/buttons to
// represent "the dealer's hand" as opposed to a named player. Must match
// the literal the referee dispatch logic checks for in table.js.
const DEALER_SENTINEL = "Dealer";
