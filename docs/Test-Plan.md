# Drinking Rules Test Suite — Plan

Goal: full unit coverage of `engine/drinking_rules.py` (every `DrinkingRules`
method, `classify_rule`, and `DrinkTracker`), plus a statistical regression
layer that checks aggregate behavior against the existing
`scripts/snapshots/<p>p/<deck>deck/<label>/benchmarks.json` baselines.

## 1. Setup

- Add `pytest` to `requirements-dev.txt` (or a `[project.optional-dependencies]
dev` group in `pyproject.toml`).
- New `tests/` directory:
  - `tests/conftest.py` — shared fixtures/builders.
  - `tests/test_drinking_rules_card_dealt.py`
  - `tests/test_drinking_rules_aces_blackjack.py`
  - `tests/test_drinking_rules_hand_resolution.py`
  - `tests/test_drinking_rules_round_end.py`
  - `tests/test_drinking_rules_hard_switch.py`
  - `tests/test_drinking_rules_handle_dispatch.py`
  - `tests/test_classify_rule.py`
  - `tests/test_drink_tracker.py`
  - `tests/test_regression_snapshots.py`

## 2. Fixtures (`conftest.py`)

Builders to avoid repeating `Card(Rank.X, Suit.Y)` boilerplate:

- `make_card(rank, suit)`
- `make_hand(*cards, doubled=False, from_split=False, result=None)` — sets
  `.result` directly so `on_hand_resolved` etc. can be tested without running
  a full round.
- `make_player(name, hands=None, is_dealer=False)`
- A small set of canonical hands: `suited_21`, `blackjack_AJ_suited_black`,
  `blackjack_plain`, `bust_hand`, `five_card_21`, `doubled_loss`, etc.
- `ace_clubs_flag()` → fresh `{"protected": False}`-style dict per test.

## 3. Unit tests by method — rule/edge-case matrix

### `on_card_dealt`
- Non-ace card → `[]`.
- Player hand:
  - A♣ to non-dealer → `(player, -1, ...)` deferred-credit msg.
  - A♣ to dealer-player → sets `ace_clubs_flag["partial_protected"]` and
    `dealer_player_pending_credit`; msg has `sips == 0`.
  - A♠: verify target = `(idx + card_pos) % len(all_player_names)` for
    `card_pos` 1..4 and player counts 2, 3, 4, 6 (wrap-around correctness,
    including target == recipient case).
  - A♥ → recipient drinks 1.
  - A♦ → dealer drinks 1 with role `"dealer"`.
- Dealer hand (`is_dealer_hand=True`):
  - A♣ → sets `ace_clubs_flag["half_protected"]`, msg `sips == 0`.
  - A♠ odd `card_pos` → dealer drinks 1, role `"dealer"`.
  - A♠ even `card_pos` → `"all"` drinks 1.
  - A♥ → `"all"` drinks 1.
  - A♦ → `"players_only"` drinks 1.

### `check_four_aces`
- `<4` aces visible → `([], triggered_first_deal)` unchanged (test both
  `True`/`False` passthrough).
- `==4` aces, `phase="first_deal"` → `("all", 2, ...)`, returns `True`.
- `==4` aces, `phase="end_of_round"`, `triggered_first_deal=False` →
  `("all", 1, ...)`, returns `False`.
- `==4` aces, `phase="end_of_round"`, `triggered_first_deal=True` → `[]`,
  flag stays `True` (no double-firing same round).
- `>4` aces (shouldn't happen with normal shoes, but multi-deck shoes can
  have duplicates) — confirm `sum(...) < 4` check still behaves (>=4 fires).

### `_bj_multiplier` / `on_blackjack`
- Plain BJ (non-suited, no A+J both-black) → mult=1.
- Suited only → x2.
- A+J ranks only (mixed suits) → x2.
- Both black suits only (not suited, e.g. A♠+J♣) → x2.
- Suited + A+J → x4.
- Suited + A+J + both black (A♣+J... wait A+J both black, e.g. A♣J♠ suited
  impossible since suited requires same suit — use A♣+J♣ → suited AND
  both-black AND A+J) → x8.
