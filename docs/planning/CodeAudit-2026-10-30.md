# Code Audit — 30 October 2026

Follow-up to [CodeAudit-2026-10.md](CodeAudit-2026-10.md). Covers the whole
server (`app/`, `engine/`), the frontend (`static/js/ui/`) and the features
added since (house-rule suggestions and table votes, quick switches, the L
badge comeback handout). It also rechecks the open items from the earlier
audit and reviews which planning docs are still needed (Part C).

Branch `update/Rob` at `8366759`.

**Health.** `pytest`: 1030 passed in 57 s. `ruff check .`: 37 errors, mostly
E501 (line too long). One matters: F811 in `tests/app/test_targeted_drinking.py`
(see N12).

**How the findings were checked.** Items marked **Probed** were reproduced
against the real Flask app with the test client (script kept outside the
repo). The others were confirmed by reading the code.

Severity: **High** = breaks the server or the game for everyone · **Medium** =
exploitable by a player or stranger, or wrong game results · **Low** = edge
case, UX or cleanup.

## Summary

| # | Severity | Area | Finding |
|---|---|---|---|
| N1 | High | DoS | Filling the room-code space makes `/create_room` loop forever and freezes the single worker |
| N2 | High | Referee | Blackjack bonus fires twice (old **B1**, still open) |
| N3 | Medium | Security | `/set_bot_personality` reopens the profile path traversal fixed in B2 · Probed |
| N4 | Medium | Auth | Kicked clients can still act (Wild Card, votes, handouts, lottery) · Probed |
| N5 | Medium | Auth | Anyone can delete or take over a reserved room before `/setup` (old **B4**, extended) · Probed |
| N6 | Medium | Security | `X-Forwarded-For` rate-limit bypass, exports need only the room code (old **B3**, still open) |
| N7 | Low | Registration | `my_registration_denied` is always `false` · Probed |
| N8 | Low | Milestone | `/claim_milestone` returns 500 for a spectator · Probed |
| N9 | Low | House rules | Admin inbox accepts suggestions by index, so a stale index can accept the wrong one |
| N10 | Low | House rules | "Vote on new rules" has no cooldown after it fails |
| N11 | Low | Robustness | `/preselect` null dereference, unbounded `hand` keys, no `MAX_CONTENT_LENGTH` |
| N12 | Low | Tests | A duplicate test name hides `test_forfeit_noop_before_expiry` |
| N13 | Low | Cleanup | `_cmd_blackjack` is dead code; 37 ruff errors |

Still open from the earlier audit: **G5**, **G13**, **B5**, **B6–B11** (Part B).

---

## Part A — New findings

### N1 — Room-code exhaustion freezes the server · High

**Issue.** `generate_room_code()` (`app/services/session_store.py:49`) loops
`while True` until it finds a free code. The code space is 22 words × 999
numbers ≈ 22,000 codes. `/create_room` needs no login and has no rate limit,
and an unused reserved room lives for `SESSION_TTL` (12 h). About 22,000 POSTs
fill every code, after which the next `/create_room` never returns. With
`gunicorn --workers 1 --threads 1` that request blocks every room on the server.
Each create also runs `cleanup_stale_sessions()` over all rooms, so the requests
slow down as the store fills.

**Fix.**
- Bound the loop (for example 50 tries), then return "Server busy, try again".
- Rate-limit `/create_room` per IP (reuse the join limiter once N6 is fixed).
- Cap the number of reserved rooms, and cut the TTL for reserved rooms nobody
  joined (12 h → about 30 min).
- Longer term: a bigger code space (B3).

### N2 — Referee Blackjack bonus fires twice · High

Unchanged since **B1**. `engine/referee.py:349` (`action <p> blackjack`) and
`:392` (`result <p> win` on a natural) both append to `_pending_bj_hands`
without checking for duplicates. BLACKJACK followed by WIN makes every other
player drink the bonus twice. Fix and regression test as described in B1:
skip the append when the same `hand` object is already queued.

