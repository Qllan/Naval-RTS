"""UX 2.3: real resized pygame HUD + port scenes with accessible settings.

Generated PNGs show the actual PortUI/Hud classes in different physical
windows; they are not scaled copies of old screenshots. Input coordinates
are also verified by the test suite. No World.update or gameplay session.
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx import ui
from nine.hud import Hud
from nine.hulls import PLAYER_HULLS
from nine.port_ui import PortUI
from nine.render import Renderer
from nine.ship import Ship
from nine.world import World


SCENES = (
    ("port-1024x768.png", (1024, 768), "port", False, False),
    ("port-1600x900-large.png", (1600, 900), "port", True, True),
    ("hud-1024x768.png", (1024, 768), "hud", False, False),
    ("hud-1600x900-large.png", (1600, 900), "hud", True, True),
)


def staged_world():
    world = World(seed=9, first_event=1e9)
    world.t = 120.0
    world.player = Ship("bastion", (3600, 3400), -90)
    world.captain.credits = 12000
    for field in ("islands", "nodes", "loot", "pirates", "tihodonts",
                  "rays", "projectiles", "smokes"):
        setattr(world, field, [])
    return world


def one_scene(screen, world, kind):
    renderer = Renderer(screen)
    renderer.cam.zoom = renderer.cam.target_zoom = 1.4
    renderer.cam.snap(world.player.pos)
    renderer.draw(world)
    if kind == "port":
        port = PortUI(screen)
        port.tab = 1
        port.sel = next(i for i, hull in enumerate(PLAYER_HULLS)
                        if hull.key == "bastion")
        port.draw(world, 0.4)
    else:
        hud = Hud(screen, world)
        hud.help_until = 0
        hud.draw(world, False, renderer.cam, mouse=(-100, -100))
    return screen.copy()


def render(output_dir):
    pygame.init()
    ui.Fonts.reset()
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    try:
        for filename, size, kind, large, colorblind in SCENES:
            ui.configure(opacity=0.9, large_font=large, colorblind=colorblind)
            screen = pygame.display.set_mode(size)
            world = staged_world()
            frame = one_scene(screen, world, kind)
            path = root / filename
            pygame.image.save(frame, str(path))
            paths.append(path)
        return paths
    finally:
        ui.configure(large_font=False, colorblind=False)
        ui.Fonts.reset()
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="ux-responsive")
    args = parser.parse_args()
    for path in render(args.output_dir):
        print(path)
