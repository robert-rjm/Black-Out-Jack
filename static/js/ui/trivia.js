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
  "The house edge in standard blackjack is around 0.5% with perfect basic strategy, one of the lowest of any casino game.",
  "Basic strategy reduces the house edge from ~2% to ~0.5%. Knowing it matters.",
  "Doubling down on 11 against any dealer card except an Ace is almost always correct basic strategy.",
  "Doubling on 10 against a dealer 9 or lower is correct basic strategy.",
  "The dealer busts roughly 28% of the time, mostly when showing a 4, 5, or 6.",
  "A dealer showing a 6 is the weakest position, they bust nearly 42% of the time.",
  "Standing on a soft 17 (Ace + 6) is a mistake, you can't bust, so hitting is always better.",
  "Soft 18 (A+7) vs. dealer 9, 10, or A: you should hit. Most players stand and lose more often.",
  "Hard 16 vs. dealer 10 with 3+ cards: stand. With only 2 cards: hit. The card composition changes the math.",
  "Hitting 12 vs. dealer 2 or 3 is correct, but standing on 12 vs. dealer 4 is also correct. The switch happens at exactly 4.",
  "Surrendering 15 vs. dealer 10 (where allowed) saves ~0.03% overall edge, one of the few hands where giving up is correct.",
  "Doubling A+5 vs. dealer 6 is correct but feels insane. You're banking on the dealer busting more than your hand improving.",
  "Removing all 5s from a deck helps the player more than removing any other single rank (~0.67% swing).",
  "Taking even money on blackjack vs. dealer Ace is mathematically identical to insurance. Same bad bet, better marketing.",

  // ── Probability & statistics ────────────────────────────────
  "The probability of being dealt a natural blackjack is about 4.8%, roughly 1 in 21.",
  "Dealer bust rates by up card: 2→35%, 3→37%, 4→40%, 5→42%, 6→42%, 7→26%, 8→24%, 9→23%, 10→23%, A→17%.",
  "The probability of losing 8 hands in a row is ~2.3%. In a 200-hand session, it'll almost certainly happen once.",
  "Even with perfect play, you'll have a losing session ~55% of the time over 100 hands. Short-term variance dominates.",
  "The variance in blackjack is ~1.15 per unit bet. Swings of ±30 units in 200 hands are completely normal.",
  "You'll get a splittable pair about 14.5% of the time. A correct double-down opportunity comes up about 9.5% of the time.",
  "The expected number of cards per hand is ~2.7. A round with 5 players burns through roughly 15 cards.",
  "A 20 wins about 85% of the time. A 19 wins about 70%. The drop-off per point is steep.",
  "Insurance is almost never worth it, the house edge on the insurance bet alone is over 7%.",

  // ── Blackjack history ───────────────────────────────────────
  "Blackjack originated in French casinos around 1700 under the name 'Vingt-et-Un' (21).",
  "Edward Thorp's 1962 book 'Beat the Dealer' introduced card counting to the public and changed blackjack forever.",
  "The name 'Blackjack' comes from an early bonus payout for a hand containing the Ace of Spades and a black Jack.",
  "Blackjack goes by many names around the world: 21, Vingt-et-Un, Pontoon, 17+4 (Siebzehn und Vier), and Black(Out)Jack if you're here.",
  "The MIT Blackjack Team won millions card counting in the 1980s and 90s, they inspired the film '21'.",
  "Las Vegas casinos introduced the 6:5 blackjack payout in the 2000s, it nearly doubles the house edge.",
  "The first basic strategy was computed in 1956 by four US Army engineers on desk calculators. It took them 3 years.",
  "Don Johnson won $15 million from Atlantic City in 2011, not by counting, but by negotiating loss-rebate deals that flipped the edge in his favor.",
  "The Griffin Book was a secret casino database of advantage players’ photos, active from the 1970s until going bankrupt in 2005.",
  "Wonging’ (back-counting, then jumping in when the count is positive) got so common that casinos created ‘no mid-shoe entry’ rules.",
  "Casinos introduced multi-deck shoes to combat Thorp’s counting system. Before that, single-deck handheld was standard.",
  "Automated shufflers were introduced to combat counting, but also increase hands-per-hour by ~20%, boosting casino profit.",

  // ── Drinking game trivia ─────────────────────────────────────
  "Drinking games date back to ancient Greece, 'Kottabos' involved flinging wine dregs at a target.",
  "Beer pong was likely invented at Dartmouth College in the 1950s, originally played with paddles.",
  "The world record for the most players in a single card game is 1,083 people.",
  "A standard deck of 52 cards has been around since at least the 14th century.",

  // ── Meta / drinking-strategy ─────────────────────────────────
  "If busting costs sips in your drinking rules, optimal strategy actually shifts, standing earlier becomes mathematically correct.",
  "Your bust rate likely climbs as the session goes on. After 45 minutes of drinking, decision quality drops ~20%.",
  "A conservative player (stands on all 12+) loses ~0.5% more edge than basic strategy. An aggressive drunk player loses ~2% more.",

  // ── Game-specific (Black(Out)Jack) ──────────────────────────
  "A suited Ace + Jack of Spades in Black(Out)Jack triggers all three multipliers: suited × A+J × both black = 8× bonus.",
  "With 4 players and 2 hands each, there are 8 player hands + 1 dealer hand = 9 hands per round.",
  "Splitting Aces up to 5 times means a single starting Ace can spawn up to 5 hands.",
  "Never split 10s in a casino, a 20 wins ~85% of the time. In Black(Out)Jack the drinking penalty makes it worth the chaos.",
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
