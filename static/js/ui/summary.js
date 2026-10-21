// ============================================================
// SESSION SUMMARY & EXPORTS
// ============================================================
// Split out of admin-settings.js: the end-of-session summary modal, the
// drink CSV / decision-log downloads and the opt-in auto-export.

// Auto-export (every 10 rounds, both reports) is a personal convenience for
// whoever's mining these sessions into bot profiles -- not a security
// boundary, just hidden from everyone else's summary modal so it doesn't
// clutter a normal player's view. Off by default even for these names; the
// checkbox in #summary-overlay opts in per-device (localStorage).
const _AUTO_EXPORT_ALLOWLIST = ["rob", "marko", "david"];

function _isAutoExportEligible() {
  return myRole === ROLE.ADMIN &&
    (myNames || []).some(n => _AUTO_EXPORT_ALLOWLIST.includes(n.toLowerCase()));
}

function setAutoExportDecisions(enabled) {
  lsSet("autoExportDecisions", enabled ? "1" : "0");
}

function _autoExportDecisionsOn() {
  return _isAutoExportEligible() && lsGet("autoExportDecisions") === "1";
}

async function showSessionSummary() {
  const overlay = document.getElementById("summary-overlay");
  const meta    = document.getElementById("summary-meta");
  const body    = document.getElementById("summary-body");
  if (!overlay) return;

  const toggleRow = document.getElementById("auto-export-row");
  const toggleBox = document.getElementById("auto-export-toggle");
  if (toggleRow) toggleRow.style.display = _isAutoExportEligible() ? "block" : "none";
  if (toggleBox) toggleBox.checked = lsGet("autoExportDecisions") === "1";

  meta.textContent = "Loading…";
  body.innerHTML   = "";
  openModal("summary-overlay");

  try {
    const res  = await fetch(`/summary_json?room_code=${encodeURIComponent(roomCode)}&_=${Date.now()}`);
    const data = await res.json();

    if (!data.ok || !data.players || !data.players.length) {
      meta.textContent = "No session data yet — play some rounds first.";
      return;
    }

    meta.textContent = `${data.rounds} round${data.rounds !== 1 ? "s" : ""} completed`;

    const drinking = lastState?.drinking_mode !== false;
    // Last round's sips per player (▲/▼ vs the round before it), merged in
    // from the old standalone "Last Round" popup.
    const lastSips = DrinkUI.lastRoundSips || {};
    const prevSips = DrinkUI.prevRoundSips || {};
    const lastRoundCell = name => {
      const last = lastSips[name] || 0;
      const diff = last - (prevSips[name] || 0);
      const arrow = diff === 0 ? "" :
        ` <span style="font-size:11px;color:${diff > 0 ? "var(--red)" : "var(--green)"}">${diff > 0 ? "▲" : "▼"}${Math.abs(diff)}</span>`;
      return `${last}${arrow}`;
    };
    const tbl = document.createElement("table");
    tbl.id = "summary-table";
    tbl.innerHTML = drinking ? `
      <thead><tr>
        <th>Player</th>
        <th>Last rd</th>
        <th>As player</th>
        <th>As dealer</th>
        <th>Total 🍺</th>
      </tr></thead>` : `
      <thead><tr>
        <th>Player</th>
      </tr></thead>`;
    const tb = document.createElement("tbody");
    data.players.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = drinking ? `
        <td style="font-weight:600">${escapeHtml(p.name)}</td>
        <td>${lastRoundCell(p.name)}</td>
        <td>${p.player_sips}</td>
        <td>${p.dealer_sips}</td>
        <td class="sum-total">${p.total_sips}</td>` : `
        <td style="font-weight:600">${escapeHtml(p.name)}</td>`;
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    body.appendChild(tbl);
  } catch (_) {
    meta.textContent = "Could not load summary — check connection.";
  }
}

function closeSummaryModal() {
  closeModal("summary-overlay");
}

// ============================================================
// CSV EXPORT
// ============================================================
function exportDrinkCSV() {
  if (!roomCode) { alert("No active session."); return; }
  window.location.href = "/export_xlsx?room_code=" + encodeURIComponent(roomCode);
}

function exportDecisionLog() {
  if (!roomCode) { alert("No active session."); return; }
  window.location.href = "/export_decisions?room_code=" + encodeURIComponent(roomCode);
}

// Fires both existing downloads back to back (same requests the manual
// summary-modal buttons make) -- staggered slightly so the browser treats
// them as two distinct attachment downloads instead of one navigation
// interrupting the other.
let _lastAutoExportRound = 0;

function _maybeAutoExportDecisions(state) {
  const round = state.round || 0;
  if (round <= _lastAutoExportRound || round % 10 !== 0) return;
  _lastAutoExportRound = round;
  if (!_autoExportDecisionsOn()) return;

  exportDrinkCSV();
  setTimeout(() => exportDecisionLog(), 400);
}
