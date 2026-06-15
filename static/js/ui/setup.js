// LAST ROUND DRINK SUMMARY
// ============================================================
// Drink-summary and milestone-toast tracking state, consolidated under one
// namespaced object (was 10 separate module-level globals). Same values,
// same mutation patterns as before — grouping them here just makes it clear
// they all belong to the same feature area (Drinks pane + milestone toasts/
// modal). Referenced from table.js and table-modals.js, both of which load
// after this file.
const DrinkUI = {
  lastRoundSips:      {},   // current completed round — shown in Drinks pane
  lastRoundDrinks:    [],   // detailed drink entries for the Drinks pane
  prevRoundSips:      {},   // round before last — shown in 🍺 header modal
  prevRoundDrinks:    [],   // detailed drink entries for the previous round
  drinksPaneSelected: null, // name of player whose detail is shown in Drinks pane
  lastRoundOverSeq:   0,    // seq-based: fire drink toast whenever this advances
  lastMilestoneKey:       null, // "boundary:winner" — prevents re-showing toast on every poll
  lastMilestoneResultKey: null, // same format — prevents re-showing drink toast on every poll
  milestoneModalOpened:   null, // key for which we already opened the modal (prevents re-open on re-poll)
  milestoneAllocations:   {},   // { playerName: sips } — stepper state in modal
};

function openLastRoundModal() {
  const body = document.getElementById("last-round-modal-body");
  if (!document.getElementById("last-round-overlay") || !body) return;

  const sips     = DrinkUI.lastRoundSips;   // last completed round — the main value
  const prevSips = DrinkUI.prevRoundSips;   // round before that — delta reference only
  const names    = Object.keys(sips);
  if (!names.length) {
    body.innerHTML = `<div style="color:var(--muted);text-align:center;font-size:13px">No previous round yet.</div>`;
  } else {
    // All players in play order, not just those who drank
    const allNames = (lastState && lastState.players) || names;
    const sorted   = allNames.slice().sort((a, b) => (sips[b] || 0) - (sips[a] || 0));
    body.innerHTML = sorted.map(n => {
      const last = sips[n]     || 0;
      const prev = prevSips[n] || 0;
      const diff = last - prev;
      const diffStr = diff === 0 ? "" :
        `<span style="font-size:11px;color:${diff > 0 ? "var(--red)" : "var(--green)"};margin-left:4px">${diff > 0 ? "▲" : "▼"}${Math.abs(diff)}</span>`;
      return `<div class="lrp-row">
        <span>${escapeHtml(n)}</span>
        <span style="display:flex;align-items:center;gap:6px">
          <span class="lrp-sips">${last} sip${last !== 1 ? "s" : ""}</span>
          ${diffStr}
        </span>
      </div>`;
    }).join("");
  }
  openModal("last-round-overlay");
}

function closeLastRoundModal() {
  closeModal("last-round-overlay");
}

