// LAST ROUND DRINK SUMMARY
// ============================================================
let _lastRoundSips      = {};   // current completed round — shown in Drinks pane
let _lastRoundDrinks    = [];   // detailed drink entries for the Drinks pane
let _prevRoundSips      = {};   // round before last — shown in 🍺 header modal
let _prevRoundDrinks    = [];   // detailed drink entries for the previous round
let _drinksPaneSelected = null; // name of player whose detail is shown in Drinks pane
let _lastMilestoneKey       = null;  // "boundary:winner" — prevents re-showing toast on every poll
let _lastMilestoneResultKey = null;  // same format — prevents re-showing drink toast on every poll
let _milestoneModalOpened   = null;  // key for which we already opened the modal (prevents re-open on re-poll)
let _milestoneAllocations   = {};    // { playerName: sips } — stepper state in modal
let _milestoneTimerID       = null;  // setInterval handle for the modal countdown

function openLastRoundModal() {
  const overlay = document.getElementById("last-round-overlay");
  const body    = document.getElementById("last-round-modal-body");
  if (!overlay || !body) return;

  const sips  = _prevRoundSips;
  const names = Object.keys(sips);
  if (!names.length) {
    body.innerHTML = `<div style="color:var(--muted);text-align:center;font-size:13px">No previous round yet.</div>`;
  } else {
    // All players in play order, not just those who drank
    const allNames = (lastState && lastState.players) || names;
    const sorted   = allNames.slice().sort((a, b) => (sips[b] || 0) - (sips[a] || 0));
    body.innerHTML = sorted.map(n => {
      const prev = sips[n] || 0;
      const cur  = _lastRoundSips[n] || 0;
      const diff = cur - prev;
      const diffStr = diff === 0 ? "" :
        `<span style="font-size:11px;color:${diff > 0 ? "var(--red)" : "var(--green)"};margin-left:4px">${diff > 0 ? "▲" : "▼"}${Math.abs(diff)}</span>`;
      return `<div class="lrp-row">
        <span>${escapeHtml(n)}</span>
        <span style="display:flex;align-items:center;gap:6px">
          <span style="font-size:11px;color:var(--muted)">prev</span>
          <span class="lrp-sips">${prev} sip${prev !== 1 ? "s" : ""}</span>
          ${diffStr}
        </span>
      </div>`;
    }).join("");
  }
  overlay.style.display = "flex";
}

function closeLastRoundModal() {
  const overlay = document.getElementById("last-round-overlay");
  if (overlay) overlay.style.display = "none";
}

// While waiting for the host to start, poll until the game exists
function startWaiting() {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (!roomCode) return;
    try {
      const url  = `/state?room_code=${encodeURIComponent(roomCode)}&client_id=${encodeURIComponent(clientId)}&_=${Date.now()}`;
      const res  = await fetch(url);
      const data = await res.json();
      if (data.ok && data.players && data.players.length > 0) {
        stopPolling();
        players  = data.players || [];
        numHands = data.num_hands || 2;
        gameMode = data.mode || "referee";
        updateHeader(data);
        buildGameUI();
        applyState(data);
        appendLog("  (Game started! Joined room " + roomCode + ")\n");
        document.getElementById("waiting").style.display = "none";
        document.getElementById("app").style.display     = "flex";
        startPolling();
      }
    } catch (_) {}
  }, 2000);
}

// Selections per pane
const sel = {
  deal:    { player: null, hand: "hand1" },
  result:  { player: null, hand: "hand1" },
  action:  { player: null, hand: "hand1" },
  digital: { player: null, hand: "hand1" },
};
let selRank = null;
let selSuit = null;

// ============================================================
// SETUP — mode
// ============================================================
let setupMode     = "digital";   // "referee" | "digital"
let setupDrinking = true;

function setBustVoteSetupToggle(on) {
  // Update ON/OFF labels — CSS sibling selector can't reach through the
  // wrapping <label>, so we mirror the same JS approach as setAnimToggle.
  const off = document.getElementById("bust-vote-lbl-setup");
  const onEl = document.getElementById("bust-vote-lbl-setup-on");
  if (off)  off.style.display  = on ? "none"   : "inline";
  if (onEl) onEl.style.display = on ? "inline" : "none";
}

function setGameType(type, btn) {
  document.querySelectorAll("#gametype-row .btn").forEach(b => b.classList.remove("sel"));
  btn.classList.add("sel");

  const refSettings  = document.getElementById("settings-ref");
  const digSettings  = document.getElementById("settings-dig");
  const wagerCell    = document.getElementById("wager-dig-cell");
  const sub          = document.getElementById("setup-sub");

  if (type === "drinking-digital") {
    setupMode     = "digital";
    setupDrinking = true;
    refSettings.style.display  = "none";
    digSettings.style.display  = "";
    wagerCell.style.display    = "";
    sub.textContent = "Virtual Drinking Blackjack — digital shoe & drink tracker";
  } else if (type === "normal") {
    setupMode     = "digital";
    setupDrinking = false;
    refSettings.style.display  = "none";
    digSettings.style.display  = "";
    wagerCell.style.display    = "none";
    sub.textContent = "Virtual Blackjack — standard rules, no drinks";
    _showMaintenanceOverlay(type, btn);
  } else {   // referee
    setupMode     = "referee";
    setupDrinking = true;
    refSettings.style.display  = "block";
    digSettings.style.display  = "none";
    sub.textContent = "Physical deck scorekeeper — real-time drink tracker";
    _showMaintenanceOverlay(type, btn);
  }
}

