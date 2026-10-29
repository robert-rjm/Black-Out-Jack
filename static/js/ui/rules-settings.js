// ============================================================
// HOUSE RULES — settings sub-view (RuleToggles-SettingsModal.md)
// ============================================================
// The "📜 House rules" screen inside the settings modal. The admin toggles
// rules (each toggle goes straight to /update_settings, which queues it for
// the next round, or applies it at once for the live rules: bust vote and
// wild card). Everyone else gets the same list read-only.
//
// /state carries only ID lists (state.rules: preset / enabled / effective /
// queued); names, groups and dependencies come from GET /rules_registry,
// fetched once. Kept out of admin-settings.js, which is long enough already.

let _rulesRegistry   = null;   // { groups, rules, presets, byId } once loaded
let _rulesRegistryP  = null;   // in-flight fetch
let _rsExpanded      = null;   // Set of open group IDs; null = pick defaults on next render
let _rsLastSignature = "";

const _PRESET_LABEL = { starter: "Starter", standard: "Standard", full: "Full" };

function loadRulesRegistry() {
  if (_rulesRegistry) return Promise.resolve(_rulesRegistry);
  if (!_rulesRegistryP) {
    _rulesRegistryP = fetch("/rules_registry")
      .then(r => r.json())
      .then(data => {
        if (!data.ok) throw new Error("registry");
        data.byId = {};
        data.rules.forEach(r => { data.byId[r.id] = r; });
        _rulesRegistry = data;
        return data;
      })
      .catch(err => { _rulesRegistryP = null; throw err; });
  }
  return _rulesRegistryP;
}

// Whether a rule is in effect at this table right now. True when the state
// has no rules block yet, so nothing disappears before the first poll.
function rulesOn(id) {
  const eff = lastState && lastState.rules && lastState.rules.effective;
  return !eff || eff.includes(id);
}

// Dependency resolution, same as RuleSet.on() on the server.
function _rsEffective(enabled, reg) {
  const memo = {};
  const eff = id => {
    if (!(id in memo)) {
      const r = reg.byId[id];
      memo[id] = enabled.has(id) && !!r && r.depends_on.every(eff);
    }
    return memo[id];
  };
  return new Set(reg.rules.filter(r => eff(r.id)).map(r => r.id));
}

function _rsPresetName(enabled, reg) {
  for (const [name, ids] of Object.entries(reg.presets)) {
    if (ids.length === enabled.size && ids.every(id => enabled.has(id))) return name;
  }
  return null;
}

function _rsPresetLabel(preset) {
  return preset ? _PRESET_LABEL[preset] || preset : "Custom";
}

// The set the admin is editing: the queued target if there is one, else
// the live set.
function _rsTarget(rules) {
  return new Set(rules.queued || rules.enabled);
}

// "📜 Rules: +A♥ to a player, −Dealer Lottery" for the queued banner, or ""
// when no rule change is queued.
function rulesQueuedSummary(state) {
  const rules = state && state.rules;
  if (!rules || !rules.queued) return "";
  if (!_rulesRegistry) { loadRulesRegistry().catch(() => {}); return "📜 Rules changes"; }
  const reg  = _rulesRegistry;
  const live = new Set(rules.effective);
  const next = _rsEffective(new Set(rules.queued), reg);
  const on   = reg.rules.filter(r => next.has(r.id) && !live.has(r.id)).map(r => r.name);
  const off  = reg.rules.filter(r => live.has(r.id) && !next.has(r.id)).map(r => r.name);
  const fmt  = (sign, names) => names.length > 3 ? `${sign}${names.length} rules` : names.map(n => sign + n).join(", ");
  const parts = [];
  if (on.length)  parts.push(fmt("+", on));
  if (off.length) parts.push(fmt("−", off));
  return parts.length ? `📜 Rules: ${parts.join(", ")}` : "📜 Rules: switch settings only";
}

// Button label in the main settings view: "Standard · 31/44".
function renderRulesSettingsButton(state) {
  const sub = document.getElementById("settings-rules-sub");
  if (!sub) return;
  const rules = state && state.rules;
  if (!rules || !_rulesRegistry) {
    sub.textContent = "";
    if (rules) loadRulesRegistry().then(() => renderRulesSettingsButton(lastState)).catch(() => {});
    return;
  }
  sub.textContent = `${_rsPresetLabel(rules.preset)} · ${rules.effective.length}/${_rulesRegistry.rules.length}`;
  const dot = document.getElementById("settings-rules-queued-dot");
  if (dot) dot.style.display = rules.queued ? "inline-block" : "none";
}

function resetRulesSettingsView() {
  _rsExpanded = null;
  _rsLastSignature = "";
}

