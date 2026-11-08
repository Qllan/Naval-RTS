"""Отрисовка мира: собирает слои из nine/gfx в кадр.

Порядок слоёв: вода → Око (низ) → порт → следы на воде → ресурсы, лут, фауна →
корабли → снаряды → дым → Пелена → [освещение: сцена × карта света] →
светящееся (вспышки, трассеры, огни) → рукава шторма → погода → туман войны → маркеры.
"""

import math

import pygame
from pygame.math import Vector2

from .gfx import objects as O
from .gfx import palette as P
from .gfx.camera import Camera
from .gfx.fx import FX
from .gfx.islands_art import IslandArt
from .gfx.port_art import PortArt, port_lights
from .gfx.lighting import Lighting, ambient_color, sun_shadow
from .gfx.ocean import FogOfWar, Ocean
from .gfx.ship_art import ShipArt, nav_lights, window_lights
from .gfx.wake import Wakes
from .gfx import veil_fx as VF
from .gfx import events_fx as EF
from collections import deque
from .ship import heading


class Renderer:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.cam = Camera(self.w, self.h)
        self.art = ShipArt()
        self.fx = FX()
        self.fx.art = self.art
        self.wakes = Wakes()
        self.islands = IslandArt()
        self.port = PortArt()
        self.motes = VF.VeilMotes()
        self.sky = VF.SkyGlimpse(self.w, self.h)
        self.distortion = True            # искажения в плотной Пелене (настройка)
        self.lightning = False
        self.last_events = []
        self.haze_enabled = True
        self.halos = True
        self.ocean = Ocean()
        self.haze = VF.Haze(self.ocean.wisp_tile)
        self.fog = FogOfWar(self.w, self.h)
        self.font = pygame.font.Font(None, 20)
        self.small = pygame.font.Font(None, 17)
        self._last_t = None
        self.high_quality = True
        self.lighting = Lighting(self.w, self.h, scale=2)

    def toggle_quality(self):
        """F10: низкое качество — карта света грубее, меньше частиц, без косм Пелены."""
        self.high_quality = not self.high_quality
        self.lighting.set_scale(2 if self.high_quality else 4)
        self.lighting.cache.clear()
        self.fx.max_particles = 2200 if self.high_quality else 700
        self.ocean.set_quality(self.high_quality)
        self.wakes.high_quality = self.high_quality
        self.halos = self.high_quality
        self.motes.max_count = 160 if self.high_quality else 60
        self.haze_enabled = self.high_quality

    def s2w(self, pos):
        return self.cam.s2w(pos)

    # --------------------------------------------------------------------

    def draw(self, world):
        p = world.player
        cam = self.cam
        if self._last_t is None:
            cam.snap(p.pos)
            dt = 1 / 60
        else:
            dt = max(0.0, min(0.1, world.t - self._last_t))
        self._last_t = world.t
        screen = self.screen
        t = world.t

        cam.update(dt, p.pos, lead=p.vel * 0.35)
        vis = world.visual_range()
        radar = world.radar_range()

        def seen(pos):
            return p.pos.distance_to(pos) < vis

        def blip(pos):
            return p.pos.distance_to(pos) < radar

        events = deque(world.fx)
        world.fx.clear()
        self.last_events = list(events)           # для звука и HUD
        for ev in events:
            if ev[0] == "sky":
                self.sky.trigger()
        self.fx.consume(events, cam, p)
        self.fx.ambient(world, cam, dt, lambda pos: cam.visible(pos, 80) and seen(pos))
        self.fx.update(dt)

        daylight = world.daylight()
        wake_ships = [p] + [pr.ship for pr in world.pirates if seen(pr.ship.pos)]
        self.wakes.update(wake_ships, t, dt)

        self.ocean.draw_water(screen, cam, t)
        self.islands.prefetch(world.islands, cam.center)
        for isl in world.islands:
            self.islands.draw(screen, cam, isl, t, daylight)
        self.wakes.draw(screen, cam, t, daylight)
        VF.draw_surge_telegraphs(screen, cam, world, self.fx)
        EF.draw_under(screen, cam, world, self.fx)
        self.ocean.draw_eye_under(screen, cam, world, self.fx)
        self.port.draw(screen, cam, world, self.font)
        self.fx.draw(screen, cam, "water")

        for n in world.nodes:
            if cam.visible(n.pos) and (seen(n.pos) or blip(n.pos)):
                O.draw_node(screen, cam, n, t, self.fx)
        for lt in world.loot:
            if cam.visible(lt.pos) and (seen(lt.pos) or blip(lt.pos)):
                O.draw_loot(screen, cam, lt, t)
        for r in world.rays:
            if cam.visible(r.pos) and seen(r.pos):
                O.draw_ray(screen, cam, r, t)
        for tx in world.tihodonts:
            # Тиходонты экранированы от радаров — только визуально
            if cam.visible(tx.pos, 200) and seen(tx.pos):
                O.draw_tihodont(screen, cam, tx, t, self.fx)

        shadow = sun_shadow(world, cam.zoom)
        ships = []
        for pr in world.pirates:
            s = pr.ship
            if not cam.visible(s.pos):
                continue
            if seen(s.pos):
                Wakes.bow_wave(screen, cam, s, daylight)
                self.art.draw(screen, cam, s, "pirate", t, shadow=shadow)
                VF.draw_cocoon(screen, cam, s, t)
                ships.append(s)
            elif blip(s.pos):
                self._blip(s.pos, t)
        for ph in world.phantoms:                  # галлюцинации неотличимы от настоящих отметок
            if cam.visible(ph["pos"]):
                self._blip(ph["pos"], t)

        alpha = 90 if p.utility_active("bioscreen") else 255
        Wakes.bow_wave(screen, cam, p, daylight)
        self.art.draw(screen, cam, p, "capsule" if world.in_capsule else "player", t, alpha, shadow=shadow)
        VF.draw_cocoon(screen, cam, p, t)
        ships.append(p)

        for pr in world.projectiles:
            if not cam.visible(pr.pos):
                continue
            if pr.kind == "torpedo" and pr.side != "player" and p.pos.distance_to(pr.pos) > vis * 0.6:
                continue          # торпеду под водой видно только вблизи
            self._projectile_body(pr)

        self.fx.draw(screen, cam, "air", emissive=False)
        for sm in world.smokes:
            if cam.visible(sm.pos, sm.radius):
                O.draw_smoke_screen(screen, cam, sm, self.fx, t)
        clear = []
        for tr in self.wakes.trails.values():
            for i, (ts, pos, ang, sp, hw) in enumerate(tr):
                age = t - ts
                if age < 3.0 and i % 3 == 0:
                    clear.append(((pos.x, pos.y), (1 - age / 3.0) * min(1.0, sp / 90)))
        self.ocean.draw_veil(screen, cam, world, clear)
        d_here = world.density_at(p.pos)
        if self.haze_enabled:
            self.haze.draw(screen, cam, d_here, t)

        # --- освещение
        ambient = ambient_color(world)
        storm = EF.storm_strength(world)
        if storm > 0:
            ambient = P.mix(ambient, (110, 120, 140), 0.45 * storm)
        if self.fx.flash > 0:
            ambient = P.mix(ambient, (255, 255, 255), self.fx.flash)
        night = 1.0 - world.daylight()
        lights = self._lights(world, ships, night)
        if self.lighting.begin(ambient):
            for kind, pos, r, col, k in lights:
                if kind == "spot":
                    self.lighting.spot(pos, r[0], r[1], col)
                else:                             # point и flood — обычные источники
                    self.lighting.light(pos, r, col, k)
            self.lighting.apply(screen)
        if self.halos:
            self._halos(world, lights, night)

        # --- светящееся поверх освещения
        self.fx.draw(screen, cam, "air", emissive=True)
        for pr in world.projectiles:
            if cam.visible(pr.pos):
                self._projectile_glow(pr)
        if night > 0.05:
            self._nav_lights(ships, night, t)
        EF.draw_emissive(screen, cam, world, self.fx, night)
        self.motes.update(world, cam, dt)
        self.motes.draw(screen, cam, t, night, self.fx)
        self._shield_bubble(p, t)
        for s in ships:
            if s is not p:
                self._hp_bar(s)

        self.ocean.draw_eye_over(screen, cam, world)
        self.ocean.draw_weather(screen, cam, world, self.fx)
        self.sky.draw(screen, dt, self.fx)
        self.lightning = EF.draw_rain(screen, cam, world, self.fx, dt)
        self.fog.draw(screen, cam, p.pos, vis)
        if self.distortion and self.high_quality:
            VF.distort(screen, d_here, t)
        self._event_signatures(world, radar)
        if radar > 0:
            pygame.draw.circle(screen, (40, 90, 80), cam.w2s(p.pos), int(cam.px(radar)), 1)
        self._lock_marker(world)

    # --- свет ------------------------------------------------------------

    def _lights(self, world, ships, night):
        """Источники света кадра: [(вид, экранная позиция, радиус px, цвет, сила)].

        Один список кормит и карту освещения (ночью), и ореолы в тумане (всегда).
        """
        cam = self.cam
        p = world.player
        t = world.t
        out = []

        def add(pos, radius, col, k, halo=True):
            if k > 0.02 and cam.visible(pos, radius):
                out.append(("point" if halo else "flood", cam.w2s(pos), cam.px(radius), col, k))

        for s in ships:
            add(s.pos, s.radius * 3.2, (120, 120, 110), 0.7 * night, halo=False)
            for wp in window_lights(s):
                add(wp, 14, (255, 210, 140), 0.8 * night)
            for pos, col in nav_lights(s):
                add(pos, 12, col, 0.9 * night)
        if world.spotlight and not world.in_capsule:
            bow = p.pos + Vector2(p.radius, 0).rotate(p.angle)
            out.append(("spot", cam.w2s(bow), (p.angle, cam.px(560)), (235, 235, 215), 1.0))
            add(bow, 30, (255, 250, 230), 1.0, halo=False)
        for pos, radius, col, k in self.fx.lights():
            add(pos, radius, col, k)
        for pr in world.projectiles:
            add(pr.pos, 26 if pr.kind == "shell" else 44, P.TRACER_EM if pr.dtype == "em" else (255, 190, 120), 0.6)
        if cam.visible(world.port, 400):
            for lp, col, r in port_lights(world):
                add(lp, r, col, 1.0)
        for n in world.nodes:
            if n.kind != "salt":
                col = {"condensate": (170, 110, 240), "filament": (200, 170, 255), "zero": (255, 255, 255)}[n.kind]
                add(n.pos, 60 + n.amount, col, 0.7 + 0.2 * math.sin(t * 2 + n.pos.x))
        for tx in world.tihodonts:
            if p.pos.distance_to(tx.pos) < world.visual_range() + 150:
                add(tx.pos, 170, (240, 90, 60) if tx.angry else (60, 220, 190), 0.55)
        for isl in world.islands:
            if isl.ruins and cam.visible(isl.pos, isl.r_max + 200):
                on = int(t * 1.2 + isl.seed % 7) % 3 == 0
                for b in self.islands.beacons(isl):
                    add(b, 90 if on else 30, (255, 70, 50), 0.9 if on else 0.3)
        add(world.eye, 700, (200, 200, 255), 1.0)
        for ev in world.events.active:
            if ev.phase(t) == "active" and ev.data.telegraphed_by_rays:
                add(ev.pos, ev.data.radius, (120, 60, 170), 0.6)
        for pos, r, col, k in EF.bloom_lights(world):
            add(pos, r, col, k)
        return out

    def _halos(self, world, lights, night):
        """Ореолы: свет рассеивается в тумане Пелены — чем гуще, тем шире и ярче ореол."""
        cam = self.cam
        base = 0.2 + 0.8 * night
        for kind, pos, r, col, k in lights:
            if kind != "point" or r > 400 or r < 6:
                continue
            d = world.density_at(cam.s2w(pos))
            h = base * k * (0.15 + 0.85 * d)
            if h < 0.06:
                continue
            q = max(1, min(4, round(0.45 * h * 6)))                   # квантование — ради кэша спрайтов
            img = self.fx.glow(P.shade(col, q / 6), r * (0.9 + 0.9 * d))
            self.screen.blit(img, img.get_rect(center=pos), special_flags=pygame.BLEND_ADD)

    def _nav_lights(self, ships, night, t):
        """Сами огни — яркие точки поверх темноты; топовый мигает."""
        cam = self.cam
        for s in ships:
            for i, (pos, col) in enumerate(nav_lights(s)):
                if i == 3 and int(t * 1.5) % 2:
                    continue
                c = cam.w2s(pos)
                img = self.fx.glow(P.shade(col, 0.5 * night), cam.px(4))
                self.screen.blit(img, img.get_rect(center=c), special_flags=pygame.BLEND_ADD)
                pygame.draw.circle(self.screen, col, c, max(1, int(cam.px(0.7))))

    # --------------------------------------------------------------------

    def _blip(self, pos, t):
        s = self.cam.w2s(pos)
        ph = (t * 1.5) % 1
        pygame.draw.circle(self.screen, P.TRACER_PIRATE, s, 3)
        pygame.draw.circle(self.screen, P.mix(P.TRACER_PIRATE, P.OCEAN_DEEP, ph), s, int(6 + 10 * ph), 1)

    def _hp_bar(self, ship):
        if ship.hp >= ship.hull.hp and ship.shield >= ship.shield_max:
            return
        cam = self.cam
        s = cam.w2s(ship.pos) + Vector2(0, -cam.px(ship.radius) - 12)
        w = max(24, int(cam.px(ship.radius * 1.6)))
        x = s.x - w / 2
        pygame.draw.rect(self.screen, (20, 12, 12), (x - 1, s.y - 1, w + 2, 6))
        pygame.draw.rect(self.screen, (200, 90, 70), (x, s.y + 2, int(w * max(0, ship.hp) / ship.hull.hp), 2))
        if ship.shield_max:
            pygame.draw.rect(self.screen, P.SHIELD_HIT, (x, s.y, int(w * ship.shield / ship.shield_max), 2))

    def _shield_bubble(self, ship, t):
        if not ship.shield_max or ship.shield < 1:
            return
        k = ship.shield / ship.shield_max
        cam = self.cam
        r = cam.px(ship.radius + 7)
        s = cam.w2s(ship.pos)
        a = int(40 + 25 * math.sin(t * 3)) if k > 0.25 else int(60 * (0.5 + 0.5 * math.sin(t * 14)))
        layer = pygame.Surface((int(r * 2 + 4), int(r * 2 + 4)), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*P.SHIELD_HIT, int(a * k + 10)), (r + 2, r + 2), int(r), max(1, int(cam.zoom)))
        self.screen.blit(layer, layer.get_rect(center=s))

    def _projectile_body(self, pr):
        """Несветящаяся часть: корпус ракеты, след торпеды."""
        cam, screen = self.cam, self.screen
        s = cam.w2s(pr.pos)
        d = pr.vel.normalize() if pr.vel.length_squared() else Vector2(1, 0)
        if pr.kind == "missile":
            pygame.draw.line(screen, (190, 190, 196), s, s - d * cam.px(4), max(2, int(cam.px(1.4))))
        elif pr.kind == "torpedo":
            pygame.draw.line(screen, (40, 70, 84), s, s - d * cam.px(9), max(2, int(cam.px(2.2))))
            pygame.draw.line(screen, (120, 170, 190), s, s - d * cam.px(4), 1)

    def _projectile_glow(self, pr):
        """Светящаяся часть: трассеры и факел ракеты — видны и ночью."""
        cam, screen = self.cam, self.screen
        s = cam.w2s(pr.pos)
        d = pr.vel.normalize() if pr.vel.length_squared() else Vector2(1, 0)
        if pr.kind == "missile":
            img = self.fx.glow((255, 170, 90) if not pr.lost else (140, 110, 90), cam.px(4))
            screen.blit(img, img.get_rect(center=s - d * cam.px(4)), special_flags=pygame.BLEND_ADD)
        elif pr.kind == "shell":
            col = P.TRACER_PLAYER if pr.side == "player" else P.TRACER_PIRATE
            if pr.dtype == "em":
                col = P.TRACER_EM
            elif pr.ammo == "ap":
                col = (220, 235, 255)
            elif pr.ammo == "he":
                col = (255, 170, 80)
            length = cam.px(4 + pr.damage * 0.35)
            pygame.draw.line(screen, col, s, s - d * length, max(1, int(cam.px(0.8 + pr.damage / 30))))
            img = self.fx.glow(P.shade(col, 0.55), cam.px(3 + pr.damage / 12))
            screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)

    def _event_signatures(self, world, radar):
        """Сигнатура активного события видна на сенсорах, но не его тип — пунктирный круг."""
        cam = self.cam
        for ev in world.events.active:
            if ev.phase(world.t) != "active":
                continue
            if world.player.pos.distance_to(ev.pos) - ev.data.radius > max(radar, world.visual_range()):
                continue
            if ev.data.shape == "band":
                d, pp = ev.direction, ev.direction.rotate(90)
                R, W = ev.data.radius, ev.data.width
                corners = [ev.pos + d * a * R + pp * b * W for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                for i in range(4):
                    a, b = corners[i], corners[(i + 1) % 4]
                    for k in range(0, 20, 2):
                        pygame.draw.line(self.screen, P.shade(ev.data.color, 0.8), cam.w2s(a + (b - a) * k / 20),
                                         cam.w2s(a + (b - a) * (k + 1) / 20), 1)
                continue
            s = cam.w2s(ev.pos)
            r = cam.px(ev.data.radius)
            n = 48
            rot = world.t * 0.05
            for i in range(0, n, 2):
                a0 = rot + i / n * math.tau
                a1 = rot + (i + 1) / n * math.tau
                pygame.draw.line(self.screen, P.shade(ev.data.color, 0.8),
                                 (s.x + math.cos(a0) * r, s.y + math.sin(a0) * r),
                                 (s.x + math.cos(a1) * r, s.y + math.sin(a1) * r), 1)

    def _target_info(self, ship, anchor):
        """Подсказка по цели: корпус, вооружение, защита — читаемость врага."""
        weapons = ", ".join(m.defn.name.split("«")[0].strip() if "«" in m.defn.name else m.defn.name
                            for m in ship.weapons) or "без оружия"
        lines = [ship.hull.name, weapons,
                 f"Щит {int(ship.shield)}  Броня {int(ship.armor)}  Корпус {int(ship.hp)}"]
        if ship.fires or ship.leaks:
            lines.append(f"Пожары {ship.fires}, течи {ship.leaks}")
        x, y = anchor
        width = max(self.small.size(line)[0] for line in lines) + 16
        height = 15 * len(lines) + 10
        if x + width > self.w - 345:              # не заезжать на панель оружия справа
            x = anchor[0] - width - 2 * (self.cam.px(ship.radius) + 17)
        y = min(max(y, 60), self.h - height - 120)       # выше подсказок внизу экрана
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        box.fill((6, 10, 16, 200))
        self.screen.blit(box, (x, y))
        pygame.draw.line(self.screen, P.TRACER_PIRATE, (x, y), (x, y + height), 2)
        for i, line in enumerate(lines):
            img = self.small.render(line, True, (235, 220, 160) if i == 0 else (175, 185, 180))
            self.screen.blit(img, (x + 9, y + 5 + i * 15))

    def _lock_marker(self, world):
        cam = self.cam
        gt = world.gun_target
        if gt is not None and not world.in_capsule:
            s = cam.w2s(gt.pos)
            r = cam.px(gt.radius) + 8
            pygame.draw.circle(self.screen, (230, 220, 150), s, int(r), 1)
            for a in (0, 90, 180, 270):
                d = heading(a + world.t * 30)
                pygame.draw.line(self.screen, (230, 220, 150), s + d * (r - 3), s + d * (r + 5), 1)
            self._target_info(gt, s + Vector2(r + 10, -r))
        tgt = world.lock_candidate
        mounts = [m for m in world.player.weapons if m.defn.kind == "missile"]
        if tgt is None or not mounts or world.in_capsule:
            return
        lock = max(m.lock for m in mounts)
        s = cam.w2s(tgt.pos)
        r = cam.px(tgt.radius) + 14
        col = (255, 90, 70) if lock >= 1 else (240, 180, 80) if lock > 0 else (120, 120, 120)
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            c = s + Vector2(sx * r, sy * r)
            pygame.draw.line(self.screen, col, c, c - Vector2(sx * 7, 0), 2)
            pygame.draw.line(self.screen, col, c, c - Vector2(0, sy * 7), 2)
        if 0 < lock < 1:
            pygame.draw.arc(self.screen, col, (s.x - r, s.y - r, r * 2, r * 2), 0, lock * math.tau, 2)
