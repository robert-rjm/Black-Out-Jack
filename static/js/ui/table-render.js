function cardEl(card) {
  const div = document.createElement("div");
  div.className = "card-vis card-el";
  if (!card || card.suit === "hidden" || card.rank === "?") {
    div.classList.add("hidden");
    div.innerHTML = `<div class="top">?</div><div class="mid"><img class="card-logo" src="/static/Logo-BlackOutJack-transparent.png" alt="" /></div><div class="bot">?</div>`;
    return div;
  }
  if (SUIT_RED[card.suit]) div.classList.add("red");
  const sym = card.symbol || SUIT_SYMBOL[card.suit] || "?";
  div.innerHTML = `
    <div class="top">${card.rank}${sym}</div>
    <div class="mid">${sym}</div>
    <div class="bot">${card.rank}${sym}</div>`;
  return div;
}

function handBlock(handState, label) {
  const block = document.createElement("div");
  block.className = "hand-block";
  if (handState.done) block.classList.add("done");

  const lab = document.createElement("div");
  lab.className = "hand-label";
  lab.textContent = label;
  block.appendChild(lab);

  const row = document.createElement("div");
  row.className = "cards-row";
  (handState.cards || []).forEach(c => row.appendChild(cardEl(c)));
  block.appendChild(row);

  const meta = document.createElement("div");
  meta.className = "hand-meta";
  let tags = [];
  // score is null when the doubled card is still face-down — don't show it
  if (handState.cards && handState.cards.length > 0 && handState.score !== null && handState.score !== undefined) {
    tags.push(`<span class="score">${handState.score}</span>`);
  }
  if (handState.blackjack)           tags.push(`<span class="bj">BJ</span>`);
  else if (handState.bust)           tags.push(`<span class="bust">BUST</span>`);
  else if (handState.stood)          tags.push(`<span class="stood">STAND</span>`);
  if (handState.doubled)             tags.push(`<span>DBL</span>`);
  if (handState.from_split)          tags.push(`<span>SPL</span>`);
  if (handState.insured)             tags.push(`<span>INS</span>`);
  if (handState.result === "win")    tags.push(`<span class="win">WIN</span>`);
  else if (handState.result === "loss")  tags.push(`<span class="loss">LOSS</span>`);
  else if (handState.result === "push")  tags.push(`<span class="push">PUSH</span>`);
  meta.innerHTML = tags.join("");
  block.appendChild(meta);

  return block;
}

function renderDealer(state) {
  const root = document.getElementById("dealer-panel");
  if (!root) return;
  root.innerHTML = "";
  if (!state.dealer_hand) {
    root.innerHTML = `<span style="font-size:11px;color:var(--muted)">Dealer hand will appear here</span>`;
    return;
  }
  const dh             = state.dealer_hand;
  const dealerName     = state.dealer || "";
  // Sum dealer-role sips across ALL players (any player can be dealer across rounds)
  const dealerRoleSips = Object.values(state.dealer_role_sips || {}).reduce((a, b) => a + b, 0);
  const drinking       = state.drinking_mode !== false;

  // Header: name + sip badge (same pattern as player seat header)
  const sipBadge = (drinking && dealerRoleSips > 0)
    ? `<span class="seat-sip-badge">🍺 ${dealerRoleSips}</span>` : "";

  const hdr = document.createElement("div");
  hdr.className = "dp-header";
  hdr.innerHTML = `
    <div><span class="dp-name">Dealer</span><span class="dp-role">${escapeHtml(dealerName)}</span></div>
    <div>${sipBadge}</div>`;
  root.appendChild(hdr);

  // Cards row
  const cards = document.createElement("div");
  cards.className = "dp-cards";
  (dh.cards || []).forEach(c => cards.appendChild(cardEl(c)));
  root.appendChild(cards);

  // Score + result tags below cards — same hand-meta style as player hands
  const meta = document.createElement("div");
  meta.className = "hand-meta";
  const tags = [];
  if (!dh.hidden && dh.score !== null && dh.score !== undefined && (dh.cards || []).length > 0) {
    tags.push(`<span class="score">${dh.score}</span>`);
  }
  if (dh.blackjack)            tags.push(`<span class="bj">BJ</span>`);
  else if (dh.bust)            tags.push(`<span class="bust">BUST</span>`);
  else if (dh.done && !dh.hidden) tags.push(`<span class="stood">STAND</span>`);
  meta.innerHTML = tags.join("");
  if (tags.length) root.appendChild(meta);
}

