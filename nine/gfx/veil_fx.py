"""Живая Пелена: филаменты в воздухе, параллакс-дымка, предвестники Всплеска,
«окно в небо» в Штиль, искажения в плотной Пелене, кокон налёта на корпусе.

По лору Пелена — взвесь псевдокристаллических нитей, которые полимеризуются от
быстрых объектов. Отсюда: мерцающие нити в воздухе, светящиеся ночью, и кокон
на корпусе, который растёт от форсажа.
"""

import math
import random

import pygame
from pygame.math import Vector2

from . import palette as P


class VeilMotes:
    """Филаменты: короткие мерцающие нити, висящие в воздухе там, где Пелена гуще."""

    def __init__(self):
        self.motes = []
        self.rng = random.Random(11)
        self.max_count = 160

    def update(self, world, cam, dt):
        rng = self.rng
        x0, y0, x1, y1 = cam.world_rect()
        pad = 60
        keep = []
        for m in self.motes:
            m[0] += m[1] * dt                      # позиция += скорость
            m[3] += m[4] * dt                      # угол += вращение
            if x0 - pad < m[0].x < x1 + pad and y0 - pad < m[0].y < y1 + pad:
                keep.append(m)
        self.motes = keep
        d = world.density_at(cam.center)
        want = int(self.max_count * min(1.0, max(0.0, (d - 0.15) / 0.6)))
        tries = 0
        while len(self.motes) < want and tries < 40:
            tries += 1
            pos = Vector2(rng.uniform(x0, x1), rng.uniform(y0, y1))
            local = world.density_at(pos)
            if rng.random() > local * 1.3:
                continue
            drift = Vector2(-14, 6) + Vector2(rng.uniform(-6, 6), rng.uniform(-6, 6))
            # [позиция, скорость, длина, угол, вращение, фаза мерцания, яркость]
            self.motes.append([pos, drift, rng.uniform(1.5, 4.5), rng.uniform(0, 360), rng.uniform(-40, 40),
                               rng.uniform(0, math.tau), local])

    def draw(self, screen, cam, t, night, fx):
        for pos, _, length, ang, _, phase, local in self.motes:
            tw = 0.5 + 0.5 * math.sin(t * 3.1 + phase)
            k = (0.35 + 0.65 * tw) * min(1.0, local * 1.4)
            col = P.mix((70, 50, 110), (230, 210, 255), k * (0.55 + 0.45 * night))
            s = cam.w2s(pos)
            d = Vector2(1, 0).rotate(ang) * cam.px(length) * 0.5
            pygame.draw.line(screen, col, s - d, s + d, 1)
            if tw > 0.7:
                pygame.draw.circle(screen, P.mix(col, (255, 255, 255), 0.4), s, 1)      # кристаллическая искра
            if tw > 0.85 and night > 0.3:
                img = fx.glow(P.shade((170, 130, 255), 0.5 * night * k), cam.px(4))
                screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)


