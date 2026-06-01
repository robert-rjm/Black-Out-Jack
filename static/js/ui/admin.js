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
  const phase        = state.phase;
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

async function castBustVote() {
  // Toggle: if already voted bust, cancel (send "none"); otherwise vote "bust"
  const current = lastState && lastState.my_bust_vote;
  const vote    = current === "bust" ? "none" : "bust";
  try {
    const res  = await fetch("/cast_bust_vote", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, vote }),
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

function updateBustVoteUI(state) {
  const panel    = document.getElementById("bust-vote-panel");
  const statusEl = document.getElementById("bust-vote-status");

  if (!panel) return;
  const enabled = state.bust_vote_enabled;
  const phase   = state.phase;

  // Show to any registered non-spectator once a round is active
  const showPanel = enabled
    && myRole !== null
    && myRole !== "spectator"
    && phase !== "pre-deal";

  panel.style.display = showPanel ? "block" : "none";
  if (!showPanel) return;

  // Highlight button when voted
  const myVote = state.my_bust_vote;
  const btn    = document.querySelector(".bust-btn-bust");
  if (btn) btn.classList.toggle("voted", myVote === "bust");

  if (!statusEl) return;
  const votes   = state.bust_votes || {};
  const bustCnt = Object.values(votes).filter(v => v === "bust").length;

  if (phase === "round-over") {
    const result = state.bust_vote_result;
    if (!myVote) {
      statusEl.textContent = bustCnt ? `${bustCnt} voted bust this round.` : "";
    } else if (result) {
      const won = result.winners.includes(myName);
      const cls = won ? "bust-vote-result-correct" : "bust-vote-result-wrong";
      const msg = won ? "✓ Called it — -1 sip!" : "✗ Wrong call — +1 sip";
      statusEl.innerHTML = `<span class="${cls}">${msg}</span>`;
    }
  } else {
    statusEl.textContent = bustCnt
      ? `${bustCnt} player${bustCnt !== 1 ? "s" : ""} betting bust`
      : (myVote === "bust" ? "You're betting dealer busts" : "");
  }
}

function showBustVoteToast(result) {
  if (!result) return;
  const toast = document.getElementById("player-toast");
  if (!toast) return;
  const parts = [];
  if (result.dealer_busted) {
    if (result.winners.length) parts.push(`✅ ${result.winners.join(", ")} called dealer bust (-1 sip each)`);
    if (result.losers.length)  parts.push(`❌ ${result.losers.join(", ")} wrong (+1 sip each)`);
  } else {
    if (result.losers.length)  parts.push(`❌ ${result.losers.join(", ")} bet on bust — wrong (+1 sip each)`);
    if (result.winners.length) parts.push(`✅ ${result.winners.join(", ")} called no bust (-1 sip each)`);
  }
  if (!parts.length) return;
  toast.textContent = parts.join(" · ");
  toast.classList.remove("show");
  void toast.offsetWidth;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 6000);
}

// ============================================================
// REGISTRATION
// ============================================================
function updateRegisterOverlay(state) {
  const overlay = document.getElementById("register-overlay");
  if (!overlay) return;
  // Show only when the server says we're not yet registered
  if (!state.my_role) {
    showRegisterOverlay(state);
  } else {
    overlay.style.display = "none";
  }
}

function showRegisterOverlay(state) {
  const overlay  = document.getElementById("register-overlay");
  const seatsEl  = document.getElementById("register-seats");
  if (!overlay || !seatsEl) return;

  const clients       = state.connected_clients || [];
  const claimedLower  = new Set(clients.map(c => c.name).filter(Boolean).map(n => n.toLowerCase()));
  const allSeats      = state.players || [];
  const available     = allSeats.filter(n => !claimedLower.has(n.toLowerCase()));

  seatsEl.innerHTML = "";
  if (available.length === 0) {
    seatsEl.innerHTML = `<p style="color:var(--muted);font-size:13px;padding:4px 0">All seats are taken — you can watch as spectator.</p>`;
  } else {
    available.forEach(name => {
      const btn   = document.createElement("button");
      btn.className   = "btn-big accent";
      btn.style.height = "52px";
      btn.textContent  = `I am ${name}`;
      btn.onclick      = () => doRegister(name);
      seatsEl.appendChild(btn);
    });
  }
  overlay.style.display = "flex";
}

