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
  if (dealerActions) dealerActions.style.display = isMyDealerClient ? "block" : "none";
  if (waitingHint)   waitingHint.style.display   = (isMyDealerClient || myRole === "spectator") ? "none" : "block";

  const hint         = document.getElementById("dig-play-role-hint");
  const voteDisp     = document.getElementById("player-vote-display");
  const suggestBanner= document.getElementById("suggest-banner");
  const suggestText  = document.getElementById("suggest-text");
  const suggestPicker= document.getElementById("suggest-picker");
  const suggestToggle= document.getElementById("suggest-toggle-row");
  const predealPanel = document.getElementById("dig-predeal-panel");
  const phase        = state.phase;

  // Show waiting-room deal panel only in pre-deal for the dealer client
  if (predealPanel) {
    predealPanel.style.display = (phase === "pre-deal" && isMyDealerClient) ? "block" : "none";
  }
  const turn         = state.current_turn;
  const presel       = state.preselections || {};
  const suggestions  = state.suggestions   || {};

  const actionSel = "#dig-action-row1 .btn, #dig-action-row2 .btn";

  // Clear all highlights
  document.querySelectorAll("#dig-action-row1 .btn.voted,       #dig-action-row2 .btn.voted").forEach(b => b.classList.remove("voted"));
  document.querySelectorAll("#dig-action-row1 .btn.voted-dealer, #dig-action-row2 .btn.voted-dealer").forEach(b => b.classList.remove("voted-dealer"));

  // Hide suggest UI by default
  if (suggestBanner) suggestBanner.style.display = "none";
  if (suggestPicker) suggestPicker.style.display  = "none";
  if (suggestToggle) suggestToggle.style.display  = "none";
  if (voteDisp)      voteDisp.style.display       = "none";

  // Role hint
  if (hint) {
    if (isMyDealerClient)       hint.textContent = phase === "playing" ? "You are the dealer — execute the player's vote." : "";
    else if (myRole === "player") hint.textContent = phase === "playing" ? "Tap to vote your play — dealer carries it out." : "";
    else                          hint.textContent = "Spectating — watching only.";
  }

  // Spectators: disable everything and stop
  if (myRole === "spectator" || !myRole) {
    document.querySelectorAll(actionSel).forEach(b => b.classList.add("disabled"));
    return;
  }

  if (phase !== "playing" || !turn) return;

  // ── DEALER VIEW ──────────────────────────────────────────────
  if (isMyDealerClient) {
    const hand = (sel.digital.hand || "hand1").toLowerCase();
    const key  = `${turn.toLowerCase()}:${hand}`;
    const vote = presel[key];

    if (voteDisp) {
      voteDisp.textContent   = vote ? `${turn} voted: ${VOTE_LABEL[vote]}` : `${turn} — no vote yet`;
      voteDisp.style.display = "block";
    }

    if (vote) {
      // Lock dealer to voted action; highlight it yellow
      document.querySelectorAll(actionSel).forEach(b => {
        const lbl = b.textContent.trim();
        if (lbl === VOTE_LABEL[vote]) {
          b.classList.add("voted-dealer");
          b.classList.remove("disabled");
        } else if (["HIT","STAND","DOUBLE","SPLIT"].includes(lbl)) {
          b.classList.add("disabled");
        }
      });
      // Show suggest-different toggle
      if (suggestToggle) suggestToggle.style.display = "block";
      if (suggestPicker) suggestPicker.style.display = _suggestPickerOpen ? "block" : "none";
    }
    // No vote → all buttons available; split/double still gated by updateActionButtons

  // ── PLAYER VIEW ──────────────────────────────────────────────
  } else if (myRole === "player") {
    const isMyTurn = myName && turn.toLowerCase() === myName.toLowerCase();

    // Not your turn → grey everything out, done
    if (!isMyTurn) {
      document.querySelectorAll(actionSel).forEach(b => b.classList.add("disabled"));
      return;
    }

    const hand       = (sel.digital.hand || "hand1").toLowerCase();
    const key        = `${myName.toLowerCase()}:${hand}`;
    const vote       = presel[key];
    const suggestion = suggestions[key];

    // Incoming dealer suggestion: show banner + highlight that button yellow
    if (suggestion) {
      if (suggestBanner && suggestText) {
        suggestText.textContent = `Dealer suggests: ${VOTE_LABEL[suggestion] || suggestion} — do you agree?`;
        suggestBanner.style.display = "block";
      }
      document.querySelectorAll(actionSel).forEach(b => {
        if (b.textContent.trim() === VOTE_LABEL[suggestion]) b.classList.add("voted-dealer");
      });
    }

    if (voteDisp) {
      if (vote) {
        document.querySelectorAll(actionSel).forEach(b => {
          if (b.textContent.trim() === VOTE_LABEL[vote]) b.classList.add("voted");
        });
        voteDisp.textContent = `Your vote: ${VOTE_LABEL[vote]} — waiting for dealer`;
      } else {
        voteDisp.textContent = "Tap to vote your play";
      }
      voteDisp.style.display = "block";
    }
  }
}

