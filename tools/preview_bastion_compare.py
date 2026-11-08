"""Render R1.1.2 -> R1.1.3 Bastion from real in-game hull/turret art.

Old ship geometry and modules are temporarily substituted for the
left panel, and restored before the right panel. Both images use the
same world-units-to-pixels scale, without changing any saved state.

Usage: python tools/preview_bastion_compare.py --output bastion-before-after.png
"""

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx.ship_art import PROFILES, R, build_hull, build_turret
from nine.hulls import DeckDetail, HULLS, Slot
from nine.modules import M, S
from nine.ship import Ship

# R1.1.2 exact previous geometry and art. Kept here ONLY for before/after.
OLD_SHAPE = ((35, 0), (27, 8), (13, 13), (-23, 14), (-34, 8), (-36, 0),
             (-34, -8), (-23, -14), (13, -13), (27, -8))
OLD_PROFILE = ((35, 0), (31, 2.4), (26, 6.4), (17, 9.95),
               (10, 11.8), (-9, 12.4), (-21, 12.5),
               (-28, 9.6), (-33, 5.6), (-36, 0))
OLD_WEAPON_SLOTS = (
    Slot("weapon", M, (19, 0), 0, 265),
    Slot("weapon", M, (-22, 0), 180, 265),
    Slot("weapon", S, (0, -11), -90, 180),
    Slot("weapon", S, (0, 11), 90, 180),
)
OLD_SUPERSTRUCTURES = ((-5, 0, 16, 8.6, True),
                       (-17, 0, 7, 6.6, False),
                       (7, 0, 8, 6.4, False))
OLD_DETAILS = (
    DeckDetail("spine_channel", (0, 0), (36, 2.8)),
    DeckDetail("shoulder_guard", (-9, -10.65), (14, 1.6)),
    DeckDetail("shoulder_guard", (-9, 10.65), (14, 1.6)),
    DeckDetail("armor_plate", (10, -8.5), (9, 4)),
    DeckDetail("armor_plate", (10, 8.5), (9, 4)),
    DeckDetail("armor_plate", (-10, -8.5), (9, 4)),
    DeckDetail("armor_plate", (-10, 8.5), (9, 4)),
    DeckDetail("service_hatch", (27, 0), (3.8, 3.2)),
    DeckDetail("radiator", (-30, 0), (6, 4)),
)

BG, PANEL, LINE = (9, 24, 33), (20, 38, 48), (58, 89, 104)
LIGHT, MUTED, ACCENT = (220, 232, 230), (152, 182, 187), (125, 218, 213)


def assembled_bastion(hull):
    """Use real hull builder, exact hull/weapon mount layout and modules."""
    original = HULLS["bastion"]
    original_profile = PROFILES["bastion"]
    try:
        HULLS["bastion"] = hull
        PROFILES["bastion"] = list(hull.visual.render_profile)
        ship = Ship("bastion", (0, 0))
        static = tuple((mod.key, mod) for _, _, mod in ship.modules()
                       if mod.category in ("armor", "engine", "utility"))
        master, _ = build_hull("bastion", "player", static, 0)
        result = master.copy()
        center = pygame.Vector2(master.get_width() / 2, master.get_height() / 2)
        for weapon in ship.weapons:
            turret = build_turret(weapon.defn.key, "player", industrial=True)
            offset = pygame.Vector2(weapon.slot.pos) * R
            result.blit(turret, turret.get_rect(center=(
                round(center.x + offset.x), round(center.y + offset.y))))
        upright = pygame.transform.rotate(result, 90)  # +X bow -> upwards
        return upright.subsurface(upright.get_bounding_rect()).copy()
    finally:
        HULLS["bastion"] = original
        PROFILES["bastion"] = original_profile


def render(output):
    pygame.init()
    try:
        current = HULLS["bastion"]
        old_visual = replace(current.visual, render_profile=OLD_PROFILE,
                             superstructures=OLD_SUPERSTRUCTURES,
                             mast=(-5, 0),
                             deck_ribs=(-30, -20, -10, 0, 10, 20, 30),
                             deck_strips=(0.38, 0.72), details=OLD_DETAILS)
        previous = replace(current, shape=OLD_SHAPE, radius=30,
                           hp=280, mass=185, speed_mult=0.82, turn_rate=76,
                           price=2500,
                           slots=OLD_WEAPON_SLOTS + current.slots[4:],
                           visual=old_visual)
        before, after = assembled_bastion(previous), assembled_bastion(current)
        images = (before, after)

        sheet = pygame.Surface((1180, 840))
        sheet.fill(BG)
        heading = pygame.font.Font(None, 46)
        sub = pygame.font.Font(None, 29)
        desc = pygame.font.Font(None, 24)
        sheet.blit(heading.render("B-31 BASTION  /  CAPITAL HULL REFRAME", True, LIGHT), (43, 32))
        sheet.blit(desc.render("SAME PIXELS PER GAME UNIT   /   REAL GAME ART", True, MUTED), (47, 84))
        scale = min(2.3, 490 / max(im.get_height() for im in images),
                    360 / max(im.get_width() for im in images))
        for index, (image, title, note, dimensions, stats) in enumerate((
            (before, "BEFORE  R1.1.2", "Short and wide", "71 x 25", "280 HP  /  185 MASS"),
            (after, "AFTER  R1.1.3", "Long and narrow capital ship", "114 x 24", "340 HP  /  230 MASS"),
        )):
            left = 35 + index * 565
            stage = pygame.Rect(left, 122, 545, 650)
            pygame.draw.rect(sheet, PANEL, stage, border_radius=9)
            pygame.draw.rect(sheet, LINE, stage, 2, border_radius=9)
            sheet.blit(sub.render(title, True, LIGHT), (left + 27, 140))
            sheet.blit(desc.render(note, True, MUTED), (left + 27, 172))
            w, h = max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale))
            img = pygame.transform.smoothscale(image, (w, h))
            sheet.blit(img, img.get_rect(center=(left + 272, 443)))
            pygame.draw.line(sheet, LINE, (left + 25, 709), (left + 520, 709))
            sheet.blit(desc.render("LENGTH x WIDTH  " + dimensions, True, ACCENT), (left + 27, 722))
            sheet.blit(desc.render(stats, True, MUTED), (left + 27, 746))
        sheet.blit(desc.render(
            "114:24 = 4.75:1   /   NEW PHYSICAL HULL + MOUNT LAYOUT   /   SAVE SLOT IDS STABLE",
            True, ACCENT), (47, 803))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(output))
        return output
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="bastion-before-after.png")
    args = parser.parse_args()
    print(render(args.output))
