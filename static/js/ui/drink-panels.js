// ============================================================
// DRINK & HANDOUT PANELS
// ============================================================
// Table-wide popups and toasts for the drink side of a round: the bust-vote
// side bet, Dealer Lottery (entry, reveal, handout), Targeted Drinking handout,
// Normal-mode buy-in handout, and the player toasts. Split out of admin.js;
// the panel instances are mounted from table.js (buildDigitalUI) and rendered
// from _syncDigitalUI.


// ============================================================
// BUST VOTE SIDE BET
// ============================================================

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
    else if (data.error) showToast(data.error, "error");
  } catch (_) {} finally {
    _requestDone();
  }
}


// Bust-vote confirmation modal + post-round status indicator; mount() uses one delegated click listener so it survives #bust-vote-players-wrap being rebuilt on every render (Improvements.md item 7).
class BustVotePanel {
  constructor() {
    this.modalOpen   = false;
    this.timerHandle = null;
    this.cardsSig    = null;   // last rendered local votes, see renderVoteCards
  }

  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".bv-vote-btn");
      if (!btn) return;
      submitBustVote(btn.dataset.vote, btn.dataset.name || undefined);
    });
  }

  open(secondsLeft) {
    if (this.modalOpen) return;
    const overlay = openModal("bust-vote-modal-overlay");
    if (!overlay) return;
    this.modalOpen = true;

    const bar      = document.getElementById("bust-vote-timer-bar");
    const label    = document.getElementById("bust-vote-timer-label");
    const duration = secondsLeft || 15;   // guard against 0

    let secs = duration;
    const tick = () => {
      if (!this.modalOpen) return;

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
          this.close();
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
            this.close();
          })();
        } else {
          this.close();
        }
        return;
      }
      // Only decrement locally when this tick wasn't just resynced from the
      // server — otherwise the next resync overwrites this and we end up
      // double-decrementing (timer skips a number every poll).
      if (!resynced) secs--;
      this.timerHandle = setTimeout(tick, 1000);
    };
    tick();
  }

  // Render per-player vote cards inside the modal.
  // Called whenever state updates while the modal is open.
  renderVoteCards(state) {
    const wrap = document.getElementById("bust-vote-players-wrap");
    if (!wrap) return;

    const bustVotes = state.my_bust_votes || {};
    // Only show human local players active in the game (skip NPCs)
    const npcSet   = new Set([...(npcPlayers || [])]);
    const locals   = myNames.filter(n => !npcSet.has(n));
    const multiLocal = locals.length > 1;

    // Only rebuild when a local vote changed. Polls re-render every 800ms;
    // replacing the buttons between pointerdown and pointerup sends the click
    // to the wrap instead of the button, so a tap was lost and had to be repeated.
    const sig = JSON.stringify(locals.map(n => [n, bustVotes[n] || null]));
    if (sig === this.cardsSig && wrap.childElementCount) return;
    this.cardsSig = sig;

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
        // Buttons -- no addEventListener here, mount()'s delegated
        // listener reads these data attributes instead.
        const btns = document.createElement("div");
        btns.classList.add("bv-btn-row");

        const bustBtn = document.createElement("button");
        bustBtn.className = "btn green bv-vote-btn";
        bustBtn.textContent = "💥 Bet Bust";
        bustBtn.dataset.vote = "bust";
        if (multiLocal) bustBtn.dataset.name = name;

        const passBtn = document.createElement("button");
        passBtn.className = "btn muted-btn bv-vote-btn";
        passBtn.textContent = "Pass";
        passBtn.dataset.vote = "pass";
        if (multiLocal) passBtn.dataset.name = name;

        btns.appendChild(bustBtn);
        btns.appendChild(passBtn);
        card.appendChild(btns);
      }

      wrap.appendChild(card);
    });
  }

  close() {
    if (!this.modalOpen) return;
    this.modalOpen = false;
    this.cardsSig  = null;
    if (this.timerHandle) { clearTimeout(this.timerHandle); this.timerHandle = null; }
    closeModal("bust-vote-modal-overlay");
  }

  render(state) {
    const statusEl      = document.getElementById("bust-vote-status");
    const statusElRound = document.getElementById("bust-vote-status-round");

    // Modal: open when window is open and any local player hasn't voted yet.
    // Delay until deal animation finishes so the modal doesn't cover the cards.
    const bustVotes  = state.my_bust_votes || {};
    const anyUnvoted = Object.values(bustVotes).some(v => v === null || v === undefined);
    if (state.bust_vote_window_open && anyUnvoted
        && myRole !== null && myRole !== ROLE.SPECTATOR
        && !_dealAnimating) {
      this.open(state.bust_vote_seconds_left || 15);
    } else if (!state.bust_vote_window_open) {
      this.close();
    }

    // Re-render player cards while modal is open (handles partial local votes)
    if (this.modalOpen) {
      this.renderVoteCards(state);
      // Update tally
      const votes   = state.bust_votes || {};
      const decided = Object.keys(votes).length;
      const bustCnt = Object.values(votes).filter(v => v === "bust").length;
      const tally   = document.getElementById("bust-vote-modal-tally");
      if (tally) tally.textContent = decided
        ? `${bustCnt} betting bust · ${decided - bustCnt} passed`
        : "";
      // Auto-close if all local players have now voted
      if (!anyUnvoted) this.close();
    }

    // Give-panel: show at round-over if this client has pending handouts
    bustGivePanel.render(state);

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
}

