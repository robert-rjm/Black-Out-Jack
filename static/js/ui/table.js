// ============================================================
// GAME UI CONSTRUCTION
// ============================================================
function buildGameUI() {
  const isDigital = gameMode === "digital";

  document.getElementById("ref-panel").style.display = isDigital ? "none"  : "block";
  document.getElementById("dig-panel").style.display = isDigital ? "block" : "none";

  const regBanner = document.getElementById("pending-reg-banner");
  if (regBanner) pendingRegBanner.mount(regBanner);

  const msModal   = document.getElementById("milestone-modal-overlay");
  const msAckOv   = document.getElementById("ms-ack-overlay");
  if (msModal && msAckOv) milestonePanel.mount(msModal, msAckOv);

  if (isDigital) {
    buildDigitalUI();
  } else {
    buildRefereeUI();
  }
}

function buildRefereeUI() {
  buildPlayerButtons("deal-players",   "deal",   true);
  buildPlayerButtons("result-players", "result", true);
  buildPlayerButtons("action-players", "action", true);
  buildHandButtons("deal-hands",   "deal");
  buildHandButtons("result-hands", "result");
  buildHandButtons("action-hands", "action");
  buildCardGrid();
  if (players.length > 0) {
    setPlayerSel("deal",   players[0]);
    setPlayerSel("result", players[0]);
    setPlayerSel("action", players[0]);
  }
}

function buildDigitalUI() {
  // Player and hand selection is driven automatically by game state (applyTurnGate)
  const roundPane = document.getElementById("pane-dig-round");
  if (roundPane) drinksPanel.mount(roundPane);
  const giveOverlay = document.getElementById("bust-give-overlay");
  if (giveOverlay) bustGivePanel.mount(giveOverlay);
  const dlGiveOverlay = document.getElementById("dealer-lottery-give-overlay");
  if (dlGiveOverlay) dealerLotteryGivePanel.mount(dlGiveOverlay);
  const bustVoteOverlay = document.getElementById("bust-vote-modal-overlay");
  if (bustVoteOverlay) bustVotePanel.mount(bustVoteOverlay);
  const insModal  = document.getElementById("insurance-modal-overlay");
  const insBanner = document.getElementById("insurance-vote-banner");
  if (insModal && insBanner) insurancePanel.mount(insModal, insBanner);
  const dlEntryOverlay = document.getElementById("dealer-lottery-modal-overlay");
  if (dlEntryOverlay) dealerLotteryEntryPanel.mount(dlEntryOverlay);
  const tdOverlay = document.getElementById("targeted-drinking-modal-overlay");
  if (tdOverlay) targetedDrinkingPanel.mount(tdOverlay);
}

// includeDealer: referee needs DEALER_SENTINEL in player lists; digital play does not
function buildPlayerButtons(containerId, pane, includeDealer) {
  const c = document.getElementById(containerId);
  c.innerHTML = "";
  let list = includeDealer ? [...players, DEALER_SENTINEL] : players;
  // Exclude NPC players from the Play pane — they act automatically
  if (pane === "digital") list = list.filter(name => !npcPlayers.has(name));
  list.forEach(name => {
    const b = document.createElement("button");
    b.className = "btn";
    b.textContent = name;
    b.onclick = () => setPlayerSel(pane, name);
    c.appendChild(b);
  });
}

function buildHandButtons(containerId, pane) {
  const c = document.getElementById(containerId);
  c.innerHTML = "";
  for (let i = 1; i <= numHands; i++) {
    const b = document.createElement("button");
    b.className = "btn" + (i === 1 ? " sel" : "");
    b.textContent = `H${i}`;
    b.onclick = () => setHandSel(pane, `hand${i}`, b, containerId);
    c.appendChild(b);
  }
}

function buildCardGrid() {
  const rg = document.getElementById("rank-grid");
  rg.innerHTML = "";
  RANKS.forEach(r => {
    const b = document.createElement("button");
    b.className = "card-btn";
    b.textContent = r;
    b.onclick = () => selectRank(r, b);
    rg.appendChild(b);
  });
  const sg = document.getElementById("suit-grid");
  sg.innerHTML = "";
  SUITS.forEach(s => {
    const b = document.createElement("button");
    b.className = `card-btn ${s.cls}`;
    b.textContent = s.label;
    b.dataset.code = s.code;
    b.onclick = () => selectSuit(s.code, b);
    sg.appendChild(b);
  });
}

// ============================================================
// SELECTION HELPERS
// ============================================================
const PLAYER_CONTAINER = {
  deal: "deal-players", result: "result-players",
  action: "action-players", digital: "dig-play-players",
};

function setPlayerSel(pane, name) {
  // During digital play, silently ignore taps on the wrong player — the
  // turn-gate CSS (pointer-events:none) covers most cases but touch events
  // can slip through on some mobile browsers, so enforce it in JS too.
  if (pane === "digital" && lastState && lastState.phase === PHASE.PLAYING && lastState.current_turn) {
    if (name.toLowerCase() !== lastState.current_turn.toLowerCase()) return;
  }
  sel[pane].player = name;
  document.querySelectorAll(`#${PLAYER_CONTAINER[pane]} .btn`).forEach(b => {
    b.classList.toggle("sel", b.textContent === name);
  });
  // After (re)selecting a player, sync the hand buttons to that player's
  // actual hand count (which grows beyond numHands after splits).
  syncHandButtonsFor(pane);
}

