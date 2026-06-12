// ============================================================
// GAME UI CONSTRUCTION
// ============================================================
function buildGameUI() {
  const isDigital = gameMode === "digital";

  document.getElementById("ref-panel").style.display = isDigital ? "none"  : "block";
  document.getElementById("dig-panel").style.display = isDigital ? "block" : "none";

  initLogCollapse();

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
  if (pane === "digital" && lastState && lastState.phase === "playing" && lastState.current_turn) {
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
  if (!isMyDealerClient && (myRole === "player" || myRole === "admin") && (myActiveName || myName)) {
    // Only allow voting when it is actually the player's own turn
    if (!lastState || lastState.phase !== "playing" ||
        !lastState.current_turn ||
        lastState.current_turn.toLowerCase() !== (myActiveName || myName || "").toLowerCase()) {
      return;  // not your turn — ignore the tap
    }
    const hand = sel.digital.hand || "hand1";

    // Immediate optimistic feedback — highlight button + update vote display NOW
    // (will be confirmed/corrected once the server responds)
    const ACT_LBL = { hit: "HIT", stand: "STAND", double: "DOUBLE", split: "SPLIT" };
    digActionButtons().forEach(b => b.classList.remove("voted"));
    digActionButtons().forEach(b => {
      if (b.textContent.trim() === (ACT_LBL[action] || action.toUpperCase()))
        b.classList.add("voted");
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
  if (lastState && lastState.phase === "playing" && lastState.current_turn &&
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
    _requestsInFlight--;
  }
}

// ============================================================
// SEND COMMAND
// ============================================================
async function sendCmd(cmd) {
  if (_requestsInFlight > 0) return;
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
  } finally {
    _requestsInFlight--;
    document.querySelectorAll(".cmd-pending").forEach(b => b.classList.remove("cmd-pending"));
  }
}

// ============================================================
// SHARED LOG SYNC
// ============================================================
function syncLogFromState(state) {
  if (state.log_version === undefined) return;
  const ver     = state.log_version || 0;
  const entries = state.log_entries  || [];

  // Version bump = new game or new round — clear the local log
  if (ver !== logVersion) {
    logVersion = ver;
    logCount   = 0;
    document.getElementById("log").innerHTML = "";
  }

  // Append only the entries we haven't seen yet
  for (let i = logCount; i < entries.length; i++) {
    appendLog(entries[i]);
  }
  logCount = entries.length;
}

// ============================================================
// VISIBLE TABLE + TURN ENFORCEMENT
// ============================================================
const SUIT_SYMBOL = { hearts: "♥", diamonds: "♦", clubs: "♣", spades: "♠" };
const SUIT_RED    = { hearts: true, diamonds: true };

function applyState(state) {
  if (!state || !state.ok) return;

  // Toggle a body-level class so all drink/sip-related UI (sip ticker, drinks
  // panel/tab, last-round button & modal, milestone toasts, leaderboard sip
  // columns, drinking trivia, etc.) can be hidden purely via CSS in Normal
  // mode. Defaults to drinking ON unless the server explicitly says otherwise.
  const drinkingOn = state.drinking_mode !== false;
  document.body.classList.toggle("no-drinking", !drinkingOn);
  const drinksTab = document.getElementById("dig-drinks-tab");
  if (drinksTab) drinksTab.textContent = drinkingOn ? "🍺 Drinks" : "🃏 Round";

  // Drop stale responses — if the server sent a state_seq and it's older than
  // what we already applied, discard silently. Prevents a slow poll from
  // overwriting a fresher command/preselect/vote response.
  if (state.state_seq !== undefined &&
      lastState && lastState.state_seq !== undefined &&
      state.state_seq < lastState.state_seq) {
    return;
  }

  // Handle kicked status first
  if (state.my_role === "kicked") {
    // If the user already acknowledged and chose to spectate, skip the popup
    if (myRole === "spectator") return;
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
      document.getElementById("log").innerHTML = "";
      document.getElementById("header-room").textContent = "";
      hideLobbyMsg();
      players  = [];
      gameMode = "referee";
    } else {
      // Register as spectator server-side so server stops returning "kicked"
      doSpectate();
    }
    return;
  }

  // Update client identity from server.
  // Only downgrade to null if we have no role yet — prevents a stale poll from
  // clearing a valid role that was just set by a fresh /register response.
  const _prevDealer = isMyDealerClient;
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
  // Use dealer name change rather than isMyDealerClient, since admin always
  // has isMyDealerClient=true regardless of who the actual dealer is.
  const newDealerName = state.dealer || "";
  const iAmDealer = myNames.some(n => n.toLowerCase() === newDealerName.toLowerCase());
  const wasDealer = myNames.some(n => n.toLowerCase() === _prevDealerName.toLowerCase());
  if (lastState !== null && iAmDealer && !wasDealer) showDealerToast();

  // Detect a fresh deal: previous state had no cards, new state has cards.
  const prevPhase = lastState ? lastState.phase : null;
  const isDeal = (
    gameMode === "digital" &&
    prevPhase === "pre-deal" &&
    state.phase === "playing" &&
    _animToggleOn()
  );

  // Keep npcPlayers in sync so bust-vote modal shows correct vote cards after
  // a player is converted from bot to human (or vice versa) mid-session.
  if (state.table) {
    npcPlayers = new Set(state.table.filter(p => p.is_npc).map(p => p.name));
  }

  // Reset idle timer on any game state change — if the round or phase advanced,
  // someone is actively playing and the dyno is clearly not idle.
  if (typeof resetIdleTimer === "function") {
    const prevRound = lastState ? (lastState.round || 0) : 0;
    if (state.phase !== prevPhase || (state.round || 0) > prevRound) {
      resetIdleTimer();
    }
  }

  // Always sync last/prev round data from server so both variables stay in lockstep.
  // Do NOT gate DrinkUI.lastRoundSips on being non-empty — that desynchronises it from
  // DrinkUI.prevRoundSips and makes the diff compare different rounds.
  if (state.last_round_sips !== undefined)  DrinkUI.lastRoundSips  = state.last_round_sips  || {};
  if (state.last_round_drinks !== undefined) DrinkUI.lastRoundDrinks = state.last_round_drinks || [];
  if (state.prev_round_sips !== undefined)  DrinkUI.prevRoundSips  = state.prev_round_sips  || {};
  if (state.prev_round_drinks !== undefined) DrinkUI.prevRoundDrinks = state.prev_round_drinks || [];

  // One-shot round-end effects — all gated on round_over_seq so a duplicate
  // or late poll (backgrounded tab, slow network) can never re-fire them.
  // prevPhase checks were unreliable: if lastState was stale when applyState
  // ran, prevPhase could be wrong and toasts would fire twice or not at all.
  const newRoundOverSeq = state.round_over_seq || 0;
  const isNewRoundOver  = newRoundOverSeq > DrinkUI.lastRoundOverSeq;
  if (isNewRoundOver) {
    // Player drink toast (registered non-spectators only)
    if (drinkingOn && myNames.length > 0 && myRole !== "spectator") {
      myNames.forEach(n => showPlayerDrinkToast(DrinkUI.lastRoundSips[n] || 0, n));
    }
    // Switch toast — hard/soft dealer switch (visible to all)
    if (state.switch_this_round) {
      showSwitchToast(state.switch_this_round, state.dealer || "Dealer");
    }
    // Bust vote result toast (visible to all)
    if (state.bust_vote_result) {
      showBustVoteToast(state.bust_vote_result);
    }
    // Insurance result toast (visible to all)
    if (state.insurance_result && state.insurance_result.length) {
      showInsuranceToast(state.insurance_result);
    }
  }
  DrinkUI.lastRoundOverSeq = Math.max(DrinkUI.lastRoundOverSeq, newRoundOverSeq);

  // Detect bust vote window closing — flush any toasts that were queued during it.
  const _prevBustOpen = lastState && lastState.bust_vote_window_open;
  lastState   = state;
  currentTurn = state.current_turn || null;
  if (_prevBustOpen && !state.bust_vote_window_open && typeof flushToastQueue === "function") {
    flushToastQueue();
  }
  // Auto-switch active seat when turn moves to another local player
  if (currentTurn && myNames.length > 1) {
    const turnLow = currentTurn.toLowerCase();
    const match   = myNames.find(n => n.toLowerCase() === turnLow);
    if (match) myActiveName = match;
  }
  syncLogFromState(state);   // shared log — all players see same entries
  updateSipTicker(state);    // header strip
  if (drinkingOn) processAceDrinkEvents(state);  // mid-round ace drink toasts
  if (drinkingOn) updateHonorPrompt(state);      // mandatory split-10s house-rule prompt
  updateKpiPanel(state);     // leaderboard + future KPI panes

  // Keep settings modal in sync while it's open
  const kickOv = document.getElementById("kick-overlay");
  if (kickOv && kickOv.style.display === "flex") {
    if (state.queued_settings) _renderQueuedBanner(state.queued_settings);
    // Refresh pending / denied registration sections on every poll
    if (myRole === "admin") openKickModal();
  }

  // Settings button — visible to all registered players (both header and bottom-nav copies)
  const showSettings = (myRole === "admin" || myRole === "player") ? "block" : "none";
  const adminBtn = document.getElementById("btn-admin-players");
  if (adminBtn) adminBtn.style.display = showSettings;
  const adminNav = document.getElementById("btn-admin-nav");
  if (adminNav) adminNav.style.display = showSettings;

  // Apply admin's animation default for first-time joiners who have no local preference
  if (state.anim_default !== undefined && lsGet("bjDealAnim") === null) {
    setAnimToggle(state.anim_default);
  }

  // Registration overlay — show when not yet registered
  updateRegisterOverlay(state);

  // Kick vote banner
  renderKickVoteBanner(state);

  // Spectator rejoin banner (shown to clients who were kicked and chose to spectate)
  const rejoinBanner = document.getElementById("spectator-rejoin-banner");
  const rejoinBtn    = document.getElementById("rejoin-req-btn");
  if (rejoinBanner) {
    if (myRole === "spectator" && state.my_name === null) {
      rejoinBanner.style.display = "flex";
      if (rejoinBtn) rejoinBtn.disabled = !!state.my_rejoin_pending;
      if (rejoinBtn) rejoinBtn.textContent = state.my_rejoin_pending ? "Request sent ✓" : "Request to rejoin";
    } else {
      rejoinBanner.style.display = "none";
    }
  }

  if (gameMode === "digital") {
    autoSwitchDigTab(state);
    updateInsuranceVisibility(state);
    updateHandLocks(state);
    updateRoundPane(state);
    updateBestPlay(state);
    updateBustVoteUI(state);
  }

  if (isDeal) {
    // animateDeal renders state itself card-by-card — don't render twice.
    // _dealAnimating flag prevents polls from overwriting cards mid-animation.
    animateDeal(state);
  } else if (_dealAnimating) {
    // Animation is in progress — skip render to avoid interrupting it.
    // (applyState still ran above for log, ticker, buttons, etc.)
  } else {
    renderDealer(state);
    renderPlayers(state);
    syncAllHandButtons();
    applyTurnGate(state);
    if (gameMode === "digital") {
      // Must run AFTER applyTurnGate — both set disabled on action buttons,
      // and these two have final say (vote lock, hand validity).
      updateActionButtons(state);  // disable SPLIT/DOUBLE when not valid
      updateRoleUI(state);         // role hint, vote lock, inactive-player gate
    }
  }

  renderMilestoneState(state);
}

// Disable SPLIT when the active hand can't be split (limit reached or cards don't match).
// Disable DOUBLE when the hand already has more than 2 cards or is already doubled.
function updateActionButtons(state) {
  if (!state || state.phase !== "playing" || !state.current_turn) return;
  const seat = (state.table || []).find(s => s.name === state.current_turn);
  if (!seat) return;
  const activeHand = (seat.hands || []).find(h => !h.done);
  if (!activeHand) return;

  const canDouble = (activeHand.cards || []).length === 2 && !activeHand.doubled;

  digActionButtons().forEach(b => {
    const lbl = b.textContent.trim();
    if (lbl === "SPLIT")  b.classList.toggle("disabled", !activeHand.can_split);
    if (lbl === "DOUBLE") b.classList.toggle("disabled", !canDouble);
  });
}

function updateHandLocks(state) {
  if (!state || state.phase !== "playing") return;
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

// Map backend action codes to the button label text in the Play pane
const BS_LABEL = { h: "HIT", s: "STAND", d: "DOUBLE", sp: "SPLIT" };

function updateBestPlay(state) {
  // Clear any previous highlight
  digActionButtons().forEach(b => b.classList.remove("best"));
  if (!state || state.phase !== "playing" || !state.best_play) return;
  const label = BS_LABEL[state.best_play];
  if (!label) return;
  // Find the matching action button and highlight it
  digActionButtons().forEach(b => {
    if (b.textContent.trim() === label) b.classList.add("best");
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
  const canAct   = role === "admin" || role === "player";
  overlay.querySelectorAll("#honor-split-modal .btn-row button").forEach(btn => {
    btn.disabled = !canAct;
  });
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
  } finally {
    _requestsInFlight--;
  }
}
window.honorResolve = honorResolve;

// ── Drinks pane: player card selection ──────────────────────────────────────
function selectDrinksPlayer(name) {
  // Toggle: tap same card again to deselect
  DrinkUI.drinksPaneSelected = (DrinkUI.drinksPaneSelected === name) ? null : name;
  renderDrinksDetail();
  // Re-highlight cards
  document.querySelectorAll(".drinks-card").forEach(el => {
    el.style.outline = el.dataset.name === DrinkUI.drinksPaneSelected
      ? "2px solid var(--accent)" : "none";
  });
}

function renderDrinksDetail() {
  const detail = document.getElementById("dig-drinks-detail");
  if (!detail) return;
  if (!DrinkUI.drinksPaneSelected) {
    detail.innerHTML = `<div style="color:var(--muted);font-size:12px;text-align:center;
      padding:20px 8px;opacity:.55;line-height:1.5">← tap a name<br>to see details</div>`;
    return;
  }
  const entries = DrinkUI.lastRoundDrinks.filter(d => d.name === DrinkUI.drinksPaneSelected);
  const total   = DrinkUI.lastRoundSips[DrinkUI.drinksPaneSelected] || 0;
  if (!entries.length) {
    detail.innerHTML = `<div style="color:var(--green);font-size:12px;text-align:center;padding:10px 4px">
      ${escapeHtml(DrinkUI.drinksPaneSelected)} — no drinks 🎉</div>`;
    return;
  }
  detail.innerHTML =
    `<div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;
                 letter-spacing:.5px;margin-bottom:5px">${escapeHtml(DrinkUI.drinksPaneSelected)} · ${total} sip${total !== 1 ? "s" : ""}</div>` +
    entries.map(d => {
      const isCredit = d.sips < 0;
      const col   = isCredit ? "var(--green)"              : "var(--red)";
      const bg    = isCredit ? "rgba(62,207,110,.08)"      : "rgba(224,92,92,.08)";
      const label = isCredit ? `${d.sips}`                 : `+${d.sips}`;
      return `<div style="font-size:11px;line-height:1.45;padding:4px 6px;border-radius:6px;margin-bottom:3px;
                   color:${col};border-left:2px solid ${col};background:${bg}">
        <span style="font-weight:700">${label}</span>
        <span style="color:var(--muted)"> ${escapeHtml(d.reason)}</span>
      </div>`;
    }).join("");
}

function updateRoundPane(state) {
  const isOver   = state.phase === "round-over";
  const panel    = document.getElementById("dig-drinks-panel");
  const agg      = document.getElementById("dig-drinks-agg");
  const detail   = document.getElementById("dig-drinks-detail");
  const none     = document.getElementById("dig-drinks-none");
  const progress = document.getElementById("dig-drinks-progress");

  if (isOver) {
    if (progress) progress.style.display = "none";
    // Always include all players; ensure dealer card shows even with 0 sips
    const allPlayers = [...new Set([...(state.players || []),
                                    ...(state.dealer ? [state.dealer] : [])])];

    if (panel) panel.style.display = "flex";
    if (none)  none.style.display  = "none";

    // Round notices (e.g. "Hard Switch triggered — A♣ protects X from drinking")
    const noticesEl = document.getElementById("dig-round-notices");
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
        const bg         = hot ? "rgba(224,92,92,.18)"  : "rgba(62,207,110,.14)";
        const border     = hot ? "rgba(224,92,92,.4)"   : "rgba(62,207,110,.4)";
        const color      = hot ? "var(--red)"           : "var(--green)";
        const outline    = isSelected ? "outline:2px solid var(--accent);outline-offset:1px;" : "";
        // Treat missing prev as 0 when at least one round has completed —
        // absent from DrinkUI.prevRoundSips means the player had 0 sips that round.
        const hasPrev = (state.round || 0) > 1;
        const prev    = hasPrev ? (DrinkUI.prevRoundSips[name] || 0) : null;
        const diff    = hasPrev ? sips - prev : 0;
        const diffColor = diff > 0 ? "var(--red)" : "var(--green)";
        const diffStr = hasPrev
          ? `<div style="font-size:9px;color:${diff === 0 ? "var(--muted)" : diffColor};line-height:1.3">
               ${diff > 0 ? "▲" : diff < 0 ? "▼" : "="}&thinsp;${Math.abs(diff)} prev
             </div>`
          : "";
        return `<button class="drinks-card" data-name="${escapeHtml(name)}"
          onclick="selectDrinksPlayer(this.dataset.name)"
          style="padding:7px 4px;border-radius:9px;text-align:center;cursor:pointer;
                 background:${bg};border:1.5px solid ${border};${outline}
                 transition:outline .1s;-webkit-tap-highlight-color:transparent">
          <div style="font-size:10px;color:var(--muted);font-weight:700;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                      max-width:100%;padding:0 2px">${escapeHtml(name)}</div>
          <div style="font-size:21px;font-weight:800;line-height:1.2;color:${color}">${sips}</div>
          <div style="font-size:10px;color:${color};opacity:.85">sip${sips !== 1 ? "s" : ""}</div>
          ${diffStr}
        </button>`;
      }).join("");
    }

    // RIGHT: detail for selected player (or prompt if none selected)
    renderDrinksDetail();

  } else {
    // Mid-round: waiting for turn or finished, not yet round-over
    DrinkUI.drinksPaneSelected = null;
    if (panel)    panel.style.display    = "none";
    if (none)     none.style.display     = "none";
    if (agg)      agg.innerHTML          = "";
    if (detail)   detail.innerHTML       = "";
    const noticesEl2 = document.getElementById("dig-round-notices");
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
  const peekBtn = document.getElementById("btn-peek");
  const peeked  = state.peeked_card;
  if (peeked) {
    showPeekedCard(peeked);
    if (peekBtn) peekBtn.textContent = "🃏 Hide next card";
  } else {
    clearPeekedCard();
    if (peekBtn) peekBtn.textContent = "🃏 Next card?";
  }
}

function autoSwitchDigTab(state) {
  const phase     = state.phase;
  const prevPhase = lastState ? lastState.phase : null;
  // Always unlock the Play tab outside of playing phase
  if (phase !== "playing") {
    const playTabBtn = document.querySelector("#dig-tabs .tab[data-args*='dig-play']");
    if (playTabBtn) { playTabBtn.disabled = false; playTabBtn.style.opacity = ""; playTabBtn.style.pointerEvents = ""; }
  }

  if (phase === "pre-deal") {
    // Only snap to Play tab on the transition into pre-deal, not on every poll —
    // otherwise players get jerked back whenever they browse tabs while waiting
    // for the new dealer to deal.
    if (prevPhase !== "pre-deal") {
      activateDigTab("dig-play");
    }
  } else if (phase === "playing") {
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
  } else if (phase === "round-over") {
    activateDigTab("dig-round");
  }
}

function activateDigTab(name) {
  document.querySelectorAll("#dig-tabs .tab").forEach(t => {
    const args = t.getAttribute("data-args") || t.getAttribute("onclick") || "";
    t.classList.toggle("active", args.includes(`"${name}"`) || args.includes(`'${name}'`));
  });
  document.querySelectorAll("#dig-panel .pane").forEach(p => p.classList.remove("active"));
  const pane = document.getElementById(`pane-${name}`);
  if (pane) pane.classList.add("active");
}

