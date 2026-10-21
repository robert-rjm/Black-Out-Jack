// ============================================================
// TIP US -- PayPal tip link + QR popup
// ============================================================
// Used by the header / bottom-nav "Tip us" buttons (#btn-beer-header,
// #btn-beer-nav) and the #beer-overlay popup.

// "Tip us": tapping the button opens PayPal in a new tab straight away (it has
// to happen inside the click or browsers block it). The QR code / copy-link
// popup then shows when the player comes back to this tab, and straight away
// if the new tab was blocked or never took focus.
let _beerUrl = "";
let _beerWaiting = false;   // PayPal tab opened; show the popup when we're back
let _beerAway = false;      // this tab has been hidden since it opened

function openBeerModal() {
  const w = window.open("/beer", "_blank");
  if (!w) { _showBeerModal(); return; }   // blocked
  try { w.opener = null; } catch (_) {}
  _beerWaiting = true;
  _beerAway = document.hidden;
  // No tab switch within a moment (opened as a window, or silently blocked):
  // show the popup now rather than leaving the tap looking dead.
  setTimeout(() => { if (_beerWaiting && !_beerAway) { _beerWaiting = false; _showBeerModal(); } }, 1500);
}

document.addEventListener("visibilitychange", () => {
  if (!_beerWaiting) return;
  if (document.hidden) { _beerAway = true; return; }
  if (_beerAway) { _beerWaiting = false; _beerAway = false; _showBeerModal(); }
});

async function _showBeerModal() {
  const box = document.getElementById("beer-qr");
  if (!box) return;
  box.innerHTML = "";
  document.getElementById("beer-url").textContent = "";
  openModal("beer-overlay");
  try {
    const res  = await fetch("/beer_qr");
    const data = await res.json();
    if (!data.ok) throw new Error("failed");
    box.innerHTML = data.svg;
    _beerUrl = data.url;
    document.getElementById("beer-url").textContent = data.url;
  } catch (_) {
    document.getElementById("beer-url").textContent = "paypal.me/robertmichels";
  }
}

function closeBeerModal() { closeModal("beer-overlay"); }

async function copyBeerLink() {
  const text = _beerUrl || "https://paypal.me/robertmichels";
  try {
    await navigator.clipboard.writeText(text);
    showToast("Link copied");
  } catch (_) {
    showToast(text);
  }
}
