# Architectural Improvements — Black(Out)Jack

> Concrete suggestions based on the June 2026 audit and post-audit review.
> Ordered roughly by effort, not priority — pick what fits the current sprint.

---

## 1 · `award_sips()` helper — centralise drink writes

**Status:** DONE

**Problem today:**
Sip events are written to four parallel accumulators in at least six different
files (`drink_tracker.py`, `polling.py`, `admin.py`, and three call sites inside
`drink_tracker.py` itself):

```python
session._drink_csv_rows.append({...})
session._sip_ticker[name] += sips
session._last_round_sips[name] += sips
session._last_round_drinks.append({...})
```

Every new feature that awards sips (Busfahrer, new Easter eggs, future mechanics)
has to remember all four writes. The bust-vote handout timeout was already missing
`_last_round_drinks` at one point.

**Fix — one function, one call site:**

Create `app/services/drink_tracker.py`:
```python
def award_sips(
    session: GameRoom,
    player_name: str,
    sips: int,
    rule: str,
    role: str = "player",
    reason: str | None = None,
) -> None:
    """
    Award `sips` to `player_name` and update all four session accumulators:
    _drink_csv_rows, _sip_ticker, _last_round_sips, _last_round_drinks.
    Call check_and_set_milestone() after if sips > 0.
    Negative sips (credits) are recorded but do not trigger milestones.
    """
    session._drink_csv_rows.append({
        "round":  session.round_count,
        "dealer": session.dealer_name,
        "player": player_name,
        "role":   role,
        "rule":   rule,
        "sips":   sips,
    })
    if sips != 0:
        session._sip_ticker[player_name] = session._sip_ticker.get(player_name, 0) + sips
        session._last_round_sips[player_name] = session._last_round_sips.get(player_name, 0) + sips
        session._last_round_drinks.append({
            "name":   player_name,
            "sips":   sips,
            "reason": reason or rule,
        })
    if sips > 0:
        check_and_set_milestone(session)
```

**Files to update:** replace the ~10 scattered write blocks in
`drink_tracker.py`, `polling.py`, and `admin.py` with `award_sips(...)` calls.

**Payoff:** Busfahrer only needs to call `award_sips()`. Future features
can't forget an accumulator. CSV export, sip ticker, and last-round drinks
stay in sync automatically.

---

## 2 · SSE (Server-Sent Events) instead of polling

**Status:** Blocked on Render. Viable once deployed elsewhere.

**Problem today:**
The app polls `/state` every N seconds. This caused:
- `_requestsInFlight` race conditions (LF-6, just patched with a one-slot queue)
- The poll-skip logic in `lobby.js` (`if (_requestsInFlight === 0)`)
- Latency: players see state changes up to the poll interval late
- ~80 lines of polling infrastructure that would disappear

**Render constraint:**
Render's free tier times out idle HTTP connections after 30 seconds, which
kills SSE streams. On a paid Render plan ($7/mo), or any VPS
(Hetzner, DigitalOcean, Fly.io, Railway), SSE works fine.

**How to implement when ready:**

Backend — add one new route in `app/routes/`:
```python
@bp.route("/stream")
def stream():
    """Push state as SSE whenever it changes."""
    room_code = request.args.get("room_code")
    def generate():
        last_seq = -1
        while True:
            session = game_sessions.get(room_code)
            if session and session._state_seq != last_seq:
                last_seq = session._state_seq
                data = json.dumps(serialize_state(session, client_id))
                yield f"data: {data}\n\n"
            time.sleep(0.3)
    return Response(generate(), mimetype="text/event-stream")
```

Frontend — replace `startPolling()` in `lobby.js`:
```js
function startPolling() {
    const es = new EventSource(`/stream?room_code=${roomCode}&client_id=${clientId}`);
    es.onmessage = e => _applyStateResult(JSON.parse(e.data));
    es.onerror   = () => showDisconnected();
}
```