// ============================================================
// BUST VOTE SIDE BET
// ============================================================

let _bustVoteModalOpen   = false;
let _bustVoteTimerHandle = null;

async function submitBustVote(choice, playerName) {
  // For single-player: pass no playerName (server uses primary name).
  // For local multiplayer: pass the specific player's name.
  const body = { room_code: roomCode, client_id: clientId, vote: choice };
  if (playerName) body.player_name = playerName;
  try {
    const res  = await fetch("/cast_bust_vote", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

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

function _openBustVoteModal(secondsLeft) {
  const overlay = document.getElementById("bust-vote-modal-overlay");
  if (!overlay || _bustVoteModalOpen) return;
  _bustVoteModalOpen    = true;
  overlay.style.display = "flex";

  const bar      = document.getElementById("bust-vote-timer-bar");
  const label    = document.getElementById("bust-vote-timer-label");
  const duration = secondsLeft || 15;   // guard against 0

  let secs = duration;
  function tick() {
    if (!_bustVoteModalOpen) return;
    const display = Math.min(secs, 15);
    if (bar)   bar.style.width   = `${(display / 15) * 100}%`;
    if (label) label.textContent = `${display}s`;
    if (secs <= 0) {
      // Auto-pass for all un-voted local players
      const bustVotes = (lastState && lastState.my_bust_votes) || {};
      const unvoted   = myNames.filter(n => !bustVotes[n]);
      if (unvoted.length) {
        // Submit pass for each unvoted player sequentially; close after last
        (async () => {
          for (const name of unvoted) await submitBustVote("pass", name);
          _closeBustVoteModal();
        })();
      } else {
        _closeBustVoteModal();
      }
      return;
    }
    secs--;
    _bustVoteTimerHandle = setTimeout(tick, 1000);
  }
  tick();
}

// Render per-player vote cards inside the modal.
// Called whenever state updates while the modal is open.
function _renderBustVoteCards(state) {
  const wrap = document.getElementById("bust-vote-players-wrap");
  if (!wrap) return;

  const bustVotes = state.my_bust_votes || {};
  // Only show human local players active in the game (skip NPCs)
  const npcSet   = new Set([...(npcPlayers || [])]);
  const locals   = myNames.filter(n => !npcSet.has(n));
  const multiLocal = locals.length > 1;

  wrap.innerHTML = "";
  locals.forEach(name => {
    const voted = bustVotes[name];
    const card  = document.createElement("div");
    card.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px solid var(--border)";

    if (multiLocal) {
      const nameLbl = document.createElement("span");
      nameLbl.style.cssText = "font-size:14px;font-weight:700;min-width:60px;color:var(--text)";
      nameLbl.textContent = name;
      card.appendChild(nameLbl);
    }

    if (voted) {
      // Already voted — show status
      const statusEl = document.createElement("span");
      statusEl.style.cssText = `font-size:13px;color:${voted === "bust" ? "var(--red)" : "var(--muted)"};font-weight:600`;
      statusEl.textContent   = voted === "bust" ? "💥 Bet Bust" : "Passed";
      card.appendChild(statusEl);
    } else {
      // Buttons
      const btns = document.createElement("div");
      btns.style.cssText = "display:flex;gap:8px;flex:1";

      const bustBtn = document.createElement("button");
      bustBtn.className   = "btn green";
      bustBtn.style.cssText = "flex:1";
      bustBtn.textContent = "💥 Bet Bust";
      bustBtn.onclick     = () => submitBustVote("bust", multiLocal ? name : undefined);

      const passBtn = document.createElement("button");
      passBtn.className   = "btn muted-btn";
      passBtn.style.cssText = "flex:1";
      passBtn.textContent = "Pass";
      passBtn.onclick     = () => submitBustVote("pass", multiLocal ? name : undefined);

      btns.appendChild(bustBtn);
      btns.appendChild(passBtn);
      card.appendChild(btns);
    }

    wrap.appendChild(card);
  });
}

function _closeBustVoteModal() {
  if (!_bustVoteModalOpen) return;
  _bustVoteModalOpen = false;
  if (_bustVoteTimerHandle) { clearTimeout(_bustVoteTimerHandle); _bustVoteTimerHandle = null; }
  const overlay = document.getElementById("bust-vote-modal-overlay");
  if (overlay) overlay.style.display = "none";
}

function updateBustVoteUI(state) {
  // Sync modal pill toggle in settings (checkbox + ON/OFF labels)
  const bustCb = document.getElementById("bust-vote-toggle-modal");
  if (bustCb) {
    const on = !!state.bust_vote_enabled;
    bustCb.checked = on;
    const lblOff = document.getElementById("bust-vote-lbl-modal");
    const lblOn  = document.getElementById("bust-vote-lbl-modal-on");
    if (lblOff) lblOff.style.display = on ? "none"   : "inline";
    if (lblOn)  lblOn.style.display  = on ? "inline" : "none";
  }

  const statusEl = document.getElementById("bust-vote-status");

  // Modal: open when window is open and any local player hasn't voted yet.
  // Delay until deal animation finishes so the modal doesn't cover the cards.
  const bustVotes  = state.my_bust_votes || {};
  const anyUnvoted = Object.values(bustVotes).some(v => v === null || v === undefined);
  if (state.bust_vote_window_open && anyUnvoted
      && myRole !== null && myRole !== "spectator"
      && !_dealAnimating) {
    _openBustVoteModal(state.bust_vote_seconds_left || 15);
  } else if (!state.bust_vote_window_open) {
    _closeBustVoteModal();
  }

  // Re-render player cards while modal is open (handles partial local votes)
  if (_bustVoteModalOpen) {
    _renderBustVoteCards(state);
    // Update tally
    const votes   = state.bust_votes || {};
    const decided = Object.keys(votes).length;
    const bustCnt = Object.values(votes).filter(v => v === "bust").length;
    const tally   = document.getElementById("bust-vote-modal-tally");
    if (tally) tally.textContent = decided
      ? `${bustCnt} betting bust · ${decided - bustCnt} passed`
      : "";
    // Auto-close if all local players have now voted
    if (!anyUnvoted) _closeBustVoteModal();
  }

  // Give-panel: show at round-over if this client has pending handouts
  _renderBustGivePanel(state);

  // Status indicator: show after window closes.
  // For local multiplayer, represent as a summary across all local names.
  if (!statusEl) return;
  const phase  = state.phase;
  const myVote = state.my_bust_vote;   // primary player's vote (backward compat)
  const show   = state.bust_vote_enabled
    && myRole !== null && myRole !== "spectator"
    && phase !== "pre-deal"
    && !state.bust_vote_window_open;

  statusEl.style.display = show ? "block" : "none";
  if (!show) return;

  const allVotes = state.bust_votes || {};
  const bustCnt  = Object.values(allVotes).filter(v => v === "bust").length;
  const myBusters = myNames.filter(n => bustVotes[n] === "bust");

  if (phase === "round-over") {
    const result = state.bust_vote_result;
    if (!myBusters.length) {
      statusEl.textContent = bustCnt ? `${bustCnt} bet on bust this round.` : "";
    } else if (result) {
      const winners    = result.winners || [];
      const myWinners  = myBusters.filter(n => winners.includes(n));
      const myLosers   = myBusters.filter(n => !winners.includes(n));
      const parts = [];
      if (myWinners.length) parts.push(`<span class="bust-vote-result-correct">✓ ${myWinners.join(", ")} called it — -1 sip + give 1!</span>`);
      if (myLosers.length)  parts.push(`<span class="bust-vote-result-wrong">✗ ${myLosers.join(", ")} wrong — +1 sip each</span>`);
      statusEl.innerHTML = parts.join("<br>");
    } else {
      // Result not yet available — re-render from current state to avoid stale text
      statusEl.textContent = bustCnt ? `${bustCnt} bet on bust this round.` : "";
    }
  } else {
    const allBusters = Object.entries(allVotes)
      .filter(([, v]) => v === "bust")
      .map(([n]) => n);
    if (allBusters.length) {
      const label = allBusters.length === 1
        ? `💥 ${allBusters[0]} bet dealer busts`
        : `💥 ${allBusters.join(" & ")} bet dealer busts`;
      statusEl.innerHTML = `<span style="color:var(--red);font-weight:700">${label}</span>`;
    } else if (myVote === "pass") {
      statusEl.textContent = "You passed the bust bet.";
    } else {
      statusEl.textContent = "";
    }
  }
}

async function giveBustSip(winnerName, recipientName) {
  try {
    const res  = await fetch("/give_bust_sip", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        winner_name: winnerName, recipient_name: recipientName,
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    else appendLog(`  Bust handout failed: ${data.error || "unknown"}\n`);
  } catch (_) {}
}

function _renderBustGivePanel(state) {
  const overlay = document.getElementById("bust-give-overlay");
  const body    = document.getElementById("bust-give-body");
  if (!overlay || !body) return;

  const pending = state.my_bust_handout_pending || [];
  if (!pending.length) {
    overlay.style.display = "none";
    body.innerHTML = "";
    return;
  }

  const allPlayers = (state.players || []);
  overlay.style.display = "flex";

  body.innerHTML = pending.map(winnerName => {
    const label  = pending.length > 1
      ? `🎉 <strong>${escapeHtml(winnerName)}</strong> called it! Give 1 sip to:`
      : "🎉 You called it! Give 1 sip to:";
    const btns   = allPlayers
      .filter(n => n.toLowerCase() !== winnerName.toLowerCase())
      .map(n => `<button class="btn wide" style="margin-bottom:8px"
          data-winner="${escapeHtml(winnerName)}" data-recipient="${escapeHtml(n)}"
          onclick="giveBustSip(this.dataset.winner, this.dataset.recipient)"
          >${escapeHtml(n)}</button>`)
      .join("");
    return `<div style="margin-bottom:${pending.length > 1 ? 16 : 0}px">
      <div style="font-size:15px;font-weight:700;color:var(--green);margin-bottom:14px;text-align:center">${label}</div>
      <div style="display:flex;flex-direction:column">${btns}</div>
    </div>`;
  }).join(`<hr style="border-color:var(--border);margin:8px 0">`);
}

function showBustVoteToast(result) {
  if (!result) return;
  const toast = document.getElementById("player-toast");
  if (!toast) return;
  const parts = [];
  if (result.dealer_busted) {
    if (result.winners.length) parts.push(`✅ ${result.winners.join(", ")} called it (-1 sip + give 1)`);
    if (result.losers.length)  parts.push(`❌ ${result.losers.join(", ")} wrong (+1 sip each)`);
  } else {
    if (result.losers.length)  parts.push(`❌ ${result.losers.join(", ")} bet bust — wrong (+1 sip each)`);
  }
  if (!parts.length) return;
  toast.textContent = parts.join(" · ");
  toast.classList.remove("show");
  void toast.offsetWidth;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 6000);
}

function showInsuranceToast(results) {
  if (!results || !results.length) return;
  const toast = document.getElementById("player-toast");
  if (!toast) return;
  const parts = results.map(r => {
    const bj    = r.player;
    const voted = r.insured ? "Insure" : "Decline";
    const dBJ   = r.dealer_bj;
    let outcome, icon;
    if (r.group_won) {
      icon = "✅";
      if (r.insured && dBJ)       outcome = `dealer had BJ — BJ holder drinks own bonus, group safe`;
      else if (!r.insured && !dBJ) outcome = `no dealer BJ — normal BJ bonus`;
      else                         outcome = `correct call`;
    } else {
      icon = "❌";
      if (r.insured && !dBJ)      outcome = `no dealer BJ — group drinks double bonus`;
      else if (!r.insured && dBJ) outcome = `dealer had BJ — auto-insurance applies`;
      else                         outcome = `wrong call`;
    }
    return `${icon} Insurance (${bj}): voted ${voted} — ${outcome}`;
  });
  toast.textContent = parts.join(" · ");
  toast.classList.remove("show");
  void toast.offsetWidth;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 8000);
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
  renderPendingRegBanner(state);
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

function renderPendingRegBanner(state) {
  const banner = document.getElementById("pending-reg-banner");
  if (!banner) return;
  const pending = state.pending_registrations || [];
  if (!pending.length || myRole !== "admin") {
    banner.style.display = "none";
    banner.innerHTML = "";
    return;
  }
  banner.style.display = "block";
  banner.innerHTML = pending.map(r =>
    `<div class="pending-reg-row">
      <span class="pending-reg-name">🙋 ${escapeHtml(r.name)} wants to join</span>
      <span class="pending-reg-btns">
        <button class="btn green btn-sm" onclick="handleRegistration('${escapeHtml(r.client_id)}', true)">✓ Accept</button>
        <button class="btn red btn-sm"   onclick="handleRegistration('${escapeHtml(r.client_id)}', false)">✗ Deny</button>
      </span>
    </div>`
  ).join("");
}

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
    seatsEl.innerHTML = `<p style="color:var(--muted);font-size:13px;padding:4px 0">All seats are taken — you can watch as spectator.</p>`;
  } else {
    available.forEach(name => {
      const btn        = document.createElement("button");
      btn.className    = "btn-big accent";
      btn.style.height = "52px";
      btn.textContent  = `I am ${name}`;
      btn.onclick      = () => doRegister(name);
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
    myRole = "spectator";
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
  if (myRole === "admin" && roomCode && clientId) {
    fetch("/set_anim_pref", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, enabled: on }),
    }).catch(() => {});
  }
}

