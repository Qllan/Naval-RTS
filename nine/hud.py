"""Интерфейс в море: панели, миникарта, журнал, оружие, справка. Экран порта — в port_ui.py."""

import pygame

from . import config as C
from .entities import RESOURCES
from .modules import AMMO, SIZE_NAME
from .ship import PIP_MAX, PIP_NAME, PIP_SYSTEMS, SUBSYSTEM_NAME, SUBSYSTEMS

UI = (170, 190, 200)
DIM = (90, 105, 115)
ACCENT = (110, 200, 190)
WARN = (240, 150, 80)
BAD = (230, 80, 70)
PANEL = (6, 10, 16, 210)

HELP_LINES = [
    "W/S — ход вперёд/назад     A/D — руль     Shift — форсаж (тратит энергию)",
    "ЛКМ / Пробел — пушки по курсору     ПКМ (держать на цели) — захват и пуск ракет, торпеды",
    "1–4 — активные модули   Z/X/C — энергия в щиты/двигатель/орудия, V — поровну   T — тип снарядов",
    "E (держать) — добыча     F — порт     H — справка     Esc — выход",
    "",
    "Пелена гуще к северо-востоку, у Ока Девятки. Там дороже ресурсы и слабее сенсоры.",
    "Электроника в Пелене ест больше энергии: если реактор не тянет — гаснут щиты и радар.",
    "Форсаж в Пелене оставляет налёт филаментов: корабль тяжелеет. Чистка — в порту.",
    "Скаты уходят на глубину — скоро Всплеск. Под Тиходонтом вас не видно, если идти тихо.",
]


