// ============================================================
// HOUSE RULES — settings sub-view (RuleToggles-SettingsModal.md)
// ============================================================
// The "📜 House rules" screen inside the settings modal. The admin toggles
// rules (each toggle goes straight to /update_settings, which queues it for
// the next round, or applies it at once for the live rules: bust vote and
// wild card, shown on top as Quick switches). Players get the same list with
// a Suggest button per rule (services/rule_votes.py): suggestions go to the
// admin's inbox, or straight to a table vote once the table has voted to
// decide rule changes that way.
//
// /state carries only ID lists (state.rules: preset / enabled / effective /
// queued); names, groups and dependencies come from GET /rules_registry,
// fetched once. Kept out of admin-settings.js, which is long enough already.

let _rulesRegistry   = null;   // { groups, rules, presets, byId } once loaded
let _rulesRegistryP  = null;   // in-flight fetch
let _rsExpanded      = null;   // Set of open group IDs; null = pick defaults on next render
let _rsLastSignature = "";

const _PRESET_LABEL = { starter: "Starter", standard: "Standard", full: "Full" };
// Chips on the setup screen and in the settings view. `sips` is the
// simulated average per player per round (3 players, 1 deck, 2 hands each;
// RuleToggles-StarterSet.md §6). Re-measure with
// `python scripts/simulation.py 3 1 --preset <name>` after rule changes.
// Full has none: what it adds over Standard is mostly the between-round
// events, which the simulation doesn't play, so its number would read the
// same as Standard's.
// Each preset has a colour (.preset-<id> in controls.css): Starter grey,
// Standard blue, Full gold, the same as the pitch deck.
const RULE_PRESETS = [
  { id: "starter",  blurb: "Learn the game",     sips: 2.2 },
  { id: "standard", blurb: "All the card rules", sips: 4.3 },
  { id: "full",     blurb: "Everything + events", sips: null },
];

// ---- Setup screen: preset picked before the room starts ----
let setupRulesPreset = "full";

function _presetChipHtml(p, active, attrs) {
  const count = _rulesRegistry ? `${_rulesRegistry.presets[p.id].length} rules` : "";
  const sips  = p.sips ? ` · ≈${p.sips} sips/rnd` : "";
  const meta  = count || sips ? `<span class="preset-chip-sips">${count}${sips}</span>` : "";
  return `<button type="button" class="preset-chip preset-${p.id}${active ? " sel" : ""}" ${attrs}>
    <span class="preset-chip-name"><span class="preset-dot"></span>${_PRESET_LABEL[p.id]}</span>
    <span class="preset-chip-blurb">${p.blurb}</span>${meta}
  </button>`;
}

function renderSetupPresetChips() {
  const box = document.getElementById("rules-preset-setup");
  if (!box) return;
  if (!_rulesRegistry) loadRulesRegistry().then(renderSetupPresetChips).catch(() => {});
  box.innerHTML = RULE_PRESETS.map(p =>
    _presetChipHtml(p, p.id === setupRulesPreset,
                    `data-action="setRulesPresetSetup" data-args='["${p.id}"]'`)).join("");
}

function setRulesPresetSetup(name) {
  if (!_PRESET_LABEL[name]) return;
  setupRulesPreset = name;
  renderSetupPresetChips();
  _renderSetupPresetBtn();
}

// The picker sits folded behind "📜 House rules: Full ▸" (most tables keep
// the default); the button names the current choice either way.
let _setupPresetOpen = false;

function toggleRulesPresetSetup() {
  _setupPresetOpen = !_setupPresetOpen;
  const panel = document.getElementById("rules-preset-setup-panel");
  if (panel) panel.style.display = _setupPresetOpen ? "" : "none";
  _renderSetupPresetBtn();
}

