"""Экран порта: сервис, верфь, оснащение, склад.

Управление: A/D или стрелки — вкладки, W/S или стрелки — выбор, Enter — действие,
Backspace — снять модуль, G — группа огня, Esc — назад / выйти в море.
"""

import pygame
from pygame.math import Vector2

from . import config as C
from .gfx import ui
from .gfx.ship_art import ShipArt
from .hulls import PLAYER_HULLS
from .modules import AMMO, CATEGORY_NAME, MODULES, SIZE_NAME, WeaponDef, module_stats
from .ship import SUBSYSTEM_NAME, SUBSYSTEMS, Ship
from .world import AMMO_PACK, MODULE_RESALE

UI, DIM, ACCENT, WARN = ui.TEXT, ui.DIM, ui.ACCENT, ui.WARN
TAB_ICON = ("utility", "hull", "gun", "cargo")

TABS = ("Сервис", "Верфь", "Оснащение", "Склад")
GROUP_NAME = {1: "ЛКМ", 2: "ПКМ", 0: "выкл."}
DENSE = 0.8          # «плотная Пелена» для сравнения характеристик



def shipyard_window(total, selected, page_size=8):
    """Видимое окно каталога; selected всегда в нём при валидном индексе."""
    if total <= 0:
        return 0, 0
    visible = max(1, min(total, page_size))
    selected = max(0, min(total - 1, selected))
    first = max(0, min(total - visible, selected - visible // 2))
    return first, first + visible


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
    def __init__(self, screen, audio=None):
        self.audio = audio
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.art = ShipArt()
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
        self.age = 0.0
        self.zones = []          # [(rect, вид, индекс)] — кликабельные зоны, пересобираются каждый кадр
        self.hover = None
        self.drag = None         # перетаскиваемый модуль: {"src", "key", "start", "active"}
        self.mouse = (0, 0)

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
        self.sound("ui_error" if color == ui.BAD else "ui_buy" if color == ACCENT else "ui_click")

    def sound(self, name):
        if self.audio is not None:
            self.audio.ui(name)

    def handle_key(self, key, world):
        """Возвращает 'leave', если игрок хочет выйти в море."""
        if key in (pygame.K_ESCAPE, pygame.K_f):
            if self.picker:
                self.picker = False
                return None
            problems = world.undock_problems()
            if problems:
                self.say("Нельзя выйти: " + problems[0], ui.BAD)
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
        if key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
            self.sound("ui_hover")
        if key in (pygame.K_UP, pygame.K_w):
            self._move(-1, n)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._move(1, n)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._activate(world)
        elif key in (pygame.K_BACKSPACE, pygame.K_DELETE) and TABS[self.tab] == "Оснащение" and not self.picker:
            err = world.uninstall(self.sel)
            self.say(err or "Модуль снят и отправлен на склад.", ui.BAD if err else ACCENT)
        elif key == pygame.K_g and TABS[self.tab] == "Оснащение" and not self.picker:
            g = world.cycle_group(self.sel)
            if g is None:
                self.say("Группа огня — только для оружия.", WARN)
            else:
                self.say(f"Группа огня: {GROUP_NAME[g]}", ACCENT)
        return None

    # --- мышь ------------------------------------------------------------------

    def handle_event(self, e, world):
        """Любое событие pygame. Возвращает 'leave', если игрок выходит в море."""
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_r:
                self._service_all(world)
                return None
            if e.key == pygame.K_p and not self.picker:
                self._sell_all(world)
                return None
            return self.handle_key(e.key, world)
        if e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
            if self.drag and not self.drag["active"]:
                if (Vector2(e.pos) - self.drag["start"]).length() > 6:
                    self.drag["active"] = True
            z = self._zone_at(e.pos)
            if z != self.hover:
                self.hover = z
                if z and z[0] in ("row", "slot", "pick", "tab", "button"):
                    self.sound("ui_hover")
                if z and z[0] in ("row", "slot") and not self.picker:
                    self.sel = z[1]
                elif z and z[0] == "pick":
                    self.pick_sel = z[1]
        elif e.type == pygame.MOUSEWHEEL:
            n = self._count(world)
            self._move(-e.y, n)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            z = self._zone_at(e.pos)
            if z is None:
                if e.button == 1 and self.picker:
                    self.picker = False
                return None
            kind, idx = z
            if e.button == 3:
                if kind == "slot":
                    err = world.uninstall(idx)
                    self.say(err or "Модуль снят и отправлен на склад.", ui.BAD if err else ACCENT)
                elif self.picker:
                    self.picker = False
                return None
            if e.button != 1:
                return None
            if kind == "tab":
                self.tab, self.sel, self.picker = idx, 0, False
                self.sound("ui_click")
            elif kind == "button":
                return self._button(idx, world)
            elif kind == "row":
                self.sel = idx
                self._activate(world)
            elif kind == "slot":
                if self.picker and idx != self.slot:
                    self.slot, self.pick_sel = idx, 0
                    self.sound("ui_click")
                else:
                    self.sel = idx
                    self._activate(world)
            elif kind == "pick":
                self.pick_sel = idx
                src, key = self.picker_items(world)[idx]
                self.drag = {"src": src, "key": key, "start": Vector2(e.pos), "active": False}
            elif kind == "group":
                g = world.cycle_group(idx)
                if g is not None:
                    self.say(f"Группа огня: {GROUP_NAME[g]}", ACCENT)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            drag, self.drag = self.drag, None
            z = self._zone_at(e.pos)
            if not drag["active"]:
                if z == ("pick", self.pick_sel):
                    self._activate(world)           # простой клик — установить в выбранный слот
                return None
            if z and z[0] == "slot":
                err = world.install(z[1], drag["key"], from_storage=(drag["src"] == "storage"))
                self.say(err or f"Установлено: {MODULES[drag['key']].name}", ui.BAD if err else ACCENT)
                if not err:
                    self.picker = False
                    self.sel = z[1]
        return None

    def _zone_at(self, pos):
        for rect, kind, idx in reversed(self.zones):
            if rect.collidepoint(pos):
                return kind, idx
        return None

    def _button(self, name, world):
        if name == "leave":
            problems = world.undock_problems()
            if problems:
                self.say("Нельзя выйти: " + problems[0], ui.BAD)
                return None
            return "leave"
        if name == "service":
            self._service_all(world)
        elif name == "sell":
            self._sell_all(world)
        return None

    def _service_all(self, world):
        cost = world.service_all_cost()
        if cost == 0:
            self.say("Корабль в порядке — чинить и пополнять нечего.", DIM)
            return
        done = world.service_all()
        if done:
            left = world.service_all_cost()
            tail = f" Не хватило на остальное ({left} КК)." if left else ""
            self.say("Готово: " + ", ".join(done) + "." + tail, ACCENT if not left else WARN)
        else:
            self.say(f"Не хватает кредитов: нужно {cost} КК.", ui.BAD)

    def _sell_all(self, world):
        value = world.cargo_value()
        if world.sell_cargo_action():
            self.say(f"Груз продан: +{value} КК", ACCENT)
        else:
            self.say("Трюм пуст.", DIM)

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
            self.say(err or f"Новый корабль: {hull.name}. Старые модули — на складе.", ui.BAD if err else ACCENT)
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
            self.say(err or f"Установлено: {MODULES[key].name}", ui.BAD if err else ACCENT)
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

    def draw(self, world, dt=1 / 60):
        self.age += dt
        self.zones = []
        k = 1 - (1 - min(1.0, self.age / 0.22)) ** 3            # анимация открытия
        w, h = 1080, 640
        rect = pygame.Rect((self.w - w) // 2, (self.h - h) // 2 + int((1 - k) * 30), w, h)
        dim = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, int(110 * k)))
        self.screen.blit(dim, (0, 0))
        ui.panel(self.screen, rect, None, ACCENT, bg=(5, 9, 14, 236))

        ui.text(self.screen, "ПОРТ БЕЖЕНЦЕВ", (rect.x + 22, rect.y + 16), ACCENT, 30, True)
        ui.text(self.screen, "нейтральный хаб · Гильдия «Горизонт»", (rect.x + 24, rect.y + 44), DIM, 15)
        cap = world.captain
        ui.icon(self.screen, "credits", (rect.right - 190, rect.y + 27), 16, ui.C_ENERGY)
        ui.text(self.screen, f"{cap.credits} КК", (rect.right - 176, rect.y + 18), UI, 22, True)
        if cap.debt:
            ui.chip(self.screen, f"ДОЛГ {cap.debt}", (rect.right - 22, rect.y + 44), ui.BAD, 15, anchor="topright")
        x = rect.x + 22
        ty = rect.y + 70
        for i, name in enumerate(TABS):
            active = i == self.tab
            col = ACCENT if active else DIM
            tw = ui.text_width(name.upper(), 17, True) + 40
            tr = pygame.Rect(x, ty, tw, 28)
            self.zones.append((tr, "tab", i))
            if not active and tr.collidepoint(self.mouse):
                pygame.draw.rect(self.screen, ui.FAINT, tr, 1)
            if active:
                pygame.draw.rect(self.screen, ui.SEL_BG, tr)
                pygame.draw.line(self.screen, ACCENT, tr.bottomleft, tr.bottomright, 2)
            ui.icon(self.screen, TAB_ICON[i], (tr.x + 14, tr.centery), 13, col)
            ui.text(self.screen, name.upper(), (tr.x + 26, tr.centery), col, 17, True, anchor="midleft")
            x = tr.right + 6
        pygame.draw.line(self.screen, ui.LINE, (rect.x + 16, ty + 29), (rect.right - 16, ty + 29))
        self._quick_bar(world, rect)

        body = pygame.Rect(rect.x + 24, rect.y + 116, rect.w - 48, rect.h - 170)
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
        if msg:
            pygame.draw.line(self.screen, col, (rect.x + 22, rect.bottom - 50), (rect.x + 22, rect.bottom - 34), 2)
            ui.text(self.screen, msg, (rect.x + 30, rect.bottom - 50), col, 18)
        pygame.draw.line(self.screen, ui.LINE, (rect.x + 16, rect.bottom - 28), (rect.right - 16, rect.bottom - 28))
        x = rect.x + 22
        for key, label in (("A/D", "вкладки"), ("W/S", "выбор"), ("Enter", "действие"), ("Backspace/ПКМ", "снять"),
                           ("G", "группа огня"), ("R", "всё починить"), ("P", "продать груз")):
            r = ui.chip(self.screen, key, (x, rect.bottom - 22), DIM, 14)
            r = ui.text(self.screen, label, (r.right + 6, rect.bottom - 22), DIM, 15)
            x = r.right + 16
        br = pygame.Rect(rect.right - 150, rect.bottom - 25, 134, 20)
        self._btn(br, "В МОРЕ  ·  Esc", "leave", ACCENT)
        if self.drag and self.drag["active"]:
            m = MODULES[self.drag["key"]]
            mx, my = self.mouse
            ui.icon(self.screen, ui.module_icon_kind(m), (mx + 14, my + 10), 16, ACCENT)
            ui.text(self.screen, m.name, (mx + 26, my + 2), ACCENT, 16, True)
        elif self.hover and self.hover[0] == "pick" and self.picker:
            self._tooltip(world, self.hover[1])

    def _btn(self, rect, label, name, color=UI, enabled=True):
        rect = pygame.Rect(rect)
        self.zones.append((rect, "button", name))
        hot = rect.collidepoint(self.mouse)
        if hot:
            pygame.draw.rect(self.screen, ui.SEL_BG, rect)
        pygame.draw.rect(self.screen, color if enabled else ui.FAINT, rect, 1)
        ui.text(self.screen, label, rect.center, (color if hot else UI) if enabled else DIM, 15, True, anchor="center")

    def _quick_bar(self, world, rect):
        """Быстрые действия при входе в порт: «всё починить и пополнить», «продать груз»."""
        y = rect.y + 18
        cost = world.service_all_cost()
        value = world.cargo_value()
        x = rect.x + 300
        if cost:
            enough = world.captain.credits >= cost
            label = f"R  Починить и пополнить всё — {cost} КК"
            w = ui.text_width(label, 15, True) + 24
            self._btn((x, y, w, 24), label, "service", ACCENT if enough else WARN)
            x += w + 8
        if value:
            label = f"P  Продать груз +{value} КК"
            w = ui.text_width(label, 15, True) + 24
            self._btn((x, y, w, 24), label, "sell", ui.C_ENERGY)

    def _tooltip(self, world, idx):
        """Подсказка у курсора: чем модуль из списка отличается от стоящего в слоте."""
        items = self.picker_items(world)
        if idx >= len(items):
            return
        src, key = items[idx]
        m = MODULES[key]
        p = world.player
        fit = list(p.fit)
        fit[self.slot] = key
        cur = ship_summary(p, world.cargo_used)
        new = ship_summary(Ship(p.hull.key, (0, 0), fit=fit), world.cargo_used)
        lines = []
        for (label, a, higher), (_, b, _) in zip(cur, new):
            if abs(b - a) > 0.05:
                if abs(a) > 1e-6:
                    v = (b - a) / abs(a) * 100
                    if abs(v) < 0.5:
                        continue
                    pct = f"{v:+.1f}%" if abs(v) < 10 else f"{v:+.0f}%"
                else:
                    pct = f"{b - a:+.0f}"
                good = (b > a) == higher
                lines.append((f"{pct}  {label.lower()}", ui.GOOD if good else ui.BAD))
        if not lines:
            lines.append(("без изменений", DIM))
        old = p.fit[self.slot]
        head = f"вместо: {MODULES[old].name}" if old else "в пустой слот"
        w = max(ui.text_width(m.name, 17, True), *(ui.text_width(t, 16) for t, _ in lines), ui.text_width(head, 15)) + 24
        h = 50 + len(lines) * 18
        mx, my = self.mouse
        r = pygame.Rect(mx + 18, my + 12, w, h)
        r.right = min(r.right, self.w - 4)
        r.bottom = min(r.bottom, self.h - 4)
        ui.panel(self.screen, r, None, ACCENT, bg=(8, 14, 20, 245))
        ui.text(self.screen, m.name, (r.x + 12, r.y + 8), UI, 17, True)
        ui.text(self.screen, head, (r.x + 12, r.y + 27), DIM, 15)
        for i, (t, col) in enumerate(lines):
            ui.text(self.screen, t, (r.x + 12, r.y + 46 + i * 18), col, 16)

    def _list(self, rows, x, y, width, sel, row_h=24, zone="row", first=0):
        """Строки (подпись, цвет[, иконка]). Иконка — вид из gfx.ui.icon. Строки кликабельны."""
        for i, row in enumerate(rows):
            label, col = row[0], row[1]
            kind = row[2] if len(row) > 2 else None
            rr = pygame.Rect(x - 8, y + i * row_h - 4, width, row_h)
            if zone:
                self.zones.append((rr, zone, first + i))
            if i == sel:
                ui.selection(self.screen, rr)
            elif zone and rr.collidepoint(self.mouse) and not self.drag:
                pygame.draw.rect(self.screen, ui.FAINT, rr, 1)
            tx = x
            if kind:
                ui.icon(self.screen, kind, (x + 7, y + i * row_h + 7), 13, col)
                tx = x + 20
            limit = width - (tx - x) - 4
            if self.font.size(label)[0] > limit:
                while label and self.font.size(label + "…")[0] > limit:
                    label = label[:-1]
                label += "…"
            self.text(label, (tx, y + i * row_h), col)

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
                    self.text(f"> {nv:.0f}", (x + 212, y + i * 21), ui.GOOD if better else ui.BAD, self.small)
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
        # Ограничиваем число строк: каталог может состоять из десятков корпусов.
        # При перемещении мышью/клавиатурой выбор остаётся видимым.
        if not PLAYER_HULLS:
            self.text("Нет доступных корпусов", (body.x, body.y), DIM)
            return
        self.sel = max(0, min(self.sel, len(PLAYER_HULLS) - 1))
        page_size = max(1, min(8, (body.h - 160) // 26))
        first, end = shipyard_window(len(PLAYER_HULLS), self.sel, page_size)
        rows = []
        for h in PLAYER_HULLS[first:end]:
            full, cost = world.hull_offer(h.key)
            mark = "  (ваш)" if h.key == world.player.hull.key else ""
            rows.append((f"{h.name:<18} {cost:>6} КК{mark}", ACCENT if mark else UI))
        self._list(rows, body.x, body.y, 360, self.sel - first, 26, first=first)
        y_footer = body.y + len(rows) * 26 + 5
        self.text(f"Корпуса {first + 1}–{end} из {len(PLAYER_HULLS)} · W/S или колесо",
                  (body.x, y_footer), DIM, self.small)
        h = PLAYER_HULLS[self.sel]
        full, cost = world.hull_offer(h.key)
        # Витрина сохраняет достаточную высоту независимо от размера каталога.
        top = y_footer + 26
        show = pygame.Rect(body.x - 8, top, 360, max(95, body.bottom - top))
        ui.panel(self.screen, show, "Витрина", ui.LINE, bg=(8, 18, 28, 255))
        self._showcase(Ship(h.key, (0, 0), -90), show, world.t)
        x, y = body.x + 390, body.y
        self.text(h.name, (x, y), ACCENT, self.big)
        self.text(h.series or h.role, (x, y + 30), DIM)
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

    def _showcase(self, ship, rect, t):
        from .gfx.camera import Camera
        from .gfx.ship_art import hull_length
        zoom = min(4.2, (rect.h - 50) / hull_length(ship.hull.key))
        cam = Camera(self.w, self.h, zoom)
        target = pygame.Vector2(rect.centerx, rect.centery + 10)
        cam.center = pygame.Vector2((self.w / 2 - target.x) / zoom, (self.h / 2 - target.y) / zoom)
        for w in ship.weapons:
            w.rel = 25 * pygame.math.Vector2(1, 0).rotate(t * 40 + w.index * 70).y
        clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-4, -4))
        self.art.draw(self.screen, cam, ship, "player", t)
        self.screen.set_clip(clip)

    def _hull_layout(self, ship, body, row_count):
        """Кликабельная схема наружных оружейных узлов.

        Внутренние системы остаются в списке, поскольку их физические
        позиции ещё не описаны в HullDef.
        """
        top = max(body.y + row_count * 22 + 70, body.y + 286)
        available = body.bottom - top - 6
        if available < 82:
            return
        rect = pygame.Rect(body.x - 8, top, 400, available)
        pygame.draw.rect(self.screen, (12, 25, 34), rect)
        pygame.draw.rect(self.screen, ui.LINE, rect, 1)
        self.text("СХЕМА КОРПУСА · НОС ВВЕРХ", (rect.x + 10, rect.y + 5), DIM, self.small)

        shape = ship.hull.shape
        max_x = max(abs(x) for x, _ in shape)
        max_y = max(abs(y) for _, y in shape)
        height = rect.h - 39
        if max_x <= 0 or max_y <= 0 or height <= 0:
            return
        scale = min((rect.w - 100) / (2 * max_y), height / (2 * max_x))
        cx, cy = rect.centerx, rect.y + 23 + height / 2

        def screen_pos(x, y):
            return (round(cx + y * scale), round(cy - x * scale))

        points = [screen_pos(x, y) for x, y in shape]
        pygame.draw.polygon(self.screen, (32, 49, 57), points)
        pygame.draw.polygon(self.screen, ui.LINE, points, 2)
        pygame.draw.line(self.screen, ui.FAINT, screen_pos(-max_x * 0.8, 0),
                         screen_pos(max_x * 0.8, 0), 1)

        for index, slot in enumerate(ship.hull.slots):
            if slot.category != "weapon":
                continue
            sx, sy = screen_pos(*slot.pos)
            selected = index == (self.slot if self.picker else self.sel)
            color = ACCENT if selected else ui.GOOD if ship.fit[index] else DIM
            radius = 11 if selected else 9
            pygame.draw.circle(self.screen, (10, 19, 24), (sx, sy), radius)
            pygame.draw.circle(self.screen, color, (sx, sy), radius, 2)
            marker = self.small.render(str(index + 1), True, UI)
            self.screen.blit(marker, marker.get_rect(center=(sx, sy)))
            self.zones.append((pygame.Rect(sx - 12, sy - 12, 24, 24), "slot", index))

        self.text("Цифры — номера оружейных слотов; узлы кликабельны",
                  (rect.x + 10, rect.bottom - 20), DIM, self.small)

    def _fitting(self, world, body):
        p = world.player
        rows = []
        for i, slot in enumerate(p.hull.slots):
            key = p.fit[i]
            name = MODULES[key].name if key else "— пусто —"
            label = f"{i + 1:02d}  {CATEGORY_NAME[slot.category]} {SIZE_NAME[slot.size]}: {name}"
            w = next((w for w in p.weapons if w.index == i), None)
            if w is not None:
                label += f"  [{GROUP_NAME[w.group]}]"
            rows.append((label, UI if key else DIM, ui.MODULE_ICON[slot.category] if not key
                         else ui.module_icon_kind(MODULES[key])))
        self._list(rows, body.x, body.y, 400, -1 if self.picker else self.sel, 22, zone="slot")
        if self.drag and self.drag["active"]:            # подсветка слотов при перетаскивании
            m = MODULES[self.drag["key"]]
            for i, slot in enumerate(p.hull.slots):
                ok = m.category == slot.category and m.size <= slot.size
                if ok:
                    pygame.draw.rect(self.screen, ui.GOOD, (body.x - 8, body.y + i * 22 - 4, 400, 22), 1)
        if self.picker:
            pygame.draw.rect(self.screen, (60, 90, 100), (body.x - 6, body.y + self.slot * 22 - 3, 400, 22), 1)
        else:
            self.text("G — группа огня выбранного орудия (ЛКМ / ПКМ / выкл.)",
                      (body.x, body.y + len(rows) * 22 + 12), DIM, self.small)
            ammo = ", ".join(f"{AMMO[k].name}: {v}" for k, v in world.captain.ammo_stock.items())
            self.text(f"Особые снаряды на борту — {ammo}", (body.x, body.y + len(rows) * 22 + 30), DIM,
                      self.small)

        self._hull_layout(p, body, len(rows))
        x = body.x + 420
        preview = None
        if self.picker:
            items = self.picker_items(world)
            prow = []
            for src, key in items:
                m = MODULES[key]
                tag = "склад" if src == "storage" else f"{m.price} КК"
                cur = " (стоит)" if p.fit[self.slot] == key and src == "shop" else ""
                prow.append((f"{m.name} [{SIZE_NAME[m.size]}] — {tag}{cur}", ACCENT if src == "storage" else UI,
                             ui.module_icon_kind(m)))
            self.text(f"Выбор модуля ({CATEGORY_NAME[p.hull.slots[self.slot].category]}) · клик или перетащите в слот",
                      (x, body.y - 2), DIM, self.small)
            visible = 12
            first = max(0, min(self.pick_sel - visible + 1, len(prow) - visible))      # прокрутка
            self._list(prow[first:first + visible], x, body.y + 18, 330, self.pick_sel - first, 22, zone="pick",
                       first=first)
            if first > 0:
                ui.text(self.screen, "▲", (x + 322, body.y + 4), DIM, 14)
            if first + visible < len(prow):
                ui.text(self.screen, f"ещё {len(prow) - first - visible} ▼", (x + 330, body.y + 18 + visible * 22),
                        DIM, 14, anchor="topright")
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
                 f"{int(MODULES[k].price * MODULE_RESALE)} КК", UI, ui.module_icon_kind(MODULES[k])) for k in storage]
        self._list(rows, body.x, body.y, 560, self.sel)
        key = storage[min(self.sel, len(storage) - 1)]
        x = body.x + 600
        self.text(MODULES[key].name, (x, body.y), ACCENT)
        for j, line in enumerate(module_stats(MODULES[key])):
            self.text(line, (x, body.y + 24 + j * 18), DIM, self.small)
