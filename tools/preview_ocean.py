"""R1.3 art review: real headless Renderer.draw scenes, without gameplay.

Positions are staged to show clear sea, dense Veil and the low-quality mode.
No game controls, World.update(), save files or server traffic are used.
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
from pygame.math import Vector2

from nine.gfx import palette as P
from nine.gfx.style_tokens import rgb
from nine.render import Renderer
from nine.ship import Ship
from nine.world import World


def scene(world, surface, hull, position, low_quality=False):
    world.t = 120.0  # daylight for comparable materials, no simulation step
    world.player = Ship(hull, position, -90)
    world.player.vel = Vector2(0, -90)
    renderer = Renderer(surface)
    renderer.cam.zoom = renderer.cam.target_zoom = 1.35
    renderer.cam.snap(world.player.pos)
    if low_quality:
        renderer.toggle_quality()
    # Sample only the visual wake history; no physics or world update.
    end = Vector2(position)
    for i in range(10):
        world.player.pos = end + Vector2(0, (9 - i) * 7)
        renderer.wakes.update([world.player], 119.25 + i * 0.075, 0.075)
    world.player.pos = end
    renderer.draw(world)
    return surface.copy()


def render(output):
    pygame.init()
    try:
        w, h = 780, 439
        screen = pygame.display.set_mode((w, h))
        world = World(seed=9, first_event=1e9)
        for attr in ("islands", "nodes", "loot", "pirates", "tihodonts",
                     "rays", "projectiles", "smokes"):
            setattr(world, attr, [])
        stage = pygame.Surface((1620, 1090))
        stage.fill(rgb("ui_bg"))
        big = pygame.font.Font(None, 45)
        medium = pygame.font.Font(None, 28)
        small = pygame.font.Font(None, 23)
        stage.blit(big.render("NAVAL-RTS  /  OCEAN + VEIL  /  R1.3",
                              True, rgb("ui_text")), (39, 25))
        stage.blit(small.render("ACTUAL GAME RENDERER / STAGED SCENES / NO PLAYTEST",
                                True, rgb("ui_muted")), (41, 76))
        configs = (
            ("OPEN WATER", "manta", (1600, 6200), False,
             "Dark steel ocean and legible hull"),
            ("DENSE VEIL", "bastion", (6400, 3200), False,
             "Cold cyan mist with restrained shimmer"),
            ("DENSE / LOW QUALITY", "bastion", (6400, 3200), True,
             "Fewer wake and sea details, same visibility rules"),
        )
        for i, (name, hull, pos, low, detail) in enumerate(configs):
            col, row = i % 2, i // 2
            x, y = 24 + col * 807, 122 + row * 480
            frame = scene(world, screen, hull, pos, low_quality=low)
            stage.blit(frame, (x, y))
            pygame.draw.rect(stage, rgb("ui_line"), (x, y, w, h), 2)
            pygame.draw.rect(stage, rgb("ui_panel"), (x, y, w, 35))
            stage.blit(medium.render(name, True, rgb("ui_text")), (x + 17, y + 6))
            stage.blit(small.render(detail, True, rgb("ui_muted")),
                       (x + 10, y + h + 5))
        x, y = 831, 602
        pygame.draw.rect(stage, rgb("ui_panel"), (x, y, 780, 439), border_radius=7)
        stage.blit(medium.render("LIVE STYLE-BIBLE PALETTE", True, rgb("ui_text")),
                   (x + 25, y + 20))
        for index, (name, color) in enumerate((
            ("DEEP OCEAN", P.OCEAN_DEEP), ("MID OCEAN", P.OCEAN_MID),
            ("WAVE RIDGE", P.OCEAN_LIGHT), ("VEIL MIST", P.VEIL_WISP),
            ("ANOMALY GLOW", P.VEIL_GLOW))):
            yy = y + 69 + index * 64
            pygame.draw.rect(stage, color, (x + 30, yy, 130, 42), border_radius=4)
            stage.blit(small.render(name, True, rgb("ui_text")), (x + 185, yy + 11))
        stage.blit(small.render("GRAPHICS ONLY / SIMULATION UNCHANGED", True,
                                rgb("ui_muted")), (x + 27, y + 401))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(stage, str(output))
        return output
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ocean-veil-r13.png")
    args = parser.parse_args()
    print(render(args.output))