async function doRegister(name) {
  const errEl = document.getElementById("register-error");
  try {
    const res  = await fetch("/register", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, name }),
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById("register-overlay").style.display = "none";
      applyState(data);
    } else {
      if (errEl) { errEl.textContent = data.error || "Could not claim seat."; errEl.style.display = "block"; }
    }
  } catch (_) {
    if (errEl) { errEl.textContent = "Network error."; errEl.style.display = "block"; }
  }
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

function openKickModal() {
  const overlay = document.getElementById("kick-overlay");
  const list    = document.getElementById("kick-list");
  if (!overlay || !list || !lastState) return;

  // Sync animation toggle to current setting
  const cb = document.getElementById("anim-toggle-modal");
  if (cb) cb.checked = lsGet("bjDealAnim") !== "0";

  const clients      = lastState.connected_clients || [];
  const tablePlayers = lastState.table || [];
  const connectedSet = new Set(clients.map(c => (c.name || "").toLowerCase()));
  const adminNames   = new Set(clients.filter(c => c.role === "admin").map(c => (c.name || "").toLowerCase()));
  const myNameLc   = (myName || "").toLowerCase();
  const kickVotes  = (lastState && lastState.kick_votes) || {};
  const isAdmin    = myRole === "admin";

  list.innerHTML = "";

  // Collect all seats (excluding self) plus spectators not in seats
  const seatedNames = new Set(tablePlayers.map(s => s.name.toLowerCase()));
  const rows = [];

  tablePlayers.forEach(seat => {
    if (seat.name.toLowerCase() === myNameLc) return;
    rows.push({ name: seat.name, isBot: !!seat.is_npc,
                connected: connectedSet.has(seat.name.toLowerCase()), seated: true });
  });

  clients.forEach(c => {
    if (!c.name || c.name.toLowerCase() === myNameLc) return;
    if (seatedNames.has(c.name.toLowerCase())) return;
    rows.push({ name: c.name, isBot: false, connected: true, seated: false, spectator: true });
  });

  if (rows.length === 0) {
    list.innerHTML = `<p style="color:var(--muted);font-size:13px;padding:8px 0">No other players in session.</p>`;
  } else {
    rows.forEach(r => {
      const row      = document.createElement("div");
      row.className  = "kick-row";
      const votes    = kickVotes[r.name.toLowerCase()] || 0;
      const voteTxt  = votes > 0 ? ` <span style="color:var(--red);font-size:11px">(${votes} vote${votes>1?"s":""})</span>` : "";
      const statusTxt = r.isBot ? " 🤖 bot"
                      : r.spectator ? " (spectating)"
                      : !r.connected ? " (disconnected)" : "";
      row.innerHTML  = `<span><span class="kick-name">${escapeHtml(r.name)}</span><span class="kick-role">${escapeHtml(statusTxt)}</span>${voteTxt}</span><span style="display:flex;gap:4px"></span>`;
      const btns = row.querySelector("span:last-child");

      const isAdminRow = adminNames.has(r.name.toLowerCase());
      const isSelf = myNameLc && r.name.toLowerCase() === myNameLc;
      if (isAdmin) {
        // Admin controls: bot + kick (never shown for self)
        if (r.seated && !r.isBot && !isSelf) {
          const botBtn       = document.createElement("button");
          botBtn.className   = "btn";
          botBtn.textContent = "🤖 Bot";
          botBtn.title       = "Auto-play for this player";
          botBtn.onclick     = () => doMakeBot(r.name);
          btns.appendChild(botBtn);
        }
        if (r.connected && !r.isBot && !isSelf) {
          const kickBtn       = document.createElement("button");
          kickBtn.className   = "btn kick-btn";
          kickBtn.textContent = "Kick";
          kickBtn.onclick     = () => doKick(r.name);
          btns.appendChild(kickBtn);
        }
      } else {
        // Player controls: vote to kick (never allowed against the admin)
        if (r.connected && !r.isBot && !isAdminRow) {
          const myVoted      = (lastState.kick_votes_mine || []).includes(r.name.toLowerCase());
          const voteBtn      = document.createElement("button");
          voteBtn.className  = "btn" + (myVoted ? " kick-btn" : "");
          voteBtn.textContent = myVoted ? "✗ Un-vote" : "Vote Kick";
          voteBtn.onclick    = () => doVoteKick(r.name);
          btns.appendChild(voteBtn);
        }
      }
      list.appendChild(row);
    });
  }
  // Transfer admin section — admin only
  const transferSection = document.getElementById("transfer-admin-section");
  const transferList    = document.getElementById("transfer-admin-list");
  if (transferSection) transferSection.style.display = isAdmin ? "" : "none";
  if (transferList && isAdmin) {
    transferList.innerHTML = "";
    const candidates = rows.filter(r => r.connected && !r.isBot);
    if (candidates.length === 0) {
      transferList.innerHTML = `<p style="color:var(--muted);font-size:13px;padding:4px 0">No connected players to transfer to.</p>`;
    } else {
      candidates.forEach(r => {
        const row     = document.createElement("div");
        row.className = "kick-row";
        row.innerHTML = `<span><span class="kick-name">${escapeHtml(r.name)}</span><span class="kick-role">${r.spectator ? " (spectating)" : ""}</span></span>`;
        const btn      = document.createElement("button");
        btn.className  = "btn";
        btn.textContent = "👑 Make Admin";
        btn.onclick    = () => doTransferAdmin(r.name);
        row.appendChild(btn);
        transferList.appendChild(row);
      });
    }
  }

  // Kicked players (admin only) — show with undo option
  let kickedSection = document.getElementById("kicked-players-section");
  if (!kickedSection) {
    kickedSection = document.createElement("div");
    kickedSection.id = "kicked-players-section";
    const kickCard = document.getElementById("kick-card");
    if (kickCard) kickCard.insertBefore(kickedSection, document.getElementById("game-settings-section").nextSibling || null);
  }
  const kickedClients = (isAdmin && lastState.kicked_clients) || [];
  if (isAdmin && kickedClients.length > 0) {
    kickedSection.style.display = "";
    kickedSection.innerHTML = `<div style="font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.05em;margin:14px 0 6px">🚫 KICKED PLAYERS</div>`;
    kickedClients.forEach(kc => {
      const row = document.createElement("div");
      row.className = "kick-row";
      row.innerHTML = `<span><span class="kick-name">${escapeHtml(kc.name)}</span><span class="kick-role"> (kicked)</span></span><span style="display:flex;gap:4px"></span>`;
      const btns = row.querySelector("span:last-child");
      const undoBtn = document.createElement("button");
      undoBtn.className   = "btn";
      undoBtn.textContent = "↩ Undo Kick";
      undoBtn.style.cssText = "background:rgba(62,207,110,.15);color:var(--green);border-color:rgba(62,207,110,.3)";
      undoBtn.onclick = () => doUndoKick(kc.client_id);
      btns.appendChild(undoBtn);
      kickedSection.appendChild(row);
    });
  } else if (kickedSection) {
    kickedSection.style.display = "none";
  }

  // Rejoin requests (admin only)
  let rejoinSection = document.getElementById("rejoin-requests-section");
  if (!rejoinSection) {
    rejoinSection = document.createElement("div");
    rejoinSection.id = "rejoin-requests-section";
    const kickCard = document.getElementById("kick-card");
    if (kickCard) kickCard.insertBefore(rejoinSection, document.getElementById("game-settings-section").nextSibling || null);
  }
  const rejoinReqs = (isAdmin && lastState.rejoin_requests) || [];
  if (isAdmin && rejoinReqs.length > 0) {
    rejoinSection.style.display = "";
    rejoinSection.innerHTML = `<div style="font-size:12px;font-weight:600;color:var(--yellow);letter-spacing:.05em;margin:14px 0 6px">🔄 REJOIN REQUESTS</div>`;
    rejoinReqs.forEach(req => {
      const row = document.createElement("div");
      row.className = "kick-row";
      row.innerHTML = `<span><span class="kick-name">${escapeHtml(req.display_name)}</span><span class="kick-role"> wants to rejoin</span></span><span style="display:flex;gap:4px"></span>`;
      const btns = row.querySelector("span:last-child");
      const approveBtn = document.createElement("button");
      approveBtn.className   = "btn";
      approveBtn.textContent = "✓ Allow";
      approveBtn.style.cssText = "background:rgba(62,207,110,.15);color:var(--green);border-color:rgba(62,207,110,.3)";
      approveBtn.onclick = () => doHandleRejoin(req.client_id, true);
      const denyBtn = document.createElement("button");
      denyBtn.className   = "btn kick-btn";
      denyBtn.textContent = "✗ Deny";
      denyBtn.onclick = () => doHandleRejoin(req.client_id, false);
      btns.appendChild(approveBtn);
      btns.appendChild(denyBtn);
      rejoinSection.appendChild(row);
    });
  } else if (rejoinSection) {
    rejoinSection.style.display = "none";
  }

  // Populate game settings section (admin only)
  if (lastState) _populateSettingsUI(lastState);

  overlay.style.display = "flex";
}

