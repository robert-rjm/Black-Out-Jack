"""
Fails if docs/Terms.md and templates/terms.html have drifted out of sync
since the last `python scripts/terms_sync.py update`.

This is a tripwire, not a correctness check: it can't tell you *what* to
fix, only that one side changed without the other (or that no baseline has
been recorded yet). docs/Terms.md is the single point of truth (readable
directly on GitHub); templates/terms.html is the styled copy served at
/terms and must say the same thing. See docs/Architecture.md ("Terms Doc
Sync Check") for the workflow.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.terms_sync import check  # noqa: E402


def test_terms_md_and_html_in_sync():
    in_sync, message = check()
    assert in_sync, message