function _renderSetupPresetBtn() {
  const btn = document.getElementById("rules-preset-setup-btn");
  if (btn) btn.textContent = `📜 House rules: ${_PRESET_LABEL[setupRulesPreset]} ${_setupPresetOpen ? "▾" : "▸"}`;
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", renderSetupPresetChips);
else renderSetupPresetChips();

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

// Same as the server: live rules (bust vote, wild card) don't count.
function _rsPresetName(enabled, reg) {
  const fixed = id => !reg.byId[id].live;
  const mine  = [...enabled].filter(fixed);
  for (const [name, ids] of Object.entries(reg.presets)) {
    const theirs = ids.filter(fixed);
    if (theirs.length === mine.length && theirs.every(id => enabled.has(id))) return name;
  }
  return null;
}

// What "Next rule" would turn on, as RuleSet.next_unlock() does: every rule
// at the lowest unlock step that still has one off, plus its off ancestors.
function _rsNextUnlock(enabled, reg) {
  const off = reg.rules.filter(r => r.unlock_step !== null && !enabled.has(r.id));
  if (!off.length) return [];
  const step = Math.min(...off.map(r => r.unlock_step));
  const picked = new Set();
  const stack  = off.filter(r => r.unlock_step === step).map(r => r.id);
  while (stack.length) {
    const id = stack.pop();
    if (picked.has(id) || enabled.has(id)) continue;
    picked.add(id);
    stack.push(...reg.byId[id].depends_on);
  }
  return reg.rules.filter(r => picked.has(r.id));
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
  const badge = document.getElementById("settings-rules-badge");
  if (badge) {
    const n = myRole === ROLE.ADMIN ? ((state.rule_votes || {}).suggestion_count || 0) : 0;
    badge.style.display = n ? "inline-block" : "none";
    badge.textContent   = n;
  }
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
  const rv = state.rule_votes || {};
  const signature = JSON.stringify([rules, isAdmin, myRole, [..._rsExpanded].sort(),
                                    rv.voting, rv.suggestions, !!rv.pending]);
  if (signature === _rsLastSignature) return;
  _rsLastSignature = signature;

  const total    = reg.rules.length;
  const liveEff  = new Set(rules.effective);
  let html = `<div class="rs-header">This table plays <strong>${escapeHtml(_rsPresetLabel(rules.preset))}</strong> · ${liveEff.size}/${total} rules on</div>`;
  if (rules.queued) {
    const nextPreset = _rsPresetName(new Set(rules.queued), reg);
    html += `<div class="rs-header rs-header-next">Next round: <strong>${escapeHtml(_rsPresetLabel(nextPreset))}</strong> · ${_rsEffective(new Set(rules.queued), reg).size}/${total} rules on</div>`;
  }

  if (isAdmin) {
    // Presets, then "Next rule". The chip that matches the set being edited
    // is filled; a custom set fills none.
    const targetPreset = _rsPresetName(target, reg);
    html += `<div class="preset-chips rs-presets">` + RULE_PRESETS.map(p =>
      _presetChipHtml(p, p.id === targetPreset, `data-rs-preset="${p.id}"`)).join("") + `</div>`;
    if (!targetPreset) html += `<div class="rs-custom-note">✏️ Custom set</div>`;
    const next = _rsNextUnlock(target, reg);
    if (next.length) {
      html += `<button type="button" class="btn wide rs-next" data-rs-next="1">➕ Next rule: ${escapeHtml(next.map(r => r.name).join(" + "))}</button>`;
    }
  }

  html += _rsQuickSwitchesHtml(reg, isAdmin, live, rv);
  if (isAdmin) html += _rsInboxHtml(reg, rv.suggestions || []);

  reg.groups.forEach(g => {
    // Live rules sit in Quick switches above, not in their groups.
    const rows = reg.rules.filter(r => r.group === g.id && !r.live);
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
      html += `<div class="rs-rows">` + rows.map(r => _rsRowHtml(r, { reg, isAdmin, target, eff, live, rv })).join("") + `</div>`;
    }
    html += `</div>`;
  });

  html += `<div class="rs-footer">`;
  if (isAdmin) {
    const changed = rules.queued
      ? reg.rules.filter(r => !r.live && (target.has(r.id) !== live.has(r.id))).length : 0;
    if (changed) {
      html += `<div class="rs-queued">${changed} change${changed === 1 ? "" : "s"} queued for next round
        <button type="button" class="btn btn-sm" data-rs-discard="1">Undo all</button></div>`;
    }
    html += rv.voting
      ? `<div class="rs-voting">🗳 Players' suggestions go to a table vote.
          <button type="button" class="btn btn-sm" data-rs-voting="false">Turn off</button></div>`
      : `<div class="rs-voting">💡 Players' suggestions come to you.
          <button type="button" class="btn btn-sm" data-rs-voting="true">Let the table vote</button></div>`;
    html += `<div class="modal-note">Rules update when the next round starts. Quick switches change at once. Want fewer sips overall? Try Easy Mode or Drink rate.</div>`;
  } else if (myRole === ROLE.PLAYER) {
    html += rv.voting
      ? `<div class="modal-note">🗳 Rule changes are decided by table vote: tap <strong>Vote</strong> on any rule. A change that passes starts next round.</div>`
      : `<div class="modal-note">💡 Suggestions go to the host.</div>
         <button type="button" class="btn wide rs-vote-btn" data-rs-propose-voting="1"${rv.pending ? " disabled" : ""}>🗳 Vote on new rules</button>`;
  }
  html += `</div>`;

  body.innerHTML = html;
  body.querySelectorAll("input[data-mixed]").forEach(cb => { cb.indeterminate = true; });
}