function _showMaintenanceOverlay(type, btn) {
  const existing = document.getElementById("maintenance-overlay");
  if (existing) existing.remove();

  const labels = { normal: "Normal", referee: "Referee" };
  const label  = labels[type] || type;

  const overlay = document.createElement("div");
  overlay.id = "maintenance-overlay";
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.78);z-index:700;display:flex;align-items:center;justify-content:center;padding:24px";

  overlay.innerHTML = `
    <div style="background:var(--surface);border-radius:16px;padding:24px;width:100%;max-width:360px;border:1px solid var(--border);text-align:center">
      <div style="font-size:28px;margin-bottom:10px">🚧</div>
      <h3 style="font-size:17px;font-weight:800;margin-bottom:10px">${label} Mode — Under Maintenance</h3>
      <p style="font-size:13px;color:var(--muted);margin-bottom:20px;line-height:1.5">
        This mode hasn't been updated to match recent features and may not work correctly.<br>
        Only <strong>Drinking</strong> mode is actively supported right now.
      </p>
      <div style="display:flex;flex-direction:column;gap:10px">
        <button class="btn" style="background:var(--border);color:var(--fg)" onclick="document.getElementById('maintenance-overlay').remove()">
          Continue Anyway
        </button>
        <button class="btn green" onclick="
          document.getElementById('maintenance-overlay').remove();
          setGameType('drinking-digital', document.querySelector('#gametype-row .btn'));
        ">
          ← Back to Drinking
        </button>
      </div>
    </div>`;

  document.body.appendChild(overlay);
}

// ============================================================
// SETUP — players
// ============================================================
const RANKS = ["A","2","3","4","5","6","7","8","9","10","J","Q","K"];
const SUITS = [
  { label: "♥", code: "h", cls: "hearts" },
  { label: "♦", code: "d", cls: "diamonds" },
  { label: "♣", code: "c", cls: "clubs" },
  { label: "♠", code: "s", cls: "spades" },
];

let numPlayersSel = 2;
function setNumPlayers(n) {
  numPlayersSel = n;
  document.querySelectorAll("#num-players-row .btn").forEach((b,i) => {
    b.classList.toggle("sel", i+2 === n);
  });
  buildNameFields(n);
}
setNumPlayers(2);

function buildNameFields(n) {
  const c = document.getElementById("name-fields");
  c.innerHTML = "";
  for (let i = 0; i < n; i++) {
    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:8px;width:100%;max-width:420px";

    const inp = document.createElement("input");
    inp.type = "text";
    inp.placeholder = `Player ${i+1} name`;
    inp.id = `pname-${i}`;
    inp.style.cssText = "flex:1;height:var(--tap);background:var(--surface);border:1.5px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:16px;padding:0 14px;";

    const npcBtn = document.createElement("button");
    npcBtn.className = "btn";
    npcBtn.id = `npc-${i}`;
    npcBtn.textContent = "BOT";
    npcBtn.dataset.npc = "0";
    npcBtn.style.cssText = "flex-shrink:0;height:var(--tap);padding:0 14px;font-size:11px;font-weight:800;letter-spacing:.6px";
    npcBtn.onclick = function(e) {
      e.preventDefault();
      const on = this.dataset.npc === "0";
      this.dataset.npc = on ? "1" : "0";
      this.classList.toggle("sel", on);
      inp.placeholder = on ? `Bot ${i+1}` : `Player ${i+1} name`;
    };

    row.appendChild(inp);
    row.appendChild(npcBtn);
    c.appendChild(row);
  }
}

// ============================================================
// START GAME
// ============================================================
async function startGame() {
  const btn = document.getElementById("start-btn");
  btn.disabled = true;

  const names = [];
  const npcs  = [];
  for (let i = 0; i < numPlayersSel; i++) {
    const isNpc = (document.getElementById(`npc-${i}`)?.dataset.npc === "1");
    const val   = (document.getElementById(`pname-${i}`)?.value || "").trim();
    const name  = val || (isNpc ? `Bot${i+1}` : `Player${i+1}`);
    names.push(name);
    if (isNpc) npcs.push(name);
  }
  npcPlayers = new Set(npcs);

  const isDigital = setupMode === "digital";
  const wager     = setupDrinking
    ? (parseInt(document.getElementById(isDigital ? "wager-dig" : "wager-ref").value) || 1)
    : 1;
  const nh        = parseInt(document.getElementById(isDigital ? "num-hands-dig" : "num-hands-ref").value) || 2;
  const numDecks  = parseInt(document.getElementById("num-decks")?.value) || 1;

  const bustVoteEnabled = !!(document.getElementById("bust-vote-setup-toggle")?.checked);

  // Player 1 is always the starting dealer
  const body = { players: names, dealer_index: 0, wager, num_hands: nh, mode: setupMode, drinking: setupDrinking, room_code: roomCode, npcs, client_id: clientId, bust_vote_enabled: bustVoteEnabled };
  if (isDigital) body.num_decks = numDecks;

  const res  = await fetch("/setup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  btn.disabled = false;

  if (!data.ok) { alert(data.output || "Setup failed."); return; }

  players          = data.players;
  numHands         = nh;
  gameMode         = data.mode || "referee";
  myRole           = data.my_role          || "admin";
  myName           = data.my_name          || null;
  myNames          = data.my_names         || (myName ? [myName] : []);
  isMyDealerClient = data.is_dealer_client !== false;  // admin always starts as dealer

  try {
    updateHeader(data);
    buildGameUI();
    applyState(data);

    document.getElementById("setup").style.display = "none";
    document.getElementById("app").style.display   = "flex";
    startPolling();
  } catch (err) {
    console.error("[startGame] Error launching game:", err);
    alert("Could not launch game: " + err.message + "\n\nCheck the browser console for details.");
    btn.disabled = false;
  }
}

