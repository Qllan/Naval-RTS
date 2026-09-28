"""Острова: текстура строится numpy'ем при первом появлении на экране и кэшируется.

Слои: мелководье (бирюзовый ореол) → мокрый камень у кромки → галька → скалы с
рельефным светом (свет с северо-запада) и мхом → руины Эры I. Прибой рисуется
каждый кадр вдоль береговой линии.
"""

import math
import random
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pygame
from pygame.math import Vector2

from . import palette as P

PX = 1.0                    # пикселей на мировую единицу в мастер-текстуре
SHALLOW = 0.45              # ширина мелководья в долях радиуса
ZOOM_STEP = 0.02           # точность масштаба: берег должен совпадать с коллизией


def np_noise(n, cells, rng):
    """Value-noise n×n на решётке cells×cells с плавной интерполяцией."""
    grid = rng.random((cells + 1, cells + 1), dtype=np.float32)
    u = np.linspace(0, cells, n, endpoint=False, dtype=np.float32)
    i = u.astype(int)
    f = u - i
    f = f * f * (3 - 2 * f)
    a = grid[np.ix_(i, i)]
    b = grid[np.ix_(i, i + 1)]
    c = grid[np.ix_(i + 1, i)]
    d = grid[np.ix_(i + 1, i + 1)]
    fx = f[None, :]
    fy = f[:, None]
    top = a + (b - a) * fx
    bot = c + (d - c) * fx
    return top + (bot - top) * fy


def _mix(c1, c2, k):
    k = np.clip(k, 0, 1)[..., None]
    a = np.asarray(c1, np.float32)
    return a + (np.asarray(c2, np.float32) - a) * k


def build_island(isl):
    ext = isl.r_max * (1 + SHALLOW) + 16
    n = int(ext * 2 * PX)
    rng = np.random.default_rng(isl.seed)
    xs = ((np.arange(n) + 0.5) / PX - ext).astype(np.float32)
    X, Y = np.meshgrid(xs, xs)
    dist = np.hypot(X, Y)
    ang = np.arctan2(Y, X)
    r = np.full_like(dist, isl.radius)
    for a, k, ph in isl.lobes:
        r += isl.radius * a * np.sin(k * ang + ph)
    n1 = np_noise(n, 6, rng)
    n2 = np_noise(n, 18, rng)
    n3 = np_noise(n, 48, rng)
    rel = dist / r + (n2 - 0.5) * 0.05

    # высота: купол + шум → рельефный свет с северо-запада
    # купол по среднему радиусу (не по углу — иначе рельеф «веером»), к берегу — спад до нуля
    dome = np.clip(1 - dist / (isl.radius * 1.05), 0, 1) ** 0.8
    shore = np.clip((1 - rel) * 6, 0, 1)
    h = (dome * 0.7 + (n1 - 0.5) * 0.35 + (n2 - 0.5) * 0.12) * shore
    gy, gx = np.gradient(h)
    light = np.clip(1.0 + (-gx - gy) * 90, 0.45, 1.5)

    rock = _mix((66, 68, 66), (92, 90, 84), n3)
    moss = _mix((40, 58, 48), (54, 74, 58), n3)
    mossy = np.clip((n1 - 0.45) * 3, 0, 1) * np.clip((1 - rel) * 4, 0, 1)
    land = _mix(rock, moss, mossy)
    land = land * light[..., None]
    gravel = _mix((84, 80, 72), (108, 102, 90), n3)
    wet = np.array((34, 38, 40), np.float32)

    rgb = np.zeros((n, n, 3), np.float32)
    alpha = np.zeros((n, n), np.float32)
    shallow = (rel >= 1.0) & (rel < 1 + SHALLOW)
    t = np.clip((rel - 1) / SHALLOW, 0, 1)
    rgb[shallow] = _mix((52, 120, 126), P.OCEAN_MID, t)[shallow]
    alpha[shallow] = (170 * (1 - t) ** 1.6)[shallow]
    # камни на мелководье
    reef = shallow & (n3 > 0.78) & (t < 0.6)
    rgb[reef] = (50, 58, 60)
    alpha[reef] = 220
    edge = (rel < 1.0) & (rel >= 0.965)
    rgb[edge] = wet
    alpha[edge] = 255
    beach = (rel < 0.965) & (rel >= 0.92)
    rgb[beach] = gravel[beach]
    alpha[beach] = 255
    inner = rel < 0.92
    rgb[inner] = land[inner]
    alpha[inner] = 255

    surf = pygame.Surface((n, n), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 0, 2)
    pygame.surfarray.pixels_alpha(surf)[:] = np.clip(alpha, 0, 255).astype(np.uint8).T

    beacons = []
    if isl.ruins:
        beacons = _ruins(surf, isl, ext)
    return surf, ext, beacons


