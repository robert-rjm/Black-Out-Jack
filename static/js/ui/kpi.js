// ============================================================
// KPI PANEL — leaderboard, stats, trivia
// ============================================================

// ---- Win% color coding ----
function wrClass(wr) {
  if (wr === null) return "";
  if (wr >= 50) return "lb-wr-good";
  if (wr >= 40) return "lb-wr-ok";
  return "lb-wr-bad";
}

// ---- Tab switching ----
function switchKpiTab(name, el) {
  document.querySelectorAll(".kpi-tabs-bar .kpi-tab").forEach(t => t.classList.toggle("active", t === el));
  document.querySelectorAll(".kpi-pane").forEach(p => p.classList.remove("active"));
  if (el) el.classList.add("active");
  const pane = document.getElementById("pane-kpi-" + name);
  if (pane) pane.classList.add("active");
  if (name === "trivia" && typeof updateTriviaPanel === "function") updateTriviaPanel(typeof lastState !== "undefined" ? lastState : null);
}

// ---- Helpers ----
function _streakLabel(current) {
  if (!current) return `<span style="opacity:.35">—</span>`;
  if (current > 0) return `<span style="color:var(--green);font-weight:700">🔥${current}</span>`;
  return `<span style="color:var(--red);font-weight:700">💀${Math.abs(current)}</span>`;
}

function _fmtDuration(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2,"0")}s`;
  return `${s}s`;
}

function _rollingAvg(history, n) {
  if (!history || history.length < n) return null;
  const slice = history.slice(-n);
  return (slice.reduce((a, b) => a + b, 0) / slice.length).toFixed(1);
}

// ---- Leaderboard renderer ----
function renderLeaderboard(state) {
  const el = document.getElementById("leaderboard-content");
  if (!el) return;

  const handStats = state.hand_stats || {};
  const sipTotals = state.sip_totals || {};
  const streaks   = state.streaks    || {};
  const dealer    = (state.dealer    || "").toLowerCase();
  const playOrder = state.play_order || state.players || [];
  const round     = state.round      || 0;

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

  const rankEmoji = ["🥇", "🥈", "🥉"];

  const tbody = rows.map((r, i) => {
    const isDealer  = r.name.toLowerCase() === dealer;
    const rowClass  = isDealer ? " lb-row-dealer" : "";
    const rankLabel = i < 3
      ? `<span class="lb-rank lb-rank-${i+1}">${rankEmoji[i]}</span>`
      : `<span class="lb-rank">${i+1}</span>`;
    const wrStr  = r.wr !== null
      ? `<span class="${wrClass(r.wr)}">${r.wr}%</span>`
      : `<span style="opacity:.4">—</span>`;
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
      <thead><tr>
        <th>Player</th><th>Win%</th><th>W/L/P</th><th>Streak</th><th>Sips</th>
      </tr></thead>
      <tbody>${tbody}</tbody>
    </table>`;
}