- `all_player_names` excludes `player_name` and `hard_switch_dealer`.
- Only 2 players, one is `hard_switch_dealer` → `others == []`, returns `[]`.

### `resolve_insurance_vote`
- `insured=True, dealer_bj=True` → BJ holder drinks own `mult` sips, plus
  a `(None, 0, ...push...)` info msg. Verify `mult` reflects suited/AJ/black
  multipliers.
- `insured=True, dealer_bj=False` → others drink `mult * 2`.
- `insured=False, dealer_bj=True` → single `(None, 0, ...)` info msg only.
- `insured=False, dealer_bj=False` → delegates to `on_blackjack` (assert
  identical output for same args).
- `hard_switch_dealer` propagation in the delegate case.

### `on_hand_resolved`
- `result != "win"` and not 21-with-5+ → `[]`.
- `result != "win"` but 21 with 5+ cards → only the handout msg
  (`sips == -len(cards)`, `role == "handout"`), regardless of win/loss/push.
- `dealer_bj=True` suppresses the 21/5+-card handout even if score==21 and
  len>=5.
- Doubled win, not suited → `+1` to each of `others_np` (others minus
  `dealer_name`), reason mentions "immunity exception".
- Doubled win that IS suited → doubled-immunity branch must NOT fire (only
  the suited branch fires, with sips=4).
- Suited win, not blackjack, not doubled → `+1` per `others_np`.
- Suited win, not blackjack, doubled → `+4` per `others_np` (not 1, and not
  also +1 from the doubled branch — confirm doubled branch is skipped because
  `hand.is_suited()` is True).
- Suited win that IS blackjack → suited bonus suppressed entirely (BJ bonus
  already covers it) — only handout / 5-card-win logic could still apply.
- Win with `len(cards) >= 5` → `+1` per `others_np`, and confirm it **stacks**
  with suited/doubled bonuses (multiple messages returned for one resolution
  when score==21, suited, doubled, and 5+ cards all true).
- `dealer_name` exclusion: dealer-player never appears in `others_np` for any
  of the above bonuses, but the handout rule (`player_name`-keyed) is
  unaffected by `dealer_name`.
- Single-other-player edge (2-player table): `others`/`others_np` length 0 or
  1 sanity.

### `check_all_hands_sweep`
- `dealer_bj=True` → `[]` regardless of hands.
- `len(player_hands) < 2` → `[]`.
- `all_cards` empty (degenerate hands with 0 cards) → `[]`.
- All same suit, not all 21 → multiplier 2, reason mentions "suited across
  all hands".
- All hands score 21, not all same suit → multiplier 2, reason "all hands
  scored 21".
- Both conditions → multiplier 4, reason mentions "(x4)".
- Neither condition → `[]`.
- `wager` scaling: sips == `wager * multiplier` for `wager` in {1, 2}.
- Cancellation messages: for each winning, doubled, non-suited hand in
  `player_hands`, an extra `(other, -1, "...Sweep cancels...")` per other
  player (not `dealer_name`, not `player_name`).
- `dealer_name` and `player_name` excluded from all recipients.

### `dealer_21_five_cards`
- score==21, len==5 → `True`.
- score==21, len==4 → `False`.
- score==20, len==6 → `False`.
- score==21 via soft ace recount with 5 cards → `True` (depends on `Hand.score`
  but worth a sanity check).

### `on_dealer_hand_revealed`
- `len(cards) >= 2` and all same suit → `("all", 2, ...)`.
- `len(cards) >= 2`, mixed suits → `[]`.
- `len(cards) == 1` (even though trivially "same suit") → `[]` (guards on
  `len(hand.cards) >= 2`).

### `on_round_end` — dealer_bj=True branch
- `num_hands` supplied vs `0` (fallback to counting `not h.from_split` hands)
  — construct players where these differ (e.g., a split occurred) and confirm
  fallback counts only non-split hands while `num_hands` overrides with the
  configured starting count.
