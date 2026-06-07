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

// ---- Streak helpers ----
function _streakLabel(current) {
  if (!current) return `<span style="opacity:.35">—</span>`;
  if (current > 0) return `<span style="color:var(--green);font-weight:700">🔥${current}</span>`;
  return `<span style="color:var(--red);font-weight:700">💀${Math.abs(current)}</span>`;
}

// ---- Leaderboard renderer ----
function renderLeaderboard(state) {
  const el = document.getElementById("leaderboard-content");
  if (!el) return;

  const handStats  = state.hand_stats  || {};
  const sipTotals  = state.sip_totals  || {};
  const streaks    = state.streaks     || {};
  const dealer     = (state.dealer     || "").toLowerCase();
  const playOrder  = state.play_order  || state.players || [];
  const round      = state.round       || 0;

  const rows = playOrder.map(name => {
    const hs      = handStats[name] || {};
    const sk      = streaks[name]   || {};
    const hands   = hs.hands  || 0;
    const wins    = hs.wins   || 0;
    const losses  = hs.losses || 0;
    const pushes  = hs.pushes || 0;
    const sips    = sipTotals[name] || 0;
    const wr      = hands > 0 ? Math.round((wins / hands) * 100) : null;
    const current = sk.current || 0;
    return { name, hands, wins, losses, pushes, sips, wr, current };
  }).filter(r => r.hands > 0 || r.sips > 0);

  if (rows.length === 0) {
    el.innerHTML = '<div class="lb-empty">No hands played yet this session</div>';
    return;
  }

  rows.sort((a, b) => {
    if (a.wr === null && b.wr === null) return a.sips - b.sips;
    if (a.wr === null) return 1;
    if (b.wr === null) return -1;
    if (b.wr !== a.wr) return b.wr - a.wr;
    return a.sips - b.sips;
  });

  function wrClass(wr) {
    if (wr === null) return "";
    if (wr >= 55) return "lb-wr-good";
    if (wr >= 40) return "lb-wr-ok";
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
      <td>${_streakLabel(r.current)}</td>
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
          <th>Streak</th>
          <th>Sips</th>
        </tr>
      </thead>
      <tbody>${tbody}</tbody>
    </table>`;
}

// ---- Stats tab renderer ----
function renderStats(state) {
  const el = document.getElementById("stats-content");
  if (!el) return;

  const handStats      = state.hand_stats         || {};
  const sipTotals      = state.sip_totals         || {};
  const maxRoundSips   = state.max_round_sips     || {};
  const streaks        = state.streaks            || {};
  const dealerBustRnds = state.dealer_bust_rounds || 0;
  const round          = state.round              || 0;
  const playOrder      = state.play_order         || state.players || [];
  const dealer         = (state.dealer            || "").toLowerCase();

  const rows = playOrder.map(name => {
    const hs        = handStats[name] || {};
    const sk        = streaks[name]   || {};
    const hands     = hs.hands        || 0;
    const dh        = hs.double_hands || 0;
    const dw        = hs.double_wins  || 0;
    const sh        = hs.split_hands  || 0;
    const sw        = hs.split_wins   || 0;
    const bj        = hs.blackjacks   || 0;
    const busts     = hs.busts        || 0;
    const totalSips = sipTotals[name] || 0;
    const maxSips   = maxRoundSips[name] || 0;
    const avgSips   = round > 0 ? (totalSips / round).toFixed(1) : "—";
    const dblPct    = dh > 0 ? Math.round((dw / dh) * 100) + "%" : "—";
    const spPct     = sh > 0 ? Math.round((sw / sh) * 100) + "%" : "—";
    const lw        = sk.longest_win  || 0;
    const ll        = sk.longest_loss || 0;
    return { name, hands, bj, busts, dh, dw, dblPct, sh, sw, spPct, avgSips, maxSips, totalSips, lw, ll };
  }).filter(r => r.hands > 0 || r.totalSips > 0);

  if (rows.length === 0) {
    el.innerHTML = '<div class="lb-empty">No data yet — play a round first</div>';
    return;
  }

  // Per-player table
  const isDealer = name => name.toLowerCase() === dealer;

  const tbody = rows.map(r => {
    const rc = isDealer(r.name) ? " lb-row-dealer" : "";
    const nameCell  = `${escapeHtml(r.name)}${isDealer(r.name) ? ' <span style="font-size:9px;color:var(--accent);opacity:.7">🎰</span>' : ''}`;
    const bjCell    = r.bj    > 0 ? `<span style="color:var(--yellow);font-weight:700">🃏${r.bj}</span>`  : `<span style="opacity:.35">—</span>`;
    const bustCell  = r.busts > 0 ? `<span style="color:var(--red)">${r.busts}</span>` : `<span style="opacity:.35">0</span>`;
    const maxCell   = r.maxSips > 0 ? `<span style="color:var(--red)">🍺${r.maxSips}</span>` : `<span style="opacity:.35">—</span>`;
    const lwCell    = r.lw > 0 ? `<span style="color:var(--green)">🔥${r.lw}</span>` : `<span style="opacity:.35">—</span>`;
    const llCell    = r.ll > 0 ? `<span style="color:var(--red)">💀${r.ll}</span>` : `<span style="opacity:.35">—</span>`;
    return `<tr class="${rc}">
      <td class="lb-name">${nameCell}</td>
      <td>${bjCell}</td>
      <td>${r.dblPct}</td>
      <td>${r.spPct}</td>
      <td>${bustCell}</td>
      <td>${r.avgSips}</td>
      <td>${maxCell}</td>
      <td>${lwCell}</td>
      <td>${llCell}</td>
    </tr>`;
  }).join("");

  const table = `
    <table class="lb-table stats-table">
      <thead><tr>
        <th>Player</th>
        <th title="Natural blackjacks won">BJ</th>
        <th title="Double down win rate">Dbl%</th>
        <th title="Split win rate">Sp%</th>
        <th title="Times busted">Busts</th>
        <th title="Average sips per round">Avg🍺</th>
        <th title="Biggest single-round sip hit">Peak🍺</th>
        <th title="Longest win streak">🔥</th>
        <th title="Longest loss streak">💀</th>
      </tr></thead>
      <tbody>${tbody}</tbody>
    </table>`;

  // Session callout cards
  const totalBJ   = rows.reduce((s, r) => s + r.bj, 0);
  const bjRate    = round > 0 ? ((totalBJ / (rows.length * round)) * 100).toFixed(1) : null;
  const bjExpected = 4.8;
  const peakRow   = [...rows].sort((a, b) => b.maxSips - a.maxSips)[0];
  const bustRate  = round > 0 ? Math.round((dealerBustRnds / round) * 100) : null;

  // Streak callouts
  const bestWinRow  = [...rows].sort((a, b) => b.lw - a.lw)[0];
  const bestLossRow = [...rows].sort((a, b) => b.ll - a.ll)[0];

  const callouts = [];

  if (totalBJ > 0) {
    callouts.push(`<div class="stat-card">
      <div class="stat-card-icon">🃏</div>
      <div class="stat-card-body">
        <div class="stat-card-value">${totalBJ} blackjack${totalBJ !== 1 ? "s" : ""}</div>
        <div class="stat-card-label">this session${bjRate !== null ? ` · ${bjRate}% rate (expected ~${bjExpected}%)` : ""}</div>
      </div>
    </div>`);
  }

  if (peakRow && peakRow.maxSips > 0) {
    callouts.push(`<div class="stat-card">
      <div class="stat-card-icon">💀</div>
      <div class="stat-card-body">
        <div class="stat-card-value">${peakRow.maxSips} sips</div>
        <div class="stat-card-label">worst round — ${escapeHtml(peakRow.name)}</div>
      </div>
    </div>`);
  }

  if (bustRate !== null) {
    const bustColour = dealerBustRnds === 0 ? "" : bustRate >= 40 ? "color:var(--green)" : bustRate >= 25 ? "color:var(--yellow)" : "color:var(--muted)";
    callouts.push(`<div class="stat-card">
      <div class="stat-card-icon">🎰</div>
      <div class="stat-card-body">
        <div class="stat-card-value" style="${bustColour}">${bustRate}% dealer busts</div>
        <div class="stat-card-label">${dealerBustRnds} of ${round} round${round !== 1 ? "s" : ""} · casino avg ~28%</div>
      </div>
    </div>`);
  }

  if (bestWinRow && bestWinRow.lw >= 2) {
    callouts.push(`<div class="stat-card">
      <div class="stat-card-icon">🔥</div>
      <div class="stat-card-body">
        <div class="stat-card-value" style="color:var(--green)">${bestWinRow.lw}-round win streak</div>
        <div class="stat-card-label">${escapeHtml(bestWinRow.name)} — longest this session</div>
      </div>
    </div>`);
  }

  if (bestLossRow && bestLossRow.ll >= 2) {
    callouts.push(`<div class="stat-card">
      <div class="stat-card-icon">📉</div>
      <div class="stat-card-body">
        <div class="stat-card-value" style="color:var(--red)">${bestLossRow.ll}-round losing streak</div>
        <div class="stat-card-label">${escapeHtml(bestLossRow.name)} — longest this session</div>
      </div>
    </div>`);
  }

  el.innerHTML = table + (callouts.length ? `<div class="stat-cards">${callouts.join("")}</div>` : "");
}

// ---- Hook into state updates ----
function updateKpiPanel(state) {
  renderLeaderboard(state);
  renderStats(state);
}
