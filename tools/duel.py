"""Матрица дуэлей для баланса: каждый корпус игрока против каждого типа рейдера.

Игрок — простой бот: кружит, стреляет из всего по ближайшей цели.
Запуск: python tools/duel.py [--seconds 40] [--seeds 3]
"""

import argparse
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pygame.math import Vector2  # noqa: E402

from nine.ai import PIRATE_LOADOUTS, Pirate  # noqa: E402
from nine.hulls import PLAYER_HULLS  # noqa: E402
from nine.ship import Ship  # noqa: E402
from nine.world import Controls, World  # noqa: E402


def duel(hull, loadout, seed, seconds, pos=(3300, 4300)):
    """Возвращает ('win'|'loss'|'draw', время, доля корпуса игрока)."""
    w = World(seed=seed, first_event=1e9)
    w.player = Ship(hull, pos, 0)
    w.pirate_spawn_cd = 1e9
    pr = Pirate(Vector2(pos) + Vector2(450, 0), random.Random(seed), loadout)
    w.pirates = [pr]
    for f in range(int(seconds * 60)):
        ctl = Controls(fire=True, fire2=True, aim=Vector2(pr.ship.pos), throttle=0.6, turn=0.3)
        w.update(1 / 60, ctl)
        if not w.pirates:
            return "win", f / 60, w.player.hp / w.player.hull.hp
        if w.in_capsule:
            return "loss", f / 60, 0.0
    return "draw", seconds, w.player.hp / w.player.hull.hp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()
    loadouts = list(PIRATE_LOADOUTS)
    print(f"{'':16}" + "".join(f"{k:>16}" for k in loadouts))
    for hull in PLAYER_HULLS:
        row = f"{hull.name:16}"
        for lo in loadouts:
            res = [duel(hull.key, lo, s, args.seconds) for s in range(args.seeds)]
            wins = sum(r[0] == "win" for r in res)
            losses = sum(r[0] == "loss" for r in res)
            t = sum(r[1] for r in res if r[0] == "win") / max(1, wins)
            row += f"{f'{wins}W {losses}L {t:4.0f}s':>16}"
        print(row)


if __name__ == "__main__":
    main()
