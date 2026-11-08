"""R1.4 real UI review sheet: HUD, shipyard, fitting and expanded blueprint.

Calls the real Renderer/Hud/PortUI. Uses staged ship/world state only;
no game controls, game time steps, purchase, saving or manual playtest.
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

W, H = 1280, 720
SCENES = ("COMBAT / HUD", "SHIPYARD / HULL", "FITTING / MODULE COMPARE",
          "ENGINEERING / BLUEPRINT")


def frames(world, screen):
    """Isolated staged captures with all original interaction zones intact."""
    world.t = 120.0
    world.player = Ship("bastion", (3600, 3400), -90)
    world.captain.credits = 12000
    world.pirates = []
    renderer = Renderer(screen)
    renderer.cam.zoom = renderer.cam.target_zoom = 1.5
    renderer.cam.snap(world.player.pos)
    renderer.draw(world)
    hud = Hud(screen, world)
    hud.draw(world, False, renderer.cam, events=(), mouse=(-100, -100))
    yield screen.copy()

    screen.fill(ui.PANEL_RGB)
    world.player = Ship("manta", world.port)
    port = PortUI(screen)
    port.tab = 1
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS) if h.key == "bastion")
    port.draw(world, 0.4)
    yield screen.copy()

    screen.fill(ui.PANEL_RGB)
    port = PortUI(screen)
    port.tab = 2
    port.sel = next(i for i, s in enumerate(world.player.hull.slots)
                    if s.category == "reactor")
    port.slot = port.sel
    port.picker = True
    port.pick_sel = next(i for i, (_, k) in enumerate(port.picker_items(world))
                         if k == "reactor_m2")
    port.draw(world, 0.4)
    yield screen.copy()

    screen.fill(ui.PANEL_RGB)
    port = PortUI(screen)
    port.tab = 2
    port.blueprint_focus = True
    port.sel = next(i for i, s in enumerate(world.player.hull.slots)
                    if s.category == "weapon")
    port.draw(world, 0.4)
    yield screen.copy()


def render(output):
    pygame.init()
    ui.Fonts.reset()
    try:
        surface = pygame.display.set_mode((W, H))
        world = World(seed=9, first_event=1e9)
        images = tuple(frames(world, surface))
        assert len(images) == 4
        sheet = pygame.Surface((2616, 1538))
        sheet.fill(ui.PANEL_RGB)
        heading = pygame.font.Font(None, 45)
        subtitle = pygame.font.Font(None, 22)
        sheet.blit(heading.render("NAVAL-RTS  /  R1.4  /  ENGINEERING INTERFACE",
                                  True, ui.TEXT), (32, 17))
        sheet.blit(subtitle.render("ACTUAL PYGAME UI  /  NO PLAYTEST  /  1280 x 720 SOURCE PANELS",
                                   True, ui.DIM), (34, 57))
        for i, (title, frame) in enumerate(zip(SCENES, images)):
            x, y = 16 + (i % 2) * 1292, 100 + (i // 2) * 722
            sheet.blit(frame, (x, y))
            pygame.draw.rect(sheet, ui.LINE, (x, y, W, H), 1)
            tab = pygame.Rect(x + 8, y + 8, 252, 26)
            pygame.draw.rect(sheet, ui.PANEL_RGB, tab)
            pygame.draw.rect(sheet, ui.ACCENT, tab, 1)
            sheet.blit(subtitle.render(title, True, ui.TEXT), (tab.x + 12, tab.y + 5))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(output))
        return output
    finally:
        ui.Fonts.reset()
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ui-r14.png")
    args = parser.parse_args()
    print(render(args.output))
