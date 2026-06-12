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
  { cat: "strategy",    text: "Standing on a soft 17 (Ace + 6) is a mistake, since you cannot bust, so hitting is always better." },
  { cat: "strategy",    text: "Soft 18 (A+7) vs. dealer 9, 10, or A: you should hit. Most players stand and lose more often." },
  { cat: "strategy",    text: "Hard 16 vs. dealer 10 with 3+ cards: stand. With only 2 cards: hit. Card composition changes the math." },
  { cat: "strategy",    text: "Hitting 12 vs. dealer 2 or 3 is correct, but standing vs. dealer 4 is also correct. The switch happens at exactly 4." },
  { cat: "strategy",    text: "Doubling A+5 vs. dealer 6 is correct but feels insane - you are banking on the dealer busting." },
  { cat: "strategy",    text: "Taking even money on blackjack vs. dealer Ace is mathematically identical to insurance. Same bad bet, better marketing." },
  { cat: "strategy",    text: "Removing all 5s from a deck helps the player more than removing any other single rank (~0.67% swing)." },
  { cat: "probability", text: "The probability of being dealt a natural blackjack is about 4.8%, roughly 1 in 21." },
  { cat: "probability", text: "Dealer bust rates by upcard: 2->35%, 3->37%, 4->40%, 5->42%, 6->42%, 7->26%, 8->24%, 9->23%, 10->23%, A->11%." },
  { cat: "probability", text: "The probability of losing 8 hands in a row is ~0.34%. In a 300-hand session, there is roughly a 12% chance it happens at least once." },
  { cat: "probability", text: "Even with perfect play, you will have a losing session ~52% of the time over 100 hands. Short-term variance dominates." },
  { cat: "probability", text: "The dealer busts roughly 28% of the time, mostly when showing a 4, 5, or 6." },
  { cat: "probability", text: "A dealer showing a 6 is the weakest position, they bust nearly 42% of the time." },
  { cat: "probability", text: "You will get a splittable pair about 14.5% of the time. A correct double-down comes up about 9.5% of the time." },
  { cat: "probability", text: "A 20 wins about 85% of the time. A 19 wins about 70%. The drop-off per point is steep." },
  { cat: "probability", text: "Insurance is almost never worth it, the house edge on the insurance bet alone is over 7%." },
  { cat: "history",     text: "Blackjack originated in French casinos around 1700 under the name Vingt-et-Un (21)." },
  { cat: "history",     text: "Edward Thorp's 1962 book Beat the Dealer introduced card counting to the public and changed blackjack forever." },
  { cat: "history",     text: "The name Blackjack comes from an early bonus payout for a hand with the Ace of Spades and a black Jack." },
  { cat: "history",     text: "Blackjack goes by many names: 21, Vingt-et-Un, Pontoon, 17+4, and Black(Out)Jack if you are here." },
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
  { cat: "game",        text: "Never split 10s in a casino. In Black(Out)Jack, the house rules make it worth the chaos." },
  { cat: "game",        text: "The dealer busts ~28% of rounds - every bust hands sips back to the players." },
  { cat: "game",        text: "The 4 Aces rule: 2 sips after first deal, 1 sip at round end. They cannot stack." },
];

var TRIVIA_CATS = [
  { key: "all",         icon: "🃏", label: "All"   },
  { key: "strategy",    icon: "🧠", label: "Strat" },
  { key: "probability", icon: "🎲", label: "Odds"  },
  { key: "history",     icon: "📜", label: "Hist"  },
  { key: "drinking",    icon: "🍺", label: "Drink" },
  { key: "game",        icon: "🎰", label: "Game"  },
];

var CAT_LABELS = { strategy:"Strategy", probability:"Odds", history:"History", drinking:"Drinking", game:"This game" };
var CAT_COLORS = { strategy:"var(--accent)", probability:"var(--yellow)", history:"#a78bfa", drinking:"var(--red)", game:"var(--green)" };

// Trivia panel state, consolidated under one namespaced object (was 5
// separate module-level globals). Same values, same mutation patterns —
// all belong to the trivia panel feature area.
const TriviaUI = {
  filter:    "all", // selected category filter ("all" or a TRIVIA_CATS key)
  index:     0,     // index of the currently shown fact within `list`
  list:      [],    // current filtered/ordered list of trivia facts
  rendered:  false, // whether the trivia DOM has been built yet
  lastRound: -1,    // last round number we rotated the fact for
  drinking:  true,  // whether drinking-mode trivia (facts + category) should show
};

function _availableFacts() {
  return TriviaUI.drinking ? TRIVIA_FACTS : TRIVIA_FACTS.filter(function(f) { return f.cat !== "drinking"; });
}

function _availableCats() {
  return TriviaUI.drinking ? TRIVIA_CATS : TRIVIA_CATS.filter(function(c) { return c.key !== "drinking"; });
}

function _buildTriviaList(round) {
  var facts = _availableFacts();
  var base = TriviaUI.filter === "all"
    ? facts
    : facts.filter(function(f) { return f.cat === TriviaUI.filter; });
  if (!base.length) base = facts;
  TriviaUI.list = base.slice();
  TriviaUI.index = (typeof round === "number" && round > 0)
    ? round % TriviaUI.list.length : 0;
}

function _isTriviaActive() {
  var p = document.getElementById("pane-kpi-trivia");
  return p && p.classList.contains("active");
}