function renderPlayers(state) {
  const root = document.getElementById("left-col");
  if (!root) return;
  const savedScroll = root.scrollTop;

  // Save each player's horizontal hand scroll before wiping DOM
  const handScroll = {};
  root.querySelectorAll(".seat[data-player]").forEach(s => {
    const row = s.querySelector(".hands-row");
    if (row) handScroll[s.dataset.player] = row.scrollLeft;
  });

  root.innerHTML = "";

  const order = state.play_order && state.play_order.length
                  ? state.play_order
                  : (state.table || []).map(t => t.name);
  const byName = {};
  (state.table || []).forEach(s => { byName[s.name] = s; });

  const showTurn = state.mode === "digital" && state.phase === "playing";
  order.forEach(name => {
    const s = byName[name];
    if (!s) return;
    const seat = document.createElement("div");
    seat.className = "seat";
    seat.dataset.player = s.name;
    if (showTurn && s.is_turn) seat.classList.add("turn");
    if (s.done)                seat.classList.add("done");

    const hdr = document.createElement("div");
    hdr.className = "seat-header";
    const role     = s.is_dealer ? `<span class="role">also dealer</span>` : "";
    const botTag   = s.is_npc    ? `<span class="role" style="color:var(--accent)">BOT</span>` : "";
    const tag      = (showTurn && s.is_turn) ? `<div class="turn-tag">${s.is_npc ? "BOT playing…" : "Turn"}</div>` : "";
    const sips     = (state.sip_totals || {})[s.name] || 0;
    const sipBadge = (state.drinking_mode !== false && sips > 0)
      ? `<span class="seat-sip-badge">🍺 ${sips}</span>` : "";

    // Crown: player had 0 net sips last round (after bust vote).
    // Show during the following round only (not during round-over when data is freshly set).
    const lastSips      = state.last_round_sips || {};
    const roundOver     = state.phase === "round-over";
    const hadPrevRound  = state.round > 1;
    const playedLastRound = s.name in lastSips;
    const wasClean        = hadPrevRound && !roundOver && playedLastRound && lastSips[s.name] === 0;
    const crownBadge    = (wasClean && state.drinking_mode !== false)
      ? `<span class="seat-crown" title="Clean last round">👑</span>` : "";

    hdr.innerHTML = `<div class="seat-name">${escapeHtml(s.name)}${crownBadge}${role}${botTag}</div><div style="display:flex;align-items:center;gap:6px">${sipBadge}${tag}</div>`;
    seat.appendChild(hdr);

    const hands = document.createElement("div");
    hands.className = "hands-row";
    (s.hands || []).forEach((h, i) => hands.appendChild(handBlock(h, `Hand ${i+1}`)));
    if (!s.hands || s.hands.length === 0) {
      const empty = document.createElement("div");
      empty.className = "hand-label";
      empty.textContent = "(no cards yet)";
      hands.appendChild(empty);
    }
    seat.appendChild(hands);
    root.appendChild(seat);
  });

  // Restore vertical + per-player horizontal scroll
  root.scrollTop = savedScroll;
  root.querySelectorAll(".seat[data-player]").forEach(s => {
    const saved = handScroll[s.dataset.player];
    if (saved) {
      const row = s.querySelector(".hands-row");
      if (row) row.scrollLeft = saved;
    }
  });
}

function applyTurnGate(state) {
  // Only enforce in digital mode + during play phase
  const gate        = state.mode === "digital" && state.phase === "playing" && state.current_turn;
  const currentSeat = (state.table || []).find(s => s.name === state.current_turn);
  const isNpcTurn   = gate && currentSeat && currentSeat.is_npc;

  // Disable all action buttons while an NPC is taking its turn
  digActionButtons().forEach(b => {
    b.classList.toggle("disabled", !!isNpcTurn);
  });

  // Auto-select current-turn player and first active hand
  if (gate) {
    sel.digital.player = state.current_turn;

    const seat = (state.table || []).find(s => s.name === state.current_turn);
    if (seat && seat.hands) {
      const firstActiveIdx = seat.hands.findIndex(h => !h.done);
      if (firstActiveIdx >= 0) {
        sel.digital.hand = `hand${firstActiveIdx + 1}`;
      }
    }
  }
}

// ============================================================
