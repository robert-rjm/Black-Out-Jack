// STATE
// ============================================================
let players    = [];
let numHands   = 2;
let gameMode   = "referee";   // "referee" | "digital"
// ---------------------------------------------------------------------------
// BJ multiplier — mirrors _bj_multiplier() in drinking_rules.py.
// cards: array of {rank, suit} objects from state.table.
// ---------------------------------------------------------------------------
function bjMultiplier(cards) {
  if (!cards || cards.length < 2) return 1;
  const suits  = cards.map(c => c.suit);
  const ranks  = cards.map(c => c.rank);
  const isSuited   = new Set(suits).size === 1;
  const hasAceJack = ranks.includes("A") && ranks.includes("J");
  const isAllBlack = suits.every(s => s === "spades" || s === "clubs");
  let mult = 1;
  if (isSuited)   mult *= 2;
  if (hasAceJack) mult *= 2;
  if (isAllBlack) mult *= 2;
  return mult;
}

// ---------------------------------------------------------------------------
// Security helper — escape user-controlled strings before inserting into HTML
// ---------------------------------------------------------------------------
function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let lastState  = null;        // last /command or /state response
let currentTurn = null;       // player name whose turn it is (digital only)
let roomCode   = "";          // active room code (e.g. "Jack-21")
let pollTimer  = null;        // setInterval handle for auto-refresh
let npcPlayers = new Set();   // names of NPC/bot players this session

// Client identity
let clientId         = "";    // UUID — persisted in localStorage
let myRole           = null;  // "admin" | "player" | "spectator" | "kicked" | null
let myName           = null;  // registered player name or null
let isMyDealerClient = false; // true when this client can execute game commands

// Shared log sync — tracks which server-side log entries have been displayed
let logCount   = 0;
let logVersion = -1;   // -1 so the first state response always triggers a sync

// ============================================================