// ---- Stats renderer ----
function renderStats(state) {
  const el = document.getElementById("stats-content");
  if (!el) return;

  const handStats         = state.hand_stats           || {};
  const sipTotals         = state.sip_totals           || {};
  const maxRoundSips      = state.max_round_sips       || {};
  const streaks           = state.streaks              || {};
  const strategyDecisions = state.strategy_decisions   || {};
  const dealerBustRnds    = state.dealer_bust_rounds   || 0;
  const round             = state.round                || 0;
  const history           = state.round_sip_history    || [];
  const sessionSecs       = state.session_seconds      || 0;
  const playOrder         = state.play_order           || state.players || [];
  const dealer            = (state.dealer              || "").toLowerCase();

  // ── Session-wide callout banner ──────────────────────────────
  const totalSips    = Object.values(sipTotals).reduce((a, b) => a + b, 0);
  const avgPerRound  = round > 0 ? (totalSips / round).toFixed(1) : null;
  const avg3         = _rollingAvg(history, 3);
  const avg5         = _rollingAvg(history, 5);
  const avg10        = _rollingAvg(history, 10);
  const sipm         = sessionSecs > 0 ? (totalSips / (sessionSecs / 60)).toFixed(2) : null;
  const totalHands   = Object.values(handStats).reduce((a, h) => a + (h.hands || 0), 0);
  const totalBJ      = Object.values(handStats).reduce((a, h) => a + (h.blackjacks || 0), 0);
  const totalBusts   = Object.values(handStats).reduce((a, h) => a + (h.busts || 0), 0);
  const totalWins    = Object.values(handStats).reduce((a, h) => a + (h.wins || 0), 0);
  const totalPushes  = Object.values(handStats).reduce((a, h) => a + (h.pushes || 0), 0);
  const bustRatePct  = totalHands > 0 ? Math.round((totalBusts / totalHands) * 100) : null;
  const winRatePct   = totalHands > 0 ? Math.round((totalWins  / totalHands) * 100) : null;
  const pushRatePct  = totalHands > 0 ? Math.round((totalPushes / totalHands) * 100) : null;
  const dealerBustPct = round > 0 ? Math.round((dealerBustRnds / round) * 100) : null;

  // Avg/round trend colour: compare overall avg to last-3
  // Green = last 3 rounds lighter than session avg; red = heavier; neutral = no data yet
  let avgRoundCol = "var(--text)";
  if (avgPerRound !== null && avg3 !== null) {
    avgRoundCol = parseFloat(avg3) < parseFloat(avgPerRound) ? "var(--green)" : "var(--red)";
  }

  // Rolling sub-labels shown only when enough rounds exist
  const rollingTags = [
    avg3  ? `L3: <b>${avg3}</b>`   : "",
    avg5  ? `L5: <b>${avg5}</b>`   : "",
    avg10 ? `L10: <b>${avg10}</b>` : "",
  ].filter(Boolean).join(" · ");

  const sessionBanner = `
    <div class="stat-session-banner">
      <div class="ssb-row">
        ${avgPerRound !== null ? `
        <div class="ssb-item">
          <div class="ssb-val" style="color:${avgRoundCol}">${avgPerRound}</div>
          <div class="ssb-lbl">Avg/round</div>
          ${rollingTags ? `<div class="ssb-rolling">${rollingTags}</div>` : ""}
        </div>` : ""}
        <div class="ssb-item"><div class="ssb-val" style="color:var(--red)">${totalSips}</div><div class="ssb-lbl">Total sips</div></div>
        ${sipm !== null ? `<div class="ssb-item"><div class="ssb-val">${sipm}</div><div class="ssb-lbl">Sips/min</div></div>` : ""}
        <div class="ssb-item"><div class="ssb-val">${_fmtDuration(sessionSecs)}</div><div class="ssb-lbl">Duration</div></div>
      </div>
      <div class="ssb-row ssb-row-sm">
        <span class="ssb-tag">${totalHands} hands</span>
        ${winRatePct !== null ? `<span class="ssb-tag">Win ${winRatePct}%</span>` : ""}
        ${bustRatePct !== null ? `<span class="ssb-tag">Bust ${bustRatePct}%</span>` : ""}
        ${pushRatePct !== null ? `<span class="ssb-tag">Push ${pushRatePct}%</span>` : ""}
        ${totalBJ ? `<span class="ssb-tag">🃏 ${totalBJ} BJ${totalBJ !== 1 ? "s" : ""}</span>` : ""}
        ${dealerBustPct !== null ? `<span class="ssb-tag">Dealer bust ${dealerBustPct}%</span>` : ""}
      </div>
    </div>`;

  // ── Per-player table ─────────────────────────────────────────
  const rows = playOrder.map(name => {
    const hs          = handStats[name] || {};
    const sk          = streaks[name]   || {};
    const hands       = hs.hands        || 0;
    const wins        = hs.wins         || 0;
    const losses      = hs.losses       || 0;
    const pushes      = hs.pushes       || 0;
    const wr          = hands > 0 ? Math.round((wins / hands) * 100) : null;
    const dh          = hs.double_hands || 0;
    const dw          = hs.double_wins  || 0;
    const sh          = hs.split_hands  || 0;
    const sw          = hs.split_wins   || 0;
    const bj          = hs.blackjacks   || 0;
    const busts       = hs.busts        || 0;
    const suited      = hs.suited_hands || 0;
    const hitH        = hs.hit_hands    || 0;
    const sub17       = hs.stand_sub17  || 0;
    const totalScore  = hs.total_score  || 0;
    const scoredH     = hs.scored_hands || 0;
    const totalSipsP  = sipTotals[name] || 0;
    const maxSips     = maxRoundSips[name] || 0;
    const avgSips     = round > 0 ? (totalSipsP / round).toFixed(1) : "—";
    const dblPct      = dh > 0 ? Math.round((dw / dh) * 100) + "%" : "—";
    const spPct       = sh > 0 ? Math.round((sw / sh) * 100) + "%" : "—";
    const hitRate     = hands > 0 ? Math.round((hitH / hands) * 100) + "%" : "—";
    const avgHV       = scoredH > 0 ? (totalScore / scoredH).toFixed(1) : "—";
    const lw          = sk.longest_win  || 0;
    const ll          = sk.longest_loss || 0;
    const current     = sk.current      || 0;
    const sd          = strategyDecisions[name] || {};
    const sdTotal     = sd.total   || 0;
    const sdCorrect   = sd.correct || 0;
    const sdPct       = sdTotal >= 3 ? Math.round((sdCorrect / sdTotal) * 100) : null;
    return { name, hands, wins, losses, pushes, wr, current, bj, busts, suited, hitRate, sub17, avgHV, dblPct, spPct, avgSips, maxSips, totalSipsP, lw, ll, sdPct, sdCorrect, sdTotal };
  }).filter(r => r.hands > 0 || r.totalSipsP > 0);

  if (rows.length === 0) {
    el.innerHTML = sessionBanner + '<div class="lb-empty">No data yet — play a round first</div>';
    return;
  }

  const isDlr = name => name.toLowerCase() === dealer;

  const tbody = rows.map(r => {
    const rc       = isDlr(r.name) ? " lb-row-dealer" : "";
    const nameCell = `${escapeHtml(r.name)}${isDlr(r.name) ? ' <span style="font-size:9px;color:var(--accent);opacity:.7">🎰</span>' : ''}`;
    const bjCell   = r.bj    > 0 ? `<span style="color:var(--yellow);font-weight:700">🃏${r.bj}</span>`  : `<span style="opacity:.35">—</span>`;
    const bstCell  = r.busts > 0 ? `<span style="color:var(--red)">${r.busts}</span>` : `<span style="opacity:.35">0</span>`;
    const maxCell  = r.maxSips > 0 ? `<span style="color:var(--red)">🍺${r.maxSips}</span>` : `<span style="opacity:.35">—</span>`;
    const lwCell   = r.lw > 0 ? `<span style="color:var(--green)">🔥${r.lw}</span>` : `<span style="opacity:.35">—</span>`;
    const llCell   = r.ll > 0 ? `<span style="color:var(--red)">💀${r.ll}</span>`   : `<span style="opacity:.35">—</span>`;
    const stCell   = r.suited > 0 ? `<span style="color:var(--accent)">${r.suited}</span>` : `<span style="opacity:.35">—</span>`;
    const s17Cell  = r.sub17  > 0 ? `<span style="color:var(--yellow)">${r.sub17}</span>`  : `<span style="opacity:.35">0</span>`;
    let sdCell;
    if (r.sdPct === null) {
      sdCell = `<span style="opacity:.35">—</span>`;
    } else {
      sdCell = `<span style="font-weight:700">${r.sdPct}%</span>`;
    }
    return `<tr class="${rc}">
      <td class="lb-name">${nameCell}</td>
      <td>${bjCell}</td>
      <td>${r.dblPct}</td>
      <td>${r.spPct}</td>
      <td>${r.hitRate}</td>
      <td>${s17Cell}</td>
      <td>${r.avgHV}</td>
      <td>${bstCell}</td>
      <td>${stCell}</td>
      <td>${sdCell}</td>
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
        <th title="Hit rate (hands with ≥1 hit)">Hit%</th>
        <th title="Times stood on sub-17">&lt;17</th>
        <th title="Average non-bust hand value">AvgHV</th>
        <th title="Times busted">Bust</th>
        <th title="Suited hands">Suit</th>
        <th title="Basic strategy accuracy (shown after 3+ decisions)">Strat%</th>
        <th title="Average sips per round">Avg🍺</th>
        <th title="Biggest single-round sip hit">Peak🍺</th>
        <th title="Longest win streak">🔥</th>
        <th title="Longest loss streak">💀</th>
      </tr></thead>
      <tbody>${tbody}</tbody>
    </table>`;

  // ── Callout cards ────────────────────────────────────────────
  const callouts = [];

  // Leaderboard tile — ranked W/L/P per player
  const rankEmoji = ["🥇", "🥈", "🥉"];
  const lbSorted = [...rows]
    .filter(r => r.hands > 0)
    .sort((a, b) => {
      if (a.wr === null && b.wr === null) return a.totalSipsP - b.totalSipsP;
      if (a.wr === null) return 1;
      if (b.wr === null) return -1;
      if (b.wr !== a.wr) return b.wr - a.wr;
      return a.totalSipsP - b.totalSipsP;
    });
  const COL = "20px 1fr 36px 64px 30px 36px"; // medal · name · win% · W/L/P · streak · sips
  if (lbSorted.length > 0) {
    const headerRow = `<div style="display:grid;grid-template-columns:${COL};gap:0 6px;
        font-size:8px;font-weight:700;color:var(--muted);text-transform:uppercase;
        letter-spacing:.3px;padding-bottom:3px;border-bottom:1px solid var(--border);margin-bottom:3px">
      <span></span>
      <span>Player</span>
      <span style="text-align:right">Win%</span>
      <span style="text-align:center">W / L / P</span>
      <span style="text-align:center">Str</span>
      <span style="text-align:right">Sips</span>
    </div>`;
    const lbLines = lbSorted.map((r, i) => {
      const medal  = i < 3 ? rankEmoji[i] : `<span style="font-size:10px;color:var(--muted)">${i + 1}</span>`;
      const wrStr  = r.wr !== null ? `<span class="${wrClass(r.wr)}">${r.wr}%</span>` : `<span style="opacity:.4">—</span>`;
      const wlp    = `<span style="color:var(--green)">${r.wins}</span><span style="color:var(--muted)">/</span><span style="color:var(--red)">${r.losses}</span><span style="color:var(--muted)">/</span><span style="color:var(--muted)">${r.pushes}</span>`;
      const sipStr = r.totalSipsP > 0 ? `<span style="color:var(--red)">🍺${r.totalSipsP}</span>` : `<span style="opacity:.35">—</span>`;
      return `<div style="display:grid;grid-template-columns:${COL};gap:0 6px;
          align-items:center;padding:2px 0;font-size:11px">
        <span style="text-align:center">${medal}</span>
        <span style="font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(r.name)}</span>
        <span style="text-align:right">${wrStr}</span>
        <span style="text-align:center">${wlp}</span>
        <span style="text-align:center">${_streakLabel(r.current)}</span>
        <span style="text-align:right">${sipStr}</span>
      </div>`;
    }).join("");
    callouts.push(`<div class="stat-card stat-card-primary" style="flex-direction:column;align-items:stretch;gap:0">
      <div style="font-size:9px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px">🏆 Rankings</div>
      ${headerRow}${lbLines}
    </div>`);
  }

  const peakRow = [...rows].sort((a, b) => b.maxSips - a.maxSips)[0];
  const bestWin = [...rows].sort((a, b) => b.lw - a.lw)[0];
  const bestLoss = [...rows].sort((a, b) => b.ll - a.ll)[0];

  if (totalBJ > 0) {
    const bjRate = round > 0 ? ((totalBJ / (Object.keys(handStats).length * round)) * 100).toFixed(1) : null;
    callouts.push(`<div class="stat-card"><div class="stat-card-icon">🃏</div><div class="stat-card-body">
      <div class="stat-card-value">${totalBJ} blackjack${totalBJ !== 1 ? "s" : ""}</div>
      <div class="stat-card-label">${bjRate !== null ? `${bjRate}% rate · expected ~4.8%` : "this session"}</div>
    </div></div>`);
  }
  if (peakRow && peakRow.maxSips > 0) {
    callouts.push(`<div class="stat-card"><div class="stat-card-icon">💀</div><div class="stat-card-body">
      <div class="stat-card-value">${peakRow.maxSips} sips</div>
      <div class="stat-card-label">worst round — ${escapeHtml(peakRow.name)}</div>
    </div></div>`);
  }
  if (dealerBustPct !== null) {
    const col = dealerBustRnds === 0 ? "" : dealerBustPct >= 40 ? "color:var(--green)" : dealerBustPct >= 25 ? "color:var(--yellow)" : "color:var(--muted)";
    callouts.push(`<div class="stat-card"><div class="stat-card-icon">🎰</div><div class="stat-card-body">
      <div class="stat-card-value" style="${col}">${dealerBustPct}% dealer busts</div>
      <div class="stat-card-label">${dealerBustRnds} of ${round} rounds · casino avg ~28%</div>
    </div></div>`);
  }

  if (bestWin && bestWin.lw >= 2) {
    callouts.push(`<div class="stat-card"><div class="stat-card-icon">🔥</div><div class="stat-card-body">
      <div class="stat-card-value" style="color:var(--green)">${bestWin.lw}-round win streak</div>
      <div class="stat-card-label">${escapeHtml(bestWin.name)} — session record</div>
    </div></div>`);
  }
  if (bestLoss && bestLoss.ll >= 2) {
    callouts.push(`<div class="stat-card"><div class="stat-card-icon">📉</div><div class="stat-card-body">
      <div class="stat-card-value" style="color:var(--red)">${bestLoss.ll}-round losing streak</div>
      <div class="stat-card-label">${escapeHtml(bestLoss.name)} — session record</div>
    </div></div>`);
  }

  el.innerHTML = sessionBanner + table + (callouts.length ? `<div class="stat-cards">${callouts.join("")}</div>` : "");
}

// ---- Hook into state updates ----
function updateKpiPanel(state) {
  renderStats(state);
  if (typeof updateTriviaPanel === "function") updateTriviaPanel(state);
}
