// ============================================================
// TRIVIA PANEL
// ============================================================
// Phase 1: categorised facts, carousel UI, round-synced auto-advance.
// Phase 2 (planned): reactive facts triggered by game events.
// ============================================================

const TRIVIA_FACTS = [
  { cat: "strategy",    text: "The house edge in standard blackjack is around 0.5% with perfect basic strategy, one of the lowest of any casino game." },
  { cat: "strategy",    text: "Basic strategy reduces the house edge from ~2% to ~0.5%. Knowing it matters." },
  { cat: "strategy",    text: "Doubling down on 11 against any dealer card except an Ace is almost always correct basic strategy." },
  { cat: "strategy",    text: "Doubling on 10 against a dealer 9 or lower is correct basic strategy." },
  { cat: "strategy",    text: "Standing on a soft 17 (Ace + 6) is a mistake - you cannot bust, so hitting is always better." },
  { cat: "strategy",    text: "Soft 18 (A+7) vs. dealer 9, 10, or A: you should hit. Most players stand and lose more often." },
  { cat: "strategy",    text: "Hard 16 vs. dealer 10 with 3+ cards: stand. With only 2 cards: hit. Card composition changes the math." },
  { cat: "strategy",    text: "Hitting 12 vs. dealer 2 or 3 is correct, but standing on 12 vs. dealer 4 is also correct. The switch happens at exactly 4." },
  { cat: "strategy",    text: "Doubling A+5 vs. dealer 6 is correct but feels insane - you are banking on the dealer busting." },
  { cat: "strategy",    text: "Taking even money on blackjack vs. dealer Ace is mathematically identical to insurance. Same bad bet, better marketing." },
  { cat: "strategy",    text: "Removing all 5s from a deck helps the player more than removing any other single rank (~0.67% swing)." },
  { cat: "probability", text: "The probability of being dealt a natural blackjack is about 4.8%, roughly 1 in 21." },
  { cat: "probability", text: "Dealer bust rates by upcard: 2->35%, 3->37%, 4->40%, 5->42%, 6->42%, 7->26%, 8->24%, 9->23%, 10->23%, A->17%." },
  { cat: "probability", text: "The probability of losing 8 hands in a row is ~2.3%. In a 200-hand session, it will almost certainly happen once." },
  { cat: "probability", text: "Even with perfect play, you will have a losing session ~55% of the time over 100 hands. Short-term variance dominates." },
  { cat: "probability", text: "The dealer busts roughly 28% of the time, mostly when showing a 4, 5, or 6." },
  { cat: "probability", text: "A dealer showing a 6 is the weakest position - they bust nearly 42% of the time." },
  { cat: "probability", text: "You will get a splittable pair about 14.5% of the time. A correct double-down comes up about 9.5% of the time." },
  { cat: "probability", text: "A 20 wins about 85% of the time. A 19 wins about 70%. The drop-off per point is steep." },
  { cat: "probability", text: "Insurance is almost never worth it - the house edge on the insurance bet alone is over 7%." },
  { cat: "history",     text: "Blackjack originated in French casinos around 1700 under the name Vingt-et-Un (21)." },
  { cat: "history",     text: "Edward Thorp's 1962 book Beat the Dealer introduced card counting to the public and changed blackjack forever." },
  { cat: "history",     text: "The name Blackjack comes from an early bonus payout for a hand with the Ace of Spades and a black Jack." },
  { cat: "history",     text: "Blackjack goes by many names: 21, Vingt-et-Un, Pontoon, 17+4 - and Black(Out)Jack if you're here." },
  { cat: "history",     text: "The MIT Blackjack Team won millions card counting in the 1980s and 90s - they inspired the film 21." },
  { cat: "history",     text: "Las Vegas casinos introduced the 6:5 blackjack payout in the 2000s - it nearly doubles the house edge." },
  { cat: "history",     text: "The first basic strategy was computed in 1956 by four US Army engineers on desk calculators. It took 3 years." },
  { cat: "history",     text: "Don Johnson won $15 million from Atlantic City in 2011 by negotiating loss-rebate deals that flipped the edge in his favor." },
  { cat: "history",     text: "Casinos introduced multi-deck shoes to combat card counting. Before that, single-deck handheld was standard." },
  { cat: "history",     text: "Automated shufflers were introduced to combat counting, but also increase hands-per-hour by ~20%." },
  { cat: "drinking",    text: "Drinking games date back to ancient Greece - Kottabos involved flinging wine dregs at a target." },
  { cat: "drinking",    text: "Beer pong was likely invented at Dartmouth College in the 1950s, originally played with paddles." },
  { cat: "drinking",    text: "The world record for the most players in a single card game is 1,083 people." },
  { cat: "drinking",    text: "A standard deck of 52 cards has been around since at least the 14th century." },
  { cat: "drinking",    text: "If busting costs sips in your rules, optimal strategy shifts - standing earlier becomes mathematically correct." },
  { cat: "drinking",    text: "Your bust rate likely climbs as the session goes on. After 45 minutes of drinking, decision quality drops ~20%." },
  { cat: "drinking",    text: "A conservative player (stands on all 12+) loses ~0.5% more edge. An aggressive drunk player loses ~2% more." },
  { cat: "game",        text: "A suited A+J of Spades in Black(Out)Jack triggers all three multipliers: suited x A+J x both black = 8x bonus." },
  { cat: "game",        text: "With 4 players and 2 hands each: 8 player hands + 1 dealer hand = 9 hands per round." },
  { cat: "game",        text: "Splitting Aces up to 5 times means a single starting Ace can spawn up to 5 hands." },
  { cat: "game",        text: "Never split 10s in a casino. In Black(Out)Jack the drinking penalty makes it worth the chaos." },
  { cat: "game",        text: "The dealer busts ~28% of rounds - every bust hands sips back to the players." },
  { cat: "game",        text: "The 4 Aces rule: 2 sips after first deal, 1 sip at round end. They cannot stack." },
];

