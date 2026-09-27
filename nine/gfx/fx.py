"""Частицы и эффекты боя. Мир складывает события в world.fx, здесь они превращаются в картинку.

События мира (кортежи):
    ("muzzle", pos, angle, size, kind, side)
    ("hit", pos, layer, dtype, kind, ship)       layer: shield | armor | hull
    ("splash", pos, kind)
    ("explosion", pos, size)                     1 — ракета, 2 — торпеда, 3 — гибель корабля
    ("ecm", pos, radius)
    ("lightning", pos)
"""

import math
import random

import pygame
from pygame.math import Vector2

from . import palette as P
from .ship_art import bow_point, stern_points

MAX_PARTICLES = 2200


class Particle:
    __slots__ = ("pos", "vel", "life", "max_life", "size", "grow", "color", "color2", "kind", "drag", "layer",
                 "angle")

    def __init__(self, pos, vel, life, size, color, kind="dot", grow=0.0, color2=None, drag=0.0, layer="air",
                 angle=0.0):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.life = self.max_life = life
        self.size = size
        self.grow = grow
        self.color = color
        self.color2 = color2 or color
        self.kind = kind
        self.drag = drag
        self.layer = layer
        self.angle = angle


def _glow_master(n=64):
    """Белый радиальный градиент — основа для свечений (тонируется и кладётся с BLEND_ADD)."""
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            d = math.hypot(x - c, y - c) / c
            k = max(0.0, 1.0 - d) ** 2
            v = int(255 * k)
            s.set_at((x, y), (v, v, v, 255))
    return s


def _puff_master(n=48):
    """Мягкое пятно с альфой — для дыма и пены."""
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            d = math.hypot(x - c, y - c) / c
            a = int(255 * max(0.0, 1.0 - d) ** 1.5)
            s.set_at((x, y), (255, 255, 255, a))
    return s


