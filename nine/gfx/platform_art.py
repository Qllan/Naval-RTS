"""Visible trading platform: fixed sea-station silhouette, docking aids, night lamps.

Procedural Pygame geometry, separate from the Refugee Port artwork.
"""
import math

import pygame
from pygame.math import Vector2

from .. import config as C


PLATFORM_EXTENT = 112
LAMP_OFFSETS = ((-64, -24), (64, -24), (-64, 34), (64, 34))
BEACON_OFFSETS = ((0, -86), (-100, 0), (100, 0))


def platform_lights(world):
    """Stable lighting locations for nighttime lighting and fog glows."""
    pos = world.platform
    lights = [(pos + Vector2(x, y), (120, 225, 240), 90)
              for x, y in LAMP_OFFSETS]
    lights.extend((pos + Vector2(x, y), (255, 193, 83), 55)
                  for x, y in BEACON_OFFSETS
                  if (int(world.t * 1.5) + int(abs(x))) % 3 == 0)
    return lights


class TradePlatformArt:
    """Small cached world-space station with visible approach and docks."""

    def __init__(self):
        self.master = None
        self.scaled = {}

    @staticmethod
    def _build():
        unit = 3
        extent = PLATFORM_EXTENT
        surface = pygame.Surface((extent * 2 * unit, extent * 2 * unit),
                                 pygame.SRCALPHA)

        def pt(x, y):
            return (round((x + extent) * unit),
                    round((y + extent) * unit))

        def poly(points, color, width=0):
            pygame.draw.polygon(surface, color, [pt(*p) for p in points],
                                width)

        # Central steel island surrounded by open-water approach buoys.
        poly([(-77, -29), (-59, -43), (59, -43), (77, -29),
              (77, 45), (57, 59), (-57, 59), (-77, 45)], (17, 32, 42))
        poly([(-75, -31), (-60, -46), (60, -46), (75, -31),
              (75, 41), (59, 56), (-59, 56), (-75, 41)], (58, 88, 101))
        for x in range(-55, 65, 15):
            pygame.draw.line(surface, (73, 103, 113),
                             pt(x, -37), pt(x, 49), 1)
        for y in range(-30, 52, 12):
            pygame.draw.line(surface, (42, 70, 82),
                             pt(-65, y), pt(65, y), 1)

        # Twin northern loading piers. Open area remains for ship approach.
        for x in (-43, 43):
            poly([(x - 10, -45), (x + 10, -45),
                  (x + 10, -89), (x - 10, -89)], (105, 114, 113))
            pygame.draw.line(surface, (236, 185, 82),
                             pt(x - 10, -84), pt(x + 10, -84), 2)
            for y in (-75, -60):
                pygame.draw.circle(surface, (20, 31, 36), pt(x - 10, y), 4)
                pygame.draw.circle(surface, (20, 31, 36), pt(x + 10, y), 4)

        # Container stacks, command tower, radar and cargo cranes.
        for x, color in ((-42, (128, 113, 80)), (-12, (70, 121, 145)),
                         (19, (148, 90, 66))):
            pygame.draw.rect(surface, color,
                             pygame.Rect(*pt(x - 11, -10), 22 * unit, 31 * unit))
            for y in (-4, 4, 12):
                pygame.draw.line(surface, (36, 57, 67),
                                 pt(x - 11, y), pt(x + 11, y), 1)

        pygame.draw.circle(surface, (24, 34, 42), pt(47, 29), 21 * unit)
        pygame.draw.circle(surface, (120, 151, 158), pt(45, 27), 18 * unit)
        pygame.draw.circle(surface, (198, 212, 208), pt(45, 27), 8 * unit, 3)
        pygame.draw.line(surface, (204, 216, 209),
                         pt(45, 17), pt(45, 6), 3)
        for x in (-60, 60):
            pygame.draw.line(surface, (207, 166, 68),
                             pt(x, 28), pt(x, -33), 5)
            pygame.draw.line(surface, (207, 166, 68),
                             pt(x, -33), pt(x + (-25 if x > 0 else 25), -57), 3)

        # Four distinct navigation lamps, visible even without world lighting.
        for x, y in LAMP_OFFSETS:
            pygame.draw.circle(surface, (133, 236, 246), pt(x, y), 4)
        return surface

    def draw(self, screen, cam, world, font):
        pos = world.platform
        if not cam.visible(pos, PLATFORM_EXTENT + 45):
            return
        if self.master is None:
            self.master = self._build()
        zq = round(cam.zoom / 0.02) * 0.02
        if zq not in self.scaled:
            size = max(4, round(self.master.get_width() * cam.zoom / 3))
            self.scaled[zq] = pygame.transform.smoothscale(
                self.master, (size, size))
            if len(self.scaled) > 8:
                self.scaled.pop(next(iter(self.scaled)))
        image = self.scaled[zq]
        center = cam.w2s(pos)
        screen.blit(image, image.get_rect(center=center))

        # Pulsing ring marks the dockable radius; directional guides face north.
        radius = max(1, round(cam.px(C.PORT_RADIUS)))
        pulse = (int(world.t * 2) % 2) == 0
        pygame.draw.circle(screen, (76, 149, 167), center, radius, 1)
        for i, (x, y) in enumerate(BEACON_OFFSETS):
            active = (int(world.t * 1.5) + i) % 3 == 0
            pygame.draw.circle(screen, (255, 207, 105) if active else
                               (90, 100, 83), cam.w2s(pos + Vector2(x, y)),
                               max(2, round(cam.px(3))))
        if pulse:
            for x, y in LAMP_OFFSETS:
                pygame.draw.circle(screen, (139, 240, 255),
                                   cam.w2s(pos + Vector2(x, y)),
                                   max(1, round(cam.px(2))))
        label = font.render("ТОРГОВАЯ ПЛАТФОРМА", True, (137, 225, 233))
        screen.blit(label, label.get_rect(midtop=cam.w2s(
            pos + Vector2(0, 65))))
