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

// House rules (RuleToggles-SettingsModal.md §7): mark what this table has
// switched off. Each rule has an <a id="ace-hearts-player"> anchor in
// Rules.md; its row or paragraph gets an "OFF AT THIS TABLE" badge. A whole
// section (the rule's doc_anchor heading) is only muted when every rule in
// it is off. A banner on top names the preset and holds the "show active
// rules only" switch.
function _ruleAnchorId(ruleId) { return ruleId.replace(/\./g, "-"); }

const _OFF_BADGE = '<span class="rule-off-badge">OFF AT THIS TABLE</span>';

function _muteSection(heading) {
  heading.classList.add("rules-section-off");
  heading.insertAdjacentHTML("beforeend", " " + _OFF_BADGE);
  const level = Number(heading.tagName[1]);
  for (let el = heading.nextElementSibling; el; el = el.nextElementSibling) {
    if (/^H[1-6]$/.test(el.tagName) && Number(el.tagName[1]) <= level) break;
    el.classList.add("rules-section-off");
  }
}

function _markHouseRules(body, state, reg) {
  const effective = new Set(state.rules.effective);
  const off = reg.rules.filter(r => !effective.has(r.id));

  const byAnchor = {};
  reg.rules.forEach(r => { (byAnchor[r.doc_anchor] = byAnchor[r.doc_anchor] || []).push(r); });
  Object.entries(byAnchor).forEach(([anchor, rules]) => {
    if (!rules.every(r => !effective.has(r.id))) return;
    const h = body.querySelector(`[id="${anchor}"]`);
    if (h && !h.classList.contains("rules-section-off")) _muteSection(h);
  });

  off.forEach(r => {
    const a = body.querySelector(`[id="${_ruleAnchorId(r.id)}"]`);
    if (!a) return;
    const host = a.closest("tr, p, li, h2, h3, h4") || a;
    if (host.classList.contains("rule-off") || host.classList.contains("rules-section-off")) return;
    host.classList.add("rule-off");
    const cell = host.tagName === "TR" ? host.firstElementChild : host;
    cell.insertAdjacentHTML("beforeend", " " + _OFF_BADGE);
  });

  const preset = state.rules.preset ? _PRESET_LABEL[state.rules.preset] : "a custom set";
  const banner = document.createElement("div");
  banner.className = "rules-house-banner";
  banner.innerHTML = `This table plays <strong>${escapeHtml(preset)}</strong> (${effective.size}/${reg.rules.length} rules).`
    + (off.length ? ` Rules marked OFF don't apply.
      <label class="rules-active-only"><input type="checkbox" id="rules-active-only-toggle"> Show active rules only</label>` : "");
  body.insertBefore(banner, body.firstChild);
  const cb = banner.querySelector("#rules-active-only-toggle");
  if (cb) {
    cb.checked = body.classList.contains("active-only");
    cb.addEventListener("change", () => body.classList.toggle("active-only", cb.checked));
  }
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
  body.classList.remove("active-only");
  // Badges only make sense for the drinking rules of a drinking table.
  if (key === "full" && lastState && lastState.drinking_mode !== false && lastState.rules) {
    try { _markHouseRules(body, lastState, await loadRulesRegistry()); } catch (_) {}
  }
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