// ---- Full initial render ----
function _buildTriviaHTML() {
  var catBtns = _availableCats().map(function(c) {
    return '<button class="trivia-cat-btn" data-cat="' + c.key + '" onclick="setTriviaFilter(\'' + c.key + '\')">' +
      '<span class="t-icon">' + c.icon + '</span>' +
      '<span class="t-label">' + c.label + '</span>' +
      '</button>';
  }).join("");

  return '<div class="trivia-card">' +
    '<div class="trivia-header">' +
      '<span class="trivia-title">🃏 Did You Know?</span>' +
      '<span class="trivia-cat-label" id="trivia-cat-label"></span>' +
    '</div>' +
    '<div class="trivia-text" id="trivia-text"></div>' +
    '<div class="trivia-nav-row" id="trivia-nav-row"></div>' +
    '</div>' +
    '<div class="trivia-categories" id="trivia-categories">' + catBtns + '</div>';
}

// ---- Partial updates (fast path) ----
function _updateTriviaContent() {
  if (!TriviaUI.list.length) return;
  var fact     = TriviaUI.list[TriviaUI.index];
  var total    = TriviaUI.list.length;
  var catColor = CAT_COLORS[fact.cat] || "var(--muted)";
  var catLabel = CAT_LABELS[fact.cat] || fact.cat;
  var catIcon  = (TRIVIA_CATS.filter(function(c){ return c.key === fact.cat; })[0] || {}).icon || "";

  // Badge — simple border + text color, neutral bg for all categories
  var badge = document.getElementById("trivia-cat-label");
  if (badge) {
    badge.textContent = catIcon + " " + catLabel;
    badge.style.color = catColor;
    badge.style.borderColor = catColor;
    badge.style.background = "rgba(255,255,255,0.08)";
  }

  // Text — use textContent (safe, no escapeHtml needed)
  var textEl = document.getElementById("trivia-text");
  if (textEl) textEl.textContent = fact.text;

  // Nav: dots (category mode) or ← counter → (all mode)
  var navRow = document.getElementById("trivia-nav-row");
  if (navRow) {
    if (TriviaUI.filter !== "all" && total <= 12) {
      var dots = '<div class="trivia-dots">';
      for (var i = 0; i < total; i++) {
        // Use CSS class for active dot — avoids inline CSS variable in style string
        var cls = "trivia-dot" + (i === TriviaUI.index ? " active" : "");
        dots += '<button class="' + cls + '" onclick="jumpTrivia(' + i + ')"></button>';
      }
      dots += '</div>';
      navRow.innerHTML = dots;
    } else {
      navRow.innerHTML =
        '<button class="trivia-arr" onclick="prevTrivia()" ' + (TriviaUI.index === 0 ? "disabled" : "") + '>&#8592;</button>' +
        '<span class="trivia-counter">' + (TriviaUI.index + 1) + ' / ' + total + '</span>' +
        '<button class="trivia-arr" onclick="nextTrivia()">&#8594;</button>';
    }
  }

  // Category buttons active state
  var btns = document.querySelectorAll(".trivia-cat-btn");
  for (var j = 0; j < btns.length; j++) {
    btns[j].classList.toggle("active", btns[j].dataset.cat === TriviaUI.filter);
  }
}

function renderTrivia() {
  var el = document.getElementById("trivia-content");
  if (!el) return;
  if (!TriviaUI.list.length) _buildTriviaList(null);

  // Rebuild if not yet rendered or if DOM was cleared externally
  if (!TriviaUI.rendered || !document.getElementById("trivia-text")) {
    el.innerHTML = _buildTriviaHTML();
    TriviaUI.rendered = true;
  }
  _updateTriviaContent();
}

function nextTrivia() {
  TriviaUI.index = (TriviaUI.index + 1) % TriviaUI.list.length;
  _updateTriviaContent();
}

function prevTrivia() {
  if (TriviaUI.index > 0) { TriviaUI.index--; _updateTriviaContent(); }
}

function jumpTrivia(i) {
  TriviaUI.index = i;
  _updateTriviaContent();
}

function setTriviaFilter(cat) {
  TriviaUI.filter = cat;
  _buildTriviaList(TriviaUI.lastRound > 0 ? TriviaUI.lastRound : null);
  _updateTriviaContent();
}

function _resetTriviaRender() {
  // Call if trivia-content is cleared externally so HTML gets rebuilt
  TriviaUI.rendered = false;
}

function updateTriviaPanel(state) {
  var drinking = !state || state.drinking_mode !== false;
  if (drinking !== TriviaUI.drinking) {
    TriviaUI.drinking = drinking;
    if (TriviaUI.filter === "drinking" && !drinking) TriviaUI.filter = "all";
    TriviaUI.rendered = false; // rebuild category buttons
    _buildTriviaList(TriviaUI.lastRound > 0 ? TriviaUI.lastRound : null);
  }
  var round = state && state.round ? state.round : null;
  if (round !== null && round !== TriviaUI.lastRound && TriviaUI.lastRound >= 0 && _isTriviaActive()) {
    TriviaUI.lastRound = round;
    _buildTriviaList(round);
  } else {
    if (round !== null) TriviaUI.lastRound = round;
    if (!TriviaUI.list.length) _buildTriviaList(round);
  }
  renderTrivia();
}
