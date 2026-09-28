"""Океан, Пелена и погода.

Океан — бесшовная текстура из шума + бегущая рябь + блики.
Пелена — две части: общий оттенок по плотности (маска низкого разрешения) и
клубящиеся «космы» тумана, которые видны только там, где Пелена густая.
"""

import math
import random

import numpy as np
import pygame
from pygame.math import Vector2

from .. import config as C
from ..veil import ValueNoise
from . import palette as P

TILE_PX = 128
_TILES = {}                 # текстуры строятся один раз на процесс
OCEAN_TILE_W = 520.0        # мировой размер плитки океана
WISP_TILE_W = 700.0
SWELL_TILE_W = 900.0
MASK_CELL_PX = 30
VEIL_EVERY = 4             # оттенок и космы пересчитываются раз в N кадров (со сдвигом)


def _tile(fn, n=TILE_PX):
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    for y in range(n):
        for x in range(n):
            s.set_at((x, y), fn(x / n, y / n))
    return s


def _fbm(noises, u, v):
    total, amp, norm = 0.0, 1.0, 0.0
    for nz in noises:
        total += nz.sample(u * nz.size, v * nz.size) * amp
        norm += amp
        amp *= 0.5
    return total / norm


class Ocean:
    def __init__(self, seed=5):
        n1, n2, n3 = ValueNoise(seed, 6), ValueNoise(seed + 1, 12), ValueNoise(seed + 2, 24)

        def water(u, v):
            k = _fbm((n1, n2, n3), u, v)
            c = P.mix(P.OCEAN_DEEP, P.OCEAN_LIGHT, max(0.0, min(1.0, (k - 0.25) * 1.3)) ** 1.6)
            return (*c, 255)

        r1, r2 = ValueNoise(seed + 5, 8), ValueNoise(seed + 6, 16)

        def ripple(u, v):
            k = _fbm((r1, r2), u, v)
            ridge = max(0.0, 1.0 - abs(k - 0.5) * 18)          # тонкие гребни
            return (*P.GLINT, int(26 * ridge))

        s1, s2 = ValueNoise(seed + 13, 4), ValueNoise(seed + 14, 8)

        def swell(u, v):
            # направленная зыбь: вытянутые гребни поперёк ветра, изломанные шумом
            k = _fbm((s1, s2), u, v)
            phase = u * 5 + v * 2 + k * 1.8
            crest = max(0.0, math.sin(2 * math.pi * phase)) ** 6
            trough = max(0.0, -math.sin(2 * math.pi * phase)) ** 2
            if crest > trough:
                return (*P.GLINT, int(44 * crest))
            return (2, 6, 12, int(40 * trough))

        w1, w2, w3 = ValueNoise(seed + 9, 4), ValueNoise(seed + 10, 8), ValueNoise(seed + 11, 16)

        def wisp(u, v):
            k = _fbm((w1, w2, w3), u, v)
            a = max(0.0, min(1.0, (k - 0.38) * 2.6))
            return (*P.VEIL_WISP, int(170 * a ** 1.3))

        if seed not in _TILES:
            _TILES[seed] = (_tile(water), _tile(ripple, 192), _tile(wisp), _tile(swell, 160))
        self.water_tile, self.ripple_tile, self.wisp_tile, self.swell_tile = _TILES[seed]
        self._scaled = {}
        self.rng = random.Random(seed)
        self.mask_small = None
        self._mask_zoom = None
        self._wisp_zoom = None
        self.density_view = None
        self.frame = 0
        self._screen_layer = None
        self.wisps_enabled = True

    def _layer(self, cam):
        """Переиспользуемый полноэкранный прозрачный слой."""
        if self._screen_layer is None or self._screen_layer.get_size() != (cam.w, cam.h):
            self._screen_layer = pygame.Surface((cam.w, cam.h), pygame.SRCALPHA)
        self._screen_layer.fill((0, 0, 0, 0))
        return self._screen_layer

    def _scaled_tile(self, name, tile, world_w, zoom):
        # масштаб квантуется: во время плавного зума кэш не пересобирается каждый кадр
        zq = max(0.05, round(zoom / 0.06) * 0.06)
        size = max(8, int(world_w * zq))
        key = (name, size)
        img = self._scaled.get(key)
        if img is None:
            if len(self._scaled) > 60:
                self._scaled.clear()
            # масштабируем мозаику 3×3 и берём центр — без швов на краях плитки
            n = tile.get_width()
            mosaic = pygame.Surface((n * 3, n * 3), pygame.SRCALPHA)
            for i in range(3):
                for j in range(3):
                    mosaic.blit(tile, (i * n, j * n))
            big = pygame.transform.smoothscale(mosaic, (size * 3, size * 3))
            img = self._scaled[key] = big.subsurface((size, size, size, size)).copy()
        return img

    def _tiled(self, screen, img, world_w, cam, offset=Vector2()):
        size = img.get_width()
        period = size / cam.zoom          # мировой период = фактический размер плитки
        x0, y0, x1, y1 = cam.world_rect()
        ox = (x0 + offset.x) % period
        oy = (y0 + offset.y) % period
        sx = int(-ox * cam.zoom)
        sy = int(-oy * cam.zoom)
        y = sy
        while y < cam.h:
            x = sx
            while x < cam.w:
                screen.blit(img, (x, y))
                x += size
            y += size

    # --- вода ---------------------------------------------------------------

    def draw_water(self, screen, cam, t):
        self._tiled(screen, self._scaled_tile("water", self.water_tile, OCEAN_TILE_W, cam.zoom), OCEAN_TILE_W, cam)
        sw = self._scaled_tile("swell", self.swell_tile, SWELL_TILE_W, cam.zoom)
        self._tiled(screen, sw, SWELL_TILE_W, cam, Vector2(-t * 16, -t * 6))       # зыбь бежит по ветру
        rip = self._scaled_tile("ripple", self.ripple_tile, OCEAN_TILE_W * 0.7, cam.zoom)
        self._tiled(screen, rip, OCEAN_TILE_W * 0.7, cam, Vector2(t * 9, t * 4))
        self._tiled(screen, rip, OCEAN_TILE_W * 0.7, cam, Vector2(-t * 6 + 211, t * 7 + 97))
        # блики: детерминированные точки мира, мерцают
        x0, y0, x1, y1 = cam.world_rect()
        step = 70
        for gy in range(int(y0 // step), int(y1 // step) + 1):
            for gx in range(int(x0 // step), int(x1 // step) + 1):
                h = (gx * 73856093 ^ gy * 19349663) & 0xffff
                ph = math.sin(t * (1.2 + (h % 7) * 0.2) + h)
                if ph < 0.75:
                    continue
                wx = gx * step + (h % step)
                wy = gy * step + ((h >> 6) % step)
                s = cam.w2s((wx, wy))
                k = (ph - 0.75) * 4
                pygame.draw.line(screen, P.mix(P.OCEAN_LIGHT, P.GLINT, k), s, s + Vector2(cam.px(4), 0), 1)

    # --- Пелена ---------------------------------------------------------------

    def draw_veil(self, screen, cam, world, clear_points=()):
        """Оттенок по плотности + космы тумана, видимые только в густой Пелене.

        Оба слоя привязаны к миру; оттенок и космы пересчитываются в разных кадрах
        (чтобы не было пиков), а между пересчётами сдвигаются вместе с камерой.
        """
        self.frame += 1
        zoom_changed = self._mask_zoom is None or abs(cam.zoom / self._mask_zoom - 1) > 0.03
        if self.mask_small is None or zoom_changed or self.frame % VEIL_EVERY == 0:
            self._rebuild_tint(cam, world, clear_points)
        if self.wisps_enabled and (self._wisp_zoom is None or zoom_changed
                                   or self.frame % VEIL_EVERY == VEIL_EVERY // 2):
            self._rebuild_wisps(cam, world)
        screen.blit(self.tint_big, cam.w2s(self._mask_origin))
        if self.wisps_enabled:
            screen.blit(self.wisps, cam.w2s(self._wisp_origin))

    def _rebuild_tint(self, cam, world, clear_points=()):
        cw, ch = cam.w // MASK_CELL_PX + 3, cam.h // MASK_CELL_PX + 3
        step = MASK_CELL_PX / cam.zoom
        x0, y0, _, _ = cam.world_rect()
        x0 -= x0 % step + step
        y0 -= y0 % step + step
        self._mask_origin = Vector2(x0, y0)
        self._mask_zoom = cam.zoom
        xs = x0 + np.arange(cw) * step
        ys = y0 + np.arange(ch) * step
        d = world.veil.density_grid(xs, ys, world.t).T
        # кильватер расчищает туман на пару секунд
        if clear_points:
            X, Y = np.meshgrid(xs, ys, indexing="ij")
            clear = np.zeros_like(d)
            for (px, py), k in clear_points:
                clear += k * np.exp(-((X - px) ** 2 + (Y - py) ** 2) / (60.0 ** 2))
            d = d * (1 - np.clip(clear, 0, 0.85))
        self.density_view = d
        hot = np.clip(d - 0.75, 0, 1)[..., None] * 2
        base, surge = np.array(P.VEIL_TINT, float), np.array(P.SURGE, float)
        rgb = base + (surge - base) * hot
        # светящиеся границы зон: Чистый слой | Мгла | Плотная Пелена
        pulse = 0.75 + 0.25 * math.sin(world.t * 2.2)
        band = (np.exp(-((d - 0.30) / 0.018) ** 2) + np.exp(-((d - 0.60) / 0.018) ** 2)) * pulse
        rgb = rgb + (np.array((210, 180, 255), float) - rgb) * np.clip(band, 0, 1)[..., None] * 0.7
        tint = pygame.Surface((cw, ch), pygame.SRCALPHA)
        pygame.surfarray.pixels3d(tint)[:] = np.clip(rgb, 0, 255).astype(np.uint8)
        alpha = np.minimum(92, 4 + 90 * d ** 1.5) + 70 * np.clip(band, 0, 1)
        pygame.surfarray.pixels_alpha(tint)[:] = np.clip(alpha, 0, 255).astype(np.uint8)
        mask = pygame.Surface((cw, ch), pygame.SRCALPHA)
        mask.fill((255, 255, 255, 0))
        pygame.surfarray.pixels_alpha(mask)[:] = (200 * np.clip((d - 0.25) * 1.6, 0, 1)).astype(np.uint8)
        self.tint_big = pygame.transform.smoothscale(tint, (cw * MASK_CELL_PX, ch * MASK_CELL_PX))
        self.mask_small = mask

    def _rebuild_wisps(self, cam, world):
        """Космы: две текстуры, плывущие в разные стороны, под маской плотности."""
        cw, ch = self.mask_small.get_size()
        size = (cw * MASK_CELL_PX, ch * MASK_CELL_PX)
        self._wisp_origin = Vector2(self._mask_origin)
        self._wisp_zoom = cam.zoom
        t = world.t
        layer = pygame.Surface(size, pygame.SRCALPHA)
        wisp = self._scaled_tile("wisp", self.wisp_tile, WISP_TILE_W, cam.zoom)
        for off in (Vector2(-t * 14, t * 6), Vector2(t * 9 + 333, -t * 11 + 170)):
            self._tiled_at(layer, wisp, WISP_TILE_W, cam.zoom, self._wisp_origin + off, size)
        layer.blit(pygame.transform.smoothscale(self.mask_small, size), (0, 0),
                   special_flags=pygame.BLEND_RGBA_MULT)
        self.wisps = layer

    def _tiled_at(self, surf, img, world_w, zoom, world_origin, size):
        """Замостить `surf`, чей левый верхний угол — точка мира `world_origin`."""
        tile = img.get_width()
        period = tile / zoom
        sx = int(-(world_origin.x % period) * zoom)
        sy = int(-(world_origin.y % period) * zoom)
        y = sy
        while y < size[1]:
            x = sx
            while x < size[0]:
                surf.blit(img, (x, y))
                x += tile
            y += tile

    # --- Око Девятки ------------------------------------------------------------

    def draw_eye_under(self, screen, cam, world, fx):
        eye = world.eye
        if not cam.visible(eye, C.EYE_BELT_R):
            return
        s = cam.w2s(eye)
        r = cam.px(C.EYE_CALM_R)
        # Зеркало: чёрная ртутная вода с отблеском
        pygame.draw.circle(screen, (3, 3, 6), s, int(r))
        for i in range(3):
            pygame.draw.circle(screen, (30 + i * 12, 30 + i * 12, 40 + i * 14), s, int(r * (0.97 - i * 0.18)), 1)
        pulse = 1 + 0.08 * math.sin(world.t * 2)
        for rad, col in ((r * 0.55, (40, 40, 60)), (r * 0.3, (110, 110, 140)), (r * 0.12, (255, 255, 255))):
            img = fx.glow(col, rad * pulse)
            screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)

    def draw_eye_over(self, screen, cam, world):
        """Рукава шторма Стены Рёва поверх Пелены."""
        eye = world.eye
        if not cam.visible(eye, C.EYE_WALL_R):
            return
        s = cam.w2s(eye)
        t = world.t
        layer = self._layer(cam)
        for arm in range(9):
            base = arm * 40 + t * 22
            pts = []
            for k in range(28):
                rr = C.EYE_CALM_R * 1.05 + (C.EYE_WALL_R - C.EYE_CALM_R) * k / 27
                a = math.radians(base + k * 13 + 6 * math.sin(t + arm))      # закрученная спираль
                pts.append((s.x + math.cos(a) * cam.px(rr), s.y + math.sin(a) * cam.px(rr)))
            width = max(2, int(cam.px(14)))
            pygame.draw.lines(layer, (170, 120, 230, 60), False, pts, width)
            pygame.draw.lines(layer, (210, 180, 255, 90), False, pts, max(1, width // 5))
        screen.blit(layer, (0, 0))

    # --- погода ---------------------------------------------------------------

    def draw_weather(self, screen, cam, world, fx):
        p = world.player
        t = world.t
        dist = p.pos.distance_to(world.eye)
        # дождь и ветер у Ока
        storm = max(0.0, 1.0 - (dist - C.EYE_CALM_R) / (C.EYE_BELT_R - C.EYE_CALM_R)) if dist > C.EYE_CALM_R else 0
        if storm > 0.02:
            tang = Vector2(p.pos - world.eye).rotate(100).normalize() if dist > 1 else Vector2(1, 0)
            rng = random.Random(int(t * 30))
            n = int(160 * storm)
            vec = tang * 16 + Vector2(0, 8)
            for _ in range(n):
                x = rng.uniform(0, cam.w)
                y = rng.uniform(0, cam.h)
                pygame.draw.line(screen, (150, 150, 185), (x, y), (x + vec.x, y + vec.y), 1)
        # Всплеск: пульсирующее свечение и разряды
        for ev in world.events.active:
            if ev.phase(t) != "active" or not ev.data.telegraphed_by_rays:
                continue
            if not cam.visible(ev.pos, ev.data.radius):
                continue
            k = ev.strength(p.pos, t)
            if k > 0:
                pulse = 0.5 + 0.5 * math.sin(t * 5)
                tint = self._layer(cam)
                tint.fill((*P.SURGE, int(30 * k * pulse)))
                screen.blit(tint, (0, 0))
            rng = random.Random(int(t * 8) + id(ev) % 97)
            if rng.random() < 0.5:
                start = ev.pos + Vector2(1, 0).rotate(rng.uniform(0, 360)) * rng.uniform(0, ev.data.radius)
                if cam.visible(start, 50):
                    pts = [cam.w2s(start)]
                    d = Vector2(1, 0).rotate(rng.uniform(0, 360))
                    for _ in range(6):
                        d = d.rotate(rng.uniform(-50, 50))
                        pts.append(pts[-1] + d * cam.px(rng.uniform(8, 20)))
                    pygame.draw.lines(screen, (220, 180, 255), False, pts, 1)
        if fx.flash > 0:
            v = int(90 * fx.flash)
            screen.fill((v, v, int(v * 1.2)), special_flags=pygame.BLEND_ADD)


class FogOfWar:
    """Затемнение за пределами визуальной дальности."""

    ALPHA = 118

    def __init__(self, w, h):
        self.layer = pygame.Surface((w, h), pygame.SRCALPHA)
        n = 256
        g = pygame.Surface((n, n), pygame.SRCALPHA)
        c = (n - 1) / 2
        for y in range(n):
            for x in range(n):
                r = math.hypot(x - c, y - c) / c
                k = min(1.0, max(0.0, (r - 0.55) / 0.45))
                g.set_at((x, y), (0, 0, 0, int(self.ALPHA * k * k * (3 - 2 * k))))
        self.grad = g
        self.cache = {}

    def draw(self, screen, cam, center_world, radius):
        size = max(8, int(cam.px(radius) * 2) // 8 * 8)
        img = self.cache.get(size)
        if img is None:
            if len(self.cache) > 80:
                self.cache.clear()
            img = self.cache[size] = pygame.transform.smoothscale(self.grad, (size, size))
        self.layer.fill((0, 0, 0, self.ALPHA))
        self.layer.blit(img, img.get_rect(center=cam.w2s(center_world)), special_flags=pygame.BLEND_RGBA_MIN)
        screen.blit(self.layer, (0, 0))