- `bj_pushes` reduces the charge: a starting-hand BJ that pushed vs dealer BJ
  is excluded from `starting_losses`.
- `starting_losses == 0` → no message for that player.
- `hard_switch_dealer` fully excluded (no message at all) even if they'd
  otherwise owe.
- Splits do **not** reduce the charge (player started with 2 hands, split one
  into 3 total — charge still based on `num_hands`/2 starting hands, not 3).

### `on_round_end` — normal branch
- Net losses: `net_losses() > 0` → msg `net * wager`; `== 0` → no msg.
  (`net_losses()` definition lives in `Player` — confirm wins offset losses.)
- Lost doubled hand → `+wager`, separate message from net-loss message.
- Lost suited hand → `+wager`, separate message.
- A hand that is both doubled AND suited AND lost → two separate `+wager`
  messages (stacking), plus contributes to net loss.
- Split wins: `split_wins = count(from_split and result=="win")`;
  `sips = max(0, split_wins - 1)`. Test 0, 1, 2, 3 split wins → sips 0, 0, 1, 2.
  Verify message goes to every *other* player (not the winner), excluding
  `hard_switch_dealer`.
- Other-player-wins-all (`winner` has 0 losses, 0 pushes):
  - `other` has 0 losses, 0 pushes → immune, sips=0, no message.
  - `other` has 0 losses, >0 pushes → `sips = max(0, w_wins - o_wins)`,
    including the `0` case (no message when result is 0).
  - `other` has >0 losses → `sips = w_wins` regardless of `o_wins`/`o_pushes`.
  - `winner` has any loss or push → rule doesn't fire for that winner at all.
  - `hard_switch_dealer` excluded as `other`.
- All-`_excluded` players (hard switch dealer with 0 other players, i.e.
  2-player game) → graceful empty results, no crash.

### `on_hard_dealer_switch`
- Empty `winning_hands` → `total == 0`; confirm the message is still returned
  with `sips == 0` (informational, since `apply()` treats `sips==0` as
  no-op/info).
- Mixed hand types in one call: dealer's own BJ (1), other player's BJ (2),
  doubled win (2), regular win (1) → `total` = sum, `lines` joined with `"; "`.
- `half_protected=True`, `total > 0` → `ceil(total/2)`, reason mentions
  "half protection" and shows `(halved from {total}: ...)`.
- `half_protected=True`, `total == 0` → falls through to normal branch
  (returns `total == 0`, no "halved" wording) — confirm the `if half_protected
  and total > 0` guard.
- Dealer's own-hand BJ valued at 1 (not 2, no multiplier) vs another player's
  BJ valued at 2 — both in the same call.

### `handle()` dispatch
- One test per `GameEventType` constructing the matching dataclass with
  minimal args and asserting it calls through to the right static method
  (use `unittest.mock.patch` on the target method, or just compare output to
  calling the method directly with the same args).
- An unrecognized object (e.g. a plain `object()` or a new dataclass not in
  the match) → `NotImplementedError`.

## 4. `classify_rule` — string-matching matrix

Build a table of `(reason_string, expected_canonical_or_None)` covering every
branch in source order, including ordering-sensitive overlaps:

- `None`-returning reasons: `"... A♣ ... credit ..."`, `"A♣ protected ..."`,
  `"A♣ protection credit ..."`, `"... bust vote correct ..."`,
  `"... protects ..."`, `"... exempt ..."`.
- `"Bust vote ... wrong ..."` → `"Bust vote wrong call"`.
- Insurance variants → the three insurance canonical names.
- `"Hard Dealer Switch (A♣ half protection)"` vs plain `"Hard Dealer Switch"`
  — confirm the half-protection check is matched **before** the generic one
  (test a string that would match both).
