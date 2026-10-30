"""
engine/rules_registry.py
========================
Single source of truth for every toggleable drinking rule.

Each rule is declared once as a ``RuleDef`` (stable ID, group, dependencies,
lowest preset, unlock step, Rules.md anchor, CSV labels). A room's choice of
rules is a ``RuleSet``; ``rules.on("ace.hearts.player")`` answers whether a
rule is in effect, with dependencies resolved (a child whose parent is off
reads as off, locked rules always read as on).

Lives in ``engine/`` because the terminal and referee modes need it too, and
``engine/`` must not import from ``app/``.

docs/Rules-Catalog.md mirrors this file; tests/engine/test_rules_catalog_sync.py
keeps the two aligned. IDs are stable and never renamed. The registry order is
append-only (it is the bit order for future share codes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

PRESET_ORDER = ("locked", "starter", "standard", "full")


@dataclass(frozen=True)
class RuleDef:
    id: str                            # "ace.hearts.player" (stable, never renamed)
    name: str                          # "A♥ to a player"
    summary: str                       # "you drink 1"
    kind: str                          # "core" | "table" | "drink" | "event" | "meta"
    timing: str                        # "instant" | "end-of-round" | "between-rounds" | "passive"
    preset: str                        # lowest preset: "locked" | "starter" | "standard" | "full"
    unlock_step: int | None = None     # order for "Next rule" (None for locked/starter rules)
    depends_on: tuple[str, ...] = ()
    doc_anchor: str = ""               # Rules.md heading slug, e.g. "41-ace-effects"
    csv_labels: tuple[str, ...] = ()   # classify_rule() outputs this rule produces
    live: bool = False                 # True: toggles apply immediately (bust vote, wild card)
    halvable: bool | None = None       # informational, for badges and the quiz

    @property
    def group(self) -> str:
        return self.id.split(".", 1)[0]


GROUPS: tuple[tuple[str, str], ...] = (
    ("core", "Core"),
    ("table", "Table rules"),
    ("insurance", "Insurance"),
    ("switch", "Dealer switch"),
    ("ace", "Aces"),
    ("dealer", "Dealer hand"),
    ("four_aces", "Four Aces"),
    ("side", "Side bets"),
    ("cards", "Special cards"),
    ("loss", "Hand losses"),
    ("others", "Other players"),
    ("bonus", "Blackjack bonus"),
    ("five_card", "5+ cards"),
    ("sweep", "All-hand bonus"),
    ("milestone", "Milestones"),
    ("streak", "Streaks"),
    ("event", "Events"),
)


def _r(id, name, summary, kind, timing, preset, step=None, dep=(), anchor="",
       csv=(), live=False, halved=None) -> RuleDef:
    return RuleDef(id, name, summary, kind, timing, preset, step, tuple(dep),
                   anchor, tuple(csv), live, halved)


_A41 = "41-ace-effects"
_A51 = "51-net-hand-losses"
_A52 = "52-other-players-results"
_A53 = "53-blackjack-bonus"
_A54 = "54-5-cards-handouts"
_A55 = "55-player-all-hand-bonus"

# Registry order is append-only. Unlock steps follow RuleToggles-StarterSet §5.
RULES: tuple[RuleDef, ...] = (
    _r("core.net_loss", "Net hand losses", "lose more than you win, drink the difference",
       "core", "end-of-round", "locked", anchor=_A51, csv=("Net hand losses",), halved=True),
    _r("core.dealer_rotation", "Dealer rotation / Soft Switch", "the dealer seat rotates",
       "core", "end-of-round", "locked", anchor="2-dealer-rotation"),
    _r("table.split_tens", "Mandatory split 10s (play with honor)", "must split unsuited 10s",
       "table", "instant", "starter",
       anchor="3-rule-modifications-from-standard-blackjack",
       csv=("Split 10s without honor", "Split suited 10s"), halved=False),
    _r("table.split_aces", "Mandatory split Aces", "any other action on A-A costs 1 sip",
       "table", "instant", "standard", 13, anchor="31-splitting-aces",
       csv=("Didn't split Aces",), halved=False),
    _r("table.split_ace_bj", "Blackjack on split Aces counts as Blackjack", "split A + 10 is a Blackjack",
       "table", "passive", "standard", 13, anchor="31-splitting-aces"),
    _r("insurance.auto_cap", "Auto-insurance cap (Ace up-card)", "dealer Blackjack on an Ace is capped",
       "drink", "passive", "starter", anchor="32-insurance",
       csv=("Dealer BJ (auto-insurance)",), halved=True),
    _r("insurance.bj_vote", "Player Blackjack insurance vote", "table votes to insure a Blackjack",
       "event", "instant", "full", 19, dep=("bonus.blackjack",), anchor="32-insurance",
       csv=("Insurance: BJ holder drinks own bonus", "Insurance: group drinks double BJ bonus"),
       halved=True),
    _r("switch.hard", "Hard Dealer Switch penalty", "dealer loses every hand, dealer drinks",
       "drink", "end-of-round", "starter", anchor="57-hard-dealer-switch-penalty",
       csv=("Hard Dealer Switch", "Hard Dealer Switch (half, A♣)"), halved=True),
    _r("ace.clubs.player", "A♣ to a player: -1 credit", "-1x wager from your net",
       "drink", "instant", "standard", 3, anchor=_A41,
       csv=("A♣ protection credit", "A♣ waived"), halved=False),
    _r("ace.spades.player", "A♠ to a player: pass a sip by position", "next player(s) drink",
       "drink", "instant", "standard", 4, anchor=_A41,
       csv=("Ace dealt: Ace of Spades (player hand)",), halved=False),
    _r("ace.hearts.player", "A♥ to a player: treat yourself", "you drink",
       "drink", "instant", "standard", 1, anchor=_A41,
       csv=("Ace dealt: Ace of Hearts (player hand)",), halved=False),
    _r("ace.diamonds.player", "A♦ to a player: dealer drinks", "the dealer drinks",
       "drink", "instant", "standard", 2, anchor=_A41,
       csv=("Ace dealt: Ace of Diamonds (player hand)",), halved=False),
    _r("ace.clubs.dealer", "A♣ to the dealer: half Hard Switch", "Hard Switch penalty halved",
       "drink", "passive", "standard", 3, dep=("switch.hard",), anchor=_A41,
       csv=("Hard Dealer Switch (half, A♣)",)),
    _r("ace.spades.dealer", "A♠ to the dealer: odd/even", "odd: dealer drinks, even: players drink",
       "drink", "instant", "standard", 4, anchor=_A41,
       csv=("Ace dealt: Ace of Spades (dealer hand)",), halved=False),
    _r("ace.hearts.dealer", "A♥ to the dealer: everyone drinks", "all players drink",
       "drink", "instant", "standard", 1, anchor=_A41,
       csv=("Ace dealt: Ace of Hearts (dealer hand)",), halved=False),
    _r("ace.diamonds.dealer", "A♦ to the dealer: players drink", "all non-dealer players drink",
       "drink", "instant", "standard", 2, anchor=_A41,
       csv=("Ace dealt: Ace of Diamonds (dealer hand)",), halved=False),
    _r("dealer.suited_hand", "Dealer suited hand", "dealer's hand is one suit, everyone drinks",
       "drink", "instant", "standard", 10, anchor="42-dealer-suited-hand",
       csv=("Dealer suited hand",), halved=False),
    _r("four_aces.first_deal", "Four Aces on first deal", "all four Aces out, everyone drinks 2",
       "drink", "instant", "standard", 12, anchor="43-four-aces-on-first-deal",
       csv=("Four Aces (first deal)",), halved=False),
    _r("four_aces.end_round", "Four Aces at end of round", "all four Aces visible, everyone drinks 1",
       "drink", "end-of-round", "standard", 12, anchor="56-four-aces-at-end-of-round",
       csv=("Four Aces (end of round)",), halved=True),
    _r("side.bust_vote", "Side bet: dealer bust vote", "bet whether the dealer busts",
       "event", "instant", "standard", 5, anchor="44-side-bet-dealer-bust", live=True,
       csv=("Bust vote credit", "Bust vote wrong call", "Bust vote handout received",
            "Bust vote handout forfeited"), halved=False),
    _r("cards.devils_hand", "Devil's Hand (third 6)", "third 6 in a hand",
       "drink", "instant", "full", 15, anchor="45-devils-hand-and-lucky-sevens",
       csv=("Devil's Hand",), halved=False),
    _r("cards.lucky_sevens", "Lucky Sevens (third 7)", "third 7 in a hand",
       "drink", "instant", "full", 15, anchor="45-devils-hand-and-lucky-sevens",
       csv=("Lucky Sevens",), halved=False),
    _r("loss.doubled", "Doubled hand counts ±2", "a double is worth 2 in your net, win or lose",
       "drink", "end-of-round", "starter", dep=("core.net_loss",), anchor=_A51,
       csv=("Lost doubled hand",), halved=True),
    _r("loss.suited", "Lost suited hand +1 (x4 if doubled too)", "lose a suited hand, one extra",
       "drink", "end-of-round", "standard", 7, dep=("core.net_loss",), anchor=_A51,
       csv=("Lost suited hand",), halved=True),
    _r("others.wins_all", "Another player wins all hands", "drink per hand they won",
       "drink", "end-of-round", "starter", anchor=_A52,
       csv=("Other-player sweep",), halved=True),
    _r("others.immunity.doubled", "Immunity break: doubled win", "others drink for a doubled win",
       "drink", "end-of-round", "standard", 9, anchor=_A52,
       csv=("Doubled win (immunity break)",), halved=True),
    _r("others.immunity.split", "Immunity break: split win", "others drink per split won",
       "drink", "end-of-round", "standard", 9, anchor=_A52,
       csv=("Split win (immunity break)",), halved=True),
    _r("others.immunity.suited", "Immunity break: suited win", "others drink for a suited win",
       "drink", "end-of-round", "standard", 8, anchor=_A52,
       csv=("Suited winning hand",), halved=True),
    _r("bonus.blackjack", "Blackjack bonus (flat 1x)", "Blackjack makes everyone else drink",
       "drink", "end-of-round", "starter", anchor=_A53,
       csv=("Blackjack bonus",), halved=True),
    _r("bonus.blackjack.multipliers", "Blackjack bonus x2 multipliers", "suited, doubled and split Blackjacks pay more",
       "drink", "end-of-round", "standard", 6, dep=("bonus.blackjack",), anchor=_A53,
       csv=("Blackjack bonus",), halved=True),
    _r("five_card.player_21", "5+ cards to exactly 21: handout", "hand out sips",
       "drink", "end-of-round", "standard", 11, anchor=_A54,
       csv=("5-card 21 handout received",), halved=False),
    _r("five_card.player_win", "5+ card win: others drink", "others drink when you win with 5+ cards",
       "drink", "end-of-round", "standard", 11, anchor=_A54,
       csv=("5+ card win",), halved=True),
    _r("five_card.dealer_21", "Dealer 5+ cards to 21: core penalties doubled", "core penalties doubled this round",
       "drink", "end-of-round", "full", 20, anchor=_A54, halved=True),
    _r("sweep.same_suit", "All-hand bonus: every card one suit", "every card across all hands is one suit",
       "drink", "end-of-round", "full", 16, anchor=_A55,
       csv=("All-hands sweep", "Sweep credit"), halved=True),
    _r("sweep.all_21", "All-hand bonus: every hand 21", "every hand totals 21",
       "drink", "end-of-round", "full", 16, anchor=_A55,
       csv=("All-hands sweep",), halved=True),
    _r("milestone.handout", "Milestone handouts (every 50 sips)", "hand out sips at each milestone",
       "meta", "between-rounds", "starter", anchor="58-milestone-handouts", halved=False),
    _r("milestone.back_to_back", "Back-to-back milestone callout", "cosmetic callout",
       "meta", "passive", "starter", dep=("milestone.handout",), anchor="back-to-back-milestones"),
    _r("milestone.worst_average", "\"Worst average\" penalty", "slowest drinker is penalised",
       "meta", "between-rounds", "full", 18, dep=("milestone.handout",),
       anchor="worst-average-penalty", halved=False),
    _r("streak.l_badge", "Losing streak \"L\" badge + comeback handout",
       "5+ losses in a row wears the L; breaking the streak hands out sips",
       "meta", "end-of-round", "full", 17, anchor="losing-streak-l-badge",
       csv=("Comeback handout",), halved=False),
    _r("event.dealer_lottery", "Dealer Lottery", "a lottery between rounds",
       "event", "between-rounds", "full", 14, anchor="59-dealer-lottery"),
    _r("event.targeted", "Targeted Drinking Mode", "a targeted drinking mini-game",
       "event", "between-rounds", "full", 22, anchor="510-targeted-drinking-mode", halved=False),
    _r("event.targeted.perfect_handout", "Targeted: perfect-graduation handout", "bonus handout for a perfect run",
       "event", "between-rounds", "full", 22, dep=("event.targeted",), anchor="510-targeted-drinking-mode"),
    _r("event.wild_card", "Wild Card easter egg", "tap the logo for a random effect",
       "event", "instant", "full", 21, anchor="easter-egg-launch-wild-card-", live=True,
       csv=("Wild Card",), halved=False),
    # Step 22, not 21: it depends on event.targeted, which unlocks at step 22.
    _r("event.wild_card.targeted", "Wild Card launches Targeted Drinking", "the Wild Card can start Targeted Drinking",
       "event", "between-rounds", "full", 22, dep=("event.wild_card", "event.targeted"),
       anchor="easter-egg-launch-wild-card-"),
)

RULES_BY_ID: dict[str, RuleDef] = {r.id: r for r in RULES}

# Lowest-preset sets. Each preset includes every rule at or below its level.
PRESETS: dict[str, frozenset[str]] = {
    name: frozenset(r.id for r in RULES
                    if PRESET_ORDER.index(r.preset) <= PRESET_ORDER.index(name))
    for name in PRESET_ORDER[1:]
}
LOCKED: frozenset[str] = frozenset(r.id for r in RULES if r.preset == "locked")
# Rules whose toggle applies at once instead of queuing for the next round.
LIVE: frozenset[str] = frozenset(r.id for r in RULES if r.live)


def _validate() -> None:
    """Fail at import time if the registry is inconsistent."""
    ids = [r.id for r in RULES]
    if len(ids) != len(set(ids)):
        raise ValueError("rules_registry: duplicate rule IDs")
    groups = {g for g, _ in GROUPS}
    for r in RULES:
        if r.group not in groups:
            raise ValueError(f"rules_registry: {r.id} has unknown group {r.group!r}")
        if r.preset not in PRESET_ORDER:
            raise ValueError(f"rules_registry: {r.id} has unknown preset {r.preset!r}")
        if not r.doc_anchor:
            raise ValueError(f"rules_registry: {r.id} has no doc_anchor")
        if r.id in r.depends_on:
            raise ValueError(f"rules_registry: {r.id} depends on itself")
        for dep in r.depends_on:
            if dep not in RULES_BY_ID:
                raise ValueError(f"rules_registry: {r.id} depends on unknown rule {dep!r}")
            parent = RULES_BY_ID[dep]
            if PRESET_ORDER.index(parent.preset) > PRESET_ORDER.index(r.preset):
                raise ValueError(f"rules_registry: {r.id} is in a lower preset than its parent {dep}")
            if r.preset == "locked" or parent.preset == "locked":
                continue
            # Unlock order: a rule never comes before its parent.
            if (parent.unlock_step or 0) > (r.unlock_step or 0):
                raise ValueError(f"rules_registry: {r.id} unlocks before its parent {dep}")
        # Locked and starter rules are on from the start, so they have no unlock step.
        has_step = r.unlock_step is not None
        if has_step != (r.preset in ("standard", "full")):
            raise ValueError(f"rules_registry: {r.id} unlock_step does not match preset {r.preset!r}")
    # Cycles: walk each rule's ancestors.
    for r in RULES:
        seen, stack = set(), list(r.depends_on)
        while stack:
            cur = stack.pop()
            if cur == r.id:
                raise ValueError(f"rules_registry: dependency cycle through {r.id}")
            if cur not in seen:
                seen.add(cur)
                stack.extend(RULES_BY_ID[cur].depends_on)
    if not PRESETS["starter"] <= PRESETS["standard"] <= PRESETS["full"]:
        raise ValueError("rules_registry: presets are not nested")
    if not LOCKED <= PRESETS["starter"]:
        raise ValueError("rules_registry: a locked rule is missing from a preset")
    if PRESETS["full"] != frozenset(RULES_BY_ID):
        raise ValueError("rules_registry: the full preset must contain every rule")


_validate()


def _preset_for(enabled: frozenset[str]) -> str | None:
    """The preset these rules match. Live rules (bust vote, wild card) are
    table toggles flipped at any time, so they don't count: a Full room
    with the bust vote off is still "Full"."""
    for name, ids in PRESETS.items():
        if ids - LIVE == enabled - LIVE:
            return name
    return None


@dataclass(frozen=True)
class RuleSet:
    """A room's chosen rules.

    ``enabled`` is what the admin toggled on (it may include children of off
    parents). ``on()`` gives the effective state: enabled, with every ancestor
    effective too. Locked rules are always on, so they are always in
    ``enabled`` as well.

    Two sets are equal when ``enabled`` is. ``preset`` is derived from it
    (the preset whose rules match, live rules aside, else None), never
    passed in.
    """
    enabled: frozenset[str]
    preset: str | None = field(init=False, compare=False)
    _effective: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        enabled = frozenset(self.enabled)
        unknown = enabled - RULES_BY_ID.keys()
        if unknown:
            raise ValueError(f"unknown rule IDs: {sorted(unknown)}")
        enabled |= LOCKED
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(self, "preset", _preset_for(enabled))
        object.__setattr__(self, "_effective", self._resolve(enabled))

    @staticmethod
    def _resolve(enabled: frozenset[str]) -> frozenset[str]:
        memo: dict[str, bool] = {}

        def eff(rule_id: str) -> bool:
            if rule_id not in memo:
                memo[rule_id] = rule_id in enabled and all(eff(d) for d in RULES_BY_ID[rule_id].depends_on)
            return memo[rule_id]

        return frozenset(r.id for r in RULES if eff(r.id))

    def on(self, rule_id: str) -> bool:
        """Effective state. Raises KeyError on an unknown ID so a typo in a
        gate fails loudly instead of silently turning the rule off."""
        if rule_id not in RULES_BY_ID:
            raise KeyError(f"unknown rule ID: {rule_id!r}")
        return rule_id in self._effective

    def effective(self) -> frozenset[str]:
        return self._effective

    def waiting_on_parent(self) -> frozenset[str]:
        """Rules switched on whose parent is off, so they read as off. The
        settings UI shows these as "on, waiting for <parent>"."""
        return self.enabled - self._effective

    def with_changes(self, on=(), off=()) -> "RuleSet":
        on, off = set(on), set(off)
        unknown = (on | off) - RULES_BY_ID.keys()
        if unknown:
            raise ValueError(f"unknown rule IDs: {sorted(unknown)}")
        locked = off & LOCKED
        if locked:
            raise ValueError(f"locked rules can't be turned off: {sorted(locked)}")
        return RuleSet((self.enabled | on) - off)

    def with_rule(self, rule_id: str, value: bool) -> "RuleSet":
        return self.with_changes(on=[rule_id]) if value else self.with_changes(off=[rule_id])

    def next_unlock(self) -> frozenset[str]:
        """What "Next rule" turns on: every rule at the lowest unlock step
        that still has one off (rules sharing a step come as a pair), plus
        any of their ancestors that are off, so the new rules take effect.
        Empty once every rule is on."""
        off = [r for r in RULES if r.unlock_step is not None and r.id not in self.enabled]
        if not off:
            return frozenset()
        step = min(r.unlock_step for r in off)
        picked, stack = set(), [r.id for r in off if r.unlock_step == step]
        while stack:
            cur = stack.pop()
            if cur not in picked and cur not in self.enabled:
                picked.add(cur)
                stack.extend(RULES_BY_ID[cur].depends_on)
        return frozenset(picked)

    @classmethod
    def from_preset(cls, name: str) -> "RuleSet":
        if name not in PRESETS:
            raise ValueError(f"unknown preset {name!r}")
        return cls(PRESETS[name])


FULL = RuleSet.from_preset("full")
STARTER = RuleSet.from_preset("starter")
STANDARD = RuleSet.from_preset("standard")

# What a new room gets: today's behaviour, i.e. everything except the dealer
# bust vote, which stays opt-in (admin turns it on in the lobby).
DEFAULT_RULES = FULL.with_changes(off=["side.bust_vote"])
