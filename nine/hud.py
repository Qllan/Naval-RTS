"""Интерфейс в море. Экран порта — в port_ui.py, общий стиль и иконки — в gfx/ui.py.

Раскладка: слева сверху — состояние корабля (силуэт с подсистемами, шкалы), по центру —
зона и плотность Пелены, справа сверху — карта, справа снизу — вооружение и энергия,
слева снизу — журнал, по центру снизу — подсказки.
"""

import math

import pygame
from pygame.math import Vector2

from . import config as C
from .entities import RESOURCES
from .gfx import ui
from .gfx.style_tokens import rgb
from .gfx.ship_art import MAST, outline
from .modules import AMMO, SIZE_NAME
from .ship import PIP_MAX, PIP_SYSTEMS, SUBSYSTEMS

HELP_LINES = [
    "W/S — ход вперёд/назад     A/D — руль     Shift — форсаж (тратит энергию)     колесо мыши — зум",
    "ЛКМ / Пробел — группа огня 1 (пушки)     ПКМ — группа 2 (держать на цели: захват ракет; торпеды)",
    "1–4 — активные модули   Z/X/C — энергия в щиты/двигатель/орудия, V — поровну   T — тип снарядов",
    "E (держать) — добыча   L — прожектор   F — порт   M — карта   K — кодекс   H — справка   Esc — пауза",
    "",
    "Пелена гуще к северо-востоку, у Ока Девятки. Там дороже ресурсы и слабее сенсоры.",
    "Электроника в Пелене ест больше энергии: если реактор не тянет — гаснут щиты и радар.",
    "Форсаж в Пелене оставляет налёт филаментов: корабль тяжелеет. Чистка — в порту.",
    "Скаты уходят на глубину — скоро Всплеск. Под Тиходонтом вас не видно, если идти тихо.",
    "Клавиши переназначаются в настройках (Esc → Настройки). ` или F1 — консоль отладки.",
]

SUB_ICON = {"engine": "engine", "rudder": "rudder", "sensors": "sensor", "weapons": "gun"}
PIP_ICON = {"shields": "shield", "engines": "engine", "weapons": "gun"}
PIP_COLOR = {"shields": ui.C_SHIELD, "engines": ui.ACCENT, "weapons": ui.WARN}
P_WARN_DARK = (150, 110, 60)


P_SHIELD_HIT = (110, 190, 255)


def P_mix(a, b, k):
    return tuple(int(x + (y - x) * max(0.0, min(1.0, k))) for x, y in zip(a, b))


def _smear(text, k, seed):
    """Размыть часть букв (амнезия в плотной Пелене)."""
    import random
    rng = random.Random(seed)
    glyphs = "~=·-"
    return "".join(ch if ch == " " or rng.random() > k * 0.7 else rng.choice(glyphs) for ch in text)


def health_color(v):
    return ui.TEXT if v > 0.95 else ui.WARN if v > 0.5 else ui.BAD


def combat_focus(world):
    """What can interrupt the player's next action?

    The HUD shows threats first. This is a display-only classification:
    it never modifies AI, sensor ranges, weapon behaviour or world events.
    """
    p = world.player
    if (p.hp <= p.hull.hp * 0.3 or p.fires > 0 or
            p.water > 0.55 or p.leaks > 0 or p.brownout or
            any(pr.kind == "missile" and pr.target is p and not pr.lost
                for pr in world.projectiles)):
        return "critical"
    radar = world.radar_range()
    if any(p.pos.distance_to(pr.ship.pos) <= min(550, radar)
           for pr in world.pirates):
        return "combat"
    if any(w.overheated for w in p.weapons):
        return "combat"
    if world.density_at(p.pos) >= C.ZONE_DENSE:
        return "hazard"
    return "cruise"


