"""Векторные корабли: корпус рисуется один раз в высоком разрешении, поворот и масштаб кэшируются.

Координаты в «единицах корпуса» (как в hulls.py): нос вдоль +X, правый борт — +Y.
Мастер-спрайт рисуется с R пикселей на единицу и сглаживается при уменьшении.
"""

import math
import random
from collections import OrderedDict

import pygame
from pygame.math import Vector2

from .palette import SHIP_PALETTES, mix, shade

R = 4                    # пикселей на единицу в мастер-спрайте
ANGLE_STEP = 2.0         # шаг кэша по углу, град
ZOOM_STEP = 0.05
CACHE_LIMIT = 5000

# Полупрофили корпусов (нос → корма, y ≥ 0); зеркалятся на левый борт
PROFILES = {
    "scout": [(21, 0), (17, 2.6), (10, 5.6), (0, 7), (-12, 7), (-17, 5.6), (-19, 3), (-19, 0)],
    "corvette": [(26, 0), (20, 3.8), (10, 8), (-4, 9.6), (-18, 9.6), (-22, 7), (-23, 0)],
    "torpedo_boat": [(28, 0), (21, 2.8), (9, 6.4), (-10, 7.4), (-18, 7), (-21, 4.2), (-21, 0)],
    "cruiser": [(30, 0), (24, 4.6), (12, 10.2), (-6, 12), (-20, 12), (-26, 9), (-28, 0)],
    "barge": [(25, 0), (23.5, 8.5), (19, 13.5), (-24, 14), (-27, 12), (-27.5, 0)],
    "raider": [(20, 0), (13, 3.6), (4, 8.6), (-6, 9), (-11, 7), (-14, 6.4), (-13, 0)],
    "capsule": [(8.5, 0), (7, 3.6), (3, 5.8), (-3, 5.8), (-7, 3.6), (-8.5, 0)],
}

# Надстройки: (x, y, длина, ширина, окна спереди)
SUPERSTRUCTURE = {
    "scout": [(-5, 0, 9, 7, True)],
    "corvette": [(0, 0, 9, 8.5, True)],
    "torpedo_boat": [(3, 0, 8, 6.5, True)],
    "cruiser": [(3, 0, 12, 10, True), (-5.5, 0, 4, 7, False)],
    "barge": [(-21, 0, 7, 22, True)],
    "raider": [(-9, 0, 6, 7.5, True)],
    "capsule": [(0, 0, 5, 5, True)],
}

FUNNELS = {"corvette": [(-6, 0, 2.2)], "cruiser": [(-5.5, 0, 2.6)], "barge": [(-21, 0, 2.4)]}
LIFEBOATS = {"corvette": [(-3, 1)], "cruiser": [(-2, 1), (-11, 1)], "barge": [(-16, 1)]}
HATCHES = {"barge": [(14, 0, 7, 18), (-8, 0, 7, 18)]}
MAST = {"scout": (-7.5, 0), "corvette": (-3, 0), "torpedo_boat": (1, 0), "cruiser": (5, 0), "barge": (-22.5, 0),
        "raider": (-10, 0), "capsule": (0, 0)}


def outline(key):
    half = PROFILES[key]
    return half + [(x, -y) for x, y in reversed(half[1:-1])]


def _scaled(pts, sx, sy):
    return [(x * sx, y * sy) for x, y in pts]


