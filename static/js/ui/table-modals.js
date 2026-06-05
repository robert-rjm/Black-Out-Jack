// Milestone state
let _lastMilestoneResultKey = null;
let _lastMilestoneKey       = null;
let _milestoneAllocations   = {};
let _milestoneModalOpened   = null;
let _milestoneTimerID       = null;

let _insuranceTimerID   = null;
let _insuranceModalKey  = null;

function updateInsuranceVisibility(state) {
  const row = document.getElementById("dig-insurance-row");
  if (row) {
    const upCard = state.dealer_hand && state.dealer_hand.cards && state.dealer_hand.cards[0];
    const dealerShowsAce = upCard && upCard.rank === "A";
    let activeHandIsBlackjack = false;
    if (state.phase === "playing" && state.current_turn && myName &&
        state.current_turn.toLowerCase() === myName.toLowerCase()) {
      const me = (state.table || []).find(p => p.name.toLowerCase() === myName.toLowerCase());
      if (me) {
        const activeHand = (me.hands || []).find(h => !h.done);
        if (activeHand) activeHandIsBlackjack = activeHand.blackjack;
      }
    }
    const hasVoteForMyHand = activeHandIsBlackjack && (state.insurance_votes || []).some(v =>
      !v.resolved && v.bj_player.toLowerCase() === (myName || "").toLowerCase()
    );
    row.style.display = (dealerShowsAce && activeHandIsBlackjack && !hasVoteForMyHand) ? "block" : "none";
  }
  renderInsuranceModal(state);
}

function renderInsuranceModal(state) {
  const overlay = document.getElementById("insurance-modal-overlay");
  if (!overlay) return;

  const openVotes = (state.insurance_votes || []).filter(v => !v.resolved);

  if (!openVotes.length) {
    _closeInsuranceModal();
    _renderInsuranceBanner(null);
    return;
  }

  const v   = openVotes[0];
  const key = `${v.bj_player}:${v.hand_idx}`;

  if (_insuranceModalKey !== key) {
    _insuranceModalKey = key;
    overlay.classList.add("open");
  }

  const allIn = (v.votes_cast != null && v.votes_needed != null && v.votes_cast >= v.votes_needed);
  if (allIn) {
    _closeInsuranceModal();
    _renderInsuranceBanner(v);
    return;
  }

  const iAmBJHolder = myName && v.bj_player.toLowerCase() === myName.toLowerCase();
  const myVote      = v.my_vote;
  const hasVoted    = myVote !== null && myVote !== undefined;

  const titleEl = document.getElementById("insurance-modal-title");
  const subEl   = document.getElementById("insurance-modal-sub");
  if (titleEl) titleEl.textContent = `Insurance Vote — ${escapeHtml(v.bj_player)} H${v.hand_idx + 1}`;
  if (subEl)   subEl.textContent   = iAmBJHolder
    ? "The group is voting whether to insure your Blackjack."
    : `${escapeHtml(v.bj_player)} has Blackjack. Vote to insure?`;

  const stakesEl = document.getElementById("insurance-modal-stakes");
  if (stakesEl) {
    const wager    = (state && state.wager) || 1;
    const entry    = (state.table || []).find(p => p.name.toLowerCase() === v.bj_player.toLowerCase());
    const bjHand   = entry && entry.hands[v.hand_idx];
    const mult     = (bjHand && bjHand.bj_mult) || 1;
    const normSips = mult * wager;
    const dblSips  = mult * 2 * wager;
    const sip      = n => `${n} sip${n !== 1 ? "s" : ""}`;
    stakesEl.innerHTML =
      `<span style="color:var(--green)">✓ INSURE + dealer BJ:</span> group safe · <strong>${escapeHtml(v.bj_player)}</strong> drinks ${sip(normSips)}<br>` +
      `<span style="color:var(--red)">✗ INSURE + no dealer BJ:</span> group drinks <strong>${sip(dblSips)} each</strong><br>` +
      `<span style="color:var(--muted)">DECLINE:</span> normal BJ bonus of ${sip(normSips)} each · tie = decline`;
  }

  const btnsEl   = document.getElementById("insurance-modal-btns");
  const statusEl = document.getElementById("insurance-modal-status");
  if (btnsEl) btnsEl.innerHTML = "";
  if (!iAmBJHolder && !hasVoted) {
    const ins = document.createElement("button");
    ins.className = "btn green wide";
    ins.textContent = "INSURE";
    ins.dataset.bjPlayer = v.bj_player;
    ins.dataset.handIdx  = v.hand_idx;
    ins.addEventListener("click", function() {
      castInsuranceVote(this.dataset.bjPlayer, parseInt(this.dataset.handIdx), true);
    });
    const dec = document.createElement("button");
    dec.className = "btn red wide";
    dec.textContent = "DECLINE";
    dec.dataset.bjPlayer = v.bj_player;
    dec.dataset.handIdx  = v.hand_idx;
    dec.addEventListener("click", function() {
      castInsuranceVote(this.dataset.bjPlayer, parseInt(this.dataset.handIdx), false);
    });
    if (btnsEl) { btnsEl.appendChild(ins); btnsEl.appendChild(dec); }
    if (statusEl) statusEl.textContent = `(${v.votes_cast ?? 0}/${v.votes_needed ?? "?"} voted)`;
  } else if (!iAmBJHolder && hasVoted) {
    const label = myVote ? "INSURE" : "DECLINE";
    const color = myVote ? "var(--green)" : "var(--red)";
    if (statusEl) statusEl.innerHTML =
      `Your vote: <strong style="color:${color}">${label}</strong> · waiting for dealer to reveal (${v.votes_cast ?? 0}/${v.votes_needed ?? "?"})`;
  } else {
    if (statusEl) statusEl.innerHTML =
      `<span style="color:var(--muted)">⏳ Waiting for group to vote… (${v.votes_cast ?? 0}/${v.votes_needed ?? "?"})</span>`;
  }

  const timerEl = document.getElementById("insurance-modal-timer");
  if (timerEl) {
    const s = v.seconds_left ?? 0;
    timerEl.textContent = s > 0 ? `⏱ ${s}s remaining` : "Time up — auto-declining…";
    timerEl.style.color = s <= 10 ? "var(--red)" : "var(--muted)";
  }
}