const HAND_CONTAINER = {
  deal: "deal-hands", result: "result-hands",
  action: "action-hands", digital: "dig-play-hands",
};

function setHandSel(pane, hand, btn, containerId) {
  sel[pane].hand = hand;
  document.querySelectorAll(`#${containerId} .btn`).forEach(b => b.classList.remove("sel"));
  btn.classList.add("sel");
}

// How many hands does the named player currently have?
function handCountFor(playerName) {
  if (!lastState || !lastState.table) return numHands;
  if (playerName === DEALER_SENTINEL) return 1;
  const seat = lastState.table.find(s => s.name === playerName);
  if (!seat || !seat.hands) return numHands;
  return Math.max(numHands, seat.hands.length);
}

// Rebuild the hand buttons in a pane so they reflect the selected player's
// actual hand count (e.g. show H3 after a split). Preserves selection when
// possible; otherwise falls back to H1.
function syncHandButtonsFor(pane) {
  const containerId = HAND_CONTAINER[pane];
  const c = document.getElementById(containerId);
  if (!c) return;
  const playerName = sel[pane].player;
  if (!playerName) return;

  const target = handCountFor(playerName);
  const existing = c.querySelectorAll(".btn").length;
  if (existing === target) return;

  // If the previously selected hand index no longer exists, fall back to hand1
  const desiredIdx = parseInt((sel[pane].hand || "hand1").replace("hand", ""), 10) || 1;
  const selIdx = desiredIdx <= target ? desiredIdx : 1;
  sel[pane].hand = `hand${selIdx}`;

  c.innerHTML = "";
  for (let i = 1; i <= target; i++) {
    const b = document.createElement("button");
    b.className = "btn" + (i === selIdx ? " sel" : "");
    b.textContent = `H${i}`;
    b.onclick = () => setHandSel(pane, `hand${i}`, b, containerId);
    c.appendChild(b);
  }
}

// Resync hand buttons across all panes — called whenever fresh state arrives.
function syncAllHandButtons() {
  ["deal", "result", "action"].forEach(syncHandButtonsFor);
}

function selectRank(rank, btn) {
  selRank = rank;
  document.querySelectorAll("#rank-grid .card-btn").forEach(b => b.classList.remove("sel"));
  btn.classList.add("sel");
  tryDeal();
}

function selectSuit(suit, btn) {
  selSuit = suit;
  document.querySelectorAll("#suit-grid .card-btn").forEach(b => b.classList.remove("sel"));
  btn.classList.add("sel");
  tryDeal();
}

function tryDeal() {
  if (!selRank || !selSuit) return;
  const player = sel.deal.player;
  const hand   = sel.deal.hand;
  if (!player) { appendLog("  Select a player first.\n"); return; }

  const pToken = (player === DEALER_SENTINEL) ? "dealer" : player;
  const card   = selRank.toLowerCase() + selSuit;
  sendCmd(`deal ${pToken} ${card} ${hand}`);

  selRank = null; selSuit = null;
  document.querySelectorAll(".card-btn.sel").forEach(b => b.classList.remove("sel"));
}

// ============================================================
// RESULT / ACTION / DIGITAL DISPATCH
// ============================================================
function sendResult(outcome) {
  const player = sel.result.player;
  const hand   = sel.result.hand;
  if (!player) { appendLog("  Select a player first.\n"); return; }
  sendCmd(player === DEALER_SENTINEL
    ? `result dealer ${outcome}`
    : `result ${player} ${outcome} ${hand}`);
}

function sendAction(action) {
  const player = sel.action.player;
  const hand   = sel.action.hand;
  if (!player) { appendLog("  Select a player first.\n"); return; }
  sendCmd(`action ${player} ${action} ${hand}`);
}

function sendDigitalPlay(action) {
  // Non-dealer player (or admin with god mode off): pre-select instead of executing
  if (!isMyDealerClient && (myRole === ROLE.PLAYER || myRole === ROLE.ADMIN) && (myActiveName || myName)) {
    // Only allow voting when it is actually the player's own turn
    if (!lastState || lastState.phase !== PHASE.PLAYING ||
        !lastState.current_turn ||
        lastState.current_turn.toLowerCase() !== (myActiveName || myName || "").toLowerCase()) {
      return;  // not your turn — ignore the tap
    }
    const hand = sel.digital.hand || "hand1";

    // Immediate optimistic feedback — highlight button + update vote display NOW
    // (will be confirmed/corrected once the server responds)
    const ACT_LBL  = { hit: "HIT", stand: "STAND", double: "DOUBLE", split: "SPLIT" };
    const ACT_CODE = { hit: "h",   stand: "s",     double: "d",      split: "sp" };
    const _code = ACT_CODE[action] || action;
    digActionButtons().forEach(b => b.classList.remove("voted"));
    digActionButtons().forEach(b => {
      if (b.dataset.actionCode === _code) b.classList.add("voted");
    });
    const _vd = document.getElementById("player-vote-display");
    if (_vd) {
      _vd.textContent    = `Your vote: ${ACT_LBL[action] || action.toUpperCase()} — sending…`;
      _vd.style.display  = "block";
    }

    sendPreselect(action, hand);
    return;
  }
  // Spectators: do nothing
  if (!isMyDealerClient) return;

  const player = sel.digital.player;
  const hand   = sel.digital.hand;
  if (!player) { appendLog("  Select a player first.\n"); return; }
  // Belt-and-suspenders: reject if somehow a different player slipped through
  if (lastState && lastState.phase === PHASE.PLAYING && lastState.current_turn &&
      player.toLowerCase() !== lastState.current_turn.toLowerCase()) return;
  sendCmd(`${action} ${player} ${hand}`);
}

