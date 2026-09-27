"""Экран порта: сервис, верфь, оснащение, склад.

Управление: A/D или стрелки — вкладки, W/S или стрелки — выбор, Enter — действие,
Backspace — снять модуль, G — группа огня, Esc — назад / выйти в море.
"""

import pygame

from . import config as C
from .hulls import PLAYER_HULLS
from .modules import AMMO, CATEGORY_NAME, MODULES, SIZE_NAME, WeaponDef, module_stats
from .ship import SUBSYSTEM_NAME, SUBSYSTEMS, Ship
from .world import AMMO_PACK, MODULE_RESALE

UI = (170, 190, 200)
DIM = (90, 105, 115)
ACCENT = (110, 200, 190)
WARN = (240, 150, 80)
BAD = (230, 80, 70)
GOOD = (120, 210, 120)
SEL = (30, 60, 70)
PANEL = (6, 10, 16, 235)

TABS = ("Сервис", "Верфь", "Оснащение", "Склад")
GROUP_NAME = {1: "ЛКМ", 2: "ПКМ", 0: "выкл."}
DENSE = 0.8          # «плотная Пелена» для сравнения характеристик


def ship_summary(ship, cargo=0.0):
    """Характеристики для сравнения: (подпись, значение, чем больше — тем лучше)."""
    ship.cargo_mass = cargo
    dps = sum(w.defn.damage * w.defn.pellets / w.defn.reload for w in ship.weapons)
    accel = ship.engine.thrust * 100 / ship.mass if ship.engine else 0
    return [
        ("Корпус", ship.hull.hp, True),
        ("Броня", ship.armor_max, True),
        ("Щит", ship.shield_max, True),
        ("Масса", ship.mass, False),
        ("Скорость", ship.base_top_speed(), True),
        ("Разгон", accel, True),
        ("Поворот", ship.hull.turn_rate * min(1.15, ship.mass_factor()), True),
        ("Энергия (чисто)", ship.power_balance(0.0), True),
        ("Энергия (Пелена)", ship.power_balance(DENSE), True),
        ("Радар (чисто)", ship.radar_range(0.0), True),
        ("Радар (Пелена)", ship.radar_range(DENSE), True),
        ("Урон/с", dps, True),
        ("Трюм", ship.cargo_capacity, True),
    ]


