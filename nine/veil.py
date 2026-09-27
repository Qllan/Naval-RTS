"""Пелена как единое поле плотности.

Одна функция `density(pos, t)` кормит всё остальное: сенсоры, налёт на корпусе,
урон электронике, выбор ресурсов и спавн врагов. Статическая часть (радиальный
градиент от Ока + шум) считается один раз в сетку, динамическая (течения и
мировые события) добавляется поверх дёшево.
"""

import math
import random

import numpy as np

from pygame.math import Vector2

from . import config as C


def _smooth(t):
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    return a + (b - a) * t


class ValueNoise:
    """Простой 2D value-noise, без внешних зависимостей."""

    def __init__(self, seed, size=64):
        rng = random.Random(seed)
        self.size = size
        self.grid = [[rng.random() for _ in range(size)] for _ in range(size)]

    def sample(self, x, y):
        s = self.size
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = _smooth(x - ix), _smooth(y - iy)
        x0, x1 = ix % s, (ix + 1) % s
        y0, y1 = iy % s, (iy + 1) % s
        g = self.grid
        top = _lerp(g[y0][x0], g[y0][x1], fx)
        bot = _lerp(g[y1][x0], g[y1][x1], fx)
        return _lerp(top, bot, fy)


class Veil:
    def __init__(self, seed=9):
        self.eye = Vector2(C.EYE_POS)
        self.noise = ValueNoise(seed)
        self.cols = C.WORLD_W // C.VEIL_CELL + 1
        self.rows = C.WORLD_H // C.VEIL_CELL + 1
        self.grid = [
            [self._static_density(cx * C.VEIL_CELL, cy * C.VEIL_CELL) for cx in range(self.cols)]
            for cy in range(self.rows)
        ]
        self.np_grid = np.array(self.grid, dtype=np.float64)
        # Внешний источник модификаторов (EventDirector); подключается миром
        self.events = None

    # --- статическая часть ------------------------------------------------

    def _radial(self, x, y):
        d = math.hypot(x - self.eye.x, y - self.eye.y)
        if d < C.EYE_CALM_R - 60:
            return 0.0                       # Зеркало: абсолютный штиль
        if d < C.EYE_CALM_R + 90:
            return _smooth((d - C.EYE_CALM_R + 60) / 150)
        if d < C.EYE_WALL_R:
            return 1.0                       # Стена Рёва
        t = max(0.0, 1.0 - (d - C.EYE_WALL_R) / (C.VEIL_REACH - C.EYE_WALL_R))
        return t ** 1.4

    def _static_density(self, x, y):
        n = self.noise.sample(x / 700.0, y / 700.0) * 0.65 + self.noise.sample(x / 260.0 + 17, y / 260.0 + 5) * 0.35
        radial = self._radial(x, y)
        base = radial + (n - 0.5) * 0.4 * min(1.0, radial * 4)
        return min(1.0, max(0.0, base))

    def static_density(self, x, y):
        """Билинейная выборка из предрасчитанной сетки."""
        gx = min(max(x / C.VEIL_CELL, 0.0), self.cols - 1.001)
        gy = min(max(y / C.VEIL_CELL, 0.0), self.rows - 1.001)
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        g = self.grid
        top = _lerp(g[iy][ix], g[iy][ix + 1], fx)
        bot = _lerp(g[iy + 1][ix], g[iy + 1][ix + 1], fx)
        return _lerp(top, bot, fy)

    # --- динамика ---------------------------------------------------------

    def current(self, x, y, t):
        """«Течение аномалии» — медленно ползущие полосы помех."""
        return 0.08 * math.sin(x * 0.0021 + t * 0.25) * math.cos(y * 0.0017 - t * 0.18)

    def density(self, pos, t):
        x, y = pos[0], pos[1]
        d = self.static_density(x, y)
        if math.hypot(x - self.eye.x, y - self.eye.y) >= C.EYE_CALM_R:
            d += self.current(x, y, t)
        if self.events is not None:
            d += self.events.modifier("density", pos, t)
        return min(1.0, max(0.0, d))

    def density_grid(self, xs, ys, t):
        """Та же плотность, что и density(), но сразу для сетки точек (numpy).

        xs, ys — одномерные массивы координат; результат имеет форму (len(ys), len(xs)).
        """
        X, Y = np.meshgrid(np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64))
        gx = np.clip(X / C.VEIL_CELL, 0.0, self.cols - 1.001)
        gy = np.clip(Y / C.VEIL_CELL, 0.0, self.rows - 1.001)
        ix, iy = gx.astype(np.int64), gy.astype(np.int64)
        fx, fy = gx - ix, gy - iy
        g = self.np_grid
        top = g[iy, ix] + (g[iy, ix + 1] - g[iy, ix]) * fx
        bot = g[iy + 1, ix] + (g[iy + 1, ix + 1] - g[iy + 1, ix]) * fx
        d = top + (bot - top) * fy
        dist = np.hypot(X - self.eye.x, Y - self.eye.y)
        cur = 0.08 * np.sin(X * 0.0021 + t * 0.25) * np.cos(Y * 0.0017 - t * 0.18)
        d = d + np.where(dist >= C.EYE_CALM_R, cur, 0.0)
        if self.events is not None:
            d = d + self.events.modifier_grid("density", X, Y, t)
        return np.clip(d, 0.0, 1.0)

    # --- зоны -------------------------------------------------------------

    def zone(self, pos, density):
        d = math.hypot(pos[0] - self.eye.x, pos[1] - self.eye.y)
        if d < C.EYE_CALM_R:
            return "Око / Зеркало"
        if d < C.EYE_WALL_R:
            return "Стена Рёва"
        if d < C.EYE_BELT_R:
            return "Пояс Разлома"
        if density < C.ZONE_MIST:
            return "Чистый слой"
        if density < C.ZONE_DENSE:
            return "Мгла"
        return "Плотная Пелена"

    def in_wall(self, pos):
        d = math.hypot(pos[0] - self.eye.x, pos[1] - self.eye.y)
        return C.EYE_CALM_R <= d < C.EYE_WALL_R

    def in_dead_zone(self, pos):
        """Мёртвая зона связи: внутри Стены и Зеркала нет карты."""
        return math.hypot(pos[0] - self.eye.x, pos[1] - self.eye.y) < C.EYE_WALL_R