async function sendPreselect(action, hand) {
  // Map full words → single-letter codes the server expects
  const ACTION_CODE = { hit: "h", stand: "s", double: "d", split: "sp" };
  const code = ACTION_CODE[action] || action;
  const vd = document.getElementById("player-vote-display");
  _requestsInFlight++;
  try {
    const res  = await fetch("/preselect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, hand, action: code }),
    });
    const data = await res.json();
    if (data.ok) {
      applyState(data);
    } else {
      // Vote was rejected — clear optimistic highlight and show reason
      digActionButtons().forEach(b => b.classList.remove("voted"));
      if (vd) { vd.textContent = `Vote failed: ${data.error || "not registered"}`; vd.style.display = "block"; }
    }
  } catch (_) {
    digActionButtons().forEach(b => b.classList.remove("voted"));
    if (vd) { vd.textContent = "Vote failed: network error"; vd.style.display = "block"; }
  } finally {
    _requestDone();
  }
}

// ============================================================
// SEND COMMAND
// ============================================================
async function sendCmd(cmd) {
  if (_requestsInFlight > 0) {
    // Queue for replay once the in-flight request settles; last intent wins.
    _pendingCmd = cmd;
    console.warn("[sendCmd] request in flight — queued:", cmd);
    return;
  }
  _pendingCmd = null;
  _requestsInFlight++;
  if (typeof resetIdleTimer === "function") resetIdleTimer();
  // Visually lock all action buttons while the request is in flight
  cmdLockButtons().forEach(b => b.classList.add("cmd-pending"));
  try {
    const res  = await fetch("/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd, room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    // Log and peeked card are handled inside applyState so all players
    // see them via polling — no direct appendLog/showPeekedCard here.
    if (data.dealer || data.players) updateHeader(data);
    applyState(data);
  } catch (_) {
    appendLog("  Command failed — server unreachable.\n");
  } finally {
    document.querySelectorAll(".cmd-pending").forEach(b => b.classList.remove("cmd-pending"));
    _requestDone();
  }
}

// ============================================================
// SHARED LOG SYNC
// ============================================================
function syncLogFromState(state) {
  if (state.log_version === undefined) return;
  const ver     = state.log_version || 0;
  const entries = state.log_entries  || [];

  // Version bump = new game or new round — reset log counter
  if (ver !== logVersion) {
    logVersion = ver;
    logCount   = 0;
  }
  logCount = entries.length;
}


// ============================================================
// APPLY STATE — helpers
// ============================================================

// Handle kicked status. Returns true if applyState should stop processing.
function _applyKicked(state) {
  if (state.my_role !== ROLE.KICKED) return false;
  if (myRole === ROLE.SPECTATOR) return true;   // already acknowledged; keep watching
  stopPolling();
  const leave = confirm("You have been removed from this session.\n\nPress OK to return to the lobby, or Cancel to stay and watch as a spectator.");
  if (leave) {
    roomCode = "";
    myRole   = null;
    myName   = null;
    isMyDealerClient = false;
    lsRemove("bjRoomCode");
    document.getElementById("app").style.display    = "none";
    document.getElementById("setup").style.display  = "none";
    document.getElementById("lobby").style.display  = "flex";
    document.getElementById("header-room").textContent = "";
    hideLobbyMsg();
    players  = [];
    gameMode = "referee";
  } else {
    // Register as spectator server-side so server stops returning "kicked"
    doSpectate();
  }
  return true;
}

// Toggle drink-mode body class and update the Drinks tab label.
function _syncDrinkMode(state, drinkingOn) {
  document.body.classList.toggle("no-drinking", !drinkingOn);
  const drinksTab = document.getElementById("dig-drinks-tab");
  if (drinksTab) drinksTab.textContent = drinkingOn ? "🍺 Drinks" : "🃏 Round";
}

// Update client identity (role, name, isMyDealerClient) from server state,
// and show a dealer-rotation toast when this client becomes the dealer.
function _syncIdentity(state) {
  const _prevDealerName = lastState ? (lastState.dealer || "") : "";
  if (state.my_role !== undefined) {
    if (state.my_role !== null) {
      myRole           = state.my_role;
      myName           = state.my_name   || null;
      myNames          = state.my_names  || (myName ? [myName] : []);
      isMyDealerClient = state.is_dealer_client || false;
      // Initialise myActiveName on first registration, or reset if the
      // active name is no longer in myNames (e.g. after admin transfer)
      if (!myActiveName && myName) {
        myActiveName = myName;
      } else if (myActiveName && myNames.length > 0 && !myNames.some(n => n.toLowerCase() === myActiveName.toLowerCase())) {
        myActiveName = myName;
      }
    } else if (!myRole) {
      myRole           = null;
      myName           = null;
      myNames          = [];
      isMyDealerClient = false;
    }
  }
  // Show toast when dealer role is newly rotated to this client.
  const newDealerName = state.dealer || "";
  const iAmDealer = myNames.some(n => n.toLowerCase() === newDealerName.toLowerCase());
  const wasDealer = myNames.some(n => n.toLowerCase() === _prevDealerName.toLowerCase());
  // No "you are dealer" toast in normal (non-drinking) mode — dealer is the house
  if (lastState !== null && iAmDealer && !wasDealer && state.drinking_mode) showDealerToast();
}

// Sync DrinkUI round data and fire all one-shot toasts gated on sequence numbers.
function _syncRoundEffects(state, drinkingOn) {
  // Always sync last/prev round data from server so both variables stay in lockstep.
  if (state.last_round_sips !== undefined)  DrinkUI.lastRoundSips   = state.last_round_sips  || {};
  if (state.last_round_drinks !== undefined) DrinkUI.lastRoundDrinks = state.last_round_drinks || [];
  if (state.prev_round_sips !== undefined)  DrinkUI.prevRoundSips   = state.prev_round_sips  || {};
  if (state.prev_round_drinks !== undefined) DrinkUI.prevRoundDrinks = state.prev_round_drinks || [];

  // One-shot round-end effects — gated on round_over_seq so duplicate/late
  // polls never re-fire them.
  const newRoundOverSeq = state.round_over_seq || 0;
  const isNewRoundOver  = newRoundOverSeq > DrinkUI.lastRoundOverSeq;
  if (isNewRoundOver) {
    if (drinkingOn && myNames.length > 0 && myRole !== ROLE.SPECTATOR) {
      myNames.forEach(n => showPlayerDrinkToast(DrinkUI.lastRoundSips[n] || 0, n));
    }
    if (drinkingOn && state.switch_this_round) {
      showSwitchToast(state.switch_this_round, state.dealer || "Dealer");
    }
    if (state.bust_vote_result) {
      showBustVoteToast(state.bust_vote_result);
    }
    if (state.insurance_result && state.insurance_result.length) {
      showInsuranceToast(state.insurance_result);
    }
    _maybeAutoExportDecisions(state);
  }
  DrinkUI.lastRoundOverSeq = Math.max(DrinkUI.lastRoundOverSeq, newRoundOverSeq);

  // Bust-handout reveal — gated on bust_handout_seq.
  const newBustHandoutSeq = state.bust_handout_seq || 0;
  if (newBustHandoutSeq > DrinkUI.lastBustHandoutSeq) {
    if (state.bust_handout_results && state.bust_handout_results.length) {
      showBustHandoutToast(state.bust_handout_results);
    }
    DrinkUI.lastBustHandoutSeq = newBustHandoutSeq;
  }

  // Dealer Lottery draw reveal — gated on dealer_lottery.result_seq.
  const dl = state.dealer_lottery || {};
  const newDealerLotterySeq = dl.result_seq || 0;
  if (newDealerLotterySeq > DrinkUI.lastDealerLotteryResultSeq) {
    if (dl.last_result) _showDealerLotteryRevealModal(dl.last_result);
    DrinkUI.lastDealerLotteryResultSeq = newDealerLotterySeq;
  }
}

// Sync log, sip ticker, in-round drink events, and KPI panel.
function _syncLog(state, drinkingOn) {
  syncLogFromState(state);
  updateSipTicker(state);
  if (drinkingOn) processAceDrinkEvents(state);
  processReshuffleEvents(state);
  if (drinkingOn) processWildCardEvent(state);
  if (drinkingOn) processTableEvents(state);
  if (drinkingOn) updateHonorPrompt(state);
  if (!drinkingOn) updateBankRunPrompt(state);
  updateKpiPanel(state);
}

// Keep settings modal, settings button, register overlay, kick vote banner,
// and spectator rejoin banner in sync with server state.
function _syncModals(state) {
  const kickOv = document.getElementById("kick-overlay");
  if (kickOv && kickOv.style.display === "flex") {
    if (state.queued_settings) _renderQueuedBanner(state.queued_settings);
    if (myRole === ROLE.ADMIN || myRole === ROLE.PLAYER) openKickModal();
  }

  const showSettings = (myRole === ROLE.ADMIN || myRole === ROLE.PLAYER) ? "block" : "none";
  const adminBtn = document.getElementById("btn-admin-players");
  if (adminBtn) adminBtn.style.display = showSettings;
  const adminNav = document.getElementById("btn-admin-nav");
  if (adminNav) adminNav.style.display = showSettings;

  if (state.anim_default !== undefined && lsGet("bjDealAnim") === null) {
    setAnimToggle(state.anim_default);
  }

  updateRegisterOverlay(state);
  renderKickVoteBanner(state);

  // Wild Card logo: pointer cursor only when Easter egg is enabled AND round is active
  const logo = document.getElementById("header-logo");
  if (logo) {
    const activePhase = state.phase === "playing" || state.phase === "dealer-ready";
    const wcEnabled   = state.wild_card_enabled !== false && state.drinking_mode !== false && activePhase;
    logo.style.cursor        = wcEnabled ? "pointer" : "default";
    logo.style.pointerEvents = wcEnabled ? "auto"    : "none";
    logo.title               = wcEnabled ? "🃏" : "";
  }

  const rejoinBanner = document.getElementById("spectator-rejoin-banner");
  const rejoinBtn    = document.getElementById("rejoin-req-btn");
  if (rejoinBanner) {
    if (myRole === ROLE.SPECTATOR && state.my_name === null) {
      rejoinBanner.style.display = "flex";
      if (rejoinBtn) rejoinBtn.disabled    = !!state.my_rejoin_pending;
      if (rejoinBtn) rejoinBtn.textContent = state.my_rejoin_pending ? "Request sent ✓" : "Request to rejoin";
    } else {
      rejoinBanner.style.display = "none";
    }
  }
}

// Digital-mode only: sync tab selection, insurance, hand locks, round pane,
// best play hint, and bust vote UI.
function _syncDigitalUI(state) {
  autoSwitchDigTab(state);
  insurancePanel.updateVisibility(state);
  updateHandLocks(state);
  drinksPanel.render(state);
  updateBestPlay(state);
  bustVotePanel.render(state);
  dealerLotteryEntryPanel.render(state);
  targetedDrinkingPanel.render(state);
}

// Dispatch render: deal animation on fresh deal, or full table render otherwise.
function _syncRender(state, isDeal) {
  if (isDeal) {
    // animateDeal renders state itself card-by-card — don't render twice.
    animateDeal(state);
  } else if (_dealAnimating) {
    // Animation in progress — skip render to avoid interrupting it.
    // (applyState still ran above for log, ticker, buttons, etc.)
  } else {
    renderDealer(state);
    renderPlayers(state);
    syncAllHandButtons();
    applyTurnGate(state);
    if (gameMode === "digital") {
      // Must run AFTER applyTurnGate — these have final say on action buttons.
      updateActionButtons(state);
      updateRoleUI(state);
    }
  }
}

// ============================================================
// VISIBLE TABLE + TURN ENFORCEMENT
// ============================================================
const SUIT_SYMBOL = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };
const SUIT_RED    = { hearts: true, diamonds: true };