// The live rules (bust vote, wild card): they change at once, so they sit on
// top instead of inside their groups.
function _rsQuickSwitchesHtml(reg, isAdmin, live, rv) {
  const rows = reg.rules.filter(r => r.live).map(r => {
    const on = live.has(r.id);
    let ctl;
    if (isAdmin) {
      ctl = `<label class="pill-toggle rs-pill"><input type="checkbox" data-rs-rule="${r.id}"${on ? " checked" : ""}><span class="pill-slider"></span></label>`;
    } else {
      ctl = `<span class="rs-state${on ? " on" : ""}">${on ? "ON" : "OFF"}</span>` + _rsSuggestBtn(r, on, rv);
    }
    return `<div class="rs-row">
      <div class="rs-text">
        <div class="rs-name">${escapeHtml(r.name)}</div>
        <div class="rs-summary">${escapeHtml(r.summary)}</div>
      </div>
      <button type="button" class="rs-info" data-rs-info="${escapeHtml(r.doc_anchor)}" title="Read the rule">ⓘ</button>
      ${ctl}
    </div>`;
  }).join("");
  return `<div class="rs-quick"><div class="modal-section-title">⚡ QUICK SWITCHES · CHANGE AT ONCE</div>${rows}</div>`;
}

// Players' suggestions waiting for the admin.
function _rsInboxHtml(reg, suggestions) {
  if (!suggestions.length) return "";
  const rows = suggestions.map((sug, i) => {
    const names = sug.ids.map(id => reg.byId[id].name).join(" + ");
    return `<div class="rs-sug">
      <div class="rs-text"><strong>${escapeHtml(sug.by)}</strong>: switch ${sug.on ? "on" : "off"} ${escapeHtml(names)}</div>
      <button type="button" class="btn btn-sm approve" data-rs-sug="${i}" data-accept="1">✓</button>
      <button type="button" class="btn btn-sm danger" data-rs-sug="${i}" data-accept="0">✗</button>
    </div>`;
  }).join("");
  return `<div class="rs-inbox"><div class="modal-section-title">💡 SUGGESTIONS (${suggestions.length})</div>${rows}</div>`;
}

