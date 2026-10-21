// ============================================================
// RULES MODAL — Rules.md / Rules-Normal.md popup
// ============================================================
// Split out of admin-settings.js. Fetches /rules (?mode=normal for Normal tables)
// and renders it with marked + DOMPurify.

let _rulesCached = {};

// marked doesn't give headings ids, so the Rules.md table-of-contents links
// (written for GitHub: "#1-game-setup") pointed at nothing. Give every heading
// GitHub's slug, mark the TOC list for styling, and tidy "[!NOTE]" callouts.
function _ruleSlug(text) {
  return text.toLowerCase().trim().replace(/[^a-z0-9_\- ]/g, "").replace(/ /g, "-");
}

function _decorateRules(body) {
  const seen = {};
  body.querySelectorAll("h1, h2, h3, h4").forEach(h => {
    const base = _ruleSlug(h.textContent);
    if (!base) return;
    const n = seen[base] = (seen[base] || 0) + 1;
    h.id = n === 1 ? base : `${base}-${n - 1}`;
    if (/^table of contents$/i.test(h.textContent.trim())) {
      const list = h.nextElementSibling;
      if (list && list.tagName === "OL") list.classList.add("rules-toc");
    }
  });
  body.querySelectorAll("blockquote").forEach(q => {
    const p = q.firstElementChild;
    if (p && /^\s*\[!NOTE\]/i.test(p.textContent)) {
      p.innerHTML = p.innerHTML.replace(/\[!NOTE\]\s*(<br\s*\/?>)?/i, "<strong>Note:</strong> ");
    }
  });
}

// In-page links scroll inside the rules popup instead of changing the URL.
document.addEventListener("click", e => {
  const a = e.target.closest && e.target.closest("#rules-body a[href^='#']");
  if (!a) return;
  e.preventDefault();
  const id = decodeURIComponent(a.getAttribute("href").slice(1));
  const target = document.getElementById(id);
  if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
});

async function openRulesModal(full) {
  const body = document.getElementById("rules-body");
  if (!document.getElementById("rules-overlay") || !body) return;
  openModal("rules-overlay", { useClass: true });

  const normal = document.body.classList.contains("no-drinking") && full !== true;
  const key = normal ? "normal" : "full";
  if (!_rulesCached[key]) {
    body.innerHTML = '<span style="color:var(--muted);font-size:13px">Loading…</span>';
    try {
      const res  = await fetch(`/rules?${normal ? "mode=normal&" : ""}_=${Date.now()}`);
      const data = await res.json();
      if (data.ok && typeof marked !== "undefined") {
        _rulesCached[key] = DOMPurify.sanitize(marked.parse(data.content));
      } else if (data.ok) {
        // marked.js not loaded — plain text fallback
        _rulesCached[key] = DOMPurify.sanitize(`<pre style="white-space:pre-wrap;font-size:12px">${data.content}</pre>`);
      } else {
        body.innerHTML = '<span style="color:var(--red)">Could not load rules.</span>';
        return;
      }
    } catch (_) {
      body.innerHTML = '<span style="color:var(--red)">Network error loading rules.</span>';
      return;
    }
  }
  body.innerHTML = _rulesCached[key];
  _decorateRules(body);
  if (normal) {
    const btn = document.createElement("button");
    btn.className = "btn wide";
    btn.textContent = "Show BlackOutJack rules";
    btn.addEventListener("click", () => openRulesModal(true));
    body.appendChild(btn);
  }
}

function closeRulesModal() {
  closeModal("rules-overlay", { useClass: true });
}

function handleRulesBackdropClick(e) {
  if (e.target === document.getElementById("rules-overlay")) {
    closeRulesModal();
  }
}