function applyState(state) {
  if (!state || !state.ok) return;

  const drinkingOn = state.drinking_mode !== false;

  // Drop stale responses — discard if older than what we already applied.
  if (state.state_seq !== undefined &&
      lastState && lastState.state_seq !== undefined &&
      state.state_seq < lastState.state_seq) {
    return;
  }

  if (_applyKicked(state)) return;

  _syncDrinkMode(state, drinkingOn);
  _syncIdentity(state);

  // Capture prevPhase before committing new state (used for deal animation
  // detection and idle-timer check).
  const prevPhase = lastState ? lastState.phase : null;
  const isDeal    = (
    gameMode === "digital" &&
    prevPhase === PHASE.PRE_DEAL &&
    state.phase === PHASE.PLAYING &&
    _animToggleOn()
  );

  // Keep npcPlayers in sync with latest table state.
  if (state.table) {
    npcPlayers = new Set(state.table.filter(p => p.is_npc).map(p => p.name));
  }

  // Reset idle timer on any game state change.
  if (typeof resetIdleTimer === "function") {
    const prevRound = lastState ? (lastState.round || 0) : 0;
    if (state.phase !== prevPhase || (state.round || 0) > prevRound) {
      resetIdleTimer();
    }
  }

  _syncRoundEffects(state, drinkingOn);

  // Commit new state — capture bust-vote open flag first.
  const _prevBustOpen = lastState && lastState.bust_vote_window_open;
  lastState   = state;
  // Optimistic hint override: prevent stale polls (same state_seq) from flipping
  // strategy_hint_enabled back to false between the /set_hint response and the next poll.
  if (window._myHintEnabled !== null && window._myHintEnabled !== undefined && lastState.table) {
    const _myNamesLc = (lastState.my_names || (lastState.my_name ? [lastState.my_name] : []))
      .map(n => n.toLowerCase());
    lastState.table.forEach(s => {
      if (_myNamesLc.includes(s.name.toLowerCase())) s.strategy_hint_enabled = window._myHintEnabled;
    });
  }
  currentTurn = state.current_turn || null;
  if (_prevBustOpen && !state.bust_vote_window_open && typeof flushToastQueue === "function") {
    flushToastQueue();
  }
  // Auto-switch active seat when turn moves to another local player.
  if (currentTurn && myNames.length > 1) {
    const turnLow = currentTurn.toLowerCase();
    const match   = myNames.find(n => n.toLowerCase() === turnLow);
    if (match) myActiveName = match;
  }

  _syncLog(state, drinkingOn);
  _syncModals(state);

  if (gameMode === "digital") _syncDigitalUI(state);
  _syncRender(state, isDeal);

  milestonePanel.render(state);
}