**What disappears:** `pollTimer`, `_pollInterval()`, the `_requestsInFlight`
poll-skip guard, `fetchState()`, the `visibilitychange` handler, and
the `_pendingCmd` queue we just built (commands no longer race with polls).
The `_requestsInFlight` counter can stay for button-locking purposes but
loses its poll-suppression role.

---

## 3 · Backend-first API — already done

The June 2026 audit addressed all known cases (FH-1, FH-2, FH-3, FM-1,
FM-4). Dealer rotation, `can_double`, KPI stats, insurance outcome text,
and bust vote outcome text all moved to the serializer. Nothing actionable
remains here unless new features add new frontend logic.

**Rule going forward:** if JS is doing arithmetic on `state.*` fields, it
belongs in `serialize_state` or a helper it calls.

---

## 4 · Pydantic for state serialization

**Status:** Actionable now. Medium effort (~1 day).

**Problem today:**
`serialize_state` returns a raw `dict`. There is no schema, no validation,
and no guarantee that the frontend gets the fields it expects. When a new
field is added to the serializer, there is no way to know if existing consumers
handle its absence.

**Fix:**

```
pip install pydantic
```

Define `app/models/state_schema.py`:
```python
from pydantic import BaseModel

class HandState(BaseModel):
    cards: list[str]
    score: int
    can_double: bool
    can_split: bool
    doubled: bool
    result: str | None

class PlayerState(BaseModel):
    name: str
    hands: list[HandState]
    sips: int

class AppState(BaseModel):
    ok: bool
    phase: str
    round: int
    players: list[PlayerState]
    best_play: str | None
    kpi_stats: dict
    # ... etc
```

Update `serialize_state` to build and return `AppState(**data).model_dump()`.
Pydantic validates on construction — missing required fields raise immediately
at the call site, not silently on the frontend.

**Payoff:** Adds a runtime contract between backend and frontend. Makes
`serialize_state` self-documenting. Enables IDE autocomplete on the schema.
Catches missing fields when a new game phase is added.

---

## 5 · Unified game engine — merge referee and digital paths

**Status:** Large effort. Most valuable long-term, especially for Busfahrer.

**Problem today:**
`RefereeSession` (CLI path, `engine/referee.py`) and the digital web path
(`app/routes/game_commands.py` calling `RefereeSession` methods) are parallel
implementations of the same game. Bust-vote resolution diverged (H-2).
Rotation logic was in the frontend because the backend didn't support it in
the web path (FH-1, now fixed). Every new feature has to decide which path
to add it to — and often ends up in both.

**Core insight:**
The game logic already lives in `engine/` — `RefereeSession`, `RoundManager`,
`DrinkTracker`. The referee CLI and the web app are both just adapters on top
of that engine. They shouldn't reimplement anything.

**Target structure:**
```
engine/
  game_engine.py      ← new: pure game logic, no I/O
  referee.py          ← thin CLI adapter: parses text commands, calls engine
app/
  routes/
    game_commands.py  ← thin web adapter: parses HTTP requests, calls engine
```

**Concrete steps:**

1. Audit what `game_commands.py` does that `referee.py` doesn't (and vice versa).
   The main gaps are: web path handles client registration, shoe management,
   and settings queuing. CLI path handles interactive bust-vote resolution.

2. Extract shared methods from `RefereeSession` into a new
   `engine/game_engine.py` base class:
   - `deal_card(player, hand)` ← already `RoundManager`
   - `apply_action(player, action)` ← `cmd_action`
   - `apply_result(player, hand, outcome)` ← `cmd_result`
   - `end_round()` ← `cmd_endround`
   - `new_round()` ← `cmd_newround`

3. `RefereeSession` becomes a CLI adapter: parses text → calls `GameEngine`.
   `game_commands.py` becomes a web adapter: parses HTTP → calls `GameEngine`.

