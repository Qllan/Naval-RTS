"""Real headless PortUI captures of UX 2.1 shipyard decision states.

Ships are the actual ShipArt output; no game update, manual playtest or
purchase occurs while capturing the review sheet.
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
from nine.hulls import PLAYER_HULLS
from nine.port_ui import PortUI
from nine.ship import Ship
from nine.world import World

SCENES = (
    ("01 / BROWSE CAPITAL HULL", "bastion", 12000, 0),
    ("02 / SMALL SHIP COMPARISON", "needle", 12000, 0),
    ("03 / NOT ENOUGH CREDITS", "bastion", 300, 0),
    ("04 / ALREADY OWNED", "manta", 12000, 0),
)


def render(output):
    pygame.init()
    try:
        game_screen = pygame.display.set_mode((1280, 720))
        sheet = pygame.Surface((2616, 1596))
        sheet.fill(ui.PANEL_RGB)
        heading = pygame.font.Font(None, 43)
        caption = pygame.font.Font(None, 23)
        sheet.blit(heading.render("NAVAL-RTS  /  UX 2.1  /  SHIPYARD DECISIONS",
                                  True, ui.TEXT), (30, 19))
        sheet.blit(caption.render(
            "REAL PYGAME UI  /  SELECT -> COMPARE -> BUY  /  NO GAMEPLAY",
            True, ui.DIM), (33, 65))
        world = World(seed=9, first_event=1e9)
        for i, (label, hull, credits, debt) in enumerate(SCENES):
            world.player = Ship("manta", world.port)
            world.captain.credits, world.captain.debt = credits, debt
            screen = game_screen
            screen.fill(ui.PANEL_RGB)
            port = PortUI(screen)
            port.tab = 1
            port.sel = next(j for j, item in enumerate(PLAYER_HULLS) if item.key == hull)
            port.draw(world, dt=0.4)
            x, y = 16 + i % 2 * 1292, 100 + i // 2 * 724
            sheet.blit(screen, (x, y))
            pygame.draw.rect(sheet, ui.LINE, (x, y, 1280, 720), 2)
            tab = pygame.Rect(x + 9, y + 8, 332, 29)
            pygame.draw.rect(sheet, ui.PANEL_RGB, tab)
            pygame.draw.rect(sheet, ui.ACCENT, tab, 1)
            sheet.blit(caption.render(label, True, ui.TEXT), (tab.x + 11, tab.y + 5))
        sheet.blit(caption.render(
            "CLICK TO SELECT / ENTER OR BUY TO CONFIRM / NO ACCIDENTAL PURCHASE",
            True, ui.DIM), (35, 1552))
        dest = Path(output)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(dest))
        return dest
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ux-shipyard-v2.png")
    options = parser.parse_args()
    print(render(options.output))
