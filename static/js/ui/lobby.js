// AGE GATE
// ============================================================
function confirmAge() {
  try { sessionStorage.setItem("bjAgeOk", "1"); } catch(_) {}
  document.getElementById("age-gate").style.display = "none";
}

function declineAge() {
  document.getElementById("age-gate-msg").textContent =
    "Sorry — this game is for adults (18+) only.";
}

// ============================================================
// LOBBY
// ============================================================
function showLobbyMsg(text, type = "error") {
  const el = document.getElementById("lobby-msg");
  el.textContent  = text;
  el.className    = type;
  el.style.display = "block";
}
function hideLobbyMsg() {
  document.getElementById("lobby-msg").style.display = "none";
}

async function createRoom() {
  hideLobbyMsg();
  let data;
  try {
    const res  = await fetch("/create_room", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    data = await res.json();
  } catch (_) {
    showLobbyMsg("Could not reach server — check your connection.");
    return;
  }
  if (!data.ok) { showLobbyMsg("Could not create room. Try again."); return; }
  roomCode = data.code;
  lsSet("bjRoomCode", roomCode);
  // Show setup screen with code badge
  document.getElementById("lobby").style.display    = "none";
  document.getElementById("setup").style.display    = "flex";
  document.getElementById("setup-room-code").textContent = roomCode;
}

async function joinRoom() {
  hideLobbyMsg();
  const input = document.getElementById("join-code");
  // Normalise: preserve original capitalisation from the server (Title-case word)
  // We'll just send whatever the user typed and let the server normalise
  const raw   = (input.value || "").trim();
  if (!raw) { showLobbyMsg("Enter a room code first."); return; }

  let data;
  try {
    const res  = await fetch("/join_room", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: raw, client_id: clientId }) });
    data = await res.json();
  } catch (_) {
    showLobbyMsg("Could not reach server — check your connection.");
    return;
  }
  if (!data.ok) { showLobbyMsg(data.error || "Room not found."); return; }

  roomCode = data.room_code || raw;   // use canonical casing from server
  lsSet("bjRoomCode", roomCode);

  if (data.has_game) {
    // Game already in progress — jump straight to the game screen
    players  = data.players || [];
    numHands = data.num_hands || 2;
    gameMode = data.mode || "referee";
    myRole           = data.my_role   || null;
    myName           = data.my_name   || null;
    myNames          = data.my_names  || (myName ? [myName] : []);
    isMyDealerClient = data.is_dealer_client || false;
    updateHeader(data);
    buildGameUI();
    applyState(data);
    appendLog("  (Joined room " + roomCode + ")\n");
    document.getElementById("lobby").style.display = "none";
    document.getElementById("app").style.display   = "flex";
    startPolling();
    startIdleWatcher();
  } else {
    // Game not started yet — show waiting screen
    document.getElementById("lobby").style.display          = "none";
    document.getElementById("waiting-code-badge").textContent = roomCode;
    document.getElementById("waiting").style.display         = "flex";
    renderWaitingPlayers(data.waiting_count || 1);
    startWaiting();
  }
}

async function cancelSetup() {
  // Delete the created room and return to the lobby
  if (roomCode) {
    try {
      await fetch("/delete_room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_code: roomCode, client_id: clientId }),
      });
    } catch (_) {}
  }
  roomCode = "";
  lsRemove("bjRoomCode");
  document.getElementById("setup").style.display = "none";
  document.getElementById("lobby").style.display = "flex";
}

function backToLobby() {
  stopPolling();
  if (roomCode) {
    const blob = new Blob([JSON.stringify({ room_code: roomCode, client_id: clientId })], { type: "application/json" });
    navigator.sendBeacon("/leave_room", blob);
  }
  roomCode = "";
  lsRemove("bjRoomCode");
  document.getElementById("waiting").style.display = "none";
  document.getElementById("lobby").style.display   = "flex";
  document.getElementById("join-code").value = "";
  _lastWaitingCount = 0;
  document.getElementById("waiting-player-list").innerHTML = "";
  document.getElementById("waiting-player-count").textContent = "1 / ?";
}

// ============================================================
// POLLING — keep all players in sync
// ============================================================

// Fast interval during active play so end-of-round appears promptly for all clients.
// Slow interval during pre-deal and round-over where nothing is time-sensitive.
const POLL_INTERVAL_FAST =  800;   // ms — used while phase is "playing" or "dealer-ready"
const POLL_INTERVAL_SLOW = 2000;   // ms — used during "pre-deal", "round-over", or unknown

function _pollInterval() {
  const phase = lastState && lastState.phase;
  return (phase === PHASE.PLAYING || phase === PHASE.DEALER_READY)
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
        '<div class="server-disconnect-note">The server may be waking up — this can take up to 30 sec.</div>' +
        '<div class="server-disconnect-elapsed" id="server-disconnect-elapsed"></div>' +
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

// =====================================