- `"net loss"`, `"lost a doubled hand"`, `"lost a suited hand"`,
  `"immunity exception"`, `"won suited hand"`, `"split hand"`,
  `"swept all hands"`, `"all-hands sweep"`, `"auto-insurance"`,
  `"Blackjack by"`, four-aces (first_deal / end_of_round), dealer suited hand,
  5-card-21 handout, 5+ card win.
- All six "Ace dealt" variants — dealer-hand vs player-hand for ♠/♥/♦, and
  confirm dealer-hand checks are matched before player-hand checks for the
  same suit (e.g. a string containing both "A♠" and "dealer" should map to
  the dealer variant, not the player variant).
- A reason string matching nothing → `"Other"`.

## 5. `DrinkTracker`

- `_resolve`:
  - `"all"` → every player (incl. dealer-player).
  - `"players_only"` → all `not p.is_dealer`.
  - exact name (case-insensitive) → `[player]`.
  - unknown name → `[]`.
- `apply`:
  - `recipient is None` or `sips == 0` → no drink added; reason printed only
    if `verbose`.
  - `sips < 0`, `role == "handout"` → routes to `_handle_handout`.
  - `sips < 0`, role != handout → direct negative `add_drink` (credit), e.g.
    sweep-cancellation.
  - `sips > 0` → `add_drink(sips, reason, role)` for each resolved target;
    confirm `role` defaults to `"player"`.
- `apply_end_of_round`:
  - `< 4` players, `easy_mode=False` → no halving, raw `apply`.
  - `>= 4` players → halving credit per player: `gained - ceil(gained/2)`.
    Test `gained` = 1 (credit 0), 2 (credit 1), 3 (credit 1), 5 (credit 2).
  - `easy_mode=True` with `< 4` players → halving still applies, label "Easy
    mode".
  - Multiple `msg_lists` combined into one batch before the pre/post snapshot
    (a player gaining sips across two separate lists is halved once on the
    combined total, not twice).
  - A player with `gained == 0` this batch → no halving credit message.
- `apply_ace_clubs_credit`:
  - `drinks_owed() > 0` → `-1` credit applied.
  - `drinks_owed() == 0` → no-op (no credit message).
- `_handle_handout`:
  - `giver` not in `self.players` minus self → `others` empty → no-op.
  - NPC giver (`is_npc=True`) → round-robin distribution to `others`,
    `total` sips distributed across `len(others)` recipients, wrapping with
    `i % len(others)`.
  - Human giver path: mock `builtins.input` to supply valid then invalid then
    valid names; confirm invalid names are rejected and looped, self-name
    rejected.
- `print_round_summary`: smoke test only — run with `verbose=False` against a
  populated `drink_log` (mixed `"player"`/`"dealer"` roles, `"House"` player
  skipped) and confirm it doesn't raise; optionally capture stdout with
  `verbose=True` and assert key substrings appear.

## 6. Integration: full-round via `RoundManager` (sanity, not exhaustive)

A handful of scripted, seeded rounds (fixed `Shoe` ordering by pre-loading
`shoe.cards`) that exercise multi-rule interactions end-to-end:
- A round producing a Hard Dealer Switch with A♣ half protection.
- A round with a player split where one split hand wins (split-win immunity
  break) and the other loses with double+suited (stacked loss penalties).
- A round with all 4 aces dealt on the first deal.
- A 4-player round to confirm `apply_end_of_round` halving fires.

These act as cross-checks that `handle()` wiring + `DrinkTracker.apply*`
combine correctly, independent of the pure unit tests above.

## 7. Regression against snapshots (`tests/test_regression_snapshots.py`)

The `scripts/snapshots/<p>p/<deck>deck/<label>/benchmarks.json` files contain
100k-round aggregates (`sips_per_round_by_rule`, `avg_sips_per_round`,
`std_sips_per_round`, hand-outcome rates). These are statistical baselines,
not exact-match targets, so the regression test:

1. Runs a smaller, faster simulation (e.g. 5,000–10,000 rounds) for each
   snapshotted config (2p/3p/4p × 1–4 decks where snapshots exist), reusing
   `scripts/simulation.py`'s `run_simulation()` logic (refactor into an
   importable function if not already).
2. Loads the corresponding snapshot's `benchmarks.json` as baseline.
3. For each rule in `sips_per_round_by_rule`, asserts the new run's per-rule
   rate is within a tolerance band derived from `std_sips_per_round` (e.g.
   `abs(new - baseline) < 3 * (std / sqrt(n_new))` or a flat relative
   tolerance like ±20% for low-frequency rules, tighter for high-frequency
   ones).
4. Asserts `avg_sips_per_round`, `blackjack_rate_pct`, `bust_rate_pct`,
   `dealer_bust_pct`, win/loss/push rates are within tolerance.
5. Flags (fails loudly) any rule key present in the new run but absent from
   the snapshot, or vice versa — catches silently-added/removed rules that
   `classify_rule` now produces differently.

Determinism note: `Shoe.shuffle` should be seeded (`random.seed(fixed_seed)`)
for this test so failures are reproducible; if `simulation.py` doesn't expose
a seed hook today, add one (default `None` so production behavior is
unchanged).

A separate, optional slow test (`@pytest.mark.slow`, skipped by default)
re-runs the full 100k-round simulation and does an exact `diff` against
`scripts/snapshots/.../simulation_results.txt`, mirroring the existing manual
`scripts/snapshot.py` workflow — for use before releases.

## 9. Bust Vote Side Bet (Rules.md §4.4)

This rule is **not** implemented in `engine/drinking_rules.py` — it lives in
`app/services/drink_tracker.py` (`apply_bust_vote_penalties`) and
`app/routes/polling.py` (`/cast_bust_vote`, `/give_bust_sip`). It's outside
the scope of §1–§7 entirely (no engine unit coverage, no simulation/snapshot
coverage, since `scripts/simulation.py` never enables `bust_vote_enabled`).
New file: `tests/test_bust_vote.py`, using a `GameRoom`/session fixture and
Flask test client.

### `apply_bust_vote_penalties` (unit, session-level)
- `bust_vote_enabled=False` → no-op, `_bust_vote_result = None`.
- Enabled, no votes cast (`_bust_votes` empty) → no-op, `_bust_vote_result =
  None`.
- Enabled, all votes are `"pass"` (no `"bust"` voters) → no-op,
  `_bust_vote_result = None`.
- Dealer has no `dealer_hand` yet (called too early) → no-op, result `None`.
- Dealer busts (`dealer_hand.is_bust() == True`):
  - Each `"bust"` voter gets `-1` credit (`add_drink(-1, "bust vote correct:
    -1 sip credit", "player")`), added to `winners`.
  - `"pass"` voters and abstainers (not in `_bust_votes`) unaffected.
  - `_bust_vote_result == {"dealer_busted": True, "winners": [...], "losers":
    []}`.
  - `_bust_handout_expires_at` set to `now + BUST_HANDOUT_WINDOW_SECONDS`.
  - `_bust_handouts_given` reset to `set()`.
- Dealer does not bust:
  - Each `"bust"` voter gets `+1` penalty (`"Bust vote wrong — dealer didn't
    bust: +1 sip"`), added to `losers`.
  - `_bust_vote_result == {"dealer_busted": False, "winners": [], "losers":
    [...]}`.
  - `_bust_handout_expires_at = None` (no handout window — no winners).
- Mixed: some voters `"bust"`, some `"pass"`, dealer busts → only `"bust"`
  voters appear in `winners`/get credited; `"pass"` voters untouched and
  absent from both lists.
- `classify_rule` round-trip: `"bust vote correct: -1 sip credit"` →
  `None` (excluded from CSV); `"Bust vote wrong — dealer didn't bust: +1
  sip"` → `"Bust vote wrong call"`. (Already in §4's matrix — cross-reference
  here.)