async function doTransferAdmin(targetName) {
  if (!confirm(`Transfer admin to ${targetName}?\nYou will lose admin controls.`)) return;
  try {
    const res  = await fetch("/transfer_admin", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target_name: targetName }),
    });
    const data = await res.json();
    if (data.ok) { closeKickModal(); applyState(data); }
    else         { alert(data.error || "Could not transfer admin."); }
  } catch (_) { alert("Network error."); }
}

async function doVoteKick(targetName) {
  try {
    const res  = await fetch("/vote_kick", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target_name: targetName }),
    });
    const data = await res.json();
    if (data.ok) {
      if (data.kicked) { closeKickModal(); }
      applyState(data);
      // Refresh the modal so vote counts and button states update
      if (!data.kicked) openKickModal();
    } else {
      alert(data.error || "Could not cast vote.");
    }
  } catch (_) { alert("Network error."); }
}

async function doMakeBot(targetName) {
  if (!confirm(`Convert ${targetName} to a bot?\nThey will auto-play for the rest of the session.`)) return;
  try {
    const res  = await fetch("/make_bot", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, player_name: targetName }),
    });
    const data = await res.json();
    if (data.ok) { closeKickModal(); applyState(data); }
    else         { alert(data.error || "Could not convert player to bot."); }
  } catch (_) { alert("Network error."); }
}