const TRIVIA_CATS = [
  { key: "all",         icon: "🃏" },
  { key: "strategy",    icon: "🧠" },
  { key: "probability", icon: "🎲" },
  { key: "history",     icon: "📜" },
  { key: "drinking",    icon: "🍺" },
  { key: "game",        icon: "🎰" },
];

const CAT_LABELS = {
  strategy: "Strategy", probability: "Odds",
  history: "History",   drinking: "Drinking", game: "This game",
};

const CAT_COLORS = {
  strategy: "var(--accent)", probability: "var(--yellow)",
  history: "#a78bfa",        drinking: "var(--red)", game: "var(--green)",
};

var _triviaFilter   = "all";
var _triviaIndex    = 0;
var _triviaList     = [];
var _triviaLastRound = -1;  // tracks last seen round for auto-advance

// Build filtered list; in "all" mode, use round-based offset so all clients sync.
function _buildTriviaList(round) {
  var base = _triviaFilter === "all"
    ? TRIVIA_FACTS
    : TRIVIA_FACTS.filter(function(f) { return f.cat === _triviaFilter; });
  _triviaList = base.slice();
  // Offset start by round so all players see the same fact at the same round
  _triviaIndex = typeof round === "number" && round > 0
    ? round % _triviaList.length
    : 0;
}

function _isTriviaActive() {
  var pane = document.getElementById("pane-kpi-trivia");
  return pane && pane.classList.contains("active");
}

function renderTrivia() {
  var el = document.getElementById("trivia-content");
  if (!el) return;
  if (!_triviaList.length) _buildTriviaList(null);

  var fact     = _triviaList[_triviaIndex];
  var total    = _triviaList.length;
  var catColor = CAT_COLORS[fact.cat] || "var(--muted)";
  var catLabel = CAT_LABELS[fact.cat] || fact.cat;
  var catIcon  = (TRIVIA_CATS.filter(function(c){ return c.key === fact.cat; })[0] || {}).icon || "";

  // Category icon pills
  var pills = TRIVIA_CATS.map(function(c) {
    var active = c.key === _triviaFilter ? " tv-pill-active" : "";
    return '<button class="tv-pill' + active + '" title="' + (CAT_LABELS[c.key] || "All") + '" onclick="setTriviaFilter(\'' + c.key + '\')">' + c.icon + '</button>';
  }).join("");

  // Dot nav for filtered categories; counter for "all"
  var navHtml;
  if (_triviaFilter !== "all" && total <= 12) {
    var dots = "";
    for (var i = 0; i < total; i++) {
      dots += '<button class="tv-dot' + (i === _triviaIndex ? " active" : "") + '" onclick="jumpTrivia(' + i + ')"></button>';
    }
    navHtml = '<div class="tv-dots">' + dots + '</div>';
  } else {
    navHtml =
      '<button class="tv-arr" onclick="prevTrivia()" ' + (_triviaIndex === 0 ? "disabled" : "") + '>&#8592;</button>' +
      '<span class="tv-counter">' + (_triviaIndex + 1) + ' / ' + total + '</span>' +
      '<button class="tv-arr" onclick="nextTrivia()">&#8594;</button>';
  }

  el.innerHTML =
    '<div class="tv-wrap">' +
      '<div class="tv-card" style="border-left-color:' + catColor + '" data-icon="' + catIcon + '">' +
        '<div class="tv-header">' +
          '<span class="tv-title">Did You Know?</span>' +
          '<span class="tv-badge" style="color:' + catColor + ';border-color:' + catColor + '">' + catIcon + ' ' + catLabel + '</span>' +
        '</div>' +
        '<div class="tv-text">' + escapeHtml(fact.text) + '</div>' +
      '</div>' +
      '<div class="tv-footer">' +
        '<div class="tv-nav">' + navHtml + '</div>' +
        '<div class="tv-pills">' + pills + '</div>' +
      '</div>' +
    '</div>';
}

function nextTrivia() {
  _triviaIndex = (_triviaIndex + 1) % _triviaList.length;
  renderTrivia();
}

function prevTrivia() {
  if (_triviaIndex > 0) { _triviaIndex--; renderTrivia(); }
}

function jumpTrivia(i) {
  _triviaIndex = i;
  renderTrivia();
}

function setTriviaFilter(cat) {
  _triviaFilter = cat;
  _buildTriviaList(_triviaLastRound > 0 ? _triviaLastRound : null);
  renderTrivia();
}

function updateTriviaPanel(state) {
  var round = state && state.round ? state.round : null;

  // Auto-advance when a new round starts and trivia tab is visible
  if (round !== null && round !== _triviaLastRound && _triviaLastRound >= 0 && _isTriviaActive()) {
    _triviaLastRound = round;
    _buildTriviaList(round);
    renderTrivia();
    return;
  }
  if (round !== null) _triviaLastRound = round;

  if (!_triviaList.length) _buildTriviaList(round);
  renderTrivia();
}
