"""Create real headless port fitting screenshots for R0.5.

Usage:
  python tools/preview_fitting.py --output-dir fitting-previews
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.port_ui import PortUI
from nine.ship import Ship
from nine.world import World


def render(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pygame.init()
    paths = []
    try:
        world = World(seed=9, first_event=1e9)
        world.captain.credits = 10000
        for key in ("needle", "manta", "bastion"):
            world.player = Ship(key, world.port)
            # Два кадра на корпус: сектор оружия и внутренний реакторный отсек.
            for mode, category in (("weapons", "weapon"), ("systems", "reactor")):
                screen = pygame.Surface((1280, 720))
                screen.fill((14, 28, 36))
                port = PortUI(screen)
                port.tab = 2  # Оснащение
                port.sel = next(i for i, slot in enumerate(world.player.hull.slots)
                                if slot.category == category)
                port.draw(world, dt=0.4)
                output = output_dir / f"fitting-{key}-{mode}.png"
                pygame.image.save(screen, str(output))
                paths.append(output)
        return paths
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="fitting-previews")
    args = parser.parse_args()
    for path in render(args.output_dir):
        print(path)