const bustVotePanel = new BustVotePanel();

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
  } catch (_) {} finally {
    _requestDone();
  }
}

// ── Bust-vote handout give-panel component (Improvements.md item 7,
// Option A: class-based, no framework) ──────────────────────────────────
// Encapsulates #bust-give-overlay. mount() attaches one delegated click
// listener for handout buttons (replacing the former per-button
// onclick="giveBustSip(...)" string); render(state) rebuilds the panel
// exactly as the old _renderBustGivePanel() function did.
class BustGivePanel {
  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".bgp-give-btn");
      if (btn) giveBustSip(btn.dataset.winner, btn.dataset.recipient);
    });
  }

  render(state) {
    if (!this.el) return;   // not mounted yet (e.g. referee mode never mounts it)
    const overlay = this.el;
    const body    = overlay.querySelector("#bust-give-body");
    if (!body) return;

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

    const _bw = (typeof state !== "undefined" && state && state.wager) || 1;
    const _bwStr = `1 wager (${_bw} ${_bw === 1 ? "sip" : "sips"})`;
    body.innerHTML = pending.map((winnerName, idx) => {
      const label = pending.length > 1
        ? `🎉 <strong>${escapeHtml(winnerName)}</strong> called it! Give ${_bwStr} to:`
        : `🎉 You called it! Give ${_bwStr} to:`;
      // No onclick= here -- mount()'s delegated listener handles taps.
      const btns = allPlayers
        .filter(n => n.toLowerCase() !== winnerName.toLowerCase())
        .map(n => `<button class="btn wide bgp-give-btn"
            data-winner="${escapeHtml(winnerName)}" data-recipient="${escapeHtml(n)}"
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
}

const bustGivePanel = new BustGivePanel();

// ============================================================
// DEALER LOTTERY (Rules.md §5.9)
// ============================================================

// ── Dealer Lottery entry panel component (Improvements.md item 7,
// Option A: class-based, no framework) ───────────────────────────────────
// Stake label: the lottery stake is 0-5 wagers (sips = wagers x table wager).
function dlStakeLabel(n) {
  const w = (typeof lastState !== "undefined" && lastState && lastState.wager) || 1;
  return `${n} wager${n === 1 ? "" : "s"} (${n * w} sip${n * w === 1 ? "" : "s"})`;
}

// Encapsulates the entry modal (countdown timer, per-player stake sliders
// + Enter buttons). mount() attaches one delegated "input" listener (live
// slider value) and one delegated "click" listener (Enter button) --
// replacing addEventListener calls re-attached on every rebuild of
// #dealer-lottery-players-wrap. render(state) is the per-poll entry point,
// replacing the old updateDealerLotteryUI() function.
class DealerLotteryEntryPanel {
  constructor() {
    this.modalOpen   = false;
    this.timerHandle = null;
    // Slider values persist here across the per-poll re-render in
    // renderCards() (that render rebuilds the DOM from scratch, so without
    // this the slider would visibly snap back to 0 on every poll tick).
    this.pendingX = {};
  }

  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;

    el.addEventListener("input", e => {
      const slider = e.target.closest(".dl-x-slider");
      if (!slider) return;
      const val = parseInt(slider.value, 10) || 0;
      this.pendingX[slider.dataset.dlName] = val;
      const valueLbl = slider.closest(".dl-entry-card").querySelector(".dl-x-value");
      if (valueLbl) valueLbl.textContent = dlStakeLabel(val);
    });

    el.addEventListener("click", e => {
      const btn = e.target.closest(".dl-enter-btn");
      if (!btn) return;
      const name   = btn.dataset.dlName;
      const slider = btn.closest(".dl-entry-row").querySelector(".dl-x-slider");
      const x      = slider ? (parseInt(slider.value, 10) || 0) : 0;
      delete this.pendingX[name];
      const npcSet     = new Set([...(npcPlayers || [])]);
      const locals     = myNames.filter(n => !npcSet.has(n));
      const multiLocal = locals.length > 1;
      submitDealerLotteryX(x, multiLocal ? name : undefined);
    });
  }

  open(secondsLeft) {
    if (this.modalOpen) return;
    const overlay = openModal("dealer-lottery-modal-overlay");
    if (!overlay) return;
    this.modalOpen = true;

    const bar      = document.getElementById("dealer-lottery-timer-bar");
    const label    = document.getElementById("dealer-lottery-timer-label");
    const duration = secondsLeft || 20;

    let secs = duration;
    const tick = () => {
      if (!this.modalOpen) return;

      let resynced = false;
      if (lastState && lastState.dealer_lottery) {
        const pending = lastState.dealer_lottery.pending;
        if (pending && typeof pending.seconds_left === "number") {
          secs = pending.seconds_left;
          resynced = true;
        } else if (!pending) {
          // Server says the window already closed (resolved or expired).
          this.close();
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
            this.close();
          })();
        } else {
          this.close();
        }
        return;
      }
      if (!resynced) secs--;
      this.timerHandle = setTimeout(tick, 1000);
    };
    tick();
  }

  close() {
    if (!this.modalOpen) return;
    this.modalOpen = false;
    if (this.timerHandle) { clearTimeout(this.timerHandle); this.timerHandle = null; }
    this.pendingX = {};
    closeModal("dealer-lottery-modal-overlay");
  }

  // Render per-player entry rows (stake slider 0-5 + Enter button) inside the modal.
  renderCards(state) {
    const wrap = document.getElementById("dealer-lottery-players-wrap");
    if (!wrap) return;

    const pending   = (state.dealer_lottery && state.dealer_lottery.pending) || {};
    const myEntries = pending.my_entries || {};
    const npcSet    = new Set([...(npcPlayers || [])]);
    const locals    = myNames.filter(n => !npcSet.has(n));
    const multiLocal = locals.length > 1;

    // No addEventListener here -- mount()'s delegated listeners handle input/click.
    wrap.innerHTML = locals.map(name => {
      const answered = myEntries[name];
      const nameLbl  = multiLocal ? `<span class="dl-name-lbl">${escapeHtml(name)}</span>` : "";

      if (answered !== null && answered !== undefined) {
        return `<div class="dl-entry-card">
          <div class="dl-entry-top">${nameLbl}<span class="dl-status">Entered: ${dlStakeLabel(answered)}</span></div>
        </div>`;
      }

      const startVal = this.pendingX[name] ?? 0;
      return `<div class="dl-entry-card">
        <div class="dl-entry-top">${nameLbl}<span class="dl-x-value">${dlStakeLabel(startVal)}</span></div>
        <div class="dl-entry-row">
          <input type="range" class="dl-x-slider" min="0" max="5" step="1" value="${startVal}" data-dl-name="${escapeHtml(name)}">
          <button class="btn dl-enter-btn" data-dl-name="${escapeHtml(name)}">Enter</button>
        </div>
      </div>`;
    }).join("");
  }

  render(state) {
    const dl = state.dealer_lottery || {};
    const pending = dl.pending;

    if (pending && myRole !== null && myRole !== ROLE.SPECTATOR && !_dealAnimating) {
      this.open(pending.seconds_left || 20);
    } else if (!pending) {
      this.close();
    }

    if (this.modalOpen) {
      this.renderCards(state);
      const answered = document.getElementById("dealer-lottery-answered");
      if (answered && pending) {
        answered.textContent = `${pending.answered_count}/${pending.total_count} answered`;
      }
    }

    dealerLotteryGivePanel.render(state);
  }
}

const dealerLotteryEntryPanel = new DealerLotteryEntryPanel();

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

let _dealerLotteryRevealOpen = false;

// Builds the score/BUST/STAND tags for a finished lottery hand, matching
// handBlock()'s own tag markup so the mid-animation swap looks identical
// to a normally-rendered hand-meta div.
function _dlHandMetaHtml(score, bust) {
  return `<span class="score">${score}</span>` +
    (bust ? `<span class="bust">BUST</span>` : `<span class="stood">STAND</span>`);
}

// Deals the extra (post-split) cards of one hand into the DOM one at a
// time, fading/sliding each in like the main table's animateDeal(), then
// reveals that hand's final score/BUST/STAND tag.
async function _dlAnimateHandCards(block, cards, score, bust) {
  const delay = ms => new Promise(r => setTimeout(r, ms));
  const row = block.querySelector(".cards-row");
  for (let i = 1; i < cards.length; i++) {
    const el = cardEl(cards[i]);
    el.style.transition = "none";
    el.style.opacity = "0";
    el.style.transform = "translateY(-16px) scale(.85)";
    row.appendChild(el);
    void el.offsetHeight; // force layout so the hidden state actually paints before transitioning
    el.style.transition = "opacity .22s ease-out, transform .22s ease-out";
    el.style.opacity = "1";
    el.style.transform = "translateY(0) scale(1)";
    await delay(380);
  }
  const meta = block.querySelector(".hand-meta");
  if (meta) meta.innerHTML = _dlHandMetaHtml(score, bust);
}

// Visual reveal: the dealer's pair actually splitting into fresh hands --
// always at least two, more if a hand re-split -- shown as real card
// visuals (reuses handBlock()/cardEl() from table-render.js — the same
// rendering the main table uses), animated in this order:
//   1. The dealer's original pair separates into two fresh hands (H1, H2).
//   2. H1 is played out fully -- including, if its own 2nd card pairs up
//      again, revealing that re-split (a new hand appears) BEFORE H1's own
//      post-split cards are dealt, then finishing H1's cards, then playing
//      the re-split hand the same way (recursively, in case IT re-splits
//      too) -- never H2.
//   3. H2 is played out fully, same rule.
// Each hand's parent_index (app/services/dealer_lottery.py) says which
// other hand it split off from (null for H1/H2 themselves), so a hand's
// block is only ever created at the moment it actually splits off, instead
// of every eventual hand (including future re-splits) appearing complete
// from the very start.
async function _showDealerLotteryRevealModal(result) {
  if (!result) return;
  const hands  = document.getElementById("dealer-lottery-reveal-hands");
  const payout = document.getElementById("dealer-lottery-reveal-payout");
  const sub    = document.getElementById("dealer-lottery-reveal-sub");
  const closeBtn = document.getElementById("dealer-lottery-reveal-close-btn");
  if (!hands) return;

  const handList = result.hands || [];
  if (sub) {
    sub.textContent = handList.length > 2
      ? `The dealer's pair re-splits into ${handList.length} fresh hands:`
      : "The dealer's pair splits into two fresh hands:";
  }
  if (payout) payout.innerHTML = "";
  if (closeBtn) closeBtn.disabled = true;

  hands.innerHTML = "";
  _dealerLotteryRevealOpen = true;
  _dlAckSent = false;
  openModal("dealer-lottery-reveal-overlay", { useClass: true });

  const delay = ms => new Promise(r => setTimeout(r, ms));

  // Group hands by parent so a re-split child is only revealed at the
  // moment it actually splits off. Children of the same parent arrive from
  // the backend in reverse-chronological order (the LAST re-split is
  // listed first, since it finishes its own resolution first) -- reverse
  // so they're revealed in the order they actually split off.
  const childrenOf = new Map();
  const roots = [];
  handList.forEach((h, i) => {
    if (h.parent_index === null || h.parent_index === undefined) {
      roots.push(i);
    } else {
      if (!childrenOf.has(h.parent_index)) childrenOf.set(h.parent_index, []);
      childrenOf.get(h.parent_index).push(i);
    }
  });
  childrenOf.forEach(list => list.reverse());

  let displayNum = 0;
  const blocks = new Array(handList.length);

  // Creates hand i's block showing just its first card (its "pair
  // separated" / "split off" moment), fading in like a freshly dealt card.
  function revealBlock(i) {
    displayNum++;
    const block = handBlock({ cards: [handList[i].cards[0]], score: null }, `Split Hand ${displayNum}`);
    block.style.transition = "none";
    block.style.opacity    = "0";
    block.style.transform  = "translateY(-16px) scale(.85)";
    hands.appendChild(block);
    void block.offsetHeight; // force layout so the hidden state actually paints before transitioning
    block.style.transition = "opacity .22s ease-out, transform .22s ease-out";
    block.style.opacity    = "1";
    block.style.transform  = "translateY(0) scale(1)";
    blocks[i] = block;
  }

  // Recursively plays hand i: reveal any re-split children first (their
  // split-off moment), then deal this hand's own remaining cards, then
  // play each child in turn -- so a hand's own cards never appear before
  // all of its children have had their split moment shown, and a child is
  // never played before its parent has fully finished.
  async function playHand(i) {
    const children = childrenOf.get(i) || [];
    for (const childIdx of children) {
      revealBlock(childIdx);
      await delay(250);
    }
    await _dlAnimateHandCards(blocks[i], handList[i].cards, handList[i].score, handList[i].bust);
    await delay(children.length ? 300 : 200);
    for (const childIdx of children) {
      await playHand(childIdx);
    }
  }

  // Step 1: the dealer's original pair separating into two fresh hands.
  revealBlock(roots[0]);
  await delay(180);
  revealBlock(roots[1]);
  await delay(350);

  // Steps 2 & 3: play H1 fully (incl. any of its own re-splits), then H2.
  await playHand(roots[0]);
  await playHand(roots[1]);
  await delay(150);

  if (payout) {
    const entries        = result.entries || {};
    const drinkAmounts    = result.drink_amounts || {};
    const creditAmounts   = result.credit_amounts || {};
    const pendingHandouts = result.pending_handouts || {};
    const participants    = Object.keys(entries).filter(n => entries[n] > 0);

    const nHands = handList.length;
    const headline = result.busted >= 2 ? `${result.busted} of ${nHands} hands busted!`
      : result.busted === 0 ? "No hand busted." : "1 hand busted — half the stake pays out.";

    if (!participants.length) {
      payout.innerHTML = `<div class="dl-reveal-headline">${headline}</div>Nobody entered, so nothing happens.`;
    } else {
      const rows = participants.map(name => {
        const bits = [];
        if (drinkAmounts[name]) {
          bits.push(`drinks <strong>${drinkAmounts[name]}</strong> sip${drinkAmounts[name] === 1 ? "" : "s"}`);
        }
        if (creditAmounts[name]) {
          bits.push(`credits <strong>${creditAmounts[name]}</strong> sip${creditAmounts[name] === 1 ? "" : "s"} off this round`);
        }
        if (pendingHandouts[name]) {
          bits.push(`hands out <strong>${pendingHandouts[name]}</strong> sip${pendingHandouts[name] === 1 ? "" : "s"}`);
        }
        if (!bits.length) bits.push("nothing happens this time");
        return `<li><span class="dl-reveal-name">${escapeHtml(name)}</span> ${bits.join(", ")}</li>`;
      });
      payout.innerHTML = `<div class="dl-reveal-headline">${headline}</div>` +
        `<ul class="dl-reveal-list">${rows.join("")}</ul>`;
    }
  }

  if (closeBtn) closeBtn.disabled = false;
}

function closeDealerLotteryRevealModal() {
  _dealerLotteryRevealOpen = false;
  closeModal("dealer-lottery-reveal-overlay", { useClass: true });
  ackDealerLotteryReveal();
}

// Tell the server this client is done with the reveal -- the sip handout
// only starts once every connected player has done so.
let _dlAckSent = false;
async function ackDealerLotteryReveal() {
  if (_dlAckSent) return;
  _dlAckSent = true;
  try {
    const res  = await fetch("/dealer_lottery/ack_reveal", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) { _dlAckSent = false; }
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
  } catch (_) {} finally {
    _requestDone();
  }
}

// ── Dealer Lottery handout give-panel component (Improvements.md item 7,
// Option A: class-based, no framework) ──────────────────────────────────
// Same pattern as BustGivePanel above: mount() attaches one delegated click
// listener (replacing the former per-button
// onclick="giveDealerLotterySip(...)" string); render(state) rebuilds the
// panel exactly as the old _renderDealerLotteryGivePanel() function did.
class DealerLotteryGivePanel {
  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".bgp-give-btn");
      if (btn) giveDealerLotterySip(btn.dataset.giver, btn.dataset.recipient);
    });
  }

  render(state) {
    if (!this.el) return;   // not mounted yet (e.g. referee mode never mounts it)
    const overlay = this.el;
    const body    = overlay.querySelector("#dealer-lottery-give-body");
    if (!body) return;

    const dl      = state.dealer_lottery || {};
    const pending = dl.my_pending_handouts || {};
    const givers  = Object.keys(pending);
    if (!givers.length) {
      overlay.style.display = "none";
      body.innerHTML = "";
      return;
    }

    // Defer behind the milestone prompt, the bust-vote handout prompt, and
    // this event's own reveal modal, so popups appear one after another,
    // never stacked.
    if (state.pending_milestone || (state.my_bust_handout_pending || []).length
        || _dealerLotteryRevealOpen) {
      overlay.style.display = "none";
      body.innerHTML = "";
      return;
    }

    // Reveal closed here but others are still watching: say why the handout
    // hasn't started instead of showing nothing.
    if (dl.reveal_pending) {
      const names = (dl.reveal_waiting_on || []).map(escapeHtml).join(", ");
      overlay.style.display = "flex";
      body.innerHTML = `<div class="bgp-entry"><div class="bgp-winner-label">🎰 You have sips to hand out!</div>
        <div style="font-size:12px;color:var(--muted)">⏳ Waiting for ${names || "everyone"} to close the draw reveal…</div></div>`;
      return;
    }

    const allPlayers = state.players || [];
    const secsLeft    = dl.handout_seconds_left || 0;
    overlay.style.display = "flex";

    const timerColour = secsLeft <= 5 ? "var(--red)" : secsLeft <= 10 ? "var(--yellow)" : "var(--green)";
    const timerStr = secsLeft > 0
      ? `<div style="font-size:12px;color:${timerColour};font-weight:700;margin-bottom:10px">⏱ ${secsLeft}s — you keep them if time runs out</div>`
      : "";

    // No onclick= here -- mount()'s delegated listener handles taps.
    body.innerHTML = givers.map(giverName => {
      const amount = pending[giverName];
      const label = givers.length > 1
        ? `🎰 <strong>${escapeHtml(giverName)}</strong> won the Dealer Lottery! Give ${amount} sip(s) to:`
        : `🎰 You won the Dealer Lottery! Give ${amount} sip(s) to:`;
      const btns = allPlayers
        .filter(n => n.toLowerCase() !== giverName.toLowerCase())
        .map(n => `<button class="btn wide bgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="${escapeHtml(n)}"
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
}

const dealerLotteryGivePanel = new DealerLotteryGivePanel();

async function giveTargetedDrinkingSip(giverName, recipientName) {
  _requestsInFlight++;
  try {
    const res  = await fetch("/targeted_drinking/give_sip", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        room_code: roomCode, client_id: clientId,
        giver_name: giverName, recipient_name: recipientName,
      }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {} finally {
    _requestDone();
  }
}

// ── Targeted Drinking perfect-graduation handout give-panel — same
// class-based pattern as DealerLotteryGivePanel above (mount() attaches one
// delegated click listener, render(state) rebuilds from scratch). ─────────
class TargetedDrinkingGivePanel {
  mount(el) {
    if (this.el) return;
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".bgp-give-btn");
      if (btn) giveTargetedDrinkingSip(btn.dataset.giver, btn.dataset.recipient);
    });
  }

  render(state) {
    if (!this.el) return;
    const overlay = this.el;
    const body    = overlay.querySelector("#targeted-drinking-give-body");
    if (!body) return;

    const td      = state.targeted_drinking || {};
    const pending = td.my_pending_handouts || {};
    const givers  = Object.keys(pending);
    if (!givers.length) {
      overlay.style.display = "none";
      body.innerHTML = "";
      return;
    }

    // Defer behind the milestone prompt, the bust-vote handout prompt, the
    // Dealer Lottery reveal, and the Targeted Drinking mini-round's own
    // reveal modal, so popups appear one after another, never stacked.
    if (state.pending_milestone || (state.my_bust_handout_pending || []).length
        || _dealerLotteryRevealOpen
        || (typeof targetedDrinkingPanel !== "undefined" && targetedDrinkingPanel.phase === "reveal")) {
      overlay.style.display = "none";
      body.innerHTML = "";
      return;
    }

    const allPlayers = state.players || [];
    const secsLeft    = td.handout_seconds_left || 0;
    overlay.style.display = "flex";

    const timerColour = secsLeft <= 5 ? "var(--red)" : secsLeft <= 10 ? "var(--yellow)" : "var(--green)";
    const timerStr = secsLeft > 0
      ? `<div style="font-size:12px;color:${timerColour};font-weight:700;margin-bottom:10px">⏱ ${secsLeft}s — you keep them if time runs out</div>`
      : "";

    // No onclick= here -- mount()'s delegated listener handles taps.
    body.innerHTML = givers.map(giverName => {
      const amount = pending[giverName];
      const label = `🏆 <strong>${escapeHtml(giverName)}</strong> graduated flawlessly! Give ${amount} sip(s) to:`;
      const btns = allPlayers
        .filter(n => n.toLowerCase() !== giverName.toLowerCase())
        .map(n => `<button class="btn wide bgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="${escapeHtml(n)}"
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
}

const targetedDrinkingGivePanel = new TargetedDrinkingGivePanel();


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
    const _gw = (typeof state !== "undefined" && state && state.wager) || 1;
    return `🎁 ${r.winner} gave 1 wager (${_gw} ${_gw === 1 ? "sip" : "sips"}) to ${r.recipient}`;
  });
  // Red if I gave away a sip or forfeited (drink), green otherwise.
  const iDrink = results.some(r =>
    (r.forfeited && _myNames.includes(r.winner)) ||
    (!r.forfeited && _myNames.includes(r.recipient))
  );
  _firePlayerToast(parts.join(" · "), iDrink, 6000);
}