// While waiting for the host to start, poll until the game exists.
// Uses self-rescheduling setTimeout (not setInterval) so a slow fetch
// never causes overlapping requests.
function startWaiting() {
  stopPolling();
  const tick = async () => {
    if (!roomCode) { pollTimer = setTimeout(tick, 2000); return; }
    try {
      const url  = `/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
      const res  = await fetch(url);
      const data = await res.json();
      if (data.ok && data.players && data.players.length > 0) {
        stopPolling();
        players  = data.players || [];
        numHands = data.num_hands || 2;
        gameMode = data.mode || "referee";
        updateHeader(data);
        buildGameUI();
        applyState(data);
        appendLog("  (Game started! Joined room " + roomCode + ")\n");
        document.getElementById("waiting").style.display = "none";
        document.getElementById("app").style.display     = "flex";
        startPolling();
        return;  // don't reschedule — startPolling() takes over
      }
    } catch (_) {}
    pollTimer = setTimeout(tick, 2000);
  };
  pollTimer = setTimeout(tick, 2000);
}

// Selections per pane
const sel = {
  deal:    { player: null, hand: "hand1" },
  result:  { player: null, hand: "hand1" },
  action:  { player: null, hand: "hand1" },
  digital: { player: null, hand: "hand1" },
};
let selRank = null;
let selSuit = null;

// ============================================================
// SETUP — mode
// ============================================================
let setupMode     = "digital";   // "referee" | "digital"
let setupDrinking = true;

function setBustVoteSetupToggle(on) {
  // Update ON/OFF labels — CSS sibling selector can't reach through the
  // wrapping <label>, so we mirror the same JS approach as setAnimToggle.
  const off = document.getElementById("bust-vote-lbl-setup");
  const onEl = document.getElementById("bust-vote-lbl-setup-on");
  if (off)  off.style.display  = on ? "none"   : "inline";
  if (onEl) onEl.style.display = on ? "inline" : "none";
}

function setEasyModeSetup(on) {
  const cb    = document.getElementById("easy-mode-setup-toggle");
  const off   = document.getElementById("easy-mode-lbl-setup");
  const onEl  = document.getElementById("easy-mode-lbl-setup-on");
  if (cb)   cb.checked          = on;
  if (off)  off.style.display   = on ? "none"   : "inline";
  if (onEl) onEl.style.display  = on ? "inline" : "none";
}

function setGameType(type, btn) {
  document.querySelectorAll("#gametype-row .btn").forEach(b => b.classList.remove("sel"));
  btn.classList.add("sel");

  const refSettings    = document.getElementById("settings-ref");
  const digSettings    = document.getElementById("settings-dig-wrap");
  const wagerCell      = document.getElementById("wager-dig-cell");
  const easyModeField  = document.getElementById("easy-mode-setup-field");
  const handsDecksRow  = document.getElementById("settings-dig");
  const togglesRow     = document.getElementById("settings-dig-toggles");
  const sub            = document.getElementById("setup-sub");

  // In Normal mode, Sips/hand and Easy Mode are hidden, leaving only 2
  // visible items per row — switch those rows from a 3-col to a true
  // 2-col grid so the remaining items are evenly sized and centered.
  const setRowCols = (row, twoCol) => {
    if (!row) return;
    row.classList.toggle("two-col", twoCol);
    row.classList.toggle("three-col", !twoCol);
  };

  if (type === "drinking-digital") {
    setupMode     = "digital";
    setupDrinking = true;
    refSettings.style.display  = "none";
    digSettings.style.display  = "";
    wagerCell.style.display    = "";
    if (easyModeField) easyModeField.style.display = "";
    setRowCols(handsDecksRow, false);
    setRowCols(togglesRow, false);
    sub.textContent = "Virtual Drinking Blackjack";
  } else if (type === "normal") {
    setupMode     = "digital";
    setupDrinking = false;
    refSettings.style.display  = "none";
    digSettings.style.display  = "";
    wagerCell.style.display    = "none";
    // Easy Mode only applies to drink halving — not relevant for Normal mode
    if (easyModeField) {
      easyModeField.style.display = "none";
      setEasyModeSetup(false);
    }
    setRowCols(handsDecksRow, true);
    setRowCols(togglesRow, true);
    sub.textContent = "Standard Blackjack with No Drinks";
  } else {   // referee
    setupMode     = "referee";
    setupDrinking = true;
    refSettings.style.display  = "block";
    digSettings.style.display  = "none";
    if (easyModeField) easyModeField.style.display = "";
    setRowCols(handsDecksRow, false);
    setRowCols(togglesRow, false);
    sub.textContent = "Drinking Blackjack Physical Scorekeeper and Drink Tracker";
  }
}

// ============================================================
// SETUP — players (dynamic list)
// ============================================================
const RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"];
const SUITS = [
  { label: "♥", code: "h", cls: "hearts" },
  { label: "♦", code: "d", cls: "diamonds" },
  { label: "♣", code: "c", cls: "clubs" },
  { label: "♠", code: "s", cls: "spades" },
];

let playerRows = [];   // [{ id, name, isBot }]
let _rowIdCtr  = 0;

// Read current input/toggle values from DOM back into playerRows state
function syncPlayerRowsFromDOM() {
  document.querySelectorAll(".player-row[data-row-id]").forEach(el => {
    const id  = parseInt(el.dataset.rowId, 10);
    const row = playerRows.find(r => r.id === id);
    if (!row) return;
    const inp = el.querySelector(".player-name-input");
    const chk = el.querySelector(".bot-chk");
    if (inp) row.name  = inp.value;
    if (chk) row.isBot = chk.checked;
  });
}

function renderPlayerRows() {
  const c = document.getElementById("name-fields");
  c.innerHTML = "";
  const showRemove = playerRows.length > 2;

  playerRows.forEach((row, i) => {
    const rowEl = document.createElement("div");
    rowEl.className = "player-row";
    rowEl.dataset.rowId = row.id;

    // Name input
    const inp = document.createElement("input");
    inp.type        = "text";
    inp.className   = "player-name-input";
    inp.value       = row.name;
    inp.placeholder = row.isBot ? `Bot ${i + 1}` : `Player ${i + 1}`;
    inp.addEventListener("input", () => {
      const r = playerRows.find(r => r.id === row.id);
      if (r) r.name = inp.value;
    });

    // Bot toggle: "BOT" label + small pill
    const toggleWrap = document.createElement("div");
    toggleWrap.className = "bot-toggle-wrap";

    const botLbl = document.createElement("span");
    botLbl.className   = "bot-lbl";
    botLbl.textContent = "BOT";

    const pillLabel = document.createElement("label");
    pillLabel.className = "pill-toggle bot-pill";

    const chk = document.createElement("input");
    chk.type      = "checkbox";
    chk.className = "bot-chk";
    chk.checked   = row.isBot;
    chk.addEventListener("change", () => {
      const r = playerRows.find(r => r.id === row.id);
      if (r) {
        r.isBot         = chk.checked;
        inp.placeholder = r.isBot ? `Bot ${i + 1}` : `Player ${i + 1}`;
      }
    });

    const slider = document.createElement("span");
    slider.className = "pill-slider";

    pillLabel.appendChild(chk);
    pillLabel.appendChild(slider);
    toggleWrap.appendChild(botLbl);
    toggleWrap.appendChild(pillLabel);

    // Remove button (invisible but still takes space when at minimum)
    const removeBtn = document.createElement("button");
    removeBtn.className        = "player-remove-btn";
    removeBtn.textContent      = "×";
    removeBtn.style.opacity = showRemove ? "1" : "0.3";
    removeBtn.disabled = !showRemove;
    removeBtn.addEventListener("click", e => {
      e.preventDefault();
      syncPlayerRowsFromDOM();
      playerRows = playerRows.filter(r => r.id !== row.id);
      renderPlayerRows();
      syncDecksToPlayerCount();
    });

    rowEl.appendChild(inp);
    rowEl.appendChild(toggleWrap);
    rowEl.appendChild(removeBtn);
    c.appendChild(rowEl);
  });
}

function addPlayerRow() {
  syncPlayerRowsFromDOM();
  playerRows.push({ id: _rowIdCtr++, name: "", isBot: false });
  renderPlayerRows();
  syncDecksToPlayerCount();
}

// Start with 2 players
playerRows = [
  { id: _rowIdCtr++, name: "", isBot: false },
  { id: _rowIdCtr++, name: "", isBot: false },
];
renderPlayerRows();

// ============================================================
// NUMBER STEPPER
// ============================================================
function getStepperValue(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (el.tagName === "INPUT") return parseInt(el.value) || 0;  // fallback for plain inputs
  return parseInt(el.dataset.value) || 0;
}

function setStepperValue(id, val) {
  const el = document.getElementById(id);
  if (!el || !el.classList.contains("stepper")) return;
  const min = parseInt(el.dataset.min) || 0;
  const max = parseInt(el.dataset.max) || Infinity;
  val = Math.max(min, Math.min(max, val));
  el.dataset.value = val;
  el.querySelector(".stepper-display").textContent = val;
  el.querySelector(".stepper-dec").classList.toggle("at-limit", val <= min);
  el.querySelector(".stepper-inc").classList.toggle("at-limit", val >= max);
}

function syncDecksToPlayerCount() {
  const count = playerRows.length;

  // Deck count auto-bump
  const decks = getStepperValue("num-decks");
  if (decks !== null) {
    if (count >= 4 && decks < 2) setStepperValue("num-decks", 2);
    if (count < 4  && decks === 2) setStepperValue("num-decks", 1);
  }

  // Easy Mode: force ON + greyed out when 4+ players (halving already applies)
  const cb    = document.getElementById("easy-mode-setup-toggle");
  const pill  = document.getElementById("easy-mode-setup-pill");
  const label = document.getElementById("easy-mode-setup-label");
  if (!cb) return;
  if (count >= 4) {
    // Force ON and disable — 4-player rule covers it
    if (!cb.checked) setEasyModeSetup(true);
    cb.disabled = true;
    if (pill)  pill.style.opacity = "0.45";
    if (label) label.title = "Halving is automatic with 4+ players";
  } else {
    cb.disabled = false;
    if (pill)  pill.style.opacity = "";
    if (label) label.title = "";
  }
}

document.addEventListener("click", e => {
  const btn = e.target.closest(".stepper-dec, .stepper-inc");
  if (!btn) return;
  const stepper = btn.closest(".stepper");
  if (!stepper) return;

  const min = parseInt(stepper.dataset.min) || 0;
  const max = parseInt(stepper.dataset.max) || Infinity;
  let val   = parseInt(stepper.dataset.value) || 0;

  val = btn.classList.contains("stepper-dec")
    ? Math.max(min, val - 1)
    : Math.min(max, val + 1);

  stepper.dataset.value = val;
  stepper.querySelector(".stepper-display").textContent = val;
  stepper.querySelector(".stepper-dec").classList.toggle("at-limit", val <= min);
  stepper.querySelector(".stepper-inc").classList.toggle("at-limit", val >= max);
});

// ============================================================
// START GAME
// ============================================================
async function startGame() {
  const btn = document.getElementById("start-btn");
  btn.disabled = true;

  syncPlayerRowsFromDOM();
  const names = [];
  const npcs  = [];
  playerRows.forEach((row, i) => {
    const isBot = row.isBot;
    const name  = (row.name || "").trim() || (isBot ? `Bot${i + 1}` : `Player${i + 1}`);
    names.push(name);
    if (isBot) npcs.push(name);
  });
  npcPlayers = new Set(npcs);

  const isDigital = setupMode === "digital";
  const wager     = setupDrinking
    ? (getStepperValue(isDigital ? "wager-dig" : "wager-ref") || 1)
    : 1;
  const nh        = getStepperValue(isDigital ? "num-hands-dig" : "num-hands-ref") || 2;
  const numDecks  = getStepperValue("num-decks") || 1;

  const bustVoteEnabled = !!(document.getElementById("bust-vote-setup-toggle")?.checked);
  const easyMode        = !!(document.getElementById("easy-mode-setup-toggle")?.checked);

  // Player 1 is always the starting dealer
  const body = { players: names, dealer_index: 0, wager, num_hands: nh, mode: setupMode, drinking: setupDrinking, room_code: roomCode, npcs, client_id: clientId, bust_vote_enabled: bustVoteEnabled, easy_mode: easyMode };
  if (isDigital) body.num_decks = numDecks;

  const res  = await fetch("/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  btn.disabled = false;

  if (!data.ok) { alert(data.output || "Setup failed."); return; }

  players          = data.players;
  numHands         = nh;
  gameMode         = data.mode || "referee";
  myRole           = data.my_role          || "admin";
  myName           = data.my_name          || null;
  myNames          = data.my_names         || (myName ? [myName] : []);
  isMyDealerClient = data.is_dealer_client !== false;  // admin always starts as dealer

  try {
    updateHeader(data);
    buildGameUI();
    applyState(data);

    document.getElementById("setup").style.display = "none";
    document.getElementById("app").style.display   = "flex";
    startPolling();
    startIdleWatcher();
  } catch (err) {
    console.error("[startGame] Error launching game:", err);
    alert("Could not launch game: " + err.message + "\n\nCheck the browser console for details.");
    btn.disabled = false;
  }
}

// ============================================================
// IDLE WATCHER — warns before Render dyno sleep (15-min idle)
// ============================================================
const IDLE_SOFT_MS   = 10 * 60 * 1000;   // 10 min → "Still there?"
const IDLE_URGENT_MS = 14 * 60 * 1000;   // 14 min → "Room about to be lost"

let _lastActivityAt  = Date.now();
let _idleWatcherID   = null;

function resetIdleTimer() {
  _lastActivityAt = Date.now();
  const banner  = document.getElementById("idle-warning-banner");
  const overlay = document.getElementById("idle-urgent-overlay");
  if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
  if (overlay) { overlay.classList.remove("open"); }
  // Ping the server to keep the dyno alive
  fetch("/state?room_code=" + encodeURIComponent(roomCode) + "&client_id=" + encodeURIComponent(clientId))
    .catch(() => {});
}

function _tickIdleWatcher() {
  const elapsed = Date.now() - _lastActivityAt;
  const banner  = document.getElementById("idle-warning-banner");
  const text    = document.getElementById("idle-warning-text");
  const overlay = document.getElementById("idle-urgent-overlay");

  if (elapsed >= IDLE_URGENT_MS) {
    // Urgent: hide banner, show blocking modal
    if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
    if (overlay) { overlay.classList.add("open"); }
  } else if (elapsed >= IDLE_SOFT_MS) {
    // Soft: yellow banner only
    if (overlay) { overlay.classList.remove("open"); }
    if (banner && text) {
      banner.style.display = "flex";
      banner.className = "idle-warning-banner idle-soft";
      text.textContent = "Still there? Tap to keep the room alive.";
    }
  } else {
    if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
    if (overlay) { overlay.classList.remove("open"); }
  }
}

function startIdleWatcher() {
  _lastActivityAt = Date.now();
  if (_idleWatcherID) clearInterval(_idleWatcherID);
  _idleWatcherID = setInterval(_tickIdleWatcher, 30_000);  // check every 30s
}

