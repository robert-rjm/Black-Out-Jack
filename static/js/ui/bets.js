// ============================================================
// NORMAL-MODE STAKES
// ============================================================
// Per-player stake panel (the stake window after Deal, cash mode only), the
// bet steppers and the accept-stake / set-bet calls. Split out of admin.js.

// ---------------------------------------------------------------------------
// Per-player stake panel (stake window after Deal, normal/digital mode only)
// ---------------------------------------------------------------------------

function _updateBetPanel(state, isPreDeal) {
  const panel     = document.getElementById("dig-bet-panel");
  const container = document.getElementById("dig-bet-steppers");
  if (!panel || !container) return;

  const isDrinking = state.drinking_mode;
  const isDigital  = state.mode === "digital";

  const tableMap = {};
  (state.table || []).forEach(p => { tableMap[p.name.toLowerCase()] = p; });
  // Bots keep their stake locked, so only human seats get a stepper.
  const mine = myNames.filter(n => {
    const p = tableMap[n.toLowerCase()];
    return p && !p.is_npc;
  });

  // Only while the stake window is open -- never at round-over, so the payout
  // screen stays readable until the next Deal.
  const show = isPreDeal && !!state.stake_window_open && isDigital && !isDrinking && mine.length > 0;
  panel.style.display = show ? "block" : "none";
  if (!show) return;

  const countdown = document.getElementById("dig-bet-countdown");
  if (countdown) countdown.textContent = Math.min(15, state.stake_window_seconds_left || 0);
  const accept = document.getElementById("dig-bet-accept");
  if (accept) {
    const confirmed = (state.stake_confirmed || []).map(n => n.toLowerCase());
    const accepted  = mine.every(n => confirmed.includes(n.toLowerCase()));
    accept.disabled    = accepted;
    accept.textContent = accepted ? "✓ Accepted — waiting for the others" : "✓ Accept stake";
  }

  const defaultBet = state.bet_amount || 5;

  // Only rebuild if seats or bets changed (avoid clobbering in-progress steppers)
  const existing = container.querySelectorAll(".player-bet-stepper");
  const needsRebuild = existing.length !== mine.length ||
    mine.some((n, i) => {
      const el = existing[i];
      return !el || el.dataset.seatName !== n;
    });

  if (!needsRebuild) {
    // Still sync displayed value from server state (another client could have polled)
    mine.forEach(n => {
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
  mine.forEach(name => {
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

async function confirmStake() {
  if (!roomCode || !clientId) return;
  try {
    const res = await fetch("/confirm_stake", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ room_code: roomCode, client_id: clientId }),
    });
    const data = await res.json();
    if (data.ok) applyState(data);
  } catch (_) {}
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
