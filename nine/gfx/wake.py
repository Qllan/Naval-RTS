"""Кильватер и буруны.

След Кельвина: за кормой расходятся два «уса» под углом ~19.5° к курсу, между ними —
полоса взбитой воды. Храним историю точек у кормы и рисуем по ней линии, которые
расползаются и бледнеют со временем. У носа на ходу — отвальные волны («усы»).
"""

import math
from collections import deque

import pygame
from pygame.math import Vector2

from . import palette as P
from .ship_art import PROFILES

SAMPLE_DT = 0.07
LIFE = 4.5
KELVIN = math.tan(math.radians(19.5))


def ts_phase(trail):
    return trail[0][0] * 3.0 if trail else 0.0


class Wakes:
    def __init__(self):
        self.trails = {}            # id(ship) → deque[(время, точка кормы, курс, скорость)]
        self._acc = 0.0

    def update(self, ships, t, dt):
        self._acc += dt
        take = self._acc >= SAMPLE_DT
        if take:
            self._acc = 0.0
        alive = set()
        for s in ships:
            key = id(s)
            alive.add(key)
            tr = self.trails.setdefault(key, deque())
            if take and s.speed > 8:
                stern = PROFILES[s.hull.key][-1][0]
                tr.append((t, s.pos + Vector2(stern, 0).rotate(s.angle), s.angle, s.speed,
                           max(y for _, y in PROFILES[s.hull.key])))
            while tr and t - tr[0][0] > LIFE:
                tr.popleft()
        # следы исчезнувших кораблей дотаивают сами
        for key in list(self.trails):
            tr = self.trails[key]
            if key not in alive:
                while tr and t - tr[0][0] > LIFE:
                    tr.popleft()
                if not tr:
                    del self.trails[key]

    def draw(self, screen, cam, t, daylight=1.0):
        foam = P.mix((90, 110, 130), P.FOAM, 0.4 + 0.6 * daylight)
        for tr in self.trails.values():
            if len(tr) < 2:
                continue
            left, right, center = [], [], []
            for (ts, pos, ang, sp, hw) in tr:
                age = t - ts
                perp = Vector2(0, 1).rotate(ang)
                spread = hw * 0.8 + age * sp * KELVIN * 0.55
                left.append((cam.w2s(pos - perp * spread), age, sp))
                right.append((cam.w2s(pos + perp * spread), age, sp))
                center.append((cam.w2s(pos), age, sp, hw))
            # центральная полоса взбитой воды — толще у кормы
            for i, ((a, age_a, sp, hw), (b, _, _, _)) in enumerate(zip(center, center[1:])):
                k = max(0.0, 1.0 - age_a / (LIFE * 0.45)) * min(1.0, sp / 120)
                if k <= 0.02:
                    continue
                # рваная полоса: толщина «дышит» от сегмента к сегменту
                width = hw * (0.5 + 0.35 * (1 - k)) * (0.75 + 0.25 * math.sin(i * 1.7 + ts_phase(tr)))
                col = P.mix(P.OCEAN_MID, foam, 0.32 * k)
                pygame.draw.line(screen, col, a, b, max(1, int(cam.px(width))))
            # «усы» Кельвина
            for arm in (left, right):
                for (a, age_a, sp), (b, _, _) in zip(arm, arm[1:]):
                    k = max(0.0, 1.0 - age_a / LIFE) * min(1.0, sp / 100)
                    if k <= 0.02:
                        continue
                    col = P.mix(P.OCEAN_MID, foam, 0.75 * k)
                    pygame.draw.line(screen, col, a, b, max(1, int(cam.px(1.1 * k + 0.4))))

    @staticmethod
    def bow_wave(screen, cam, ship, daylight=1.0):
        """Отвальные волны у носа: белые дуги, расходящиеся вдоль бортов."""
        sp = ship.speed
        if sp < 25:
            return
        k = min(1.0, sp / max(1.0, ship.base_top_speed()))
        prof = PROFILES[ship.hull.key]
        foam = P.mix((90, 110, 130), P.FOAM, 0.4 + 0.6 * daylight)
        col = P.mix(P.OCEAN_MID, foam, 0.8 * k)
        for side in (-1, 1):
            pts = []
            for i, (x, y) in enumerate(prof[:4]):
                out = 1.0 + 0.25 * k + i * 0.18 * k
                pts.append(cam.w2s(ship.pos + Vector2(x - i * 1.2 * k, side * (y * out + 0.6)).rotate(ship.angle)))
            if len(pts) > 1:
                pygame.draw.lines(screen, col, False, pts, max(1, int(cam.px(1.2 * k + 0.3))))