// Disable SPLIT when the active hand can't be split (limit reached or cards don't match).
// Disable DOUBLE when the hand already has more than 2 cards or is already doubled.
function updateActionButtons(state) {
  if (!state || state.phase !== PHASE.PLAYING || !state.current_turn) return;
  const seat = (state.table || []).find(s => s.name === state.current_turn);
  if (!seat) return;
  const activeHand = (seat.hands || []).find(h => !h.done);
  if (!activeHand) return;

  // can_double is computed server-side in serialize_hand() — 2-card hand, not yet doubled
  digActionButtons().forEach(b => {
    const code = b.dataset.actionCode;
    if (code === "sp") b.classList.toggle("disabled", !activeHand.can_split);
    if (code === "d")  b.classList.toggle("disabled", !activeHand.can_double);
  });
}

function updateHandLocks(state) {
  if (!state || state.phase !== PHASE.PLAYING) return;
  const seat = (state.table || []).find(s => s.name === state.current_turn);
  if (!seat || !seat.hands) return;
  const c = document.getElementById("dig-play-hands");
  if (!c) return;
  c.querySelectorAll(".btn").forEach((btn, i) => {
    const locked = seat.hands.slice(0, i).some(h => !h.done);
    btn.classList.toggle("disabled", locked);
    btn.title = locked ? "Finish previous hand first" : "";
  });
}

