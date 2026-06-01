// INIT — generate clientId, then reconnect to existing server session on page reload
// ============================================================
(async () => {
  // Hide age gate if already confirmed this session
  try {
    if (sessionStorage.getItem('bjAgeOk') === '1') {
      document.getElementById("age-gate").style.display = "none";
    }
  } catch(_) {
    // sessionStorage blocked (e.g. private browsing) — skip gate
    document.getElementById("age-gate").style.display = "none";
  }

  // Restore deal-animation toggle from localStorage (default: on)
  setAnimToggle(lsGet("bjDealAnim") !== "0");

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
      isMyDealerClient = data.is_dealer_client || false;
      updateHeader(data);
      buildGameUI();
      appendLog("  (Reconnected to room " + roomCode + ")\n");
      applyState(data);
      document.getElementById("lobby").style.display = "none";
      document.getElementById("app").style.display   = "flex";
      startPolling();
    }
  } catch (_) {}
})();