class _Canvas:
    """Холст мастер-спрайта с переводом координат корпуса в пиксели."""

    def __init__(self, extent):
        self.extent = extent
        size = int(extent * 2 * R)
        self.surf = pygame.Surface((size, size), pygame.SRCALPHA)
        self.c = size / 2

    def p(self, x, y):
        return (self.c + x * R, self.c + y * R)

    def poly(self, pts, color, width=0):
        pygame.draw.polygon(self.surf, color, [self.p(x, y) for x, y in pts], int(width * R) if width else 0)

    def line(self, a, b, color, width=0.4):
        pygame.draw.line(self.surf, color, self.p(*a), self.p(*b), max(1, int(width * R)))

    def circle(self, x, y, r, color, width=0):
        pygame.draw.circle(self.surf, color, self.p(x, y), max(1, int(r * R)), int(width * R) if width else 0)

    def rect(self, x, y, lx, ly, color, width=0, radius=0.6):
        rr = pygame.Rect(0, 0, lx * R, ly * R)
        rr.center = self.p(x, y)
        pygame.draw.rect(self.surf, color, rr, int(width * R) if width else 0, border_radius=int(radius * R))
        return rr


# --- корпус -----------------------------------------------------------------

def build_hull(hull_key, pal_key, static_modules, damage_level):
    """Мастер-спрайт корпуса со статичными модулями и следами повреждений."""
    pal = SHIP_PALETTES[pal_key]
    pts = outline(hull_key)
    extent = max(max(abs(x), abs(y)) for x, y in pts) + 8
    cv = _Canvas(extent)
    bow = PROFILES[hull_key][0][0]
    stern = PROFILES[hull_key][-1][0]

    # борт, затенённая правая половина, планширь
    cv.poly(pts, pal.hull)
    cv.poly([(x, y) for x, y in pts if y >= 0] + [(stern, 0)], shade(pal.hull, 0.78))
    cv.poly(pts, pal.trim, width=0.6)

    # палуба с досками
    deck = _scaled(pts, 0.9, 0.78)
    cv.poly(deck, pal.deck)
    half_w = max(y for _, y in PROFILES[hull_key]) * 0.78
    y = -half_w + 1.6
    while y < half_w:
        cv.line((stern * 0.85, y), (bow * 0.8, y), pal.plank, 0.18)
        y += 1.6
    cv.poly(deck, shade(pal.deck, 0.7), width=0.25)

    # полоса стороны у носа
    if hull_key != "capsule":
        x0 = bow * 0.62
        band = [(x0, -half_w * 0.9), (x0 + 2.2, -half_w * 0.6), (x0 + 2.2, half_w * 0.6), (x0, half_w * 0.9)]
        cv.poly(band, pal.accent)
        if pal_key == "pirate":                       # «зубы» Прилива
            for i in range(-2, 3):
                cv.poly([(x0 + 2.2, i * 1.6 - 0.6), (x0 + 3.6, i * 1.6), (x0 + 2.2, i * 1.6 + 0.6)], pal.accent)

    # грузовые люки
    for hx, hy, lx, ly in HATCHES.get(hull_key, []):
        cv.rect(hx, hy, lx, ly, shade(pal.deck, 0.62), radius=0.4)
        for k in range(1, 4):
            cv.line((hx - lx / 2, hy - ly / 2 + k * ly / 4), (hx + lx / 2, hy - ly / 2 + k * ly / 4),
                    shade(pal.deck, 0.5), 0.2)

    _static_modules(cv, hull_key, pal, static_modules, bow, stern, half_w)

    # надстройки
    for sx, sy, lx, ly, windows in SUPERSTRUCTURE.get(hull_key, []):
        cv.rect(sx + 0.5, sy + 0.7, lx, ly, shade(pal.trim, 0.8), radius=0.8)          # тень
        cv.rect(sx, sy, lx, ly, pal.superstructure, radius=0.8)
        cv.rect(sx - 0.4, sy - 0.4, lx - 1.6, ly - 1.8, pal.roof, radius=0.6)
        if windows:
            n = max(2, int(ly / 1.6))
            for k in range(n):
                wy = sy - ly / 2 + (k + 0.5) * ly / n
                cv.rect(sx + lx / 2 - 0.5, wy, 0.7, ly / n * 0.6, pal.window, radius=0.1)
    for fx, fy, r in FUNNELS.get(hull_key, []):
        cv.circle(fx, fy, r, shade(pal.trim, 0.9))
        cv.circle(fx, fy, r * 0.6, (20, 20, 22))
        cv.circle(fx - r * 0.25, fy - r * 0.25, r * 0.25, shade(pal.superstructure, 0.9))
    for lx, ly in LIFEBOATS.get(hull_key, []):
        for side in (-1, 1):
            by = side * (half_w - 0.8)
            cv.rect(lx, by, 4, 1.4, (215, 120, 60), radius=0.7)
    mx, my = MAST.get(hull_key, (0, 0))
    cv.circle(mx, my, 0.9, shade(pal.trim, 1.2))

    # кнехты по бортам
    if hull_key not in ("capsule",):
        for bx in (bow * 0.35, stern * 0.6):
            for side in (-1, 1):
                cv.circle(bx, side * half_w * 0.92, 0.35, shade(pal.trim, 1.6))

    _damage(cv, hull_key, damage_level, pts, half_w, bow, stern)

    shadow = pygame.Surface(cv.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(shadow, (0, 0, 0, 120), [cv.p(x, y) for x, y in pts])
    small = pygame.transform.smoothscale(shadow, (shadow.get_width() // 6, shadow.get_height() // 6))
    shadow = pygame.transform.smoothscale(small, shadow.get_size())
    return cv.surf, shadow


def _static_modules(cv, hull_key, pal, static_modules, bow, stern, half_w):
    for key, m in static_modules:
        cat = m.category
        if cat == "armor":
            # бронеплиты вдоль бортов
            th = 0.9 if m.size > 1 else 0.55
            for side in (-1, 1):
                x = stern * 0.8
                while x < bow * 0.55:
                    cv.rect(x + 1.4, side * (half_w + 0.35), 2.6, th, pal.armor, radius=0.15)
                    x += 3.2
        elif cat == "engine":
            n = 1 if m.size == 1 else 2
            for k in range(n):
                off = 0 if n == 1 else (-2.2 if k == 0 else 2.2)
                cv.rect(stern + 0.4, off, 1.6, 1.8, (26, 26, 28), radius=0.4)
        elif cat == "utility":
            if m.effect == "drill":
                cv.poly([(bow - 0.5, -1.6), (bow + 5.5, 0), (bow - 0.5, 1.6)], (150, 140, 118))
                for k in range(3):
                    cv.line((bow + k * 1.6, -1.2 + k * 0.35), (bow + k * 1.6 + 0.8, 1.2 - k * 0.35),
                            (100, 92, 76), 0.2)
            elif m.effect == "collector":
                for side in (-1, 1):
                    cv.circle(bow * 0.15, side * half_w * 0.62, 1.4, (60, 40, 90))
                    cv.circle(bow * 0.15, side * half_w * 0.62, 1.4, (170, 110, 230), width=0.3)
            elif m.effect == "cargo":
                for k, col in enumerate(((160, 90, 60), (70, 110, 150), (140, 130, 70))):
                    cv.rect(stern * 0.55 + k * 2.4, 0, 2, half_w * 1.1, col, radius=0.2)
            elif m.effect in ("repair", "damage_control"):
                cv.rect(stern * 0.35, half_w * 0.5, 1.6, 1.6, (200, 60, 60), radius=0.3)
            elif m.effect == "smoke":
                cv.circle(stern * 0.8, -half_w * 0.5, 0.9, (90, 90, 92))
            elif m.effect in ("ecm", "bioscreen"):
                col = (120, 200, 255) if m.effect == "ecm" else (90, 220, 190)
                cv.circle(stern * 0.3, -half_w * 0.45, 1.0, col, width=0.3)


def _damage(cv, hull_key, level, pts, half_w, bow, stern):
    if level <= 0:
        return
    rng = random.Random(hash(hull_key) & 0xffff)
    for _ in range(4 * level):
        x = rng.uniform(stern * 0.8, bow * 0.7)
        y = rng.uniform(-half_w * 0.8, half_w * 0.8)
        r = rng.uniform(0.8, 1.8)
        s = pygame.Surface((int(r * 2 * R), int(r * 2 * R)), pygame.SRCALPHA)
        pygame.draw.circle(s, (12, 10, 10, 150), (r * R, r * R), r * R)
        px, py = cv.p(x, y)
        cv.surf.blit(s, (px - r * R, py - r * R))
    if level >= 2:
        for _ in range(3):
            x = rng.uniform(stern * 0.6, bow * 0.5)
            y = rng.uniform(-half_w * 0.6, half_w * 0.6)
            cv.line((x, y), (x + rng.uniform(-3, 3), y + rng.uniform(-2, 2)), (20, 16, 14), 0.3)


# --- турели ------------------------------------------------------------------

def build_turret(module_key, pal_key):
    pal = SHIP_PALETTES[pal_key]
    cv = _Canvas(9)
    body, dark = pal.turret, shade(pal.turret, 0.55)
    light = shade(pal.turret, 1.3)
    if module_key == "autocannon_s":
        cv.rect(4, 0, 7, 1.1, dark, radius=0.3)
        cv.rect(7.6, 0, 1.2, 1.6, dark, radius=0.2)
        cv.circle(0, 0, 2.6, body)
        cv.circle(-0.5, -0.5, 1.1, light)
    elif module_key == "scatter_s":
        for a in (-12, 0, 12):
            d = Vector2(1, 0).rotate(a)
            cv.line((d.x * 1.5, d.y * 1.5), (d.x * 5.5, d.y * 5.5), dark, 1.0)
        cv.circle(0, 0, 2.8, body)
        cv.circle(-0.6, -0.6, 1.2, light)
    elif module_key == "cannon_m":
        for y in (-1.1, 1.1):
            cv.rect(6, y, 9, 1.1, dark, radius=0.3)
        cv.rect(0, 0, 7.5, 7, body, radius=2.2)
        cv.rect(-0.6, -0.6, 4.5, 4.2, light, radius=1.4)
        cv.rect(-2.8, 0, 1.6, 5.5, shade(body, 0.8), radius=0.5)
    elif module_key == "em_m":
        cv.rect(5, 0, 7, 1.6, dark, radius=0.5)
        for k in range(3):
            cv.circle(3 + k * 2, 0, 1.3, (90, 150, 210), width=0.35)
        cv.circle(8.8, 0, 1.0, (160, 220, 255))
        cv.circle(0, 0, 3.4, body)
        cv.circle(-0.6, -0.6, 1.4, (120, 180, 230))
    elif module_key in ("missile_s", "missile_m"):
        n = 2 if module_key == "missile_s" else 3
        size = 5.5 if n == 2 else 7.5
        cv.rect(0, 0, size, size, body, radius=0.8)
        cv.rect(-0.4, -0.4, size - 1.6, size - 1.6, light, radius=0.6)
        step = size / n
        for i in range(n):
            for j in range(n):
                cv.circle(-size / 2 + step * (i + 0.5), -size / 2 + step * (j + 0.5), step * 0.3, (30, 30, 34))
    elif module_key == "torpedo_m":
        cv.rect(0, 0, 11, 3.2, body, radius=1.5)
        cv.rect(-0.3, -0.5, 9.5, 1.3, light, radius=0.6)
        cv.circle(5.2, 0, 1.2, (20, 24, 30))
    else:
        cv.circle(0, 0, 2.5, body)
    return cv.surf


# --- кэш и отрисовка ------------------------------------------------------

class ShipArt:
    def __init__(self):
        self.masters = {}
        self.turrets = {}
        self.cache = OrderedDict()

    def _rotated(self, key, master, angle, zoom):
        ab = round(angle / ANGLE_STEP) * ANGLE_STEP
        zb = max(ZOOM_STEP, round(zoom / ZOOM_STEP) * ZOOM_STEP)
        ck = (key, ab % 360, zb)
        img = self.cache.get(ck)
        if img is None:
            img = pygame.transform.rotozoom(master, -ab, zb / R)
            self.cache[ck] = img
            if len(self.cache) > CACHE_LIMIT:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(ck)
        return img

    def _hull_master(self, ship, pal_key):
        static = tuple((k, m) for _, _, m in ship.modules() if m.category in ("armor", "engine", "utility")
                       for k in [m.key])
        dmg = 0 if ship.hp > ship.hull.hp * 0.6 else 1 if ship.hp > ship.hull.hp * 0.3 else 2
        key = (ship.hull.key, pal_key, tuple(k for k, _ in static), dmg)
        m = self.masters.get(key)
        if m is None:
            m = self.masters[key] = build_hull(ship.hull.key, pal_key, static, dmg)
        return key, m

    def draw(self, screen, cam, ship, pal_key, t=0.0, alpha=255):
        key, (hull_img, shadow_img) = self._hull_master(ship, pal_key)
        center = cam.w2s(ship.pos)
        # крен/затопление: корабль «садится» — темнее
        sh = self._rotated(("shadow",) + key, shadow_img, ship.angle, cam.zoom)
        screen.blit(sh, sh.get_rect(center=center + Vector2(4, 6) * cam.zoom * 0.7))
        img = self._rotated(key, hull_img, ship.angle, cam.zoom)
        if ship.water > 0.05 or alpha < 255:
            img = img.copy()
            if ship.water > 0.05:
                k = int(255 * (1 - 0.45 * ship.water))
                img.fill((k, k, min(255, k + 20), 255), special_flags=pygame.BLEND_RGBA_MULT)
            if alpha < 255:
                img.set_alpha(alpha)
        screen.blit(img, img.get_rect(center=center))

        for w in ship.weapons:
            tk = (w.defn.key, pal_key)
            master = self.turrets.get(tk)
            if master is None:
                master = self.turrets[tk] = build_turret(*tk)
            ang = w.world_angle(ship) if w.defn.kind == "gun" else ship.angle + w.slot.facing
            timg = self._rotated(("t",) + tk, master, ang, cam.zoom)
            if alpha < 255:
                timg = timg.copy()
                timg.set_alpha(alpha)
            screen.blit(timg, timg.get_rect(center=cam.w2s(w.world_pos(ship))))
            if w.overheated or w.heat > 70:
                glow = min(1.0, w.heat / 100)
                pygame.draw.circle(screen, mix((120, 40, 20), (255, 120, 40), glow), cam.w2s(w.world_pos(ship)),
                                   max(1, int(cam.px(1.2))))

        # вращающаяся антенна радара
        if ship.sensor and ship.hull.key in MAST:
            mx, my = MAST[ship.hull.key]
            base = cam.w2s(ship.pos + Vector2(mx, my).rotate(ship.angle))
            if ship.sensor.veil_resist:
                pygame.draw.circle(screen, (110, 180, 190), base, max(2, int(cam.px(2.0))), 1)
            else:
                d = Vector2(1, 0).rotate(t * 220) * cam.px(2.6)
                pygame.draw.line(screen, (170, 200, 205), base - d, base + d, max(1, int(cam.px(0.6))))


def hull_length(hull_key):
    xs = [x for x, _ in PROFILES[hull_key]]
    return max(xs) - min(xs)


def stern_points(ship):
    """Точки у кормы в мире — для кильватерного следа."""
    stern = PROFILES[ship.hull.key][-1][0]
    w = max(y for _, y in PROFILES[ship.hull.key]) * 0.6
    return [ship.pos + Vector2(stern, s * w).rotate(ship.angle) for s in (-1, 1)]


def bow_point(ship):
    return ship.pos + Vector2(PROFILES[ship.hull.key][0][0], 0).rotate(ship.angle)


def hull_radius_px(ship, cam):
    return cam.px(ship.radius)


__all__ = ["ShipArt", "outline", "stern_points", "bow_point", "hull_length", "math"]