async function doKick(targetName) {
  if (!confirm(`Remove ${targetName} from the session?`)) return;
  try {
    const res  = await fetch("/kick", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target_name: targetName }),
    });
    const data = await res.json();
    if (data.ok) { closeKickModal(); }
    else         { alert(data.error || "Could not kick player."); }
  } catch (_) { alert("Network error."); }
}

async function doUndoKick(targetClientId) {
  try {
    const res  = await fetch("/undo_kick", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target_client_id: targetClientId }),
    });
    const data = await res.json();
    if (data.ok) { applyState(data); openKickModal(); }
    else         { alert(data.error || "Could not undo kick."); }
  } catch (_) { alert("Network error."); }
}

function closeKickModal() {
  const overlay = document.getElementById("kick-overlay");
  if (overlay) overlay.style.display = "none";
}

async function doHandleRejoin(targetClientId, approve) {
  try {
    const res  = await fetch("/handle_rejoin", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId,
                                target_client_id: targetClientId, approve }),
    });
    const data = await res.json();
    if (data.ok) { openKickModal(); applyState(data); }
    else         { alert(data.error || "Could not process request."); }
  } catch (_) { alert("Network error."); }
}

async function doRequestRejoin() {
  try {
    const res  = await fetch("/request_rejoin", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId,
                                display_name: myName || clientId.slice(0, 6) }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

// ============================================================
// KICK VOTE BANNER
// ============================================================
function renderKickVoteBanner(state) {
  let banner = document.getElementById("kick-vote-banner");
  if (!banner) return;
  const votes  = state.kick_votes_detail || {};
  const entries = Object.entries(votes).filter(([, voters]) => voters.length > 0);
  if (entries.length === 0) { banner.style.display = "none"; return; }
  banner.style.display = "block";
  banner.innerHTML = entries.map(([target, voters]) => {
    const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
    const who = voters.map(v => escapeHtml(cap(v))).join(", ");
    return `<span>&#128683; <b>${who}</b> vote${voters.length > 1 ? "s" : ""} to kick <b>${escapeHtml(cap(target))}</b></span>`;
  }).join("<br>");
}

// ============================================================
// RULES MODAL
// ============================================================
let _rulesCached = null;

async function openRulesModal() {
  const overlay = document.getElementById("rules-overlay");
  const body    = document.getElementById("rules-body");
  if (!overlay || !body) return;
  overlay.classList.add("open");

  if (_rulesCached) {
    body.innerHTML = _rulesCached;
    return;
  }

  body.innerHTML = '<span style="color:var(--muted);font-size:13px">Loading…</span>';
  try {
    const res  = await fetch(`/rules?_=${Date.now()}`);
    const data = await res.json();
    if (data.ok && typeof marked !== "undefined") {
      _rulesCached = DOMPurify.sanitize(marked.parse(data.content));
    } else if (data.ok) {
      // marked.js not loaded — plain text fallback
      _rulesCached = DOMPurify.sanitize(`<pre style="white-space:pre-wrap;font-size:12px">${data.content}</pre>`);
    } else {
      _rulesCached = '<span style="color:var(--red)">Could not load rules.</span>';
    }
    body.innerHTML = _rulesCached;
  } catch (_) {
    body.innerHTML = '<span style="color:var(--red)">Network error loading rules.</span>';
  }
}

function closeRulesModal() {
  const overlay = document.getElementById("rules-overlay");
  if (overlay) overlay.classList.remove("open");
}

function handleRulesBackdropClick(e) {
  if (e.target === document.getElementById("rules-overlay")) {
    closeRulesModal();
  }
}

// ============================================================
// ADMIN GAME SETTINGS
// ============================================================
function _populateSettingsUI(state) {
  // Show settings section only for admin
  const section = document.getElementById("game-settings-section");
  if (!section) return;
  if (myRole !== "admin") { section.style.display = "none"; return; }
  section.style.display = "block";

  // Populate current values
  const wagerEl    = document.getElementById("setting-wager");
  const handsEl    = document.getElementById("setting-num-hands");
  const decksEl    = document.getElementById("setting-num-decks");
  const decksRow   = document.getElementById("setting-decks-row");
  const removeEl   = document.getElementById("setting-remove-name");

  // Sync bust vote pill toggle
  const bustCb = document.getElementById("bust-vote-toggle-modal");
  if (bustCb) bustCb.checked = !!state.bust_vote_enabled;

  if (wagerEl)   wagerEl.value    = state.wager            || 1;
  if (handsEl)   handsEl.value    = state.num_hands         || 2;
  if (decksEl)   decksEl.value    = 1;
  if (decksRow)  decksRow.style.display = (state.mode === "digital") ? "flex" : "none";
  const rotateEl = document.getElementById("setting-rotate-every");
  if (rotateEl)  rotateEl.value  = state.dealer_rotate_every || 1;

  // Populate remove-player dropdown — exclude dealer seat and admin's own seat
  if (removeEl) {
    removeEl.innerHTML = "";
    const adminNameLc = (myName || "").toLowerCase();
    (state.table || []).forEach(seat => {
      if (seat.is_dealer) return;
      if (seat.name.toLowerCase() === adminNameLc) return;
      const opt = document.createElement("option");
      opt.value = seat.name;
      opt.textContent = seat.name + (seat.is_npc ? " 🤖" : "");
      removeEl.appendChild(opt);
    });
    if (!removeEl.options.length) {
      const opt = document.createElement("option");
      opt.value = ""; opt.textContent = "(no removable seats)";
      removeEl.appendChild(opt);
    }
  }

  // Show pending changes banner
  _renderQueuedBanner(state.queued_settings || {});
}

function _renderQueuedBanner(queued) {
  const banner = document.getElementById("queued-settings-banner");
  const list   = document.getElementById("queued-settings-list");
  if (!banner || !list) return;

  const items = [];
  if ("wager"     in queued) items.push(`Sips/hand → ${queued.wager}`);
  if ("num_hands" in queued) items.push(`Hands/player → ${queued.num_hands}`);
  if ("num_decks" in queued) items.push(`Decks → ${queued.num_decks}`);
  (queued.add_players    || []).forEach(p => items.push(`Add ${p.is_npc ? "bot" : "player"}: ${escapeHtml(p.name)}`));
  (queued.remove_players || []).forEach(n => items.push(`Remove player: ${escapeHtml(n)}`));

  if (items.length === 0) {
    banner.style.display = "none";
  } else {
    list.innerHTML = items.map(i => `<li>${i}</li>`).join("");
    banner.style.display = "block";
  }
}

async function queueSettings() {
  const wager    = parseInt(document.getElementById("setting-wager")?.value    || "1");
  const numHands = parseInt(document.getElementById("setting-num-hands")?.value || "2");
  const numDecks = parseInt(document.getElementById("setting-num-decks")?.value || "1");
  const mode     = lastState?.mode || "referee";

  const body = { room_code: roomCode, client_id: clientId, wager, num_hands: numHands };
  if (mode === "digital") body.num_decks = numDecks;

  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      lastState = data;
      _renderQueuedBanner(data.queued_settings || {});
    } else {
      alert(data.error || "Could not queue settings.");
    }
  } catch (_) { alert("Network error."); }
}

