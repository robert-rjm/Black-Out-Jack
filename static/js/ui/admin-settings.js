function openKickModal() {
  const overlay = document.getElementById("kick-overlay");
  const list    = document.getElementById("kick-list");
  if (!overlay || !list || !lastState) return;

  // Sync animation toggle to current setting
  const cb = document.getElementById("anim-toggle-modal");
  if (cb) cb.checked = lsGet("bjDealAnim") !== "0";

  // GodMode toggle is admin-only — hide it for regular players
  const godRow = document.querySelector("#kick-overlay .kick-toggle-row:has(#god-mode-toggle-modal)");
  if (godRow) godRow.style.display = (myRole === "admin") ? "flex" : "none";

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
        // Take Back — only for remote (non-local) seated non-bot players
        if (r.seated && !r.isBot) {
          const currentLocals = (lastState && lastState.my_names) || [];
          const isLocal       = currentLocals.some(n => n.toLowerCase() === r.name.toLowerCase());
          if (!isLocal) {
            const tbBtn        = document.createElement("button");
            tbBtn.className    = "btn";
            tbBtn.textContent  = "Take Back";
            tbBtn.title        = "Reclaim this seat — move the remote player to spectator";
            tbBtn.style.cssText = "font-size:11px;padding:0 10px";
            tbBtn.onclick      = () => takeBackSeat(r.name);
            btns.appendChild(tbBtn);
          }
        }
        // Admin controls: bot / make-human + kick (never shown for self)
        if (r.seated && !r.isBot && !isSelf) {
          const botBtn       = document.createElement("button");
          botBtn.className   = "btn";
          botBtn.textContent = "🤖 Bot";
          botBtn.title       = "Auto-play for this player";
          botBtn.onclick     = () => doMakeBot(r.name);
          btns.appendChild(botBtn);
        }
        if (r.isBot) {
          const humanBtn       = document.createElement("button");
          humanBtn.className   = "btn";
          humanBtn.textContent = "👤 Human";
          humanBtn.title       = "Convert bot back to human-controlled";
          humanBtn.onclick     = () => doMakeHuman(r.name);
          btns.appendChild(humanBtn);
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

  // Pending registrations (admin only) — approve / deny
  let pendingRegSection = document.getElementById("pending-reg-modal-section");
  if (!pendingRegSection) {
    pendingRegSection = document.createElement("div");
    pendingRegSection.id = "pending-reg-modal-section";
    const kickCard = document.getElementById("kick-card");
    if (kickCard) kickCard.insertBefore(pendingRegSection, document.getElementById("game-settings-section").nextSibling || null);
  }
  const pendingRegs = (isAdmin && lastState.pending_registrations) || [];
  if (isAdmin && pendingRegs.length > 0) {
    pendingRegSection.style.display = "block";
    pendingRegSection.innerHTML = `<div style="font-size:12px;font-weight:600;color:var(--accent);letter-spacing:.05em;margin:14px 0 6px">🙋 WAITING TO JOIN</div>`;
    pendingRegs.forEach(r => {
      const row = document.createElement("div");
      row.className = "kick-row";
      row.innerHTML = `<span><span class="kick-name">${escapeHtml(r.name)}</span><span class="kick-role"> (waiting)</span></span><span style="display:flex;gap:4px"></span>`;
      const btns = row.querySelector("span:last-child");
      const acceptBtn = document.createElement("button");
      acceptBtn.className   = "btn";
      acceptBtn.textContent = "✓ Accept";
      acceptBtn.style.cssText = "background:rgba(62,207,110,.15);color:var(--green);border-color:rgba(62,207,110,.3)";
      acceptBtn.onclick = () => { handleRegistration(r.client_id, true); closeKickModal(); };
      const denyBtn = document.createElement("button");
      denyBtn.className   = "btn kick-btn";
      denyBtn.textContent = "✗ Deny";
      denyBtn.onclick = () => handleRegistration(r.client_id, false);
      btns.appendChild(acceptBtn);
      btns.appendChild(denyBtn);
      pendingRegSection.appendChild(row);
    });
  } else if (pendingRegSection) {
    pendingRegSection.style.display = "none";
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

  // Denied registrations (admin only) — show with "Allow back" option
  let deniedSection = document.getElementById("denied-reg-section");
  if (!deniedSection) {
    deniedSection = document.createElement("div");
    deniedSection.id = "denied-reg-section";
    const kickCard = document.getElementById("kick-card");
    if (kickCard) kickCard.insertBefore(deniedSection, document.getElementById("game-settings-section").nextSibling || null);
  }
  const deniedClients = (isAdmin && lastState.denied_clients) || [];
  if (isAdmin && deniedClients.length > 0) {
    deniedSection.style.display = "block";
    deniedSection.innerHTML = `<div style="font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.05em;margin:14px 0 6px">🚷 BLOCKED FROM JOINING</div>`;
    deniedClients.forEach(dc => {
      const row = document.createElement("div");
      row.className = "kick-row";
      row.innerHTML = `<span><span class="kick-name" style="color:var(--muted)">Unknown client</span><span class="kick-role"> (denied)</span></span><span style="display:flex;gap:4px"></span>`;
      const btns = row.querySelector("span:last-child");
      const allowBtn = document.createElement("button");
      allowBtn.className   = "btn";
      allowBtn.textContent = "↩ Allow back";
      allowBtn.style.cssText = "background:rgba(62,207,110,.15);color:var(--green);border-color:rgba(62,207,110,.3)";
      allowBtn.onclick = () => doResetRegistration(dc.client_id);
      btns.appendChild(allowBtn);
      deniedSection.appendChild(row);
    });
  } else if (deniedSection) {
    deniedSection.style.display = "none";
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

async function doMakeHuman(targetName) {
  if (!confirm(`Convert ${targetName} back to a human player?\nThey will need to act manually on their turns.`)) return;
  try {
    const res  = await fetch("/make_human", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, player_name: targetName }),
    });
    const data = await res.json();
    if (data.ok) { closeKickModal(); applyState(data); }
    else         { alert(data.error || "Could not convert bot to player."); }
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

async function doResetRegistration(targetClientId) {
  try {
    const res  = await fetch("/reset_registration", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId, target_client_id: targetClientId }),
    });
    const data = await res.json();
    if (data.ok) { applyState(data); openKickModal(); }
    else         { alert(data.error || "Could not reset."); }
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
  // Bust vote pill toggle sync is handled by updateBustVoteUI — just sync checkbox here
  const bustCb2 = document.getElementById("bust-vote-toggle-modal");
  if (bustCb2) bustCb2.checked = !!state.bust_vote_enabled;
  const easyModalCb = document.getElementById("easy-mode-toggle-modal");
  const easyModalOff = document.getElementById("easy-mode-lbl-modal");
  const easyModalOn  = document.getElementById("easy-mode-lbl-modal-on");
  const easyOn = !!state.easy_mode;
  if (easyModalCb) easyModalCb.checked = easyOn;
  if (easyModalOff) easyModalOff.style.display = easyOn ? "none"   : "inline";
  if (easyModalOn)  easyModalOn.style.display  = easyOn ? "inline" : "none";
  const godCb = document.getElementById("god-mode-toggle-modal");
  if (godCb) godCb.checked = !!state.god_mode_enabled;
  const godLblOff = document.getElementById("god-mode-lbl-off");
  const godLblOn  = document.getElementById("god-mode-lbl-on");
  if (godLblOff) godLblOff.style.display = state.god_mode_enabled ? "none"   : "inline";
  if (godLblOn)  godLblOn.style.display  = state.god_mode_enabled ? "inline" : "none";

  if (wagerEl)   wagerEl.value    = state.wager            || 1;
  if (handsEl)   handsEl.value    = state.num_hands         || 2;
  if (decksEl)   decksEl.value    = state.num_decks || 1;
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
      applyState(data);
      _renderQueuedBanner(data.queued_settings || {});
    } else {
      alert(data.error || "Could not queue settings.");
    }
  } catch (_) { alert("Network error."); }
}

