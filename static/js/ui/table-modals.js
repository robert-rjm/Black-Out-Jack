let _insuranceModalKey   = null;
let _insuranceMinimised  = false;

function updateInsuranceVisibility(state) {
  const row = document.getElementById("dig-insurance-row");
  if (row) {
    const upCard = state.dealer_hand && state.dealer_hand.cards && state.dealer_hand.cards[0];
    const dealerShowsAce = upCard && upCard.rank === "A";
    let activeHandIsBlackjack = false;
    const activeName = myActiveName || myName;
    if (state.phase === PHASE.PLAYING && state.current_turn && activeName &&
        state.current_turn.toLowerCase() === activeName.toLowerCase()) {
      const me = (state.table || []).find(p => p.name.toLowerCase() === activeName.toLowerCase());
      if (me) {
        const activeHand = (me.hands || []).find(h => !h.done);
        if (activeHand) activeHandIsBlackjack = activeHand.blackjack;
      }
    }
    const hasVoteForMyHand = activeHandIsBlackjack && (state.insurance_votes || []).some(v =>
      !v.resolved && v.bj_player.toLowerCase() === (activeName || "").toLowerCase()
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
    // If the vote just resolved, show the outcome in the banner instead of
    // hiding it immediately.  The backend clears insurance_result on new round,
    // so the banner disappears naturally without extra cleanup.
    const results = state.insurance_result;
    if (results && results.length) {
      _renderInsuranceBannerOutcome(results);
    } else {
      _renderInsuranceBanner(null);
    }
    return;
  }

  const v   = openVotes[0];
  const key = `${v.bj_player}:${v.hand_idx}`;

  if (_insuranceModalKey !== key) {
    _insuranceModalKey  = key;
    _insuranceMinimised = false;  // always expand on new vote
    openModal("insurance-modal-overlay", { useClass: true });
    // Wire up minimize button once
    const minBtn = document.getElementById("insurance-modal-minimize");
    if (minBtn && !minBtn._wired) {
      minBtn._wired = true;
      minBtn.addEventListener("click", () => {
        _insuranceMinimised = true;
        closeModal("insurance-modal-overlay", { useClass: true });
      });
    }
  }

  // Local multiplayer: find which local seats still need to vote
  const voterNames   = myNames.filter(n => n.toLowerCase() !== v.bj_player.toLowerCase());
  const votedNames   = Object.keys(v.votes_cast_by || {}).map(n => n.toLowerCase());
  const pendingLocal = voterNames.filter(n => !votedNames.includes(n.toLowerCase()));

  // Active voter: prefer first pending local seat, else fall back to myActiveName/myName
  const activeVoter  = pendingLocal.length > 0 ? pendingLocal[0]
                     : (myActiveName || myName);

  // If minimised, keep overlay closed — render compact banner instead
  if (_insuranceMinimised) {
    closeModal("insurance-modal-overlay", { useClass: true });
    _renderInsuranceBanner(v, true, activeVoter);
    return;
  }

  const allIn = (v.votes_cast != null && v.votes_needed != null && v.votes_cast >= v.votes_needed);
  if (allIn) {
    _insuranceMinimised = false;
    _closeInsuranceModal();
    _renderInsuranceBanner(v);
    return;
  }

  const iAmBJHolder  = activeVoter && v.bj_player.toLowerCase() === activeVoter.toLowerCase();
  const myVote       = v.my_vote;
  const hasVoted     = myVote !== null && myVote !== undefined;

  const titleEl = document.getElementById("insurance-modal-title");
  const subEl   = document.getElementById("insurance-modal-sub");
  if (titleEl) titleEl.textContent = `Insurance Vote — ${escapeHtml(v.bj_player)} H${v.hand_idx + 1}`;

  // Local multiplayer: show which player is currently voting
  const voterLabel = voterNames.length > 1
    ? ` <span style="color:var(--accent);font-size:11px">(${escapeHtml(activeVoter)})</span>`
    : "";
  if (subEl) subEl.innerHTML = iAmBJHolder
    ? "The group is voting whether to insure your Blackjack."
    : `${escapeHtml(v.bj_player)} has Blackjack. Vote to insure?${voterLabel}`;

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

  if (!iAmBJHolder && pendingLocal.length > 0) {
    // Show vote buttons for the current pending local player
    const ins = document.createElement("button");
    ins.className = "btn green wide";
    ins.textContent = "INSURE";
    ins.addEventListener("click", () => castInsuranceVote(v.bj_player, v.hand_idx, true, activeVoter));
    const dec = document.createElement("button");
    dec.className = "btn red wide";
    dec.textContent = "DECLINE";
    dec.addEventListener("click", () => castInsuranceVote(v.bj_player, v.hand_idx, false, activeVoter));
    if (btnsEl) { btnsEl.appendChild(ins); btnsEl.appendChild(dec); }

    // Show remaining voters as chips
    const remaining = pendingLocal.slice(1);
    const votedChips = voterNames.filter(n => !pendingLocal.includes(n))
      .map(n => `<span style="opacity:.5;text-decoration:line-through">${escapeHtml(n)}</span>`).join(" ");
    const pendingChips = pendingLocal
      .map((n, i) => i === 0
        ? `<strong style="color:var(--accent)">${escapeHtml(n)}</strong>`
        : `<span style="opacity:.6">${escapeHtml(n)}</span>`).join(" → ");
    if (statusEl) statusEl.innerHTML =
      `Voting: ${pendingChips}${votedChips ? ` · done: ${votedChips}` : ""} &nbsp;(${v.votes_cast ?? 0}/${v.votes_needed ?? "?"})`;

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
  closeModal("insurance-modal-overlay", { useClass: true });
  _insuranceModalKey = null;
}

function _renderInsuranceBanner(v, minimisedActiveVote = false, activeVoter = null) {
  const banner  = document.getElementById("insurance-vote-banner");
  const content = document.getElementById("insurance-vote-banner-content");
  if (!banner || !content) return;

  if (!v) {
    banner.style.display = "none";
    banner.classList.remove("minimised");
    content.innerHTML = "";
    return;
  }

  // ── Minimised active-vote state ──────────────────────────────
  if (minimisedActiveVote) {
    banner.classList.add("minimised");
    const s          = v.seconds_left ?? 0;
    const timerColor = s <= 10 ? "var(--red)" : "var(--muted)";
    const voterStr   = activeVoter ? ` <span style="color:var(--accent)">${escapeHtml(activeVoter)}</span>` : "";

    // Build quick vote buttons if voter hasn't voted yet
    const isBJHolder  = activeVoter && v.bj_player.toLowerCase() === activeVoter.toLowerCase();
    const votedNames  = Object.keys(v.votes_cast_by || {}).map(n => n.toLowerCase());
    const canVote     = !isBJHolder && activeVoter && !votedNames.includes(activeVoter.toLowerCase());

    // Build with DOM nodes — onclick string interpolation breaks for names
    // containing apostrophes (browsers decode &#39; → ' before JS eval).
    content.innerHTML = "";

    const _labelSpan = document.createElement("span");
    _labelSpan.className = "ins-banner-label";
    _labelSpan.innerHTML = `🃏 Insurance${voterStr}`;
    content.appendChild(_labelSpan);

    const _timerSpan = document.createElement("span");
    _timerSpan.className = "ins-banner-timer";
    _timerSpan.style.color = timerColor;
    _timerSpan.textContent = `⏱ ${s}s`;
    content.appendChild(_timerSpan);

    if (canVote) {
      const _btnsSpan = document.createElement("span");
      _btnsSpan.className = "ins-banner-btns";
      const _insBtn = document.createElement("button");
      _insBtn.style.cssText = "background:var(--green);color:#000";
      _insBtn.textContent = "INSURE";
      _insBtn.addEventListener("click", () => castInsuranceVote(v.bj_player, v.hand_idx, true, activeVoter));
      const _decBtn = document.createElement("button");
      _decBtn.style.cssText = "background:var(--red);color:#fff";
      _decBtn.textContent = "DECLINE";
      _decBtn.addEventListener("click", () => castInsuranceVote(v.bj_player, v.hand_idx, false, activeVoter));
      _btnsSpan.appendChild(_insBtn);
      _btnsSpan.appendChild(_decBtn);
      content.appendChild(_btnsSpan);
    } else {
      const _votedSpan = document.createElement("span");
      _votedSpan.style.cssText = "font-size:11px;color:var(--muted)";
      _votedSpan.textContent = `${v.votes_cast ?? 0}/${v.votes_needed ?? "?"} voted`;
      content.appendChild(_votedSpan);
    }

    const _expandSpan = document.createElement("span");
    _expandSpan.className = "ins-banner-expand";
    _expandSpan.textContent = "expand";
    _expandSpan.addEventListener("click", _expandInsuranceModal);
    content.appendChild(_expandSpan);

    banner.style.display = "";
    return;
  }

  // ── Resolved vote result state ───────────────────────────────
  banner.classList.remove("minimised");
  const insureCount  = v.insure_count ?? 0;
  const declineCount = (v.votes_cast ?? 0) - insureCount;
  const voteLabel    = insureCount > declineCount ? "INSURE" : "DECLINE";
  const color        = voteLabel === "INSURE" ? "var(--green)" : "var(--red)";
  content.innerHTML  =
    `🃏 Insurance vote closed — <strong style="color:${color}">${voteLabel}</strong> ` +
    `(${insureCount} insure / ${declineCount} decline) · waiting for dealer to reveal`;
  banner.style.display = "block";
}

function _renderInsuranceBannerOutcome(results) {
  const banner  = document.getElementById("insurance-vote-banner");
  const content = document.getElementById("insurance-vote-banner-content");
  if (!banner || !content) return;
  banner.classList.remove("minimised");
  const parts = results.map(r => {
    const icon    = r.group_won ? "✅" : "❌";
    const color   = r.group_won ? "var(--green)" : "var(--red)";
    const voted   = r.insured ? "INSURE" : "DECLINE";
    const outcome = r.outcome_text || (r.group_won ? "correct call" : "wrong call");
    return `${icon} <strong style="color:${color}">${escapeHtml(r.player)}: ${voted}</strong> — ${outcome}`;
  });
  content.innerHTML = `🃏 Insurance result — ${parts.join(" &nbsp;·&nbsp; ")}`;
  banner.style.display = "block";
}

function _expandInsuranceModal() {
  _insuranceMinimised = false;
  openModal("insurance-modal-overlay", { useClass: true });
  const banner = document.getElementById("insurance-vote-banner");
  if (banner) { banner.classList.remove("minimised"); banner.style.display = "none"; }
}

async function castInsuranceVote(bjPlayer, handIdx, vote, voterName = null) {
  _requestsInFlight++;
  try {
    const res  = await fetch("/vote_insurance", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        bj_player: bjPlayer, hand_idx: handIdx, vote,
        ...(voterName ? { voter_name: voterName } : {}),
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
    else appendLog(`  Insurance vote failed: ${data.error || "unknown error"}\n`);
  } catch (_) {
    appendLog("  Insurance vote failed: network error\n");
  } finally {
    _requestsInFlight--;
  }
}


// ── Milestone: 50-sip handout feature ───────────────────────────────────────

function renderMilestoneState(state) {
  const ms     = state && state.pending_milestone;
  const result = state && state.last_milestone_result;

  // ── Drink notification for recipients (fires once per result) ──────────
  if (result) {
    const rKey = `${result.boundary}:${result.winner}`;
    if (rKey !== DrinkUI.lastMilestoneResultKey) {
      DrinkUI.lastMilestoneResultKey = rKey;
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
    if (DrinkUI.lastMilestoneKey && document.getElementById("milestone-modal-overlay").classList.contains("open")) {
      _closeMilestoneModal();
    }
    return;
  }

  const key       = `${ms.boundary}:${ms.winner}`;
  const iAmWinner = !!ms.i_am_winner;  // server-authoritative; no JS name-matching needed

  // Show announcement toast exactly once per new milestone (all players)
  if (key !== DrinkUI.lastMilestoneKey) {
    DrinkUI.lastMilestoneKey     = key;
    DrinkUI.milestoneAllocations = {};
    _showMilestoneToast(ms);
  }

  if (iAmWinner) {
    _hideWaitingBanner();
    // Open the handout modal exactly once for this milestone
    if (DrinkUI.milestoneModalOpened !== key) {
      DrinkUI.milestoneModalOpened = key;
      // Short delay so the toast is visible before modal covers it
      setTimeout(() => _openMilestoneModal(ms, state), 600);
    } else {
      // Modal already open — keep timer in sync; auto-submit when time's up
      _updateMilestoneTimer(ms.seconds_left);
      if (ms.seconds_left <= 0) {
        const overlay = document.getElementById("milestone-modal-overlay");
        if (overlay && overlay.classList.contains("open")) {
          submitMilestoneHandout();
        }
      }
    }
  } else {
    // Non-winners: persistent waiting banner with live countdown
    _showWaitingBanner(ms);
  }
}

function _showMilestoneToast(ms) {
  const html = `🎉 ${escapeHtml(ms.winner)} hit ${ms.boundary} sips!`;
  const _show = () => {
    const toast = document.getElementById("milestone-toast");
    if (!toast) return;
    toast.innerHTML = html;
    toast.classList.remove("show");
    void toast.offsetWidth;
    toast.classList.add("show");
    setTimeout(() => _hideMilestoneToast(), 5000);
  };
  if (typeof _bustVoteOpen === "function" && _bustVoteOpen()) {
    ToastUI.queue.push(_show);
  } else {
    _show();
  }
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
  if (sub)   sub.textContent   = `Hand out up to ${ms.handout} sips — unassigned ones come back to you.`;

  // Build stepper list from current players except self
  const players = (lastState && lastState.players || []).filter(
    n => n.toLowerCase() !== (myName || "").toLowerCase()
  );
  // Drop any allocation entries for players no longer in the roster (e.g. a
  // player left/was kicked between two milestones with the same
  // boundary+winner, so DrinkUI.lastMilestoneKey didn't change and the dict wasn't
  // reset) — stale entries would otherwise count toward `used` and could
  // block the winner from allocating their full handout.
  Object.keys(DrinkUI.milestoneAllocations).forEach(n => {
    if (!players.includes(n)) delete DrinkUI.milestoneAllocations[n];
  });

  // Initialize allocations to 0 for everyone
  players.forEach(n => { if (!(DrinkUI.milestoneAllocations[n] >= 0)) DrinkUI.milestoneAllocations[n] = 0; });

  _renderMilestoneSteppers(players, ms.handout);
  _updateMilestoneTimer(ms.seconds_left);
  openModal("milestone-modal-overlay", { useClass: true });
}

function _closeMilestoneModal() {
  closeModal("milestone-modal-overlay", { useClass: true });
}

function _renderMilestoneSteppers(players, total) {
  const container = document.getElementById("milestone-steppers");
  if (!container) return;
  container.innerHTML = "";
  players.forEach(name => {
    const row = document.createElement("div");
    row.className = "ms-stepper";
    const val = DrinkUI.milestoneAllocations[name] || 0;

    // Build with DOM nodes — onclick string interpolation breaks for names
    // containing apostrophes (browsers decode &#39; → ' before JS eval).
    // Count span uses data-ms-player instead of id so the name never lands
    // in a CSS selector or HTML attribute raw.
    const nameSpan = document.createElement("span");
    nameSpan.className = "ms-name";
    nameSpan.textContent = name;

    const decBtn = document.createElement("button");
    decBtn.textContent = "−";
    decBtn.addEventListener("click", () => milestoneAdjust(name, -1));

    const countSpan = document.createElement("span");
    countSpan.className = "ms-count";
    countSpan.dataset.msPlayer = name;
    countSpan.textContent = val;

    const incBtn = document.createElement("button");
    incBtn.textContent = "+";
    incBtn.addEventListener("click", () => milestoneAdjust(name, +1));

    row.appendChild(nameSpan);
    row.appendChild(decBtn);
    row.appendChild(countSpan);
    row.appendChild(incBtn);
    container.appendChild(row);
  });
  _updateMilestoneRemaining(total);
}

function milestoneAdjust(name, delta) {
  const ms = lastState && lastState.pending_milestone;
  const total = ms ? ms.handout : 5;
  const cur   = DrinkUI.milestoneAllocations[name] || 0;
  const used  = Object.values(DrinkUI.milestoneAllocations).reduce((a, b) => a + b, 0);
  const newVal = Math.max(0, Math.min(cur + delta, cur + (total - used) + (delta < 0 ? 0 : 0)));

  if (delta > 0 && used >= total) return;  // budget exhausted

  DrinkUI.milestoneAllocations[name] = Math.max(0, cur + delta);
  const el = document.querySelector(`[data-ms-player="${CSS.escape(name)}"]`);
  if (el) el.textContent = DrinkUI.milestoneAllocations[name];
  _updateMilestoneRemaining(total);
}

function _updateMilestoneRemaining(total) {
  const used = Object.values(DrinkUI.milestoneAllocations).reduce((a, b) => a + b, 0);
  const left = total - used;
  const rem  = document.getElementById("milestone-remaining");
  const btn  = document.getElementById("milestone-submit-btn");
  if (rem) {
    if (left === 0) {
      rem.textContent = "✓ All sips assigned";
      rem.style.color = "var(--green)";
    } else {
      rem.textContent = `${left} sip${left !== 1 ? "s" : ""} back to you`;
      rem.style.color = "var(--yellow)";
    }
  }
  if (btn) btn.disabled = false;  // always submittable — unassigned sips go to winner
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
  const used = Object.values(DrinkUI.milestoneAllocations).reduce((a, b) => a + b, 0);

  const btn = document.getElementById("milestone-submit-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Sending…"; }

  try {
    const res = await fetch("/claim_milestone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, allocations: DrinkUI.milestoneAllocations }),
    });
    const data = await res.json();
    if (data.ok) {
      _closeMilestoneModal();
      DrinkUI.lastMilestoneKey     = null;
      DrinkUI.milestoneModalOpened = null;
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

