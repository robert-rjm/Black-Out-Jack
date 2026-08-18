# Donate to Developers

## Goal
An optional, non-intrusive "support the developers" link across the app's
non-gameplay surfaces. This is a hobby drinking-game project, so the ask
must read as a tip jar, never a paywall. Nothing appears during active
gameplay, and every placement is visible to **all** players (no host-only
or drinking-mode-only gating).

## Status: implemented with a placeholder link

All five placements are live. They currently point at the repo's GitHub
Issues page as a contact route, with the copy
**"🍺 Buy us a beer (contact us via GitHub)"**. When the real donation
account exists, swap that single URL in the five places listed below.

| # | Surface | File | Status |
|---|---------|------|--------|
| 1 | Lobby credits block | `templates/partials/index/_lobby.html` | Done |
| 2 | Session Summary modal | `templates/partials/index/_modals.html` | Done |
| 3 | Terms & Disclaimer footer | `templates/terms.html` | Done |
| 4 | Rules & Cheat Sheet modal | `templates/partials/index/_modals.html` | Done |
| 5 | README "Support this project" | `README.md` | Done |
| 6 | In-game header / bottom nav | n/a | Deliberately skipped |

### What was added

**1. Lobby credits block.** One link inside `.lobby-credits`, after the
Terms link, styled to match the existing GitHub and Terms links. The new
`.lobby-donate-link` class was folded into the existing
`.lobby-github-link, .lobby-terms-link` rule in
`static/css/components/utilities.css` rather than given its own block, so
the three links stay visually identical.

**2. Session Summary modal.** A footer line placed after
`#auto-export-row`, so it reads as a footer rather than a third action
button competing with the two report-download buttons. It deliberately
does **not** carry the `drink-only` class that the session report button
uses, so it shows regardless of drinking mode. This is a static template
addition; `showSessionSummary()` in
`static/js/ui/admin-settings.js` only rewrites `#summary-meta` and
`#summary-body`, so no JS change was needed.

**3. Terms & Disclaimer page.** Added inside `.terms-footer`, below the
existing GitHub link. Uses the footer's existing link styling.

**4. Rules & Cheat Sheet modal.** Note the finding here: **this modal
previously showed no credits at all.** Its `#rules-body` is filled at
runtime by `openRulesModal()`, which fetches `/rules` and renders
`docs/Rules.md` through marked and DOMPurify, so the modal's content was
purely the rules document. The credits and donate footer were added
statically inside `#rules-card`, after `#rules-body`, rather than into
`docs/Rules.md`. That keeps the rules document purely rules and prevents
the credits from being cached into `_rulesCached`.

**5. README.** A `## Support this project` section above `## License`.

**Shared styling.** A `.modal-donate` rule in
`static/css/components/utilities.css` covers both modal footers (11px,
muted color, top border, centered), matching the surrounding footer text.

### Verified
Checked against the running dev server: all links resolve to the correct
URL, the rules modal opens with its new credits footer, the terms footer
shows both links, and the summary modal's donate line sits after the
auto-export row with no `drink-only` class. No console errors.

## Remaining work: choose the payment platform

Requirement: no private info (real name, phone number, address, email)
exposed to donors.

**Recommended: GitHub Sponsors.**
- The repo already lives on GitHub, so the link is contextually natural.
- Publicly it shows only the GitHub username. Identity and tax details
  are verified privately with GitHub and Stripe, never shown to donors.
- No platform fee on GitHub's side for personal accounts. Payouts go via
  Stripe Connect, which needs a bank account entered privately.
- Available to Swiss maintainers.

**TWINT: not recommended.** Personal TWINT is tied to a phone number, so
a public "TWINT me" link means publishing that number. The QR-code and
sticker products that avoid this are business or association offerings
requiring a registered business or club account with a bank, which is
disproportionate for this project.

**Avoid PayPal.me.** The profile page and payment receipts expose the
recipient's real name to donors.

**Optional secondary: Ko-fi or Buy Me a Coffee, configured with Stripe
rather than PayPal.** Useful for donors without a GitHub account; the
public page shows only a display name. Adds a second link to maintain, so
only worth it if GitHub Sponsors alone proves too niche.

> Verify current terms, fee structure, and Swiss availability on each
> platform before committing, since these change over time.

### Open questions
- Who owns the sponsor account? GitHub Sponsors is per-account, but the
  project credits three people (Robert, David & Marko). Options: a GitHub
  **org** sponsor account for the project (cleanest for a shared
  project), or one personal account with an informal split. Needs a
  decision between the three devs.
- Final URL, once the account exists. Swapping it is the only code change
  left.

## Out of scope
- Any in-game surface (header, bottom nav, admin panel).
- Donation tiers, perks, or in-game recognition for donors.
- Splitting received funds between the three developers, which is an
  off-platform arrangement rather than an app concern.