function updateBestPlay(state) {
  // Clear any previous highlight
  digActionButtons().forEach(b => b.classList.remove("best"));
  if (!state || state.phase !== PHASE.PLAYING || !state.best_play) return;
  // Only highlight if the current player has hints enabled (server-side per-seat flag)
  const myNames = state.my_names || (state.my_name ? [state.my_name] : []);
  const hintsOn = (state.table || []).some(s => myNames.includes(s.name) && s.strategy_hint_enabled);
  if (!hintsOn) return;
  // state.best_play is the backend code (h/s/d/sp) — matches data-action-code directly
  digActionButtons().forEach(b => {
    if (b.dataset.actionCode === state.best_play) b.classList.add("best");
  });
}

// ── House rule: mandatory split on unsuited 10s (drinking mode only) ───────
// Purely a display layer: the backend decides when this prompt is needed
// (state.honor_pending) and what each choice does. The frontend just shows
// or hides the overlay and forwards the player's choice to /honor_resolve.
function updateHonorPrompt(state) {
  const overlay = document.getElementById("honor-split-overlay");
  if (!overlay) return;
  overlay.classList.toggle("open", !!(state && state.honor_pending));

  // Only admins and seated players may resolve the prompt -- spectators
  // see it (for visibility) but their buttons are disabled.
  const role     = state && state.my_role;
  const canAct   = role === ROLE.ADMIN || role === ROLE.PLAYER;
  overlay.querySelectorAll("#honor-split-modal .btn-row button").forEach(btn => {
    btn.disabled = !canAct;
  });

  // Label the "without honor" button with the action that's actually
  // pending (Hit / Double / Stand), so the +1 sip context is clear.
  const noBtn = document.getElementById("honor-no-btn");
  if (noBtn) {
    const action = (state && state.honor_pending_action) || "stand";
    const label  = action.charAt(0).toUpperCase() + action.slice(1);
    noBtn.textContent = `${label} without honor (1 sip)`;
  }

  // Swap title/subtitle based on whether this is an Ace-pair or 10-pair rule.
  const reason   = state && state.honor_pending_reason;
  const isAces   = reason === "aces";
  const titleEl  = document.getElementById("honor-title");
  const subEl    = document.getElementById("honor-sub");
  const emojiEl  = document.getElementById("honor-emoji");
  if (titleEl) titleEl.textContent = isAces ? "House Rule: Always Split Aces" : "House Rule: Always Split 10s";
  if (emojiEl) emojiEl.textContent = isAces ? "🂡" : "🃏";
  if (subEl)   subEl.textContent   = isAces
    ? "You have two Aces — the house rule says you must split. Play anyway and take a 1-sip penalty?"
    : "Your hand is two unsuited 10-value cards: the house rule says you must split. Do it anyway and take a 1-sip penalty?";
}

