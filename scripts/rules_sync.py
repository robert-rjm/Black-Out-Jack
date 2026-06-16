"""
scripts/rules_sync.py
======================
Local replacement for the old verify_rules() drift-check.

Tracks SHA256 hashes of docs/Rules.md and engine/drinking_rules.py in
docs/.rules_sync.json. tests/test_rules_doc_sync.py fails if either file
has changed since the last recorded sync, telling you which side moved
so you can review the other before re-pinning.

Usage:
    python scripts/rules_sync.py check    # same check the test runs
    python scripts/rules_sync.py update   # re-pin after confirming alignment
"""
import sys
import os
import hashlib
import json

HERE      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_MD  = os.path.join(HERE, "docs", "Rules.md")
RULES_PY  = os.path.join(HERE, "engine", "drinking_rules.py")
HASH_FILE = os.path.join(HERE, "docs", ".rules_sync.json")


def _hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def current_hashes() -> dict:
    return {"rules_md": _hash(RULES_MD), "drinking_rules_py": _hash(RULES_PY)}


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
            "No docs/.rules_sync.json found. Run "
            "`python scripts/rules_sync.py update` once docs/Rules.md and "
            "engine/drinking_rules.py are aligned to start tracking."
        )

    docs_changed = current["rules_md"] != recorded.get("rules_md")
    code_changed = current["drinking_rules_py"] != recorded.get("drinking_rules_py")

    if not docs_changed and not code_changed:
        return True, "docs/Rules.md and engine/drinking_rules.py are in sync."

    if docs_changed and not code_changed:
        return False, (
            "docs/Rules.md changed but engine/drinking_rules.py did not.\n"
            "Check whether the rule logic in drinking_rules.py needs updating "
            "to match the new docs, then run "
            "`python scripts/rules_sync.py update`."
        )

    if code_changed and not docs_changed:
        return False, (
            "engine/drinking_rules.py changed but docs/Rules.md did not.\n"
            "Check whether docs/Rules.md (and Cheat-Sheet.md / "
            "Comprehensive-Example.md) need updating to describe the new "
            "logic, then run `python scripts/rules_sync.py update`."
        )

    return False, (
        "Both docs/Rules.md and engine/drinking_rules.py changed since the "
        "last sync. After confirming they're still aligned, run "
        "`python scripts/rules_sync.py update`."
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
