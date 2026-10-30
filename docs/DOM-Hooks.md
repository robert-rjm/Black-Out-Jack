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
- `#lobby`, `#lobby-msg`, `#join-code` (`resetToSetup`, the "🏠 Lobby" button, also lives here)
- `#waiting`, `#waiting-code-badge`, `#waiting-player-list`, `#waiting-player-count` (waiting room: `renderWaitingPlayers`, `startWaiting`)

### `static/js/ui/poll.js`
- The `/state` poll loop and visibility re-poll (`startPolling`, `stopPolling`, `fetchState`)
- Connection-lost screen: `#server-disconnect-overlay`, `#server-disconnect-elapsed`, `#server-disconnect-tryagain-btn`

### `static/js/ui/room-qr.js`
- Room QR / invite dialog: `#qr-overlay`, `#qr-card`, `#qr-svg`, `#qr-code-text`, `#qr-url`, `[data-action="openRoomQr"|"copyInviteLink"|"closeRoomQr"]`

### `static/js/ui/tip.js`
- Header/bottom-nav "Tip us" buttons: `#btn-beer-header`, `#btn-beer-nav` (`[data-action="openBeerModal"|"closeBeerModal"|"copyBeerLink"]`). Tapping one opens the `/beer` PayPal redirect in a new tab; `#beer-overlay` (QR from `/beer_qr`, "Open PayPal" link, copy link) shows when the player returns to the game tab, or at once if the new tab was blocked

### `static/js/ui/idle.js`
- Idle watcher (warns before the 15-minute host sleep; seated players only): `#idle-warning-banner`, `#idle-warning-text`, `#idle-urgent-overlay`

### `static/js/ui/setup.js`
- `#setup`, `#setup-sub`, `#setup-room-code` (tap to open the QR dialog), `#header-room` (same)
- `#gametype-row`, `#num-players-row`, `#name-fields`
- `#settings-ref`, `#settings-dig`, `#wager-dig-cell`
- `#start-btn`, `#anim-toggle`, `#anim-lbl-setup`, `#anim-lbl-setup-on`

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

### `static/js/ui/drink-panels.js`
- Bust vote side bet (`BustVotePanel`, `BustGivePanel`):
  - `#bust-vote-modal-overlay`, `#bust-vote-timer-bar`, `#bust-vote-timer-label`
  - `#bust-vote-players-wrap`, `#bust-vote-modal-tally`
  - `#bust-vote-status`, `#bust-vote-status-round`
  - `#bust-give-overlay`, `#bust-give-body`
- Dealer Lottery (Rules.md §5.9; `DealerLotteryEntryPanel`, `DealerLotteryGivePanel`):
  - `#dealer-lottery-modal-overlay`, `#dealer-lottery-players-wrap`, `#dealer-lottery-answered`
  - `#dealer-lottery-timer-bar`, `#dealer-lottery-timer-label`
  - `#dealer-lottery-reveal-overlay`, `#dealer-lottery-reveal-sub`, `#dealer-lottery-reveal-hands`
  - `#dealer-lottery-reveal-payout`, `#dealer-lottery-reveal-close-btn`
  - `#dealer-lottery-give-overlay`, `#dealer-lottery-give-body`
- Targeted Drinking perfect-graduation handout (`TargetedDrinkingGivePanel`):
  `#targeted-drinking-give-overlay`, `#targeted-drinking-give-body`
- Normal-mode buy-in handout (`BuyinGivePanel`): `#buyin-give-overlay`, `#buyin-give-body`
- Player toasts: `#player-toast`

### `static/js/ui/seats.js`
- Registration and role management (join overlay, host approval banner, seat transfers, spectate):
  - `#register-overlay`, `#register-seats`, `#register-error`
  - `#register-pending`, `#register-denied`, `#pending-reg-banner`
- Local seat switcher (multi-seat device):
  - `#local-seat-switcher`, `#local-seat-active`, `#local-seat-picker`, `#add-local-seat-row`

