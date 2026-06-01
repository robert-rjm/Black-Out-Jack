# DOM Hooks Contract

This document defines selector ownership for the web UI modules and the shared event hooks used by `templates/index.html` partials.

## Shared hooks

- `data-action`: click action dispatched by `static/js/ui/bootstrap.js`
- `data-args`: JSON array arguments for `data-action`
- `data-enter-action`: action fired on Enter key
- `data-change-action`: action fired on input change
- `data-backdrop-action`: action fired only when backdrop itself is clicked
- `data-stop-propagation="true"`: prevents clicks from bubbling to backdrop handlers

## Module ownership

### `static/js/ui/lobby.js`
- `#age-gate`, `#age-gate-msg`
- `#lobby`, `#lobby-msg`, `#join-code`
- `#waiting`, `#waiting-code-badge`
- Polling + visibility sync (`startPolling`, `stopPolling`)

### `static/js/ui/setup.js`
- `#setup`, `#setup-sub`, `#setup-room-code`
- `#gametype-row`, `#num-players-row`, `#name-fields`
- `#settings-ref`, `#settings-dig`, `#wager-dig-cell`
- `#start-btn`, `#anim-toggle`, `#anim-lbl-setup`, `#anim-lbl-setup-on`
- Last-round modal nodes: `#last-round-overlay`, `#last-round-modal-body`

### `static/js/ui/table.js`
- Core table and panel state nodes:
  - `#ref-panel`, `#dig-panel`
  - `#deal-*`, `#result-*`, `#action-*`
  - `#pane-*` and digital action rows
  - `#left-col`, `#dealer-panel`, `#log`, `#sip-ticker`
- Toast and milestone nodes:
  - `#dealer-toast`, `#player-toast`, `#switch-toast`, `#milestone-toast`
  - `#milestone-modal-*`, `#ms-waiting-banner`, `#ms-drink-toast`

### `static/js/ui/admin.js`
- Registration and role management:
  - `#register-overlay`, `#register-seats`, `#register-error`
- Rules modal:
  - `#rules-overlay`, `#rules-card`, `#rules-body`, `#rules-close-btn`
- Settings modal:
  - `#kick-overlay`, `#kick-card`, `#kick-list`, `#transfer-admin-*`
  - `#game-settings-section`, `#queued-settings-banner`, `#queued-settings-list`
  - `#setting-*`, `#anim-toggle-modal`, `#anim-lbl-modal`, `#anim-lbl-modal-on`
- Summary modal:
  - `#summary-overlay`, `#summary-card`, `#summary-meta`, `#summary-body`

### `static/js/ui/log.js`
- Header and tabs:
  - `#header-title`, `#header-sub`, `#header-room`
  - `#ref-tabs`, `#dig-tabs`

## Rule of thumb

If a selector is listed above, keep behavior changes in the owning module. New click/change/enter handlers should be wired with `data-*` attributes and delegated through `bootstrap.js`.
