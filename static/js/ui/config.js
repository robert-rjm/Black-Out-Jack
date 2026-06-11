window.UI_TEXT = Object.freeze({
  tagline: "Drinking Blackjack with friends",
  setupSub: "Virtual Drinking Blackjack",
});

// Sentinel value used in referee-mode player-selector lists/buttons to
// represent "the dealer's hand" as opposed to a named player. Must match
// the literal the referee dispatch logic checks for in table.js.
const DEALER_SENTINEL = "Dealer";
