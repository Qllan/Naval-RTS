"""Deterministic network-foundation index benchmark (no real client, no playtest).

Run python tools/check_network_foundation.py --check
"""

import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pygame.math import Vector2

from nine.spatial import PositionGrid


def measure(seed=505, entity_count=1000, viewer_count=100, radius=900):
    rng = random.Random(seed)
    entities = [SimpleNamespace(pos=Vector2(rng.uniform(0, 16000),
                                            rng.uniform(0, 16000)))
                for _ in range(entity_count)]
    viewers = [Vector2(rng.uniform(0, 16000), rng.uniform(0, 16000))
               for _ in range(viewer_count)]
    index = PositionGrid(entities)
    candidate_checks = sum(1 for center in viewers
                           for _ in index.cell_candidates(center, radius))
    reference_checks = entity_count * viewer_count
    ratio = candidate_checks / reference_checks
    print(f"NETWORK INTEREST | entities={entity_count}, observers={viewer_count}, "
          f"cells_checked_candidates={candidate_checks}/{reference_checks} "
          f"({ratio:.2%} of full scan)")
    # Deterministic small correctness sample: ordered exact radius lookup.
    for center in viewers[:10]:
        expected = []
        for i, entity in enumerate(entities):
            d = entity.pos - center
            d2 = d.length_squared()
            if d2 <= radius * radius:
                expected.append((d2, i, entity))
        expected.sort(key=lambda t: (t[0], t[1]))
        assert index.query_radius(center, radius) == expected
    return ratio


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    ratio = measure()
    if args.check and ratio >= 0.125:
        raise SystemExit("Unexpectedly high candidate ratio")