async function queueAddPlayer() {
  const nameEl = document.getElementById("setting-add-name");
  const npcEl  = document.getElementById("setting-add-npc");
  const name   = (nameEl?.value || "").trim();
  if (!name) { nameEl?.focus(); return; }

  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        room_code: roomCode, client_id: clientId,
        add_player: name, add_player_npc: npcEl?.checked || false,
      }),
    });
    const data = await res.json();
    if (data.ok) {
      lastState = data;
      if (nameEl) nameEl.value = "";
      if (npcEl)  npcEl.checked = false;
      _renderQueuedBanner(data.queued_settings || {});
    } else {
      alert(data.error || "Could not queue add player.");
    }
  } catch (_) { alert("Network error."); }
}

async function queueRemovePlayer() {
  const removeEl = document.getElementById("setting-remove-name");
  const name     = removeEl?.value;
  if (!name) return;

  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, remove_player: name }),
    });
    const data = await res.json();
    if (data.ok) {
      lastState = data;
      _renderQueuedBanner(data.queued_settings || {});
    } else {
      alert(data.error || "Could not queue remove player.");
    }
  } catch (_) { alert("Network error."); }
}

async function clearQueuedSettings() {
  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, clear_queued: true }),
    });
    const data = await res.json();
    if (data.ok) {
      lastState = data;
      _renderQueuedBanner({});
    }
  } catch (_) {}
}

