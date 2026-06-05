// STATE
// ============================================================
let players    = [];
let numHands   = 2;
let gameMode   = "referee";   // "referee" | "digital"

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
let myNames          = [];    // all local player names (local multiplayer)
let isMyDealerClient = false; // true when this client can execute game commands
let myActiveName     = null;  // the local seat currently acting (auto-switches by turn)

// Shared log sync — tracks which server-side log entries have been displayed
let logCount   = 0;
let logVersion = -1;   // -1 so the first state response always triggers a sync

// ============================================================
