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

// Card rank and suit constants — used by table.js (card picker) and
// any other module that needs to enumerate a standard deck.
const RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"];
const SUITS = [
  { label: "♥", code: "h", cls: "hearts" },
  { label: "♦", code: "d", cls: "diamonds" },
  { label: "♣", code: "c", cls: "clubs" },
  { label: "♠", code: "s", cls: "spades" },
];
