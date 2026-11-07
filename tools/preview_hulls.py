"""Build a review sheet of the new industrial sci-fi hulls.

Usage: python tools/preview_hulls.py --output hull-preview.png
This is a headless PNG preview for art direction reviews; no game save is touched.
"""
import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Allow running the tool directly: python tools/preview_hulls.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from nine.gfx.ship_art import R, build_hull, build_turret
from nine.ship import Ship


MODELS = (
    ("needle", "N-17  /  NEEDLE", "Sensor rails  ·  slim patrol frame"),
    ("manta", "M-08  /  MANTA", "Cargo cells  ·  broad utility deck"),
    ("bastion", "B-31  /  BASTION", "Armor plates  ·  reinforced battleship"),
)
BACKGROUND = (13, 26, 35)
PANEL = (20, 36, 45)
EDGE = (70, 98, 109)
MAIN = (216, 226, 229)
MUTED = (130, 163, 169)
ACCENT = (95, 168, 173)


def render(output):
    pygame.init()
    try:
        surface = pygame.Surface((1500, 820))
        surface.fill(BACKGROUND)
        heading = pygame.font.Font(None, 44)
        label = pygame.font.Font(None, 36)
        small = pygame.font.Font(None, 25)
        text = heading.render("NAVAL-RTS  /  HULL DESIGN STUDY R0.3", True, MAIN)
        surface.blit(text, (52, 38))
        sub = small.render("Three constructions, one modular fitting system", True, MUTED)
        surface.blit(sub, (55, 87))

        for i, (key, name, tagline) in enumerate(MODELS):
            x, y, width, height = 38 + i * 493, 132, 466, 636
            pygame.draw.rect(surface, PANEL, (x, y, width, height), border_radius=10)
            pygame.draw.rect(surface, EDGE, (x, y, width, height), 2, border_radius=10)
            pygame.draw.line(surface, ACCENT, (x + 22, y + 25), (x + 76, y + 25), 3)
            title = label.render(name, True, MAIN)
            surface.blit(title, (x + 22, y + 42))
            desc = small.render(tagline, True, MUTED)
            surface.blit(desc, (x + 22, y + 85))

            ship = Ship(key, (0, 0))
            static = tuple((m.key, m) for _, _, m in ship.modules()
                           if m.category in ("armor", "engine", "utility"))
            master, _ = build_hull(key, "player", static, 0)
            assembled = pygame.Surface(master.get_size(), pygame.SRCALPHA)
            assembled.blit(master, (0, 0))
            center = pygame.Vector2(master.get_width() / 2, master.get_height() / 2)
            for weapon in ship.weapons:
                turret = build_turret(weapon.defn.key, "player")
                pos = center + pygame.Vector2(weapon.slot.pos) * R
                assembled.blit(turret, turret.get_rect(center=(round(pos.x), round(pos.y))))

            # The hull is defined with its bow along +X; rotate to bow-up.
            topdown = pygame.transform.rotate(assembled, 90)
            factor = min(1.0, 406 / topdown.get_width(), 449 / topdown.get_height())
            scaled = pygame.transform.smoothscale(
                topdown,
                (max(1, round(topdown.get_width() * factor)),
                 max(1, round(topdown.get_height() * factor))),
            )
            stage = pygame.Rect(x + 20, y + 126, width - 40, 445)
            surface.blit(scaled, scaled.get_rect(center=stage.center))
            pygame.draw.line(surface, EDGE, (x + 22, y + 580), (x + width - 22, y + 580))
            slot_count = sum(s.category == "weapon" for s in ship.hull.slots)
            bottom = f"{slot_count} weapon mounts  |  {len(ship.hull.slots)} total module slots"
            surface.blit(small.render(bottom, True, MUTED), (x + 22, y + 594))
        surface.blit(small.render("Preview only  ·  hulls and modules rendered by the game code", True, MUTED),
                     (50, 789))
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(surface, str(output))
        return output
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="hull-preview.png")
    args = parser.parse_args()
    print(render(args.output))