### N3 — `/set_bot_personality` path traversal · Medium · Probed

**Issue.** The B2 fix only lets plain names (`[A-Za-z0-9_-]{1,32}`) through as a
personality in `/setup`. `/set_bot_personality` (`app/routes/players.py:100`)
stores any string. `load_profile()` (`engine/style_strategy.py:60`) builds
`player_profiles/<name>.json`, so `../../data/x` loads any `.json` file on the
server. The probe stored `'../../data/whatever'` with `ok: true`. A JSON file
that isn't a profile (a list, or a dict without `deviations`) will likely
raise during the bot's turn. Every room creator is admin, so anyone can reach
this route.

**Fix.** Move `_PERSONALITY_RE` into `validators.py` and use it in both routes.
Better: accept only names in `available_profiles()` + `"basic"`. Also check in
`load_profile` that the resolved path stays inside the profiles directory.
Add a test next to `tests/app/test_setup_limits.py`.

### N4 — Kicked clients can still act · Medium · Probed

**Issue.** `/kick` and a passed kick vote set `info["kicked"] = True` but keep
`info["name"]`. Many routes only check `if not client_info.get("name")`, so a
kicked client passes them. The probe had a kicked player press Wild Card
during a round, and it worked. Routes affected:

| Route | File |
|---|---|
| `/wild_card` | `routes/wild_card.py:98` |
| `/cast_bust_vote`, `/give_bust_sip`, `/buyin_handout/give`, `/l_handout/give` | `routes/side_bets.py:111, 188, 258, 290` |
| Dealer Lottery entry and handout | `routes/dealer_lottery.py:52, 110` |
| Targeted Drinking handout and vote | `routes/targeted_drinking.py:51, 96` |
| `/claim_milestone` | `routes/admin.py:258` |
| `/set_hint` | `routes/admin.py:66` |

Once another client claims the freed seat (`/register` skips kicked entries),
two clients control the same seat.

**Fix.** Add one helper, for example `seated_client(session, client_id) ->
(info, names) | error`, that rejects missing, kicked, spectator and pending
clients and returns the client's seat names (`local_names` or `[name]`). Use it
in every player route. `get_client_info` already turns a kicked client into
`role: "kicked"`, so the helper can build on it. Clearing `name` on kick would
also work, but the admin's "undo kick" list reads that name.

### N5 — Reserved rooms: delete and takeover · Medium · Probed

