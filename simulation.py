"""
simulation.py  (entry-point shim)
===================================
Simulation logic lives in scripts/simulation.py.
Run:
    python simulation.py
    python scripts/simulation.py
"""
import scripts.simulation  # noqa: F401 — side-effectful entry point

if __name__ == "__main__":
    import runpy
    runpy.run_path("scripts/simulation.py", run_name="__main__")
