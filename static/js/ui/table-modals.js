// ── Insurance vote panel component (Improvements.md item 7, Option A:
// class-based, no framework) ─────────────────────────────────────────────
// Encapsulates both insurance-vote surfaces -- the full modal
// (#insurance-modal-overlay) and the compact banner
// (#insurance-vote-banner) it minimises into. mount() attaches one
// delegated click listener per surface (replacing the modal's ad-hoc
// "_wired" flag on the minimize button, and the addEventListener calls
// re-attached on every rebuild of the vote buttons / expand span in both
// surfaces); updateVisibility(state) is the per-poll entry point,
// replacing the old updateInsuranceVisibility() function.
class InsurancePanel {
  constructor() {
    this.modalKey  = null;
    this.minimised = false;
  }

  mount(modalEl, bannerEl) {
    if (this.modalEl) return;   // idempotent -- buildGameUI() may run more than once
    this.modalEl  = modalEl;
    this.bannerEl = bannerEl;

    const onVoteClick = e => {
      const btn = e.target.closest("[data-ins-vote]");
      if (!btn) return;
      castInsuranceVote(btn.dataset.bjPlayer, Number(btn.dataset.handIdx),
        btn.dataset.insVote === "true", btn.dataset.voter || null);
    };

    modalEl.addEventListener("click", e => {
      if (e.target.closest("#insurance-modal-minimize")) {
        this.minimised = true;
        closeModal("insurance-modal-overlay", { useClass: true });
        return;
      }
      onVoteClick(e);
    });

    bannerEl.addEventListener("click", e => {
      if (e.target.closest(".ins-banner-expand")) { this._expand(); return; }
      onVoteClick(e);
    });
  }

  updateVisibility(state) {
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
    this.renderModal(state);
  }