### `static/js/ui/bets.js`
- Normal-mode stake panel (stake window after Deal): `#dig-bet-panel` and its per-player stepper rows

### `static/js/ui/admin.js`
- Bust vote (the vote itself is in `drink-panels.js`; the on/off switch is a Quick switch in `rules-settings.js`):
  - `#player-vote-display`
- Honor prompt and strategy suggest:
  - `#honor-split-overlay`, `#honor-no-btn`
  - `#suggest-picker`, `#suggest-banner`, `#suggest-text`
  - `#suggest-toggle-row`, `#suggest-toggle-btn`
- Digital panel controls (also read by `table.js`):
  - `#dig-predeal-panel`, `#dig-play-content`, `#dig-play-role-hint`
  - `#dig-drinks-dealer-actions`, `#dig-drinks-waiting`
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
    total sips drunk across the whole subgame run, plus the same
    correct/wrong counts and dealer bust rate as the live stats panel)
  - `#td-stats-panel` (`#td-stats-dealer-bust`, `#td-stats-targets`) --
    live statistics table (correct/wrong calls per target, dealer bust
    rate this run), visible through vote/waiting/reveal, hidden only
    during the summary phase (which shows its own final version instead)

### `static/js/ui/admin-settings.js`
- Drink Rate Mode (Multiplayer.md, Drink Rate Mode):
  - Settings button: `[data-action="openDrinkRateModal"]`; seat badge `.seat-rate-badge`
  - `#drink-rate-overlay`, `#drink-rate-card`, `#drink-rate-mine` (one `.drink-rate-row[data-seat]` per seat, plus an `__all__` Everyone row for the admin; each row has a `select` and a `[data-drink-rate-go]` button whose `data-mode` is `set` or `propose`; a non-admin's `propose` button reads "Request")
  - Late-joiner boost modal: `#late-join-overlay`, `#late-join-modal`, `#late-join-sub`, `#late-join-btns`, `#late-join-note`, `[data-late-join-take]`, `[data-late-join-dismiss]`
  - Vote modal: `#drink-rate-vote-overlay`, `#drink-rate-vote-modal`, `#drink-rate-vote-title`, `#drink-rate-vote-sub`, `#drink-rate-vote-tally`, `#drink-rate-vote-btns`, `#drink-rate-vote-status`, `#drink-rate-vote-timer`, `[data-drink-rate-vote]`
- Normal-mode money overview (Round tab): `#dig-money-overview` (`.money-table`, `.money-head`, `.money-foot`)
- Admin-AFK vote (Multiplayer.md, AFK handling):
  - `#admin-afk-banner` (holds the Start AFK vote button while the game is waiting on the admin)
  - `#admin-afk-modal-overlay`, `#admin-afk-modal`, `#admin-afk-modal-title`, `#admin-afk-modal-sub`
  - `#admin-afk-modal-tally`, `#admin-afk-modal-btns`, `#admin-afk-modal-status`, `#admin-afk-modal-timer`
  - `[data-admin-afk-open]`, `[data-admin-afk-vote]`
- Kick / player management modal:
  - `#kick-overlay`, `#kick-card`, `#kick-list`
  - `#kick-vote-banner`
  - `#kicked-players-section`
  - `#transfer-admin-section`, `#transfer-admin-list`
  - `#pending-reg-modal-section`, `#denied-reg-section`, `#rejoin-requests-section`
  - `#targeted-drinking-admin-section` (admin start/cancel controls, created
    dynamically like the sections above it)
- Game settings panel (inside kick modal):
  - `#game-settings-section`, `#queued-settings-banner`, `#queued-settings-list`
  - `#setting-wager`, `#setting-num-hands`, `#setting-num-decks`, `#setting-decks-row`
  - `#setting-rotate-every`, `#setting-add-name`, `#setting-remove-name`, `#setting-add-npc`
- Settings toggles (inside kick modal):
  - `#anim-toggle-modal`
  - `#strategy-hint-toggle-modal`
  - `#easy-mode-toggle-modal`, `#easy-mode-lbl-modal`, `#easy-mode-lbl-modal-on`
  - `#god-mode-toggle-modal`, `#god-mode-lbl-off`, `#god-mode-lbl-on`

### Comeback handout (`static/js/ui/drink-panels.js` `LHandoutGivePanel`)
- `#l-handout-give-overlay`, `#l-handout-give-card`, `#l-handout-give-body` (`.lgp-give-btn` with `data-giver` / `data-recipient`; empty recipient = keep), `.lgp-timer`
- Seat badge `.seat-l-badge` (one per player in `state.l_badge_holders`)

### `static/js/ui/rules-settings.js`
- House rules sub-view (inside the settings modal, RuleToggles-SettingsModal.md):
  - Button `[data-action="showSettingsSubview"][data-args='["rules"]']`, label `#settings-rules-sub`, queued dot `#settings-rules-queued-dot`
  - `#settings-rules-view`, `#rules-settings-body` (built from `GET /rules_registry` and `state.rules`)
  - Groups `.rs-group` (`[data-rs-expand]` header, `input[data-rs-group]` tri-state toggle), rows `.rs-row` (`input[data-rs-rule]`, `[data-rs-info]` opens the Rules popup at the rule's section)
  - Footer `.rs-footer`, `.rs-queued`, `[data-rs-discard]` (Undo all)
  - Preset chips `.preset-chips.rs-presets` (`[data-rs-preset]`), `.rs-custom-note`, Next rule `[data-rs-next]`
  - Quick switches `.rs-quick` (live rules), admin inbox `.rs-inbox` (`[data-rs-sug]` + `data-accept`), suggestion badge `#settings-rules-badge`
  - Player controls: `[data-rs-suggest]` (Suggest / Vote button, `data-on`), `[data-rs-propose-voting]` (🗳 Vote on new rules); admin `[data-rs-voting]`
- Rule vote modal: `#rule-vote-modal-overlay`, `#rule-vote-modal`, `#rule-vote-modal-title`, `#rule-vote-modal-sub`, `#rule-vote-modal-tally`, `#rule-vote-modal-btns` (`[data-rule-vote]`), `#rule-vote-modal-status`, `#rule-vote-modal-timer`
- Setup screen preset picker: `#rules-preset-setup-field`, `#rules-preset-setup` (`.preset-chip`, `[data-action="setRulesPresetSetup"]`)

### `static/js/ui/rules.js`
- Rules modal (`/rules`, `?mode=normal` for Normal tables): `#rules-overlay`, `#rules-body`
- House rules marks (drinking tables): `.rules-house-banner`, `#rules-active-only-toggle` (adds `.active-only` to `#rules-body`), `.rule-off`, `.rules-section-off`, `.rule-off-badge`

### `static/js/ui/summary.js`
- Summary modal: `#summary-overlay`, `#summary-meta`, `#summary-body`
- `#auto-export-row`, `#auto-export-toggle` (auto-export-decisions-every-10-rounds opt-in, only rendered for the admin when playing under one of the mined-profile names)
- Drink CSV / decision-log downloads (`exportDrinkCSV`, `exportDecisionLog`)

### `static/js/ui/recap-pdf.js`
- Summary modal "📊 Download Recap (PDF)" button: `[data-action="exportRecapAndClose"]` (wrapper in `bootstrap.js`) → `exportRecapPdf()`; builds the PDF in a temporary off-screen `<iframe>` it removes afterwards

### `static/js/ui/log.js`
- Header and tabs:
  - `#header-title`, `#header-sub`, `#header-room`
  - `#ref-tabs`, `#dig-tabs`
- Peeked card display:
  - `#peeked-card-wrap`, `#peeked-card-display`

## Rule of thumb

If a selector is listed above, keep behavior changes in the owning module. New click/change/enter handlers should be wired with `data-*` attributes and delegated through `bootstrap.js`.
