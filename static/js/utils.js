// ============================================================
// SAFE localStorage HELPERS
// Safari Private Browsing throws SecurityError on any localStorage access.
// All reads/writes go through these wrappers so a blocked storage never crashes the app.
// ============================================================
function lsGet(k)    { try { return localStorage.getItem(k);    } catch(_) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v);        } catch(_) {} }
function lsRemove(k) { try { localStorage.removeItem(k);        } catch(_) {} }

// ============================================================
// MODAL OPEN/CLOSE HELPERS
// Some overlays toggle visibility via inline style.display
// (flex/none), others via a CSS "open" class. Pass
// { useClass: true } for the latter. Returns the overlay
// element (or null) so callers can keep configuring it.
// ============================================================
function openModal(id, { useClass = false } = {}) {
  const overlay = document.getElementById(id);
  if (!overlay) return null;
  if (useClass) overlay.classList.add("open");
  else          overlay.style.display = "flex";
  return overlay;
}
function closeModal(id, { useClass = false } = {}) {
  const overlay = document.getElementById(id);
  if (!overlay) return;
  if (useClass) overlay.classList.remove("open");
  else          overlay.style.display = "none";
}

// ============================================================
// CACHED BUTTON-GROUP LOOKUPS
// #dig-action-row1/2 .btn and #panel .btn / #bottom-nav .bnav-btn are
// static markup (rendered once by the server template, never rebuilt) but
// were being re-queried with querySelectorAll on every poll/command. Cache
// each NodeList as an array on first access and reuse it.
// ============================================================
let _digActionBtnsCache = null;
function digActionButtons() {
  if (!_digActionBtnsCache) {
    _digActionBtnsCache = Array.from(
      document.querySelectorAll("#dig-action-row1 .btn, #dig-action-row2 .btn")
    );
  }
  return _digActionBtnsCache;
}

// ============================================================
// BUTTON DISABLE — class + aria-disabled + reason
// The .disabled class alone only blocked the mouse (pointer-events); a
// keyboard Enter/Space still fired the click. bootstrap.js now refuses to
// dispatch any [aria-disabled="true"] trigger and shows its reason as a
// toast, so taps on touch screens explain *why* instead of doing nothing.
// ============================================================
const NPC_TURN_REASON = "Wait — a bot is playing its turn";

function setBtnDisabled(btn, disabled, reason) {
  btn.classList.toggle("disabled", !!disabled);
  if (disabled) {
    btn.setAttribute("aria-disabled", "true");
    if (reason) { btn.dataset.disabledReason = reason; btn.title = reason; }
  } else {
    btn.removeAttribute("aria-disabled");
    if (btn.dataset.disabledReason) {
      delete btn.dataset.disabledReason;
      btn.title = "";
    }
  }
}

// ============================================================
// TOAST — short, non-blocking feedback for button presses that fail or
// are refused. One shared live region so screen readers announce it too.
// ============================================================
let _toastTimer = null;
function showToast(text, type = "info") {
  if (!text) return;
  let el = document.getElementById("app-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "app-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.className   = `app-toast show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), type === "error" ? 4000 : 2500);
}

let _cmdLockBtnsCache = null;
function cmdLockButtons() {
  if (!_cmdLockBtnsCache) {
    _cmdLockBtnsCache = Array.from(
      document.querySelectorAll("#panel .btn, #bottom-nav .bnav-btn")
    );
  }
  return _cmdLockBtnsCache;
}

// ============================================================
