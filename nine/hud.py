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
from .gfx.ship_art import MAST, outline
from .modules import AMMO, SIZE_NAME
from .ship import PIP_MAX, PIP_SYSTEMS, SUBSYSTEMS

HELP_LINES = [
    "W/S — ход вперёд/назад     A/D — руль     Shift — форсаж (тратит энергию)     колесо мыши — зум",
    "ЛКМ / Пробел — группа огня 1 (пушки)     ПКМ — группа 2 (держать на цели: захват ракет; торпеды)",
    "1–4 — активные модули   Z/X/C — энергия в щиты/двигатель/орудия, V — поровну   T — тип снарядов",
    "E (держать) — добыча     F — порт     H — справка     Esc — выход",
    "",
    "Пелена гуще к северо-востоку, у Ока Девятки. Там дороже ресурсы и слабее сенсоры.",
    "Электроника в Пелене ест больше энергии: если реактор не тянет — гаснут щиты и радар.",
    "Форсаж в Пелене оставляет налёт филаментов: корабль тяжелеет. Чистка — в порту.",
    "Скаты уходят на глубину — скоро Всплеск. Под Тиходонтом вас не видно, если идти тихо.",
]

SUB_ICON = {"engine": "engine", "rudder": "rudder", "sensors": "sensor", "weapons": "gun"}
PIP_ICON = {"shields": "shield", "engines": "engine", "weapons": "gun"}
PIP_COLOR = {"shields": ui.C_SHIELD, "engines": ui.ACCENT, "weapons": ui.WARN}
P_WARN_DARK = (150, 110, 60)


def health_color(v):
    return ui.TEXT if v > 0.95 else ui.WARN if v > 0.5 else ui.BAD


