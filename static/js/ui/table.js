// ============================================================
// GAME UI CONSTRUCTION
// ============================================================
function buildGameUI() {
  const isDigital = gameMode === "digital";

  document.getElementById("ref-panel").style.display = isDigital ? "none"  : "block";
  document.getElementById("dig-panel").style.display = isDigital ? "block" : "none";

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

// includeDealer: referee needs "Dealer" in player lists; digital play does not
function buildPlayerButtons(containerId, pane, includeDealer) {
  const c = document.getElementById(containerId);
  c.innerHTML = "";
  let list = includeDealer ? [...players, "Dealer"] : players;
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
  if (playerName === "Dealer") return 1;
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

  const pToken = (player === "Dealer") ? "dealer" : player;
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
  sendCmd(player === "Dealer"
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
  // Non-dealer player: pre-select their intended action instead of executing
  if (!isMyDealerClient && myRole === "player" && myName) {
    // Only allow voting when it is actually the player's own turn
    if (!lastState || lastState.phase !== "playing" ||
        !lastState.current_turn ||
        lastState.current_turn.toLowerCase() !== myName.toLowerCase()) {
      return;  // not your turn — ignore the tap
    }
    const hand = sel.digital.hand || "hand1";

    // Immediate optimistic feedback — highlight button + update vote display NOW
    // (will be confirmed/corrected once the server responds)
    const ACT_LBL = { hit: "HIT", stand: "STAND", double: "DOUBLE", split: "SPLIT" };
    document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => b.classList.remove("voted"));
    document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => {
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
      document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => b.classList.remove("voted"));
      if (vd) { vd.textContent = `Vote failed: ${data.error || "not registered"}`; vd.style.display = "block"; }
    }
  } catch (_) {
    document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => b.classList.remove("voted"));
    if (vd) { vd.textContent = "Vote failed: network error"; vd.style.display = "block"; }
  }
}

