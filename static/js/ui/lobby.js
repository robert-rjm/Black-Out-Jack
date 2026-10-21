// AGE GATE
// ============================================================
let _pendingInviteJoin = false;   // an ?room= invite link is waiting for the age gate

function confirmAge() {
  try { sessionStorage.setItem("bjAgeOk", "1"); } catch(_) {}
  document.getElementById("age-gate").style.display = "none";
  if (_pendingInviteJoin) { _pendingInviteJoin = false; joinRoom(); }
}

// A scanned QR code / shared link opens the app at /?room=CODE.
function _readInviteCode() {
  try {
    const c = (new URLSearchParams(location.search).get("room") || "").trim();
    return /^[A-Za-z0-9]{1,24}$/.test(c) ? c : "";
  } catch (_) { return ""; }
}
function _ageConfirmed() {
  try { return sessionStorage.getItem("bjAgeOk") === "1"; } catch (_) { return true; }
}

function declineAge() {
  document.getElementById("age-gate-card").classList.remove("active");
  document.querySelector(".underage-screen").classList.add("active");
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


async function shuffleRoomCode() {
  // Delete the current reserved room and create a fresh one
  if (roomCode) {
    try {
      await fetch("/delete_room", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ room_code: roomCode, client_id: clientId }),
      });
    } catch (_) {}
  }
  await createRoom();
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
