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
  - `#left-col`, `#dealer-panel`, `#sip-ticker`
  - `#btn-admin-nav`, `#btn-admin-players`
- Digital game panels:
  - `#dig-predeal-panel`, `#dig-play-content`, `#dig-play-hands`
  - `#dig-round-notices`, `#dig-drinks-progress`
  - `#dig-drinks-panel`, `#dig-drinks-tab`, `#dig-drinks-agg`, `#dig-drinks-detail`, `#dig-drinks-none`
  - `#rank-grid`, `#suit-grid`
- Toast and milestone nodes:
  - `#dealer-toast`, `#player-toast`, `#switch-toast`, `#milestone-toast`
  - `#milestone-modal-*`, `#ms-waiting-banner`, `#ms-drink-toast`
- Spectator / rejoin:
  - `#spectator-rejoin-banner`, `#rejoin-req-btn`
- Bank run overlay:
  - `#bank-run-overlay`, `#bank-run-player-name`
- Peek card (display managed by `log.js`):
  - `#btn-peek`
- Shared with `admin.js`: `#player-vote-display`, `#honor-split-overlay`, `#honor-no-btn`

### `static/js/ui/admin.js`
- Registration and role management:
  - `#register-overlay`, `#register-seats`, `#register-error`
  - `#register-pending`, `#register-denied`, `#pending-reg-banner`
- Bust vote side bet:
  - `#bust-vote-modal-overlay`, `#bust-vote-timer-bar`, `#bust-vote-timer-label`
  - `#bust-vote-players-wrap`, `#bust-vote-modal-tally`
  - `#bust-vote-status`, `#bust-vote-status-round`
  - `#bust-vote-toggle-modal`, `#bust-vote-lbl-modal`, `#bust-vote-lbl-modal-on`
  - `#bust-give-overlay`, `#bust-give-body`
  - `#player-vote-display`
- Honor prompt and strategy suggest:
  - `#honor-split-overlay`, `#honor-no-btn`
  - `#suggest-picker`, `#suggest-banner`, `#suggest-text`
  - `#suggest-toggle-row`, `#suggest-toggle-btn`
- Local seat switcher (admin multi-seat):
  - `#local-seat-switcher`, `#local-seat-active`, `#local-seat-picker`, `#add-local-seat-row`
- Digital panel controls (also read by `table.js`):
  - `#dig-predeal-panel`, `#dig-play-content`, `#dig-play-role-hint`
  - `#dig-drinks-dealer-actions`, `#dig-drinks-waiting`
- Dealer Lottery (Rules.md §5.9):
  - `#dealer-lottery-modal-overlay`, `#dealer-lottery-players-wrap`, `#dealer-lottery-answered`
  - `#dealer-lottery-timer-bar`, `#dealer-lottery-timer-label`
  - `#dealer-lottery-reveal-overlay`, `#dealer-lottery-reveal-sub`, `#dealer-lottery-reveal-hands`
  - `#dealer-lottery-reveal-payout`, `#dealer-lottery-reveal-close-btn`
  - `#dealer-lottery-give-overlay`, `#dealer-lottery-give-body`
- Targeted Drinking Mode (Rules.md §5.10) -- vote, reveal, and the
  end-of-subgame recap are one continuous modal/card
  (`#targeted-drinking-modal-overlay` / `.td-modal-card`), never separate
  overlays that close and reopen:
  - `#td-close-btn` (top-corner ✕ -- ends the subgame for admin after a
    confirm() prompt, dismisses the local view for anyone else)
  - `#td-vote-phase`, `#td-modal-sub`, `#td-players-wrap` (also reused,
    with a filler message, for the "waiting for next mini-round" state)
  - `#td-timer-bar`, `#td-timer-label`
  - `#td-status-banner` -- shown while the current normal round is still
    live (before the first mini-round of a subgame can even open), and
    again once it's ended but awaiting a `[data-td-start]` "Start
    Targeting Now" tap (any registered player, not admin-only); also
    carries its own admin-only `[data-td-cancel]` ✕ in both states
  - `#td-reveal-phase`, `#targeted-drinking-reveal-sub`,
    `#targeted-drinking-reveal-hand`, `#targeted-drinking-reveal-payout`,
    `#td-continue-btn` (`[data-td-continue]` -- also used by the summary
    phase's Close button)
  - `#td-summary-phase`, `#td-summary-sub`, `#td-summary-list` (per-target
    total sips drunk across the whole subgame run)

### `static/js/ui/admin-settings.js`
- Kick / player management modal:
  - `#kick-overlay`, `#kick-card`, `#kick-list`
  - `#kick-vote-banner`
  - `#kicked-players-section`
  - `#transfer-admin-section`, `#transfer-admin-list`
  - `#pending-reg-modal-section`, `#denied-reg-section`, `#rejoin-requests-section`
  - `#targeted-drinking-admin-section` (admin start/cancel controls, created
    dynamically like the sections above it)
- Rules modal:
  - `#rules-overlay`, `#rules-body`
- Game settings panel (inside kick modal):
  - `#game-settings-section`, `#queued-settings-banner`, `#queued-settings-list`
  - `#setting-wager`, `#setting-num-hands`, `#setting-num-decks`, `#setting-decks-row`
  - `#setting-rotate-every`, `#setting-add-name`, `#setting-remove-name`, `#setting-add-npc`
- Settings toggles (inside kick modal):
  - `#anim-toggle-modal`
  - `#bust-vote-toggle-modal`
  - `#strategy-hint-toggle-modal`
  - `#easy-mode-toggle-modal`, `#easy-mode-lbl-modal`, `#easy-mode-lbl-modal-on`
  - `#god-mode-toggle-modal`, `#god-mode-lbl-off`, `#god-mode-lbl-on`
- Summary modal:
  - `#summary-overlay`, `#summary-meta`, `#summary-body`
  - `#auto-export-row`, `#auto-export-toggle` (auto-export-decisions-every-10-rounds opt-in, only rendered for the admin when playing under one of the mined-profile names)

### `static/js/ui/log.js`
- Header and tabs:
  - `#header-title`, `#header-sub`, `#header-room`
  - `#ref-tabs`, `#dig-tabs`
- Peeked card display:
  - `#peeked-card-wrap`, `#peeked-card-display`

## Rule of thumb

If a selector is listed above, keep behavior changes in the owning module. New click/change/enter handlers should be wired with `data-*` attributes and delegated through `bootstrap.js`.
