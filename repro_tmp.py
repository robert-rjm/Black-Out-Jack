import io, contextlib
from scripts.simulation import run_simulation

r = run_simulation(num_players=2, num_decks=1, num_rounds=20, seed=42)
print("OK", type(r), len(r))