// A player's Suggest / Vote button for one rule (spectators get none).
function _rsSuggestBtn(r, on, rv) {
  if (myRole !== ROLE.PLAYER) return "";
  const verb = rv.voting ? "Vote" : "Suggest";
  const busy = rv.voting && rv.pending;
  return `<button type="button" class="btn btn-sm rs-suggest" data-rs-suggest="${r.id}" data-on="${on ? 0 : 1}"${busy ? " disabled" : ""}>${verb} ${on ? "off" : "on"}</button>`;
}

function _rsRowHtml(r, { reg, isAdmin, target, eff, live, rv }) {
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
    ctl = _rsSuggestBtn(r, live.has(r.id), rv);
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

async function _rsSend(payload, url = "/update_settings") {
  let state = lastState;
  try {
    const res  = await fetch(url, {
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
    .filter(r => r.group === groupId && r.preset !== "locked" && !r.live).map(r => r.id);
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
  if (e.target.closest("[data-rs-discard]")) { _rsSend({ rules_discard: true }); return; }
  if (e.target.closest("[data-rs-next]")) { _rsSend({ rules_next: true }); return; }
  const voting = e.target.closest("[data-rs-voting]");
  if (voting) { _rsSend({ rule_voting: voting.dataset.rsVoting === "true" }); return; }
  const sug = e.target.closest("[data-rs-sug]");
  if (sug) {
    _rsSend({ index: Number(sug.dataset.rsSug), accept: sug.dataset.accept === "1" }, "/rules/suggestion");
    return;
  }
  const suggest = e.target.closest("[data-rs-suggest]");
  if (suggest) {
    const id = suggest.dataset.rsSuggest, on = suggest.dataset.on === "1";
    const rv = (lastState && lastState.rule_votes) || {};
    const what = `switch ${on ? "on" : "off"} ${_rulesRegistry.byId[id].name}`;
    if (!confirm(rv.voting ? `Start a table vote to ${what}?` : `Suggest to the host: ${what}?`)) return;
    _rsSend({ rule_id: id, on }, "/rules/suggest").then(() => {
      if (!rv.voting) showToast("💡 Suggestion sent to the host.");
    });
    return;
  }
  if (e.target.closest("[data-rs-propose-voting]")) {
    if (!confirm("Ask the table to decide rule changes by vote? If most say yes, players' suggestions go straight to a table vote instead of the host.")) return;
    _rsSend({}, "/rules/propose_voting");
    return;
  }
  const preset = e.target.closest("[data-rs-preset]");
  if (preset) {
    const name = preset.dataset.rsPreset;
    // Switching between presets doesn't ask; replacing a custom set does.
    if (!_rsPresetName(_rsTarget(lastState.rules), _rulesRegistry)
        && !confirm(`Replace your custom rules with ${_PRESET_LABEL[name]}?`)) return;
    _rsSend({ rules_preset: name });
  }
});

document.addEventListener("change", e => {
  const cb = e.target;
  if (!cb.closest || !cb.closest("#rules-settings-body")) return;
  if (cb.dataset.rsRule)  _rsToggleRule(cb.dataset.rsRule, cb.checked);
  if (cb.dataset.rsGroup) _rsToggleGroup(cb.dataset.rsGroup, cb.checked);
});

// ---- "🆕 New rule" toast ----
// Called from applyState with the previous and new state: when the table's
// rules gain something (a queued "Next rule" reaching the round start, say),
// tell everyone. Live toggles (bust vote, wild card) have their own UI.
function noteRuleChanges(prev, next) {
  const before = prev && prev.rules && prev.rules.effective;
  const after  = next && next.rules && next.rules.effective;
  if (!before || !after || !_rulesRegistry) {
    if (after && !_rulesRegistry) loadRulesRegistry().catch(() => {});
    return;
  }
  const had   = new Set(before);
  const added = after.filter(id => !had.has(id) && !_rulesRegistry.byId[id].live)
                     .map(id => _rulesRegistry.byId[id]);
  if (!added.length) return;
  const text = added.length <= 2
    ? `🆕 New rule: ${added.map(r => `${r.name} (${r.summary})`).join(" · ")}`
    : `🆕 ${added.length} new rules are on. See 📜 House rules in ⚙️ Settings.`;
  showToast(text, "info", 6000);
}

// ---- Rule vote modal (table-wide, like the Target Proposal vote) ----
// Called from applyState for every client. One vote at a time: either
// "decide rule changes by vote?" or one suggested rule change. The outcome
// arrives as rule_votes.result and is toasted once per seq.
let _rvModalKey  = null;
let _rvResultSeq = null;   // null until the first state, so joining doesn't replay an old result

function renderRuleVote(state) {
  const rv = (state && state.rule_votes) || {};
  const result = rv.result;
  if (_rvResultSeq === null) _rvResultSeq = result ? result.seq : 0;
  else if (result && result.seq > _rvResultSeq) {
    _rvResultSeq = result.seq;
    showToast(`📜 ${result.text}`, result.passed ? "info" : "error", 5000);
  }

  const pending = rv.pending;
  if (!pending) {
    if (_rvModalKey) { _rvModalKey = null; closeModal("rule-vote-modal-overlay", { useClass: true }); }
    return;
  }
  const key = `${pending.kind}:${pending.proposer}:${pending.ids.join(",")}:${pending.on}`;
  if (_rvModalKey !== key) {
    _rvModalKey = key;
    openModal("rule-vote-modal-overlay", { useClass: true });
  }

  const reg   = _rulesRegistry;
  const names = pending.ids.map(id => (reg && reg.byId[id]) ? reg.byId[id].name : id).join(" + ");
  const live  = reg && pending.ids.some(id => reg.byId[id] && reg.byId[id].live);
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };

  set("rule-vote-modal-title", pending.kind === "enable" ? "🗳 Vote on new rules?" : "📜 Rule vote");
  set("rule-vote-modal-sub", pending.kind === "enable"
    ? `<strong>${escapeHtml(pending.proposer)}</strong> wants the table to decide rule changes by vote. ` +
      `If this passes, anyone can put a rule up for a vote, and a majority changes it without the host.`
    : `<strong>${escapeHtml(pending.proposer)}</strong> wants to switch <strong>${pending.on ? "on" : "off"}</strong> ` +
      `${escapeHtml(names)}${live ? ", starting now." : ", from next round."}`);
  set("rule-vote-modal-tally",
    `Yes: <strong style="color:var(--green)">${pending.yes_count}</strong> &nbsp;·&nbsp; ` +
    `No: <strong style="color:var(--red)">${pending.no_count}</strong> &nbsp;·&nbsp; ` +
    `Needed to pass: ${pending.needed}/${pending.total_voters}`);
  const voted = pending.my_vote !== null && pending.my_vote !== undefined;
  set("rule-vote-modal-btns", (!pending.eligible || voted) ? "" :
    `<button class="btn green wide" data-rule-vote="true">YES</button>` +
    `<button class="btn red wide" data-rule-vote="false">NO</button>`);
  set("rule-vote-modal-status", !pending.eligible
    ? `<span style="color:var(--muted)">Watching: only seated players vote.</span>`
    : voted
    ? `Your vote: <strong style="color:${pending.my_vote ? "var(--green)" : "var(--red)"}">${pending.my_vote ? "YES" : "NO"}</strong> · waiting on the rest of the table…`
    : `<span style="color:var(--muted)">Cast your vote below.</span>`);
  set("rule-vote-modal-timer", pending.seconds_left > 0 ? `⏱ ${pending.seconds_left}s remaining` : "Time up!");
}

document.addEventListener("click", async e => {
  const btn = e.target.closest && e.target.closest("[data-rule-vote]");
  if (!btn) return;
  try {
    const res  = await fetch("/rules/vote", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ room_code: roomCode, client_id: clientId, vote: btn.dataset.ruleVote === "true" }),
    });
    const data = await res.json();
    if (data.ok === false) showToast(data.error || "Could not vote.", "error");
    else applyState(data);
  } catch (_) { showToast("Network error.", "error"); }
});
