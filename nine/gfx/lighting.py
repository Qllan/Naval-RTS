"""Динамическое освещение и смена суток.

Карта освещения рисуется в пониженном разрешении: заливка цветом окружающего света,
поверх — источники (радиальные пятна и конусы) с BLEND_ADD. Затем сцена умножается
на карту (BLEND_MULT). Всё, что светится само (трассеры, вспышки, огни), рисуется
уже после умножения и потому остаётся ярким ночью.
"""

import math

import pygame
from pygame.math import Vector2

from . import palette as P

# Окружающий свет по высоте солнца
AMBIENT_NIGHT = (92, 104, 150)     # лунный свет
AMBIENT_DUSK = (236, 170, 146)
AMBIENT_DAY = (255, 255, 255)


def ambient_color(world):
    """Цвет окружающего света: ночь → сумерки (тёплые) → день."""
    e = world.sun_elevation()
    if e >= 0.35:
        return AMBIENT_DAY
    if e >= 0.0:
        return P.mix(AMBIENT_DUSK, AMBIENT_DAY, e / 0.35)
    if e >= -0.2:
        return P.mix(AMBIENT_NIGHT, AMBIENT_DUSK, (e + 0.2) / 0.2)
    return AMBIENT_NIGHT


def sun_shadow(world, zoom):
    """Смещение тени (в пикселях) по положению солнца; ночью теней нет."""
    e = world.sun_elevation()
    if e <= 0.02:
        return None
    az = world.time_of_day * 360 + 90          # солнце идёт по кругу за сутки
    length = min(14.0, 3.0 / max(0.12, e))
    return Vector2(1, 0).rotate(az) * length * zoom * 0.5


def _radial(n=96):
    s = pygame.Surface((n, n))
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            d = math.hypot(x - c, y - c) / c
            k = max(0.0, 1.0 - d)
            v = int(255 * k * k)
            s.set_at((x, y), (v, v, v))
    return s


def _cone(n=192, half_angle=18):
    """Конус прожектора, вершина — в центре левого края, светит вправо."""
    s = pygame.Surface((n, n))
    cy = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            dx, dy = x, y - cy
            dist = math.hypot(dx, dy) / n
            if dist > 1 or dx <= 0:
                continue
            ang = abs(math.degrees(math.atan2(dy, dx)))
            if ang > half_angle:
                continue
            edge = 1.0 - ang / half_angle
            v = int(255 * (1 - dist) ** 1.2 * min(1.0, edge * 2.5))
            s.set_at((x, y), (v, v, v))
    return s


_MASTERS = {}


class Lighting:
    def __init__(self, w, h, scale=2):
        self.w, self.h = w, h
        self.set_scale(scale)
        if "radial" not in _MASTERS:
            _MASTERS["radial"] = _radial()
            _MASTERS["cone"] = _cone()
        self.radial = _MASTERS["radial"]
        self.cone = _MASTERS["cone"]
        self.cache = {}
        self.active = False

    def set_scale(self, scale):
        self.scale = scale
        self.map = pygame.Surface((self.w // scale, self.h // scale))

    def _sprite(self, kind, color, size, angle=0):
        key = (kind, color, size, int(angle) // 3 * 3)
        img = self.cache.get(key)
        if img is None:
            base = self.radial if kind == "radial" else self.cone
            img = pygame.transform.smoothscale(base, (size, size))
            img.fill(color, special_flags=pygame.BLEND_MULT)
            if kind == "cone":
                # вершина конуса должна быть в центре картинки — дополняем слева и поворачиваем
                full = pygame.Surface((size * 2, size))
                full.blit(img, (size, 0))
                img = pygame.transform.rotate(full, -key[3])
            if len(self.cache) > 900:
                self.cache.clear()
            self.cache[key] = img
        return img

    def begin(self, ambient):
        self.active = ambient != AMBIENT_DAY
        if self.active:
            self.map.fill(ambient)
        return self.active

    def light(self, screen_pos, radius_px, color, intensity=1.0):
        """Точечный источник. radius_px — радиус в экранных пикселях."""
        if not self.active or radius_px < 2:
            return
        size = max(4, int(radius_px * 2 / self.scale) // 2 * 2)
        if size > 2048:
            return
        col = tuple(min(255, int(c * intensity)) for c in color)
        col = tuple(c // 8 * 8 for c in col)
        img = self._sprite("radial", col, size)
        pos = (screen_pos[0] / self.scale - size / 2, screen_pos[1] / self.scale - size / 2)
        self.map.blit(img, pos, special_flags=pygame.BLEND_ADD)

    def spot(self, screen_pos, angle, length_px, color):
        """Конус прожектора из точки в направлении angle."""
        if not self.active:
            return
        size = max(8, int(length_px / self.scale) // 4 * 4)
        img = self._sprite("cone", color, size, angle)
        c = (screen_pos[0] / self.scale, screen_pos[1] / self.scale)
        self.map.blit(img, img.get_rect(center=c), special_flags=pygame.BLEND_ADD)

    def apply(self, screen):
        if not self.active:
            return
        big = pygame.transform.smoothscale(self.map, (self.w, self.h))
        screen.blit(big, (0, 0), special_flags=pygame.BLEND_MULT)
