// ============================================================
// IDLE WATCHER — warns before Render dyno sleep (15-min idle)
// Shown to all seated players (admin + player roles); spectators excluded.
// ============================================================
const IDLE_SOFT_MS   = 10 * 60 * 1000;   // 10 min → "Still there?"
const IDLE_URGENT_MS = 14 * 60 * 1000;   // 14 min → "Room about to be lost"

let _lastActivityAt  = Date.now();
let _idleWatcherID   = null;
let _idleSoundState  = null;  // tracks last sound played: null | "soft" | "urgent"

// --------------- sound ---------------
function _playIdleSound(type) {
  try {
    const ctx  = new (window.AudioContext || window.webkitAudioContext)();
    const beep = (freq, startSec, dur) => {
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, ctx.currentTime + startSec);
      gain.gain.linearRampToValueAtTime(0.25, ctx.currentTime + startSec + 0.01);
      gain.gain.linearRampToValueAtTime(0,    ctx.currentTime + startSec + dur);
      osc.start(ctx.currentTime + startSec);
      osc.stop(ctx.currentTime  + startSec + dur + 0.05);
    };
    if (type === "soft") {
      // Two gentle mid-pitch chimes
      beep(660, 0,    0.18);
      beep(660, 0.28, 0.18);
    } else {
      // Three urgent higher-pitched beeps
      beep(920, 0,    0.14);
      beep(920, 0.20, 0.14);
      beep(920, 0.40, 0.22);
    }
  } catch (_) { /* AudioContext not supported or blocked */ }
}

function resetIdleTimer() {
  _lastActivityAt = Date.now();
  _idleSoundState = null;
  const banner  = document.getElementById("idle-warning-banner");
  const overlay = document.getElementById("idle-urgent-overlay");
  if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
  if (overlay) { overlay.classList.remove("open"); }
  // Ping the server to keep the dyno alive
  fetch("/state?room_code=" + encodeURIComponent(roomCode) + "&client_id=" + encodeURIComponent(clientId))
    .catch(() => {});
}

function _tickIdleWatcher() {
  const elapsed = Date.now() - _lastActivityAt;
  const banner  = document.getElementById("idle-warning-banner");
  const text    = document.getElementById("idle-warning-text");
  const overlay = document.getElementById("idle-urgent-overlay");

  if (elapsed >= IDLE_URGENT_MS) {
    // Urgent: hide banner, show blocking modal + play sound once
    if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
    if (overlay) { overlay.classList.add("open"); }
    if (_idleSoundState !== "urgent") {
      _idleSoundState = "urgent";
      _playIdleSound("urgent");
    }
  } else if (elapsed >= IDLE_SOFT_MS) {
    // Soft: yellow banner + play sound once
    if (overlay) { overlay.classList.remove("open"); }
    if (banner && text) {
      banner.style.display = "flex";
      banner.className = "idle-warning-banner idle-soft";
      text.textContent = "Still there? Tap to keep the room alive.";
    }
    if (_idleSoundState !== "soft" && _idleSoundState !== "urgent") {
      _idleSoundState = "soft";
      _playIdleSound("soft");
    }
  } else {
    if (banner)  { banner.style.display = "none"; banner.className = "idle-warning-banner"; }
    if (overlay) { overlay.classList.remove("open"); }
  }
}

function startIdleWatcher() {
  // Spectators don't keep the dyno alive and don't need the warning
  if (typeof myRole !== "undefined" && myRole === ROLE.SPECTATOR) return;
  _lastActivityAt = Date.now();
  _idleSoundState = null;
  if (_idleWatcherID) clearInterval(_idleWatcherID);
  _idleWatcherID = setInterval(_tickIdleWatcher, 30_000);  // check every 30s
}
