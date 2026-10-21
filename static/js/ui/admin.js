// ROLE-BASED UI
// ============================================================
const VOTE_LABEL = { h: "HIT", s: "STAND", d: "DOUBLE", sp: "SPLIT" };

let _suggestPickerOpen = false;

function toggleSuggestPicker() {
  _suggestPickerOpen = !_suggestPickerOpen;
  const picker = document.getElementById("suggest-picker");
  const btn    = document.getElementById("suggest-toggle-btn");
  if (picker) picker.style.display = _suggestPickerOpen ? "block" : "none";
  if (btn)    btn.textContent = _suggestPickerOpen ? "✕ Cancel suggestion" : "💬 Suggest different action";
}

async function sendSuggest(action) {
  const turn = (lastState && lastState.current_turn) || "";
  const hand = (sel.digital.hand || "hand1").toLowerCase();
  if (!turn) return;
  try {
    const res  = await fetch("/suggest_action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, player_name: turn, hand, action }),
    });
    const data = await res.json();
    if (data.ok) {
      _suggestPickerOpen = false;
      applyState(data);
    }
  } catch (_) {}
}

async function respondSuggest(accept) {
  const hand = (sel.digital.hand || "hand1").toLowerCase();
  try {
    const res  = await fetch("/respond_suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, hand, accept }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

function updateRoleUI(state) {
  // Drinks tab is visible to all; dealer-only actions inside the pane are toggled separately
  const dealerActions = document.getElementById("dig-drinks-dealer-actions");
  const waitingHint   = document.getElementById("dig-drinks-waiting");
  const isRoundOver   = state.phase === PHASE.ROUND_OVER;
  // NEW ROUND is only relevant at round-over; during pre-deal the DEAL button takes over
  if (dealerActions) dealerActions.style.display = (isMyDealerClient && isRoundOver) ? "block" : "none";
  if (waitingHint)   waitingHint.style.display   = (!isMyDealerClient && myRole !== ROLE.SPECTATOR && isRoundOver) ? "block" : "none";

  const hint         = document.getElementById("dig-play-role-hint");
  const voteDisp     = document.getElementById("player-vote-display");
  const suggestBanner= document.getElementById("suggest-banner");
  const suggestText  = document.getElementById("suggest-text");
  const suggestPicker= document.getElementById("suggest-picker");
  const suggestToggle= document.getElementById("suggest-toggle-row");
  const predealPanel   = document.getElementById("dig-predeal-panel");
  const playContent    = document.getElementById("dig-play-content");
  const phase          = state.phase;
  const isPreDeal      = phase === PHASE.PRE_DEAL;

  // Waiting-room deal panel: above tabs, dealer only
  if (predealPanel) {
    // Hidden while the stake window runs so a double-tap on DEAL can't skip it
    predealPanel.style.display = (isPreDeal && isMyDealerClient && !state.stake_window_open) ? "block" : "none";
  }
  // Per-player stake panel: shown to every human seat while the stake window is open (normal mode only)
  _updateBetPanel(state, isPreDeal);
  // Hide all play actions until cards are on the table
  if (playContent) {
    playContent.style.display = isPreDeal ? "none" : "block";
  }
  const turn         = state.current_turn;
  const presel       = state.preselections || {};
  const suggestions  = state.suggestions   || {};

  // Clear all highlights
  digActionButtons().forEach(b => b.classList.remove("voted"));
  digActionButtons().forEach(b => b.classList.remove("voted-dealer"));

  // Hide suggest UI by default
  if (suggestBanner) suggestBanner.style.display = "none";
  if (suggestPicker) suggestPicker.style.display  = "none";
  if (suggestToggle) suggestToggle.style.display  = "none";
  if (voteDisp)      voteDisp.style.display       = "none";
  const showVoteText = state.drinking_mode !== false;

  // Local seat switcher (play panel)
  _updateLocalSeatSwitcher();

  // Role hint (drinking mode only; in normal mode the dealer is the house)
  if (state.drinking_mode === false) {
    if (hint) hint.textContent = "";
  } else if (hint) {
    if (isMyDealerClient)                           hint.textContent = phase === PHASE.PLAYING ? "You are the dealer — execute the player's vote." : "";
    else if (myRole === ROLE.PLAYER || myRole === ROLE.ADMIN) hint.textContent = phase === PHASE.PLAYING ? "Tap to vote your play — dealer carries it out." : "";
    else                                            hint.textContent = "Spectating — watching only.";
  }

  // Spectators: disable everything and stop
  if (myRole === ROLE.SPECTATOR || !myRole) {
    digActionButtons().forEach(b => b.classList.add("disabled"));
    return;
  }

  if (phase !== PHASE.PLAYING || !turn) return;

  // ── DEALER VIEW ──────────────────────────────────────────────
  if (isMyDealerClient) {
    // While the bust-vote side-bet window is still open, grey out the play
    // panel so it doesn't look "ready to go" — players are still placing
    // their bust bets.
    if (state.bust_vote_window_open) {
      digActionButtons().forEach(b => b.classList.add("disabled"));
      if (hint) hint.textContent = "⏳ Waiting on bust-vote bets...";
      if (voteDisp) {
        voteDisp.textContent   = "⏳ Waiting on bust-vote bets...";
        voteDisp.style.display = "block";
      }
      return;
    }

    const hand = (sel.digital.hand || "hand1").toLowerCase();
    const key  = `${turn.toLowerCase()}:${hand}`;
    const vote = presel[key];

    if (voteDisp) {
      voteDisp.textContent   = vote ? `${turn} voted: ${VOTE_LABEL[vote]}` : `${turn} — no vote yet`;
      voteDisp.style.display = showVoteText ? "block" : "none";
    }

    if (vote) {
      // Lock dealer to voted action; highlight it yellow
      // vote is the backend code (h/s/d/sp) matching data-action-code
      digActionButtons().forEach(b => {
        const code = b.dataset.actionCode;
        if (code === vote) {
          b.classList.add("voted-dealer");
          b.classList.remove("disabled");
        } else if (code) {   // any action button (has data-action-code)
          b.classList.add("disabled");
        }
      });
      // Show suggest-different toggle
      if (suggestToggle) suggestToggle.style.display = "block";
      if (suggestPicker) suggestPicker.style.display = _suggestPickerOpen ? "block" : "none";
    }
    // No vote → all buttons available; split/double still gated by updateActionButtons

  // ── PLAYER VIEW ──────────────────────────────────────────────
  } else if (myRole === ROLE.PLAYER) {
    const activeName = myActiveName || myName;
    const isMyTurn   = activeName && turn.toLowerCase() === activeName.toLowerCase();

    // Not your turn → grey everything out, done
    if (!isMyTurn) {
      digActionButtons().forEach(b => b.classList.add("disabled"));
      return;
    }

    const hand       = (sel.digital.hand || "hand1").toLowerCase();
    const key        = `${activeName.toLowerCase()}:${hand}`;
    const vote       = presel[key];
    const suggestion = suggestions[key];

    // Incoming dealer suggestion: show banner + highlight that button yellow
    if (suggestion) {
      if (suggestBanner && suggestText) {
        suggestText.textContent = `Dealer suggests: ${VOTE_LABEL[suggestion] || suggestion} — do you agree?`;
        suggestBanner.style.display = "block";
      }
      digActionButtons().forEach(b => {
        if (b.dataset.actionCode === suggestion) b.classList.add("voted-dealer");
      });
    }

    if (voteDisp) {
      if (vote) {
        digActionButtons().forEach(b => {
          if (b.dataset.actionCode === vote) b.classList.add("voted");
        });
        voteDisp.textContent = `Your vote: ${VOTE_LABEL[vote]} — waiting for dealer`;
      } else {
        voteDisp.textContent = "Tap to vote your play";
      }
      voteDisp.style.display = showVoteText ? "block" : "none";
    }
  }
}

// ============================================================
// TABLE SETTINGS TOGGLES (host)
// ============================================================

async function setBustVoteEnabled(on) {
  try {
    const res  = await fetch("/update_settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, bust_vote_enabled: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

function setStrategyHintEnabled(on) {
  // Per-player preference — stored server-side so badge and blue border are state-driven
  window._myHintEnabled = on; // optimistic: prevent next poll from flipping the checkbox back
  fetch("/set_hint", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ room_code: roomCode, client_id: clientId, enabled: on }),
  }).then(r => r.json()).then(data => { if (data.ok) applyState(data); })
    .catch(() => { if (lastState) applyState(lastState); });
}

async function setWildCardEnabled(on) {
  try {
    const res  = await fetch("/update_settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, wild_card_enabled: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

async function setEasyModeAdmin(on) {
  try {
    const res  = await fetch("/update_settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, easy_mode: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

async function setDrinkingModeAdmin(on) {
  try {
    const res  = await fetch("/update_settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, drinking_mode: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

async function setBuyinHandouts(on) {
  try {
    const res  = await fetch("/update_settings", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, buyin_handouts: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

async function setPaused(paused) {
  try {
    const res = await fetch("/set_paused", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, paused: !!paused }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    if (paused && typeof closeKickModal === "function") closeKickModal();
  } catch (e) { console.error("setPaused failed", e); }
}

function _syncPausedOverlay(state) {
  const overlay = document.getElementById("paused-overlay");
  if (!overlay) return;
  overlay.classList.toggle("open", !!state.paused);
  const isAdmin = (myRole === ROLE.ADMIN);
  const btn  = document.getElementById("paused-resume-btn");
  const wait = document.getElementById("paused-wait");
  if (btn)  btn.style.display  = isAdmin ? "inline-block" : "none";
  if (wait) wait.style.display = isAdmin ? "none" : "block";
}

async function setGodMode(on) {
  try {
    const res = await fetch("/toggle_god_mode", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, enabled: on }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (e) { console.error("setGodMode failed", e); }
}

// ── Local seat management ────────────────────────────────────────────────────

function cycleLocalSeat() {
  if (!myNames || myNames.length <= 1) return;
  const idx  = myNames.findIndex(n => n.toLowerCase() === (myActiveName || "").toLowerCase());
  myActiveName = myNames[(idx + 1) % myNames.length];
  _updateLocalSeatSwitcher();
}

function _updateLocalSeatSwitcher() {
  const switcher = document.getElementById("local-seat-switcher");
  const activeEl = document.getElementById("local-seat-active");
  if (!switcher) return;
  if (myNames && myNames.length > 1) {
    switcher.style.display = "flex";
    if (activeEl) activeEl.textContent = myActiveName || myNames[0];
  } else {
    switcher.style.display = "none";
  }
}

function showLocalSeatPicker() {
  const picker = document.getElementById("local-seat-picker");
  if (!picker || !lastState) return;
  if (picker.style.display !== "none") { picker.style.display = "none"; return; }

  const clients      = lastState.connected_clients || [];
  // Seats registered as another client's PRIMARY name are remote-owned — not requestable.
  const remotePrimary = new Set(
    clients.filter(c => c.name && c.role !== myRole || c.name)
           .map(c => (c.name || "").toLowerCase()).filter(Boolean)
  );
  const myNamesLower = new Set((myNames || []).map(n => n.toLowerCase()));
  // All seats controlled locally by OTHER clients (in their local_names but not their primary)
  const otherLocalNames = new Set(
    clients.flatMap(c => (c.local_names || []).filter(n => (c.name || "").toLowerCase() !== n.toLowerCase()))
           .map(n => n.toLowerCase()).filter(Boolean)
  );

  // Available = not one of my own seats AND not a remote player's primary registration
  const available = (lastState.players || []).filter(n => {
    const lc = n.toLowerCase();
    return !myNamesLower.has(lc) && !remotePrimary.has(lc);
  });

  if (!available.length) {
    picker.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:4px 0">No seats available to claim.</div>';
    picker.style.display = "block";
    return;
  }

  picker.innerHTML = "";
  available.forEach(name => {
    const btn = document.createElement("button");
    btn.className = "btn wide seat-pick-btn";
    const needsTransfer = otherLocalNames.has(name.toLowerCase());
    btn.textContent = name + (needsTransfer ? " (request transfer)" : "");
    btn.addEventListener("click", (e) => { e.stopPropagation(); requestLocalSeat(name); });
    picker.appendChild(btn);
  });
  picker.style.display = "block";
}

async function requestLocalSeat(name) {
  const picker = document.getElementById("local-seat-picker");
  if (picker) picker.style.display = "none";
  try {
    const res  = await fetch("/request_local_seat", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, name }),
    });
    const data = await res.json();
    if (data.ok) {
      applyState(data);
      if (data.transfer_pending) alert(`Seat transfer requested for "${name}" — waiting for the current controller to approve.`);
      else if (data.pending)     alert(`Seat request for "${name}" sent — waiting for admin approval.`);
    } else {
      alert(data.error || "Could not request seat.");
    }
  } catch (_) { alert("Network error."); }
}


// ============================================================
// REGISTRATION
// ============================================================
function updateRegisterOverlay(state) {
  const overlay = document.getElementById("register-overlay");
  if (!overlay) return;

  if (state.my_registration_denied) {
    // Permanently blocked — show hard stop, no seat buttons
    _showRegisterBlocked();
    return;
  }
  if (state.my_registration_rejected) {
    // Rejected once — show message + seat buttons so they can try again
    _showRegisterDenied(state);
    return;
  }
  if (state.my_registration_pending) {
    _showRegisterPending();
    return;
  }
  if (!state.my_role || state.my_role === "pending") {
    showRegisterOverlay(state);
  } else {
    overlay.style.display = "none";
  }

  // Admin: render pending registration approvals banner
  pendingRegBanner.render(state);

  // Seat transfer requests (current controller must approve/deny)
  _syncSeatTransfers(state.pending_seat_transfers || []);
}

function _showRegisterPending() {
  const overlay  = document.getElementById("register-overlay");
  const seatsEl  = document.getElementById("register-seats");
  const pendEl   = document.getElementById("register-pending");
  const deniedEl = document.getElementById("register-denied");
  if (seatsEl)  seatsEl.innerHTML = "";
  if (pendEl)   pendEl.style.display  = "block";
  if (deniedEl) deniedEl.style.display = "none";
  if (overlay)  overlay.style.display = "flex";
}

function _showRegisterDenied(state) {
  // Rejected but can retry — show message above seat buttons
  const pendEl   = document.getElementById("register-pending");
  const deniedEl = document.getElementById("register-denied");
  if (pendEl)   pendEl.style.display   = "none";
  if (deniedEl) {
    deniedEl.textContent  = "✗ Request denied — choose a seat and try again.";
    deniedEl.style.display = "block";
  }
  showRegisterOverlay(state);
}

function _showRegisterBlocked() {
  // Permanently blocked — no seat buttons, hard stop
  const overlay  = document.getElementById("register-overlay");
  const seatsEl  = document.getElementById("register-seats");
  const pendEl   = document.getElementById("register-pending");
  const deniedEl = document.getElementById("register-denied");
  if (seatsEl)  seatsEl.innerHTML      = "";
  if (pendEl)   pendEl.style.display   = "none";
  if (deniedEl) {
    deniedEl.textContent   = "✗ You have been denied too many times and cannot join this session.";
    deniedEl.style.display = "block";
  }
  // Hide spectate button too
  const spectateBtn = overlay && overlay.querySelector(".muted-btn");
  if (spectateBtn) spectateBtn.style.display = "none";
  if (overlay) overlay.style.display = "flex";
}

// ── Pending-registration approval banner component (Improvements.md item 7,
// Option A: class-based, no framework) ──────────────────────────────────
// mount() attaches one delegated click listener (replacing the former
// per-button onclick="handleRegistration('${client_id}', ...)" strings --
// the one site in this file where server-derived data was interpolated
// directly into an onclick= attribute rather than read back via dataset);
// render(state) rebuilds the banner exactly as the old
// renderPendingRegBanner() function did.
class PendingRegBanner {
  mount(el) {
    if (this.el) return;   // idempotent -- buildGameUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest("[data-approve]");
      if (btn) handleRegistration(btn.dataset.clientId, btn.dataset.approve === "true");
    });
  }

  render(state) {
    if (!this.el) return;
    const banner = this.el;
    const pending = state.pending_registrations || [];
    if (!pending.length || myRole !== ROLE.ADMIN) {
      banner.style.display = "none";
      banner.innerHTML = "";
      return;
    }
    banner.style.display = "block";
    // No onclick= here -- mount()'s delegated listener handles taps.
    banner.innerHTML = pending.map(r =>
      `<div class="pending-reg-row">
        <span class="pending-reg-name">🙋 ${escapeHtml(r.name)} wants to join</span>
        <span class="pending-reg-btns">
          <button class="btn approve btn-sm" data-client-id="${escapeHtml(r.client_id)}" data-approve="true">✓ Accept</button>
          <button class="btn danger btn-sm" data-client-id="${escapeHtml(r.client_id)}" data-approve="false">✗ Deny</button>
        </span>
      </div>`
    ).join("");
  }
}

const pendingRegBanner = new PendingRegBanner();

function showRegisterOverlay(state) {
  const overlay  = document.getElementById("register-overlay");
  const seatsEl  = document.getElementById("register-seats");
  const pendEl   = document.getElementById("register-pending");
  const deniedEl = document.getElementById("register-denied");
  if (!overlay || !seatsEl) return;

  if (pendEl)   pendEl.style.display  = "none";

  // Also account for seats currently pending (don't let two clients claim same seat)
  const pendingNames = new Set(
    (state.pending_registrations || []).map(r => r.name.toLowerCase())
  );
  const clients      = state.connected_clients || [];
  const claimedLower = new Set(clients.map(c => c.name).filter(Boolean).map(n => n.toLowerCase()));
  const allSeats     = state.players || [];
  const available    = allSeats.filter(n =>
    !claimedLower.has(n.toLowerCase()) && !pendingNames.has(n.toLowerCase())
  );

  seatsEl.innerHTML = "";
  if (available.length === 0) {
    seatsEl.innerHTML = `<p class="reg-no-seats">All seats are taken — you can watch as spectator.</p>`;
  } else {
    available.forEach(name => {
      const btn     = document.createElement("button");
      btn.className = "btn-big accent reg-seat-btn";
      btn.textContent = `I am ${name}`;
      btn.addEventListener("click", () => doRegister(name));
      seatsEl.appendChild(btn);
    });
  }
  overlay.style.display = "flex";
}

async function doRegister(name) {
  const errEl    = document.getElementById("register-error");
  const pendEl   = document.getElementById("register-pending");
  const deniedEl = document.getElementById("register-denied");
  if (deniedEl) deniedEl.style.display = "none";
  try {
    const res  = await fetch("/register", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, name }),
    });
    const data = await res.json();
    if (data.ok) {
      if (data.pending) {
        // Awaiting admin approval — show pending state
        if (pendEl) pendEl.style.display = "block";
        const seatsEl = document.getElementById("register-seats");
        if (seatsEl) seatsEl.innerHTML = "";
        applyState(data);
      } else {
        document.getElementById("register-overlay").style.display = "none";
        applyState(data);
      }
    } else {
      if (errEl) { errEl.textContent = data.error || "Could not claim seat."; errEl.style.display = "block"; }
    }
  } catch (_) {
    if (errEl) { errEl.textContent = "Network error."; errEl.style.display = "block"; }
  }
}

// ── Seat-transfer modal ─────────────────────────────────────────────────────
let _seatTransferQueue = [];

function _processSeatTransferQueue() {
  const overlay = document.getElementById("seat-transfer-overlay");
  if (!overlay) return;
  if (_seatTransferQueue.length === 0) {
    overlay.style.display = "none";
    return;
  }
  const req = _seatTransferQueue[0];
  const msg = document.getElementById("seat-transfer-msg");
  if (msg) msg.textContent = `${req.requester_name} wants to take control of ${req.target}. Give it up?`;
  overlay.style.display = "flex";

  const acceptBtn = document.getElementById("seat-transfer-accept");
  const denyBtn   = document.getElementById("seat-transfer-deny");
  // Rebind (clone to clear old listeners)
  const newAccept = acceptBtn.cloneNode(true);
  const newDeny   = denyBtn.cloneNode(true);
  acceptBtn.replaceWith(newAccept);
  denyBtn.replaceWith(newDeny);
  newAccept.onclick = () => _handleSeatTransfer(req.target, true);
  newDeny.onclick   = () => _handleSeatTransfer(req.target, false);
}

async function _handleSeatTransfer(target, approve) {
  const overlay = document.getElementById("seat-transfer-overlay");
  if (overlay) overlay.style.display = "none";
  _seatTransferQueue = _seatTransferQueue.filter(r => r.target !== target);
  try {
    const res  = await fetch("/handle_seat_transfer", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target, approve }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
  _processSeatTransferQueue();
}

function _syncSeatTransfers(transfers) {
  // Merge incoming server list into queue (add new, remove resolved)
  const incomingTargets = new Set((transfers || []).map(r => r.target));
  // Remove resolved
  _seatTransferQueue = _seatTransferQueue.filter(r => incomingTargets.has(r.target));
  // Add new
  for (const t of (transfers || [])) {
    if (!_seatTransferQueue.find(r => r.target === t.target)) {
      _seatTransferQueue.push(t);
    }
  }
  // Show modal only if not currently displaying one
  const overlay = document.getElementById("seat-transfer-overlay");
  if (overlay && overlay.style.display !== "flex") _processSeatTransferQueue();
}

async function handleRegistration(targetClientId, approve) {
  try {
    const res  = await fetch("/handle_registration", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        target_client_id: targetClientId, approve,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      applyState(data);
      // Refresh modal if it's open so sections update immediately
      const kickOverlay = document.getElementById("kick-overlay");
      if (kickOverlay && kickOverlay.style.display === "flex") openKickModal();
    }
  } catch (_) {}
}

async function doSpectate() {
  try {
    const res  = await fetch("/register", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, name: "" }),
    });
    const data = await res.json();
    myRole = ROLE.SPECTATOR;
    document.getElementById("register-overlay").style.display = "none";
    if (data.ok) applyState(data);
  } catch (_) {
    document.getElementById("register-overlay").style.display = "none";
  }
}

// ============================================================
// KICK
// ============================================================
function setAnimToggle(on) {
  lsSet("bjDealAnim", on ? "1" : "0");
  // Sync both pill toggles (checkbox + ON/OFF labels)
  [["anim-toggle", "anim-lbl-setup", "anim-lbl-setup-on"],
   ["anim-toggle-modal", "anim-lbl-modal", "anim-lbl-modal-on"]].forEach(([cbId, offId, onId]) => {
    const cb = document.getElementById(cbId);
    if (cb) cb.checked = on;
    const lblOff = document.getElementById(offId);
    const lblOn  = document.getElementById(onId);
    if (lblOff) lblOff.style.display = on ? "none"   : "inline";
    if (lblOn)  lblOn.style.display  = on ? "inline" : "none";
  });
  // Admin pushes preference to server so new joiners inherit it
  if (myRole === ROLE.ADMIN && roomCode && clientId) {
    fetch("/set_anim_pref", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, enabled: on }),
    }).catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Per-player stake panel (stake window after Deal, normal/digital mode only)
// ---------------------------------------------------------------------------

function _updateBetPanel(state, isPreDeal) {
  const panel     = document.getElementById("dig-bet-panel");
  const container = document.getElementById("dig-bet-steppers");
  if (!panel || !container) return;

  const isDrinking = state.drinking_mode;
  const isDigital  = state.mode === "digital";

  const tableMap = {};
  (state.table || []).forEach(p => { tableMap[p.name.toLowerCase()] = p; });
  // Bots keep their stake locked, so only human seats get a stepper.
  const mine = myNames.filter(n => {
    const p = tableMap[n.toLowerCase()];
    return p && !p.is_npc;
  });

  // Only while the stake window is open -- never at round-over, so the payout
  // screen stays readable until the next Deal.
  const show = isPreDeal && !!state.stake_window_open && isDigital && !isDrinking && mine.length > 0;
  panel.style.display = show ? "block" : "none";
  if (!show) return;

  const countdown = document.getElementById("dig-bet-countdown");
  if (countdown) countdown.textContent = Math.min(15, state.stake_window_seconds_left || 0);
  const accept = document.getElementById("dig-bet-accept");
  if (accept) {
    const confirmed = (state.stake_confirmed || []).map(n => n.toLowerCase());
    const accepted  = mine.every(n => confirmed.includes(n.toLowerCase()));
    accept.disabled    = accepted;
    accept.textContent = accepted ? "✓ Accepted — waiting for the others" : "✓ Accept stake";
  }

  const defaultBet = state.bet_amount || 5;

  // Only rebuild if seats or bets changed (avoid clobbering in-progress steppers)
  const existing = container.querySelectorAll(".player-bet-stepper");
  const needsRebuild = existing.length !== mine.length ||
    mine.some((n, i) => {
      const el = existing[i];
      return !el || el.dataset.seatName !== n;
    });

  if (!needsRebuild) {
    // Still sync displayed value from server state (another client could have polled)
    mine.forEach(n => {
      const p   = tableMap[n.toLowerCase()];
      const val = p ? (p.player_bet || defaultBet) : defaultBet;
      const row = container.querySelector(`.player-bet-stepper[data-seat-name='${n}']`);
      if (!row) return;
      // Only update if the stepper isn't actively being changed (no pending fetch)
      if (!row.dataset.pending) {
        row.dataset.value = val;
        const disp = row.querySelector(".bet-stepper-display");
        if (disp) disp.textContent = "$" + val.toFixed(2);
        _syncBetStepperLimits(row, val, defaultBet);
      }
    });
    return;
  }

  container.innerHTML = "";
  mine.forEach(name => {
    const p   = tableMap[name.toLowerCase()];
    const val = p ? (p.player_bet || defaultBet) : defaultBet;
    const min = 2.5;
    const max = defaultBet * 20;
    const step = 2.5;

    const row = document.createElement("div");
    row.className = "player-bet-stepper";
    row.dataset.seatName = name;
    row.dataset.value    = val;
    row.style.cssText    = "display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px";

    row.innerHTML = `
      <span style="font-size:13px;font-weight:600;min-width:60px">${escapeHtml(name)}</span>
      <div style="display:flex;align-items:center;gap:6px">
        <button class="btn btn-sm bet-stepper-dec" style="width:32px;height:32px;padding:0;font-size:16px">−</button>
        <span class="bet-stepper-display" style="min-width:60px;text-align:center;font-size:14px;font-weight:600">$${val.toFixed(2)}</span>
        <button class="btn btn-sm bet-stepper-inc" style="width:32px;height:32px;padding:0;font-size:16px">+</button>
      </div>
    `;

    _syncBetStepperLimits(row, val, defaultBet);

    row.querySelector(".bet-stepper-dec").addEventListener("click", () => _changeBet(row, -step, min, max, step, name));
    row.querySelector(".bet-stepper-inc").addEventListener("click", () => _changeBet(row, +step, min, max, step, name));
    container.appendChild(row);
  });
}

function _syncBetStepperLimits(row, val, defaultBet) {
  const min = 2.5;
  const max = defaultBet * 20;
  const dec = row.querySelector(".bet-stepper-dec");
  const inc = row.querySelector(".bet-stepper-inc");
  if (dec) dec.disabled = val <= min;
  if (inc) inc.disabled = val >= max;
}

function _changeBet(row, delta, min, max, step, playerName) {
  let val = parseFloat(row.dataset.value) || 0;
  val = Math.round((val + delta) / step) * step;
  val = Math.max(min, Math.min(max, val));
  val = Math.round(val * 100) / 100;

  row.dataset.value = val;
  const disp = row.querySelector(".bet-stepper-display");
  if (disp) disp.textContent = "$" + val.toFixed(2);
  _syncBetStepperLimits(row, val, lastState ? lastState.bet_amount : 5);

  // Mark pending so poll doesn't overwrite mid-flight
  row.dataset.pending = "1";
  setPlayerBet(playerName, val).finally(() => { delete row.dataset.pending; });
}

async function confirmStake() {
  if (!roomCode || !clientId) return;
  try {
    const res = await fetch("/confirm_stake", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

async function setPlayerBet(playerName, bet) {
  if (!roomCode || !clientId) return;
  try {
    const res = await fetch("/set_player_bet", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, player_name: playerName, bet }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}
