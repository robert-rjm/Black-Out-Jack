// CHAT LOG
// ============================================================
function appendLog(text, clear = false) {
  const log = document.getElementById("log");
  if (clear) log.innerHTML = "";
  if (!text) return;

  text.split("\n").forEach(line => {
    if (!line.trim()) return;
    const div = document.createElement("div");
    div.className = "chat-msg";
    const l = line.toLowerCase();
    if (l.includes("drink") || l.includes("sip"))                           div.classList.add("msg-drink");
    else if (l.includes("blackjack") || l.includes("***"))                  div.classList.add("msg-bj");
    else if (l.includes("win") || l.includes("dealer") && l.includes("bust")) div.classList.add("msg-ok");
    else if (l.includes("bust"))                                             div.classList.add("msg-drink");
    else if (l.includes("===") || l.includes("---") || l.includes("round")) div.classList.add("msg-header");
    div.textContent = line.trim();
    log.appendChild(div);
  });
  log.scrollTop = log.scrollHeight;
}

function updateSipTicker(state) {
  const el = document.getElementById("sip-ticker");
  if (!el) return;
  const drinking = state.drinking_mode !== false;
  const grand    = state.sip_grand_total || 0;
  const totals   = state.sip_totals || {};
  if (!drinking || (grand === 0 && Object.keys(totals).length === 0)) {
    el.style.display = "none";
    return;
  }
  el.style.display = "flex";
  el.innerHTML = "";
  const tot = document.createElement("span");
  tot.className   = "st-total";
  tot.textContent = `🍺 ${grand} total`;
  el.appendChild(tot);
  const order = state.play_order || state.players || [];
  order.forEach(name => {
    const div = document.createElement("div"); div.className = "st-div"; el.appendChild(div);
    const p   = document.createElement("div"); p.className   = "st-player";
    p.innerHTML = `<span class="st-name">${escapeHtml(name)}</span><span class="st-count">${totals[name] || 0}</span>`;
    el.appendChild(p);
  });
}

function showPeekedCard(card) {
  const wrap    = document.getElementById("peeked-card-wrap");
  const display = document.getElementById("peeked-card-display");
  if (!wrap || !display) return;
  display.innerHTML = "";
  display.appendChild(cardEl(card));
  // Also add a text label next to the card
  const lbl = document.createElement("span");
  lbl.style.cssText = "font-size:13px;font-weight:700;color:var(--text);align-self:center";
  lbl.textContent = `${card.rank}${card.symbol || ""}`;
  display.appendChild(lbl);
  wrap.style.display = "block";
}

// ============================================================
// DEALER TOAST
// ============================================================
let _dealerToastTimer = null;
function showDealerToast() {
  const el = document.getElementById("dealer-toast");
  if (!el) return;
  // Cross-dismiss: hide drink toast if it's still up
  _dismissPlayerToast();
  if (_dealerToastTimer) { clearTimeout(_dealerToastTimer); _dealerToastTimer = null; }
  el.classList.add("show");
  _dealerToastTimer = setTimeout(() => {
    el.classList.remove("show");
    _dealerToastTimer = null;
  }, 10000);
}

// ============================================================
// PLAYER DRINK TOAST
// ============================================================
let _playerToastTimer = null;
function _dismissPlayerToast() {
  const el = document.getElementById("player-toast");
  if (el) el.classList.remove("show");
  if (_playerToastTimer) { clearTimeout(_playerToastTimer); _playerToastTimer = null; }
}
function showPlayerDrinkToast(sips) {
  const el = document.getElementById("player-toast");
  if (!el) return;
  // Cross-dismiss: hide dealer toast if it's still up
  const dt = document.getElementById("dealer-toast");
  if (dt) dt.classList.remove("show");
  if (_dealerToastTimer) { clearTimeout(_dealerToastTimer); _dealerToastTimer = null; }
  if (_playerToastTimer) { clearTimeout(_playerToastTimer); _playerToastTimer = null; }
  if (sips > 0) {
    el.textContent = `🍺 You drink ${sips} sip${sips !== 1 ? "s" : ""}!`;
    el.className   = "drink show";
  } else {
    el.textContent = "🎉 Clean round!";
    el.className   = "clean show";
  }
  _playerToastTimer = setTimeout(() => {
    el.classList.remove("show");
    _playerToastTimer = null;
  }, 3500);
}

// ============================================================
// SWITCH TOAST (hard / soft dealer switch — shown to all players)
// ============================================================
const _HARD_MSGS = [
  "💀 Dealer lost every hand — Hard Switch!",
  "😬 Dealer got swept. Hard Switch!",
  "🫠 Everyone wins, Dealer drinks. Hard Switch!",
  "🃏 Dealer goes down! Hard Switch!",
];
const _SOFT_MSGS = [
  "😏 Dealer dominated! Soft Switch.",
  "🎰 Dealer won all hands — Soft Switch!",
  "🤑 Table wrecked by the Dealer. Soft Switch!",
];