// ============================================================
// SEND COMMAND
// ============================================================
async function sendCmd(cmd) {
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
  if (state.my_role !== undefined) {
    if (state.my_role !== null) {
      myRole           = state.my_role;
      myName           = state.my_name   || null;
      isMyDealerClient = state.is_dealer_client || false;
    } else if (!myRole) {
      myRole           = null;
      myName           = null;
      isMyDealerClient = false;
    }
  }
  // Show toast when dealer role is newly rotated to this client (skip initial load)
  if (lastState !== null && !_prevDealer && isMyDealerClient) showDealerToast();

  // Detect a fresh deal: previous state had no cards, new state has cards.
  const prevPhase = lastState ? lastState.phase : null;
  const isDeal = (
    gameMode === "digital" &&
    prevPhase === "pre-deal" &&
    state.phase === "playing" &&
    _animToggleOn()
  );

  // Update last-round and prev-round sips/drinks whenever the server provides them.
  if (state.last_round_sips && Object.keys(state.last_round_sips).length) {
    _lastRoundSips = state.last_round_sips;
  }
  if (state.last_round_drinks && state.last_round_drinks.length) {
    _lastRoundDrinks = state.last_round_drinks;
  }
  if (state.prev_round_sips !== undefined) _prevRoundSips  = state.prev_round_sips  || {};
  if (state.prev_round_drinks !== undefined) _prevRoundDrinks = state.prev_round_drinks || [];

  // Player drink toast — fires once on round-over transition for registered players
  if (prevPhase !== "round-over" && state.phase === "round-over" && myName && myRole !== "spectator") {
    showPlayerDrinkToast(_lastRoundSips[myName] || 0);
  }
  // Switch toast — fires on round-over with hard/soft switch (visible to all)
  if (prevPhase !== "round-over" && state.phase === "round-over" && state.switch_this_round) {
    showSwitchToast(state.switch_this_round, state.dealer || "Dealer");
  }
  // Bust vote toast — fires on round-over when votes were cast (visible to all)
  if (prevPhase !== "round-over" && state.phase === "round-over" && state.bust_vote_result) {
    showBustVoteToast(state.bust_vote_result);
  }

  lastState   = state;
  currentTurn = state.current_turn || null;
  syncLogFromState(state);   // shared log — all players see same entries
  updateSipTicker(state);    // header strip

  // Keep queued-settings banner in sync while settings modal is open
  const kickOv = document.getElementById("kick-overlay");
  if (kickOv && kickOv.style.display === "flex" && state.queued_settings) {
    _renderQueuedBanner(state.queued_settings);
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

  document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => {
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
  document.querySelectorAll("#dig-action-row1 .btn.best, #dig-action-row2 .btn.best").forEach(b => b.classList.remove("best"));
  if (!state || state.phase !== "playing" || !state.best_play) return;
  const label = BS_LABEL[state.best_play];
  if (!label) return;
  // Find the matching action button and highlight it
  document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => {
    if (b.textContent.trim() === label) b.classList.add("best");
  });
}

// ── Drinks pane: player card selection ──────────────────────────────────────
function selectDrinksPlayer(name) {
  // Toggle: tap same card again to deselect
  _drinksPaneSelected = (_drinksPaneSelected === name) ? null : name;
  renderDrinksDetail();
  // Re-highlight cards
  document.querySelectorAll(".drinks-card").forEach(el => {
    el.style.outline = el.dataset.name === _drinksPaneSelected
      ? "2px solid var(--accent)" : "none";
  });
}

function renderDrinksDetail() {
  const detail = document.getElementById("dig-drinks-detail");
  if (!detail) return;
  if (!_drinksPaneSelected) {
    detail.innerHTML = `<div style="color:var(--muted);font-size:12px;text-align:center;
      padding:20px 8px;opacity:.55;line-height:1.5">← tap a name<br>to see details</div>`;
    return;
  }
  const entries = _lastRoundDrinks.filter(d => d.name === _drinksPaneSelected);
  const total   = _lastRoundSips[_drinksPaneSelected] || 0;
  if (!entries.length) {
    detail.innerHTML = `<div style="color:var(--green);font-size:12px;text-align:center;padding:10px 4px">
      ${escapeHtml(_drinksPaneSelected)} — no drinks 🎉</div>`;
    return;
  }
  detail.innerHTML =
    `<div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;
                 letter-spacing:.5px;margin-bottom:5px">${escapeHtml(_drinksPaneSelected)} · ${total} sip${total !== 1 ? "s" : ""}</div>` +
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
        const sips       = _lastRoundSips[name] || 0;
        const hot        = sips > 0;
        const isSelected = _drinksPaneSelected === name;
        const bg         = hot ? "rgba(224,92,92,.18)"  : "rgba(62,207,110,.14)";
        const border     = hot ? "rgba(224,92,92,.4)"   : "rgba(62,207,110,.4)";
        const color      = hot ? "var(--red)"           : "var(--green)";
        const outline    = isSelected ? "outline:2px solid var(--accent);outline-offset:1px;" : "";
        const prev    = _prevRoundSips[name] ?? null;
        const hasPrev = prev !== null;
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
    // Mid-round: player finished their turn, waiting for others
    _drinksPaneSelected = null;
    if (panel)    panel.style.display    = "none";
    if (none)     none.style.display     = "none";
    if (progress) progress.style.display = "block";
    if (agg)      agg.innerHTML          = "";
    if (detail)   detail.innerHTML       = "";
    const noticesEl2 = document.getElementById("dig-round-notices");
    if (noticesEl2) { noticesEl2.innerHTML = ""; noticesEl2.style.display = "none"; }
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
  const phase = state.phase;
  if (phase === "pre-deal") {
    activateDigTab("dig-play");
  } else if (phase === "playing") {
    // Non-dealer: if all my hands are done, move me to Drinks so I'm not staring at buttons
    if (!isMyDealerClient && myName) {
      const me = (state.table || []).find(p => p.name.toLowerCase() === myName.toLowerCase());
      if (me && me.done) {
        activateDigTab("dig-round");
      } else {
        activateDigTab("dig-play");
      }
    } else {
      activateDigTab("dig-play");   // dealer stays on Play to execute turns
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

function updateInsuranceVisibility(state) {
  const row = document.getElementById("dig-insurance-row");
  if (!row) return;
  const upCard = state.dealer_hand && state.dealer_hand.cards && state.dealer_hand.cards[0];
  const dealerShowsAce = upCard && upCard.rank === "A";

  // Only show if the current player's active hand is a blackjack
  let activeHandIsBlackjack = false;
  if (state.phase === "playing" && state.current_turn && myName &&
      state.current_turn.toLowerCase() === myName.toLowerCase()) {
    const me = (state.table || []).find(p => p.name.toLowerCase() === myName.toLowerCase());
    if (me) {
      const activeHand = (me.hands || []).find(h => !h.done);
      if (activeHand) activeHandIsBlackjack = activeHand.blackjack;
    }
  }

  // Hide the individual button when the vote system already has an entry for this hand
  // (the vote panel handles it instead)
  const hasVoteForMyHand = activeHandIsBlackjack && (state.insurance_votes || []).some(v =>
    !v.resolved && v.bj_player.toLowerCase() === (myName || "").toLowerCase()
  );

  row.style.display = (dealerShowsAce && activeHandIsBlackjack && !hasVoteForMyHand) ? "block" : "none";
  renderInsuranceVotePanel(state);
}

function renderInsuranceVotePanel(state) {
  const panel   = document.getElementById("insurance-vote-panel");
  const content = document.getElementById("insurance-vote-content");
  if (!panel || !content) return;

  const openVotes = (state.insurance_votes || []).filter(v => !v.resolved);
  if (!openVotes.length) { panel.style.display = "none"; return; }
  panel.style.display = "block";
  content.innerHTML   = "";

  openVotes.forEach(v => {
    const iAmBJHolder = myName && v.bj_player.toLowerCase() === myName.toLowerCase();
    const myVote      = v.my_vote;   // null = not voted yet, true/false = voted
    const hasVoted    = myVote !== null && myVote !== undefined;

    const div = document.createElement("div");
    div.style.marginBottom = "4px";

    if (iAmBJHolder) {
      const wager2      = (state && state.wager) || 1;
      const myEntry     = (state && state.table || []).find(
        p => p.name.toLowerCase() === v.bj_player.toLowerCase());
      const myBjHand    = myEntry && myEntry.hands[v.hand_idx];
      const mult2       = myBjHand ? bjMultiplier(myBjHand.cards) : 1;
      const norm2       = mult2 * wager2;
      const dbl2        = mult2 * 2 * wager2;
      const sip2        = n => `${n} sip${n !== 1 ? "s" : ""}`;
      div.innerHTML = `<div style="font-size:12px;color:var(--yellow);font-weight:700;margin-bottom:4px">
        ⏳ Insurance vote for your Blackjack (Hand ${v.hand_idx + 1}) in progress…
      </div>
      <div style="font-size:11px;color:var(--muted);line-height:1.6">
        If the group insures and dealer has BJ → you drink ${sip2(norm2)}, they're safe<br>
        If the group insures and dealer has no BJ → they each drink ${sip2(dbl2)}
      </div>`;
    } else if (hasVoted) {
      const voteLabel  = myVote ? "INSURE" : "DECLINE";
      const voteColor  = myVote ? "var(--green)" : "var(--red)";
      const allIn      = (v.votes_cast != null && v.votes_needed != null
                          && v.votes_cast >= v.votes_needed);
      const waitingMsg = allIn
        ? "All votes in — waiting for dealer to reveal"
        : "Waiting for others…";
      div.innerHTML = `<div style="font-size:12px;color:var(--muted)">
        Your vote on ${escapeHtml(v.bj_player)} H${v.hand_idx + 1}:
        <strong style="color:${voteColor}">${voteLabel}</strong> — ${waitingMsg}
      </div>`;
    } else {
      // Use data attributes so player name never appears in an onclick string
      const insureBtn  = document.createElement("button");
      insureBtn.className = "btn green wide";
      insureBtn.textContent = "INSURE";
      insureBtn.dataset.bjPlayer = v.bj_player;
      insureBtn.dataset.handIdx  = v.hand_idx;
      insureBtn.addEventListener("click", function() {
        castInsuranceVote(this.dataset.bjPlayer, parseInt(this.dataset.handIdx), true);
      });
      const declineBtn = document.createElement("button");
      declineBtn.className = "btn red wide";
      declineBtn.textContent = "DECLINE";
      declineBtn.dataset.bjPlayer = v.bj_player;
      declineBtn.dataset.handIdx  = v.hand_idx;
      declineBtn.addEventListener("click", function() {
        castInsuranceVote(this.dataset.bjPlayer, parseInt(this.dataset.handIdx), false);
      });
      const btnRow = document.createElement("div");
      btnRow.className = "btn-row";
      btnRow.style.marginBottom = "0";
      btnRow.appendChild(insureBtn);
      btnRow.appendChild(declineBtn);

      // Compute actual sip counts from card data already in state.table
      const wager       = (state && state.wager) || 1;
      const playerEntry = (state && state.table || []).find(
        p => p.name.toLowerCase() === v.bj_player.toLowerCase());
      const bjHand      = playerEntry && playerEntry.hands[v.hand_idx];
      const mult        = bjHand ? bjMultiplier(bjHand.cards) : 1;
      const normalSips  = mult * wager;
      const doubleSips  = mult * 2 * wager;
      const sip         = n => `${n} sip${n !== 1 ? "s" : ""}`;

      const label = document.createElement("div");
      label.style.cssText = "font-size:12px;color:var(--yellow);font-weight:700;margin-bottom:6px";
      label.textContent = `Insure ${escapeHtml(v.bj_player)}'s Blackjack? (Hand ${v.hand_idx + 1})`;

      const stakes = document.createElement("div");
      stakes.style.cssText = "font-size:11px;color:var(--muted);margin-bottom:8px;line-height:1.6";
      stakes.innerHTML =
        `<span style="color:var(--green)">INSURE + dealer BJ:</span> group safe · ${escapeHtml(v.bj_player)} drinks ${sip(normalSips)}<br>` +
        `<span style="color:var(--red)">INSURE + no dealer BJ:</span> group drinks <strong>${sip(doubleSips)} each</strong><br>` +
        `<span style="color:var(--muted)">DECLINE:</span> normal BJ bonus of ${sip(normalSips)} each &nbsp;·&nbsp; tie or no vote = decline`;

      div.appendChild(label);
      div.appendChild(stakes);
      div.appendChild(btnRow);
    }
    content.appendChild(div);
  });
}

async function castInsuranceVote(bjPlayer, handIdx, vote) {
  try {
    const res  = await fetch("/vote_insurance", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        bj_player: bjPlayer, hand_idx: handIdx, vote,
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    else appendLog(`  Insurance vote failed: ${data.error || "unknown error"}\n`);
  } catch (_) {
    appendLog("  Insurance vote failed: network error\n");
  }
}

// ── Milestone: 50-sip handout feature ───────────────────────────────────────

function renderMilestoneState(state) {
  const ms     = state && state.pending_milestone;
  const result = state && state.last_milestone_result;

  // ── Drink notification for recipients (fires once per result) ──────────
  if (result) {
    const rKey = `${result.boundary}:${result.winner}`;
    if (rKey !== _lastMilestoneResultKey) {
      _lastMilestoneResultKey = rKey;
      // Check if I'm a recipient
      if (myName) {
        // allocations keys might be capitalised differently — case-insensitive lookup
        const myEntry = Object.entries(result.allocations || {})
          .find(([n]) => n.toLowerCase() === myName.toLowerCase());
        if (myEntry) {
          const [, sipCount] = myEntry;
          _showDrinkToast(sipCount, result.winner);
        }
      }
    }
  }

  // ── Pending milestone handling ─────────────────────────────────────────
  if (!ms) {
    _hideMilestoneToast();
    _hideWaitingBanner();
    // Close modal if the TTL expired server-side while modal was open
    if (_lastMilestoneKey && document.getElementById("milestone-modal-overlay").classList.contains("open")) {
      _closeMilestoneModal();
    }
    return;
  }

  const key       = `${ms.boundary}:${ms.winner}`;
  const iAmWinner = !!ms.i_am_winner;  // server-authoritative; no JS name-matching needed

  // Show announcement toast exactly once per new milestone (all players)
  if (key !== _lastMilestoneKey) {
    _lastMilestoneKey     = key;
    _milestoneAllocations = {};
    _showMilestoneToast(ms);
  }

  if (iAmWinner) {
    _hideWaitingBanner();
    // Open the handout modal exactly once for this milestone
    if (_milestoneModalOpened !== key) {
      _milestoneModalOpened = key;
      // Short delay so the toast is visible before modal covers it
      setTimeout(() => _openMilestoneModal(ms, state), 600);
    } else {
      // Modal already open — just keep the timer in sync
      _updateMilestoneTimer(ms.seconds_left);
    }
  } else {
    // Non-winners: persistent waiting banner with live countdown
    _showWaitingBanner(ms);
  }
}

function _showMilestoneToast(ms) {
  const toast = document.getElementById("milestone-toast");
  if (!toast) return;
  toast.innerHTML = `🎉 ${escapeHtml(ms.winner)} hit ${ms.boundary} sips!`;
  toast.classList.remove("show");
  // Force reflow so animation restarts cleanly
  void toast.offsetWidth;
  toast.classList.add("show");
  // Auto-hide after 5 seconds
  setTimeout(() => _hideMilestoneToast(), 5000);
}

function _hideMilestoneToast() {
  const toast = document.getElementById("milestone-toast");
  if (toast) toast.classList.remove("show");
}

function _showWaitingBanner(ms) {
  // In-flow slot (digital mode — sits exactly above the tab bar)
  const slot = document.getElementById("ms-waiting-slot");
  const s    = ms.seconds_left;
  const timerStr = s > 0 ? ` · ⏱ ${s}s` : "";
  const html = `🎉 <strong>${escapeHtml(ms.winner)}</strong> is handing out ${ms.handout} milestone sips…${timerStr}`;
  if (slot) {
    slot.innerHTML     = html;
    slot.style.display = "block";
  }
  // Fallback fixed banner (referee mode / any other context)
  const fixed = document.getElementById("ms-waiting-banner");
  if (fixed && !slot) {
    fixed.innerHTML = html;
    fixed.classList.add("show");
  }
}

function _hideWaitingBanner() {
  const slot = document.getElementById("ms-waiting-slot");
  if (slot) slot.style.display = "none";
  const fixed = document.getElementById("ms-waiting-banner");
  if (fixed) fixed.classList.remove("show");
}

function _showDrinkToast(sips, winner) {
  const toast = document.getElementById("ms-drink-toast");
  if (!toast) return;
  const sipWord = sips === 1 ? "sip" : "sips";
  toast.innerHTML = `🍺 Drink ${sips} ${sipWord}!<br><span style="font-size:11px;font-weight:500;opacity:.8">${escapeHtml(winner)}'s milestone handout</span>`;
  toast.classList.remove("show");
  void toast.offsetWidth;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 8000);
}

function _openMilestoneModal(ms, state) {
  const overlay = document.getElementById("milestone-modal-overlay");
  if (!overlay) return;

  const title = document.getElementById("milestone-modal-title");
  const sub   = document.getElementById("milestone-modal-sub");
  if (title) title.textContent = `You hit ${ms.boundary} sips first! 🏆`;
  if (sub)   sub.textContent   = `Hand out ${ms.handout} sips — split however you like (not yourself).`;

  // Build stepper list from current players except self
  const players = (lastState && lastState.players || []).filter(
    n => n.toLowerCase() !== (myName || "").toLowerCase()
  );
  // Initialize allocations to 0 for everyone
  players.forEach(n => { if (!(_milestoneAllocations[n] >= 0)) _milestoneAllocations[n] = 0; });

  _renderMilestoneSteppers(players, ms.handout);
  _updateMilestoneTimer(ms.seconds_left);
  overlay.classList.add("open");
}

function _closeMilestoneModal() {
  const overlay = document.getElementById("milestone-modal-overlay");
  if (overlay) overlay.classList.remove("open");
  if (_milestoneTimerID) { clearInterval(_milestoneTimerID); _milestoneTimerID = null; }
}

function _renderMilestoneSteppers(players, total) {
  const container = document.getElementById("milestone-steppers");
  if (!container) return;
  container.innerHTML = "";
  players.forEach(name => {
    const row = document.createElement("div");
    row.className = "ms-stepper";
    const val = _milestoneAllocations[name] || 0;
    row.innerHTML = `
      <span class="ms-name">${escapeHtml(name)}</span>
      <button onclick="milestoneAdjust('${escapeHtml(name)}', -1)">−</button>
      <span class="ms-count" id="ms-count-${escapeHtml(name)}">${val}</span>
      <button onclick="milestoneAdjust('${escapeHtml(name)}', +1)">+</button>`;
    container.appendChild(row);
  });
  _updateMilestoneRemaining(total);
}

function milestoneAdjust(name, delta) {
  const ms = lastState && lastState.pending_milestone;
  const total = ms ? ms.handout : 5;
  const cur   = _milestoneAllocations[name] || 0;
  const used  = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  const newVal = Math.max(0, Math.min(cur + delta, cur + (total - used) + (delta < 0 ? 0 : 0)));

  if (delta > 0 && used >= total) return;  // budget exhausted

  _milestoneAllocations[name] = Math.max(0, cur + delta);
  const el = document.getElementById(`ms-count-${name}`);
  if (el) el.textContent = _milestoneAllocations[name];
  _updateMilestoneRemaining(total);
}

function _updateMilestoneRemaining(total) {
  const used = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  const left = total - used;
  const rem  = document.getElementById("milestone-remaining");
  const btn  = document.getElementById("milestone-submit-btn");
  if (rem) {
    rem.textContent = left === 0 ? "✓ All sips assigned" : `${left} sip${left !== 1 ? "s" : ""} left to assign`;
    rem.style.color = left === 0 ? "var(--green)" : "var(--yellow)";
  }
  if (btn) btn.disabled = (left !== 0);
}

function _updateMilestoneTimer(secondsLeft) {
  const timerEl = document.getElementById("milestone-timer");
  if (!timerEl) return;
  if (secondsLeft == null) return;
  const s = Math.max(0, secondsLeft);
  timerEl.textContent = s > 0 ? `⏱ ${s}s remaining` : "⏱ Time's up!";
  timerEl.style.color = s <= 10 ? "var(--red)" : "var(--muted)";
}

async function submitMilestoneHandout() {
  const ms = lastState && lastState.pending_milestone;
  if (!ms) return;
  const used = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  if (used !== ms.handout) return;  // shouldn't happen (button is disabled), but guard anyway

  const btn = document.getElementById("milestone-submit-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }

  try {
    const res = await fetch("/claim_milestone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, allocations: _milestoneAllocations }),
    });
    const data = await res.json();
    if (data.ok) {
      _closeMilestoneModal();
      _lastMilestoneKey     = null;
      _milestoneModalOpened = null;
      applyState(data);
    } else {
      alert(data.error || "Could not claim milestone.");
      if (btn) { btn.disabled = false; btn.textContent = "Hand out sips"; }
    }
  } catch (_) {
    alert("Network error — try again.");
    if (btn) { btn.disabled = false; btn.textContent = "Hand out sips"; }
  }
}

function cardEl(card) {
  const div = document.createElement("div");
  div.className = "card-vis card-el";
  if (!card || card.suit === "hidden" || card.rank === "?") {
    div.classList.add("hidden");
    div.innerHTML = `<div class="top">?</div><div class="mid">★</div><div class="bot">?</div>`;
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
    hdr.innerHTML = `<div class="seat-name">${escapeHtml(s.name)}${role}${botTag}</div><div style="display:flex;align-items:center;gap:6px">${sipBadge}${tag}</div>`;
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
  document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn").forEach(b => {
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
