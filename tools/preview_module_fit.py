"""Real, headless R1.2 fitting preview: baseline vs alternative full loadouts.

Ships are rendered by their actual hull/turret builders. No gameplay
simulation, purchase operation, game save or server is touched.

Usage: python tools/preview_module_fit.py --output module-fit-r12.png
"""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx.ship_art import R, build_hull, build_turret
from nine.ship import Ship, fit_problems

# Module index: weapon(s), engine, reactor, shield, armor, sensor, utilities.
VARIANTS = {
    "needle": {
        "label": "N-17 / NEEDLE",
        "description": "Patrol gun  ->  interceptor / ECM",
        "changes": {0: "missile_s", 2: "engine_s", 5: "armor_s",
                    7: "ecm", 8: "smoke"},
    },
    "manta": {
        "label": "M-08 / MANTA",
        "description": "Cargo platform  ->  sensor / veil protection",
        "changes": {1: "missile_m", 3: "engine_m2", 4: "reactor_m2",
                    5: "shield_res_m", 6: "armor_comp_m",
                    7: "sensor_m", 8: "ecm", 9: "bioscreen"},
    },
    "bastion": {
        "label": "B-31 / BASTION",
        "description": "Gunline capital ship  ->  missile / EW",
        "changes": {0: "missile_m", 1: "torpedo_m",
                    4: "engine_m2", 5: "reactor_m2",
                    6: "shield_res_m", 7: "armor_comp_m",
                    9: "ecm", 10: "smoke"},
    },
}

BG = (9, 23, 32)
PANEL = (20, 38, 48)
BORDER = (62, 95, 106)
TEXT = (229, 238, 236)
MUTED = (160, 185, 188)
ACCENT = (120, 218, 208)


def variants(key):
    base = Ship(key, (0, 0))
    fit = list(base.fit)
    for index, module_key in VARIANTS[key]["changes"].items():
        fit[index] = module_key
    if fit_problems(base.hull, fit):
        raise ValueError(f"Invalid alternative loadout {key}: {fit_problems(base.hull, fit)}")
    return base, Ship(key, (0, 0), fit=fit)


def ship_image(ship):
    static = tuple((i, m) for i, _, m in ship.modules()
                   if m.category != "weapon")
    master, _ = build_hull(ship.hull.key, "player", static, 0)
    combined = master.copy()
    center = pygame.Vector2(master.get_width() / 2, master.get_height() / 2)
    for w in ship.weapons:
        turret = build_turret(w.defn.key, "player", industrial=True)
        pos = center + pygame.Vector2(w.slot.pos) * R
        combined.blit(turret, turret.get_rect(center=(round(pos.x), round(pos.y))))
    bow_up = pygame.transform.rotate(combined, 90)
    return bow_up.subsurface(bow_up.get_bounding_rect()).copy()


def render(output):
    pygame.init()
    try:
        surface = pygame.Surface((1800, 1470))
        surface.fill(BG)
        heading = pygame.font.Font(None, 55)
        title = pygame.font.Font(None, 31)
        small = pygame.font.Font(None, 25)
        micro = pygame.font.Font(None, 22)
        surface.blit(heading.render("NAVAL-RTS / R1.2 / MODULAR FIT VISUALS",
                                    True, TEXT), (48, 28))
        surface.blit(small.render(
            "Same physical hull and scale within each row / actual pygame renderer",
            True, MUTED), (53, 83))

        for row, key in enumerate(("needle", "manta", "bastion")):
            a, b = variants(key)
            imgs = (ship_image(a), ship_image(b))
            # Identical world scale in both columns of a row.
            scale = min(2.3, 352 / max(img.get_height() for img in imgs),
                        615 / max(img.get_width() for img in imgs))
            top = 126 + row * 440
            for col, (ship, image) in enumerate(zip((a, b), imgs)):
                left = 40 + col * 888
                box = pygame.Rect(left, top, 864, 420)
                pygame.draw.rect(surface, PANEL, box, border_radius=9)
                pygame.draw.rect(surface, BORDER, box, 2, border_radius=9)
                caption = ("BASE / STOCK" if col == 0 else "ALTERNATIVE / REFITTED")
                surface.blit(title.render(f"{VARIANTS[key]['label']}    {caption}",
                                          True, TEXT), (left + 20, top + 14))
                w, h = max(1, round(image.get_width() * scale)), max(1, round(image.get_height() * scale))
                scaled = pygame.transform.smoothscale(image, (w, h))
                surface.blit(scaled, scaled.get_rect(center=(left + 432, top + 210)))
                pygame.draw.line(surface, BORDER, (left + 22, top + 366),
                                 (left + 842, top + 366))
                line = (VARIANTS[key]["description"] if col else
                        "Original module positions / baseline weapons")
                surface.blit(micro.render(line, True, ACCENT if col else MUTED),
                             (left + 24, top + 379))
        surface.blit(small.render(
            "Weapons + systems + utilities are installed at real indexed slots / simulation unchanged",
            True, MUTED), (48, 1451))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, str(output))
        return output
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="module-fit-r12.png")
    args = parser.parse_args()
    print(render(args.output))