async function takeBackSeat(playerName) {
  if (!confirm(`Take back ${playerName}'s seat?\nThey will become a spectator and you will control this seat locally.`)) return;
  try {
    const res  = await fetch("/take_back_seat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, player_name: playerName }),
    });
    const data = await res.json();
    if (data.ok) { applyState(data); openKickModal(); }
    else alert(data.error || "Could not take back seat.");
  } catch (_) { alert("Network error."); }
}

async function queueAddPlayer() {
  const nameEl = document.getElementById("setting-add-name");
  const npcEl  = document.getElementById("setting-add-npc");
  const name   = (nameEl?.value || "").trim();
  if (!name) { nameEl?.focus(); return; }

  const isNpc = npcEl?.checked || false;

  // Non-bot players are always local by default — local_names is updated
  // automatically when apply_queued_settings runs (lobby.py style: all non-NPCs).
  // No special handling needed here.
  const body = {
    room_code: roomCode, client_id: clientId,
    add_player: name, add_player_npc: isNpc,
  };

  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) {
      applyState(data);
      if (nameEl) nameEl.value  = "";
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
      applyState(data);
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
      applyState(data);
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
    if (data.ok) applyState(data);
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
  // Notify server so admin role is transferred and client is removed
  if (roomCode) {
    const blob = new Blob([JSON.stringify({ room_code: roomCode, client_id: clientId })], { type: "application/json" });
    navigator.sendBeacon("/leave_room", blob);
  }
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