async function honorResolve(choice) {
  document.getElementById("honor-split-overlay")?.classList.remove("open");
  _requestsInFlight++;
  try {
    const res  = await fetch("/honor_resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, choice }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {
    appendLog("  Honor resolve failed — server unreachable.\n");
  } finally {
    _requestDone();
  }
}
window.honorResolve = honorResolve;

// ── "Bank Run" modal: shown to a player whose bankroll hits $0 (Normal
// mode only). Offers a re-buy back to the starting bankroll, or to keep
// spectating with $0 (Exit / Spectate just dismisses the modal — the
// player can still watch the table).
function updateBankRunPrompt(state) {
  const overlay = document.getElementById("bank-run-overlay");
  if (!overlay) return;

  const bankRun = (state && state.bank_run_players) || [];
  // Only show the modal to a busted player who hasn't dismissed it yet.
  const myBusted = myNames.find(n => bankRun.some(b => b.toLowerCase() === n.toLowerCase()));

  if (myBusted && !DrinkUI._bankRunDismissed?.has(myBusted)) {
    overlay.classList.add("open");
    const nameEl = document.getElementById("bank-run-player-name");
    if (nameEl) nameEl.textContent = myBusted;
    overlay.dataset.player = myBusted;
  } else {
    overlay.classList.remove("open");
  }
}

async function bankRebuy() {
  const overlay = document.getElementById("bank-run-overlay");
  const player  = overlay?.dataset.player;
  overlay?.classList.remove("open");
  if (!player) return;
  _requestsInFlight++;
  try {
    const res  = await fetch("/rebuy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, player }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {
    appendLog("  Rebuy failed — server unreachable.\n");
  } finally {
    _requestDone();
  }
}
window.bankRebuy = bankRebuy;

function bankExit() {
  const overlay = document.getElementById("bank-run-overlay");
  const player  = overlay?.dataset.player;
  overlay?.classList.remove("open");
  if (player) {
    DrinkUI._bankRunDismissed = DrinkUI._bankRunDismissed || new Set();
    DrinkUI._bankRunDismissed.add(player);
  }
}
window.bankExit = bankExit;

// ── Drinks pane component (Improvements.md item 7, Option A: class-based,
// no framework) ──────────────────────────────────────────────────────────
// Encapsulates #pane-dig-round's drinks-summary subtree. mount() attaches
// one delegated click listener for .drinks-card taps (replacing the former
// per-card onclick="selectDrinksPlayer(...)" string), so re-rendering the
// cards on every poll never needs to re-attach any handler. render(state)
// rebuilds the DOM exactly as the old updateRoundPane()/renderDrinksDetail()
// functions did -- same markup, same behavior, just no string-built onclick.
class DrinksPanel {
  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const card = e.target.closest(".drinks-card");
      if (card) this._selectPlayer(card.dataset.name);
    });
  }

  _selectPlayer(name) {
    // Toggle: tap same card again to deselect
    DrinkUI.drinksPaneSelected = (DrinkUI.drinksPaneSelected === name) ? null : name;
    this._renderDetail();
    // Re-highlight cards via CSS class (outline defined in utilities.css)
    this.el.querySelectorAll(".drinks-card").forEach(cardEl => {
      cardEl.classList.toggle("selected", cardEl.dataset.name === DrinkUI.drinksPaneSelected);
    });
  }

  _renderDetail() {
    const detail = this.el.querySelector("#dig-drinks-detail");
    if (!detail) return;
    if (!DrinkUI.drinksPaneSelected) {
      detail.innerHTML = `<div class="drinks-detail-empty">← tap a name<br>to see details</div>`;
      return;
    }
    const entries = DrinkUI.lastRoundDrinks.filter(d => d.name === DrinkUI.drinksPaneSelected);
    const total   = DrinkUI.lastRoundSips[DrinkUI.drinksPaneSelected] || 0;
    if (!entries.length) {
      detail.innerHTML = `<div class="drinks-detail-clean">${escapeHtml(DrinkUI.drinksPaneSelected)} — no drinks 🎉</div>`;
      return;
    }
    detail.innerHTML =
      `<div class="drinks-detail-header">${escapeHtml(DrinkUI.drinksPaneSelected)} · ${total} sip${total !== 1 ? "s" : ""}</div>` +
      entries.map(d => {
        const isCredit = d.sips < 0;
        const col   = isCredit ? "var(--green)" : "var(--red)";
        const bg    = `color-mix(in srgb, ${col} 8%, transparent)`;
        const label = isCredit ? `${d.sips}`            : `+${d.sips}`;
        // Static layout via .drinks-entry; dynamic color/border/bg stay inline
        return `<div class="drinks-entry" style="color:${col};border-left:2px solid ${col};background:${bg}">
          <span class="drinks-entry-label">${label}</span>
          <span class="drinks-entry-reason"> ${escapeHtml(d.reason)}</span>
        </div>`;
      }).join("");
  }

  render(state) {
    if (!this.el) return;   // not mounted yet (e.g. referee mode never mounts it)
    const isOver   = state.phase === PHASE.ROUND_OVER;
    const panel    = this.el.querySelector("#dig-drinks-panel");
    const agg      = this.el.querySelector("#dig-drinks-agg");
    const detail   = this.el.querySelector("#dig-drinks-detail");
    const none     = this.el.querySelector("#dig-drinks-none");
    const progress = this.el.querySelector("#dig-drinks-progress");

    if (isOver) {
      if (progress) progress.style.display = "none";
      // Always include all players; ensure dealer card shows even with 0 sips
      const allPlayers = [...new Set([...(state.players || []),
                                      ...(state.dealer ? [state.dealer] : [])])];

      if (panel) panel.style.display = "flex";
      if (none)  none.style.display  = "none";

      // Round notices (e.g. "Hard Switch triggered — A♣ protects X from drinking")
      const noticesEl = this.el.querySelector("#dig-round-notices");
      if (noticesEl) {
        const notices = state.round_notices || [];
        noticesEl.innerHTML = notices.map(n =>
          `<div class="round-notice">${escapeHtml(n)}</div>`
        ).join("");
        noticesEl.style.display = notices.length ? "block" : "none";
      }

      // LEFT: 2-col grid of tappable player cards
      if (agg) {
        agg.innerHTML = allPlayers.map(name => {
          const sips       = DrinkUI.lastRoundSips[name] || 0;
          const hot        = sips > 0;
          const isSelected = DrinkUI.drinksPaneSelected === name;
          const color      = hot ? "var(--red)" : "var(--green)";
          const bg         = `color-mix(in srgb, ${color} ${hot ? 18 : 14}%, transparent)`;
          const border     = `color-mix(in srgb, ${color} 40%, transparent)`;
          // Treat missing prev as 0 when at least one round has completed —
          // absent from DrinkUI.prevRoundSips means the player had 0 sips that round.
          const hasPrev = (state.round || 0) > 1;
          const prev    = hasPrev ? (DrinkUI.prevRoundSips[name] || 0) : null;
          const diff    = hasPrev ? sips - prev : 0;
          const diffColor = diff > 0 ? "var(--red)" : "var(--green)";
          const diffStr = hasPrev
            ? `<div class="dc-diff" style="color:${diff === 0 ? "var(--muted)" : diffColor}">
                 ${diff > 0 ? "▲" : diff < 0 ? "▼" : "="}&thinsp;${Math.abs(diff)} prev
               </div>`
            : "";
          // Static layout on .drinks-card (utilities.css); dynamic bg/border stay
          // inline. No onclick= here -- mount()'s delegated listener handles taps.
          return `<button class="drinks-card${isSelected ? " selected" : ""}" data-name="${escapeHtml(name)}"
            style="background:${bg};border:1.5px solid ${border}">
            <div class="dc-name">${escapeHtml(name)}</div>
            <div class="dc-count" style="color:${color}">${sips}</div>
            <div class="dc-unit" style="color:${color}">sip${sips !== 1 ? "s" : ""}</div>
            ${diffStr}
          </button>`;
        }).join("");
      }

      // RIGHT: detail for selected player (or prompt if none selected)
      this._renderDetail();

    } else {
      // Mid-round: waiting for turn or finished, not yet round-over
      DrinkUI.drinksPaneSelected = null;
      if (panel)    panel.style.display    = "none";
      if (none)     none.style.display     = "none";
      if (agg)      agg.innerHTML          = "";
      if (detail)   detail.innerHTML       = "";
      const noticesEl2 = this.el.querySelector("#dig-round-notices");
      if (noticesEl2) { noticesEl2.innerHTML = ""; noticesEl2.style.display = "none"; }
      if (progress) {
        const mySeats    = (myNames || []);
        const anyDone    = mySeats.some(n => {
          const seat = (state.table || []).find(p => p.name.toLowerCase() === n.toLowerCase());
          return seat && seat.done;
        });
        const anyPlaying = mySeats.some(n => {
          const seat = (state.table || []).find(p => p.name.toLowerCase() === n.toLowerCase());
          return seat && seat.hands && seat.hands.length > 0;
        });
        if (anyDone) {
          progress.textContent = "✋ You're done — waiting for results…";
        } else if (anyPlaying) {
          progress.textContent = "⏳ Waiting for your turn…";
        } else {
          progress.textContent = "⏳ Waiting for round to start…";
        }
        progress.style.display = "block";
      }
    }

    // Peeked card — sync across state polls; button label reflects toggle state
    const peekBtn = this.el.querySelector("#btn-peek");
    const peeked  = state.peeked_card;
    if (peeked) {
      showPeekedCard(peeked);
      if (peekBtn) peekBtn.textContent = "🃏 Hide next card";
    } else {
      clearPeekedCard();
      if (peekBtn) peekBtn.textContent = "🃏 Next card?";
    }
  }
}