def _ruins(surf, isl, ext):
    """Руины Эры I: фундаменты, стены, обрушенная башня, мачта, цистерны, площадка."""
    rng = random.Random(isl.seed)
    concrete, dark, rust = (118, 118, 112), (58, 58, 56), (120, 70, 44)

    def p(x, y):
        return ((x + ext) * PX, (y + ext) * PX)

    base = isl.radius * 0.45
    cx, cy = rng.uniform(-base, base) * 0.4, rng.uniform(-base, base) * 0.4
    # дорога
    a = rng.uniform(0, math.tau)
    d = Vector2(math.cos(a), math.sin(a))
    pygame.draw.line(surf, (72, 72, 68), p(*(Vector2(cx, cy) - d * base)), p(*(Vector2(cx, cy) + d * base)),
                     max(2, int(5 * PX)))
    # фундаменты и стены
    for _ in range(rng.randint(3, 6)):
        w, h = rng.uniform(14, 34), rng.uniform(10, 24)
        x, y = cx + rng.uniform(-base, base) * 0.8, cy + rng.uniform(-base, base) * 0.8
        rect = pygame.Rect(0, 0, w * PX, h * PX)
        rect.center = p(x, y)
        pygame.draw.rect(surf, concrete, rect)
        pygame.draw.rect(surf, dark, rect.inflate(-4, -4))
        for _ in range(3):                                   # обломки внутри
            q = (rect.x + rng.uniform(2, rect.w - 2), rect.y + rng.uniform(2, rect.h - 2))
            pygame.draw.circle(surf, concrete, q, max(1, int(rng.uniform(1, 3) * PX)))
        pygame.draw.line(surf, (40, 40, 38), rect.topleft, (rect.centerx, rect.top), 2)   # пролом
    # цистерны
    for _ in range(rng.randint(1, 3)):
        q = p(cx + rng.uniform(-base, base), cy + rng.uniform(-base, base))
        r = rng.uniform(5, 9) * PX
        pygame.draw.circle(surf, rust, q, r)
        pygame.draw.circle(surf, (90, 50, 30), q, r, 2)
        pygame.draw.circle(surf, (70, 40, 26), q, r * 0.4)
    # заброшенная вертолётная площадка — полёты невозможны со времён Пелены
    if rng.random() < 0.6:
        q = p(cx - base * 0.5, cy + base * 0.4)
        r = 16 * PX
        pygame.draw.circle(surf, (86, 88, 86), q, r)
        pygame.draw.circle(surf, (170, 160, 90), q, r, 2)
        hx, hy = q
        s = r * 0.45
        for x in (-s * 0.6, s * 0.6):
            pygame.draw.line(surf, (190, 180, 110), (hx + x, hy - s), (hx + x, hy + s), 3)
        pygame.draw.line(surf, (190, 180, 110), (hx - s * 0.6, hy), (hx + s * 0.6, hy), 3)
        pygame.draw.line(surf, (40, 40, 38), (hx - r * 0.7, hy - r * 0.3), (hx + r * 0.2, hy + r * 0.6), 2)
    # обрушенная башня и мачта с тарелкой
    tq = p(cx + base * 0.3, cy - base * 0.3)
    pygame.draw.circle(surf, concrete, tq, 9 * PX)
    pygame.draw.circle(surf, dark, tq, 6 * PX)
    fall = Vector2(1, 0).rotate(rng.uniform(0, 360))
    pygame.draw.line(surf, concrete, tq, (tq[0] + fall.x * 30 * PX, tq[1] + fall.y * 30 * PX), max(3, int(7 * PX)))
    mq = p(cx - base * 0.2, cy - base * 0.5)
    pygame.draw.circle(surf, (150, 150, 146), mq, 5 * PX, 2)
    pygame.draw.line(surf, (150, 150, 146), mq, (mq[0] + 6 * PX, mq[1] - 6 * PX), 2)
    return [Vector2(cx + base * 0.3, cy - base * 0.3) + isl.pos]


