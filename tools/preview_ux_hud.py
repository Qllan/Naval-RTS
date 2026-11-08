"""UX 2.2 — staged real Renderer.draw + Hud.draw visual review.

All states are produced with real ship data, true HUD logic, and controlled
visual-only stimuli for emergency conditions. No World.update(), save,
purchase or interactive gameplay session is performed.
"""

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx import ui
from nine.hud import Hud
from nine.render import Renderer
from nine.ship import Ship
from nine.world import World

W, H = 1280, 720
SCENES = (
    ("01 / NAVIGATION", "manta", (1850, 6150), "cruise"),
    ("02 / DENSE VEIL", "bastion", (6400, 3220), "hazard"),
    ("03 / INCOMING MISSILE", "bastion", (3800, 4100), "missile"),
    ("04 / SHIP EMERGENCY", "bastion", (3800, 4100), "critical"),
)


def scene(world, surface, hull, position, state):
    p = Ship(hull, position, -90)
    world.player = p
    world.t = 120.0
    world.log.clear()
    world.pirates = []
    world.phantoms = []
    world.projectiles = []
    world.nodes = []
    world.loot = []
    world.tihodonts = []
    world.rays = []
    world.smokes = []
    world.islands = []

    if state == "critical":
        p.hp = p.hull.hp * 0.24
        p.armor = min(p.armor, p.armor_max * 0.25)
        p.fires = 2
        p.water = 0.3
    renderer = Renderer(surface)
    renderer.cam.zoom = renderer.cam.target_zoom = 1.55
    renderer.cam.snap(p.pos)
    renderer.draw(world)
    if state == "missile":
        # Only a staged incoming signal; not a spawned live projectile.
        world.projectiles = [
            SimpleNamespace(kind="missile", target=p, lost=False)
        ]
    hud = Hud(surface, world)
    hud.draw(world, False, renderer.cam, events=(), mouse=(-100, -100))
    return surface.copy()


def render(output):
    pygame.init()
    ui.Fonts.reset()
    try:
        surface = pygame.display.set_mode((W, H))
        world = World(seed=9, first_event=1e9)
        sheet = pygame.Surface((2616, 1596))
        sheet.fill(ui.PANEL_RGB)
        large = pygame.font.Font(None, 45)
        small = pygame.font.Font(None, 24)
        sheet.blit(large.render("NAVAL-RTS  /  UX 2.2  /  COMBAT PRIORITIES",
                                True, ui.TEXT), (27, 18))
        sheet.blit(small.render(
            "ACTUAL GAME HUD / STAGED CONDITIONS / NO INTERACTIVE PLAYTEST",
            True, ui.DIM), (31, 64))
        for i, (title, hull, pos, state) in enumerate(SCENES):
            frame = scene(world, surface, hull, pos, state)
            x, y = 16 + (i % 2) * 1292, 100 + (i // 2) * 724
            sheet.blit(frame, (x, y))
            pygame.draw.rect(sheet, ui.LINE, (x, y, W, H), 2)
            badge = pygame.Rect(x + 10, y + 8, 295, 28)
            pygame.draw.rect(sheet, ui.PANEL_RGB, badge)
            pygame.draw.rect(sheet, ui.ACCENT, badge, 1)
            sheet.blit(small.render(title, True, ui.TEXT),
                       (badge.x + 10, badge.y + 5))
        sheet.blit(small.render(
            "HEALTH + POWER + WEAPON READINESS STAY / ROUTINE DATA YIELDS TO DANGER",
            True, ui.DIM), (28, 1572))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(output))
        return output
    finally:
        ui.Fonts.reset()
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ux-hud-v22.png")
    args = parser.parse_args()
    print(render(args.output))
