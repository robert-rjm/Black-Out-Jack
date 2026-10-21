// ============================================================
// POLLING — keep all players in sync
// ============================================================
// The /state poll loop and the connection-lost screens. Shared by every
// screen; split out of lobby.js. The counters it uses (pollTimer,
// _consecutiveFailures, _disconnectedSince, _disconnectedTimer) live in state.js.

// Fast interval during active play so end-of-round appears promptly for all clients.
// Slow interval during pre-deal and round-over where nothing is time-sensitive.
const POLL_INTERVAL_FAST =  800;   // ms — used while phase is "playing" or "dealer-ready"
const POLL_INTERVAL_SLOW = 2000;   // ms — used during "pre-deal", "round-over", or unknown

function _pollInterval() {
  const phase = lastState && lastState.phase;
  return (phase === PHASE.PLAYING || phase === PHASE.DEALER_READY
          || (lastState && lastState.stake_window_open))
    ? POLL_INTERVAL_FAST
    : POLL_INTERVAL_SLOW;
}

// Fetch a single /state snapshot and pass the parsed response to onResult if ok.
// Tracks consecutive failures to show/hide the server-disconnected overlay.
async function fetchState(onResult) {
  try {
    const url  = `/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
    const res  = await fetch(url);
    const data = await res.json();
    if (data.ok) {
      _consecutiveFailures = 0;
      hideDisconnected();
      onResult(data);
    } else {
      _onPollFailure();
    }
  } catch (_) {
    _onPollFailure();
  }
}

function _onPollFailure() {
  _consecutiveFailures++;
  if (_consecutiveFailures >= 3) showDisconnected();
}

// ---------------------------------------------------------------------------
// Server-disconnected overlay
// ---------------------------------------------------------------------------

function showDisconnected() {
  let overlay = document.getElementById("server-disconnect-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "server-disconnect-overlay";
    overlay.className = "server-disconnect-overlay";
    overlay.innerHTML =
      '<div class="server-disconnect-card">' +
        '<div class="server-disconnect-spinner"></div>' +
        '<div class="server-disconnect-title">Server disconnected</div>' +
        '<div class="server-disconnect-msg">Attempting to reconnect…</div>' +
        '<div class="server-disconnect-note">The server may be waking up or is disconnected. Please wait or try again later.</div>' +
        '<div class="server-disconnect-elapsed" id="server-disconnect-elapsed"></div>' +
        '<button class="btn server-disconnect-giveup" data-action="showGiveUpScreen">Give up</button>' +
      '</div>';
    document.body.appendChild(overlay);
  }
  overlay.style.display = "flex";
  if (!_disconnectedSince) {
    _disconnectedSince = Date.now();
    _disconnectedTimer = setInterval(_updateDisconnectElapsed, 1000);
    _updateDisconnectElapsed();
  }
}

function showGiveUpScreen() {
  if (_disconnectedTimer) { clearInterval(_disconnectedTimer); _disconnectedTimer = null; }
  const card = document.querySelector("#server-disconnect-overlay .server-disconnect-card");
  if (!card) return;
  card.innerHTML =
    '<img src="/static/img/logo-transparent.png" alt="Black(Out)Jack Logo" class="server-disconnect-logo">' +
    '<div class="server-disconnect-title" style="font-size:20px">Thanks for playing BlackOutJack!</div>' +
    '<div class="server-disconnect-msg">Come back when the server is ready.</div>' +
    '<button class="btn server-disconnect-tryagain" id="server-disconnect-tryagain-btn" data-action="tryAgainFromGiveUp">Try again</button>';
}

async function tryAgainFromGiveUp() {
  const btn = document.getElementById("server-disconnect-tryagain-btn");
  if (btn) { btn.disabled = true; btn.textContent = "Checking…"; }
  try {
    const url = `/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();
    if (data.ok) {
      hideDisconnected();
      resetToSetup();
      return;
    }
  } catch (_) {}
  // Still unreachable
  if (btn) { btn.disabled = false; btn.textContent = "Try again"; }
  const card = document.querySelector("#server-disconnect-overlay .server-disconnect-card");
  if (!card) return;
  let note = card.querySelector(".tryagain-note");
  if (!note) {
    note = document.createElement("div");
    note.className = "tryagain-note";
    card.appendChild(note);
  }
  note.textContent = "Still unreachable.";
  note.style.opacity = "1";
  clearTimeout(note._hideTimer);
  note._hideTimer = setTimeout(() => { note.style.opacity = "0"; }, 2500);
}

function _updateDisconnectElapsed() {
  const el = document.getElementById("server-disconnect-elapsed");
  if (!el || !_disconnectedSince) return;
  const secs = Math.floor((Date.now() - _disconnectedSince) / 1000);
  el.textContent = secs > 0 ? secs + "s" : "";
}

function hideDisconnected() {
  const overlay = document.getElementById("server-disconnect-overlay");
  if (overlay) overlay.style.display = "none";
  if (_disconnectedTimer) { clearInterval(_disconnectedTimer); _disconnectedTimer = null; }
  _disconnectedSince = null;
}

// Apply a /state response: update UI and header.
function _applyStateResult(data) {
  applyState(data);
  if (data.dealer) updateHeader(data);
}

function startPolling() {
  stopPolling();
  const tick = async () => {
    // Skip the fetch while a game-action request is in flight — the command
    // response will call applyState with fresher (higher state_seq) data.
    if (roomCode && _requestsInFlight === 0) {
      await fetchState(_applyStateResult);
    }
    // Reschedule — interval adapts automatically to the latest phase.
    pollTimer = setTimeout(tick, _pollInterval());
  };
  pollTimer = setTimeout(tick, _pollInterval());
}

function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
}

// Safari throttles timers aggressively when the tab is backgrounded or the
// screen locks. Force an immediate re-poll the moment the user comes back.
// Skip if a request is already in flight — we'll get fresh state from it.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && roomCode && _requestsInFlight === 0) {
    fetchState(_applyStateResult);
  }
});