**Issue.** Before `/setup` the room's value is `None`:
- `/delete_room` (`routes/lobby.py:72`) deletes it for any caller (probe: a
  stranger's request returned `ok: true` and the room was gone). Players
  waiting in the lobby lose the room.
- `/setup` lets any caller configure it and become admin (B4).

**Fix.** Store the creator's `client_id` with the reservation in `reserve_room()`
(for example `_room_creator[code]`) and require it in both routes.

### N6 — Rate-limit bypass and open exports · Medium

Unchanged since **B3**. `routes/lobby.py:107` takes the first `X-Forwarded-For`
value, which the client controls. `/state`, `/summary_json`, `/export_xlsx` and
`/export_decisions` need only the room code and have no rate limit. Fix as in
B3: `ProxyFix(x_for=1)` + `request.remote_addr`, rate-limit misses on every
room-code route, and require a registered `client_id` for the exports and the
summary.

### N7 — `my_registration_denied` is always false · Low · Probed

**Issue.** `serializer.py:364` reads `_ci.get("reg_denials", 0)`, but
`get_client_info()` (`validators.py:91`) never returns `reg_denials`. After two
denials the server refuses the player ("You have been denied too many
times…"), but `/state` says `my_registration_denied: false`. The UI
(`seats.js:99`) shows "rejected, try again" and the seat buttons instead of
the blocked screen. The check also hardcodes `2` instead of `MAX_REG_DENIALS`.

**Fix.** Read the count from `session._room_clients.get(client_id, {})` (or add
it to `get_client_info`) and compare with `MAX_REG_DENIALS`. Add a test.

### N8 — `/claim_milestone` 500 for spectators · Low · Probed

**Issue.** `caller_info.get("name", "")` is `None` for a spectator (the key
exists with value `None`), so `caller_name.lower()` raises (`admin.py:260`).
The global error handler turns that into a JSON 500.

**Fix.** `caller_name = caller_info.get("name") or ""`. Not verified: the check
compares only the caller's **primary** seat. If a milestone can go to a seat
the client controls through `local_names` (the admin's local seats), that
client can't claim it, and it is forfeited. Worth a test.

### N9 — Suggestion inbox accepts by index · Low

**Issue.** `/rules/suggestion` takes `index` (`services/rule_votes.py:91`), and
the inbox renders `data-rs-sug="${i}"` (`rules-settings.js:348`).
`suggest_rule()` removes an older suggestion for the same rule and appends the
new one, and the list is trimmed to `MAX_RULE_SUGGESTIONS`. If that happens
between the admin's last poll and the tap, the index points at a different
suggestion and the admin accepts or dismisses the wrong change.

**Fix.** Address a suggestion by a stable key: its first rule ID (one
suggestion per rule already holds) or a sequence number stored on it.

### N10 — "Vote on new rules" can be spammed · Low

**Issue.** `_open_vote()` applies `_rule_vote_cooldowns` only for
`kind == "change"`. A player can reopen the `enable` vote as soon as the last
one fails, filling the log and popping the vote modal on every phone.

**Fix.** Apply the same freeze to `enable` votes, or a separate per-player
cooldown.

### N11 — `/preselect` and request size · Low

- `routes/suggestions.py:51–52` uses `player.hands` before checking `if player`.
  It is unlikely in practice (`current_turn` matched the name), but the guard
  is in the wrong order.
- `/preselect` and `/suggest_action` store `f"{name}:{hand}"` with any `hand`
  string, so one client can add any number of keys to `_preselections` and
  `_suggestions` for the rest of the round. Validate `hand` with
  `^hand\d{1,2}$`.
- There is no `MAX_CONTENT_LENGTH`. Set one (for example 64 KB) in
  `create_app()`.

### N12 — Hidden duplicate test · Low

`tests/app/test_targeted_drinking.py` defines `test_forfeit_noop_before_expiry`
twice (ruff F811, first copy at line 329). Python keeps only the second
definition, so the first test never runs. Rename one of them.

### N13 — Cleanup · Low

- `_cmd_blackjack` (`routes/commands/digital.py:309`) is not in
  `DIGITAL_COMMANDS`, so it never runs. Delete it, or register it if the
  BLACKJACK button is meant to exist in digital mode.
- `ruff check .`: 37 errors. 3 can be fixed with `--fix` (unused imports in
  tests), plus E402 / E741 / E731 / F841 and E501 in `app/config.py`,
  `serializer.py`, `drink_tracker.py`, `referee.py` and `player_actions.py`.
- The error replies are inconsistent: some routes `escape()` the error string
  and others don't. It is harmless because the frontend escapes, but it should
  be one convention.

---

## Part B — Earlier audit items still open

| # | Severity | Status | Note |
|---|---|---|---|
| G5 | Medium | Open | Normal (casino) mode uses drinking table rules |
| G13 | Low | Open | Referee `action … insurance` (`referee.py:339`) still ignores `insurance.bj_vote` |
| B1 | High | Open | = N2 |
| B3 | Medium | Open | = N6 |
| B4 | Medium | Open | = N5 |
| B5 | Medium | Open (not re-run) | Flaky `test_drinking_table_cannot_switch_to_normal`; one full run passed today |
| B6 | Low | Open | `_join_attempts` pruned only per returning IP |
| B7 | Low | Open | `create_app()` rewrites the bundle on every start |
| B8 | Info | Open | About 180 `innerHTML` assignments; spot checks of `log.js`, `rules.js` and `rules-settings.js` found everything escaped |
| B9 | Low | Open | No security headers; `after_request` only sets the no-cache headers |
| B10 | Info | Open | `requirements.txt` still has no version pins |
| B11 | Info | Open | Real first names in `engine/player_profiles/*.json` and the data folders |

Checked and fine: client IDs are only sent to the admin (`pending_registrations`,
`kicked_clients`, `denied_clients`). The comeback handout is wired into `tick`
and is forced at `newround`. The house-rule queue/apply logic and
`registry_payload` look right. Markdown rules are rendered through DOMPurify.

---

## Part C — Planning docs: still needed?

| Doc | Status | Recommendation |
|---|---|---|
| `CodeAudit-2026-10.md` | Part A (gates) done except G5 / G13. Part B mostly open. Parts C–E are brainstorms | **Keep.** Mark B1/B3/B4 with links to this audit |
| `DonateToDevelopers.md` | All four surfaces done. The "placeholder link" is now the real PayPal link in `_lobby.html` and `_modals.html` | **Done.** Update its status line, then archive or delete |
| `DrinkTypeMode.md` | Implemented. The last open box (`Rules.md / Terms.md` note) is half done: Rules.md §6.3 exists, Terms.md has nothing | **Nearly done.** Add the Terms.md line (or drop the box), then archive |
| `RuleToggles-Implementation.md` | Phases 0–4 shipped (only 3 and 4 carry ✅ in the table; 0–2 are in the code: registry, gates, coverage tests). Phase 5 partly done (majority vote built) | **Mostly done.** Mark phases 0–2 ✅. Move the Phase 5 leftovers (xlsx RULES sheet, share codes, save my house rules, quiz hooks, Normal→Drinking preset) to TODO.md, then archive |
| `RuleToggles-SettingsModal.md` | Built. Only §10 nice-to-haves (save, share code, per-rule intensity) are left | **Done.** Archive; the nice-to-haves go with the Phase 5 list above |
| `RuleToggles-StarterSet.md` | Presets shipped. Its quoted TODO checkboxes are stale. Open questions (Normal→Drinking lands on Starter? "Pub" preset for referee) | **Done.** Archive after moving the two open questions to TODO.md |
| `TODO.md` | "Simplified ruleset" and "add one rule at a time" are done (presets + ➕ Next rule) but still unchecked. Last updated 2026-07-18 | **Keep and update.** Tick those two, add the Rule Toggles Phase 5 list |
| `FileRefactor.md` | B1–B3 and C1–C3 done. A (manual check), D1–D4, E1–E4, F and G are open | **Keep** |
| `ImplementationImprovements.md` | 15 long-term architecture items, all open; overlaps with the earlier audit's Part C | **Keep** (or merge into the audit's production-readiness list) |
| `PlayerStyleBots.md` | Most "Next steps" are built but unchecked: `style_strategy.py`, profiles for rob / david / marko, the personality picker in admin settings, `/set_bot_personality`, `test_style_strategy.py`. Still open in practice: collecting more beta data, offline validation, the debug view of a bot's deviations | **Keep, but update.** Tick steps 3–6, leave only data collection and validation |
| `TargetedDrinkingMode.md` | Shipped (1,191 lines, mostly the build log). Open: playtest the MVP (§5), cooldown consent override (8.3), rescue / spectator side bets (8.5), Dealer Aces (8.7) | **Keep, but slim down.** Move the four open items to TODO.md and archive the build log |

Suggested tidy-up: create `docs/planning/archive/` for finished plans and keep
the top-level folder for open work only.

---

## Suggested order of work

1. N1 (bounded code loop + create rate limit) and N3 (personality check):
   small, and both close a server-wide risk.
2. N2 / B1 referee double bonus, with its regression test.
3. N4 shared "seated client" helper across the player routes.
4. N5 / B4 creator token for reserved rooms, then N6 / B3.
5. Low items N7–N13 in one cleanup pass, plus `ruff --fix`.
6. Docs tidy-up from Part C.
