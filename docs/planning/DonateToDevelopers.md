# Donate to Developers — Implementation Plan

## Goal
Add an optional, non-intrusive "support the developers" link across the
app's non-gameplay surfaces. This is a hobby drinking-game project — the
ask must read as a tip jar, never a paywall. Nothing appears during
active gameplay, and every placement is visible to **all** players (no
host-only or drinking-mode-only gating).

## Decisions (confirmed)

| # | Surface | Decision |
|---|---------|----------|
| 1 | Lobby credits block | Add |
| 2 | Session Summary modal | Add — next to the report download buttons |
| 3 | Terms & Disclaimer page footer | Add |
| 4 | Rules & Cheat Sheet modal | Add — **currently has no credits at all** |
| 5 | README | Add as "Support this project" |
| 6 | In-game header / bottom nav | **Nothing in game** |
| 7 | Visibility | All players, every placement — no gating |

Copy: **"🍺 Buy us a beer"** in-app (fits the drinking-game branding and
the existing 🍺 icon usage), **"Support this project"** as the README
section heading.

## Payment platform — recommendation

Requirement: no private info (real name, phone number, address, email)
exposed to donors.

**Recommended: GitHub Sponsors.**
- The repo already lives on GitHub, so the link is contextually natural.
- Publicly it shows only the GitHub username — identity and tax details
  are verified privately with GitHub/Stripe and never shown to donors.
- No platform fee on GitHub's side for personal accounts; payouts go via
  Stripe Connect (needs a bank account, entered privately).
- Available to Swiss maintainers.

**TWINT — not recommended.** Personal TWINT is tied to a phone number,
so a public "TWINT me" link means publishing that number. The
QR-code/sticker products that avoid this are business/association
offerings requiring a registered business or club account with a bank —
disproportionate for this project.

**Also avoid PayPal.me** — the profile page and payment receipts expose
the recipient's real name to donors.

**Optional secondary: Ko-fi or Buy Me a Coffee, configured with Stripe
(not PayPal).** Useful for donors without a GitHub account; the public
page shows only a display name. Adds a second link to maintain, so only
worth it if GitHub Sponsors alone proves too niche.

> Verify current terms, fee structure, and Swiss availability on each
> platform before committing — these change over time.

### Open before implementation
- Who owns the sponsor account? GitHub Sponsors is per-account, but the
  project credits three people (Robert, David & Marko). Options: a
  GitHub **org** sponsor account for the project (cleanest for a shared
  project), or one personal account with an informal split. Needs a
  decision between the three devs.
- Final URL, once the account exists. Every code change below is blocked
  on having it.

## Implementation steps

Single shared URL, referenced in four places in the app plus the README.

### 1. Lobby credits block
`templates/partials/index/_lobby.html:30-37` — add one `<a>` line inside
`.lobby-credits`, after the GitHub link, styled to match
`.lobby-github-link`. Add a `.lobby-donate-link` rule in the lobby CSS if
it needs to stand out slightly more than the GitHub/Terms links.

### 2. Session Summary modal
`templates/partials/index/_modals.html:356-372` — the modal already ends
with a `.btn-row.summary-actions` holding the two report-download buttons
(`⬇️ Download Session Report`, `⬇️ Export Drinks Log`) and then
`#auto-export-row`. Add the donate link as a small line **after**
`#auto-export-row`, so it reads as a footer rather than a third action
button competing with the downloads.

Important: do **not** copy the `drink-only` class used on the session
report button (`_modals.html:363`) — per decision #7 the donate line
shows regardless of drinking mode. This is a static template addition, so
no change needed in `showSessionSummary()`
(`static/js/ui/admin-settings.js:947`), which only rewrites
`#summary-meta` and `#summary-body`.

### 3. Terms & Disclaimer page
`templates/terms.html:124-129` — add the link inside `.terms-footer`,
below the existing GitHub link.

### 4. Rules & Cheat Sheet modal
`templates/partials/index/_modals.html:18-22`. Note the finding here:
**the rules modal currently shows no credits.** Its `#rules-body` is
filled at runtime by `openRulesModal()`
(`static/js/ui/admin-settings.js:514-540`), which fetches `/rules` and
renders `docs/Rules.md` through marked + DOMPurify — so the modal's
content is purely the rules document.

Add a static credits + donate footer inside `#rules-card`, after
`#rules-body`, mirroring the lobby credits block ("Made by Robert, David
& Marko" + donate link). Do this in the template rather than in
`docs/Rules.md`, so the rules document stays purely rules and the
credits aren't cached into `_rulesCached`.

### 5. README
`README.md` — add a `## Support this project` section (near the bottom,
after the existing content) with one line and the donate link. Optionally
a shields.io badge in the centered badge stack at the top
(`README.md:8-18`) to match the existing PLAY NOW / RULES badges.

## Out of scope
- Any in-game surface (header, bottom nav, admin panel) — decision #6.
- Donation tiers, perks, or in-game recognition for donors.
- Splitting received funds between the three developers (an
  off-platform arrangement, not an app concern).