4. Shared rules (bust-vote resolution, rotation, blackjack BJ) live in
   `GameEngine` only — both adapters call the same function.

**This is a prerequisite for Busfahrer** if Busfahrer should also work in
referee mode. Without a unified engine, Busfahrer gets added to the web path
only, and the CLI path is left behind.

---

## 6 · Decompose `GameRoom`

**Status:** DONE. All three phases complete:
- Phase A: `DrinkLedger` extracted (`session.drinks.*`)
- Phase B: `SessionStats` extracted (`session.stats.*`)
- Phase C: `GameConfig` extracted (`session.config.*`)

Property shims remain on `GameRoom` for backward compat; remove alongside test cleanup when convenient.

**Problem today:**
`GameRoom` has ~40 fields across 5 unrelated concerns. Any file that imports
`GameRoom` can touch any field. There is no encapsulation — `polling.py` writes
to `_drink_csv_rows`, `admin.py` writes to `_milestones_claimed`, `serializer.py`
reads everything. When a bug touches the drink ledger, the entire `GameRoom`
is in scope.

**Target decomposition:**

```python
@dataclass
class DrinkLedger:
    csv_rows: list = field(default_factory=list)
    sip_ticker: dict = field(default_factory=dict)
    last_round_sips: dict = field(default_factory=dict)
    last_round_drinks: list = field(default_factory=list)
    prev_round_sips: dict = field(default_factory=dict)
    dealer_role_ticker: dict = field(default_factory=dict)
    milestones_claimed: dict = field(default_factory=dict)
    wild_card_presses: dict = field(default_factory=dict)

@dataclass
class SessionStats:
    hand_stats: dict = field(default_factory=dict)
    dealer_hand_stats: dict = field(default_factory=dict)
    streaks: dict = field(default_factory=dict)
    round_sip_history: list = field(default_factory=list)
    max_round_sips: dict = field(default_factory=dict)
    strategy_decisions: dict = field(default_factory=dict)

@dataclass
class GameConfig:
    mode: str = "referee"
    drinking_mode: bool = True
    easy_mode: bool = False
    bust_vote_enabled: bool = False
    strategy_hint_enabled: bool = False
    god_mode: bool = True
    dealer_rotate_every: int = 1
    bet_amount: float = 10
    starting_bankroll: float = 100

@dataclass
class GameRoom:
    session: RefereeSession
    config: GameConfig = field(default_factory=GameConfig)
    round: RoundState = field(default_factory=RoundState)
    drinks: DrinkLedger = field(default_factory=DrinkLedger)
    stats: SessionStats = field(default_factory=SessionStats)
    # ... client registry, queued settings, bankrolls
```

**Migration strategy (incremental, not a big bang):**

Phase A — `DrinkLedger` first. It has the most scattered writers, and
`award_sips()` (item 1 above) is the natural forcing function. Once
`award_sips()` exists, update it to write to `session.drinks.*` instead
of `session._*`. Update `serialize_state` and `reports.py` to read from
`session.drinks`. This is self-contained.

Phase B — `SessionStats`. Touched mainly by `drink_tracker.py`'s harvest
helpers and `serializer.py`. Straightforward rename.

Phase C — `GameConfig`. Mostly read-only after setup. Low risk.

**Add property shims during migration** to keep existing call sites working:
```python
@property
def _sip_ticker(self):          # keep old name working during transition
    return self.drinks.sip_ticker
```
Remove shims after all call sites are updated.

---

## 7 · Frontend component architecture

**Status:** Low urgency. Would require partial rewrite of JS layer.

**Problem today:**
The frontend is ~3000 lines of imperative DOM manipulation across 10+ JS files.
Specific pain points:
- FC-1 (apostrophe injection via `onclick` strings) is a structural problem:
  building event handlers as strings is always fragile.
- The `data-action` / `data-args` dispatch system in `bootstrap.js` is a
  hand-rolled component event system.
