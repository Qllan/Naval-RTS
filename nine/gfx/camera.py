"""Камера с плавным следованием, зумом колесом и тряской."""

import math
import random

from pygame.math import Vector2

ZOOM_MIN, ZOOM_MAX = 0.55, 2.4
ZOOM_DEFAULT = 1.75


class Camera:
    def __init__(self, w, h, zoom=ZOOM_DEFAULT):
        self.w, self.h = w, h
        self.center = Vector2()
        self.zoom = zoom
        self.target_zoom = zoom
        self.shake = 0.0              # амплитуда в пикселях
        self.shake_scale = 1.0        # настройка «Тряска камеры»
        self._shake_off = Vector2()
        self._rng = random.Random(7)

    # --- преобразования ---------------------------------------------------

    def w2s(self, pos):
        """Мир → экран."""
        return (Vector2(pos) - self.center) * self.zoom + Vector2(self.w / 2, self.h / 2) + self._shake_off

    def s2w(self, pos):
        """Экран → мир (для прицеливания мышью)."""
        return (Vector2(pos) - Vector2(self.w / 2, self.h / 2) - self._shake_off) / self.zoom + self.center

    def px(self, length):
        """Мировая длина → пиксели."""
        return length * self.zoom

    def visible(self, pos, margin=60.0):
        """Попадает ли точка (с запасом в мировых единицах) на экран."""
        half_w = self.w / 2 / self.zoom + margin
        half_h = self.h / 2 / self.zoom + margin
        return abs(pos[0] - self.center.x) < half_w and abs(pos[1] - self.center.y) < half_h

    def world_rect(self):
        """(x0, y0, x1, y1) видимой области в мировых координатах."""
        hw, hh = self.w / 2 / self.zoom, self.h / 2 / self.zoom
        return self.center.x - hw, self.center.y - hh, self.center.x + hw, self.center.y + hh

    # --- управление -------------------------------------------------------

    def zoom_by(self, steps):
        self.target_zoom = min(ZOOM_MAX, max(ZOOM_MIN, self.target_zoom * (1.12 ** steps)))

    def add_shake(self, amount):
        self.shake = min(14.0 * self.shake_scale, self.shake + amount * self.shake_scale)

    def update(self, dt, target, lead=Vector2()):
        """Следует за целью с небольшим упреждением по скорости."""
        goal = Vector2(target) + lead
        k = 1.0 - math.exp(-8.0 * dt)
        self.center += (goal - self.center) * k
        self.zoom += (self.target_zoom - self.zoom) * (1.0 - math.exp(-10.0 * dt))
        if self.shake > 0.05:
            ang = self._rng.uniform(0, 360)
            self._shake_off = Vector2(1, 0).rotate(ang) * self.shake
            self.shake *= math.exp(-9.0 * dt)
        else:
            self.shake = 0.0
            self._shake_off = Vector2()

    def snap(self, target):
        self.center = Vector2(target)