async function saveRotateEvery() {
  const v = parseInt(document.getElementById("setting-rotate-every")?.value || "1");
  if (isNaN(v) || v < 1) return;
  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, dealer_rotate_every: v }),
    });
    const data = await res.json();
    if (data.ok) lastState = data;
    else alert(data.error || "Could not save.");
  } catch (_) { alert("Network error."); }
}

async function rotateDealer() {
  try {
    const res  = await fetch("/rotate_dealer", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    if (data.ok) { applyState(data); closeKickModal(); }
    else alert(data.error || "Could not rotate dealer.");
  } catch (_) { alert("Network error."); }
}

// ============================================================
// FINAL SUMMARY
// ============================================================
async function showSessionSummary() {
  const overlay = document.getElementById("summary-overlay");
  const meta    = document.getElementById("summary-meta");
  const body    = document.getElementById("summary-body");
  if (!overlay) return;

  meta.textContent = "Loading…";
  body.innerHTML   = "";
  overlay.style.display = "flex";

  try {
    const res  = await fetch(`/summary_json?room_code=${encodeURIComponent(roomCode)}&_=${Date.now()}`);
    const data = await res.json();

    if (!data.ok || !data.players || !data.players.length) {
      meta.textContent = "No drink data yet — play some rounds first.";
      return;
    }

    meta.textContent = `${data.rounds} round${data.rounds !== 1 ? "s" : ""} completed`;

    const tbl = document.createElement("table");
    tbl.id = "summary-table";
    tbl.innerHTML = `
      <thead><tr>
        <th>Player</th>
        <th>As player</th>
        <th>As dealer</th>
        <th>Total 🍺</th>
      </tr></thead>`;
    const tb = document.createElement("tbody");
    data.players.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td style="font-weight:600">${escapeHtml(p.name)}</td>
        <td>${p.player_sips}</td>
        <td>${p.dealer_sips}</td>
        <td class="sum-total">${p.total_sips}</td>`;
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    body.appendChild(tbl);
  } catch (_) {
    meta.textContent = "Could not load summary — check connection.";
  }
}

function closeSummaryModal() {
  const overlay = document.getElementById("summary-overlay");
  if (overlay) overlay.style.display = "none";
}

// ============================================================
// CSV EXPORT
// ============================================================
function exportDrinkCSV() {
  if (!roomCode) { alert("No active session."); return; }
  window.location.href = "/export_csv?room_code=" + encodeURIComponent(roomCode);
}

// ============================================================
// RESET
// ============================================================
function resetToSetup() {
  if (!confirm("End current session and return to lobby?")) return;
  stopPolling();
  roomCode         = "";
  myRole           = null;
  myName           = null;
  isMyDealerClient = false;
  lsRemove("bjRoomCode");
  document.getElementById("app").style.display    = "none";
  document.getElementById("setup").style.display  = "none";
  document.getElementById("lobby").style.display  = "flex";
  document.getElementById("log").innerHTML = "";
  document.getElementById("header-room").textContent = "";
  document.getElementById("join-code").value = "";
  hideLobbyMsg();
  players  = [];
  gameMode = "referee";
}

// ============================================================