class PortUI:
    def __init__(self, screen):
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 18)
        self.big = pygame.font.Font(None, 32)
        self.reset()

    def reset(self):
        self.tab = 0
        self.sel = 0
        self.picker = False      # выбор модуля для слота
        self.pick_sel = 0
        self.slot = 0
        self.message = ("", UI)

    # --- данные вкладок -------------------------------------------------

    def service_items(self, world):
        cap = world.captain
        return [
            (f"Продать груз (+{world.cargo_value()} КК)", world.sell_cargo_action),
            (f"Полный ремонт: корпус, броня, подсистемы ({world.repair_cost()} КК)", world.repair),
            (f"Пополнить боезапас и заряды ({world.rearm_cost()} КК)", world.rearm),
            (f"Бронебойные снаряды ×{AMMO_PACK} ({world.ammo_pack_cost('ap')} КК), на борту "
             f"{cap.ammo_stock['ap']}", lambda: world.buy_ammo("ap")),
            (f"Фугасные снаряды ×{AMMO_PACK} ({world.ammo_pack_cost('he')} КК), на борту "
             f"{cap.ammo_stock['he']}", lambda: world.buy_ammo("he")),
            (f"Очистить налёт филаментов ({C.CLEAN_COST} КК)", world.clean_hull),
            (f"Погасить долг ({cap.debt} КК)" if cap.debt else "Долгов нет", world.pay_debt_action),
            (f"Лечение травмы ({C.MEDICAL_COST} КК)" if cap.trauma else "Капитан здоров", world.heal),
        ]

    def picker_items(self, world):
        """Модули для выбранного слота: сначала со склада, потом из магазина."""
        compat = world.compatible(self.slot)
        keys = {m.key for m in compat}
        items = [("storage", k) for k in dict.fromkeys(world.captain.storage) if k in keys]
        items += [("shop", m.key) for m in sorted(compat, key=lambda m: m.price)]
        return items

    # --- ввод -------------------------------------------------------------

    def say(self, text, color=UI):
        self.message = (text, color)

    def handle_key(self, key, world):
        """Возвращает 'leave', если игрок хочет выйти в море."""
        if key in (pygame.K_ESCAPE, pygame.K_f):
            if self.picker:
                self.picker = False
                return None
            problems = world.undock_problems()
            if problems:
                self.say("Нельзя выйти: " + problems[0], BAD)
                return None
            return "leave"
        if not self.picker and key in (pygame.K_LEFT, pygame.K_a):
            self.tab = (self.tab - 1) % len(TABS)
            self.sel = 0
            return None
        if not self.picker and key in (pygame.K_RIGHT, pygame.K_d):
            self.tab = (self.tab + 1) % len(TABS)
            self.sel = 0
            return None
        n = self._count(world)
        if key in (pygame.K_UP, pygame.K_w):
            self._move(-1, n)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._move(1, n)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(world)
        elif key in (pygame.K_BACKSPACE, pygame.K_DELETE) and TABS[self.tab] == "Оснащение" and not self.picker:
            err = world.uninstall(self.sel)
            self.say(err or "Модуль снят и отправлен на склад.", BAD if err else ACCENT)
        elif key == pygame.K_g and TABS[self.tab] == "Оснащение" and not self.picker:
            g = world.cycle_group(self.sel)
            if g is None:
                self.say("Группа огня — только для оружия.", WARN)
            else:
                self.say(f"Группа огня: {GROUP_NAME[g]}", ACCENT)
        return None

    def _count(self, world):
        tab = TABS[self.tab]
        if tab == "Сервис":
            return len(self.service_items(world))
        if tab == "Верфь":
            return len(PLAYER_HULLS)
        if tab == "Оснащение":
            return len(self.picker_items(world)) if self.picker else len(world.player.hull.slots)
        return len(world.captain.storage)

    def _move(self, d, n):
        if n == 0:
            return
        if self.picker:
            self.pick_sel = (self.pick_sel + d) % n
        else:
            self.sel = (self.sel + d) % n

    def _activate(self, world):
        tab = TABS[self.tab]
        if tab == "Сервис":
            items = self.service_items(world)
            if self.sel < len(items):
                label, action = items[self.sel]
                ok = action()
                self.say(("Готово: " if ok else "Недоступно: ") + label, ACCENT if ok else WARN)
        elif tab == "Верфь":
            hull = PLAYER_HULLS[self.sel]
            err = world.buy_hull(hull.key)
            self.say(err or f"Новый корабль: {hull.name}. Старые модули — на складе.", BAD if err else ACCENT)
        elif tab == "Оснащение":
            if not self.picker:
                self.slot = self.sel
                self.picker = True
                self.pick_sel = 0
                return
            items = self.picker_items(world)
            if not items:
                return
            src, key = items[self.pick_sel]
            err = world.install(self.slot, key, from_storage=(src == "storage"))
            self.say(err or f"Установлено: {MODULES[key].name}", BAD if err else ACCENT)
            if not err:
                self.picker = False
        elif tab == "Склад":
            storage = world.captain.storage
            if self.sel < len(storage):
                key = storage[self.sel]
                price = world.sell_from_storage(key)
                self.say(f"Продано: {MODULES[key].name} (+{price} КК)", ACCENT)
                self.sel = min(self.sel, max(0, len(storage) - 1))

    # --- отрисовка --------------------------------------------------------

    def text(self, s, pos, color=UI, font=None, center=False, right=False):
        img = (font or self.font).render(s, True, color)
        r = img.get_rect()
        if center:
            r.midtop = pos
        elif right:
            r.topright = pos
        else:
            r.topleft = pos
        self.screen.blit(img, r)
        return r

    def wrapped(self, s, pos, width, color=UI, font=None):
        """Текст с переносом по словам. Возвращает y под последней строкой."""
        font = font or self.small
        x, y = pos
        line = ""
        for word in s.split():
            test = f"{line} {word}".strip()
            if font.size(test)[0] > width and line:
                self.text(line, (x, y), color, font)
                y += font.get_linesize()
                line = word
            else:
                line = test
        if line:
            self.text(line, (x, y), color, font)
            y += font.get_linesize()
        return y

    def draw(self, world):
        w, h = 1060, 620
        rect = pygame.Rect((self.w - w) // 2, (self.h - h) // 2, w, h)
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill(PANEL)
        self.screen.blit(surf, rect.topleft)
        pygame.draw.rect(self.screen, (40, 60, 70), rect, 1)

        self.text("ПОРТ БЕЖЕНЦЕВ", (rect.x + 20, rect.y + 14), ACCENT, self.big)
        cap = world.captain
        money = f"Кредиты: {cap.credits} КК" + (f"   Долг: {cap.debt}" if cap.debt else "")
        self.text(money, (rect.right - 20, rect.y + 18), BAD if cap.debt else UI, right=True)
        x = rect.x + 20
        for i, name in enumerate(TABS):
            col = ACCENT if i == self.tab else DIM
            r = self.text(f"  {name}  ", (x, rect.y + 52), col)
            if i == self.tab:
                pygame.draw.line(self.screen, ACCENT, r.bottomleft, r.bottomright, 2)
            x = r.right + 12

        body = pygame.Rect(rect.x + 20, rect.y + 86, rect.w - 40, rect.h - 140)
        tab = TABS[self.tab]
        if tab == "Сервис":
            self._service(world, body)
        elif tab == "Верфь":
            self._shipyard(world, body)
        elif tab == "Оснащение":
            self._fitting(world, body)
        else:
            self._storage(world, body)

        msg, col = self.message
        self.text(msg, (rect.x + 20, rect.bottom - 48), col)
        hint = "A/D — вкладки   W/S — выбор   Enter — действие   Backspace — снять   G — группа огня   Esc — в море"
        self.text(hint, (rect.centerx, rect.bottom - 24), DIM, self.small, center=True)

    def _list(self, rows, x, y, width, sel, row_h=24):
        for i, (label, col) in enumerate(rows):
            if i == sel:
                pygame.draw.rect(self.screen, SEL, (x - 6, y + i * row_h - 3, width, row_h))
            self.text(label, (x, y + i * row_h), col)

    def _stats(self, world, x, y, preview=None):
        """Сводка корабля; с `preview` — сравнение «было > станет»."""
        cargo = world.cargo_used
        cur = ship_summary(world.player, cargo)
        new = ship_summary(preview, cargo) if preview else None
        title = world.player.hull.name
        if preview is not None and preview.hull is not world.player.hull:
            title += f"  >  {preview.hull.name}"
        self.text(title, (x, y), ACCENT)
        y += 26
        for i, (label, val, higher) in enumerate(cur):
            self.text(label, (x, y + i * 21), DIM, self.small)
            self.text(f"{val:.0f}", (x + 200, y + i * 21), UI, self.small, right=True)
            if new:
                nv = new[i][1]
                if abs(nv - val) > 0.5:
                    better = (nv > val) == higher
                    self.text(f"> {nv:.0f}", (x + 212, y + i * 21), GOOD if better else BAD, self.small)
        y += len(cur) * 21 + 10
        p = world.player
        col = WARN if min(p.subsystems.values()) < 1 else DIM
        for i in range(0, len(SUBSYSTEMS), 2):
            pair = SUBSYSTEMS[i:i + 2]
            line = "   ".join(f"{SUBSYSTEM_NAME[k]} {int(p.subsystems[k] * 100)}%" for k in pair)
            self.text(line, (x, y + i // 2 * 18), col, self.small)

    def _service(self, world, body):
        rows = [(label, UI) for label, _ in self.service_items(world)]
        self._list(rows, body.x, body.y, 560, self.sel)
        p = world.player
        y = body.y + len(rows) * 24 + 20
        self.text(f"Корпус {int(p.hp)}/{int(p.hull.hp)}   Броня {int(p.armor)}/{int(p.armor_max)}   "
                  f"Налёт {int(p.fouling * 100)}%", (body.x, y), DIM)
        self._stats(world, body.right - 300, body.y)

    def _shipyard(self, world, body):
        rows = []
        for h in PLAYER_HULLS:
            full, cost = world.hull_offer(h.key)
            mark = "  (ваш)" if h.key == world.player.hull.key else ""
            rows.append((f"{h.name:<18} {cost:>6} КК{mark}", ACCENT if mark else UI))
        self._list(rows, body.x, body.y, 360, self.sel)
        h = PLAYER_HULLS[self.sel]
        full, cost = world.hull_offer(h.key)
        x, y = body.x + 390, body.y
        self.text(h.name, (x, y), ACCENT, self.big)
        self.text(h.role, (x, y + 30), DIM)
        self.wrapped(h.desc, (x, y + 52), 600)
        self.text(f"Цена с базовым оснащением {full} КК, со сдачей текущего корпуса {cost} КК",
                  (x, y + 74), UI, self.small)
        slots = {}
        for s in h.slots:
            slots.setdefault(s.category, []).append(SIZE_NAME[s.size])
        line = ", ".join(f"{CATEGORY_NAME[c]} {'/'.join(v)}" for c, v in slots.items())
        self.text("Слоты: " + line, (x, y + 96), DIM, self.small)
        preview = Ship(h.key, (0, 0))
        self._stats(world, x, y + 128, preview)

    def _fitting(self, world, body):
        p = world.player
        rows = []
        for i, slot in enumerate(p.hull.slots):
            key = p.fit[i]
            name = MODULES[key].name if key else "— пусто —"
            label = f"{CATEGORY_NAME[slot.category]} {SIZE_NAME[slot.size]}: {name}"
            w = next((w for w in p.weapons if w.index == i), None)
            if w is not None:
                label += f"  [{GROUP_NAME[w.group]}]"
            rows.append((label, UI if key else DIM))
        self._list(rows, body.x, body.y, 400, -1 if self.picker else self.sel, 22)
        if self.picker:
            pygame.draw.rect(self.screen, (60, 90, 100), (body.x - 6, body.y + self.slot * 22 - 3, 400, 22), 1)
        else:
            self.text("G — группа огня выбранного орудия (ЛКМ / ПКМ / выкл.)",
                      (body.x, body.y + len(rows) * 22 + 12), DIM, self.small)
            ammo = ", ".join(f"{AMMO[k].name}: {v}" for k, v in world.captain.ammo_stock.items())
            self.text(f"Особые снаряды на борту — {ammo}", (body.x, body.y + len(rows) * 22 + 30), DIM,
                      self.small)

        x = body.x + 420
        preview = None
        if self.picker:
            items = self.picker_items(world)
            prow = []
            for src, key in items:
                m = MODULES[key]
                tag = "склад" if src == "storage" else f"{m.price} КК"
                cur = " (стоит)" if p.fit[self.slot] == key and src == "shop" else ""
                prow.append((f"{m.name} [{SIZE_NAME[m.size]}] — {tag}{cur}", ACCENT if src == "storage" else UI))
            self.text(f"Выбор модуля ({CATEGORY_NAME[p.hull.slots[self.slot].category]})", (x, body.y - 2), DIM,
                      self.small)
            self._list(prow[:12], x, body.y + 18, 330, self.pick_sel if self.pick_sel < 12 else -1, 22)
            if items:
                key = items[min(self.pick_sel, len(items) - 1)][1]
                m = MODULES[key]
                y = body.y + 18 + min(12, len(prow)) * 22 + 10
                y = self.wrapped(m.desc, (x, y), 330) + 4
                for j, line in enumerate(module_stats(m)):
                    self.text(line, (x, y + j * 18), DIM, self.small)
                fit = list(p.fit)
                fit[self.slot] = key
                preview = Ship(p.hull.key, (0, 0), fit=fit)
        else:
            key = p.fit[self.sel] if self.sel < len(p.fit) else None
            if key:
                m = MODULES[key]
                self.text(m.name, (x, body.y), ACCENT)
                y = self.wrapped(m.desc, (x, body.y + 22), 330) + 4
                for j, line in enumerate(module_stats(m)):
                    self.text(line, (x, y + j * 18), DIM, self.small)
                if isinstance(m, WeaponDef) and m.kind == "gun":
                    slot = p.hull.slots[self.sel]
                    self.text(f"Установка: сектор {min(slot.arc, m.arc):g}°, направление {slot.facing:+g}°",
                              (x, y + len(module_stats(m)) * 18), DIM, self.small)
            else:
                self.text("Enter — выбрать модуль", (x, body.y), DIM)
        self._stats(world, body.right - 250, body.y, preview)

    def _storage(self, world, body):
        storage = world.captain.storage
        if not storage:
            self.text("Склад пуст. Сюда попадают снятые модули и трофеи.", (body.x, body.y), DIM)
            return
        rows = [(f"{MODULES[k].name} [{SIZE_NAME[MODULES[k].size]}] — продать за "
                 f"{int(MODULES[k].price * MODULE_RESALE)} КК", UI) for k in storage]
        self._list(rows, body.x, body.y, 560, self.sel)
        key = storage[min(self.sel, len(storage) - 1)]
        x = body.x + 600
        self.text(MODULES[key].name, (x, body.y), ACCENT)
        for j, line in enumerate(module_stats(MODULES[key])):
            self.text(line, (x, body.y + 24 + j * 18), DIM, self.small)
