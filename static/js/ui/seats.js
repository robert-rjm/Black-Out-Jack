// ============================================================
// SEATS & REGISTRATION
// ============================================================
// Which seat(s) this device controls and how it gets them: the multi-seat
// switcher, the join / register overlay, the host's approval banner, seat
// transfers and spectating. Split out of admin.js.

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