function renderRulesSettings(state) {
  const body = document.getElementById("rules-settings-body");
  if (!body || !state || !state.rules) return;
  if (!_rulesRegistry) {
    body.innerHTML = '<p class="modal-note">Loading rules…</p>';
    loadRulesRegistry()
      .then(() => renderRulesSettings(lastState))
      .catch(() => { body.innerHTML = '<p class="modal-note">Could not load the rules.</p>'; });
    return;
  }
  const reg     = _rulesRegistry;
  const isAdmin = myRole === ROLE.ADMIN;
  const rules   = state.rules;
  const live    = new Set(rules.enabled);
  const target  = isAdmin ? _rsTarget(rules) : live;
  const eff     = _rsEffective(target, reg);

  if (_rsExpanded === null) {
    // Groups with something switched off start open; the rest stay
    // collapsed so the first view is short on mobile.
    _rsExpanded = new Set(reg.groups
      .filter(g => reg.rules.some(r => r.group === g.id && r.preset !== "locked" && !eff.has(r.id)))
      .map(g => g.id));
  }

  // Polls re-call this every tick; only rebuild when something changed, or
  // a tap mid-rebuild gets lost.
  const signature = JSON.stringify([rules, isAdmin, [..._rsExpanded].sort()]);
  if (signature === _rsLastSignature) return;
  _rsLastSignature = signature;

  const total    = reg.rules.length;
  const liveEff  = new Set(rules.effective);
  let html = `<div class="rs-header">This table plays <strong>${escapeHtml(_rsPresetLabel(rules.preset))}</strong> · ${liveEff.size}/${total} rules on</div>`;
  if (rules.queued) {
    const nextPreset = _rsPresetName(new Set(rules.queued), reg);
    html += `<div class="rs-header rs-header-next">Next round: <strong>${escapeHtml(_rsPresetLabel(nextPreset))}</strong> · ${_rsEffective(new Set(rules.queued), reg).size}/${total} rules on</div>`;
  }

  reg.groups.forEach(g => {
    const rows = reg.rules.filter(r => r.group === g.id);
    if (!rows.length) return;
    const locked     = rows.every(r => r.preset === "locked");
    const toggleable = rows.filter(r => r.preset !== "locked");
    const onCount    = rows.filter(r => eff.has(r.id)).length;
    const open       = _rsExpanded.has(g.id);
    let groupCtl;
    if (locked) {
      groupCtl = `<span class="rs-lock" title="This is the game itself.">🔒</span>`;
    } else if (isAdmin) {
      const allOn  = toggleable.every(r => target.has(r.id));
      const allOff = toggleable.every(r => !target.has(r.id));
      groupCtl = `<label class="pill-toggle rs-pill"><input type="checkbox" data-rs-group="${g.id}"${allOn ? " checked" : ""}${!allOn && !allOff ? " data-mixed=\"1\"" : ""}><span class="pill-slider"></span></label>`;
    } else {
      groupCtl = "";
    }
    html += `<div class="rs-group${open ? " open" : ""}">
      <div class="rs-group-head">
        <button type="button" class="rs-group-btn" data-rs-expand="${g.id}">
          <span class="rs-caret">${open ? "▾" : "▸"}</span>
          <span class="rs-group-label">${escapeHtml(g.label)}</span>
          <span class="rs-count">${onCount}/${rows.length}</span>
        </button>
        ${groupCtl}
      </div>`;
    if (open) {
      html += `<div class="rs-rows">` + rows.map(r => _rsRowHtml(r, { reg, isAdmin, target, eff, live })).join("") + `</div>`;
    }
    html += `</div>`;
  });

  if (isAdmin) {
    const changed = rules.queued
      ? reg.rules.filter(r => !r.live && (target.has(r.id) !== live.has(r.id))).length : 0;
    html += `<div class="rs-footer">`;
    if (changed) {
      html += `<div class="rs-queued">${changed} change${changed === 1 ? "" : "s"} queued for next round
        <button type="button" class="btn btn-sm" data-rs-discard="1">Undo all</button></div>`;
    }
    html += `<div class="modal-note">Rules update when the next round starts. ⚡ rules change at once. Want fewer sips overall? Try Easy Mode or Drink rate.</div></div>`;
  }

  body.innerHTML = html;
  body.querySelectorAll("input[data-mixed]").forEach(cb => { cb.indeterminate = true; });
}

