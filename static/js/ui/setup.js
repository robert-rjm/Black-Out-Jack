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
  const betCell        = document.getElementById("bet-dig-cell");
  const easyModeField  = document.getElementById("easy-mode-setup-field");
  const presetField    = document.getElementById("rules-preset-setup-field");
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
    if (betCell) betCell.style.display = "none";
    if (easyModeField) easyModeField.style.display = "";
    if (presetField) presetField.style.display = "";
    setRowCols(handsDecksRow, false);
    setRowCols(togglesRow, false);
    sub.textContent = "Virtual Drinking Blackjack";
  } else if (type === "normal") {
    setupMode     = "digital";
    setupDrinking = false;
    refSettings.style.display  = "none";
    digSettings.style.display  = "";
    wagerCell.style.display    = "none";
    if (betCell) betCell.style.display = "";
    // Easy Mode only applies to drink halving — not relevant for Normal mode
    if (easyModeField) {
      easyModeField.style.display = "none";
      setEasyModeSetup(false);
    }
    // House rules are drinking rules
    if (presetField) presetField.style.display = "none";
    // Normal mode default: 1 hand per player (players bet against the house)
    setStepperValue("num-hands-dig", 1);
    setRowCols(handsDecksRow, false);
    setRowCols(togglesRow, true);
    sub.textContent = "Standard Blackjack with No Drinks";
  } else {   // referee
    setupMode     = "referee";
    setupDrinking = true;
    refSettings.style.display  = "block";
    digSettings.style.display  = "none";
    if (betCell) betCell.style.display = "none";
    if (easyModeField) easyModeField.style.display = "";
    if (presetField) presetField.style.display = "";
    setRowCols(handsDecksRow, false);
    setRowCols(togglesRow, false);
    sub.textContent = "Drinking Blackjack Physical Scorekeeper and Drink Tracker";
  }
}

// ============================================================
// SETUP — players (dynamic list)
// ============================================================
// RANKS and SUITS are defined in config.js (loaded first).

let playerRows = [];   // [{ id, name, isBot, personality }]
let _rowIdCtr  = 0;

// Personality profiles available on the server (populated async below).
// Options beyond "basic" only show up once loaded -- harmless if a row was
// already toggled to bot before the fetch resolves, since re-rendering just
// adds the extra <option>s without losing the row's current selection.
let availablePersonalities = [];

async function loadAvailablePersonalities() {
  try {
    const res  = await fetch("/player_personalities");
    const data = await res.json();
    availablePersonalities = Array.isArray(data.personalities) ? data.personalities : [];
  } catch (_) {
    availablePersonalities = [];
  }
  syncPlayerRowsFromDOM();
  renderPlayerRows();
}

// Read current input/toggle values from DOM back into playerRows state
function syncPlayerRowsFromDOM() {
  document.querySelectorAll(".player-row-group[data-row-id]").forEach(el => {
    const id  = parseInt(el.dataset.rowId, 10);
    const row = playerRows.find(r => r.id === id);
    if (!row) return;
    const inp  = el.querySelector(".player-name-input");
    const chk  = el.querySelector(".bot-chk");
    const psel = el.querySelector(".bot-personality-select");
    if (inp)  row.name        = inp.value;
    if (chk)  row.isBot       = chk.checked;
    if (psel) row.personality = psel.value;
  });
}