class Haze:
    """Верхний слой дымки с параллаксом: движется быстрее земли, будто ближе к камере."""

    def __init__(self, tile):
        self.tile = tile
        self.cache = {}

    def draw(self, screen, cam, density, t):
        if density < 0.2:
            return
        alpha = int(min(1.0, (density - 0.2) / 0.6) * 95)
        size = int(360 * cam.zoom) // 8 * 8 or 8
        key = (size, alpha // 8)
        img = self.cache.get(key)
        if img is None:
            img = pygame.transform.smoothscale(self.tile, (size, size))
            img.set_alpha(alpha // 8 * 8)
            if len(self.cache) > 40:
                self.cache.clear()
            self.cache[key] = img
        par = 1.35                                # параллакс: верхний слой смещается сильнее
        ox = int(-(cam.center.x * cam.zoom * par + t * 22) % size)
        oy = int(-(cam.center.y * cam.zoom * par - t * 9) % size)
        y = oy - size
        while y < cam.h:
            x = ox - size
            while x < cam.w:
                screen.blit(img, (x, y))
                x += size
            y += size


def draw_surge_telegraphs(screen, cam, world, fx):
    """Перед Всплеском снизу из воды поднимается пульсирующее свечение (и скаты уходят)."""
    t = world.t
    for ev in world.events.active:
        if ev.phase(t) != "warning" or not ev.data.telegraphed_by_rays:
            continue
        if not cam.visible(ev.pos, ev.data.radius):
            continue
        k = 1.0 - (ev.start - t) / max(0.1, ev.data.warning_time)          # 0 → 1 к началу
        pulse = 0.5 + 0.5 * math.sin(t * (3 + 6 * k))
        c = cam.w2s(ev.pos)
        r = cam.px(ev.data.radius * (0.25 + 0.55 * k))
        img = fx.glow(P.shade((150, 70, 220), 0.25 + 0.35 * k * pulse), r)
        screen.blit(img, img.get_rect(center=c), special_flags=pygame.BLEND_ADD)
        # расходящиеся кольца из глубины
        for i in range(3):
            ph = (t * 0.6 + i / 3) % 1
            rr = int(cam.px(ev.data.radius * 0.8 * ph))
            if rr > 2:
                pygame.draw.circle(screen, P.mix(P.OCEAN_MID, (170, 110, 240), (1 - ph) * k), c, rr, 1)


class SkyGlimpse:
    """Штиль: туман расходится, и на миг видно чистое небо — тизер финала с полётом.

    Небесный свет и лучи рисуются один раз в слой; каждый кадр — только прозрачность и тени облаков.
    """

    DURATION = 5.0

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.left = 0.0
        self.rng = random.Random(5)
        self.clouds = []
        self.light = None
        self.shadows = pygame.Surface((w, h), pygame.SRCALPHA)

    def _build(self):
        w, h = self.w, self.h
        light = pygame.Surface((w, h), pygame.SRCALPHA)
        small = pygame.Surface((w // 8, h // 8), pygame.SRCALPHA)
        cx, cy = w * 0.3 / 8, -h * 0.15 / 8
        for y in range(small.get_height()):
            for x in range(small.get_width()):
                d = math.hypot(x - cx, y - cy) / (w / 8)
                a = max(0.0, 1.0 - d) ** 1.4
                small.set_at((x, y), (190, 220, 255, int(150 * a)))
        light.blit(pygame.transform.smoothscale(small, (w, h)), (0, 0))
        rays = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(7):
            a = math.radians(38 + i * 9)
            end = (w * 0.2 + math.cos(a) * w * 1.3, -40 + math.sin(a) * w * 1.3)
            pygame.draw.line(rays, (255, 244, 210, 26), (w * 0.2, -40), end, 30)
        light.blit(rays, (0, 0))
        self.light = light

    def trigger(self):
        self.left = self.DURATION
        if self.light is None:
            self._build()
        self.clouds = [(Vector2(self.rng.uniform(-200, self.w), self.rng.uniform(0, self.h)),
                        self.rng.uniform(120, 260)) for _ in range(6)]

    def draw(self, screen, dt, fx=None):
        if self.left <= 0:
            return
        self.left -= dt
        k = math.sin(math.pi * max(0.0, min(1.0, 1 - self.left / self.DURATION)))
        self.light.set_alpha(int(190 * k))
        screen.blit(self.light, (0, 0))
        self.shadows.fill((0, 0, 0, 0))
        for pos, r in self.clouds:
            pos.x += 40 * dt
            pygame.draw.ellipse(self.shadows, (0, 0, 20, int(34 * k)), (pos.x, pos.y, r * 1.8, r))
        screen.blit(self.shadows, (0, 0))


def distort(screen, density, t, strength=1.0):
    """Плотная Пелена «болеет» экран: цветной двойник со сдвигом и дрожащая полоса."""
    k = max(0.0, (density - 0.55) / 0.45) * strength
    if k <= 0.02:
        return
    ghost = screen.copy()
    ghost.fill((255, 110, 255), special_flags=pygame.BLEND_MULT)
    ghost.set_alpha(int(60 * k))
    off = int(2 + 4 * k * (0.6 + 0.4 * math.sin(t * 7)))
    screen.blit(ghost, (off, 0))
    if int(t * 5) % 7 == 0:
        y = int((t * 173) % screen.get_height())
        band = screen.subsurface((0, y, screen.get_width(), min(6, screen.get_height() - y))).copy()
        screen.blit(band, (int(8 * k), y))


def draw_cocoon(screen, cam, ship, t):
    """Кокон налёта: светлые кристаллические нити, облепившие корпус. Растёт с налётом."""
    f = ship.fouling
    if f < 0.05:
        return
    from .ship_art import outline
    pts = outline(ship.hull.key)
    rng = random.Random(hash(ship.hull.key) & 0xffff)
    n = int(6 + 34 * f)
    col = P.mix((90, 60, 130), (220, 200, 255), 0.4 + 0.3 * math.sin(t * 2))
    for i in range(n):
        a = pts[rng.randrange(len(pts))]
        b = pts[rng.randrange(len(pts))]
        mid = Vector2((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) * rng.uniform(0.3, 0.9)
        pa = cam.w2s(ship.pos + (Vector2(a) * rng.uniform(0.85, 1.05)).rotate(ship.angle))
        pm = cam.w2s(ship.pos + mid.rotate(ship.angle))
        pygame.draw.line(screen, col, pa, pm, 1)
    if f > 0.3:
        for i in range(int(10 * f)):
            q = Vector2(pts[rng.randrange(len(pts))]) * rng.uniform(0.95, 1.12)
            pygame.draw.circle(screen, (235, 220, 255), cam.w2s(ship.pos + q.rotate(ship.angle)),
                               max(1, int(cam.px(0.5))))
