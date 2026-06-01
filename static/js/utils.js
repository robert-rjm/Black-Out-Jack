// ============================================================
// SAFE localStorage HELPERS
// Safari Private Browsing throws SecurityError on any localStorage access.
// All reads/writes go through these wrappers so a blocked storage never crashes the app.
// ============================================================
function lsGet(k)    { try { return localStorage.getItem(k);    } catch(_) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v);        } catch(_) {} }
function lsRemove(k) { try { localStorage.removeItem(k);        } catch(_) {} }

// ============================================================
