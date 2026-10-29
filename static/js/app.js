// INIT — toggle label setup + clientId + reconnect
// ============================================================

// Run synchronously on script load (DOM is ready — scripts are at bottom of <body>).
// Must be outside the async IIFE so these run before any await.
_syncAnimToggles(_animToggleOn());           // show the saved pref, or the device default
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
  // Age gate buttons are handled by bootstrap.js event delegation →
  // confirmAge() / declineAge() in lobby.js.

  // Generate or load persistent client UUID
  let savedId = lsGet("bjClientId");
  if (!savedId) {
    savedId = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2) + Date.now().toString(36);
    lsSet("bjClientId", savedId);
  }
  clientId = savedId;

  // An invite link (/?room=CODE, e.g. from a scanned QR code) takes precedence
  // over a remembered room: put the code in the join box and join it. If the
  // age gate is still up, wait until it is confirmed.
  const invite = _readInviteCode();
  if (invite) {
    const input = document.getElementById("join-code");
    if (input) input.value = invite;
    try { history.replaceState(null, "", location.pathname); } catch (_) {}
    if (_ageConfirmed()) joinRoom(); else _pendingInviteJoin = true;
    return;
  }

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
