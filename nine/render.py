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
from .gfx.lighting import Lighting, ambient_color, sun_shadow
from .gfx.ocean import FogOfWar, Ocean
from .gfx.ship_art import ShipArt, nav_lights, window_lights
from .gfx.wake import Wakes
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
        self.ocean = Ocean()
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
        self.ocean.wisps_enabled = self.high_quality

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

        self.fx.consume(world.fx, cam, p)
        self.fx.ambient(world, cam, dt, lambda pos: cam.visible(pos, 80) and seen(pos))
        self.fx.update(dt)

        daylight = world.daylight()
        wake_ships = [p] + [pr.ship for pr in world.pirates if seen(pr.ship.pos)]
        self.wakes.update(wake_ships, t, dt)

        self.ocean.draw_water(screen, cam, t)
        self.wakes.draw(screen, cam, t, daylight)
        self.ocean.draw_eye_under(screen, cam, world, self.fx)
        O.draw_port(screen, cam, world, self.font)
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
                ships.append(s)
            elif blip(s.pos):
                self._blip(s.pos, t)

        alpha = 90 if p.utility_active("bioscreen") else 255
        Wakes.bow_wave(screen, cam, p, daylight)
        self.art.draw(screen, cam, p, "capsule" if world.in_capsule else "player", t, alpha, shadow=shadow)
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
        self.ocean.draw_veil(screen, cam, world)

        # --- освещение
        ambient = ambient_color(world)
        if self.fx.flash > 0:
            ambient = P.mix(ambient, (255, 255, 255), self.fx.flash)
        night = 1.0 - world.daylight()
        if self.lighting.begin(ambient):
            self._lights(world, ships, night)
            self.lighting.apply(screen)

        # --- светящееся поверх освещения
        self.fx.draw(screen, cam, "air", emissive=True)
        for pr in world.projectiles:
            if cam.visible(pr.pos):
                self._projectile_glow(pr)
        if night > 0.05:
            self._nav_lights(ships, night, t)
        self._shield_bubble(p, t)
        for s in ships:
            if s is not p:
                self._hp_bar(s)

        self.ocean.draw_eye_over(screen, cam, world)
        self.ocean.draw_weather(screen, cam, world, self.fx)
        self.fog.draw(screen, cam, p.pos, vis)
        self._event_signatures(world, radar)
        if radar > 0:
            pygame.draw.circle(screen, (40, 90, 80), cam.w2s(p.pos), int(cam.px(radar)), 1)
        self._lock_marker(world)

    # --- свет ------------------------------------------------------------

    def _lights(self, world, ships, night):
        cam, L = self.cam, self.lighting
        p = world.player
        t = world.t
        # корабли: палубные огни, окна, ходовые огни
        for s in ships:
            L.light(cam.w2s(s.pos), cam.px(s.radius * 3.2), (120, 120, 110), 0.7 * night)
            for wp in window_lights(s):
                L.light(cam.w2s(wp), cam.px(14), (255, 210, 140), 0.8 * night)
            for pos, col in nav_lights(s):
                L.light(cam.w2s(pos), cam.px(12), col, 0.9 * night)
        if world.spotlight and not world.in_capsule:
            bow = p.pos + Vector2(p.radius, 0).rotate(p.angle)
            L.spot(cam.w2s(bow), p.angle, cam.px(560), (235, 235, 215))
            L.light(cam.w2s(bow), cam.px(30), (255, 250, 230), 1.0)
        # вспышки, взрывы, пожары
        for pos, radius, col, k in self.fx.lights():
            if cam.visible(pos, radius):
                L.light(cam.w2s(pos), cam.px(radius), col, k)
        for pr in world.projectiles:
            if cam.visible(pr.pos):
                col = P.TRACER_EM if pr.dtype == "em" else (255, 190, 120)
                L.light(cam.w2s(pr.pos), cam.px(26 if pr.kind == "shell" else 44), col, 0.6)
        # порт, ресурсы, фауна, Око
        if cam.visible(world.port, 400):
            for lp, col, r in O.port_lights(world):
                L.light(cam.w2s(lp), cam.px(r), col, 1.0)
        for n in world.nodes:
            if n.kind != "salt" and cam.visible(n.pos, 80):
                col = {"condensate": (170, 110, 240), "filament": (200, 170, 255), "zero": (255, 255, 255)}[n.kind]
                L.light(cam.w2s(n.pos), cam.px(60 + n.amount), col, 0.7 + 0.2 * math.sin(t * 2 + n.pos.x))
        for tx in world.tihodonts:
            if cam.visible(tx.pos, 200) and p.pos.distance_to(tx.pos) < world.visual_range() + 150:
                col = (240, 90, 60) if tx.angry else (60, 220, 190)
                L.light(cam.w2s(tx.pos), cam.px(170), col, 0.55)
        if cam.visible(world.eye, 900):
            L.light(cam.w2s(world.eye), cam.px(700), (200, 200, 255), 1.0)
        for ev in world.events.active:
            if ev.phase(t) == "active" and ev.data.telegraphed_by_rays and cam.visible(ev.pos, ev.data.radius):
                L.light(cam.w2s(ev.pos), cam.px(ev.data.radius), (120, 60, 170), 0.6)

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
