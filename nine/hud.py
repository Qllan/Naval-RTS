"""Интерфейс: панели, миникарта, журнал, экран порта, справка."""

import pygame
from pygame.math import Vector2

from . import config as C
from .entities import RESOURCES, SHIP_CLASSES

UI = (170, 190, 200)
DIM = (90, 105, 115)
ACCENT = (110, 200, 190)
WARN = (240, 150, 80)
BAD = (230, 80, 70)
PANEL = (6, 10, 16, 210)

HELP_LINES = [
    "W/S — ход вперёд/назад     A/D — руль     Shift — форсаж",
    "ЛКМ / Пробел — огонь по курсору     E (держать) — добыча",
    "F — швартовка в порту     H — справка     F12 — скриншот     Esc — выход",
    "",
    "Пелена гуще к северо-востоку, у Ока Девятки. Там дороже ресурсы и слабее сенсоры.",
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
        box = pygame.Rect(12, 12, 300, 150)
        self.panel(box)
        name = p.cls.name
        self.text(name, (22, 20), WARN if world.in_capsule else ACCENT)
        self.bar(22, 46, 160, p.hull / p.cls.hull, (200, 90, 70), f"Корпус {int(p.hull)}/{int(p.cls.hull)}")
        if p.cls.shield:
            self.bar(22, 62, 160, p.shield / p.cls.shield, (70, 140, 210), f"Щиты {int(p.shield)}")
        self.bar(22, 78, 160, p.fouling, (160, 90, 210), f"Налёт {int(p.fouling * 100)}%")
        self.text(f"Скорость {int(p.speed)}  (макс {int(p.max_speed())})", (22, 94), DIM, self.small)
        self.text(f"Кредиты: {cap.credits} КК", (22, 112), UI)
        cargo = f"Трюм: {int(world.cargo_used)}/{world.cargo_capacity}  (~{world.cargo_value()} КК)"
        self.text(cargo, (22, 132), UI, self.small)
        y = box.bottom + 6
        if cap.debt:
            self.text(f"ДОЛЖНИК: {cap.debt} КК", (16, y), BAD)
            y += 20
        if cap.trauma:
            self.text("Травма: перезарядка и радар ослаблены", (16, y), WARN, self.small)

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

        if docked:
            self._dock(world)
        elif self.show_help or t < self.help_until:
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

    def dock_options(self, world):
        cap = world.captain
        opts = [
            ("1", f"Продать груз (+{world.cargo_value()} КК)"),
            ("2", f"Ремонт корпуса ({world.repair_cost()} КК)"),
            ("3", f"Очистить налёт ({C.CLEAN_COST} КК)"),
        ]
        for key, kind, label in (("4", "sensor", "Сенсоры"), ("5", "cargo", "Трюм +15"), ("6", "gun", "Орудия")):
            cost = world.upgrade_cost(kind)
            lvl = cap.upgrades[kind]
            opts.append((key, f"{label} ур.{lvl} -> {lvl + 1} ({cost} КК)" if cost else f"{label}: максимум"))
        for key, sk in (("7", "cruiser"), ("8", "barge"), ("9", "scout")):
            cls = SHIP_CLASSES[sk]
            mark = "  (текущий)" if world.player.cls.key == sk else ""
            opts.append((key, f"Корабль: {cls.name} ({world.ship_cost(sk)} КК с обменом){mark}"))
        opts.append(("0", f"Погасить долг ({cap.debt} КК)" if cap.debt else "Долгов нет"))
        opts.append(("M", f"Лечение травмы ({C.MEDICAL_COST} КК)" if cap.trauma else "Здоров"))
        return opts

    def _dock(self, world):
        w, h = 560, 380
        rect = pygame.Rect((self.w - w) // 2, (self.h - h) // 2, w, h)
        self.panel(rect)
        self.text("ПОРТ БЕЖЕНЦЕВ", (rect.centerx, rect.y + 22), ACCENT, self.big, center=True)
        for i, (key, label) in enumerate(self.dock_options(world)):
            self.text(f"[{key}]  {label}", (rect.x + 24, rect.y + 50 + i * 24), UI)
        if world.captain.debt:
            self.text("Пока есть долг — покупки кораблей и модулей закрыты", (rect.centerx, rect.bottom - 44), BAD, self.small, center=True)
        self.text("[F] / [Esc] — выйти в море", (rect.centerx, rect.bottom - 22), DIM, self.small, center=True)
