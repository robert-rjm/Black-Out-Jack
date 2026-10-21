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


// ============================================================
// DEAL ANIMATION PREFERENCE
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
