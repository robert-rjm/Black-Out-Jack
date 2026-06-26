// ============================================================
// TOAST QUEUE — suppress mid-round toasts during bust vote window
// ============================================================
// Toast state, consolidated under one namespaced object (was 4 separate
// module-level globals: ToastUI.queue, ToastUI.dealerTimer, ToastUI.playerTimer,
// ToastUI.switchTimer). Same values, same mutation patterns as before.
const ToastUI = {
  queue:        [],   // queued toast-show callbacks, flushed after bust vote closes
  dealerTimer:  null, // setTimeout handle for the dealer toast auto-hide
  playerTimer:  null, // setTimeout handle for the player drink toast auto-hide
  switchTimer:  null, // setTimeout handle for the dealer switch toast auto-hide
};

/** True while the bust vote window is open (reads lastState set in table.js). */
function _bustVoteOpen() {
  return !!(typeof lastState !== "undefined" && lastState && lastState.bust_vote_window_open);
}

/**
 * Flush all queued toasts, staggered 3.5 s apart so they don't overlap.
 * Called by table.js when bust_vote_window_open transitions true → false.
 */
function flushToastQueue() {
  if (!ToastUI.queue.length) return;
  const q = ToastUI.queue.splice(0);
  q.forEach((fn, i) => setTimeout(fn, i * 3500));
}

// Log removed — stub so existing call sites don't throw
// ============================================================
function appendLog() {}

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
function showDealerToast() {
  const el = document.getElementById("dealer-toast");
  if (!el) return;
  // Cross-dismiss: hide drink toast if it's still up
  _dismissPlayerToast();
  if (ToastUI.dealerTimer) { clearTimeout(ToastUI.dealerTimer); ToastUI.dealerTimer = null; }
  el.classList.add("show");
  ToastUI.dealerTimer = setTimeout(() => {
    el.classList.remove("show");
    ToastUI.dealerTimer = null;
  }, 10000);
}

