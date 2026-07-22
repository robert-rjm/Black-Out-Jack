"""
scripts/terms_sync.py
======================
Same tripwire as scripts/rules_sync.py, for the Terms & Disclaimer page.

Tracks SHA256 hashes of docs/Terms.md and templates/terms.html in
docs/.terms_sync.json. tests/app/test_terms_doc_sync.py fails if either file
has changed since the last recorded sync, telling you which side moved so
you can review the other before re-pinning.

docs/Terms.md is the single point of truth (readable directly on GitHub);
templates/terms.html is the styled in-app copy served at /terms. This check
doesn't compare their content directly (one's Markdown, the other's HTML) --
it only flags when one was edited without the other, the same way
rules_sync.py does for docs/Rules.md vs engine/drinking_rules.py.

Usage:
    python scripts/terms_sync.py check    # same check the test runs
    python scripts/terms_sync.py update   # re-pin after confirming alignment
"""
import sys
import os
import hashlib
import json

HERE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS_MD   = os.path.join(HERE, "docs", "Terms.md")
TERMS_HTML = os.path.join(HERE, "templates", "terms.html")
HASH_FILE  = os.path.join(HERE, "docs", ".terms_sync.json")


def _hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def current_hashes() -> dict:
    return {"terms_md": _hash(TERMS_MD), "terms_html": _hash(TERMS_HTML)}


def recorded_hashes() -> dict | None:
    if not os.path.exists(HASH_FILE):
        return None
    with open(HASH_FILE, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Warning: could not parse {HASH_FILE}: {e}", file=sys.stderr)
            return None


def check() -> tuple[bool, str]:
    """Returns (in_sync, message)."""
    current = current_hashes()
    recorded = recorded_hashes()

    if recorded is None:
        return False, (
            "No docs/.terms_sync.json found. Run "
            "`python scripts/terms_sync.py update` once docs/Terms.md and "
            "templates/terms.html are aligned to start tracking."
        )

    md_changed   = current["terms_md"]   != recorded.get("terms_md")
    html_changed = current["terms_html"] != recorded.get("terms_html")

    if not md_changed and not html_changed:
        return True, "docs/Terms.md and templates/terms.html are in sync."

    if md_changed and not html_changed:
        return False, (
            "docs/Terms.md changed but templates/terms.html did not.\n"
            "docs/Terms.md is the source of truth -- update templates/terms.html "
            "to match, then run `python scripts/terms_sync.py update`."
        )

    if html_changed and not md_changed:
        return False, (
            "templates/terms.html changed but docs/Terms.md did not.\n"
            "docs/Terms.md is the source of truth -- update it to match "
            "templates/terms.html's new wording, then run "
            "`python scripts/terms_sync.py update`."
        )

    return False, (
        "Both docs/Terms.md and templates/terms.html changed since the "
        "last sync. After confirming they still say the same thing, run "
        "`python scripts/terms_sync.py update`."
    )


def update() -> None:
    with open(HASH_FILE, "w", encoding="utf-8") as f:
        json.dump(current_hashes(), f, indent=2)
        f.write("\n")
    print(f"Updated {os.path.relpath(HASH_FILE, HERE)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "update":
        update()
    else:
        ok, msg = check()
        print(("OK: " if ok else "WARNING: ") + msg)
        sys.exit(0 if ok else 1)
