"""
Fails if docs/Rules.md and engine/drinking_rules.py have drifted out of
sync since the last `python scripts/rules_sync.py update`.

This is a tripwire, not a correctness check: it can't tell you *what*
to fix, only that one side changed without the other (or that no
baseline has been recorded yet). See docs/Architecture.md ("Rules/Code
Sync Check") for the workflow.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.rules_sync import check  # noqa: E402


def test_rules_and_drinking_logic_in_sync():
    in_sync, message = check()
    assert in_sync, message