class IslandArt:
    """Текстуры островов строятся в фоновом потоке заранее; пока не готово — простой силуэт."""

    PREFETCH = 3000.0

    def __init__(self):
        self.masters = {}           # id острова → (surf, ext, beacons)
        self.pending = {}
        self.scaled = OrderedDict()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def request(self, isl):
        key = id(isl)
        if key not in self.masters and key not in self.pending:
            self.pending[key] = self.pool.submit(build_island, isl)

    def prefetch(self, islands, center):
        """По одной задаче за раз, всегда — ближайший ещё не готовый остров."""
        if any(not f.done() for f in self.pending.values()):
            return
        todo = [i for i in islands if id(i) not in self.masters and id(i) not in self.pending
                and i.pos.distance_to(center) < self.PREFETCH]
        if todo:
            self.request(min(todo, key=lambda i: i.pos.distance_to(center)))

    def _collect(self, isl):
        """Забрать готовый результат фоновой сборки (или None, если ещё строится)."""
        key = id(isl)
        fut = self.pending.get(key)
        if fut is None or not fut.done():
            return None
        m = self.masters[key] = fut.result()
        del self.pending[key]
        return m

    def master(self, isl):
        return self.masters.get(id(isl)) or self._collect(isl)

    def beacons(self, isl):
        m = self.master(isl)
        return m[2] if m else []

    def _placeholder(self, screen, cam, isl):
        c = cam.w2s(isl.pos)
        for scale, col in ((1 + SHALLOW * 0.5, (22, 52, 60)), (1.0, (58, 62, 60))):
            pts = [(c.x + math.cos(a) * isl.r_at(a) * scale * cam.zoom, c.y + math.sin(a) * isl.r_at(a) * scale * cam.zoom)
                   for a in (i / 48 * math.tau for i in range(48))]
            pygame.draw.polygon(screen, col, pts)

    def draw(self, screen, cam, isl, t, daylight):
        if not cam.visible(isl.pos, isl.r_max * (1 + SHALLOW) + 20):
            return
        m = self.masters.get(id(isl)) or self._collect(isl)
        if m is None:
            self._placeholder(screen, cam, isl)
            self._surf_line(screen, cam, isl, t, daylight, cam.zoom)
            return
        surf, ext, _ = m
        zq = max(0.1, round(cam.zoom / ZOOM_STEP) * ZOOM_STEP)
        size = max(4, int(surf.get_width() * cam.zoom / PX))
        key = (id(isl), zq)
        img = self.scaled.get(key)
        if img is None:
            moving = abs(cam.zoom - cam.target_zoom) > 0.01
            near = [k for k in self.scaled if k[0] == id(isl)]
            if moving and near:
                # во время зума — быстрое масштабирование ближайшей готовой картинки
                best = min(near, key=lambda k: abs(k[1] - zq))
                img = pygame.transform.scale(self.scaled[best], (size, size))
            else:
                img = pygame.transform.smoothscale(surf, (size, size))
                self.scaled[key] = img
                if len(self.scaled) > 40:
                    self.scaled.popitem(last=False)
        else:
            self.scaled.move_to_end(key)
        screen.blit(img, img.get_rect(center=cam.w2s(isl.pos)))
        self._surf_line(screen, cam, isl, t, daylight, cam.zoom)

    @staticmethod
    def _surf_line(screen, cam, isl, t, daylight, zq):
        """Прибой: пенная кромка вдоль берега, «дышит» волнами."""
        foam = P.mix((80, 100, 120), P.FOAM, 0.4 + 0.6 * daylight)
        n = 72
        c = cam.w2s(isl.pos)
        for ring, phase in ((1.02, 0.0), (1.07, 1.7)):
            pts = []
            for i in range(n + 1):
                a = i / n * math.tau
                r = isl.r_at(a) * (ring + 0.012 * math.sin(t * 1.6 + a * 7 + phase))
                pts.append((c.x + math.cos(a) * r * zq, c.y + math.sin(a) * r * zq))
            k = 0.6 + 0.4 * math.sin(t * 1.6 + phase)
            col = P.mix(P.OCEAN_MID, foam, (0.55 if ring < 1.05 else 0.25) * k)
            for j in range(0, n, 2 if ring > 1.05 else 1):
                pygame.draw.line(screen, col, pts[j], pts[j + 1], max(1, int(zq * (1.6 if ring < 1.05 else 1))))