// Mirrors showBustHandoutToast exactly, for Targeted Drinking's own
// perfect-graduation handout -- without this the recipient of a graduate's
// handout had no clear indication they now owe sips (only a silent bump in
// their session sip total).
function showTargetedDrinkingHandoutToast(results) {
  if (!results || !results.length) return;
  const _myNames = (typeof myNames !== "undefined" && myNames) ? myNames : [];
  const parts = results.map(r => {
    if (r.forfeited) return `⏱️ ${r.giver} didn't choose in time — drinks it themselves`;
    return `🏆 ${r.giver} gave a sip to ${r.recipient}`;
  });
  // Red if I gave away a sip or forfeited (drink), green otherwise.
  const iDrink = results.some(r =>
    (r.forfeited && _myNames.includes(r.giver)) ||
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


// ── Normal-mode buy-in handout (players above the buy-in hand out a sip) ──
async function giveBuyinSip(giverName, recipientName) {
  try {
    const res  = await fetch("/buyin_handout/give", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId,
                                giver_name: giverName, recipient_name: recipientName }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

// Normal-mode handout picker for players above the buy-in. Same shape as
// DealerLotteryGivePanel: one delegated click listener, render(state) rebuilds.
class BuyinGivePanel {
  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".bgp-give-btn");
      if (btn) giveBuyinSip(btn.dataset.giver, btn.dataset.recipient);
    });
  }

  render(state) {
    if (!this.el) return;
    const body = this.el.querySelector("#buyin-give-body");
    if (!body) return;

    const pending = state.my_buyin_handouts || {};
    const givers  = Object.keys(pending);
    // Wait for the round to be fully over so the result isn't hidden behind the picker.
    if (!givers.length || state.phase !== "round-over") {
      this.el.style.display = "none";
      body.innerHTML = "";
      return;
    }

    this.el.style.display = "flex";
    const allPlayers = state.players || [];
    body.innerHTML = givers.map(giverName => {
      const amount = pending[giverName];
      const label = givers.length > 1
        ? `🍻 <strong>${escapeHtml(giverName)}</strong> is above the buy-in! Hand out ${amount} sip(s) to:`
        : `🍻 You're above the buy-in! Hand out ${amount} sip(s) to:`;
      const btns = allPlayers
        .filter(n => n.toLowerCase() !== giverName.toLowerCase())
        .map(n => `<button class="btn wide bgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="${escapeHtml(n)}"
            >${escapeHtml(n)}</button>`)
        .join("");
      const pass = `<button class="btn wide bgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="">Pass</button>`;
      const mb = givers.length > 1 ? " bgp-multi-entry" : "";
      return `<div class="bgp-entry${mb}">
        <div class="bgp-winner-label">${label}</div>
        <div class="bgp-btns-col">${btns}${pass}</div>
      </div>`;
    }).join(`<hr class="bgp-divider">`);
  }
}

