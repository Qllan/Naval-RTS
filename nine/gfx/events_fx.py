"""Внешний вид мировых событий: Шторм, Цветение, Течение аномалии."""

import math
import random

import pygame
from pygame.math import Vector2

from . import palette as P


def _visible(cam, ev):
    return cam.visible(ev.pos, ev.data.radius + 100)


def storm_strength(world):
    return max((ev.strength(world.player.pos, world.t) for ev in world.events.active
                if ev.data.name == "Шторм"), default=0.0)


def bloom_patches(ev):
    """Детерминированные светящиеся пятна Цветения."""
    rng = random.Random(int(ev.pos.x * 7 + ev.pos.y * 13))
    out = []
    for _ in range(26):
        r = ev.data.radius * math.sqrt(rng.random()) * 0.9
        a = rng.uniform(0, math.tau)
        out.append((ev.pos + Vector2(math.cos(a), math.sin(a)) * r, rng.uniform(30, 80), rng.uniform(0, math.tau)))
    return out


def draw_under(screen, cam, world, fx):
    """На воде: струи течения, барашки шторма."""
    t = world.t
    for ev in world.events.active:
        if ev.phase(t) != "active" or not _visible(cam, ev):
            continue
        name = ev.data.name
        if name == "Течение аномалии":
            _current(screen, cam, ev, t)
        elif name == "Шторм":
            _whitecaps(screen, cam, ev, t)


def draw_emissive(screen, cam, world, fx, night):
    """Светится поверх освещения: Цветение."""
    t = world.t
    for ev in world.events.active:
        if ev.phase(t) != "active" or ev.data.name != "Цветение" or not _visible(cam, ev):
            continue
        age = min(1.0, (t - ev.start) / 4, (ev.start + ev.data.duration - t) / 4)
        for pos, r, ph in bloom_patches(ev):
            if not cam.visible(pos, r):
                continue
            k = age * (0.55 + 0.45 * math.sin(t * 1.3 + ph)) * (0.35 + 0.65 * night)
            q = max(1, round(k * 6)) / 6
            img = fx.glow(P.shade((60, 230, 180), q * 0.8), cam.px(r))
            screen.blit(img, img.get_rect(center=cam.w2s(pos)), special_flags=pygame.BLEND_ADD)
            for i in range(4):
                sp = pos + Vector2(1, 0).rotate(ph * 57 + i * 90 + t * 20) * r * 0.5
                if (int(t * 4) + i) % 3 == 0:
                    pygame.draw.circle(screen, (200, 255, 230), cam.w2s(sp), 1)


def bloom_lights(world):
    for ev in world.events.active:
        if ev.phase(world.t) == "active" and ev.data.name == "Цветение":
            for pos, r, ph in bloom_patches(ev):
                yield pos, r * 1.6, (60, 230, 180), 0.6 + 0.3 * math.sin(world.t * 1.3 + ph)


def _current(screen, cam, ev, t):
    """«Река» помех: струи бегут вдоль полосы, берега мерцают."""
    d = ev.direction
    perp = d.rotate(90)
    R, W = ev.data.radius, ev.data.width
    rng = random.Random(int(ev.pos.x) ^ int(ev.pos.y))
    speed = 95.0
    for i in range(70):
        u0, v = rng.uniform(-1, 1), rng.uniform(-0.95, 0.95)
        u = (u0 + t * speed / R) % 2 - 1
        fade = min(1.0, (1 - abs(u)) * 4, (1 - abs(v)) * 3)
        p0 = ev.pos + d * (u * R) + perp * (v * W)
        if not cam.visible(p0, 40):
            continue
        col = P.mix(P.OCEAN_MID, (190, 160, 255), 0.55 * fade)
        pygame.draw.line(screen, col, cam.w2s(p0), cam.w2s(p0 + d * rng.uniform(18, 40)), 1)
    for side in (-1, 1):                              # мерцающие берега
        n = 40
        pts = [cam.w2s(ev.pos + d * (R * (2 * k / n - 1)) + perp * (side * W * (1 + 0.03 * math.sin(t * 2 + k))))
               for k in range(n + 1)]
        col = P.mix(P.OCEAN_MID, (150, 110, 230), 0.5 + 0.2 * math.sin(t * 3))
        for k in range(0, n, 2):
            pygame.draw.line(screen, col, pts[k], pts[k + 1], 1)


def _whitecaps(screen, cam, ev, t):
    """Барашки: белые гребни мелькают по всей акватории шторма."""
    x0, y0, x1, y1 = cam.world_rect()
    step = 55
    wind = ev.direction
    for gy in range(int(y0 // step), int(y1 // step) + 1):
        for gx in range(int(x0 // step), int(x1 // step) + 1):
            h = (gx * 92821 ^ gy * 68917) & 0xffff
            ph = math.sin(t * (1.5 + (h % 5) * 0.3) + h)
            if ph < 0.55:
                continue
            wp = Vector2(gx * step + h % step, gy * step + (h >> 5) % step)
            s = ev.strength(wp, t)
            if s <= 0.05:
                continue
            a = cam.w2s(wp)
            b = cam.w2s(wp + wind.rotate(90) * 7)
            pygame.draw.line(screen, P.mix(P.OCEAN_MID, P.FOAM, (ph - 0.55) * 2.2 * s), a, b, 2)


def draw_rain(screen, cam, world, fx, dt):
    """Дождь по ветру и молнии, если игрок в шторме. Возвращает True, если ударила молния."""
    k = storm_strength(world)
    if k <= 0.02:
        return False
    wind = next((ev.direction for ev in world.events.active if ev.data.name == "Шторм"), Vector2(1, 0))
    rng = random.Random(int(world.t * 40))
    vec = wind * 12 + Vector2(0, 18)
    for _ in range(int(260 * k)):
        x, y = rng.uniform(-20, cam.w), rng.uniform(-20, cam.h)
        pygame.draw.line(screen, (150, 160, 185), (x, y), (x + vec.x, y + vec.y), 1)
    if random.random() < 0.12 * k * dt:          # молния — в среднем раз в 8 секунд в сердце шторма
        fx.flash = max(fx.flash, 0.8)
        return True
    return False
