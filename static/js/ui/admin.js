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
    predealPanel.style.display = (isPreDeal && isMyDealerClient) ? "block" : "none";
  }
  // Per-player bet panel: shown to non-dealer players in pre-deal (normal/digital mode only)
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

  // Local seat switcher (play panel)
  _updateLocalSeatSwitcher();

  // Role hint
  if (hint) {
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
      voteDisp.style.display = "block";
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
  _requestsInFlight++;
  try {
    const res  = await fetch("/cast_bust_vote", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {} finally {
    _requestDone();
  }
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


function _openBustVoteModal(secondsLeft) {
  if (_bustVoteModalOpen) return;
  const overlay = openModal("bust-vote-modal-overlay");
  if (!overlay) return;
  _bustVoteModalOpen = true;

  const bar      = document.getElementById("bust-vote-timer-bar");
  const label    = document.getElementById("bust-vote-timer-label");
  const duration = secondsLeft || 15;   // guard against 0

  let secs = duration;
  function tick() {
    if (!_bustVoteModalOpen) return;

    // Re-sync with the server's clock each tick. The server pauses/extends
    // the bust-vote window while an insurance vote is pending, so trust
    // bust_vote_seconds_left over our local countdown when it's available
    // and the window is still open server-side.
    let resynced = false;
    if (lastState) {
      if (lastState.bust_vote_window_open && typeof lastState.bust_vote_seconds_left === "number") {
        secs = lastState.bust_vote_seconds_left;
        resynced = true;
      } else if (!lastState.bust_vote_window_open) {
        // Server says the window already closed (e.g. all votes decided) —
        // close the modal without re-submitting votes.
        _closeBustVoteModal();
        return;
      }
    }

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
    // Only decrement locally when this tick wasn't just resynced from the
    // server — otherwise the next resync overwrites this and we end up
    // double-decrementing (timer skips a number every poll).
    if (!resynced) secs--;
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
    card.classList.add("bv-vote-card");

    if (multiLocal) {
      const nameLbl = document.createElement("span");
      nameLbl.classList.add("bv-name-lbl");
      nameLbl.textContent = name;
      card.appendChild(nameLbl);
    }

    if (voted) {
      // Already voted — show status
      const statusEl = document.createElement("span");
      statusEl.classList.add("bv-status", voted === "bust" ? "bv-status--bust" : "bv-status--pass");
      statusEl.textContent = voted === "bust" ? "💥 Bet Bust" : "Passed";
      card.appendChild(statusEl);
    } else {
      // Buttons
      const btns = document.createElement("div");
      btns.classList.add("bv-btn-row");

      const bustBtn = document.createElement("button");
      bustBtn.className = "btn green bv-vote-btn";
      bustBtn.textContent = "💥 Bet Bust";
      bustBtn.addEventListener("click", () => submitBustVote("bust", multiLocal ? name : undefined));

      const passBtn = document.createElement("button");
      passBtn.className = "btn muted-btn bv-vote-btn";
      passBtn.textContent = "Pass";
      passBtn.addEventListener("click", () => submitBustVote("pass", multiLocal ? name : undefined));

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
  closeModal("bust-vote-modal-overlay");
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

  const statusEl      = document.getElementById("bust-vote-status");
  const statusElRound = document.getElementById("bust-vote-status-round");

  // Modal: open when window is open and any local player hasn't voted yet.
  // Delay until deal animation finishes so the modal doesn't cover the cards.
  const bustVotes  = state.my_bust_votes || {};
  const anyUnvoted = Object.values(bustVotes).some(v => v === null || v === undefined);
  if (state.bust_vote_window_open && anyUnvoted
      && myRole !== null && myRole !== ROLE.SPECTATOR
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
    && myRole !== null && myRole !== ROLE.SPECTATOR
    && phase !== PHASE.PRE_DEAL
    && !state.bust_vote_window_open;

  statusEl.style.display = show ? "block" : "none";
  if (statusElRound) statusElRound.style.display = show ? "block" : "none";
  if (!show) return;

  const allVotes = state.bust_votes || {};
  const bustCnt  = Object.values(allVotes).filter(v => v === "bust").length;
  const myBusters = myNames.filter(n => bustVotes[n] === "bust");

  if (phase === PHASE.ROUND_OVER) {
    const result = state.bust_vote_result;
    if (!myBusters.length) {
      statusEl.textContent = bustCnt ? `${bustCnt} bet on bust this round.` : "";
    } else if (result) {
      const winners    = result.winners || [];
      const myWinners  = myBusters.filter(n => winners.includes(n));
      const myLosers   = myBusters.filter(n => !winners.includes(n));
      const wLabel     = result.winner_label || "called it";
      const lLabel     = result.loser_label  || "wrong";
      const parts = [];
      if (myWinners.length) parts.push(`<span class="bust-vote-result-correct">✓ ${myWinners.map(escapeHtml).join(", ")} ${escapeHtml(wLabel)}</span>`);
      if (myLosers.length)  parts.push(`<span class="bust-vote-result-wrong">✗ ${myLosers.map(escapeHtml).join(", ")} ${escapeHtml(lLabel)}</span>`);
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
        ? `💥 ${escapeHtml(allBusters[0])} bet dealer busts`
        : `💥 ${allBusters.map(escapeHtml).join(" & ")} bet dealer busts`;
      statusEl.innerHTML = `<span class="bust-label">${label}</span>`;
    } else if (myVote === "pass") {
      statusEl.textContent = "You passed the bust bet.";
    } else {
      statusEl.textContent = "";
    }
  }
  // Mirror to the drinks-pane copy
  if (statusElRound) statusElRound.innerHTML = statusEl.innerHTML;
}

async function giveBustSip(winnerName, recipientName) {
  _requestsInFlight++;
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
  } catch (_) {} finally {
    _requestDone();
  }
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

  // Defer behind the milestone handout popup so the two allocation prompts
  // (and their countdown timers) appear one after the other, not stacked.
  // The server gives the bust-handout window a fresh countdown once the
  // milestone prompt clears (see polling.py), so nothing is lost by waiting.
  if (state.pending_milestone) {
    overlay.style.display = "none";
    body.innerHTML = "";
    return;
  }

  const allPlayers  = (state.players || []);
  const secsLeft    = state.bust_handout_seconds_left || 0;
  overlay.style.display = "flex";

  const timerColour = secsLeft <= 5 ? "var(--red)" : secsLeft <= 10 ? "var(--yellow)" : "var(--green)";
  const timerStr    = secsLeft > 0
    ? `<div style="font-size:12px;color:${timerColour};font-weight:700;margin-bottom:10px">⏱ ${secsLeft}s — auto-assigns if time runs out</div>`
    : "";

  body.innerHTML = pending.map((winnerName, idx) => {
    const label = pending.length > 1
      ? `🎉 <strong>${escapeHtml(winnerName)}</strong> called it! Give 1 sip to:`
      : "🎉 You called it! Give 1 sip to:";
    const btns = allPlayers
      .filter(n => n.toLowerCase() !== winnerName.toLowerCase())
      .map(n => `<button class="btn wide bgp-give-btn"
          data-winner="${escapeHtml(winnerName)}" data-recipient="${escapeHtml(n)}"
          onclick="giveBustSip(this.dataset.winner, this.dataset.recipient)"
          >${escapeHtml(n)}</button>`)
      .join("");
    const mb = pending.length > 1 ? " bgp-multi-entry" : "";
    return `<div class="bgp-entry${mb}">
      <div class="bgp-winner-label">${label}</div>
      ${timerStr}
      <div class="bgp-btns-col">${btns}</div>
    </div>`;
  }).join(`<hr class="bgp-divider">`);
}

// ============================================================
// DEALER LOTTERY (docs/planning/DealerLottery-Plan.md)
// ============================================================

let _dealerLotteryModalOpen   = false;
let _dealerLotteryTimerHandle = null;

async function submitDealerLotteryX(x, playerName) {
  const body = { room_code: roomCode, client_id: clientId, x };
  if (playerName) body.player_name = playerName;
  _requestsInFlight++;
  try {
    const res  = await fetch("/dealer_lottery/enter", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(body),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {} finally {
    _requestDone();
  }
}

function _openDealerLotteryModal(secondsLeft) {
  if (_dealerLotteryModalOpen) return;
  const overlay = openModal("dealer-lottery-modal-overlay");
  if (!overlay) return;
  _dealerLotteryModalOpen = true;

  const bar      = document.getElementById("dealer-lottery-timer-bar");
  const label    = document.getElementById("dealer-lottery-timer-label");
  const duration = secondsLeft || 20;

  let secs = duration;
  function tick() {
    if (!_dealerLotteryModalOpen) return;

    let resynced = false;
    if (lastState && lastState.dealer_lottery) {
      const pending = lastState.dealer_lottery.pending;
      if (pending && typeof pending.seconds_left === "number") {
        secs = pending.seconds_left;
        resynced = true;
      } else if (!pending) {
        // Server says the window already closed (resolved or expired).
        _closeDealerLotteryModal();
        return;
      }
    }

    const display = Math.min(secs, 20);
    if (bar)   bar.style.width   = `${(display / 20) * 100}%`;
    if (label) label.textContent = `${display}s`;
    if (secs <= 0) {
      // Auto-submit 0 for any unanswered local players
      const myEntries = (lastState && lastState.dealer_lottery && lastState.dealer_lottery.pending)
        ? lastState.dealer_lottery.pending.my_entries : {};
      const unanswered = myNames.filter(n => (myEntries || {})[n] == null);
      if (unanswered.length) {
        (async () => {
          for (const name of unanswered) await submitDealerLotteryX(0, name);
          _closeDealerLotteryModal();
        })();
      } else {
        _closeDealerLotteryModal();
      }
      return;
    }
    if (!resynced) secs--;
    _dealerLotteryTimerHandle = setTimeout(tick, 1000);
  }
  tick();
}

function _closeDealerLotteryModal() {
  if (!_dealerLotteryModalOpen) return;
  _dealerLotteryModalOpen = false;
  if (_dealerLotteryTimerHandle) { clearTimeout(_dealerLotteryTimerHandle); _dealerLotteryTimerHandle = null; }
  closeModal("dealer-lottery-modal-overlay");
}

// Render per-player entry rows (stake select 0-5 + Enter button) inside the modal.
function _renderDealerLotteryCards(state) {
  const wrap = document.getElementById("dealer-lottery-players-wrap");
  if (!wrap) return;

  const pending   = (state.dealer_lottery && state.dealer_lottery.pending) || {};
  const myEntries = pending.my_entries || {};
  const npcSet    = new Set([...(npcPlayers || [])]);
  const locals    = myNames.filter(n => !npcSet.has(n));
  const multiLocal = locals.length > 1;

  wrap.innerHTML = "";
  locals.forEach(name => {
    const answered = myEntries[name];
    const card = document.createElement("div");
    card.classList.add("dl-entry-card");

    if (multiLocal) {
      const nameLbl = document.createElement("span");
      nameLbl.classList.add("dl-name-lbl");
      nameLbl.textContent = name;
      card.appendChild(nameLbl);
    }

    if (answered !== null && answered !== undefined) {
      const statusEl = document.createElement("span");
      statusEl.classList.add("dl-status");
      statusEl.textContent = `Entered: ${answered}`;
      card.appendChild(statusEl);
    } else {
      const row = document.createElement("div");
      row.classList.add("dl-entry-row");

      const select = document.createElement("select");
      select.classList.add("dl-x-select");
      for (let i = 0; i <= 5; i++) select.appendChild(new Option(String(i), String(i)));

      const enterBtn = document.createElement("button");
      enterBtn.className = "btn dl-enter-btn";
      enterBtn.textContent = "Enter";
      enterBtn.addEventListener("click", () => {
        submitDealerLotteryX(parseInt(select.value, 10) || 0, multiLocal ? name : undefined);
      });

      row.appendChild(select);
      row.appendChild(enterBtn);
      card.appendChild(row);
    }

    wrap.appendChild(card);
  });
}

function updateDealerLotteryUI(state) {
  const dl = state.dealer_lottery || {};
  const pending = dl.pending;

  if (pending && myRole !== null && myRole !== ROLE.SPECTATOR && !_dealAnimating) {
    _openDealerLotteryModal(pending.seconds_left || 20);
  } else if (!pending) {
    _closeDealerLotteryModal();
  }

  if (_dealerLotteryModalOpen) {
    _renderDealerLotteryCards(state);
    const answered = document.getElementById("dealer-lottery-answered");
    if (answered && pending) {
      answered.textContent = `${pending.answered_count}/${pending.total_count} answered`;
    }
  }

  _renderDealerLotteryGivePanel(state);
}

async function giveDealerLotterySip(giverName, recipientName) {
  _requestsInFlight++;
  try {
    const res  = await fetch("/dealer_lottery/give_sip", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        giver_name: giverName, recipient_name: recipientName,
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    else appendLog(`  Dealer Lottery handout failed: ${data.error || "unknown"}\n`);
  } catch (_) {} finally {
    _requestDone();
  }
}

function _renderDealerLotteryGivePanel(state) {
  const overlay = document.getElementById("dealer-lottery-give-overlay");
  const body    = document.getElementById("dealer-lottery-give-body");
  if (!overlay || !body) return;

  const dl      = state.dealer_lottery || {};
  const pending = dl.my_pending_handouts || {};
  const givers  = Object.keys(pending);
  if (!givers.length) {
    overlay.style.display = "none";
    body.innerHTML = "";
    return;
  }

  // Defer behind the milestone and bust-vote handout prompts so allocation
  // popups appear one after another, never stacked.
  if (state.pending_milestone || (state.my_bust_handout_pending || []).length) {
    overlay.style.display = "none";
    body.innerHTML = "";
    return;
  }

  const allPlayers = state.players || [];
  const secsLeft    = dl.handout_seconds_left || 0;
  overlay.style.display = "flex";

  const timerColour = secsLeft <= 5 ? "var(--red)" : secsLeft <= 10 ? "var(--yellow)" : "var(--green)";
  const timerStr = secsLeft > 0
    ? `<div style="font-size:12px;color:${timerColour};font-weight:700;margin-bottom:10px">⏱ ${secsLeft}s — you keep them if time runs out</div>`
    : "";

  body.innerHTML = givers.map(giverName => {
    const amount = pending[giverName];
    const label = givers.length > 1
      ? `🎰 <strong>${escapeHtml(giverName)}</strong>'s split hands both busted! Give ${amount} sip(s) to:`
      : `🎰 Both split hands busted! Give ${amount} sip(s) to:`;
    const btns = allPlayers
      .filter(n => n.toLowerCase() !== giverName.toLowerCase())
      .map(n => `<button class="btn wide bgp-give-btn"
          data-giver="${escapeHtml(giverName)}" data-recipient="${escapeHtml(n)}"
          onclick="giveDealerLotterySip(this.dataset.giver, this.dataset.recipient)"
          >${escapeHtml(n)}</button>`)
      .join("");
    const mb = givers.length > 1 ? " bgp-multi-entry" : "";
    return `<div class="bgp-entry${mb}">
      <div class="bgp-winner-label">${label}</div>
      ${timerStr}
      <div class="bgp-btns-col">${btns}</div>
    </div>`;
  }).join(`<hr class="bgp-divider">`);
}

function _cardStr(c) { return `${c.rank}${c.symbol}`; }

function showDealerLotteryToast(result) {
  if (!result) return;
  const a = (result.hand_a || []).map(_cardStr).join(" ");
  const b = (result.hand_b || []).map(_cardStr).join(" ");
  const aOutcome = result.hand_a_bust ? "BUST" : "stands";
  const bOutcome = result.hand_b_bust ? "BUST" : "stands";
  const text = `🎰 Dealer Lottery split: ${a} (${aOutcome}) / ${b} (${bOutcome})`;
  const _myNames = (typeof myNames !== "undefined" && myNames) ? myNames : [];
  const myX = _myNames.some(n => (result.entries || {})[n] > 0);
  // Green if both busted (a win for anyone who entered), red otherwise.
  const iDrink = myX && result.busted < 2;
  _firePlayerToast(text, iDrink, 7000);
}

// Shared toast helper — sets content, applies drink/clean class, triggers show animation.
function _firePlayerToast(text, iDrink, ms) {
  const toast = document.getElementById("player-toast");
  if (!toast) return;
  toast.textContent = text;
  toast.className = (iDrink ? "drink" : "clean") + " show";
  void toast.offsetWidth;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), ms);
}

function showBustVoteToast(result) {
  if (!result) return;
  const lines = result.outcome_lines || [];
  if (!lines.length) return;
  const _myNames = (typeof myNames !== "undefined" && myNames) ? myNames : [];
  const iDrink = _myNames.some(n => (result.losers || []).includes(n));
  _firePlayerToast(lines.join(" · "), iDrink, 6000);
}

function showBustHandoutToast(results) {
  if (!results || !results.length) return;
  const _myNames = (typeof myNames !== "undefined" && myNames) ? myNames : [];
  const parts = results.map(r => {
    if (r.forfeited) return `⏱️ ${r.winner} didn't choose in time — drinks it themselves`;
    return `🎁 ${r.winner} gave 1 sip to ${r.recipient}`;
  });
  // Red if I gave away a sip or forfeited (drink), green otherwise.
  const iDrink = results.some(r =>
    (r.forfeited && _myNames.includes(r.winner)) ||
    (!r.forfeited && _myNames.includes(r.recipient))
  );
  _firePlayerToast(parts.join(" · "), iDrink, 6000);
}

function showInsuranceToast(results) {
  if (!results || !results.length) return;
  const parts = results.map(r => {
    const icon    = r.group_won ? "✅" : "❌";
    const voted   = r.insured ? "Insure" : "Decline";
    const outcome = r.outcome_text || (r.group_won ? "correct call" : "wrong call");
    return `${icon} Insurance (${r.player}): voted ${voted} — ${outcome}`;
  });
  // Red if any insurance outcome means I personally drink, green otherwise.
  const _myNames = (typeof myNames !== "undefined" && myNames) ? myNames : [];
  const iDrink = results.some(r => {
    const amHolder = _myNames.includes(r.player);
    if (amHolder) {
      // BJ holder drinks their own bonus when insured & dealer had BJ.
      return r.insured && r.dealer_bj;
    }
    // Rest of the group drinks double when the group's insurance call lost.
    return !r.group_won;
  });
  _firePlayerToast(parts.join(" · "), iDrink, 8000);
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

function renderPendingRegBanner(state) {
  const banner = document.getElementById("pending-reg-banner");
  if (!banner) return;
  const pending = state.pending_registrations || [];
  if (!pending.length || myRole !== ROLE.ADMIN) {
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
// Per-player bet panel (pre-deal, normal/digital mode only)
// ---------------------------------------------------------------------------

function _updateBetPanel(state, isPreDeal) {
  const panel     = document.getElementById("dig-bet-panel");
  const container = document.getElementById("dig-bet-steppers");
  if (!panel || !container) return;

  const isDrinking = state.drinking_mode;
  const isDigital  = state.mode === "digital";

  // Only show in digital (normal-money) mode during pre-deal, for players who have seats
  const isRoundOver = state.phase === PHASE.ROUND_OVER;
  const show = (isPreDeal || isRoundOver) && isDigital && !isDrinking && myNames.length > 0;
  panel.style.display = show ? "block" : "none";
  if (!show) return;

  // Build one stepper per seat this client controls
  const tableMap = {};
  (state.table || []).forEach(p => { tableMap[p.name.toLowerCase()] = p; });

  const defaultBet = state.bet_amount || 5;

  // Only rebuild if seats or bets changed (avoid clobbering in-progress steppers)
  const existing = container.querySelectorAll(".player-bet-stepper");
  const needsRebuild = existing.length !== myNames.length ||
    myNames.some((n, i) => {
      const el = existing[i];
      return !el || el.dataset.seatName !== n;
    });

  if (!needsRebuild) {
    // Still sync displayed value from server state (another client could have polled)
    myNames.forEach(n => {
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
  myNames.forEach(name => {
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
