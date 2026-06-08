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
  const res  = await fetch("/create_room", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const data = await res.json();
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
  const code  = (input.value || "").trim().toUpperCase();
  // Normalise: preserve original capitalisation from the server (Title-case word)
  // We'll just send whatever the user typed and let the server normalise
  const raw   = (input.value || "").trim();
  if (!raw) { showLobbyMsg("Enter a room code first."); return; }

  const res  = await fetch("/join_room", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: raw, client_id: clientId }) });
  const data = await res.json();
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
  } else {
    // Game not started yet — show waiting screen
    document.getElementById("lobby").style.display          = "none";
    document.getElementById("waiting-code-badge").textContent = roomCode;
    document.getElementById("waiting").style.display         = "flex";
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
  return (phase === "playing" || phase === "dealer-ready")
    ? POLL_INTERVAL_FAST
    : POLL_INTERVAL_SLOW;
}

function startPolling() {
  stopPolling();
  const tick = async () => {
    if (roomCode) {
      try {
        const url  = `/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
        const res  = await fetch(url);
        const data = await res.json();
        if (data.ok) { applyState(data); if (data.dealer) updateHeader(data); }
      } catch (_) {}
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
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && roomCode) {
    fetch(`/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`)
      .then(r => r.json())
      .then(data => { if (data.ok) { applyState(data); if (data.dealer) updateHeader(data); } })
      .catch(() => {});
  }
});

// ============================================================
