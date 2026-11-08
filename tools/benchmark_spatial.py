"""Non-interactive, deterministic broad-phase candidate-count benchmark.

No UI, gameplay loop, combat simulation, or wall-clock pass/fail thresholds.
Run: python tools/benchmark_spatial.py --check
"""

import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pygame.math import Vector2

from nine.spatial import ShipCollisionGrid


def measure(seed=1209, ships_count=120, probes_count=1500):
    rng = random.Random(seed)
    ships = [SimpleNamespace(pos=Vector2(rng.uniform(0, 10000),
                                         rng.uniform(0, 10000)),
                             radius=rng.uniform(10, 35), alive=True)
             for _ in range(ships_count)]
    probes = [Vector2(rng.uniform(0, 10000), rng.uniform(0, 10000))
              for _ in range(probes_count)]
    grid = ShipCollisionGrid(ships)
    candidates = sum(len(grid.candidates(pos)) for pos in probes)
    brute_force = ships_count * probes_count
    ratio = candidates / brute_force if brute_force else 0.0
    print(f"Targets: {ships_count} | Queries: {probes_count} | "
          f"Broad-phase candidates: {candidates} / {brute_force} "
          f"({ratio:.2%} of brute-force tests)")
    return ratio


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Require a strong candidate reduction on seeded sparse data")
    args = parser.parse_args()
    ratio = measure()
    if args.check and ratio >= 0.05:
        raise SystemExit("Spatial grid failed the synthetic reduction check")