const buyinGivePanel = new BuyinGivePanel();


// ── Comeback handout (L badge: a 5+ round losing streak just broke) ──
async function giveLHandout(giverName, recipientName) {
  try {
    const res  = await fetch("/l_handout/give", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId,
                                giver_name: giverName, recipient_name: recipientName }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
}

// Same shape as BuyinGivePanel, plus a countdown: sips nobody is picked for
// in time go back to the giver. Waits behind the other handout prompts
// (milestone, bust vote, Dealer Lottery, Targeted Drinking) and the rule
// vote, so popups come one after another, never stacked; the server holds
// the countdown while those are open.
class LHandoutGivePanel {
  mount(el) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;
    el.addEventListener("click", e => {
      const btn = e.target.closest(".lgp-give-btn");
      if (btn) giveLHandout(btn.dataset.giver, btn.dataset.recipient);
    });
  }

  _blocked(state) {
    const dl = state.dealer_lottery || {};
    return !!(state.pending_milestone
      || (state.my_bust_handout_pending || []).length
      || dl.pending || dl.reveal_pending || Object.keys(dl.my_pending_handouts || {}).length
      || (typeof _dealerLotteryRevealOpen !== "undefined" && _dealerLotteryRevealOpen)
      || (typeof targetedDrinkingPanel !== "undefined" && targetedDrinkingPanel.phase === "reveal")
      || ((state.rule_votes || {}).pending));
  }

  render(state) {
    if (!this.el) return;
    const body = this.el.querySelector("#l-handout-give-body");
    if (!body) return;

    const pending = state.my_l_handouts || {};
    const givers  = Object.keys(pending);
    if (!givers.length || state.phase !== "round-over" || this._blocked(state)) {
      this.el.style.display = "none";
      body.innerHTML = "";
      return;
    }

    this.el.style.display = "flex";
    const secs = state.l_handout_seconds_left || 0;
    const allPlayers = state.players || [];
    const html = givers.map(giverName => {
      const amount = pending[giverName];
      const sipWord = amount === 1 ? "sip" : "sips";
      const label = givers.length > 1
        ? `🔁 <strong>${escapeHtml(giverName)}</strong> broke the losing streak! Hand out ${amount} ${sipWord} to:`
        : `🔁 You broke your losing streak! Hand out ${amount} ${sipWord} to:`;
      const btns = allPlayers
        .filter(n => n.toLowerCase() !== giverName.toLowerCase())
        .map(n => `<button class="btn wide bgp-give-btn lgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="${escapeHtml(n)}"
            >${escapeHtml(n)}</button>`)
        .join("");
      const keep = `<button class="btn wide bgp-give-btn lgp-give-btn"
            data-giver="${escapeHtml(giverName)}" data-recipient="">Keep them (drink ${amount} myself)</button>`;
      const mb = givers.length > 1 ? " bgp-multi-entry" : "";
      return `<div class="bgp-entry${mb}">
        <div class="bgp-winner-label">${label}</div>
        <div class="bgp-btns-col">${btns}${keep}</div>
      </div>`;
    }).join(`<hr class="bgp-divider">`);
    body.innerHTML = html +
      `<div class="lgp-timer">⏱ ${secs}s · if nobody is picked, you drink them</div>`;
  }
}

const lHandoutGivePanel = new LHandoutGivePanel();
