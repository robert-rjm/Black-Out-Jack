"""
scripts/_cli.py -- Shared CLI input helpers for terminal scripts.

Imported by play_terminal.py, play_referee.py, and simulation.py.
"""


def safe_int(prompt: str, default: int, lo: int = 1, hi: int = 999) -> int:
    """Prompt for an integer in [lo, hi]. Returns default on empty input or EOF."""
    while True:
        try:
            raw = input(prompt).strip().rstrip(".,:;")
        except EOFError:
            return default
        if not raw:
            return default
        try:
            val = int(raw)
        except ValueError:
            print("  Please enter a number.")
            continue
        if lo <= val <= hi:
            return val
        print(f"  Please enter a number between {lo} and {hi}.")


def yes_no(prompt: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer. Returns default on empty input or EOF."""
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        raw = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw.startswith("y")
