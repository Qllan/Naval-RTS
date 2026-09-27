"""Отрисовка мира. Геометрия полигонами — никаких повёрнутых спрайтов."""

import math

import pygame
from pygame.math import Vector2

from . import config as C
from .entities import RESOURCES, heading
from .ai import Tihodont

WATER = (7, 13, 22)
WAVE = (15, 27, 42)
VEIL_CELL_PX = 24

COL_PLAYER = (205, 215, 225)
COL_CAPSULE = (240, 150, 60)
COL_PIRATE = (190, 75, 50)
COL_PORT = (90, 160, 190)
COL_LOOT = (230, 190, 90)


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.cam = Vector2()
        self.frame = 0
        cw, ch = self.w // VEIL_CELL_PX + 2, self.h // VEIL_CELL_PX + 2
        self.veil_small = pygame.Surface((cw, ch), pygame.SRCALPHA)
        self.veil_big = None
        self.fog = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        self.fog_grad = self._make_fog_gradient(256)
        self.fog_cache = {}
        self.font = pygame.font.Font(None, 20)

    def to_screen(self, pos):
        return Vector2(pos) - self.cam

    def on_screen(self, pos, margin=60):
        s = self.to_screen(pos)
        return -margin < s.x < self.w + margin and -margin < s.y < self.h + margin

    def poly(self, shape, pos, angle, color, width=0, scale=1.0):
        pts = [Vector2(x, y).rotate(angle) * scale + self.to_screen(pos) for x, y in shape]
        pygame.draw.polygon(self.screen, color, pts, width)

    # --------------------------------------------------------------------

    def draw(self, world):
        self.frame += 1
        p = world.player
        self.cam = p.pos - Vector2(self.w / 2, self.h / 2)
        vis = world.visual_range()
        radar = world.radar_range()

        def seen(pos):
            return p.pos.distance_to(pos) < vis

        def blip(pos):
            return p.pos.distance_to(pos) < radar

        self._water(world.t)
        self._eye(world)
        self._port(world)
        self._events(world, radar)

        for n in world.nodes:
            if self.on_screen(n.pos) and (seen(n.pos) or blip(n.pos)):
                self._node(n, world.t)
        for lt in world.loot:
            if self.on_screen(lt.pos) and (seen(lt.pos) or blip(lt.pos)):
                s = self.to_screen(lt.pos)
                pygame.draw.rect(self.screen, COL_LOOT, (s.x - 4, s.y - 4, 8, 8), 1)
        for r in world.rays:
            if self.on_screen(r.pos) and seen(r.pos):
                self._ray(r)
        for tx in world.tihodonts:
            # Тиходонты экранированы от радаров — только визуально
            if self.on_screen(tx.pos, 160) and seen(tx.pos):
                self._tihodont(tx, world.t)
        for pr in world.pirates:
            if not self.on_screen(pr.ship.pos):
                continue
            if seen(pr.ship.pos):
                self._ship(pr.ship, COL_PIRATE)
            elif blip(pr.ship.pos):
                s = self.to_screen(pr.ship.pos)
                pygame.draw.circle(self.screen, COL_PIRATE, s, 3)
                pygame.draw.circle(self.screen, COL_PIRATE, s, 9, 1)
        for b in world.bullets:
            s = self.to_screen(b.pos)
            e = s - b.vel.normalize() * 7 if b.vel.length_squared() else s
            col = (250, 230, 140) if b.owner == "player" else (255, 130, 70)
            pygame.draw.line(self.screen, col, s, e, 2)

        self._ship(p, COL_CAPSULE if world.in_capsule else COL_PLAYER, player=True)

        self._veil(world)
        self._storm_arms(world)
        self._fog(vis)
        if radar > 0:
            pygame.draw.circle(self.screen, (40, 90, 80), (self.w // 2, self.h // 2), int(radar), 1)

    # --------------------------------------------------------------------

    def _water(self, t):
        self.screen.fill(WATER)
        step = 110
        x0 = int(self.cam.x // step) * step
        y0 = int(self.cam.y // step) * step
        for gy in range(y0, int(self.cam.y + self.h) + step, step):
            for gx in range(x0, int(self.cam.x + self.w) + step, step):
                phase = math.sin(gx * 0.013 + gy * 0.007 + t * 1.3)
                s = Vector2(gx, gy) - self.cam + Vector2(phase * 6, 0)
                pygame.draw.line(self.screen, WAVE, s, s + Vector2(14, 0), 1)

    def _veil(self, world):
        # Пересчёт раз в 2 кадра: поле меняется медленно
        if self.frame % 2 == 1 or self.veil_big is None:
            surf = self.veil_small
            cw, ch = surf.get_size()
            ox = self.cam.x - (self.cam.x % VEIL_CELL_PX)
            oy = self.cam.y - (self.cam.y % VEIL_CELL_PX)
            self._veil_origin = Vector2(ox, oy)
            for cy in range(ch):
                wy = oy + cy * VEIL_CELL_PX
                for cx in range(cw):
                    wx = ox + cx * VEIL_CELL_PX
                    d = world.veil.density((wx, wy), world.t)
                    a = int(min(215, 15 + 210 * d ** 1.3))
                    surf.set_at((cx, cy), (int(60 + 70 * d), int(30 + 20 * d), int(95 + 80 * d), a))
            self.veil_big = pygame.transform.smoothscale(surf, (cw * VEIL_CELL_PX, ch * VEIL_CELL_PX))
        self.screen.blit(self.veil_big, self._veil_origin - self.cam)

    FOG_ALPHA = 160

    def _make_fog_gradient(self, n):
        """Радиальный градиент альфы: прозрачно в центре, FOG_ALPHA к краю."""
        surf = pygame.Surface((n, n), pygame.SRCALPHA)
        c = (n - 1) / 2
        for y in range(n):
            for x in range(n):
                r = math.hypot(x - c, y - c) / c
                k = min(1.0, max(0.0, (r - 0.55) / 0.45))
                surf.set_at((x, y), (0, 0, 0, int(self.FOG_ALPHA * k * k * (3 - 2 * k))))
        return surf

    def _fog(self, vis):
        size = max(8, int(vis * 2) // 8 * 8)
        grad = self.fog_cache.get(size)
        if grad is None:
            if len(self.fog_cache) > 64:
                self.fog_cache.clear()
            grad = self.fog_cache[size] = pygame.transform.smoothscale(self.fog_grad, (size, size))
        self.fog.fill((0, 0, 0, self.FOG_ALPHA))
        rect = grad.get_rect(center=(self.w // 2, self.h // 2))
        self.fog.blit(grad, rect, special_flags=pygame.BLEND_RGBA_MIN)
        self.screen.blit(self.fog, (0, 0))

    def _eye(self, world):
        eye = world.eye
        if not self.on_screen(eye, C.EYE_BELT_R):
            return
        s = self.to_screen(eye)
        t = world.t
        # Зеркало — ртутная вода и столб света
        pygame.draw.circle(self.screen, (2, 2, 4), s, int(C.EYE_CALM_R))
        pygame.draw.circle(self.screen, (60, 60, 70), s, int(C.EYE_CALM_R), 1)
        glow = 26 + 6 * math.sin(t * 2)
        for i in range(4):
            pygame.draw.circle(self.screen, (60 + i * 50, 60 + i * 50, 70 + i * 50), s, int(glow * (1 - i * 0.22)))

    def _storm_arms(self, world):
        """Стена Рёва — вращающиеся рукава шторма поверх Пелены."""
        eye = world.eye
        if not self.on_screen(eye, C.EYE_WALL_R):
            return
        s = self.to_screen(eye)
        t = world.t
        for arm in range(6):
            base = arm * 60 + t * 25
            pts = []
            for k in range(20):
                r = C.EYE_CALM_R + (C.EYE_WALL_R - C.EYE_CALM_R) * k / 19
                a = math.radians(base + k * 9)
                pts.append((s.x + math.cos(a) * r, s.y + math.sin(a) * r))
            pygame.draw.lines(self.screen, (150, 90, 200), False, pts, 2)

    def _port(self, world):
        if not self.on_screen(world.port, 200):
            return
        s = self.to_screen(world.port)
        pygame.draw.circle(self.screen, (20, 40, 55), s, int(C.PORT_RADIUS))
        pygame.draw.circle(self.screen, COL_PORT, s, int(C.PORT_RADIUS), 1)
        pygame.draw.rect(self.screen, (40, 70, 90), (s.x - 50, s.y - 30, 100, 60))
        pygame.draw.rect(self.screen, COL_PORT, (s.x - 50, s.y - 30, 100, 60), 1)
        for i in range(4):
            on = (int(world.t * 2) + i) % 4 == 0
            pygame.draw.circle(self.screen, (250, 220, 120) if on else (90, 80, 50), (s.x - 36 + i * 24, s.y - 36), 3)
        lbl = self.font.render("Порт беженцев", True, COL_PORT)
        self.screen.blit(lbl, (s.x - lbl.get_width() / 2, s.y + 38))

    def _events(self, world, radar):
        for ev in world.events.active:
            if ev.phase(world.t) != "active":
                continue
            # Сигнатура видна на радаре, если край события в зоне сенсоров
            if world.player.pos.distance_to(ev.pos) - ev.data.radius > max(radar, world.visual_range()):
                continue
            s = self.to_screen(ev.pos)
            pulse = 1.0 + 0.02 * math.sin(world.t * 3)
            pygame.draw.circle(self.screen, ev.data.color, s, int(ev.data.radius * pulse), 1)

    def _node(self, n, t):
        kind = RESOURCES[n.kind]
        s = self.to_screen(n.pos)
        r = 5 + int(n.amount / 12)
        glow = 0.6 + 0.4 * math.sin(t * 2 + n.pos.x)
        col = tuple(int(c * glow) for c in kind.color)
        pygame.draw.polygon(self.screen, col, [(s.x, s.y - r), (s.x + r, s.y), (s.x, s.y + r), (s.x - r, s.y)], 1)

    def _ray(self, r):
        k = 1.0 - r.depth
        if k <= 0.05:
            return
        col = (int(60 + 100 * k), int(120 + 100 * k), int(140 + 90 * k))
        shape = ((7, 0), (-3, 9), (-6, 0), (-3, -9))
        self.poly(shape, r.pos, r.angle, tuple(int(c * k) for c in col))

    def _tihodont(self, tx, t):
        s = self.to_screen(tx.pos)
        body = (60, 30, 30) if tx.angry else (18, 34, 42)
        fwd = heading(tx.angle)
        rect = pygame.Rect(0, 0, Tihodont.RADIUS * 2.2, Tihodont.RADIUS * 1.3)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (*body, 200), rect)
        for i in range(7):
            x = rect.w * (0.2 + 0.1 * i)
            y = rect.h * (0.5 + 0.25 * math.sin(i * 1.7))
            a = int(140 + 100 * math.sin(t * 1.5 + i))
            pygame.draw.circle(surf, (90, 220, 200, max(0, a)), (x, y), 3)
        rot = pygame.transform.rotate(surf, -Vector2(1, 0).angle_to(fwd))
        self.screen.blit(rot, rot.get_rect(center=s))

    def _ship(self, ship, color, player=False):
        if ship.throttle > 0.05:
            tail = ship.pos - heading(ship.angle) * (ship.cls.radius + 4)
            flame = (255, 160, 70) if ship.boosting else (120, 180, 220)
            pygame.draw.circle(self.screen, flame, self.to_screen(tail), 3 + (2 if ship.boosting else 0))
        if player and ship.fouling > 0.05:
            f = ship.fouling
            color = tuple(int(c * (1 - f) + v * f) for c, v in zip(color, (150, 80, 200)))
        self.poly(ship.cls.shape, ship.pos, ship.angle, color)
        if ship.shield > 1:
            a = ship.shield / max(1.0, ship.cls.shield)
            col = (int(30 + 30 * a), int(60 + 80 * a), int(90 + 110 * a))
            pygame.draw.circle(self.screen, col, self.to_screen(ship.pos), int(ship.cls.radius + 6), 1)