const drinksPanel = new DrinksPanel();

function autoSwitchDigTab(state) {
  const phase     = state.phase;
  const prevPhase = lastState ? lastState.phase : null;
  // Always unlock the Play tab outside of playing phase
  if (phase !== PHASE.PLAYING) {
    const playTabBtn = document.querySelector("#dig-tabs .tab[data-args*='dig-play']");
    if (playTabBtn) { playTabBtn.disabled = false; playTabBtn.style.opacity = ""; playTabBtn.style.pointerEvents = ""; }
  }

  if (phase === PHASE.PRE_DEAL) {
    // Only snap to Play tab on the transition into pre-deal, not on every poll —
    // otherwise players get jerked back whenever they browse tabs while waiting
    // for the new dealer to deal.
    if (prevPhase !== PHASE.PRE_DEAL) {
      activateDigTab("dig-play");
    }
  } else if (phase === PHASE.PLAYING) {
    if (!isMyDealerClient && myNames.length > 0) {
      const allDone = myNames.every(n => {
        const seat = (state.table || []).find(p => p.name.toLowerCase() === n.toLowerCase());
        return seat && seat.done;
      });
      const currentTurn  = (state.current_turn || "").toLowerCase();
      const isMyTurn     = myNames.some(n => n.toLowerCase() === currentTurn);
      const isMultiSeat  = myNames.length > 1;

      // Lock the Play tab button for single-seat players when it's not their turn
      const playTabBtn = document.querySelector("#dig-tabs .tab[data-args*='dig-play']");
      if (playTabBtn) {
        const lock = !isMyTurn && !isMultiSeat;
        playTabBtn.disabled = lock;
        playTabBtn.style.opacity = lock ? "0.35" : "";
        playTabBtn.style.pointerEvents = lock ? "none" : "";
      }

      if (allDone) {
        activateDigTab("dig-round");   // hands done → always go to Drinks
      } else if (!isMyTurn && !isMultiSeat) {
        activateDigTab("dig-round");   // single-seat, not your turn → Drinks
      } else {
        activateDigTab("dig-play");    // your turn, or multi-seat managing seats
      }
    } else {
      // Dealer / unregistered — unlock Play tab and stay on it
      const playTabBtn = document.querySelector("#dig-tabs .tab[data-args*='dig-play']");
      if (playTabBtn) { playTabBtn.disabled = false; playTabBtn.style.opacity = ""; playTabBtn.style.pointerEvents = ""; }
      activateDigTab("dig-play");
    }
  } else if (phase === PHASE.ROUND_OVER) {
    activateDigTab("dig-round");
  }
}

function activateDigTab(name) {
  document.querySelectorAll("#dig-tabs .tab").forEach(t => {
    const args = t.getAttribute("data-args") || t.getAttribute("onclick") || "";
    t.classList.toggle("active", args.includes(`"${name}"`) || args.includes(`'${name}'`));
  });
  document.querySelectorAll("#dig-panel .pane").forEach(p => p.classList.remove("active"))
  const pane = document.getElementById("pane-" + name);
  if (pane) pane.classList.add("active");
}
