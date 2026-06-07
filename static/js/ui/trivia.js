// ============================================================
// TRIVIA PANEL — rotating blackjack & drinking facts
// ============================================================
//
// Phase 1 (current): static rotating facts, cycling on each render call.
// Phase 2 (planned): reactive facts triggered by game events
//                    (e.g. ace dealt, dealer shows 6, player busts, etc.)
// ============================================================

const TRIVIA_FACTS = [
  // ── Blackjack strategy ──────────────────────────────────────
  "The house edge in standard blackjack is around 0.5% with perfect basic strategy — one of the lowest of any casino game.",
  "Always split Aces and 8s — splitting 8s turns a losing 16 into two potentially winning hands.",
  "Never split 10s. A 20 wins ~85% of the time. Don't ruin it.",
  "Doubling down on 11 against any dealer card except an Ace is almost always correct basic strategy.",
  "Standing on a soft 17 (Ace + 6) is a mistake — you can't bust, so hitting is always better.",
  "Basic strategy reduces the house edge from ~2% to ~0.5%. Knowing it matters.",
  "The dealer busts roughly 28% of the time — mostly when showing a 4, 5, or 6.",
  "A dealer showing a 6 is the weakest position — they bust nearly 42% of the time.",
  "Doubling on 10 against a dealer 9 or lower is correct basic strategy.",
  "Insurance is almost never worth it — the house edge on the insurance bet alone is over 7%.",

  // ── Blackjack history ───────────────────────────────────────
  "Blackjack originated in French casinos around 1700 under the name 'Vingt-et-Un' (21).",
  "Edward Thorp's 1962 book 'Beat the Dealer' introduced card counting to the public and changed blackjack forever.",
  "The name 'Blackjack' comes from an early bonus payout for a hand containing the Ace of Spades and a black Jack.",
  "Las Vegas casinos introduced the 6:5 blackjack payout in the 2000s — it nearly doubles the house edge.",
  "The MIT Blackjack Team won millions card counting in the 1980s and 90s — they inspired the film '21'.",

  // ── Drinking game trivia ─────────────────────────────────────
  "Drinking games date back to ancient Greece — 'Kottabos' involved flinging wine dregs at a target.",
  "Beer pong was likely invented at Dartmouth College in the 1950s, originally played with paddles.",
  "The world record for the most players in a single card game is 1,083 people.",
  "A standard deck of 52 cards has been around since at least the 14th century.",
  "There are 2,598,960 possible 5-card poker hands from a standard deck.",

  // ── Fun facts ───────────────────────────────────────────────
  "The probability of being dealt a natural blackjack is about 4.8% — roughly 1 in 21.",
  "There are exactly 4 ways to make a blackjack with an Ace of Spades and a black Jack in a single deck.",
  "A suited Ace + Jack of Spades in Black(Out)Jack triggers all three multipliers: suited × A+J × both black = 8× bonus.",
  "With 4 players and 2 hands each, there are 8 player hands + 1 dealer hand = 9 hands per round.",
  "Splitting Aces up to 5 times means a single starting Ace can spawn up to 5 hands.",
];

let _triviaIndex = 0;

// ---- Renderer ----
function renderTrivia() {
  const el = document.getElementById("trivia-content");
  if (!el) return;

  const fact = TRIVIA_FACTS[_triviaIndex % TRIVIA_FACTS.length];

  el.innerHTML = `
    <div class="trivia-card">
      <div class="trivia-icon">🃏</div>
      <div class="trivia-text">${escapeHtml(fact)}</div>
      <button class="trivia-next-btn" onclick="nextTrivia()">Next fact →</button>
      <div class="trivia-counter">${(_triviaIndex % TRIVIA_FACTS.length) + 1} / ${TRIVIA_FACTS.length}</div>
    </div>`;
}

function nextTrivia() {
  _triviaIndex = (_triviaIndex + 1) % TRIVIA_FACTS.length;
  renderTrivia();
}

// ---- Hook into KPI tab switch ----
function updateTriviaPanel() {
  renderTrivia();
}