class Hud:
    MINIMAP = 190

    def __init__(self, screen, world):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 18)
        self.big = pygame.font.Font(None, 34)
        self.minimap_bg = self._build_minimap(world)
        self.show_help = False
        self.help_until = 12.0

    def text(self, s, pos, color=UI, font=None, center=False):
        img = (font or self.font).render(s, True, color)
        r = img.get_rect()
        if center:
            r.center = pos
        else:
            r.topleft = pos
        self.screen.blit(img, r)
        return r

    def panel(self, rect):
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill(PANEL)
        self.screen.blit(surf, rect.topleft)
        pygame.draw.rect(self.screen, (40, 60, 70), rect, 1)

    def bar(self, x, y, w, frac, color, label):
        pygame.draw.rect(self.screen, (25, 35, 40), (x, y, w, 8))
        pygame.draw.rect(self.screen, color, (x, y, int(w * max(0.0, min(1.0, frac))), 8))
        self.text(label, (x + w + 8, y - 4), DIM, self.small)

    # --------------------------------------------------------------------

    def _build_minimap(self, world):
        n = self.MINIMAP
        surf = pygame.Surface((n, n))
        for y in range(n):
            for x in range(n):
                d = world.veil.static_density(x / n * C.WORLD_W, y / n * C.WORLD_H)
                surf.set_at((x, y), (int(8 + 60 * d), int(14 + 12 * d), int(24 + 80 * d)))
        return surf

    def draw(self, world, docked):
        p, cap = world.player, world.captain
        t = world.t

        # --- статус корабля
        box = pygame.Rect(12, 12, 320, 196)
        self.panel(box)
        self.text(p.hull.name, (22, 20), WARN if world.in_capsule else ACCENT)
        self.bar(22, 46, 160, p.hp / p.hull.hp, (200, 90, 70), f"Корпус {int(p.hp)}/{int(p.hull.hp)}")
        if p.armor_max:
            self.bar(22, 62, 160, p.armor / p.armor_max, (170, 150, 110), f"Броня {int(p.armor)}")
        if p.shield_max:
            self.bar(22, 78, 160, p.shield / p.shield_max, (70, 140, 210), f"Щит {int(p.shield)}")
        if p.cap_max:
            bal = p.power_balance(world.density_at(p.pos))
            col = (230, 210, 90) if not p.brownout else BAD
            self.bar(22, 94, 160, p.capacitor / p.cap_max, col, f"Энергия {bal:+.1f}/с")
        self.bar(22, 110, 160, p.fouling, (160, 90, 210), f"Налёт {int(p.fouling * 100)}%")
        self.text(f"Скорость {int(p.speed)}  (макс {int(p.max_speed())})  масса {int(p.mass)}", (22, 124), DIM,
                  self.small)
        x = 22
        for k in SUBSYSTEMS:
            v = p.subsystems[k]
            col = DIM if v > 0.95 else WARN if v > 0.5 else BAD
            r = self.text(f"{SUBSYSTEM_NAME[k][:4]} {int(v * 100)}", (x, 142), col, self.small)
            x = r.right + 10
        self.text(f"Кредиты: {cap.credits} КК", (22, 162), UI)
        cargo = f"Трюм: {int(world.cargo_used)}/{world.cargo_capacity}  (~{world.cargo_value()} КК)"
        self.text(cargo, (22, 182), UI, self.small)
        y = box.bottom + 6
        dmg = []
        if p.fires:
            dmg.append(f"ПОЖАР ×{p.fires}")
        if p.leaks or p.water > 0.02:
            dmg.append(f"Течь ×{p.leaks}, вода {int(p.water * 100)}%, крен {p.list_angle:.0f}°")
        if dmg:
            self.text("   ".join(dmg), (16, y), BAD if p.fires or p.water > 0.6 else WARN)
            y += 20
        if cap.debt:
            self.text(f"ДОЛЖНИК: {cap.debt} КК", (16, y), BAD)
            y += 20
        if cap.trauma:
            self.text("Травма: перезарядка и радар ослаблены", (16, y), WARN, self.small)

        self._weapons(world)

        # --- миникарта
        self._minimap(world)

        # --- сенсоры и зона
        d = world.density_at(p.pos)
        zone = world.veil.zone(p.pos, d)
        zc = ACCENT if d < C.ZONE_MIST else WARN if d < C.ZONE_DENSE else BAD
        self.text(zone, (self.w // 2, 20), zc, self.big, center=True)
        radar = world.radar_range()
        radar_s = "РАДАР ОТКЛЮЧЁН" if radar <= 0 else f"Радар {int(radar)} м"
        self.text(f"Пелена {int(d * 100)}%   ·   {radar_s}   ·   Обзор {int(world.visual_range())} м",
                  (self.w // 2, 46), DIM, self.small, center=True)

        hints = []
        if world.in_capsule:
            hints.append(("Вы в капсуле. Идите к порту (юго-запад) и нажмите F.", WARN))
        if world.can_dock() and not docked:
            hints.append(("[F] Пришвартоваться", ACCENT))
        tx = world.sheltering_tihodont()
        if tx:
            if world.player_loud():
                hints.append(("Шум двигателя! Тиходонт беспокоится", BAD))
            else:
                hints.append(("Под Тиходонтом: вы скрыты от сенсоров", ACCENT))
        if world.emp_timer > 0:
            hints.append((f"ЭМ-вспышка: {world.emp_timer:.0f} c", BAD))
        if world.events.modifier("shield_drain", p.pos, t) > 0.5:
            hints.append(("Всплеск Пелены выжигает щиты", BAD))
        if world.events.modifier("accuracy", p.pos, t) > 0.2:
            hints.append(("Штиль: точность выше, сенсоры чище", ACCENT))
        if p.brownout:
            hints.append(("Энергия на нуле! Щиты гаснут, радар слепнет", BAD))
        if p.utility_active("bioscreen"):
            hints.append(("Био-экран: вас не видят", ACCENT))
        if world.in_smoke(p.pos):
            hints.append(("В дымовой завесе", ACCENT))
        if any(pr.kind == "missile" and pr.target is p and not pr.lost for pr in world.projectiles):
            hints.append(("Ракета на подлёте!", BAD))
        if p.fouling > 0.4:
            hints.append(("Корпус обрастает филаментами — сбавьте ход", WARN))
        node = min(world.nodes, key=lambda n: n.pos.distance_squared_to(p.pos), default=None)
        if node and node.pos.distance_to(p.pos) < 75 and not world.in_capsule:
            full = world.cargo_used >= world.cargo_capacity
            hints.append((("Трюм полон" if full else "[E] Добыча: ") + ("" if full else RESOURCES[node.kind].name), WARN if full else ACCENT))
        for i, (s, c) in enumerate(hints):
            self.text(s, (self.w // 2, self.h - 80 + i * 20 - 20 * (len(hints) - 1)), c, center=True)

        # --- журнал
        y = self.h - 24
        for msg, when in reversed(world.log):
            age = t - when
            if age > 10:
                continue
            k = max(0.25, 1.0 - age / 10)
            self.text(msg, (16, y), tuple(int(c * k) for c in UI), self.small)
            y -= 18

        if not docked and (self.show_help or t < self.help_until):
            self._help()

    def _minimap(self, world):
        n = self.MINIMAP
        x0, y0 = self.w - n - 12, 12
        self.screen.blit(self.minimap_bg, (x0, y0))
        pygame.draw.rect(self.screen, (40, 60, 70), (x0, y0, n, n), 1)
        if world.veil.in_dead_zone(world.player.pos):
            self.text("НЕТ СВЯЗИ", (x0 + n // 2, y0 + n // 2), BAD, self.big, center=True)
            return

        def m(pos):
            return (x0 + pos[0] / C.WORLD_W * n, y0 + pos[1] / C.WORLD_H * n)

        pygame.draw.circle(self.screen, (120, 190, 210), m(world.port), 4, 1)
        pygame.draw.circle(self.screen, (230, 230, 240), m(world.eye), 3)
        pygame.draw.circle(self.screen, (120, 70, 170), m(world.eye), int(C.EYE_WALL_R / C.WORLD_W * n), 1)
        pp = m(world.player.pos)
        pygame.draw.circle(self.screen, (255, 255, 255), pp, 2)
        pygame.draw.circle(self.screen, (40, 90, 80), pp, max(1, int(world.radar_range() / C.WORLD_W * n)), 1)
        self.text("Око", (m(world.eye)[0] + 6, m(world.eye)[1] - 6), DIM, self.small)

    def _help(self):
        w = 640
        rect = pygame.Rect((self.w - w) // 2, 76, w, 24 + 20 * len(HELP_LINES))
        self.panel(rect)
        for i, line in enumerate(HELP_LINES):
            self.text(line, (rect.x + 14, rect.y + 12 + i * 20), UI if i < 3 else DIM, self.small)

    def _weapons(self, world):
        p = world.player
        actives = [u for u in p.utilities if u.defn.active]
        rows = len(p.weapons) + len(actives)
        has_guns = any(m.defn.kind == "gun" and m.defn.dmg_type == "kinetic" for m in p.weapons)
        extra = 1 + (1 if has_guns else 0)       # энергия (+ снаряды)
        if world.in_capsule:
            return
        h = (rows + extra) * 20 + 16
        box = pygame.Rect(self.w - 332, self.h - 24 - h, 320, h)
        self.panel(box)
        y = box.y + 8

        # распределение энергии
        x = box.x + 10
        for key, sys_ in zip("ZXC", PIP_SYSTEMS):
            r = self.text(f"{key} {PIP_NAME[sys_][:4]}", (x, y), DIM, self.small)
            for i in range(PIP_MAX):
                col = (230, 210, 90) if i < p.pips[sys_] else (40, 50, 55)
                pygame.draw.rect(self.screen, col, (r.right + 5 + i * 8, y + 3, 6, 9))
            x += 102
        y += 22
        pygame.draw.line(self.screen, (40, 60, 70), (box.x + 8, y - 4), (box.right - 8, y - 4))
        if has_guns:
            ammo = world.ammo_type
            stock = "" if ammo == "std" else f" ({world.captain.ammo_stock[ammo]})"
            others = ", ".join(f"{AMMO[k].short} {v}" for k, v in world.captain.ammo_stock.items())
            self.text(f"[T] Снаряды: {AMMO[ammo].name}{stock}", (box.x + 10, y), UI, self.small)
            self.text(others, (box.right - 10 - self.small.size(others)[0], y), DIM, self.small)
            y += 20

        for m in p.weapons:
            d = m.defn
            ready = m.reload <= 0 and m.has_ammo and not m.overheated
            col = UI if ready else DIM
            grp = {1: "Л", 2: "П", 0: "—"}[m.group]
            label = d.name.split("«")[0].strip() if "«" in d.name else d.name
            self.text(f"{grp}  {label} {SIZE_NAME[d.size]}", (box.x + 10, y), col, self.small)
            bx = box.x + 180
            if m.overheated:
                pygame.draw.rect(self.screen, BAD, (bx, y + 4, int(60 * m.heat / 100), 6))
            else:
                frac = 1.0 - (m.reload / (d.reload * p.reload_mult()) if d.reload else 0)
                pygame.draw.rect(self.screen, (25, 35, 40), (bx, y + 4, 60, 6))
                pygame.draw.rect(self.screen, ACCENT if ready else DIM, (bx, y + 4, int(60 * max(0, frac)), 6))
                if m.heat > 1:
                    hc = WARN if m.heat > 60 else (120, 110, 80)
                    pygame.draw.rect(self.screen, hc, (bx, y + 11, int(60 * m.heat / 100), 2))
            info = ""
            if m.overheated:
                info = "ПЕРЕГРЕВ"
            elif d.ammo:
                info = f"{m.ammo}/{d.ammo}"
            if d.kind == "missile" and m.lock > 0:
                info += f" {int(m.lock * 100)}%"
            self.text(info, (box.x + 248, y), BAD if m.overheated or (d.ammo and m.ammo == 0) else DIM,
                      self.small)
            y += 20
        for n, u in enumerate(actives, 1):
            if u.active_time > 0:
                state, col = f"активен {u.active_time:.0f} с", ACCENT
            elif u.cooldown > 0:
                state, col = f"{u.cooldown:.0f} с", DIM
            elif u.defn.charges and u.charges == 0:
                state, col = "нет зарядов", WARN
            else:
                state, col = "готов", UI
            charges = f" ×{u.charges}" if u.defn.charges else ""
            self.text(f"[{n}] {u.defn.name}{charges}", (box.x + 10, y), col, self.small)
            self.text(state, (box.x + 248, y), col, self.small)
            y += 20