class Hud:
    MINIMAP = 180

    def __init__(self, screen, world):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.minimap_bg = self._build_minimap(world)
        self.show_help = False
        self.help_until = 12.0
        self._ghost = {}           # «призрак» недавнего значения шкалы — видно, сколько сняли

    # --------------------------------------------------------------------

    def _build_minimap(self, world):
        n = self.MINIMAP
        surf = pygame.Surface((n, n))
        for y in range(n):
            for x in range(n):
                d = world.veil.static_density(x / n * C.WORLD_W, y / n * C.WORLD_H)
                surf.set_at((x, y), (int(6 + 70 * d), int(12 + 14 * d), int(20 + 90 * d)))
        for i in range(0, n, n // 8):
            pygame.draw.line(surf, (22, 34, 44), (i, 0), (i, n))
            pygame.draw.line(surf, (22, 34, 44), (0, i), (n, i))
        return surf

    def _ghosted(self, key, frac, dt):
        g = self._ghost.get(key, frac)
        g = frac if frac >= g else max(frac, g - dt * 0.35)
        self._ghost[key] = g
        return g

    # --------------------------------------------------------------------

    def draw(self, world, docked):
        if docked:
            return
        dt = 1 / 60
        self._status(world, dt)
        self._zone(world)
        self._minimap(world)
        self._weapons(world)
        self._hints(world)
        self._log(world)
        if self.show_help or world.t < self.help_until:
            self._help()

    # --- состояние корабля -------------------------------------------------------

    def _status(self, world, dt):
        s, p, cap = self.screen, world.player, world.captain
        box = ui.panel(self.screen, (12, 12, 330, 188), p.hull.name, ui.WARN if world.in_capsule else ui.ACCENT)
        self._silhouette(world, pygame.Rect(box.x + 12, box.y + 28, 62, 120))

        x, y, w = box.x + 88, box.y + 32, 150
        rows = [("hull", "Корпус", p.hp, p.hull.hp, ui.C_HULL)]
        if p.armor_max:
            rows.append(("armor", "Броня", p.armor, p.armor_max, ui.C_ARMOR))
        if p.shield_max:
            rows.append(("shield", "Щит", p.shield, p.shield_max, ui.C_SHIELD))
        for key, label, v, vmax, col in rows:
            frac = v / vmax if vmax else 0
            ui.icon(s, key, (x + 6, y + 5), 12, col)
            ui.bar(s, (x + 18, y + 1, w, 8), frac, col, segments=10, ghost=self._ghosted(key, frac, dt))
            ui.text(s, f"{int(max(0, v))}", (box.right - 12, y - 2), ui.TEXT, 16, anchor="topright")
            y += 18
        if p.cap_max:
            bal = p.power_balance(world.density_at(p.pos))
            col = ui.BAD if p.brownout else ui.C_ENERGY
            ui.icon(s, "reactor", (x + 6, y + 5), 12, col)
            ui.bar(s, (x + 18, y + 2, w, 6), p.capacitor / p.cap_max, col)
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
        ui.text(s, f"макс {int(p.max_speed())}", (x + 64, box.bottom - 56), ui.DIM, 15)
        ui.text(s, f"масса {int(p.mass)}", (x + 64, box.bottom - 40), ui.DIM, 15)
        if p.list_angle > 0.5:
            ui.text(s, f"крен {p.list_angle:.0f}°", (x + 64, box.bottom - 24), ui.WARN, 15)

        # кредиты и трюм
        y = box.bottom + 6
        ui.panel(self.screen, (12, y, 330, 28), None, ui.LINE)
        ui.icon(s, "credits", (28, y + 14), 14, ui.C_ENERGY)
        ui.text(s, f"{cap.credits} КК", (42, y + 7), ui.TEXT, 18)
        ui.icon(s, "cargo", (150, y + 14), 14, ui.TEXT)
        full = world.cargo_used >= world.cargo_capacity
        ui.text(s, f"{int(world.cargo_used)}/{world.cargo_capacity}", (164, y + 7), ui.WARN if full else ui.TEXT, 18)
        ui.text(s, f"~{world.cargo_value()} КК", (330, y + 7), ui.DIM, 16, anchor="topright")

        y += 34
        chips = []
        if p.fires:
            chips.append((f"ПОЖАР ×{p.fires}", ui.BAD))
        if p.leaks or p.water > 0.02:
            chips.append((f"ТЕЧЬ ×{p.leaks} · вода {int(p.water * 100)}%", ui.BAD if p.water > 0.6 else ui.WARN))
        if cap.debt:
            chips.append((f"ДОЛГ {cap.debt} КК", ui.BAD))
        if cap.trauma:
            chips.append(("ТРАВМА", ui.WARN))
        x = 12
        for label, col in chips:
            r = ui.chip(s, label, (x, y), col, 15)
            x = r.right + 6

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
        s, p = self.screen, world.player
        d = world.density_at(p.pos)
        zone = world.veil.zone(p.pos, d)
        zc = ui.ACCENT if d < C.ZONE_MIST else ui.WARN if d < C.ZONE_DENSE else ui.BAD
        cx = self.w // 2
        ui.text(s, zone.upper(), (cx, 12), zc, 26, True, anchor="midtop")
        bw = 240
        r = pygame.Rect(cx - bw // 2, 40, bw, 5)
        ui.bar(s, r, d, zc)
        for th in (C.ZONE_MIST, C.ZONE_DENSE):
            x = r.x + bw * th
            pygame.draw.line(s, ui.DIM, (x, r.y - 3), (x, r.bottom + 2), 1)
        radar = world.radar_range()
        radar_s = "РАДАР ОТКЛ." if radar <= 0 else f"радар {int(radar)}"
        ui.text(s, f"Пелена {int(d * 100)}%  ·  {radar_s}  ·  обзор {int(world.visual_range())}", (cx, 50),
                ui.BAD if radar <= 0 else ui.DIM, 15, anchor="midtop")

    # --- карта -------------------------------------------------------------------

    def _minimap(self, world):
        s = self.screen
        n = self.MINIMAP
        box = ui.panel(self.screen, (self.w - n - 24, 12, n + 12, n + 34), "Карта")
        x0, y0 = box.x + 6, box.y + 26
        s.blit(self.minimap_bg, (x0, y0))
        if world.veil.in_dead_zone(world.player.pos):
            veil = pygame.Surface((n, n), pygame.SRCALPHA)
            veil.fill((10, 4, 16, 200))
            s.blit(veil, (x0, y0))
            ui.text(s, "НЕТ СВЯЗИ", (x0 + n // 2, y0 + n // 2), ui.BAD, 24, True, anchor="center")
            return

        def m(pos):
            return (x0 + pos[0] / C.WORLD_W * n, y0 + pos[1] / C.WORLD_H * n)

        pygame.draw.circle(s, ui.ACCENT, m(world.port), 4, 1)
        pygame.draw.circle(s, (240, 240, 250), m(world.eye), 3)
        pygame.draw.circle(s, (140, 90, 190), m(world.eye), int(C.EYE_WALL_R / C.WORLD_W * n), 1)
        ui.text(s, "Око", (m(world.eye)[0] - 8, m(world.eye)[1] + 6), ui.DIM, 14, anchor="topright")
        ui.text(s, "Порт", (m(world.port)[0] + 7, m(world.port)[1] - 6), ui.DIM, 14)
        p = world.player
        pp = Vector2(m(p.pos))
        pygame.draw.circle(s, (40, 110, 100), pp, max(2, int(world.radar_range() / C.WORLD_W * n)), 1)
        tri = [pp + Vector2(5, 0).rotate(p.angle), pp + Vector2(-3, 3).rotate(p.angle),
               pp + Vector2(-3, -3).rotate(p.angle)]
        pygame.draw.polygon(s, (255, 255, 255), tri)
        ui.text(s, "С", (x0 + n - 8, y0 + 4), ui.DIM, 14, True)

    # --- вооружение ------------------------------------------------------------------

    def _weapons(self, world):
        s, p = self.screen, world.player
        if world.in_capsule:
            return
        actives = [u for u in p.utilities if u.defn.active]
        has_guns = any(m.defn.kind == "gun" and m.defn.dmg_type == "kinetic" for m in p.weapons)
        rows = len(p.weapons) + len(actives)
        h = 30 + 30 + (22 if has_guns else 0) + rows * 22 + 8
        box = ui.panel(self.screen, (self.w - 344, self.h - 12 - h, 332, h), "Вооружение")
        y = box.y + 28

        # энергия по системам
        x = box.x + 12
        for key, sys_ in zip("ZXC", PIP_SYSTEMS):
            col = PIP_COLOR[sys_]
            ui.chip(s, key, (x, y + 2), ui.DIM, 14)
            ui.icon(s, PIP_ICON[sys_], (x + 26, y + 9), 12, col)
            for i in range(PIP_MAX):
                on = i < p.pips[sys_]
                pygame.draw.rect(s, col if on else ui.FAINT, (x + 36 + i * 11, y + 3, 8, 12))
            x += 106
        y += 26
        pygame.draw.line(s, ui.LINE, (box.x + 10, y), (box.right - 10, y))
        y += 6
        if has_guns:
            ammo = world.ammo_type
            ui.chip(s, "T", (box.x + 12, y + 1), ui.DIM, 14)
            col = {"std": ui.TEXT, "ap": (210, 225, 255), "he": ui.WARN}[ammo]
            stock = "" if ammo == "std" else f"  {world.captain.ammo_stock[ammo]}"
            ui.text(s, f"{AMMO[ammo].name}{stock}", (box.x + 36, y), col, 17)
            others = "   ".join(f"{AMMO[k].short} {v}" for k, v in world.captain.ammo_stock.items())
            ui.text(s, others, (box.right - 12, y + 1), ui.DIM, 15, anchor="topright")
            y += 22

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
                info = f"{m.ammo}/{d.ammo}" if d.ammo else ""
                if d.kind == "missile" and m.lock > 0:
                    info = f"{int(m.lock * 100)}%"
                ui.text(s, info, (box.right - 12, y + 1), ui.BAD if d.ammo and m.ammo == 0 else ui.DIM, 15,
                        anchor="topright")
            y += 22
        for n, u in enumerate(actives, 1):
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
            y += 22

    # --- подсказки и журнал ---------------------------------------------------------

    def _hints(self, world):
        s, p, t = self.screen, world.player, world.t
        hints = []
        if world.in_capsule:
            hints.append(("Вы в капсуле. Идите к порту (юго-запад) и нажмите F.", ui.WARN))
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
        y = self.h - 26 - 24 * (len(hints) - 1)
        for label, col in hints:
            w = ui.text_width(label, 18) + 24
            r = pygame.Rect(0, 0, w, 20)
            r.midtop = (self.w // 2 - 20, y - 2)
            bg = pygame.Surface(r.size, pygame.SRCALPHA)
            bg.fill((5, 9, 14, 170))
            s.blit(bg, r)
            pygame.draw.line(s, col, r.topleft, r.bottomleft, 2)
            ui.text(s, label, r.center, col, 18, anchor="center")
            y += 24

    def _log(self, world):
        y = self.h - 26
        for msg, when in reversed(world.log):
            age = world.t - when
            if age > 10:
                continue
            k = max(0.25, 1.0 - age / 10)
            ui.text(self.screen, "›", (14, y), tuple(int(c * k) for c in ui.ACCENT), 16, True)
            ui.text(self.screen, msg, (26, y), tuple(int(c * k) for c in ui.TEXT), 16)
            y -= 18

    def _help(self):
        w = 780
        rect = ui.panel(self.screen, ((self.w - w) // 2, 72, w, 36 + 20 * len(HELP_LINES)), "Управление  ·  H — скрыть")
        for i, line in enumerate(HELP_LINES):
            ui.text(self.screen, line, (rect.x + 16, rect.y + 28 + i * 20), ui.TEXT if i < 4 else ui.DIM, 16)