class FX:
    def __init__(self):
        self.particles = []
        self.rng = random.Random(3)
        self._glow = _glow_master()
        self._puff = _puff_master()
        self._glow_cache = {}
        self._puff_cache = {}
        self.flash = 0.0            # вспышка молнии на весь экран

    # --- спрайты ----------------------------------------------------------

    @staticmethod
    def _bucket(radius):
        r = max(2, int(radius))
        return r if r < 12 else r // 3 * 3 if r < 48 else r // 8 * 8

    @staticmethod
    def _fade(color, k):
        """Затухание квантуется, чтобы кэш спрайтов срабатывал."""
        q = round(k * 8) / 8
        return tuple(int(c * q) for c in color)

    def glow(self, color, radius):
        r = self._bucket(radius)
        key = (color, r)
        img = self._glow_cache.get(key)
        if img is None:
            img = pygame.transform.smoothscale(self._glow, (r * 2, r * 2))
            img.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if len(self._glow_cache) > 800:
                self._glow_cache.clear()
            self._glow_cache[key] = img
        return img

    def puff(self, color, radius, alpha):
        r = self._bucket(radius)
        a = max(0, min(255, int(alpha) // 16 * 16))
        key = (color, r, a)
        img = self._puff_cache.get(key)
        if img is None:
            img = pygame.transform.smoothscale(self._puff, (r * 2, r * 2))
            img.fill((*color, a), special_flags=pygame.BLEND_RGBA_MULT)
            if len(self._puff_cache) > 1500:
                self._puff_cache.clear()
            self._puff_cache[key] = img
        return img

    # --- порождение -------------------------------------------------------

    def add(self, *a, **kw):
        if len(self.particles) < MAX_PARTICLES:
            self.particles.append(Particle(*a, **kw))

    def _rv(self, speed):
        return Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(0, speed)

    def consume(self, events, cam, player):
        rng = self.rng
        while events:
            ev = events.popleft()
            kind = ev[0]
            if kind == "muzzle":
                _, pos, ang, size, wkind, side = ev
                d = Vector2(1, 0).rotate(ang)
                if wkind == "gun":
                    self.add(pos, Vector2(), 0.07 + 0.03 * size, 5 + 4 * size, P.MUZZLE, "glow")
                    for _ in range(2 + size):
                        self.add(pos, d.rotate(rng.uniform(-25, 25)) * rng.uniform(60, 160), 0.35,
                                 1.8 + size, P.SMOKE, "smoke", grow=10, drag=3.0)
                else:
                    for _ in range(6):
                        self.add(pos, -d.rotate(rng.uniform(-40, 40)) * rng.uniform(20, 70), 0.9, 3,
                                 (120, 120, 124), "smoke", grow=14, drag=2.0)
                    self.add(pos, Vector2(), 0.12, 9, (255, 200, 140), "glow")
                if side == "player" and wkind == "gun" and size > 1:
                    cam.add_shake(0.8)
            elif kind == "hit":
                _, pos, layer, dtype, pkind, ship = ev
                self._hit(pos, layer, dtype, pkind, ship)
                if ship is player:
                    cam.add_shake(2.5 if pkind == "shell" else 5.0)
            elif kind == "splash":
                _, pos, pkind = ev
                self._splash(pos, 1.6 if pkind == "torpedo" else 1.0)
            elif kind == "explosion":
                _, pos, size = ev
                self._explosion(pos, size)
                dist = player.pos.distance_to(pos)
                if dist < 500:
                    cam.add_shake(size * 3.0 * (1 - dist / 500))
            elif kind == "ecm":
                _, pos, radius = ev
                self.add(pos, Vector2(), 0.6, radius, (120, 200, 255), "ring", layer="air")
                for _ in range(24):
                    self.add(pos + self._rv(radius * 0.8), Vector2(), 0.3, 3, (160, 220, 255), "glow")
            elif kind == "lightning":
                self.flash = 1.0

    def _hit(self, pos, layer, dtype, pkind, ship):
        rng = self.rng
        if layer == "shield":
            # рябь по пузырю щита в точке удара
            to = Vector2(pos) - ship.pos
            ang = Vector2(1, 0).angle_to(to) if to.length_squared() else 0
            self.add(ship.pos, ship.vel, 0.35, ship.radius + 7, P.SHIELD_HIT, "arc", angle=ang)
            self.add(pos, Vector2(), 0.12, 7, P.SHIELD_HIT, "glow")
            return
        col = (160, 210, 255) if dtype == "em" else P.SPARK
        n = 6 if pkind == "shell" else 14
        for _ in range(n):
            self.add(pos, self._rv(260) + ship.vel, rng.uniform(0.15, 0.4), 1.5, col, "spark", drag=4.0)
        self.add(pos, Vector2(), 0.1, 6, col, "glow")
        if layer == "hull":
            for _ in range(3):
                self.add(pos, self._rv(40) + ship.vel * 0.5, 1.2, 2.5, P.SMOKE, "smoke", grow=9, drag=1.5)

    def _splash(self, pos, scale):
        rng = self.rng
        self.add(pos, Vector2(), 0.8 * scale, 3 * scale, P.FOAM, "ring", grow=22 * scale, layer="water")
        for _ in range(int(6 * scale)):
            self.add(pos, self._rv(70 * scale), rng.uniform(0.3, 0.7), 1.6, P.FOAM, "dot", drag=3.0, layer="water")

    def _explosion(self, pos, size):
        rng = self.rng
        s = {1: 1.0, 2: 1.6, 3: 2.6}[size]
        self.add(pos, Vector2(), 0.25 * s, 22 * s, (255, 210, 140), "glow")
        self.add(pos, Vector2(), 0.5 * s, 14 * s, P.FIRE, "glow")
        self.add(pos, Vector2(), 0.5, 6 * s, (255, 230, 200), "ring", grow=120 * s, layer="water")
        for _ in range(int(14 * s)):
            self.add(pos, self._rv(220 * s), rng.uniform(0.3, 0.8), 1.8, P.SPARK, "spark", drag=2.5)
        for _ in range(int(10 * s)):
            self.add(pos + self._rv(6 * s), self._rv(50 * s), rng.uniform(1.2, 2.6) * s ** 0.5, 5 * s,
                     P.SMOKE, "smoke", grow=16, drag=1.2, color2=(40, 40, 44))
        for _ in range(int(6 * s)):
            self.add(pos + self._rv(10 * s), self._rv(30), rng.uniform(0.3, 0.6), 7 * s, P.FIRE, "fire",
                     grow=10, drag=2.0)
        if size >= 3:
            self._splash(pos, 2.4)

    # --- непрерывные эффекты -----------------------------------------------

    def ambient(self, world, cam, dt, visible):
        """Кильватер, дым пожаров, следы ракет, пузыри торпед."""
        rng = self.rng
        ships = [world.player] + [p.ship for p in world.pirates if visible(p.ship.pos)]
        for s in ships:
            sp = s.speed
            if sp > 15:
                n = sp * dt / 5
                while n > 0:
                    if rng.random() < n:
                        for sp_pos in stern_points(s):
                            side = (sp_pos - s.pos).rotate(-s.angle)
                            out = Vector2(0, 1 if side.y > 0 else -1).rotate(s.angle) * rng.uniform(8, 20)
                            self.add(sp_pos, out - s.vel * 0.05, rng.uniform(1.8, 3.0), 3.0, P.FOAM, "foam",
                                     grow=6.5, drag=0.8, layer="water")
                    n -= 1
                if sp > s.base_top_speed() * 0.6 and rng.random() < sp * dt / 25:
                    b = bow_point(s)
                    for side in (-1, 1):
                        v = Vector2(-0.3, side).rotate(s.angle) * rng.uniform(25, 50)
                        self.add(b, v, 0.7, 1.5, P.FOAM, "foam", grow=4, drag=1.5, layer="water")
            if s.boosting and rng.random() < 0.6:
                for sp_pos in stern_points(s):
                    self.add(sp_pos, -s.vel * 0.2, 0.18, 4, (255, 170, 90), "glow")
            for i in range(s.fires):
                if rng.random() < 18 * dt:
                    off = Vector2(rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4)) * s.radius
                    fp = s.pos + off.rotate(s.angle)
                    self.add(fp, s.vel + Vector2(rng.uniform(-8, 8), -rng.uniform(10, 25)), rng.uniform(0.3, 0.6),
                             3.5, P.FIRE, "fire", grow=5)
                    self.add(fp, s.vel * 0.8 + Vector2(rng.uniform(-10, 10), -rng.uniform(15, 35)),
                             rng.uniform(1.4, 2.4), 3, P.SMOKE, "smoke", grow=10, drag=0.4, color2=(30, 30, 32))
            if s.water > 0.3 and rng.random() < s.water * 6 * dt:
                self.add(s.pos + self._rv(s.radius * 0.6), Vector2(), 1.2, 2, P.FOAM, "ring", grow=10,
                         layer="water")
        for pr in world.projectiles:
            if not visible(pr.pos):
                continue
            if pr.kind == "missile" and rng.random() < 0.8:
                self.add(pr.pos, self._rv(8), rng.uniform(0.5, 0.9), 1.6, (140, 140, 146), "smoke", grow=7,
                         drag=1.0)
            elif pr.kind == "torpedo" and rng.random() < 0.5:
                self.add(pr.pos + self._rv(3), Vector2(), 0.9, 1.2, P.FOAM, "dot", layer="water")

    # --- шаг и отрисовка ------------------------------------------------------

    def update(self, dt):
        keep = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            if p.drag:
                p.vel *= math.exp(-p.drag * dt)
            p.pos += p.vel * dt
            p.size += p.grow * dt
            keep.append(p)
        self.particles = keep
        self.flash = max(0.0, self.flash - dt * 4)

    def draw(self, screen, cam, layer):
        zoom = cam.zoom
        for p in self.particles:
            if p.layer != layer or not cam.visible(p.pos, 40):
                continue
            k = p.life / p.max_life
            s = cam.w2s(p.pos)
            r = p.size * zoom
            if p.kind in ("glow", "fire"):
                img = self.glow(self._fade(p.color, k), r)
                screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)
            elif p.kind in ("smoke", "foam"):
                col = P.mix(p.color2, p.color, round(k * 4) / 4)
                alpha = (170 if p.kind == "smoke" else 120) * k
                img = self.puff(col, r, alpha)
                screen.blit(img, img.get_rect(center=s))
            elif p.kind == "spark":
                tail = s - p.vel * zoom * 0.03
                pygame.draw.line(screen, P.mix((60, 30, 10), p.color, k), s, tail, max(1, int(zoom)))
            elif p.kind == "dot":
                pygame.draw.circle(screen, P.mix(P.OCEAN_MID, p.color, k), s, max(1, int(r * 0.6)))
            elif p.kind == "ring":
                if r > 1:
                    pygame.draw.circle(screen, P.mix(P.OCEAN_MID, p.color, k), s, int(r), max(1, int(zoom * k * 2)))
            elif p.kind == "arc":
                rect = pygame.Rect(0, 0, r * 2, r * 2)
                rect.center = s
                a = math.radians(-p.angle)
                pygame.draw.arc(screen, P.mix(P.OCEAN_MID, p.color, k), rect, a - 0.7, a + 0.7,
                                max(1, int(3 * k * zoom)))