- Net-effect floor: a player who wins the bust vote (-1 credit) but has 0
  other drinks this round — confirm `drinks_owed()` doesn't go negative
  where that matters downstream (e.g. milestone ticker uses
  `max(0, sum(...))`).

### `/cast_bust_vote` (route)
- `bust_vote_enabled=False` → `{"ok": False, "error": "Bust vote not
  enabled."}`.
- Vote window expired (`_bust_vote_expires_at` in the past or `None`) →
  rejected.
- `vote` not in `("bust", "pass")` → rejected.
- Valid vote recorded in `_bust_votes[voter_name]`; re-casting overwrites
  (last vote wins).
- Local-multiplayer `player_name` override: must be in the voter's
  `local_names` and a real player; otherwise rejected.
- When all human non-dealer players have voted → `auto_play_npc_turns` /
  `_run_deferred_dealer_play` triggered (assert via mock/spy).

### `/give_bust_sip` (route)
- Not a confirmed winner (`dealer_busted=False` or name not in `winners`) →
  rejected.
- Already given (`winner_name in _bust_handouts_given`) → rejected
  ("Already given.").
- `recipient_name` not a valid player → rejected.
- Self-assignment (`recipient == winner`, `forfeit=False`) → rejected
  ("Cannot give to yourself.").
- Valid handout: recipient gets `+1` (`"Bust vote handout from {winner}: +1
  sip"`), `winner_name` added to `_bust_handouts_given`,
  `_last_round_sips`/`_sip_ticker`/`_drink_csv_rows` all patched, milestone
  check re-run.
- `forfeit=True`: self-assignment to the winner is allowed, reason becomes
  `"Bust vote forfeited — {winner} didn't assign in time: +1 sip"`.

### ⚠ Bug: handout forfeit is not server-enforced
`_bust_handout_expires_at` is set when winners are determined, but **nothing
on the backend checks it**. Compare to milestones: `apply_milestone_forfeit`
is called on every `/state` poll (`app/routes/polling.py`) and auto-penalizes
a winner who doesn't assign their handout in time. The bust-vote equivalent
only happens if the *frontend* notices its local timer expired and calls
`/give_bust_sip` with `forfeit=true` — if that call never arrives (closed
tab, client bug, network drop), the winner's `-1` credit stands with no
counterbalancing `+1`, and `_bust_handout_expires_at`/`_bust_handouts_given`
are never finalized for that round.

Given the goal of keeping all scoring/timing logic server-authoritative (no
client-trusted timers), this should be fixed by adding an
`apply_bust_handout_forfeit(session)` function mirroring
`apply_milestone_forfeit`:
- If `_bust_handout_expires_at` is set and `time.monotonic() >=
  _bust_handout_expires_at`, for every winner in `_bust_vote_result["winners"]`
  not yet in `_bust_handouts_given`, apply the same `+1` "forfeited" drink,
  add to `_bust_handouts_given`, and clear `_bust_handout_expires_at` once all
  winners are resolved.
- Call it from the same poll-tick spot as `apply_milestone_forfeit`
  (`app/routes/polling.py` line ~104).
- Once added, `/give_bust_sip`'s client-supplied `forfeit=true` path becomes
  redundant/defense-in-depth rather than the sole enforcement — tests should
  cover both the server-side auto-forfeit and the route still behaving
  correctly if called concurrently (idempotent via `_bust_handouts_given`
  check).

Test additions for the fix:
- Time-travel (`monotonic` patched/advanced past `_bust_handout_expires_at`)
  with an unresolved winner → `apply_bust_handout_forfeit` applies `+1` and
  marks them given.
- Already-given winner → no double penalty.
- Window not yet expired → no-op.
- No `_bust_vote_result` / no winners → no-op.

## 10. Running

- `pytest -m "not slow"` for the fast unit + regression suite (CI default).
- `pytest -m slow` for the full 100k-round snapshot diff (manual/release).
- Add to `pyproject.toml`: `[tool.pytest.ini_options] markers = ["slow: full
100k-round simulation regression"]`.