function _rsRowHtml(r, { reg, isAdmin, target, eff, live }) {
  const locked  = r.preset === "locked";
  const isOn    = eff.has(r.id);
  const waiting = target.has(r.id) && !isOn;
  const missing = r.depends_on.filter(d => !eff.has(d)).map(d => reg.byId[d].name);
  const queued  = isAdmin && !r.live && target.has(r.id) !== live.has(r.id);
  const badges  = [];
  if (r.live) badges.push(`<span class="rs-badge" title="Changes at once">⚡</span>`);
  if (r.halvable) badges.push(`<span class="rs-badge" title="Halved in Easy Mode">½</span>`);
  if (queued) badges.push(`<span class="rs-badge rs-badge-next">next round</span>`);
  let note = "";
  if (missing.length && (target.has(r.id) || !isAdmin)) note = `<div class="rs-note">↳ requires ${escapeHtml(missing.join(", "))}</div>`;
  else if (!isAdmin && !isOn && !locked) note = `<div class="rs-note">Off at this table</div>`;
  let ctl;
  if (locked) {
    ctl = `<span class="rs-lock" title="This is the game itself. Use Normal mode to play without drinking.">🔒</span>`;
  } else if (isAdmin) {
    ctl = `<label class="pill-toggle rs-pill"><input type="checkbox" data-rs-rule="${r.id}"${target.has(r.id) ? " checked" : ""}><span class="pill-slider"></span></label>`;
  } else {
    ctl = "";
  }
  const muted = !isOn || waiting;
  return `<div class="rs-row${muted ? " rs-off" : ""}">
    <div class="rs-text">
      <div class="rs-name">${escapeHtml(r.name)} ${badges.join("")}</div>
      <div class="rs-summary">${escapeHtml(r.summary)}</div>
      ${note}
    </div>
    <button type="button" class="rs-info" data-rs-info="${escapeHtml(r.doc_anchor)}" title="Read the rule">ⓘ</button>
    ${ctl}
  </div>`;
}

async function _rsSend(payload) {
  let state = lastState;
  try {
    const res  = await fetch("/update_settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, ...payload }),
    });
    const data = await res.json();
    if (data.ok === false) alert(data.error || "Could not change the rules.");
    else { applyState(data); state = data; }
  } catch (_) { alert("Network error."); }
  _rsLastSignature = "";   // redraw even if the server said no, so toggles snap back
  if (state) {
    renderRulesSettings(state);
    renderRulesSettingsButton(state);
    _renderQueuedBanner(state.queued_settings || {});
  }
}

function _rsToggleRule(id, on) {
  const reg = _rulesRegistry;
  if (!on) return _rsSend({ rules_off: [id] });
  // Turning a child on while a parent is off: offer to turn both on.
  const target = _rsTarget(lastState.rules);
  const eff    = _rsEffective(target, reg);
  const offParents = [];
  const walk = rid => reg.byId[rid].depends_on.forEach(d => {
    if (!eff.has(d) && !offParents.includes(d)) { offParents.push(d); walk(d); }
  });
  walk(id);
  const needOn = offParents.filter(d => !target.has(d));
  if (needOn.length) {
    const names = needOn.map(d => reg.byId[d].name).join(", ");
    if (!confirm(`${reg.byId[id].name} needs ${names}. Turn on both?`)) {
      _rsLastSignature = "";
      return renderRulesSettings(lastState);
    }
  }
  return _rsSend({ rules_on: [id, ...needOn] });
}

function _rsToggleGroup(groupId, on) {
  const ids = _rulesRegistry.rules
    .filter(r => r.group === groupId && r.preset !== "locked").map(r => r.id);
  return _rsSend(on ? { rules_on: ids } : { rules_off: ids });
}

async function _rsOpenRule(anchor) {
  await openRulesModal(true);
  const el = anchor && document.getElementById(anchor);
  if (el) el.scrollIntoView({ block: "start" });
}

document.addEventListener("click", e => {
  const body = e.target.closest && e.target.closest("#rules-settings-body");
  if (!body) return;
  const expand = e.target.closest("[data-rs-expand]");
  if (expand) {
    const id = expand.dataset.rsExpand;
    if (_rsExpanded.has(id)) _rsExpanded.delete(id); else _rsExpanded.add(id);
    renderRulesSettings(lastState);
    return;
  }
  const info = e.target.closest("[data-rs-info]");
  if (info) { _rsOpenRule(info.dataset.rsInfo); return; }
  if (e.target.closest("[data-rs-discard]")) _rsSend({ rules_discard: true });
});

document.addEventListener("change", e => {
  const cb = e.target;
  if (!cb.closest || !cb.closest("#rules-settings-body")) return;
  if (cb.dataset.rsRule)  _rsToggleRule(cb.dataset.rsRule, cb.checked);
  if (cb.dataset.rsGroup) _rsToggleGroup(cb.dataset.rsGroup, cb.checked);
});
