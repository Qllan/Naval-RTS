"""Staged UX 2.0 fitting snapshots from the real PortUI, no gameplay playtest."""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx import ui
from nine.port_ui import PortUI
from nine.ship import Ship
from nine.world import World


SCENES = (
    ("01 / SELECT A SHIP NODE", "manta", "overview"),
    ("02 / PREVIEW & COMPARE", "bastion", "compare"),
    ("03 / OPTIONAL ENGINEERING", "bastion", "blueprint"),
)


def render(output):
    pygame.init()
    try:
        screen = pygame.display.set_mode((1280, 720))
        sheet = pygame.Surface((2616, 1538))
        sheet.fill(ui.PANEL_RGB)
        title = pygame.font.Font(None, 45)
        small = pygame.font.Font(None, 24)
        sheet.blit(title.render("NAVAL-RTS / UX 2.0 / SHIP-FIRST FITTING", True, ui.TEXT),
                   (30, 22))
        sheet.blit(small.render(
            "Actual PortUI / clicks select / only explicit install spends credits / no gameplay",
            True, ui.DIM), (34, 64))
        world = World(seed=9, first_event=1e9)
        world.captain.credits = 12000
        for index, (label, hull, mode) in enumerate(SCENES):
            world.player = Ship(hull, world.port)
            screen.fill(ui.PANEL_RGB)
            port = PortUI(screen)
            port.tab = 2
            port.sel = next(i for i, slot in enumerate(world.player.hull.slots)
                            if slot.category == "reactor")
            if mode == "compare":
                port.picker = True
                port.slot = port.sel
                port.pick_sel = next(
                    i for i, (source, key) in enumerate(port.picker_items(world))
                    if key == "reactor_m2")
            if mode == "blueprint":
                port.blueprint_focus = True
            port.draw(world, 0.4)
            frame_x = 16 + index % 2 * 1292
            frame_y = 100 + index // 2 * 724
            sheet.blit(screen, (frame_x, frame_y))
            pygame.draw.rect(sheet, ui.LINE, (frame_x, frame_y, 1280, 720), 2)
            label_rect = pygame.Rect(frame_x + 12, frame_y + 10, 300, 31)
            pygame.draw.rect(sheet, ui.PANEL_RGB, label_rect)
            pygame.draw.rect(sheet, ui.ACCENT, label_rect, 1)
            sheet.blit(small.render(label, True, ui.TEXT),
                       (label_rect.x + 10, label_rect.y + 7))
        sheet.blit(small.render("USER FLOW: SELECT SLOT  >  PREVIEW CONSEQUENCES  >  INSTALL",
                                True, ui.TEXT), (1345, 1062))
        sheet.blit(small.render("Full mass / energy / layout diagnostics remain behind V.",
                                True, ui.DIM), (1345, 1110))
        sheet.blit(small.render("Weapon slots and saved module indices remain unchanged.",
                                True, ui.DIM), (1345, 1142))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(output))
        return output
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ux-fitting-v2.png")
    args = parser.parse_args()
    print(render(args.output))
