"""Generate an authentic R1.1 Bastion before/after review with game ship renderer.

The 'before' geometry is the last approved R1.1 visual data. The tool
temporarily substitutes art-only HullVisual and PROFILES during rendering,
then restores them. No gameplay data, saves, or world simulation change.

Usage:
    python tools/preview_bastion_compare.py --output bastion-before-after.png
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
from nine.hulls import DeckDetail, HULLS
from nine.ship import Ship

OLD_PROFILE = ((35, 0), (31, 3.7), (26, 8.3), (17, 11.3),
               (10, 13), (-9, 13.5), (-21, 14),
               (-28, 11), (-33, 8), (-36, 0))
OLD_SUPERSTRUCTURES = ((-5, 0, 15, 10, True),
                       (-17, 0, 6, 7, False),
                       (7, 0, 8, 7, False))
OLD_DETAILS = (
    DeckDetail("spine_channel", (0, 0), (36, 2.8)),
    DeckDetail("shoulder_guard", (-9, -12), (12, 1.8)),
    DeckDetail("shoulder_guard", (-9, 12), (12, 1.8)),
    DeckDetail("armor_plate", (10, -8.5), (9, 4)),
    DeckDetail("armor_plate", (10, 8.5), (9, 4)),
    DeckDetail("armor_plate", (-10, -8.5), (9, 4)),
    DeckDetail("armor_plate", (-10, 8.5), (9, 4)),
    DeckDetail("service_hatch", (27, 0), (3.8, 3.2)),
    DeckDetail("radiator", (-30, 0), (6, 4)),
)

BG = (9, 24, 33)
PANEL = (20, 38, 48)
LINE = (58, 89, 104)
LIGHT = (220, 232, 230)
MUTED = (152, 182, 187)
ACCENT = (125, 218, 213)


def assembled_bastion(profile, visual):
    """Use the real hull and turret builders with selected art-only metadata."""
    original = HULLS["bastion"]
    original_profile = PROFILES["bastion"]
    try:
        HULLS["bastion"] = replace(original, visual=visual)
        PROFILES["bastion"] = list(profile)
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
        # In-game bow follows +X; the review sheet shows bow up.
        upright = pygame.transform.rotate(result, 90)
        return upright.subsurface(upright.get_bounding_rect()).copy()
    finally:
        HULLS["bastion"] = original
        PROFILES["bastion"] = original_profile


def render(output):
    pygame.init()
    try:
        hull = HULLS["bastion"]
        old_visual = replace(hull.visual, render_profile=OLD_PROFILE,
                             superstructures=OLD_SUPERSTRUCTURES, details=OLD_DETAILS)
        versions = (assembled_bastion(OLD_PROFILE, old_visual),
                    assembled_bastion(hull.visual.render_profile, hull.visual))
        sheet = pygame.Surface((1180, 840))
        sheet.fill(BG)
        h1 = pygame.font.Font(None, 48)
        h2 = pygame.font.Font(None, 31)
        body = pygame.font.Font(None, 25)
        sheet.blit(h1.render("B-31 BASTION  /  SILHOUETTE REFINEMENT", True, LIGHT), (48, 32))
        sheet.blit(body.render("ACTUAL GAME RENDER  /  EQUAL SCALE  /  TOP DOWN", True, MUTED),
                   (50, 83))

        # Lock a common scale for both images: no independent scaling trick.
        scale = min(1.75, 510 / max(x.get_height() for x in versions),
                    385 / max(x.get_width() for x in versions))
        for i, (img, label, note, beam) in enumerate((
            (versions[0], "BEFORE  /  R1.1", "Wide central slab + squared stern", 14.0),
            (versions[1], "AFTER  /  R1.1.2", "Longer bow + tapered armored hull", 12.5),
        )):
            x = 35 + 565 * i
            box = pygame.Rect(x, 120, 545, 650)
            pygame.draw.rect(sheet, PANEL, box, border_radius=9)
            pygame.draw.rect(sheet, LINE, box, 2, border_radius=9)
            sheet.blit(h2.render(label, True, LIGHT), (x + 28, 142))
            sheet.blit(body.render(note, True, MUTED), (x + 28, 176))
            width = max(1, round(img.get_width() * scale))
            height = max(1, round(img.get_height() * scale))
            scaled = pygame.transform.smoothscale(img, (width, height))
            stage_center = (x + 272, 440)
            sheet.blit(scaled, scaled.get_rect(center=stage_center))
            pygame.draw.line(sheet, LINE, (x + 25, 718), (x + 520, 718))
            measure = f"MAX HALF-BEAM  {beam:.1f}  /  FULL BEAM {beam * 2:.1f}"
            sheet.blit(body.render(measure, True, ACCENT), (x + 28, 732))
        sheet.blit(body.render("MAX BODY WIDTH -10.7%  /  PHYSICS + WEAPON SLOTS UNCHANGED",
                               True, ACCENT), (48, 798))
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(sheet, str(out))
        return out
    finally:
        pygame.quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="bastion-before-after.png")
    args = ap.parse_args()
    print(render(args.output))