let _switchToastTimer = null;
function showSwitchToast(switchType, dealerName) {
  const el = document.getElementById("switch-toast");
  if (!el) return;
  if (_switchToastTimer) { clearTimeout(_switchToastTimer); _switchToastTimer = null; }
  const pool = switchType === "hard" ? _HARD_MSGS : _SOFT_MSGS;
  const tmpl = pool[Math.floor(Math.random() * pool.length)];
  el.textContent = tmpl;
  if (switchType === "hard") {
    el.style.background = "var(--red)";
    el.style.color      = "#fff";
  } else {
    el.style.background = "var(--green)";
    el.style.color      = "#000";
  }
  el.classList.add("show");
  _switchToastTimer = setTimeout(() => {
    el.classList.remove("show");
    _switchToastTimer = null;
  }, 4500);
}

// ============================================================
// HEADER
// ============================================================
function updateHeader(data) {
  if (data.players) players = data.players;
  const dealer = data.dealer || "";
  const round  = data.round  || "";
  const mode   = data.mode   || gameMode;
  const drinking = data.drinking_mode !== false;
  const badge = mode === "digital"
    ? (drinking
        ? '<span class="mode-badge digital">🍺 Drinking</span>'
        : '<span class="mode-badge normal">🃏 Normal</span>')
    : '<span class="mode-badge referee">📋 Referee</span>';
  document.getElementById("header-title").innerHTML = `Black-Out-Jack ${badge}`;
  document.getElementById("header-sub").textContent = `Round ${round}  |  Dealer: ${dealer}`;
  if (roomCode) document.getElementById("header-room").textContent = "Room: " + roomCode;
}

// ============================================================
// TABS
// ============================================================
function switchRefTab(name, el) {
  document.querySelectorAll("#ref-tabs .tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll("#ref-panel .pane").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  document.getElementById(`pane-${name}`).classList.add("active");
}

function switchDigTab(name, el) {
  document.querySelectorAll("#dig-tabs .tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll("#dig-panel .pane").forEach(p => p.classList.remove("active"));
  el.classList.add("active");
  document.getElementById(`pane-${name}`).classList.add("active");
}

// ============================================================
// NEW ROUND — auto-decides rotation; no modal needed
// ============================================================
function clearPeekedCard() {
  const wrap = document.getElementById("peeked-card-wrap");
  if (wrap) wrap.style.display = "none";
  const display = document.getElementById("peeked-card-display");
  if (display) display.innerHTML = "";
}

async function doNewRound() {
  const state       = lastState || {};
  const switchType  = state.switch_this_round;        // "hard" | "soft" | null
  const roundsTD    = state.rounds_this_dealer || 1;
  const rotateEvery = state.dealer_rotate_every || 1;
  // Auto-rotate when hard/soft switch fired, or when rotation interval is reached
  const rotate = !!(switchType || roundsTD >= rotateEvery);
  clearPeekedCard();
  await sendCmd(rotate ? "newround rotate" : "newround");
  buildGameUI();
  if (gameMode === "digital") {
    await sendCmd("deal");
  } else {
    const firstTab = document.querySelector("#ref-tabs .tab");
    if (firstTab) switchRefTab("deal", firstTab);
  }
}

// ============================================================

// ============================================================
// ACE DRINK TOAST  (fires mid-round when an ace causes drinks)
// ============================================================
let _lastAceSeq = 0;

function processAceDrinkEvents(state) {
  const events  = state.ace_drink_events || [];
  const seq     = state.ace_drink_seq    || 0;
  // Reset if server started a new round (seq went back to 0 or below our last seen)
  if (seq < _lastAceSeq) _lastAceSeq = 0;
  if (seq <= _lastAceSeq || !events.length) return;

  // Only process events newer than what we've seen
  const newEvents = events.filter(e => e.seq > _lastAceSeq);
  _lastAceSeq = seq;
  if (!newEvents.length) return;

  // myName / myRole are module-level vars set in table.js (same bundle scope)
  const _myName = (typeof myName !== "undefined") ? myName : null;
  const _myRole = (typeof myRole !== "undefined") ? myRole : null;
  const _isDealer = _myRole === "dealer" || _myRole === "admin";

  // Collect events that affect this client
  const relevant = newEvents.filter(e => {
    if (e.recipient === "all")          return true;
    if (e.recipient === "players_only") return !_isDealer;
    return _myName && e.recipient.toLowerCase() === _myName.toLowerCase();
  });
  if (!relevant.length) return;

  const totalSips = relevant.reduce((s, e) => s + e.sips, 0);
  const firstReason = relevant[0].reason || "";

  const el = document.getElementById("player-toast");
  if (!el) return;
  const dt = document.getElementById("dealer-toast");
  if (dt) dt.classList.remove("show");

  // Short descriptive label: strip the verbose "=> X drinks N sip" suffix
  const label = firstReason.replace(/\s*=>\s*.+$/, "").trim();
  el.textContent = `🃏 ${label} — drink ${totalSips} sip${totalSips !== 1 ? "s" : ""}!`;
  el.className   = "drink show";
  if (typeof _playerToastTimer !== "undefined" && _playerToastTimer) {
    clearTimeout(_playerToastTimer);
  }
  setTimeout(() => el.classList.remove("show"), 5000);
}
