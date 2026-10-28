"""
Keeps docs/Rules-Catalog.md and engine/rules_registry.py aligned
(RuleToggles-Implementation §6.1): the registry is the source of truth.
"""
import re
from pathlib import Path

from engine.rules_registry import RULES, RULES_BY_ID

CATALOG = Path(__file__).resolve().parents[2] / "docs" / "Rules-Catalog.md"


def _anchor(rule_id: str) -> str:
    return rule_id.replace(".", "-")


def _catalog_text() -> str:
    return CATALOG.read_text(encoding="utf-8")


def test_every_registry_rule_has_a_catalog_entry_and_vice_versa():
    anchors = set(re.findall(r'<a id="([^"]+)"></a>', _catalog_text()))
    rule_anchors = {a for a in anchors if not a.startswith("mod-")}   # mod.* aren't toggles
    assert rule_anchors == {_anchor(r.id) for r in RULES}


def test_summary_table_matches_registry():
    rows = re.findall(
        r"^\| \[`([^`]+)`\]\(#[^)]*\) \| .*? \| (\w+) \| ([\w-]+) \| (\w+) \|$",
        _catalog_text(), flags=re.M)
    assert {r[0] for r in rows} == set(RULES_BY_ID)
    for rule_id, kind, timing, preset in rows:
        rule = RULES_BY_ID[rule_id]
        assert (kind, timing, preset.lower()) == (rule.kind, rule.timing, rule.preset), rule_id


def test_catalog_dependencies_match_registry():
    blocks = re.split(r"\n(?=### <a id=)", _catalog_text())[1:]
    for block in blocks:
        head = re.match(r'### <a id="([^"]+)"></a>.*? — `([^`]+)`', block)
        if not head or head.group(2) not in RULES_BY_ID:
            continue
        dep = re.search(r"\*\*Depends on:\*\* ([^\n]*?)(?: ·|\n|$)", block)
        listed = set(re.findall(r"`([a-z_.]+)`", dep.group(1))) & set(RULES_BY_ID) if dep else set()
        assert listed == set(RULES_BY_ID[head.group(2)].depends_on), head.group(2)