class Hud:
    MINIMAP = 180

    def __init__(self, screen, world):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.minimap_bg = self._build_minimap(world)
        self.show_help = False
        self.help_until = 12.0
        self._ghost = {}           # «призрак» недавнего значения шкалы — видно, сколько сняли
        self._last = {}
        self._popups = []
        self._flash_until = {}
        self._incoming = []
        self.buttons = []          # [(rect, action)] — кликабельные зоны, пересобираются каждый кадр
        self.panels = []           # прямоугольники панелей: клик по ним не стреляет
        self.minimap_rect = None
        self.hints = True
        self.show_minimap = True
        self.show_log = True
        self.keys = None           # Settings — чтобы подсказки показывали назначенные клавиши
        self._fog = None
        self._fog_t = -1.0
        self.focus = "cruise"
        self.visible_alerts = []  # labels actually shown this frame

    # --------------------------------------------------------------------

    def _build_minimap(self, world):
        n = self.MINIMAP
        surf = pygame.Surface((n, n))
        for y in range(n):
            for x in range(n):
                d = world.veil.static_density(x / n * C.WORLD_W, y / n * C.WORLD_H)
                # Dark steel and cold teal, matching the world Veil instead
                # of the obsolete purple minimap. Contrast stays conservative.
                sea, mist = rgb("water_deep"), rgb("veil_mist")
                surf.set_at((x, y), P_mix(sea, mist, min(0.46, d * 0.46)))
        for i in range(0, n, n // 8):
            pygame.draw.line(surf, ui.FAINT, (i, 0), (i, n))
            pygame.draw.line(surf, ui.FAINT, (0, i), (n, i))
        for isl in world.islands:
            pts = []
            for k in range(24):
                a = k / 24 * math.tau
                r = isl.r_at(a)
                pts.append(((isl.pos.x + math.cos(a) * r) / C.WORLD_W * n, (isl.pos.y + math.sin(a) * r) / C.WORLD_H * n))
            pygame.draw.polygon(surf, (78, 84, 80), pts)
            if isl.ruins:
                pygame.draw.circle(surf, (170, 70, 60), (isl.pos.x / C.WORLD_W * n, isl.pos.y / C.WORLD_H * n), 1)
        return surf

    def _ghosted(self, key, frac, dt):
        g = self._ghost.get(key, frac)
        g = frac if frac >= g else max(frac, g - dt * 0.35)
        self._ghost[key] = g
        return g

    # --------------------------------------------------------------------

    def draw(self, world, docked, cam=None, events=(), mouse=None):
        if docked:
            return
        dt = 1 / 60
        self.buttons, self.panels = [], []
        self.mouse = mouse if mouse is not None else pygame.mouse.get_pos()
        self.focus = combat_focus(world)
        self.visible_alerts = []
        self._track_numbers(world, dt)
        self._track_hits(world, events, dt)
        if cam is not None:
            self._edge_markers(world, cam)
        self._damage_direction(world)
        self._status(world, dt)
        self._zone(world)
        self.minimap_rect = None
        if self.show_minimap:
            self._minimap(world)
        self._weapons(world)
        if self.hints:
            # Tutorials and routine orders yield the screen to actual threats.
            if self.focus not in ("combat", "critical"):
                self._goal(world)
            self._hints(world)
        self._toasts(world)
        if self.show_log and self.focus == "cruise":
            self._log(world)
        if self.show_help or world.t < self.help_until:
            self._help()
        self._flashes(dt)

    # --- обратная связь -----------------------------------------------------------

    def _button(self, rect, action):
        """Регистрирует кликабельную зону; возвращает True, если над ней курсор."""
        r = pygame.Rect(rect)
        self.buttons.append((r, action))
        return r.collidepoint(self.mouse)

    def action_at(self, pos):
        for r, action in self.buttons:
            if r.collidepoint(pos):
                return action
        return None

    def over_ui(self, pos):
        return self.action_at(pos) is not None or any(r.collidepoint(pos) for r in self.panels)

    def _track_numbers(self, world, dt):
        """Вспышка при изменении кредитов и груза: «+120» всплывает рядом со значением."""
        cap = world.captain
        cur = {"credits": cap.credits, "cargo": int(world.cargo_used)}
        for key, val in cur.items():
            old = self._last.get(key)
            if old is not None and val != old:
                pos = (120, 184) if key == "credits" else (230, 184)
                self._popups.append([f"{val - old:+d}", pos, 1.2, ui.GOOD if val > old else ui.BAD])
                self._flash_until[key] = 0.6
            self._last[key] = val
        for k in list(self._flash_until):
            self._flash_until[k] -= dt

    def _flashes(self, dt):
        keep = []
        for item in self._popups:
            label, (x, y), life, col = item
            item[2] -= dt
            if item[2] <= 0:
                continue
            k = item[2] / 1.2
            img = ui.Fonts.get(18, True).render(label, True, col)
            img.set_alpha(int(255 * min(1.0, k * 2)))
            self.screen.blit(img, (x, y - (1 - k) * 26))
            keep.append(item)
        self._popups = keep

    def _track_hits(self, world, events, dt):
        """Запоминаем, откуда прилетело, — для индикатора направления урона."""
        p = world.player
        for ev in events:
            if ev[0] == "hit" and ev[5] is p and len(ev) > 7:
                d = ev[7] - p.pos
                if d.length_squared() > 1:
                    self._incoming.append([Vector2(1, 0).angle_to(d), 1.0, ev[2]])
        for item in self._incoming:
            item[1] -= dt
        self._incoming = [i for i in self._incoming if i[1] > 0][-8:]

    def _damage_direction(self, world):
        """Красные дуги вокруг центра экрана — со стороны, откуда бьют."""
        if not self._incoming:
            return
        c = (self.w / 2, self.h / 2)
        r = 86
        for ang, life, layer in self._incoming:
            col = P_SHIELD_HIT if layer == "shield" else ui.BAD
            a = math.radians(-ang)
            rect = pygame.Rect(c[0] - r, c[1] - r, r * 2, r * 2)
            w = max(1, int(5 * life))
            pygame.draw.arc(self.screen, P_mix(ui.FAINT, col, life), rect, a - 0.35, a + 0.35, w)

    def _edge_markers(self, world, cam):
        """Стрелки у края экрана: порт, путевая точка, контакты радара, сигнатуры событий."""
        p = world.player
        marks = [(world.port, ui.ACCENT, "Порт")]
        if getattr(world, "waypoint", None) is not None:
            marks.append((world.waypoint, ui.C_ENERGY, "Точка"))
        radar = world.radar_range()
        for pr in world.pirates:
            if p.pos.distance_to(pr.ship.pos) < radar:
                marks.append((pr.ship.pos, ui.BAD, None))
        for ph in world.phantoms:
            marks.append((ph["pos"], ui.BAD, None))
        margin = 30
        for pos, col, label in marks:
            s = cam.w2s(pos)
            if 0 <= s.x <= self.w and 0 <= s.y <= self.h:
                if label == "Точка":         # путевая точка на экране — ромб над водой
                    pygame.draw.polygon(self.screen, col, [s + Vector2(0, -9), s + Vector2(7, 0), s + Vector2(0, 9),
                                                           s + Vector2(-7, 0)], 2)
                    ui.text(self.screen, f"{int(p.pos.distance_to(pos))} м", s + Vector2(0, 12), col, 14,
                            anchor="midtop")
                continue
            c = Vector2(self.w / 2, self.h / 2)
            d = s - c
            if d.length_squared() < 1:
                continue
            k = min((self.w / 2 - margin) / max(1e-6, abs(d.x)), (self.h / 2 - margin) / max(1e-6, abs(d.y)))
            e = c + d * k
            dirn = d.normalize()
            tri = [e + dirn * 10, e + dirn.rotate(140) * 8, e + dirn.rotate(-140) * 8]
            pygame.draw.polygon(self.screen, col, tri)
            if label:
                dist = int(p.pos.distance_to(pos))
                ui.text(self.screen, f"{label} {dist}", e - dirn * 22, col, 14, anchor="center")

    def _toasts(self, world):
        """Уведомления по центру сверху: последние важные сообщения, плавно гаснут."""
        colors = {"bad": ui.BAD, "good": ui.GOOD, "event": (190, 150, 255), "info": ui.TEXT}
        recent = [m for m in world.log if world.t - m[1] < 4.5 and m[2] != "info"][-2:]
        y = 62
        for text, when, level in recent:
            age = world.t - when
            k = min(1.0, age * 6, (4.5 - age) / 0.8)
            col = colors[level]
            while ui.text_width(text, 20, True) > min(450, self.w - 100) and len(text) > 5:
                text = text[:-2] + "…"
            w = ui.text_width(text, 20, True) + 36
            r = pygame.Rect(0, 0, w, 28)
            r.midtop = (self.w // 2, y - int((1 - min(1.0, age * 6)) * 12))
            bg = pygame.Surface(r.size, pygame.SRCALPHA)
            bg.fill((5, 9, 14, int(210 * k)))
            self.screen.blit(bg, r)
            pygame.draw.rect(self.screen, P_mix(ui.FAINT, col, k), r, 1)
            pygame.draw.line(self.screen, P_mix(ui.FAINT, col, k), r.topleft, r.bottomleft, 3)
            img = ui.Fonts.get(20, True).render(text, True, col)
            img.set_alpha(int(255 * k))
            self.screen.blit(img, img.get_rect(center=r.center))
            y += 32

    # --- состояние корабля -------------------------------------------------------

    def _status(self, world, dt):
        s, p, cap = self.screen, world.player, world.captain
        box = ui.panel(self.screen, (12, 12, 330, 168), p.hull.name,
                       ui.BAD if self.focus == "critical" else ui.WARN if world.in_capsule
                       else ui.ACCENT)
        self.panels.append(box.union(pygame.Rect(12, box.bottom, 330, 34)))
        self._silhouette(world, pygame.Rect(box.x + 12, box.y + 28, 62, 107))

        x, y, w = box.x + 88, box.y + 32, 150
        rows = [("hull", "Корпус", p.hp, p.hull.hp, ui.C_HULL)]
        if p.armor_max:
            rows.append(("armor", "Броня", p.armor, p.armor_max, ui.C_ARMOR))
        if p.shield_max:
            rows.append(("shield", "Щит", p.shield, p.shield_max, ui.C_SHIELD))
        for key, label, v, vmax, col in rows:
            frac = v / vmax if vmax else 0
            # Actual words are as important as tint in a glanceable HUD.
            short = {"hull": "КОРПУС", "armor": "БРОНЯ", "shield": "ЩИТ"}[key]
            ui.text(s, short, (x + 2, y - 3), ui.DIM, 13, True)
            ui.bar(s, (x + 70, y + 1, 96, 8), frac, col,
                   segments=10, ghost=self._ghosted(key, frac, dt))
            ui.text(s, f"{int(max(0, v))}", (box.right - 12, y - 2), ui.TEXT, 16, anchor="topright")
            y += 18
        if p.cap_max:
            bal = p.power_balance(world.density_at(p.pos))
            col = ui.BAD if p.brownout else ui.C_ENERGY
            ui.text(s, "ЭНЕРГИЯ", (x + 2, y - 3), ui.DIM, 13, True)
            ui.bar(s, (x + 70, y + 2, 96, 6), p.capacitor / p.cap_max, col)
            ui.text(s, f"{bal:+.1f}/с", (box.right - 12, y - 2), ui.BAD if bal < 0 else ui.DIM, 16,
                    anchor="topright")
            y += 18
        if p.fouling > 0.01:
            ui.bar(s, (x + 18, y + 2, w, 4), p.fouling, ui.C_FOUL)
            ui.text(s, f"налёт {int(p.fouling * 100)}%", (box.right - 12, y - 3), ui.C_FOUL, 14, anchor="topright")

        # скорость: дуга + число
        sc = Vector2(x + 30, box.bottom - 36)
        frac = min(1.0, p.speed / max(1.0, p.max_speed()))
        rect = pygame.Rect(0, 0, 50, 50)
        rect.center = sc
        pygame.draw.arc(s, ui.FAINT, rect, math.radians(-30), math.radians(210), 3)
        pygame.draw.arc(s, ui.ACCENT if not p.boosting else ui.WARN, rect,
                        math.radians(210 - 240 * frac), math.radians(210), 3)
        ui.text(s, int(p.speed), sc + Vector2(0, -2), ui.TEXT, 20, True, anchor="center")
        ui.text(s, "скор.", sc + Vector2(0, 12), ui.DIM, 13, anchor="center")
        ui.text(s, f"макс {int(p.max_speed())}", (x + 64, box.bottom - 45), ui.DIM, 15)
        # Mass is a fitting decision, not a permanent combat readout.
        if p.list_angle > 1:
            ui.text(s, f"КРЕН {p.list_angle:.0f}°", (x + 64, box.bottom - 25),
                    ui.WARN, 15)
        elif p.boosting:
            ui.text(s, "ФОРСАЖ", (x + 64, box.bottom - 25), ui.WARN, 15)

        # кредиты и трюм
        y = box.bottom + 6
        ui.panel(self.screen, (12, y, 330, 28), None, ui.LINE)
        ui.icon(s, "credits", (28, y + 14), 14, ui.C_ENERGY)
        ui.text(s, f"{cap.credits} КК", (42, y + 7), ui.C_ENERGY if self._flash_until.get("credits", 0) > 0
                else ui.TEXT, 18, bold=self._flash_until.get("credits", 0) > 0)
        ui.icon(s, "cargo", (150, y + 14), 14, ui.TEXT)
        full = world.cargo_used >= world.cargo_capacity
        ui.text(s, f"{int(world.cargo_used)}/{world.cargo_capacity}", (164, y + 7), ui.WARN if full else ui.TEXT, 18)
        ui.text(s, f"~{world.cargo_value()} КК", (330, y + 7), ui.DIM, 16, anchor="topright")

        # Two short, ranked alerts instead of an unbounded wall of chips.
        # The classifier shares the same facts as gameplay; display-only.
        y += 34
        chips = []
        if p.fires:
            chips.append((0, f"ПОЖАР ×{p.fires}", ui.BAD))
        if p.leaks or p.water > 0.02:
            chips.append((0, f"ТЕЧЬ · ВОДА {int(p.water * 100)}%", ui.BAD if p.water > 0.6 else ui.WARN))
        if p.hp < p.hull.hp * 0.3 and not world.in_capsule:
            chips.append((0, "КОРПУС ПОВРЕЖДЁН", ui.BAD))
        if p.brownout:
            chips.append((0, "НЕТ ЭНЕРГИИ", ui.BAD))
        if any(w.defn.ammo and w.ammo == 0 for w in p.weapons):
            chips.append((1, "НЕТ БОЕЗАПАСА", ui.WARN))
        if p.cap_max and p.power_balance(0.8) < 0 and world.density_at(p.pos) < 0.6:
            chips.append((1, "В ПЕЛЕНЕ НЕ ХВАТИТ ЭНЕРГИИ", ui.WARN))
        if p.mass_factor() < 0.8:
            chips.append((2, f"ПЕРЕГРУЗ −{int((1 - p.mass_factor()) * 100)}%", ui.WARN))
        if cap.debt:
            chips.append((2, f"ДОЛГ {cap.debt} КК", ui.BAD))
        if cap.trauma:
            chips.append((2, "ТРАВМА", ui.WARN))
        if world.spotlight and world.daylight() < 0.5:
            chips.append((2, "ПРОЖЕКТОР ВЫДАЁТ", ui.WARN))
        chips.sort(key=lambda item: item[0])
        for priority, label, col in chips[:2]:
            while ui.text_width(label, 15, True) > 304 and len(label) > 4:
                label = label[:-2] + "…"
            ui.chip(s, label, (12, y), col, 15)
            y += 18

    def _silhouette(self, world, rect):
        """Силуэт корабля носом вверх: заливка по корпусу, вода снизу, подсистемы и оружие точками."""
        s, p = self.screen, world.player
        pts = outline(p.hull.key)
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        area = pygame.Rect(rect.x, rect.y, rect.w, rect.h - 16)
        k = min(area.h / (max(xs) - min(xs)), area.w / (max(ys) - min(ys))) * 0.92
        cx = (max(xs) + min(xs)) / 2

        def m(x, y):
            return (area.centerx + y * k, area.centery - (x - cx) * k)

        poly = [m(x, y) for x, y in pts]
        hp = max(0.0, p.hp / p.hull.hp)
        fill = ui.C_HULL if hp < 0.3 else P_WARN_DARK if hp < 0.6 else (56, 76, 86)
        pygame.draw.polygon(s, fill, poly)
        if p.water > 0.02:
            ys_poly = [q[1] for q in poly]
            top, bottom = min(ys_poly), max(ys_poly)
            level = bottom - (bottom - top) * p.water
            clip = s.get_clip()
            s.set_clip(pygame.Rect(area.x - 10, level, area.w + 20, bottom - level + 2))
            pygame.draw.polygon(s, (40, 90, 160), poly)
            s.set_clip(clip)
        pygame.draw.polygon(s, ui.C_ARMOR if p.armor > 0 else ui.DIM, poly, 2 if p.armor > 0 else 1)
        for w in p.weapons:
            pygame.draw.circle(s, ui.BAD if w.overheated else ui.TEXT, m(*w.slot.pos), 3)
        mx, my = MAST.get(p.hull.key, (0, 0))
        pygame.draw.circle(s, health_color(p.subsystems["sensors"]), m(mx, my), 3)
        stern = min(xs)
        pygame.draw.circle(s, health_color(p.subsystems["engine"]), m(stern + 2.5, 0), 3)
        for i in range(p.fires):
            ui.icon(s, "fire", (area.centerx - 10 + i * 10, area.centery), 10, ui.BAD)
        # подсистемы значками под силуэтом
        for i, key in enumerate(SUBSYSTEMS):
            ui.icon(s, SUB_ICON[key], (rect.x + 7 + i * 16, rect.bottom - 4), 11, health_color(p.subsystems[key]))

    # --- зона ----------------------------------------------------------------------

    def _zone(self, world):
        """Small navigation context; detail only when Veil is consequential."""
        s, p = self.screen, world.player
        d = world.density_at(p.pos)
        zone = world.veil.zone(p.pos, d)
        dense = d >= C.ZONE_DENSE
        mist = d >= C.ZONE_MIST
        zc = ui.BAD if dense else ui.WARN if mist else ui.ACCENT
        cx = self.w // 2
        bw = 194
        band_w = min(326, max(230, self.w - 696))
        band = ui.panel(s, (cx - band_w // 2, 6, band_w, 49),
                        None, accent=zc)
        self.panels.append(band)
        ui.text(s, zone.upper(), (band.x + 13, 12), zc, 20, True)
        ui.text(s, f"{int(d * 100)}%", (band.right - 13, 13), ui.TEXT, 17,
                True, anchor="topright")
        bw = min(bw, band.w - 50)
        r = pygame.Rect(cx - bw // 2, 39, bw, 4)
        ui.bar(s, r, d, zc)
        for th in (C.ZONE_MIST, C.ZONE_DENSE):
            line_x = round(r.x + bw * th)
            pygame.draw.line(s, ui.DIM, (line_x, r.y - 2),
                             (line_x, r.bottom + 2))
        # Radar failure is a hazard, not permanent text in safe waters.
        radar = world.radar_range()
        if radar <= 0:
            ui.chip(s, "РАДАР ОТКЛ.", (cx + 171, 8), ui.BAD, 14)
        elif dense:
            ui.text(s, f"РАДАР {int(radar)}", (cx + 171, 14), ui.WARN, 14)
        # Time remains in a small separate navigator label.
        ui.text(s, world.clock(), (cx + 170, 35), ui.DIM, 15)

    # --- карта -------------------------------------------------------------------

    def _minimap(self, world):
        s = self.screen
        n = self.MINIMAP
        box = ui.panel(self.screen, (self.w - n - 24, 12, n + 12, n + 34), "Карта · M")
        self.panels.append(box)
        self.minimap_rect = box
        x0, y0 = box.x + 6, box.y + 26
        s.blit(self.minimap_bg, (x0, y0))
        if self._fog is None or world.t - self._fog_t > 0.5 or world.t < self._fog_t:
            from .screens import fog_surface
            self._fog = fog_surface(world.memory, n)
            self._fog_t = world.t
        s.blit(self._fog, (x0, y0))
        if world.veil.in_dead_zone(world.player.pos):
            veil = pygame.Surface((n, n), pygame.SRCALPHA)
            veil.fill((*rgb("ui_bg"), 218))
            s.blit(veil, (x0, y0))
            ui.text(s, "НЕТ СВЯЗИ", (x0 + n // 2, y0 + n // 2), ui.BAD, 24, True, anchor="center")
            return

        def m(pos):
            return (x0 + pos[0] / C.WORLD_W * n, y0 + pos[1] / C.WORLD_H * n)

        for mk in world.marks.values():
            if mk["kind"] in ("ruins", "wreck"):
                col = (200, 110, 90) if mk["kind"] == "ruins" else ui.WARN
                pygame.draw.circle(s, tuple(int(c * (0.3 + 0.7 * mk["clarity"])) for c in col), m(mk["pos"]), 2)
        for pi in world.pirates:
            if world.on_radar(pi.ship.pos) or world.perceives(pi.ship.pos):
                pygame.draw.circle(s, ui.BAD, m(pi.ship.pos), 2)
        for ph in world.phantoms:
            pygame.draw.circle(s, ui.BAD, m(ph["pos"]), 2)
        for ev in world.events.active:
            if ev.phase(world.t) == "active" and (ev.covers(world.player.pos) or world.perceives(ev.pos)):
                pygame.draw.circle(s, ev.data.color, m(ev.pos), max(3, int(ev.data.radius / C.WORLD_W * n)), 1)
        if world.waypoint is not None:
            wp = Vector2(m(world.waypoint))
            pygame.draw.line(s, (120, 110, 70), m(world.player.pos), wp)
            pygame.draw.polygon(s, (240, 220, 120), [wp + Vector2(0, -4), wp + Vector2(4, 0), wp + Vector2(0, 4),
                                                     wp + Vector2(-4, 0)])
        pygame.draw.circle(s, ui.ACCENT, m(world.port), 4, 1)
        pygame.draw.circle(s, (240, 240, 250), m(world.eye), 3)
        pygame.draw.circle(s, rgb("veil_fringe"), m(world.eye),
                           int(C.EYE_WALL_R / C.WORLD_W * n), 1)
        ui.text(s, "Око", (m(world.eye)[0] - 8, m(world.eye)[1] + 6), ui.DIM, 14, anchor="topright")
        ui.text(s, "Порт", (m(world.port)[0] + 7, m(world.port)[1] - 6), ui.DIM, 14)
        p = world.player
        pp = Vector2(m(p.pos))
        pygame.draw.circle(s, (40, 110, 100), pp, max(2, int(world.radar_range() / C.WORLD_W * n)), 1)
        tri = [pp + Vector2(5, 0).rotate(p.angle), pp + Vector2(-3, 3).rotate(p.angle),
               pp + Vector2(-3, -3).rotate(p.angle)]
        pygame.draw.polygon(s, (255, 255, 255), tri)
        ui.text(s, "С", (x0 + n - 8, y0 + 4), ui.DIM, 14, True)

    def _goal(self, world):
        """Трекер цели обучения под картой: название и подсказка."""
        g = world.goal
        if g is None:
            return
        from .world import GOALS
        i, title, hint = g
        w = self.MINIMAP + 12
        x = self.w - w - 12
        y = 12 + (self.MINIMAP + 34 + 8 if self.show_minimap else 0)
        lines = ui.wrap(hint, w - 20, 15)
        box = ui.panel(self.screen, (x, y, w, 46 + 16 * len(lines)), f"Цель {i + 1}/{len(GOALS)}", ui.C_ENERGY)
        self.panels.append(box)
        ui.text(self.screen, title, (x + 10, y + 26), ui.TEXT, 17, True)
        for j, line in enumerate(lines):
            ui.text(self.screen, line, (x + 10, y + 44 + j * 16), ui.DIM, 15)

    # --- вооружение ------------------------------------------------------------------

    def _weapons(self, world):
        s, p = self.screen, world.player
        if world.in_capsule:
            return
        actives = [u for u in p.utilities if u.defn.active]
        has_guns = any(m.defn.kind == "gun" and m.defn.dmg_type == "kinetic" for m in p.weapons)
        rows = len(p.weapons) + len(actives)
        h = 37 + 30 + (22 if has_guns else 0) + rows * 24 + 8
        ready_count = sum(w.reload <= 0 and w.has_ammo and not w.overheated
                          for w in p.weapons)
        box = ui.panel(self.screen, (self.w - 344, self.h - 12 - h, 332, h), "АРСЕНАЛ")
        col = ui.GOOD if ready_count == len(p.weapons) else ui.WARN
        ui.text(s, f"{ready_count}/{len(p.weapons)} ГОТОВО",
                (box.right - 13, box.y + 8), col, 15, True,
                anchor="topright")
        self.panels.append(box)
        y = box.y + 33

        # энергия по системам
        x = box.x + 12
        for key, sys_ in zip("ZXC", PIP_SYSTEMS):
            col = PIP_COLOR[sys_]
            ui.chip(s, key, (x, y + 2), ui.DIM, 14)
            ui.icon(s, PIP_ICON[sys_], (x + 26, y + 9), 12, col)
            zone = self._button((x - 2, y, 102, 18), ("pip", sys_))
            for i in range(PIP_MAX):
                on = i < p.pips[sys_]
                pygame.draw.rect(s, col if on else ui.FAINT, (x + 36 + i * 11, y + 3, 8, 12))
            if zone:
                pygame.draw.rect(s, col, (x - 2, y, 102, 18), 1)
            x += 106
        y += 26
        pygame.draw.line(s, ui.LINE, (box.x + 10, y), (box.right - 10, y))
        y += 6
        if has_guns:
            if self._button((box.x + 8, y - 2, box.w - 16, 22), ("ammo",)):
                pygame.draw.rect(s, ui.LINE, (box.x + 8, y - 2, box.w - 16, 22), 1)
            ammo = world.ammo_type
            ui.chip(s, "T", (box.x + 12, y + 1), ui.DIM, 14)
            col = {"std": ui.TEXT, "ap": (210, 225, 255), "he": ui.WARN}[ammo]
            stock = "" if ammo == "std" else f"  {world.captain.ammo_stock[ammo]}"
            ui.text(s, f"{AMMO[ammo].name}{stock}", (box.x + 36, y), col, 17)
            others = "   ".join(f"{AMMO[k].short} {v}" for k, v in world.captain.ammo_stock.items())
            ui.text(s, others, (box.right - 12, y + 1), ui.DIM, 15, anchor="topright")
            y += 24

        for m in p.weapons:
            d = m.defn
            ready = m.reload <= 0 and m.has_ammo and not m.overheated
            col = ui.TEXT if ready else ui.DIM
            grp = {1: "Л", 2: "П", 0: "–"}[m.group]
            ui.chip(s, grp, (box.x + 12, y + 2), ui.ACCENT if m.group else ui.FAINT, 14)
            ui.icon(s, ui.module_icon_kind(d), (box.x + 38, y + 9), 13, col)
            label = d.name.split("«")[0].strip() if "«" in d.name else d.name
            ui.text(s, f"{label} {SIZE_NAME[d.size]}", (box.x + 50, y + 1), col, 16)
            bx = box.x + 190
            if m.overheated:
                ui.bar(s, (bx, y + 4, 70, 6), m.heat / 100, ui.BAD)
                ui.text(s, "ПЕРЕГРЕВ", (box.right - 12, y + 1), ui.BAD, 15, True, anchor="topright")
            else:
                frac = 1.0 - (m.reload / (d.reload * p.reload_mult()) if d.reload else 0)
                ui.bar(s, (bx, y + 4, 70, 5), frac, ui.ACCENT if ready else ui.DIM)
                if m.heat > 1:
                    ui.bar(s, (bx, y + 11, 70, 2), m.heat / 100, ui.WARN if m.heat > 60 else (120, 110, 80))
                info = f"{m.ammo}/{d.ammo}" if d.ammo else ("ГОТОВО" if ready else "ЗАРЯД")
                if d.ammo and m.ammo == 0:
                    info = "НЕТ БК"
                elif d.kind == "missile" and m.lock > 0:
                    info = f"ЗАХВАТ {int(m.lock * 100)}%"
                info_col = ui.BAD if d.ammo and m.ammo == 0 else ui.GOOD if ready else ui.DIM
                ui.text(s, info, (box.right - 12, y + 1), info_col, 15,
                        anchor="topright")
            y += 24
        for n, u in enumerate(actives, 1):
            if self._button((box.x + 8, y, box.w - 16, 21), ("utility", n - 1)):
                pygame.draw.rect(s, ui.LINE, (box.x + 8, y, box.w - 16, 21), 1)
            if u.active_time > 0:
                state, col = f"{u.active_time:.0f} с", ui.ACCENT
            elif u.cooldown > 0:
                state, col = f"{u.cooldown:.0f} с", ui.DIM
            elif u.defn.charges and u.charges == 0:
                state, col = "пусто", ui.WARN
            else:
                state, col = "готов", ui.TEXT
            ui.chip(s, str(n), (box.x + 12, y + 2), col, 14, fill=(20, 60, 60) if u.active_time > 0 else None)
            ui.icon(s, "utility", (box.x + 38, y + 9), 13, col)
            charges = f" ×{u.charges}" if u.defn.charges else ""
            ui.text(s, f"{u.defn.name}{charges}", (box.x + 50, y + 1), col, 16)
            if u.cooldown > 0 and u.active_time <= 0:
                ui.bar(s, (box.x + 190, y + 6, 70, 3), 1 - u.cooldown / u.defn.cooldown, ui.DIM)
            ui.text(s, state, (box.right - 12, y + 1), col, 15, anchor="topright")
            y += 24

    # --- подсказки и журнал ---------------------------------------------------------

    def _hints(self, world):
        s, p, t = self.screen, world.player, world.t
        hints = []
        if world.in_capsule:
            hints.append(("Вы в капсуле. Идите к порту (юго-запад) и нажмите F.", ui.WARN))
        if p.hp < p.hull.hp * 0.3 and not world.in_capsule:
            hints.append(("КОРПУС КРИТИЧЕСКИ ПОВРЕЖДЁН", ui.BAD))
        if p.fires:
            hints.append((f"ПОЖАР НА КОРАБЛЕ ×{p.fires}", ui.BAD))
        if p.water > 0.55:
            hints.append(("ОПАСНОЕ ЗАТОПЛЕНИЕ", ui.BAD))
        if any(w.overheated for w in p.weapons):
            hints.append(("ОРУДИЕ ПЕРЕГРЕТО", ui.WARN))
        if world.can_dock():
            hints.append(("[F] Пришвартоваться", ui.ACCENT))
        if world.sheltering_tihodont():
            if world.player_loud():
                hints.append(("Шум двигателя! Тиходонт беспокоится", ui.BAD))
            else:
                hints.append(("Под Тиходонтом: вы скрыты от сенсоров", ui.ACCENT))
        if world.emp_timer > 0:
            hints.append((f"ЭМ-вспышка: {world.emp_timer:.0f} c", ui.BAD))
        if world.events.modifier("shield_drain", p.pos, t) > 0.5:
            hints.append(("Всплеск Пелены выжигает щиты", ui.BAD))
        if world.events.modifier("accuracy", p.pos, t) > 0.2:
            hints.append(("Штиль: точность выше, сенсоры чище", ui.ACCENT))
        if p.brownout:
            hints.append(("Энергия на нуле! Щиты гаснут, радар слепнет", ui.BAD))
        if p.utility_active("bioscreen"):
            hints.append(("Био-экран: вас не видят", ui.ACCENT))
        if world.in_smoke(p.pos):
            hints.append(("В дымовой завесе", ui.ACCENT))
        if any(pr.kind == "missile" and pr.target is p and not pr.lost for pr in world.projectiles):
            hints.append(("Ракета на подлёте!", ui.BAD))
        if p.fouling > 0.4:
            hints.append(("Корпус обрастает филаментами — сбавьте ход", ui.WARN))
        node = min(world.nodes, key=lambda n: n.pos.distance_squared_to(p.pos), default=None)
        if node and node.pos.distance_to(p.pos) < 75 and not world.in_capsule:
            full = world.cargo_used >= world.cargo_capacity
            hints.append(("Трюм полон" if full else f"[E] Добыча: {RESOURCES[node.kind].name}",
                          ui.WARN if full else ui.ACCENT))
        # Only two highest-priority actionable signals may occupy the sea.
        # Keep stable order among equal priorities (missiles and brownout
        # beat routine mining and repair notes).
        def priority(item):
            label, color = item
            if label.startswith("Ракета на подлёте"):
                return -3
            if label.startswith("Энергия на нуле"):
                return -2
            if label.startswith(("КОРПУС КРИТИЧЕСКИ", "ОПАСНОЕ ЗАТОПЛЕНИЕ",
                                 "ПОЖАР НА КОРАБЛЕ")):
                return -1
            return 0 if color == ui.BAD else 1 if color == ui.WARN else 2

        hints.sort(key=priority)
        chosen = hints[:2]
        self.visible_alerts = [text for text, _ in chosen]
        y = self.h - 78 - 25 * (len(chosen) - 1)
        for label, col in chosen:
            # Keep the centre-bottom lane clear of the right arsenal and
            # the left status/log at 960px and other medium resolutions.
            left_edge, right_edge = 345, self.w - 356
            max_label_width = min(470, max(160, right_edge - left_edge - 36))
            while ui.text_width(label, 18) > max_label_width and len(label) > 5:
                label = label[:-2] + "…"
            width = ui.text_width(label, 18) + 24
            rect = pygame.Rect(0, 0, width, max(23, ui.Fonts.get(18, True).get_height() + 5))
            rect.midtop = ((left_edge + right_edge) // 2, y)
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            bg.fill((*ui.PANEL_RGB, 224))
            s.blit(bg, rect)
            pygame.draw.line(s, col, rect.topleft, rect.bottomleft, 3)
            ui.text(s, label, rect.center, col, 18, True, anchor="center")
            y += 25

    def _log(self, world):
        """At sea, keep only the newest two routine entries.

        During threats the journal yields entirely to the action layer.
        Full history remains available elsewhere; data is not erased.
        """
        y = self.h - 29
        blur = max(0.0, (world.density_at(world.player.pos) - 0.6) / 0.4)
        colors = {"bad": ui.BAD, "good": ui.GOOD,
                  "event": rgb("veil_fringe"), "info": ui.TEXT}
        shown = 0
        for msg, when, level in reversed(world.log):
            age = world.t - when
            if age > 10:
                continue
            if blur > 0:
                msg = _smear(msg, blur * min(1.0, age / 4),
                             int(when * 100))
            while ui.text_width(msg, 16) > min(395, self.w * 0.34) and len(msg) > 5:
                msg = msg[:-2] + "…"
            k = max(0.35, 1.0 - age / 10)
            ui.text(self.screen, "›", (14, y),
                    tuple(int(c * k) for c in ui.ACCENT), 16, True)
            ui.text(self.screen, msg, (26, y),
                    tuple(int(c * k) for c in colors[level]), 16)
            y -= 19
            shown += 1
            if shown >= 2:
                break

    def _help(self):
        w = 780
        rect = ui.panel(self.screen, ((self.w - w) // 2, 72, w, 36 + 20 * len(HELP_LINES)), "Управление  ·  H — скрыть")
        for i, line in enumerate(HELP_LINES):
            ui.text(self.screen, line, (rect.x + 16, rect.y + 28 + i * 20), ui.TEXT if i < 4 else ui.DIM, 16)

