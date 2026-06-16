// INIT — toggle label setup + clientId + reconnect
// ============================================================

// Run synchronously on script load (DOM is ready — scripts are at bottom of <body>).
// Must be outside the async IIFE so these run before any await.
setAnimToggle(lsGet("bjDealAnim") !== "0");  // restore animation pref (default ON)
setBustVoteSetupToggle(true);                 // bust-vote toggle starts ON in setup

(async () => {
  // Hide age gate if already confirmed this session
  try {
    if (sessionStorage.getItem('bjAgeOk') === '1') {
      document.getElementById("age-gate").style.display = "none";
    }
  } catch(_) {
    document.getElementById("age-gate").style.display = "none";
  }
  // Attach age gate button handlers
  document.querySelector('[data-action="confirmAge"]').addEventListener('click', () => {
    try { sessionStorage.setItem("bjAgeOk", "1"); } catch(_) {}
    document.getElementById("age-gate").style.display = "none";
  });
  document.querySelector('[data-action="declineAge"]').addEventListener('click', () => {
    document.getElementById('age-gate-card').classList.remove('active');
    document.querySelector('.underage-screen').classList.add('active');
  });

  // Generate or load persistent client UUID
  let savedId = lsGet("bjClientId");
  if (!savedId) {
    savedId = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
    lsSet("bjClientId", savedId);
  }
  clientId = savedId;

  const saved = lsGet("bjRoomCode");
  if (!saved) return;   // no saved room — stay on lobby

  try {
    const url  = `/state?room_code=${encodeURIComponent(saved)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
    const res  = await fetch(url);
    const data = await res.json();
    if (data.ok && data.players && data.players.length > 0) {
      roomCode         = saved;
      players          = data.players;
      numHands         = data.num_hands || 2;
      gameMode         = data.mode || "referee";
      myRole           = data.my_role          || null;
      myName           = data.my_name          || null;
      myNames          = data.my_names         || (myName ? [myName] : []);
      isMyDealerClient = data.is_dealer_client || false;
      updateHeader(data);
      buildGameUI();
      appendLog("  (Reconnected to room " + roomCode + ")\n");
      applyState(data);
      document.getElementById("lobby").style.display = "none";
      document.getElementById("app").style.display   = "flex";
      startPolling();
      startIdleWatcher();
    }
  } catch (_) {
  showLobbyMsg("Connection lost — refresh to reconnect.");
  }
})();