  renderModal(state) {
    const overlay = document.getElementById("insurance-modal-overlay");
    if (!overlay) return;

    const openVotes = (state.insurance_votes || []).filter(v => !v.resolved);

    if (!openVotes.length) {
      this._closeModal();
      // If the vote just resolved, show the outcome in the banner instead of
      // hiding it immediately.  The backend clears insurance_result on new round,
      // so the banner disappears naturally without extra cleanup.
      const results = state.insurance_result;
      if (results && results.length) {
        this.renderBannerOutcome(results);
      } else {
        this.renderBanner(null);
      }
      return;
    }

    const v   = openVotes[0];
    const key = `${v.bj_player}:${v.hand_idx}`;

    if (this.modalKey !== key) {
      this.modalKey  = key;
      this.minimised = false;  // always expand on new vote
      openModal("insurance-modal-overlay", { useClass: true });
    }

    // Local multiplayer: find which local seats still need to vote
    const voterNames   = myNames.filter(n => n.toLowerCase() !== v.bj_player.toLowerCase());
    const votedNames   = Object.keys(v.votes_cast_by || {}).map(n => n.toLowerCase());
    const pendingLocal = voterNames.filter(n => !votedNames.includes(n.toLowerCase()));

    // Active voter: prefer first pending local seat, else fall back to myActiveName/myName
    const activeVoter  = pendingLocal.length > 0 ? pendingLocal[0]
                       : (myActiveName || myName);

    // If minimised, keep overlay closed — render compact banner instead
    if (this.minimised) {
      closeModal("insurance-modal-overlay", { useClass: true });
      this.renderBanner(v, true, activeVoter);
      return;
    }

    const allIn = (v.votes_cast != null && v.votes_needed != null && v.votes_cast >= v.votes_needed);
    if (allIn) {
      this.minimised = false;
      this._closeModal();
      this.renderBanner(v);
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
      // Show vote buttons for the current pending local player.
      // No addEventListener here -- mount()'s delegated listener handles taps.
      if (btnsEl) {
        btnsEl.innerHTML =
          `<button class="btn green wide" data-ins-vote="true"  data-bj-player="${escapeHtml(v.bj_player)}" data-hand-idx="${v.hand_idx}" data-voter="${escapeHtml(activeVoter)}">INSURE</button>` +
          `<button class="btn red wide"   data-ins-vote="false" data-bj-player="${escapeHtml(v.bj_player)}" data-hand-idx="${v.hand_idx}" data-voter="${escapeHtml(activeVoter)}">DECLINE</button>`;
      }

      // Show remaining voters as chips
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

  _closeModal() {
    closeModal("insurance-modal-overlay", { useClass: true });
    this.modalKey = null;
  }

  renderBanner(v, minimisedActiveVote = false, activeVoter = null) {
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

      // No addEventListener here -- mount()'s delegated listener handles taps.
      const btnsHtml = canVote
        ? `<span class="ins-banner-btns">
             <button style="background:var(--green);color:#000" data-ins-vote="true"  data-bj-player="${escapeHtml(v.bj_player)}" data-hand-idx="${v.hand_idx}" data-voter="${escapeHtml(activeVoter)}">INSURE</button>
             <button style="background:var(--red);color:#fff"   data-ins-vote="false" data-bj-player="${escapeHtml(v.bj_player)}" data-hand-idx="${v.hand_idx}" data-voter="${escapeHtml(activeVoter)}">DECLINE</button>
           </span>`
        : `<span style="font-size:11px;color:var(--muted)">${v.votes_cast ?? 0}/${v.votes_needed ?? "?"} voted</span>`;

      content.innerHTML =
        `<span class="ins-banner-label">🃏 Insurance${voterStr}</span>` +
        `<span class="ins-banner-timer" style="color:${timerColor}">⏱ ${s}s</span>` +
        btnsHtml +
        `<span class="ins-banner-expand">expand</span>`;

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

  renderBannerOutcome(results) {
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

  _expand() {
    this.minimised = false;
    openModal("insurance-modal-overlay", { useClass: true });
    const banner = document.getElementById("insurance-vote-banner");
    if (banner) { banner.classList.remove("minimised"); banner.style.display = "none"; }
  }
}

const insurancePanel = new InsurancePanel();

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
    _requestDone();
  }
}


// ── Milestone panel component (Improvements.md item 7, Option A:
// class-based, no framework) — 50-sip handout feature ──────────────────
// Coordinates four surfaces: the announcement toast, the non-winners'
// waiting banner, the winner's handout modal (+/- steppers), and
// recipients' drink-acknowledgement modal. mount() attaches one delegated
// listener for the steppers (replacing addEventListener calls re-attached
// on every rebuild) and one for the ack button (replacing a cloneNode
// trick used only to strip a previous listener before attaching a new
// one -- the same problem mount() solves formally). render(state) is the
// per-poll entry point, replacing the old renderMilestoneState() function.
// milestoneAdjust/submitMilestoneHandout stay top-level functions (not
// methods) since the modal's submit button is wired via the static
// data-action="submitMilestoneHandout" dispatch in the template, which
// only resolves plain window-level names.
class MilestonePanel {
  mount(modalEl, ackOverlayEl) {
    if (this.modalEl) return;   // idempotent -- buildGameUI() may run more than once
    this.modalEl     = modalEl;
    this.ackOverlayEl = ackOverlayEl;

    modalEl.addEventListener("click", e => {
      const btn = e.target.closest("[data-ms-adjust]");
      if (btn) milestoneAdjust(btn.dataset.msPlayer, Number(btn.dataset.msAdjust));
    });

    ackOverlayEl.addEventListener("click", e => {
      if (e.target.closest("#ms-ack-btn")) ackOverlayEl.classList.remove("open");
    });
  }

  render(state) {
    const ms     = state && state.pending_milestone;
    const result = state && state.last_milestone_result;

    // ── Drink notification for recipients (fires once per result) ──────
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
            this.showDrinkAck(sipCount, result.winner);
          }
        }
      }
    }

    // ── Pending milestone handling ──────────────────────────────────────
    if (!ms) {
      this.hideToast();
      this.hideWaitingBanner();
      // Close modal if the TTL expired server-side while modal was open
      if (DrinkUI.lastMilestoneKey && document.getElementById("milestone-modal-overlay").classList.contains("open")) {
        this.closeModal();
      }
      return;
    }

    const key       = `${ms.boundary}:${ms.winner}`;
    const iAmWinner = !!ms.i_am_winner;  // server-authoritative; no JS name-matching needed

    // Show announcement toast exactly once per new milestone (all players)
    if (key !== DrinkUI.lastMilestoneKey) {
      DrinkUI.lastMilestoneKey     = key;
      DrinkUI.milestoneAllocations = {};
      this.showToast(ms);
    }

    if (iAmWinner) {
      this.hideWaitingBanner();
      // Open the handout modal exactly once for this milestone
      if (DrinkUI.milestoneModalOpened !== key) {
        DrinkUI.milestoneModalOpened = key;
        // Short delay so the toast is visible before modal covers it
        setTimeout(() => this.openModal(ms, state), 600);
      } else {
        // Modal already open — keep timer in sync; auto-submit when time's up
        this.updateTimer(ms.seconds_left);
        if (ms.seconds_left <= 0) {
          const overlay = document.getElementById("milestone-modal-overlay");
          if (overlay && overlay.classList.contains("open")) {
            submitMilestoneHandout();
          }
        }
      }
    } else {
      // Non-winners: persistent waiting banner with live countdown
      this.showWaitingBanner(ms);
    }
  }

  showToast(ms) {
    const html = `🎉 ${escapeHtml(ms.winner)} hit ${ms.boundary} sips!`;
    const _show = () => {
      const toast = document.getElementById("milestone-toast");
      if (!toast) return;
      toast.innerHTML = html;
      toast.classList.remove("show");
      void toast.offsetWidth;
      toast.classList.add("show");
      setTimeout(() => this.hideToast(), 5000);
    };
    if (typeof _bustVoteOpen === "function" && _bustVoteOpen()) {
      ToastUI.queue.push(_show);
    } else {
      _show();
    }
  }

  hideToast() {
    const toast = document.getElementById("milestone-toast");
    if (toast) toast.classList.remove("show");
  }

  showWaitingBanner(ms) {
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

  hideWaitingBanner() {
    const slot = document.getElementById("ms-waiting-slot");
    if (slot) slot.style.display = "none";
    const fixed = document.getElementById("ms-waiting-banner");
    if (fixed) fixed.classList.remove("show");
  }

  showDrinkAck(sips, winner) {
    // Open the acknowledgement modal instead of a dismissable toast.
    // No cloneNode-to-strip-old-listener trick needed -- mount()'s
    // delegated listener on ackOverlayEl handles every open of this modal.
    const overlay = document.getElementById("ms-ack-overlay");
    if (!overlay) return;
    const sipWord = sips === 1 ? "sip" : "sips";
    const title   = document.getElementById("ms-ack-title");
    const sub     = document.getElementById("ms-ack-sub");
    if (title) title.textContent = `Drink ${sips} ${sipWord}!`;
    if (sub)   sub.textContent   = `${escapeHtml(winner)} reached a milestone and handed you ${sips} ${sipWord}.`;
    overlay.classList.add("open");
  }

  openModal(ms, state) {
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

    this.renderSteppers(players, ms.handout);
    this.updateTimer(ms.seconds_left);
    openModal("milestone-modal-overlay", { useClass: true });
  }

  closeModal() {
    closeModal("milestone-modal-overlay", { useClass: true });
  }

  renderSteppers(players, total) {
    const container = document.getElementById("milestone-steppers");
    if (!container) return;
    // No addEventListener here -- mount()'s delegated listener handles taps.
    container.innerHTML = players.map(name => {
      const val = DrinkUI.milestoneAllocations[name] || 0;
      return `<div class="ms-stepper">
        <span class="ms-name">${escapeHtml(name)}</span>
        <button data-ms-player="${escapeHtml(name)}" data-ms-adjust="-1">−</button>
        <span class="ms-count" data-ms-player="${escapeHtml(name)}">${val}</span>
        <button data-ms-player="${escapeHtml(name)}" data-ms-adjust="1">+</button>
      </div>`;
    }).join("");
    this.updateRemaining(total);
  }

  updateRemaining(total) {
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

  updateTimer(secondsLeft) {
    const timerEl = document.getElementById("milestone-timer");
    if (!timerEl) return;
    if (secondsLeft == null) return;
    const s = Math.max(0, secondsLeft);
    timerEl.textContent = s > 0 ? `⏱ ${s}s remaining` : "⏱ Time's up!";
    timerEl.style.color = s <= 10 ? "var(--red)" : "var(--muted)";
  }
}

const milestonePanel = new MilestonePanel();

// Note: the stepper's data-ms-player attribute is shared by both the +/-
// buttons (read by mount()'s delegated listener) and the count <span>
// (looked up below to update the displayed value) -- querySelector on a
// dataset value can match either, so this scopes to the span specifically
// via its element type below.
function milestoneAdjust(name, delta) {
  const ms = lastState && lastState.pending_milestone;
  const total = ms ? ms.handout : 5;
  const cur   = DrinkUI.milestoneAllocations[name] || 0;
  const used  = Object.values(DrinkUI.milestoneAllocations).reduce((a, b) => a + b, 0);

  if (delta > 0 && used >= total) return;  // budget exhausted

  DrinkUI.milestoneAllocations[name] = Math.max(0, cur + delta);
  const el = document.querySelector(`span.ms-count[data-ms-player="${CSS.escape(name)}"]`);
  if (el) el.textContent = DrinkUI.milestoneAllocations[name];
  milestonePanel.updateRemaining(total);
}

async function submitMilestoneHandout() {
  const ms = lastState && lastState.pending_milestone;
  if (!ms) return;

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
      milestonePanel.closeModal();
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


// ── Targeted Drinking Mode panel component (Rules.md §5.10,
// Improvements.md item 7 Option A: class-based, no framework) ─────────────
// A standalone mini-game played between normal rounds -- an isolated
// dealer-only hand (never the round's real dealer hand) is dealt once the
// vote window closes, and revealed card-by-card the same way Dealer
// Lottery's redeal is. Vote, reveal, and the end-of-subgame recap are ONE
// continuous modal/card (no separate overlay ever closes and reopens) --
// #td-vote-phase / #td-reveal-phase / #td-summary-phase are three inner
// sections of the same #targeted-drinking-modal-overlay, toggled by
// show/hide. While the subgame is active but between mini-rounds (the
// short back-to-back reveal-pause breather), the modal stays open too,
// showing a lightweight "waiting" message inside #td-vote-phase, instead
// of closing and popping back open moments later -- that close/reopen
// flicker was the whole complaint this version fixes. The vote UI turns
// into the dealt hand the instant the last relevant vote is cast (the
// backend already resolves the mini-round immediately once every target
// has voted -- see submit_targeted_drinking_vote -- so there is no timer
// wait once that happens). Targeted players (who still need to vote) get
// BUST/STAND buttons; everyone else (spectators, the host, and targets
// who've already voted) get a read-only live view of every target's name
// and vote as it's cast. A top-corner ✕ lets the admin end the whole
// subgame on the spot (no trip through Settings, with a confirm() guard
// since it discards everyone's progress), or lets anyone else dismiss
// their own view of the current mini-round without affecting the game.
// The modal only fully closes once the subgame has ended AND its recap
// has been acknowledged (via the Continue/Close button, or its
// auto-continue fallback).
class TargetedDrinkingPanel {
  constructor() {
    this.modalOpen  = false;
    this.phase      = null;   // "vote" | "reveal" | "waiting" | "summary" | null
    this._dismissed = false;  // non-admin tapped ✕ -- hide until the next pending window opens
    this._hadPending = false; // edge-detects a fresh pending window opening, to clear _dismissed
    this._revealTimer = null;
    this._revealKey    = null; // result_seq currently shown, so re-renders don't restart the deal
    this._queuedSummary = null; // an ended-subgame recap waiting to be shown once reveal/vote clears
  }

  mount(el, bannerEl) {
    if (this.el) return;   // idempotent -- buildDigitalUI() may run more than once
    this.el = el;

    el.addEventListener("click", e => {
      if (e.target.closest("#td-close-btn")) { this._onCloseClick(); return; }
      if (e.target.closest("[data-td-continue]")) { this._onContinueClick(); return; }
      const btn = e.target.closest("[data-td-vote]");
      if (!btn) return;
      const npcSet     = new Set([...(npcPlayers || [])]);
      const locals     = myNames.filter(n => !npcSet.has(n));
      const multiLocal = locals.length > 1;
      submitTargetedDrinkingVote(btn.dataset.tdVote, multiLocal ? btn.dataset.tdName : undefined);
    });

    // Host can end the whole subgame from the idle status banner too --
    // not just the mini-round modal -- so "cancel without going via
    // Settings" holds even before the first mini-round has opened.
    if (bannerEl) {
      bannerEl.addEventListener("click", e => {
        if (e.target.closest("[data-td-cancel]")) cancelTargetedDrinking({ reopenSettings: false });
      });
    }
  }

  // Admin: end the whole subgame immediately (cancelTargetedDrinking itself
  // confirms first), same effect as the Settings → Players "Cancel Targeted
  // Drinking" button, just reachable straight from the mini-game itself.
  // Anyone else: just stop showing this mini-round's modal to me locally --
  // doesn't submit a vote or touch server state, so an unvoted target still
  // defaults to STAND at the timer exactly as if they'd ignored the app.
  _onCloseClick() {
    if (myRole === ROLE.ADMIN) {
      cancelTargetedDrinking({ reopenSettings: false });
      return;
    }
    this._dismissed = true;
    this._queuedSummary = null;
    if (this._revealTimer) { clearTimeout(this._revealTimer); this._revealTimer = null; }
    this.phase = null;
    this.close();
  }

  // Reveal/summary don't auto-close -- tapping Continue (or its auto-fire
  // fallback) hands control back to render(), which re-derives whatever
  // should show next (a queued end-of-subgame recap, the "waiting for next
  // mini-round" filler, or a full close) from the latest state, so there's
  // never a moment where the modal closes only to immediately reopen.
  _onContinueClick() {
    if (this._revealTimer) { clearTimeout(this._revealTimer); this._revealTimer = null; }
    this.phase = null;
    if (typeof lastState !== "undefined" && lastState) this.render(lastState);
  }

  open() {
    if (this.modalOpen) return;
    const overlay = openModal("targeted-drinking-modal-overlay");
    if (!overlay) return;
    this.modalOpen = true;
  }

  close() {
    if (!this.modalOpen) return;
    this.modalOpen = false;
    closeModal("targeted-drinking-modal-overlay");
  }

  render(state) {
    const td         = (state && state.targeted_drinking) || {};
    const pending     = td.pending;
    const banner      = document.getElementById("td-status-banner");
    const resultSeq   = td.result_seq || 0;
    const summarySeq  = td.summary_seq || 0;

    // Queue an ending recap -- may arrive alongside a fresh mini-round
    // result (the last target graduated on this very resolve) or entirely
    // on its own (the admin cancelled outside of any mini-round). Shown
    // after any reveal currently in front of it, never skipped.
    if (summarySeq > DrinkUI.lastTargetedDrinkingSummarySeq) {
      DrinkUI.lastTargetedDrinkingSummarySeq = summarySeq;
      if (td.last_summary) this._queuedSummary = td.last_summary;
    }

    // A freshly resolved mini-round result just landed -- this is the
    // "vote modal immediately turns into the dealt hand" transition: same
    // overlay stays open, only the inner section swaps, no close/reopen.
    if (resultSeq > DrinkUI.lastTargetedDrinkingResultSeq) {
      DrinkUI.lastTargetedDrinkingResultSeq = resultSeq;
      if (td.last_result) {
        this._dismissed = false;
        this._enterRevealPhase(td.last_result, resultSeq);
      }
    }

    if (this.phase === "reveal" || this.phase === "summary") {
      if (banner) banner.style.display = "none";
      return;   // owns the modal until Continue, its auto-fire fallback, or the ✕
    }

    // A recap is waiting and nothing currently in front of it -- show it
    // before anything else (including closing).
    if (this._queuedSummary) {
      const summary = this._queuedSummary;
      this._queuedSummary = null;
      this._enterSummaryPhase(summary);
      if (banner) banner.style.display = "none";
      return;
    }

    if (!td.active) {
      // Subgame not running and nothing left queued to show -- fully closed.
      this.phase = null;
      this.close();
      if (banner) banner.style.display = "none";
      return;
    }

    // Edge-triggered: only clear a local dismissal when a genuinely NEW
    // vote window opens, not on every tick where pending happens to be
    // null (that would immediately un-dismiss the "waiting" filler state
    // between mini-rounds, defeating the ✕).
    const pendingIsOpen = !!pending;
    if (pendingIsOpen && !this._hadPending) this._dismissed = false;
    this._hadPending = pendingIsOpen;

    const npcSet    = new Set([...(npcPlayers || [])]);
    const locals    = myNames.filter(n => !npcSet.has(n));
    const targetsLc = (td.targets || []).map(n => n.toLowerCase());
    const myTargets = locals.filter(n => targetsLc.includes(n.toLowerCase()));
    const votesCast = (pending && pending.votes_cast) || {};
    const amTargeted = myTargets.length > 0;
    const allVoted    = amTargeted && myTargets.every(n => votesCast[n]);

    // A mini-round can only ever be open once the current normal round has
    // ended (check_targeted_drinking_trigger only arms at round-end), so
    // gate the blocking modal on that too -- before the very first
    // mini-round opens (subgame just started, current round still being
    // played out live), show the small non-blocking banner instead, same
    // as Dealer Lottery/Milestone never popping a modal over live play.
    const isRoundOver = state && state.phase === PHASE.ROUND_OVER;

    if (pending && !this._dismissed && myRole !== null && !_dealAnimating) {
      this.phase = "vote";
      if (banner) banner.style.display = "none";
      this.open();
      this._showPhase("vote");

      const subEl = document.getElementById("td-modal-sub");
      if (amTargeted && !allVoted) {
        if (subEl) subEl.textContent = "Call it — will the dealer's hand bust?";
        this._renderTargetVoteView(pending, myTargets);
      } else {
        if (subEl) subEl.textContent = "Watching the call — will the dealer's hand bust?";
        this._renderSpectatorVoteView(pending, td);
      }

      const bar      = document.getElementById("td-timer-bar");
      const label    = document.getElementById("td-timer-label");
      const duration = 15;
      const secs     = pending.seconds_left || 0;
      const display  = Math.min(secs, duration);
      if (bar)   bar.style.width   = `${(display / duration) * 100}%`;
      if (label) label.textContent = secs > 0 ? `${secs}s` : "Time up!";
    } else if (isRoundOver && !this._dismissed) {
      // Between mini-rounds (subgame still active, current round already
      // over) -- keep the SAME modal open with a lightweight waiting
      // state instead of closing it, so there's no flicker before the
      // next mini-round's vote phase takes over.
      this.phase = "waiting";
      this.open();
      this._showPhase("vote");
      const subEl = document.getElementById("td-modal-sub");
      const wrap  = document.getElementById("td-players-wrap");
      const bar   = document.getElementById("td-timer-bar");
      const label = document.getElementById("td-timer-label");
      if (subEl) subEl.textContent = amTargeted
        ? "You're targeted — the next mini-round starts shortly…"
        : "Waiting for the next mini-round…";
      if (wrap) wrap.innerHTML = (td.targets || []).map(n =>
        `<div class="td-spectator-row"><span class="dl-name-lbl">${escapeHtml(n)}</span></div>`).join("");
      if (bar)   bar.style.width = "0%";
      if (label) label.textContent = "";
      if (banner) banner.style.display = "none";
    } else {
      // Dismissed locally, or the subgame just started and the current
      // normal round is still being played out live -- no blocking modal,
      // just the compact status banner.
      this.phase = null;
      this.close();
      if (banner) {
        const cancelBtn = myRole === ROLE.ADMIN
          ? `<button class="td-banner-cancel" data-td-cancel title="End targeting">✕</button>`
          : "";
        if (myTargets.length) {
          banner.innerHTML = `🎯 You're targeted — next mini-round starts between rounds${cancelBtn}`;
        } else {
          const names = escapeHtml((td.targets || []).join(", "));
          banner.innerHTML = `🎯 Targeting <strong>${names}</strong>${cancelBtn}`;
        }
        banner.style.display = "block";
      }
    }
  }

  _showPhase(phase) {
    const voteEl    = document.getElementById("td-vote-phase");
    const revealEl  = document.getElementById("td-reveal-phase");
    const summaryEl = document.getElementById("td-summary-phase");
    // "waiting" reuses the vote-phase container's shell (see render()).
    if (voteEl)    voteEl.style.display    = (phase === "vote" || phase === "waiting") ? "" : "none";
    if (revealEl)  revealEl.style.display  = phase === "reveal"  ? "" : "none";
    if (summaryEl) summaryEl.style.display = phase === "summary" ? "" : "none";
  }

  // Targeted-player view: BUST/STAND buttons per locally-controlled
  // targeted seat still awaiting a vote.
  _renderTargetVoteView(pending, myTargets) {
    const wrap = document.getElementById("td-players-wrap");
    if (!wrap) return;

    const votesCast  = pending.votes_cast || {};
    const streaks    = (lastState && lastState.targeted_drinking && lastState.targeted_drinking.streaks) || {};
    const multiLocal = myTargets.length > 1;

    // No addEventListener here -- mount()'s delegated listener handles clicks.
    wrap.innerHTML = myTargets.map(name => {
      const nameLbl   = multiLocal ? `<span class="dl-name-lbl">${escapeHtml(name)}</span>` : "";
      const streak    = streaks[name] || 0;
      const streakLbl = `<span class="td-streak">${streak}/3 correct</span>`;
      const myVote    = votesCast[name];

      if (myVote) {
        const label = myVote === "bust" ? "BUST" : "STAND";
        return `<div class="dl-entry-card">
          <div class="dl-entry-top">${nameLbl}${streakLbl}</div>
          <div class="dl-status">Voted: ${label}</div>
        </div>`;
      }

      return `<div class="dl-entry-card">
        <div class="dl-entry-top">${nameLbl}${streakLbl}</div>
        <div class="td-vote-row">
          <button class="btn red wide td-vote-btn"   data-td-vote="bust"  data-td-name="${escapeHtml(name)}">BUST</button>
          <button class="btn green wide td-vote-btn" data-td-vote="stand" data-td-name="${escapeHtml(name)}">STAND</button>
        </div>
      </div>`;
    }).join("");
  }

  // Spectator/host (and already-voted targets) view: read-only, shows
  // every target's name and vote decision live as it's cast -- not just
  // this client's own local seats.
  _renderSpectatorVoteView(pending, td) {
    const wrap = document.getElementById("td-players-wrap");
    if (!wrap) return;

    const votesCast = pending.votes_cast || {};
    const targets   = td.targets || [];

    wrap.innerHTML = targets.map(name => {
      const vote     = votesCast[name];
      const voteHtml = vote
        ? `<span class="td-spectator-vote">${vote.toUpperCase()}</span>`
        : `<span class="td-spectator-vote pending">…deciding</span>`;
      return `<div class="td-spectator-row"><span class="dl-name-lbl">${escapeHtml(name)}</span>${voteHtml}</div>`;
    }).join("");
  }

  // Visual reveal: the isolated dealer-only hand dealt and played out --
  // shown as real card visuals (reuses handBlock()/cardEl() from
  // table-render.js, same as Dealer Lottery's own reveal), 2 initial cards
  // then each hit fading/sliding in one at a time, ending with a BUST/STAND
  // tag, then the per-target payout list. The subtitle names every target
  // and their vote up front (color-coded green/red the moment we know --
  // the outcome was already decided server-side before any card animates)
  // and keeps showing it through the whole animation, so spectators see
  // who called what, and whether they nailed it, as the cards land.
  async _enterRevealPhase(result, resultSeq) {
    if (!result || !result.hand) return;
    this.phase     = "reveal";
    this._revealKey = resultSeq;

    const handWrap    = document.getElementById("targeted-drinking-reveal-hand");
    const payout      = document.getElementById("targeted-drinking-reveal-payout");
    const sub         = document.getElementById("targeted-drinking-reveal-sub");
    const continueBtn = document.getElementById("td-continue-btn");
    if (!handWrap) return;

    const votes   = result.votes   || {};
    const correct = result.correct || {};
    const names   = Object.keys(votes);
    const callLine = names.length
      ? names.map(n => {
          const color = correct[n] ? "var(--green)" : "var(--red)";
          return `<strong>${escapeHtml(n)}</strong> called ` +
                 `<strong style="color:${color}">${(votes[n] || "?").toUpperCase()}</strong>`;
        }).join(" · ")
      : "The dealer plays out a fresh hand:";
    if (sub) sub.innerHTML = callLine;
    if (payout) payout.innerHTML = "";
    if (continueBtn) continueBtn.disabled = true;

    handWrap.innerHTML = "";
    this.open();
    this._showPhase("reveal");

    const delay = ms => new Promise(r => setTimeout(r, ms));
    const cards = result.hand.cards || [];

    const block = handBlock({ cards: cards.slice(0, 2), score: null }, "Dealer");
    handWrap.appendChild(block);
    await delay(300);

    const row = block.querySelector(".cards-row");
    for (let i = 2; i < cards.length; i++) {
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
    // If the user (or the admin ✕) tore down the reveal mid-animation, don't
    // clobber whatever's rendered now with a stale result.
    if (this._revealKey !== resultSeq) return;

    const meta = block.querySelector(".hand-meta");
    if (meta) meta.innerHTML = `<span class="score">${result.hand.score}</span>` +
      (result.hand.bust ? `<span class="bust">BUST</span>` : `<span class="stood">STAND</span>`);
    await delay(300);
    if (this._revealKey !== resultSeq) return;

    if (payout) {
      payout.innerHTML = names.length
        ? `<ul class="dl-reveal-list">${names.map(n => _tdRevealLine(n, result)).join("")}</ul>`
        : `<div class="dl-reveal-headline">No one was targeted this mini-round.</div>`;
    }
    if (continueBtn) continueBtn.disabled = false;

    // Auto-continue if nobody taps the button -- mini-rounds can chain
    // back-to-back, so an AFK/slow player must not permanently block their
    // own next vote prompt behind a reveal they never dismissed.
    if (this._revealTimer) clearTimeout(this._revealTimer);
    this._revealTimer = setTimeout(() => this._onContinueClick(), 8000);
  }

  // End-of-subgame recap: reason it ended + how many sips each original
  // target drank in total across every mini-round of the run (survives
  // graduation -- a target who's already been released still shows up
  // with their final tally).
  _enterSummaryPhase(summary) {
    this.phase = "summary";

    const sub  = document.getElementById("td-summary-sub");
    const list = document.getElementById("td-summary-list");
    const totals = (summary && summary.totals) || {};
    const names  = Object.keys(totals);

    if (sub) sub.textContent = summary && summary.reason === "all_graduated"
      ? "Everyone called it enough times in a row to be released! 🎓"
      : "The host ended it early.";

    if (list) {
      list.innerHTML = names.length
        ? `<ul class="dl-reveal-list">${names.map(n => {
            const sips = totals[n] || 0;
            return `<li><span class="dl-reveal-name">${escapeHtml(n)}</span> drank ` +
                   `<strong>${sips}</strong> sip${sips === 1 ? "" : "s"} total</li>`;
          }).join("")}</ul>`
        : `<div class="dl-reveal-headline">Nobody had to drink at all!</div>`;
    }

    this.open();
    this._showPhase("summary");

    if (this._revealTimer) clearTimeout(this._revealTimer);
    this._revealTimer = setTimeout(() => this._onContinueClick(), 10000);
  }
}

const targetedDrinkingPanel = new TargetedDrinkingPanel();

async function submitTargetedDrinkingVote(vote, playerName) {
  const body = { room_code: roomCode, client_id: clientId, vote };
  if (playerName) body.player_name = playerName;
  _requestsInFlight++;
  try {
    const res  = await fetch("/targeted_drinking/vote", {
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

// Builds one target's outcome line for the reveal modal's payout list --
// the vote word is color-coded green/red (correct/wrong), not the flat
// purple every other Dealer-Lottery-style payout line uses.
function _tdRevealLine(name, result) {
  const vote      = (result.votes || {})[name] || "?";
  const isCorrect = (result.correct || {})[name];
  const graduated = (result.graduated || []).includes(name);
  const sips      = (result.sips || {})[name];
  const streak    = (result.streaks || {})[name] || 0;
  const color     = isCorrect ? "var(--green)" : "var(--red)";

  let text;
  if (graduated) {
    text = `correct! 🎓 Graduated!`;
  } else if (isCorrect) {
    text = `correct (streak: ${streak}/3)`;
  } else {
    text = `wrong, drinks ${sips} sip${sips === 1 ? "" : "s"}`;
  }
  return `<li><span class="dl-reveal-name">${escapeHtml(name)}</span> called ` +
         `<strong style="color:${color}">${vote.toUpperCase()}</strong> — ${text}</li>`;
}