// ============================================================
// PLAYER DRINK TOAST
// ============================================================
function _dismissPlayerToast() {
  const el = document.getElementById("player-toast");
  if (el) el.classList.remove("show");
  if (ToastUI.playerTimer) { clearTimeout(ToastUI.playerTimer); ToastUI.playerTimer = null; }
}
function showPlayerDrinkToast(sips, playerName) {
  const el = document.getElementById("player-toast");
  if (!el) return;
  // Cross-dismiss: hide dealer toast if it's still up
  const dt = document.getElementById("dealer-toast");
  if (dt) dt.classList.remove("show");
  if (ToastUI.dealerTimer) { clearTimeout(ToastUI.dealerTimer); ToastUI.dealerTimer = null; }
  if (ToastUI.playerTimer) { clearTimeout(ToastUI.playerTimer); ToastUI.playerTimer = null; }
  const prefix = playerName ? escapeHtml(playerName) + " — " : "";
  if (sips > 0) {
    el.textContent = `🍺 ${prefix}drink ${sips} sip${sips !== 1 ? "s" : ""}!`;
    el.className   = "drink show";
  } else {
    el.textContent = playerName ? `🎉 ${prefix}clean round!` : "🎉 Clean round!";
    el.className   = "clean show";
  }
  ToastUI.playerTimer = setTimeout(() => {
    el.classList.remove("show");
    ToastUI.playerTimer = null;
  }, 6000);
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

function showSwitchToast(switchType, dealerName) {
  const el = document.getElementById("switch-toast");
  if (!el) return;
  if (ToastUI.switchTimer) { clearTimeout(ToastUI.switchTimer); ToastUI.switchTimer = null; }
  const pool = switchType === "hard" ? _HARD_MSGS : _SOFT_MSGS;
  const tmpl = pool[Math.floor(Math.random() * pool.length)];
  el.textContent = tmpl;
  // Dealer switches are purely informational — always yellow, regardless of
  // hard/soft type.
  el.style.background = "var(--yellow)";
  el.style.color      = "#000";
  el.classList.add("show");
  ToastUI.switchTimer = setTimeout(() => {
    el.classList.remove("show");
    ToastUI.switchTimer = null;
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
  const drinking    = state.drinking_mode !== false;
  const switchType  = state.switch_this_round;        // "hard" | "soft" | null
  const roundsTD    = state.rounds_this_dealer || 1;
  const rotateEvery = state.dealer_rotate_every || 1;
  // Normal mode: fixed house dealer — never rotate.
  // Drinking mode: auto-rotate when hard/soft switch fired, or rotation interval reached.
  const rotate = drinking && !!(switchType || roundsTD >= rotateEvery);
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
  const _myName   = (typeof myName  !== "undefined") ? myName  : null;
  const _myRole   = (typeof myRole  !== "undefined") ? myRole  : null;
  const _isDealer = _myRole === ROLE.DEALER || _myRole === ROLE.ADMIN;

  // Shown to ALL players — ace drink events are social info everyone should see.
  // Separate into events that affect the current client vs others.
  const mine = newEvents.filter(e => {
    if (e.recipient === "all")          return true;
    if (e.recipient === "players_only") return !_isDealer;
    return _myName && e.recipient.toLowerCase() === _myName.toLowerCase();
  });

  const el = document.getElementById("player-toast");
  if (!el) return;
  const dt = document.getElementById("dealer-toast");
  if (dt) dt.classList.remove("show");

  let text;
  if (mine.length > 0) {
    // Events that include the current player — keep "drink N sips" framing
    const totalSips  = mine.reduce((s, e) => s + e.sips, 0);
    const label      = mine[0].reason.replace(/\s*=>\s*.+$/, "").trim();
    text = `🃏 ${label} — drink ${totalSips} sip${totalSips !== 1 ? "s" : ""}!`;
  } else {
    // Events for other players — show the full reason so everyone knows who drinks
    // Reason format: "A♥ dealt to X => Y drinks N sip(s)"
    // Reformat as:   "🃏 A♥ dealt to X — Y drinks N sip(s)"
    const reason = newEvents[0].reason || "";
    text = `🃏 ${reason.replace(/\s*=>\s*/, " — ")}`;
  }

  const duration = mine.length > 0 ? 5000 : 8000;

  const _showAceToast = () => {
    const toastEl = document.getElementById("player-toast");
    if (!toastEl) return;
    const dtEl = document.getElementById("dealer-toast");
    if (dtEl) dtEl.classList.remove("show");
    toastEl.textContent = text;
    // Red if I'm one of the players drinking from this ace effect, green
    // if someone else is drinking instead.
    toastEl.className   = (mine.length > 0 ? "drink" : "clean") + " show";
    if (ToastUI.playerTimer) {
      clearTimeout(ToastUI.playerTimer);
    }
    setTimeout(() => toastEl.classList.remove("show"), duration);
  };

  if (_bustVoteOpen()) {
    ToastUI.queue.push(_showAceToast);
  } else {
    _showAceToast();
  }
}

// ============================================================
// SHOE RESHUFFLE TOAST (fires mid-round if the shoe runs low
// and auto-reshuffles before the next card is dealt)
// ============================================================
let _lastReshuffleSeq = 0;

function processReshuffleEvents(state) {
  const events = state.reshuffle_events || [];
  const seq    = state.reshuffle_seq    || 0;
  // Reset if server started a new round (seq went back to 0 or below our last seen)
  if (seq < _lastReshuffleSeq) _lastReshuffleSeq = 0;
  if (seq <= _lastReshuffleSeq || !events.length) return;

  const newEvents = events.filter(e => e.seq > _lastReshuffleSeq);
  _lastReshuffleSeq = seq;
  if (!newEvents.length) return;

  const el = document.getElementById("switch-toast");
  if (!el) return;

  const _showReshuffleToast = () => {
    if (ToastUI.switchTimer) { clearTimeout(ToastUI.switchTimer); ToastUI.switchTimer = null; }
    el.textContent      = "🔀 Shoe ran low — reshuffled mid-round!";
    el.style.background = "var(--yellow)";
    el.style.color      = "#000";
    el.classList.remove("show");
    void el.offsetWidth;
    el.classList.add("show");
    ToastUI.switchTimer = setTimeout(() => {
      el.classList.remove("show");
      ToastUI.switchTimer = null;
    }, 4500);
  };

  if (_bustVoteOpen()) {
    ToastUI.queue.push(_showReshuffleToast);
  } else {
    _showReshuffleToast();
  }
}

// ============================================================
// DEVIL'S HAND (666) / LUCKY SEVENS (777) TABLE EVENTS
// ============================================================
let _lastTableEventSeq = 0;

function processTableEvents(state) {
  const events = state.table_events || [];
  const seq    = state.table_event_seq || 0;
  if (seq < _lastTableEventSeq) _lastTableEventSeq = 0;
  if (seq <= _lastTableEventSeq || !events.length) return;

  const newEvents = events.filter(e => e.seq > _lastTableEventSeq);
  _lastTableEventSeq = seq;
  if (!newEvents.length) return;

  const el = document.getElementById("player-toast");
  if (!el) return;

  newEvents.forEach(ev => {
    const _show = () => {
      el.textContent = ev.text;
      // curse = red (drink), lucky = green (credit)
      el.className = (ev.outcome === "lucky" ? "clean" : "drink") + " show";
      if (ToastUI.playerTimer) clearTimeout(ToastUI.playerTimer);
      ToastUI.playerTimer = setTimeout(() => el.classList.remove("show"), 7000);
    };
    if (_bustVoteOpen()) {
      ToastUI.queue.push(_show);
    } else {
      _show();
    }
  });
}

// ============================================================
// WILD CARD EASTER EGG  (logo press → 40/20/40 drink event)
// ============================================================
let _lastWildCardSeq = 0;

function processWildCardEvent(state) {
  const seq = state.wild_card_seq || 0;
  // seq resets each round (RoundState) — reset our tracker too
  if (seq < _lastWildCardSeq) _lastWildCardSeq = 0;
  if (seq <= _lastWildCardSeq) return;
  _lastWildCardSeq = seq;

  const text    = state.wild_card_text;
  const outcome = state.wild_card_outcome; // "self" | "random" | "dud"
  if (!text) return;

  const el = document.getElementById("player-toast");
  if (!el) return;
  const dt = document.getElementById("dealer-toast");
  if (dt) dt.classList.remove("show");

  const _showWildToast = () => {
    el.textContent = text;
    // "drink" class (red) for self/random, "clean" (green) for dud
    el.className = (outcome === "dud" ? "clean" : "drink") + " show";
    if (ToastUI.playerTimer) clearTimeout(ToastUI.playerTimer);
    ToastUI.playerTimer = setTimeout(() => el.classList.remove("show"), 7000);
  };

  // Flash logo with spin animation
  const logo = document.getElementById("header-logo");
  if (logo) {
    logo.classList.add("wild-card-flash");
    setTimeout(() => logo.classList.remove("wild-card-flash"), 900);
  }

  if (_bustVoteOpen()) {
    ToastUI.queue.push(_showWildToast);
  } else {
    _showWildToast();
  }
}

async function triggerWildCard() {
  if (typeof roomCode === "undefined" || typeof clientId === "undefined") return;

  // Optimistic spin on the logo
  const logo = document.getElementById("header-logo");
  if (logo) logo.classList.add("wild-card-spin");

  try {
    const res  = await fetch("/wild_card", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    if (logo) logo.classList.remove("wild-card-spin");

    if (data.ok) {
      if (typeof applyState === "function") applyState(data);
    } else {
      // Show brief error in the player-toast (no attribution reveals the attempt)
      const el = document.getElementById("player-toast");
      if (el) {
        el.textContent = "🃏 " + (data.output || "Wild Card unavailable right now.");
        el.className   = "clean show";
        if (ToastUI.playerTimer) clearTimeout(ToastUI.playerTimer);
        ToastUI.playerTimer = setTimeout(() => el.classList.remove("show"), 4500);
      }
    }
  } catch (_) {
    if (logo) logo.classList.remove("wild-card-spin");
  }
}
