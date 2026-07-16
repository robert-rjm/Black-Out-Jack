// DEAL ANIMATION
// ============================================================
let _dealAnimating = false;   // true while cards are being dealt one-by-one

function _animToggleOn() {
  return lsGet("bjDealAnim") !== "0";
}

// Called by applyState when phase just flipped pre-deal → playing.
// Renders state, hides all cards, then reveals them one at a time.
async function animateDeal(newState) {
  _dealAnimating = true;
  const CARD_MS  = 300;
  const delay    = ms => new Promise(r => setTimeout(r, ms));

  try {
    // 1. Render full state so DOM has all card elements.
    _renderStateSilent(newState);

    // 2. Collect card elements in visual deal order (before first paint).
    const cardEls = _collectNewCardEls(newState);

    // 3. Hide all cards instantly using inline styles — no transition yet.
    cardEls.forEach(el => {
      el.style.transition = "none";
      el.style.opacity    = "0";
      el.style.transform  = "translateY(-16px) scale(.85)";
    });

    // 4. Wait one animation frame so the browser paints the hidden state.
    await new Promise(r => requestAnimationFrame(r));

    // 5. Reveal cards one by one with a smooth transition.
    for (const el of cardEls) {
      el.style.transition = "opacity .22s ease-out, transform .22s ease-out";
      el.style.opacity    = "1";
      el.style.transform  = "translateY(0) scale(1)";
      await delay(CARD_MS);
    }

    // 6. Clean up inline styles so CSS can take over normally.
    cardEls.forEach(el => {
      el.style.transition = "";
      el.style.opacity    = "";
      el.style.transform  = "";
    });
  } finally {
    _dealAnimating = false;
    // Now that cards are visible, open bust-vote modal if window is still open
    if (lastState && gameMode === "digital") updateBustVoteUI(lastState);
  }
}

// Renders state into the DOM without triggering any further animation.
function _renderStateSilent(state) {
  renderDealer(state);
  renderPlayers(state);
  syncAllHandButtons();
  applyTurnGate(state);
  if (gameMode === "digital") {
    autoSwitchDigTab(state);
    updateInsuranceVisibility(state);
    updateHandLocks(state);
    updateActionButtons(state);
    drinksPanel.render(state);
    updateBestPlay(state);
    updateBustVoteUI(state);
    updateRoleUI(state);
  }
}

// After rendering, collect card DOM elements in deal order so we can
// animate them in the right sequence.
// Server deal order (per _digital_initial_deal):
//   for round in [0,1]:
//     for each player: for each hand: deal card[round]
//     dealer: deal card[round]
function _collectNewCardEls(state) {
  const byName = {};
  (state.table || []).forEach(s => { byName[s.name] = s; });
  const order = state.play_order || (state.table || []).map(s => s.name);

  // Max cards any hand/dealer has (normally 2)
  const maxCards = Math.max(
    ...((state.table || []).flatMap(s => (s.hands || []).map(h => (h.cards || []).length))),
    (state.dealer_hand && state.dealer_hand.cards ? state.dealer_hand.cards.length : 0),
    0
  );

  // Build sequence: for each round → every hand of every player → dealer
  const seq = [];
  for (let round = 0; round < maxCards; round++) {
    for (const name of order) {
      const seat = byName[name];
      const numHands = seat ? (seat.hands || []).length : 1;
      for (let hi = 0; hi < numHands; hi++) {
        seq.push({ name, handIdx: hi, cardIdx: round, isDealer: false });
      }
    }
    seq.push({ isDealer: true, cardIdx: round });
  }

  // Index seat DOM elements by player name via the seat's data-player
  // attribute (set in renderPlayers()), rather than assuming DOM order
  // matches play_order — keeps this correct even if a seat fails to render.
  const seatMap = {};
  document.querySelectorAll("#left-col .seat[data-player]").forEach(seat => {
    seatMap[seat.dataset.player.toLowerCase()] = seat;
  });

  const els = [];
  for (const step of seq) {
    if (step.isDealer) {
      const panel = document.getElementById("dealer-panel");
      if (!panel) continue;
      const cardEls = panel.querySelectorAll(".card-el");
      if (cardEls[step.cardIdx]) els.push(cardEls[step.cardIdx]);
    } else {
      const seat = seatMap[step.name.toLowerCase()];
      if (!seat) continue;
      const hb = seat.querySelectorAll(".hand-block")[step.handIdx];
      if (!hb) continue;
      const cardEls = hb.querySelectorAll(".card-el");
      if (cardEls[step.cardIdx]) els.push(cardEls[step.cardIdx]);
    }
  }
  return els;
}

// ============================================================