- Inline CSS in JS (LF-3, now cleaned up) will regrow as new features are added
  without a component boundary to contain it.
- Every panel (bust vote, insurance, milestone, peeked card) rebuilds its
  full `innerHTML` on every state update — no diffing, no lifecycle.

**What would need to change:**

Option A — **Minimal: class-based JS components, no framework.**
Wrap each panel in a class with `render(state)` and `mount(el)` methods.
Event listeners are attached once in `mount()`, never rebuilt. No dependency
on a build tool.
```js
class BustVotePanel {
    mount(el) {
        this.el = el;
        el.addEventListener("click", e => {
            const btn = e.target.closest("[data-vote]");
            if (btn) castBustVote(btn.dataset.vote);
        });
    }
    render(state) {
        // update only changed parts, not full innerHTML
    }
}
```

Option B — **Preact via CDN, no build step.**
Preact is 3KB, works via `<script type="module">`, and JSX is optional
(can use `h()` calls directly). Converts each panel to a function component.
Gives diffing, hooks, and event handler props. The rest of the app stays
vanilla JS — panels can be converted one at a time.
```html
<script type="module">
import { h, render } from 'https://esm.sh/preact';
import { useState } from 'https://esm.sh/preact/hooks';
</script>
```

**Recommended path:** Option A first (no new dependencies, no build tool),
then Option B for the panels that receive state on every poll tick
(bust vote, drinks panel, action buttons).

---

## 8 · Test directory split

**Status:** Quick win. ~30 minutes.

**Problem today:**
All 18 test files are in a single `tests/` directory. Engine tests
(`test_drinking_rules_*`, `test_regression_snapshots`, `test_classify_rule`)
have no Flask dependency. App tests (`test_bust_vote`, `test_decision_log`)
require Flask and a full `GameRoom`. Without the split, `pytest.importorskip`
band-aids are needed to stop collection failures.

**Target layout:**
```
tests/
  conftest.py           ← shared fixtures (make_player, make_hand, etc.)
  engine/
    conftest.py         ← engine-only fixtures
    test_drink_tracker.py
    test_drinking_rules_aces_blackjack.py
    test_drinking_rules_card_dealt.py
    test_drinking_rules_hand_resolution.py
    test_drinking_rules_handle_dispatch.py
    test_drinking_rules_hard_switch.py
    test_drinking_rules_round_end.py
    test_regression_snapshots.py
    test_round_manager_integration.py
    test_round_end_helpers.py
    test_rules_doc_sync.py
  app/
    conftest.py         ← Flask app fixture
    test_bust_vote.py
    test_classify_rule.py
    test_decision_log.py
    test_harvest_helpers.py
    test_normal_mode_no_drinking.py
    test_payout_tracker.py
```

**`pyproject.toml` change:**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]   # unchanged — pytest discovers subdirectories automatically
```

**CI benefit:** Can run `pytest tests/engine/` without Flask installed.
`pytest tests/app/` requires Flask but can be skipped in environments
where only the engine is being tested. The `importorskip` lines in
`test_bust_vote.py` and `test_decision_log.py` have been removed.

---

## Summary table

| # | | Improvement | Effort | Blocked? | Do before Busfahrer? |
|---|---|---|---|---|---|
| 1 | [X] | `award_sips()` helper | Small (2–3h) | No | **Yes** |
| 2 | [ ] | SSE instead of polling | Medium (1 week) | Yes — needs off Render | No |
| 3 | [X] | Backend-first API | Done | — | — |
| 4 | [ ] | Pydantic serialization | Medium (1 day) | No | No |
| 5 | [ ] | Unified game engine | Large (2–3 weeks) | No | Ideal |
| 6 | [X] | Decompose `GameRoom` | Medium per phase | No — do Phase A with #1 | Phase A yes |
| 7 | [ ] | Frontend components | Large (ongoing) | No | No |
| 8 | [X] | Test directory split | Small (30 min) | No | **Yes** |