function _closeInsuranceModal() {
  const overlay = document.getElementById("insurance-modal-overlay");
  if (overlay) overlay.classList.remove("open");
  _insuranceModalKey = null;
}

function _renderInsuranceBanner(v) {
  const banner  = document.getElementById("insurance-vote-banner");
  const content = document.getElementById("insurance-vote-banner-content");
  if (!banner || !content) return;
  if (!v) { banner.style.display = "none"; content.innerHTML = ""; return; }
  const insureCount  = v.insure_count ?? 0;
  const declineCount = (v.votes_cast ?? 0) - insureCount;
  const voteLabel    = insureCount > declineCount ? "INSURE" : "DECLINE";
  const color        = voteLabel === "INSURE" ? "var(--green)" : "var(--red)";
  content.innerHTML  =
    `🃏 Insurance vote closed — <strong style="color:${color}">${voteLabel}</strong> ` +
    `(${insureCount} insure / ${declineCount} decline) · waiting for dealer to reveal`;
  banner.style.display = "block";
}

async function castInsuranceVote(bjPlayer, handIdx, vote) {
  try {
    const res  = await fetch("/vote_insurance", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        bj_player: bjPlayer, hand_idx: handIdx, vote,
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    else appendLog(`  Insurance vote failed: ${data.error || "unknown error"}\n`);
  } catch (_) {
    appendLog("  Insurance vote failed: network error\n");
  }
}


// ── Milestone: 50-sip handout feature ───────────────────────────────────────

function renderMilestoneState(state) {
  const ms     = state && state.pending_milestone;
  const result = state && state.last_milestone_result;

  // ── Drink notification for recipients (fires once per result) ──────────
  if (result) {
    const rKey = `${result.boundary}:${result.winner}`;
    if (rKey !== _lastMilestoneResultKey) {
      _lastMilestoneResultKey = rKey;
      // Check if I'm a recipient
      if (myName) {
        // allocations keys might be capitalised differently — case-insensitive lookup
        const myEntry = Object.entries(result.allocations || {})
          .find(([n]) => n.toLowerCase() === myName.toLowerCase());
        if (myEntry) {
          const [, sipCount] = myEntry;
          _showDrinkToast(sipCount, result.winner);
        }
      }
    }
  }

  // ── Pending milestone handling ─────────────────────────────────────────
  if (!ms) {
    _hideMilestoneToast();
    _hideWaitingBanner();
    // Close modal if the TTL expired server-side while modal was open
    if (_lastMilestoneKey && document.getElementById("milestone-modal-overlay").classList.contains("open")) {
      _closeMilestoneModal();
    }
    return;
  }

  const key       = `${ms.boundary}:${ms.winner}`;
  const iAmWinner = !!ms.i_am_winner;  // server-authoritative; no JS name-matching needed

  // Show announcement toast exactly once per new milestone (all players)
  if (key !== _lastMilestoneKey) {
    _lastMilestoneKey     = key;
    _milestoneAllocations = {};
    _showMilestoneToast(ms);
  }

  if (iAmWinner) {
    _hideWaitingBanner();
    // Open the handout modal exactly once for this milestone
    if (_milestoneModalOpened !== key) {
      _milestoneModalOpened = key;
      // Short delay so the toast is visible before modal covers it
      setTimeout(() => _openMilestoneModal(ms, state), 600);
    } else {
      // Modal already open — just keep the timer in sync
      _updateMilestoneTimer(ms.seconds_left);
    }
  } else {
    // Non-winners: persistent waiting banner with live countdown
    _showWaitingBanner(ms);
  }
}

function _showMilestoneToast(ms) {
  const toast = document.getElementById("milestone-toast");
  if (!toast) return;
  toast.innerHTML = `🎉 ${escapeHtml(ms.winner)} hit ${ms.boundary} sips!`;
  toast.classList.remove("show");
  // Force reflow so animation restarts cleanly
  void toast.offsetWidth;
  toast.classList.add("show");
  // Auto-hide after 5 seconds
  setTimeout(() => _hideMilestoneToast(), 5000);
}

function _hideMilestoneToast() {
  const toast = document.getElementById("milestone-toast");
  if (toast) toast.classList.remove("show");
}

function _showWaitingBanner(ms) {
  // In-flow slot (digital mode — sits exactly above the tab bar)
  const slot = document.getElementById("ms-waiting-slot");
  const s    = ms.seconds_left;
  const timerStr = s > 0 ? ` · ⏱ ${s}s` : "";
  const html = `🎉 <strong>${escapeHtml(ms.winner)}</strong> is handing out ${ms.handout} milestone sips…${timerStr}`;
  if (slot) {
    slot.innerHTML     = html;
    slot.style.display = "block";
  }
  // Fallback fixed banner (referee mode / any other context)
  const fixed = document.getElementById("ms-waiting-banner");
  if (fixed && !slot) {
    fixed.innerHTML = html;
    fixed.classList.add("show");
  }
}

function _hideWaitingBanner() {
  const slot = document.getElementById("ms-waiting-slot");
  if (slot) slot.style.display = "none";
  const fixed = document.getElementById("ms-waiting-banner");
  if (fixed) fixed.classList.remove("show");
}

function _showDrinkToast(sips, winner) {
  // Open the acknowledgement modal instead of a dismissable toast
  const overlay = document.getElementById("ms-ack-overlay");
  if (!overlay) return;
  const sipWord = sips === 1 ? "sip" : "sips";
  const title   = document.getElementById("ms-ack-title");
  const sub     = document.getElementById("ms-ack-sub");
  if (title) title.textContent = `Drink ${sips} ${sipWord}!`;
  if (sub)   sub.textContent   = `${escapeHtml(winner)} reached a milestone and handed you ${sips} ${sipWord}.`;
  overlay.classList.add("open");
  const btn = document.getElementById("ms-ack-btn");
  if (btn) {
    // Replace to remove any previous listener
    const fresh = btn.cloneNode(true);
    btn.parentNode.replaceChild(fresh, btn);
    fresh.addEventListener("click", () => overlay.classList.remove("open"), { once: true });
  }
}

function _openMilestoneModal(ms, state) {
  const overlay = document.getElementById("milestone-modal-overlay");
  if (!overlay) return;

  const title = document.getElementById("milestone-modal-title");
  const sub   = document.getElementById("milestone-modal-sub");
  if (title) title.textContent = `You hit ${ms.boundary} sips first! 🏆`;
  if (sub)   sub.textContent   = `Hand out ${ms.handout} sips — split however you like (not yourself).`;

  // Build stepper list from current players except self
  const players = (lastState && lastState.players || []).filter(
    n => n.toLowerCase() !== (myName || "").toLowerCase()
  );
  // Initialize allocations to 0 for everyone
  players.forEach(n => { if (!(_milestoneAllocations[n] >= 0)) _milestoneAllocations[n] = 0; });

  _renderMilestoneSteppers(players, ms.handout);
  _updateMilestoneTimer(ms.seconds_left);
  overlay.classList.add("open");
}

function _closeMilestoneModal() {
  const overlay = document.getElementById("milestone-modal-overlay");
  if (overlay) overlay.classList.remove("open");
  if (_milestoneTimerID) { clearInterval(_milestoneTimerID); _milestoneTimerID = null; }
}

function _renderMilestoneSteppers(players, total) {
  const container = document.getElementById("milestone-steppers");
  if (!container) return;
  container.innerHTML = "";
  players.forEach(name => {
    const row = document.createElement("div");
    row.className = "ms-stepper";
    const val = _milestoneAllocations[name] || 0;
    row.innerHTML = `
      <span class="ms-name">${escapeHtml(name)}</span>
      <button onclick="milestoneAdjust('${escapeHtml(name)}', -1)">−</button>
      <span class="ms-count" id="ms-count-${escapeHtml(name)}">${val}</span>
      <button onclick="milestoneAdjust('${escapeHtml(name)}', +1)">+</button>`;
    container.appendChild(row);
  });
  _updateMilestoneRemaining(total);
}

function milestoneAdjust(name, delta) {
  const ms = lastState && lastState.pending_milestone;
  const total = ms ? ms.handout : 5;
  const cur   = _milestoneAllocations[name] || 0;
  const used  = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  const newVal = Math.max(0, Math.min(cur + delta, cur + (total - used) + (delta < 0 ? 0 : 0)));

  if (delta > 0 && used >= total) return;  // budget exhausted

  _milestoneAllocations[name] = Math.max(0, cur + delta);
  const el = document.getElementById(`ms-count-${name}`);
  if (el) el.textContent = _milestoneAllocations[name];
  _updateMilestoneRemaining(total);
}

function _updateMilestoneRemaining(total) {
  const used = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  const left = total - used;
  const rem  = document.getElementById("milestone-remaining");
  const btn  = document.getElementById("milestone-submit-btn");
  if (rem) {
    rem.textContent = left === 0 ? "✓ All sips assigned" : `${left} sip${left !== 1 ? "s" : ""} left to assign`;
    rem.style.color = left === 0 ? "var(--green)" : "var(--yellow)";
  }
  if (btn) btn.disabled = (left !== 0);
}

function _updateMilestoneTimer(secondsLeft) {
  const timerEl = document.getElementById("milestone-timer");
  if (!timerEl) return;
  if (secondsLeft == null) return;
  const s = Math.max(0, secondsLeft);
  timerEl.textContent = s > 0 ? `⏱ ${s}s remaining` : "⏱ Time's up!";
  timerEl.style.color = s <= 10 ? "var(--red)" : "var(--muted)";
}

async function submitMilestoneHandout() {
  const ms = lastState && lastState.pending_milestone;
  if (!ms) return;
  const used = Object.values(_milestoneAllocations).reduce((a, b) => a + b, 0);
  if (used !== ms.handout) return;  // shouldn't happen (button is disabled), but guard anyway

  const btn = document.getElementById("milestone-submit-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }

  try {
    const res = await fetch("/claim_milestone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, allocations: _milestoneAllocations }),
    });
    const data = await res.json();
    if (data.ok) {
      _closeMilestoneModal();
      _lastMilestoneKey     = null;
      _milestoneModalOpened = null;
      applyState(data);
    } else {
      alert(data.error || "Could not claim milestone.");
      if (btn) { btn.disabled = false; btn.textContent = "Hand out sips"; }
    }
  } catch (_) {
    alert("Network error — try again.");
    if (btn) { btn.disabled = false; btn.textContent = "Hand out sips"; }
  }
}