function renderPlayerRows() {
  const c = document.getElementById("name-fields");
  c.innerHTML = "";
  const showRemove = playerRows.length > 2;

  playerRows.forEach((row, i) => {
    const group = document.createElement("div");
    group.className = "player-row-group";
    group.dataset.rowId = row.id;

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

    // Bot personality select -- only shown/meaningful while isBot is on.
    // Kept in the row's own element so syncPlayerRowsFromDOM() can read it
    // via a plain querySelector, same pattern as the name input/checkbox.
    const personalitySelect = document.createElement("select");
    personalitySelect.className = "bot-personality-select";
    personalitySelect.appendChild(new Option("Bot (Basic Strategy)", "basic"));
    availablePersonalities.forEach(name => {
      const label = name.charAt(0).toUpperCase() + name.slice(1) + "-bot";
      personalitySelect.appendChild(new Option(label, name));
    });
    personalitySelect.value = row.personality || "basic";
    personalitySelect.style.display = row.isBot ? "" : "none";
    personalitySelect.addEventListener("change", () => {
      const r = playerRows.find(r => r.id === row.id);
      if (r) r.personality = personalitySelect.value;
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
      personalitySelect.style.display = chk.checked ? "" : "none";
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
    group.appendChild(rowEl);
    group.appendChild(personalitySelect);
    c.appendChild(group);
  });
}

function addPlayerRow() {
  syncPlayerRowsFromDOM();
  playerRows.push({ id: _rowIdCtr++, name: "", isBot: false, personality: "basic" });
  renderPlayerRows();
  syncDecksToPlayerCount();
}

// Start with 2 players
playerRows = [
  { id: _rowIdCtr++, name: "", isBot: false, personality: "basic" },
  { id: _rowIdCtr++, name: "", isBot: false, personality: "basic" },
];
renderPlayerRows();
loadAvailablePersonalities();

// ============================================================
// NUMBER STEPPER
// ============================================================
function _stepperDisplay(el, val) {
  const step = parseFloat(el.dataset.step) || 1;
  return el.dataset.money !== undefined || step % 1 !== 0
    ? `$${val.toFixed(2)}`
    : String(val);
}

function getStepperValue(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (el.tagName === "INPUT") return parseInt(el.value) || 0;  // fallback for plain inputs
  const step = parseFloat(el.dataset.step) || 1;
  const val = parseFloat(el.dataset.value) || 0;
  return step % 1 !== 0 ? val : (parseInt(el.dataset.value) || 0);
}

function setStepperValue(id, val) {
  const el = document.getElementById(id);
  if (!el || !el.classList.contains("stepper")) return;
  const step = parseFloat(el.dataset.step) || 1;
  const min = parseFloat(el.dataset.min) || 0;
  const max = parseFloat(el.dataset.max) || Infinity;
  val = Math.max(min, Math.min(max, val));
  if (step % 1 !== 0) val = Math.round(val * 100) / 100;
  el.dataset.value = val;
  el.querySelector(".stepper-display").textContent = _stepperDisplay(el, val);
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

  const step = parseFloat(stepper.dataset.step) || 1;
  const min  = parseFloat(stepper.dataset.min) || 0;
  const max  = parseFloat(stepper.dataset.max) || Infinity;
  let val    = parseFloat(stepper.dataset.value) || 0;

  val = btn.classList.contains("stepper-dec")
    ? Math.max(min, val - step)
    : Math.min(max, val + step);
  if (step % 1 !== 0) val = Math.round(val * 100) / 100;

  stepper.dataset.value = val;
  stepper.querySelector(".stepper-display").textContent = _stepperDisplay(stepper, val);
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
  const personalities = {};
  playerRows.forEach((row, i) => {
    const isBot = row.isBot;
    const name  = (row.name || "").trim() || (isBot ? `Bot${i + 1}` : `Player${i + 1}`);
    names.push(name);
    if (isBot) {
      npcs.push(name);
      personalities[name] = row.personality || "basic";
    }
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
  const body = { players: names, dealer_index: 0, wager, num_hands: nh, mode: setupMode, drinking: setupDrinking, room_code: roomCode, npcs, personalities, client_id: clientId, bust_vote_enabled: bustVoteEnabled, easy_mode: easyMode };
  if (setupDrinking) body.rules_preset = setupRulesPreset;
  if (isDigital) body.num_decks = numDecks;
  if (!setupDrinking) {
    body.bet_amount = getStepperValue("bet-dig") || 10;
  }

  let data;
  try {
    const res  = await fetch("/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    data = await res.json();
  } catch (_) {
    alert("Could not reach server — check your connection and try again.");
    btn.disabled = false;
    return;
  }
  btn.disabled = false;

  if (!data.ok) { alert(data.error || "Setup failed."); return; }

  players          = data.players;
  numHands         = nh;
  gameMode         = data.mode || "referee";
  myRole           = data.my_role          || ROLE.ADMIN;
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
