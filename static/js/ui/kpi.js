// ============================================================
// KPI PANEL — leaderboard, stats, trivia
// ============================================================

// ---- Tab switching ----
function switchKpiTab(name, el) {
  document.querySelectorAll(".kpi-tabs-bar .kpi-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".kpi-pane").forEach(p => p.classList.remove("active"));
  if (el) el.classList.add("active");
  const pane = document.getElementById("pane-kpi-" + name);
  if (pane) pane.classList.add("active");
}

// ---- Leaderboard renderer ----
function renderLeaderboard(state) {
  const el = document.getElementById("leaderboard-content");
  if (!el) return;

  const handStats  = state.hand_stats  || {};
  const sipTotals  = state.sip_totals  || {};
  const dealer     = (state.dealer     || "").toLowerCase();
  const playOrder  = state.play_order  || state.players || [];
  const round      = state.round       || 0;

  // Build rows — one per player that has played at least one hand
  const rows = playOrder.map(name => {
    const hs    = handStats[name] || {};
    const hands = hs.hands  || 0;
    const wins  = hs.wins   || 0;
    const losses= hs.losses || 0;
    const pushes= hs.pushes || 0;
    const sips  = sipTotals[name] || 0;
    const wr    = hands > 0 ? Math.round((wins / hands) * 100) : null;
    return { name, hands, wins, losses, pushes, sips, wr };
  }).filter(r => r.hands > 0 || r.sips > 0);

  if (rows.length === 0) {
    el.innerHTML = '<div class="lb-empty">No hands played yet this session</div>';
    return;
  }

  // Sort by win rate desc (null → last), then sips asc as tiebreak
  rows.sort((a, b) => {
    if (a.wr === null && b.wr === null) return a.sips - b.sips;
    if (a.wr === null) return 1;
    if (b.wr === null) return -1;
    if (b.wr !== a.wr) return b.wr - a.wr;
    return a.sips - b.sips;
  });

  // Win-rate colour helper
  function wrClass(wr) {
    if (wr === null) return "";
    if (wr >= 55)   return "lb-wr-good";
    if (wr >= 40)   return "lb-wr-ok";
    return "lb-wr-bad";
  }

  const rankEmoji = ["🥇", "🥈", "🥉"];

  const tbody = rows.map((r, i) => {
    const isDealer  = r.name.toLowerCase() === dealer;
    const rowClass  = isDealer ? " lb-row-dealer" : "";
    const rankLabel = i < 3
      ? `<span class="lb-rank lb-rank-${i+1}">${rankEmoji[i]}</span>`
      : `<span class="lb-rank">${i+1}</span>`;
    const wrStr  = r.wr !== null ? `<span class="${wrClass(r.wr)}">${r.wr}%</span>` : `<span style="opacity:.4">—</span>`;
    const sipStr = r.sips > 0
      ? `<span class="lb-sips">🍺${r.sips}</span>`
      : `<span class="lb-sips-zero">—</span>`;
    const wlp = r.hands > 0
      ? `<span style="color:var(--green)">${r.wins}</span>/<span style="color:var(--red)">${r.losses}</span>/<span style="color:var(--muted)">${r.pushes}</span>`
      : `<span style="opacity:.4">—</span>`;

    return `<tr class="${rowClass}">
      <td class="lb-name">${rankLabel}${escapeHtml(r.name)}${isDealer ? ' <span style="font-size:9px;color:var(--accent);opacity:.7">🎰</span>' : ''}</td>
      <td>${wrStr}</td>
      <td>${wlp}</td>
      <td>${sipStr}</td>
    </tr>`;
  }).join("");

  const roundLabel = round > 0 ? `${round} round${round !== 1 ? "s" : ""} played` : "";

  el.innerHTML = `
    ${roundLabel ? `<div class="lb-meta">${roundLabel}</div>` : ""}
    <table class="lb-table">
      <thead>
        <tr>
          <th>Player</th>
          <th>Win %</th>
          <th>W/L/P</th>
          <th>Sips</th>
        </tr>
      </thead>
      <tbody>${tbody}</tbody>
    </table>`;
}

// ---- Hook into state updates ----
function updateKpiPanel(state) {
  renderLeaderboard(state);
}
