"""Экран порта: сервис, верфь, оснащение, склад.

Управление: A/D или стрелки — вкладки, W/S или стрелки — выбор, Enter — действие,
Backspace — снять модуль, G — группа огня, V — крупный чертёж, Esc — назад / выйти в море.
"""

import math

import pygame
from pygame.math import Vector2

from . import config as C
from .gfx import ui
from .engineering import engineering_notices
from .gfx.ship_art import ShipArt
from .hulls import PLAYER_HULLS
from .modules import AMMO, CATEGORY_NAME, MODULES, SIZE_NAME, WeaponDef, module_stats
from .ship import CARGO_MASS, SUBSYSTEM_NAME, SUBSYSTEMS, Ship
from .world import AMMO_PACK, MODULE_RESALE

UI, DIM, ACCENT, WARN = ui.TEXT, ui.DIM, ui.ACCENT, ui.WARN
TAB_ICON = ("utility", "hull", "gun", "cargo")

TABS = ("Сервис", "Верфь", "Оснащение", "Склад")
GROUP_NAME = {1: "ЛКМ", 2: "ПКМ", 0: "выкл."}
DENSE = 0.8          # «плотная Пелена» для сравнения характеристик



def schematic_layout_rect(body, row_count, focus=False):
    """Размер схемы в нормальном и в полноразмерном режимах fitting.

    Полноразмерный режим не зависит от числа установленных модулей.
    """
    top = body.y + 34 if focus else max(body.y + row_count * 22 + 86, body.y + 295)
    return pygame.Rect(body.x - 8, top, 400, max(0, body.bottom - top - 6))


def fitting_layout_regions(body):
    """Three deliberately unequal UX zones: navigation, ship, decision.

    Geometry is deterministic and can be tested without initializing a game.
    The ship takes the largest share; all three zones remain non-overlapping.
    """
    body = pygame.Rect(body)
    gutter = 8
    rail_w = max(162, round(body.w * 0.196))
    detail_w = max(282, round(body.w * 0.322))
    left = pygame.Rect(body.x - 8, body.y, rail_w, body.h - 6)
    center = pygame.Rect(left.right + gutter, body.y,
                         body.w - rail_w - detail_w - 2 * gutter,
                         body.h - 6)
    right = pygame.Rect(center.right + gutter, body.y,
                        detail_w, body.h - 6)
    return left, center, right


def schematic_side_slots(slots):
    """Разбить внутренние узлы на два борта и упорядочить от носа к корме.

    Сортировка по продольным координатам сохраняет читаемые, преимущественно
    параллельные линии вместо пересечений при произвольной нумерации слотов.
    Для старых корпусов без координат порядок остаётся по номеру слота.
    """
    systems = [(i, slot) for i, slot in enumerate(slots) if slot.category != "weapon"]
    columns = (systems[::2], systems[1::2])
    return tuple(sorted(col, key=lambda item: (
        item[1].diagram_pos is None,
        -(item[1].diagram_pos[0] if item[1].diagram_pos is not None else 0),
        item[0]))
                 for col in columns)


def weapon_arc_points(center, facing, arc, radius):
    """Точки сектора на схеме: 0° — нос вверх, +90° — правый борт.

    Сектор ограничен геометрией слота и реальным углом оружия. Чистая
    функция, которую можно отдельно проверять без инициализации pygame.
    """
    arc = max(0.0, min(360.0, float(arc)))
    steps = max(6, math.ceil(arc / 8.0))
    cx, cy = center
    points = [(round(cx), round(cy))]
    for i in range(steps + 1):
        angle = math.radians(facing - arc * 0.5 + arc * i / steps)
        points.append((round(cx + radius * math.sin(angle)),
                       round(cy - radius * math.cos(angle))))
    return points


def shipyard_layout_regions(body):
    """Catalogue / dominant ship viewport / purchase decision, non-overlapping."""
    body = pygame.Rect(body)
    gutter = 9
    catalogue_w = max(184, round(body.w * 0.205))
    offer_w = max(295, round(body.w * 0.308))
    catalogue = pygame.Rect(body.x - 8, body.y, catalogue_w, body.h - 6)
    hero = pygame.Rect(catalogue.right + gutter, body.y,
                       body.w - catalogue_w - offer_w - gutter * 2,
                       body.h - 6)
    offer = pygame.Rect(hero.right + gutter, body.y, offer_w, body.h - 6)
    return catalogue, hero, offer


def hull_purchase_issue(world, hull):
    """Match World.buy_hull guards without mutating the player or money."""
    if hull.key == world.player.hull.key:
        return "УЖЕ В ВАШЕМ ФЛОТЕ"
    if not hull.purchasable:
        return "КОРПУС НЕДОСТУПЕН"
    if world.captain.debt > 0:
        return "ПОГАСИТЕ ДОЛГ"
    _, cost = world.hull_offer(hull.key)
    if world.captain.credits < cost:
        return f"НЕ ХВАТАЕТ {cost - world.captain.credits} КК"
    if world.cargo_used > Ship(hull.key, (0, 0)).cargo_capacity:
        return "ГРУЗ НЕ ПОМЕСТИТСЯ"
    return None


def shipyard_window(total, selected, page_size=8):
    """Видимое окно каталога; selected всегда в нём при валидном индексе."""
    if total <= 0:
        return 0, 0
    visible = max(1, min(total, page_size))
    selected = max(0, min(total - 1, selected))
    first = max(0, min(total - visible, selected - visible // 2))
    return first, first + visible


def engineering_snapshot(ship, cargo=0.0, *, engine_pips=None):
    """Сухой проектный расчёт сборки; не меняет корабль и его ресурсы.

    Включает модули и внешний груз, но не затопление, повреждения, форсаж
    или обрастание. Для сравнения использует одинаковое распределение энергии.
    """
    total_mass = ship.hull.mass + ship.module_mass + cargo * CARGO_MASS
    design_mass = ship.hull.mass * 1.6
    mass_factor = min(1.1, (design_mass / total_mass) ** 0.5)
    pips = ship.pips["engines"] if engine_pips is None else engine_pips
    speed_pips = 0.85 + 0.075 * pips
    engine = ship.engine
    return {
        "hull_mass": ship.hull.mass,
        "module_mass": ship.module_mass,
        "cargo_mass": cargo * CARGO_MASS,
        "total_mass": total_mass,
        "design_mass": design_mass,
        "power_output": ship.output,
        "upkeep_clear": ship.upkeep(0.0),
        "balance_clear": ship.power_balance(0.0),
        "upkeep_veil": ship.upkeep(DENSE),
        "balance_veil": ship.power_balance(DENSE),
        "speed": (engine.top_speed * ship.hull.speed_mult * mass_factor * speed_pips
                  if engine else 0.0),
        "accel": (engine.thrust * 100 / total_mass if engine else 0.0),
        "turn": ship.hull.turn_rate * min(1.15, mass_factor) * ship.layout_turn_factor,
        "side_shift": abs(ship.side_balance) * 100.0,
        "spread": ship.mass_spread * 100.0,
        "layout_turn_pct": ship.layout_turn_factor * 100.0,
    }


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
        ("Поворот", ship.hull.turn_rate * min(1.15, ship.mass_factor()) *
         ship.layout_turn_factor, True),
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
        self.blueprint_focus = False  # V: расширенная инженерная схема
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
        if key == pygame.K_v and TABS[self.tab] == "Оснащение":
            self.blueprint_focus = not self.blueprint_focus
            self.sound("ui_click")
            return None
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
                    if z[0] != "row" or TABS[self.tab] != "Верфь":
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
                # In the shipyard a catalogue click is selection only.
                # Purchase happens on the explicit button (or Enter).
                if TABS[self.tab] != "Верфь":
                    self._activate(world)
                else:
                    self.sound("ui_click")
            elif kind == "slot":
                # Clicking a ship node selects equipment; it never buys it.
                # Purchase/install is an explicit CTA (or keyboard Enter).
                old_slot = self.slot
                was_picker = self.picker
                self.slot, self.sel, self.picker = idx, idx, True
                if not was_picker or idx != old_slot:
                    self.pick_sel = 0
                self.sound("ui_click")
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
                # A candidate click only previews. It must not spend money.
                # Use the install button, Enter, or an intentional drag/drop.
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
        if name == "purchase_hull" and TABS[self.tab] == "Верфь":
            if PLAYER_HULLS and hull_purchase_issue(world, PLAYER_HULLS[self.sel]) is None:
                self._activate(world)
            return None
        if name == "blueprint" and TABS[self.tab] == "Оснащение":
            self.blueprint_focus = not self.blueprint_focus
            self.sound("ui_click")
            return None
        if name == "choose" and TABS[self.tab] == "Оснащение":
            self.slot = self.sel
            self.pick_sel = 0
            self.picker = True
            self.sound("ui_click")
            return None
        if name == "install" and TABS[self.tab] == "Оснащение" and self.picker:
            self._activate(world)
            return None
        if name == "remove" and TABS[self.tab] == "Оснащение":
            idx = self.slot if self.picker else self.sel
            err = world.uninstall(idx)
            self.say(err or "Модуль снят на склад.", ui.BAD if err else ACCENT)
            if not err:
                self.picker = False
            return None
        if name == "back" and TABS[self.tab] == "Оснащение":
            self.picker = False
            self.sound("ui_click")
            return None
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
        ui.panel(self.screen, rect, None, ACCENT, bg=(*ui.PANEL_RGB, 245))
        # Fixed top/bottom plates, under existing controls and labels.
        pygame.draw.rect(self.screen, ui.FAINT, (rect.x + 1, rect.y + 1, rect.w - 2, 60))
        pygame.draw.line(self.screen, ui.LINE, (rect.x + 17, rect.y + 60),
                         (rect.right - 17, rect.y + 60), 1)

        ui.text(self.screen, "ПОРТ БЕЖЕНЦЕВ", (rect.x + 22, rect.y + 15), UI, 30, True)
        ui.text(self.screen, "НЕЙТРАЛЬНЫЙ ТЕХНИЧЕСКИЙ УЗЕЛ  /  ГИЛЬДИЯ «ГОРИЗОНТ»",
                (rect.x + 24, rect.y + 44), DIM, 15)
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
                pygame.draw.rect(self.screen, ui.LINE, tr, 1)
                pygame.draw.line(self.screen, ACCENT, tr.bottomleft, tr.bottomright, 3)
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
        if enabled:
            self.zones.append((rect, "button", name))
        hot = rect.collidepoint(self.mouse)
        if hot and enabled:
            pygame.draw.rect(self.screen, ui.SEL_BG, rect)
        pygame.draw.rect(self.screen, color if enabled else ui.LINE, rect, 2 if hot and enabled else 1)
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
        candidate = Ship(p.hull.key, (0, 0), fit=fit)
        new = ship_summary(candidate, world.cargo_used)
        lines = []
        issue = world.install_problem(self.slot, key, from_storage=(src == "storage"))
        if issue:
            lines.append((f"НЕЛЬЗЯ УСТАНОВИТЬ: {issue}", ui.BAD))
        for notice in engineering_notices(candidate, world.cargo_used, DENSE):
            lines.append((f"! {notice.text}", WARN))
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
        ui.panel(self.screen, r, None, ACCENT, bg=(*ui.PANEL_RGB, 247))
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

    def _engineering_panel(self, world, body, preview=None):
        """Инженерный баланс, без закрытия списка модулей и сравнения fitting."""
        panel = pygame.Rect(body.right - 279, body.y, 274, body.h - 6)
        ui.panel(self.screen, panel, accent=ui.LINE,
                 bg=(*ui.PANEL_RGB, 244))
        x, y = panel.x + 11, panel.y + 10
        self.text("ИНЖЕНЕРНЫЙ БАЛАНС", (x, y), UI, self.small)
        pygame.draw.line(self.screen, ACCENT, (x, y + 19),
                         (panel.right - 11, y + 19), 1)
        cur = engineering_snapshot(world.player, world.cargo_used)
        nxt = (engineering_snapshot(preview, world.cargo_used,
                                    engine_pips=world.player.pips["engines"])
               if preview is not None else None)

        # Differences are shown inline next to each metric when preview exists.
        selected = preview if preview is not None else world.player
        notices = engineering_notices(selected, world.cargo_used, DENSE)
        if notices:
            summary = notices[0].short + (f" (+{len(notices) - 1})" if len(notices) > 1 else "")
            self.text(summary, (x, y + 22), WARN, self.small)
        elif preview is None:
            self.text("Проектные характеристики", (x, y + 22), DIM, self.small)

        def section(title, yy):
            pygame.draw.line(self.screen, ui.LINE, (x, yy + 17),
                             (panel.right - 11, yy + 17))
            self.text(title, (x, yy), UI, self.small)

        def metric(label, key, yy, *, higher=True, signed=False, decimals=0):
            value = cur[key]
            changed = nxt is not None and abs(nxt[key] - value) > 0.05
            color = ui.GOOD if changed and ((nxt[key] > value) == higher) else (
                ui.BAD if changed else UI)
            self.text(label, (x, yy), DIM, self.small)
            fmt = f"+.{decimals}f" if signed else f".{decimals}f"
            if changed:
                self.text(f"{format(value, fmt)} > {format(nxt[key], fmt)}",
                          (panel.right - 11, yy), color, self.small, right=True)
            else:
                self.text(format(value, fmt), (panel.right - 11, yy),
                          color, self.small, right=True)

        def meter(yy, amount, capacity, label, *, bad=False):
            self.text(label, (x, yy - 2), DIM, self.small)
            bar = pygame.Rect(x, yy + 16, panel.w - 24, 8)
            pygame.draw.rect(self.screen, ui.FAINT, bar)
            if capacity > 0:
                ratio = max(0.0, min(1.0, amount / capacity))
                filled = pygame.Rect(bar.x, bar.y, round(bar.w * ratio), bar.h)
                if filled.w:
                    pygame.draw.rect(self.screen, ui.BAD if bad else ACCENT, filled)
            pygame.draw.rect(self.screen, ui.LINE, bar, 1)

        section("МАССА · сухое состояние", y + 43)
        metric("Корпус", "hull_mass", y + 65)
        metric("Модули", "module_mass", y + 85, higher=False)
        metric("Груз (масса)", "cargo_mass", y + 105, higher=False)
        metric("Итого", "total_mass", y + 125, higher=False)
        meter(y + 147, nxt["total_mass"] if nxt else cur["total_mass"],
              cur["design_mass"] * 1.35,
              f"Проектный ориентир {cur['design_mass']:.0f}",
              bad=(nxt["total_mass"] if nxt else cur["total_mass"]) > cur["design_mass"])
        metric("Бортовой перекос %", "side_shift", y + 179, higher=False, decimals=1)

        section("ЭНЕРГИЯ · ед/с", y + 207)
        metric("Реактор", "power_output", y + 230)
        metric("Расход", "upkeep_clear", y + 250, higher=False)
        metric("Баланс", "balance_clear", y + 270, signed=True)
        metric("В Пелене", "balance_veil", y + 290, signed=True)
        if (nxt or cur)["balance_veil"] < 0:
            self.text("! Риск энергодефицита в Пелене", (x, y + 312),
                      WARN, self.small)

        section("ХОДОВЫЕ · без повреждений", y + 335)
        metric("Скорость", "speed", y + 357)
        metric("Разгон", "accel", y + 378)
        metric("Поворот", "turn", y + 399)
        metric("Компоновка %", "layout_turn_pct", y + 420, decimals=1)

    def _stats(self, world, x, y, preview=None, *, columns=1):
        """Ship comparison; optional 2-column density for the wide shipyard.

        Other uses (narrow service pane) retain their old layout.
        """
        cargo = world.cargo_used
        cur = ship_summary(world.player, cargo)
        new = ship_summary(preview, cargo) if preview else None
        title = world.player.hull.name
        if preview is not None and preview.hull is not world.player.hull:
            title += f"  >  {preview.hull.name}"
        self.text(title, (x, y), ACCENT)
        y += 26
        columns = 2 if columns == 2 else 1
        rows = (len(cur) + columns - 1) // columns
        step = 23 if columns == 2 else 21
        column_width = 305
        for i, (label, val, higher) in enumerate(cur):
            col_index = i // rows
            row_index = i % rows
            xx, yy = x + col_index * column_width, y + row_index * step
            self.text(label, (xx, yy), DIM, self.small)
            self.text(f"{val:.0f}", (xx + 200, yy), UI, self.small, right=True)
            if new:
                nv = new[i][1]
                if abs(nv - val) > 0.5:
                    better = (nv > val) == higher
                    self.text(f"> {nv:.0f}", (xx + 212, yy),
                              ui.GOOD if better else ui.BAD, self.small)
        y += rows * step + 12
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
        """UX 2.0: see the ship first, compare, then explicitly purchase.

        The catalogue no longer buys on click. All values come from the
        existing hull_offer/ship_summary and buy_hull game rules.
        """
        if not PLAYER_HULLS:
            self.text("Нет доступных корпусов", (body.x, body.y), DIM)
            return
        self.sel = max(0, min(self.sel, len(PLAYER_HULLS) - 1))
        rail, hero, offer = shipyard_layout_regions(body)
        ui.panel(self.screen, rail, accent=ui.LINE, bg=(*ui.PANEL_RGB, 250))
        ui.panel(self.screen, hero, accent=ui.LINE, bg=(*ui.PANEL_RGB, 250))
        ui.panel(self.screen, offer, accent=ui.LINE, bg=(*ui.PANEL_RGB, 250))

        self.text("КАТАЛОГ КОРПУСОВ", (rail.x + 12, rail.y + 12), UI, self.small)
        self.text("ВЫБЕРИТЕ КОРАБЛЬ", (rail.x + 12, rail.y + 34), DIM, self.small)
        page_size = max(1, min(8, (rail.h - 102) // 40))
        first, end = shipyard_window(len(PLAYER_HULLS), self.sel, page_size)
        for row_num, i in enumerate(range(first, end)):
            hull = PLAYER_HULLS[i]
            _, cost = world.hull_offer(hull.key)
            own = hull.key == world.player.hull.key
            selected = i == self.sel
            row = pygame.Rect(rail.x + 7, rail.y + 65 + row_num * 40,
                              rail.w - 14, 37)
            if selected:
                ui.selection(self.screen, row)
            elif row.collidepoint(self.mouse):
                pygame.draw.rect(self.screen, ui.LINE, row, 1)
            label = hull.name
            while self.small.size(label)[0] > row.w - 16 and len(label) > 4:
                label = label[:-2] + "…"
            self.text(label, (row.x + 7, row.y + 2),
                      ACCENT if selected else UI, self.small)
            price = "ВАШ КОРАБЛЬ" if own else f"{cost:,} КК"
            self.text(price, (row.x + 7, row.y + 19),
                      ui.GOOD if own else DIM, self.small)
            self.zones.append((row, "row", i))
        self.text(f"{first + 1}–{end} / {len(PLAYER_HULLS)}  ·  W/S",
                  (rail.x + 11, rail.bottom - 24), DIM, self.small)

        hull = PLAYER_HULLS[self.sel]
        full, cost = world.hull_offer(hull.key)
        preview = Ship(hull.key, (0, 0), -90)
        self.text("КОРПУС / ВИД СВЕРХУ", (hero.x + 17, hero.y + 13), UI, self.small)
        self.text(hull.name.upper(), (hero.x + 17, hero.y + 39), ACCENT, self.font)
        pygame.draw.line(self.screen, ui.LINE,
                         (hero.x + 15, hero.y + 70), (hero.right - 15, hero.y + 70))
        mid_x = hero.centerx
        for k in (-2, -1, 0, 1, 2):
            xx = mid_x + k * 56
            pygame.draw.line(self.screen, ui.FAINT, (xx, hero.y + 88),
                             (xx, hero.bottom - 55))
        stage = pygame.Rect(hero.x + 12, hero.y + 84, hero.w - 24, hero.h - 142)
        self._showcase(preview, stage, world.t)
        pygame.draw.line(self.screen, ui.LINE,
                         (hero.x + 15, hero.bottom - 52),
                         (hero.right - 15, hero.bottom - 52))
        self.text(f"{len([s for s in hull.slots if s.category == 'weapon'])} ОРУЖЕЙНЫХ УЗЛА   ·   "
                  f"{len(hull.slots)} МОДУЛЬНЫХ СЛОТОВ",
                  (hero.centerx, hero.bottom - 43), DIM, self.small, center=True)
        self.text("ИГРОВАЯ МОДЕЛЬ  ·  НОС ВВЕРХ",
                  (hero.centerx, hero.bottom - 22), DIM, self.small, center=True)

        # The right panel answers "is this ship better for me?" rather
        # than exposing the entire 13-row spreadsheet.
        self.text("ПАСПОРТ КОРАБЛЯ", (offer.x + 15, offer.y + 12), UI, self.small)
        series = hull.series or hull.role
        self.text(series[:39], (offer.x + 15, offer.y + 39), DIM, self.small)
        self._shipyard_blurb(hull.desc, offer.x + 15, offer.y + 72,
                            offer.w - 30, 4)
        self.text("СРАВНЕНИЕ С ВАШИМ", (offer.x + 15, offer.y + 159),
                  UI, self.small)
        a = {name: (value, better) for name, value, better in
             ship_summary(world.player, world.cargo_used)}
        b = {name: value for name, value, _ in ship_summary(preview, world.cargo_used)}
        for i, name in enumerate(("Корпус", "Броня", "Щит", "Скорость", "Урон/с")):
            value, higher = a[name]
            change = b[name]
            improved = (change > value) == higher
            same = abs(change - value) < 0.51
            color = DIM if same else ui.GOOD if improved else ui.BAD
            yy = offer.y + 187 + i * 23
            self.text(name.upper(), (offer.x + 15, yy), DIM, self.small)
            result = f"{value:.0f} → {change:.0f}" if not same else f"{change:.0f} ="
            self.text(result, (offer.right - 16, yy),
                      color, self.small, right=True)
        pygame.draw.line(self.screen, ui.LINE,
                         (offer.x + 15, offer.y + 309),
                         (offer.right - 15, offer.y + 309))
        owned = hull.key == world.player.hull.key
        self.text("ТЕКУЩИЙ КОРПУС" if owned else "К ДОПЛАТЕ С УЧЁТОМ ОБМЕНА",
                  (offer.x + 15, offer.y + 321), DIM, self.small)
        self.text("УЖЕ ВО ФЛОТЕ" if owned else f"{cost:,} КК",
                  (offer.x + 15, offer.y + 342), UI, self.big)
        issue = hull_purchase_issue(world, hull)
        if issue is not None:
            # Owned hulls already say "УЖЕ ВО ФЛОТЕ" in the price field.
            if not owned:
                self.text(issue, (offer.x + 15, offer.bottom - 79),
                          WARN, self.small)
        else:
            self.text("ГОТОВ К ПОКУПКЕ", (offer.x + 15, offer.bottom - 79),
                      ui.GOOD, self.small)
        self._btn((offer.x + 14, offer.bottom - 55, offer.w - 28, 39),
                  "КУПИТЬ КОРПУС  ·  ENTER" if issue is None else "ПОКУПКА НЕДОСТУПНА",
                  "purchase_hull", ACCENT if issue is None else ui.LINE,
                  enabled=issue is None)

    def _shipyard_blurb(self, text, x, y, width, max_lines=4):
        """Short readable description; never overlaps the comparison metrics."""
        words = text.split()
        lines, current = [], ""
        for word in words:
            proposed = f"{current} {word}".strip()
            if current and self.small.size(proposed)[0] > width:
                lines.append(current)
                current = word
            else:
                current = proposed
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            final = lines[-1]
            while final and self.small.size(final + "…")[0] > width:
                final = final[:-1]
            lines[-1] = final + "…"
        for i, line in enumerate(lines):
            self.text(line, (x, y + i * 19), DIM, self.small)

    def _showcase(self, ship, rect, t):
        from .gfx.camera import Camera
        from .gfx.ship_art import hull_length
        zoom = min(5.0, (rect.h - 16) / hull_length(ship.hull.key))
        cam = Camera(self.w, self.h, zoom)
        target = pygame.Vector2(rect.centerx, rect.centery + 10)
        cam.center = pygame.Vector2((self.w / 2 - target.x) / zoom, (self.h / 2 - target.y) / zoom)
        for w in ship.weapons:
            w.rel = 25 * pygame.math.Vector2(1, 0).rotate(t * 40 + w.index * 70).y
        clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-4, -4))
        self.art.draw(self.screen, cam, ship, "player", t)
        self.screen.set_clip(clip)

    def _hull_layout(self, ship, body, row_count, preview_fit=None, focus=False,
                     rect_override=None):
        """Чертёж корпуса: оружие на палубе, внутренние системы — по бортам.

        Внутренние узлы имеют отдельные координаты diagram_pos, которые
        задаются проектом корпуса. Бортовые ярлыки являются кликабельными,
        чтобы на узких корпусах значки не перекрывали друг друга.
        """
        rect = (pygame.Rect(rect_override) if rect_override is not None
                else schematic_layout_rect(body, row_count, focus=focus))
        if rect.h < 105:
            return
        ui.panel(self.screen, rect, accent=ui.LINE,
                 bg=(*ui.PANEL_RGB, 247))
        self.text("ИНЖЕНЕРНЫЙ ЧЕРТЁЖ · НОС ВВЕРХ" if focus else
                  "СХЕМА КОРПУСА · НОС ВВЕРХ", (rect.x + 10, rect.y + 5), UI, self.small)

        shape = ship.hull.shape
        max_x = max(abs(x) for x, _ in shape)
        max_y = max(abs(y) for _, y in shape)
        height = rect.h - 43
        if max_x <= 0 or max_y <= 0 or height <= 0:
            return
        # Бортовые таблички занимают две боковые полосы по ~100px.
        scale = min((rect.w - 234) / (2 * max_y), height / (2 * max_x))
        cx, cy = rect.centerx, rect.y + 23 + height / 2

        def screen_pos(x, y):
            return (round(cx + y * scale), round(cy - x * scale))

        points = [screen_pos(x, y) for x, y in shape]
        pygame.draw.polygon(self.screen, ui.SEL_BG, points)
        pygame.draw.polygon(self.screen, ui.LINE, points, 2)
        pygame.draw.line(self.screen, ui.FAINT, screen_pos(-max_x * 0.8, 0),
                         screen_pos(max_x * 0.8, 0), 1)

        current_fit = ship.fit if preview_fit is None else preview_fit
        selected_index = self.slot if self.picker else self.sel
        has_selection = 0 <= selected_index < len(ship.hull.slots)
        if has_selection:
            mount = ship.hull.slots[selected_index]
            if mount.category == "weapon":
                key = current_fit[selected_index]
                module = MODULES[key] if key else None
                arc = min(mount.arc, module.arc) if isinstance(module, WeaponDef) else mount.arc
                sx, sy = screen_pos(*mount.pos)
                radius = max(23, min(43, height * 0.28))
                verts = weapon_arc_points((sx - rect.x, sy - rect.y),
                                          mount.facing, arc, radius)
                overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.polygon(overlay, (78, 170, 166, 56), verts)
                pygame.draw.lines(overlay, (115, 216, 202, 170), False, verts, 2)
                old_clip = self.screen.get_clip()
                self.screen.set_clip(rect.inflate(-2, -2))
                self.screen.blit(overlay, rect.topleft)
                self.screen.set_clip(old_clip)

        # Подписи внутренних систем формируют два читабельных ряда с
        # направляющими к их собственным проектным точкам внутри корпуса.
        side_sets = schematic_side_slots(ship.hull.slots)
        abbreviations = {
            "engine": "ДВ", "reactor": "РЕ", "shield": "ЩТ",
            "armor": "БР", "sensor": "СН", "utility": "УТ",
        }
        longest = max((len(s) for s in side_sets), default=0)
        if focus:
            row_step = min(62, max(26, (rect.h - 110) // max(1, longest - 1)))
        else:
            row_step = min(26, max(20, (rect.h - 53) // max(1, longest)))
        for side, set_of_slots in enumerate(side_sets):
            card_x = rect.x + 9 if side == 0 else rect.right - 104
            for row_index, (index, slot) in enumerate(set_of_slots):
                y = rect.y + (46 if focus else 27) + row_index * row_step
                card = pygame.Rect(card_x, y, 95, 21)
                selected = index == selected_index
                filled = current_fit[index] is not None
                color = ACCENT if selected else ui.GOOD if filled else DIM
                pygame.draw.rect(self.screen, ui.SEL_BG if selected else ui.PANEL_RGB, card)
                pygame.draw.rect(self.screen, color if selected else ui.LINE, card,
                                 2 if selected else 1)
                label = f"{index + 1:02d} {abbreviations.get(slot.category, '??')} {SIZE_NAME[slot.size]}"
                self.text(label, (card.x + 7, card.y + 2), color, self.small)
                self.zones.append((card, "slot", index))
                if slot.diagram_pos is not None:
                    sx, sy = screen_pos(*slot.diagram_pos)
                    endpoint = (card.right, card.centery) if side == 0 else (card.left, card.centery)
                    pygame.draw.line(self.screen, color if selected else ui.FAINT,
                                     endpoint, (sx, sy), 2 if selected else 1)
                    pygame.draw.circle(self.screen, color, (sx, sy), 4 if selected else 2)

        # Оружейные узлы всегда рисуются поверх внутренних линий.
        for index, slot in enumerate(ship.hull.slots):
            if slot.category != "weapon":
                continue
            sx, sy = screen_pos(*slot.pos)
            selected = index == selected_index
            color = ACCENT if selected else ui.GOOD if current_fit[index] else DIM
            radius = 10 if selected else 8
            pygame.draw.circle(self.screen, (10, 19, 24), (sx, sy), radius)
            pygame.draw.circle(self.screen, color, (sx, sy), radius, 2)
            marker = self.small.render(str(index + 1), True, UI)
            self.screen.blit(marker, marker.get_rect(center=(sx, sy)))
            self.zones.append((pygame.Rect(sx - 11, sy - 11, 22, 22), "slot", index))

        if has_selection:
            slot = ship.hull.slots[selected_index]
            chosen = current_fit[selected_index]
            status = "занят" if chosen is not None else "пуст"
            detail = f"Узел {selected_index + 1:02d} · {CATEGORY_NAME[slot.category]} {SIZE_NAME[slot.size]} · {status}"
            if slot.category == "weapon":
                module = MODULES[chosen] if chosen else None
                arc = min(slot.arc, module.arc) if isinstance(module, WeaponDef) else slot.arc
                detail += f" · сектор {arc:g}°"
            self.text(detail, (rect.x + 9, rect.bottom - 19), ACCENT, self.small)
        else:
            self.text("Выберите узел на чертеже или в списке", (rect.x + 9, rect.bottom - 19),
                      DIM, self.small)

    def _fitting_hero(self, world, rect, fit=None):
        """Dominant, actual ship art with click-through schematic callouts.

        Hitboxes are purposefully separate from the image pixels: narrow
        hulls still provide 30px targets, and overlapping internal modules
        become labelled side callouts rather than unusable tiny hotspots.
        """
        from .gfx.camera import Camera
        from .gfx.ship_art import hull_length

        p = world.player
        ui.panel(self.screen, rect, accent=ui.LINE,
                 bg=(*ui.PANEL_RGB, 250))
        self.text(p.hull.name, (rect.x + 17, rect.y + 12), UI, self.big)
        self.text("КОНСТРУКЦИЯ  /  НОС ВВЕРХ", (rect.x + 18, rect.y + 47), DIM, self.small)
        self._btn((rect.right - 226, rect.y + 13, 210, 29),
                  "V  ИНЖЕНЕРНЫЙ ВИД", "blueprint", DIM)
        pygame.draw.line(self.screen, ui.LINE, (rect.x + 14, rect.y + 76),
                         (rect.right - 14, rect.y + 76))
        cx, cy = rect.centerx, rect.y + round(rect.h * 0.54)
        for dx in (-114, -57, 0, 57, 114):
            col = ui.LINE if dx == 0 else ui.FAINT
            pygame.draw.line(self.screen, col, (cx + dx, rect.y + 92),
                             (cx + dx, rect.bottom - 33))
        for dy in (-104, -52, 0, 52, 104):
            pygame.draw.line(self.screen, ui.FAINT, (rect.x + 133, cy + dy),
                             (rect.right - 133, cy + dy))
        zoom = min(5.8, (rect.h - 139) / hull_length(p.hull.key))
        cam = Camera(self.w, self.h, zoom=zoom)
        cam.center = Vector2((self.w / 2 - cx) / zoom, (self.h / 2 - cy) / zoom)
        # Projected build only; never change the actual ship/cargo.
        shown = Ship(p.hull.key, (0, 0), -90, fit=fit if fit is not None else list(p.fit))
        old_clip = self.screen.get_clip()
        self.screen.set_clip(rect.inflate(-8, -66))
        self.art.draw(self.screen, cam, shown, "player", world.t)
        self.screen.set_clip(old_clip)

        selected = self.slot if self.picker else self.sel
        current_fit = fit if fit is not None else p.fit
        def at(pos):
            x, y = pos
            return round(cx + y * zoom), round(cy - x * zoom)

        # Internal nodes: full-size labelled callouts with leader lines.
        for side, columns in enumerate(schematic_side_slots(p.hull.slots)):
            place_x = rect.x + 9 if side == 0 else rect.right - 115
            count = len(columns)
            if not count:
                continue
            first_y = rect.y + 101
            span = rect.h - 166
            for index_in_side, (idx, slot) in enumerate(columns):
                yy = first_y + (index_in_side * span // max(1, count - 1))
                card = pygame.Rect(place_x, yy - 13, 107, 29)
                active = idx == selected
                filled = current_fit[idx] is not None
                col = ACCENT if active else ui.GOOD if filled else DIM
                if slot.diagram_pos is not None:
                    node = at(slot.diagram_pos)
                    endpoint = (card.right, card.centery) if side == 0 else (card.x, card.centery)
                    pygame.draw.line(self.screen, col if active else ui.LINE,
                                     endpoint, node, 2 if active else 1)
                    pygame.draw.circle(self.screen, col, node, 4 if active else 2)
                pygame.draw.rect(self.screen, ui.SEL_BG if active else ui.PANEL_RGB, card)
                pygame.draw.rect(self.screen, col if active else ui.LINE,
                                 card, 2 if active else 1)
                name = CATEGORY_NAME[slot.category].upper()
                label = f"{idx + 1:02d} {name}"
                if self.small.size(label)[0] > 96:
                    label = f"{idx + 1:02d} {name[:7]}"
                self.text(label, (card.x + 6, card.y + 6), col, self.small)
                self.zones.append((card, "slot", idx))
        # Weapon positions remain clickable directly on the actual hull.
        for idx, slot in enumerate(p.hull.slots):
            if slot.category != "weapon":
                continue
            sx, sy = at(slot.pos)
            active = idx == selected
            col = ACCENT if active else ui.GOOD if current_fit[idx] else DIM
            pygame.draw.circle(self.screen, ui.PANEL_RGB, (sx, sy), 15)
            pygame.draw.circle(self.screen, col, (sx, sy), 15, 3 if active else 2)
            marker = self.small.render(str(idx + 1), True, UI)
            self.screen.blit(marker, marker.get_rect(center=(sx, sy)))
            self.zones.append((pygame.Rect(sx - 15, sy - 15, 30, 30), "slot", idx))
        self.text("НАЖМИ УЗЕЛ, ЧТОБЫ ВЫБРАТЬ ОБОРУДОВАНИЕ",
                  (rect.centerx, rect.bottom - 28), DIM, self.small, center=True)

    def _fitting_impact(self, world, preview, rect, y):
        """Show the four immediate consequences, not a diagnostics wall."""
        before = engineering_snapshot(world.player, world.cargo_used)
        after = engineering_snapshot(preview, world.cargo_used,
                                     engine_pips=world.player.pips["engines"])
        rows = (("ЭНЕРГИЯ", "balance_clear", True),
                ("В ПЕЛЕНЕ", "balance_veil", True),
                ("МАССА", "total_mass", False),
                ("СКОРОСТЬ", "speed", True))
        self.text("ЧТО ИЗМЕНИТСЯ", (rect.x + 17, y), UI, self.small)
        for i, (label, key, higher) in enumerate(rows):
            a, b = before[key], after[key]
            changed = abs(a - b) > 0.05
            positive = (b > a) == higher
            color = (ui.GOOD if positive else ui.BAD) if changed else DIM
            yy = y + 24 + i * 19
            self.text(label, (rect.x + 17, yy), DIM, self.small)
            value = f"{a:.0f} → {b:.0f}" if changed else f"{a:.0f} ="
            self.text(value, (rect.right - 17, yy), color, self.small, right=True)

    def _fitting(self, world, body):
        """User-first fitting: nodes -> real ship -> selected action.

        Engineering detail moves to V; initial screen only shows a focused
        decision, with an explicit installation action and preview.
        """
        p = world.player
        slots = p.hull.slots
        if not slots:
            self.text("У этого корпуса нет узлов оснащения.", (body.x, body.y), DIM)
            return
        self.sel = max(0, min(self.sel, len(slots) - 1))
        self.slot = max(0, min(self.slot, len(slots) - 1))
        if self.blueprint_focus:
            self._btn((body.x - 8, body.y - 2, 245, 28),
                      "V  ВЕРНУТЬСЯ К СБОРКЕ", "blueprint", ACCENT)
            diag = pygame.Rect(body.x - 8, body.y + 36, body.w - 306,
                               body.h - 44)
            self._hull_layout(p, body, len(slots), focus=True,
                              rect_override=diag)
            self._engineering_panel(world, body)
            return

        left, center, right = fitting_layout_regions(body)
        ui.panel(self.screen, left, accent=ui.LINE, bg=(*ui.PANEL_RGB, 250))
        ui.panel(self.screen, right, accent=ui.LINE, bg=(*ui.PANEL_RGB, 250))
        self.text("УЗЛЫ КОРАБЛЯ", (left.x + 13, left.y + 12), UI, self.small)
        self.text(f"{len(slots)} СЛОТОВ  ·  W/S", (left.x + 13, left.y + 35),
                  DIM, self.small)
        active_index = self.slot if self.picker else self.sel
        row_h = 30
        visible = max(1, (left.h - 126) // row_h)
        first = max(0, min(len(slots) - visible, active_index - visible // 2))
        for idx in range(first, min(len(slots), first + visible)):
            slot = slots[idx]
            key = p.fit[idx]
            yy = left.y + 70 + (idx - first) * row_h
            row = pygame.Rect(left.x + 7, yy - 3, left.w - 14, 29)
            selected = idx == active_index
            if selected:
                ui.selection(self.screen, row)
            elif row.collidepoint(self.mouse):
                pygame.draw.rect(self.screen, ui.LINE, row, 1)
            icon_color = ACCENT if selected else ui.GOOD if key else DIM
            ui.icon(self.screen, ui.MODULE_ICON[slot.category],
                    (row.x + 15, row.centery), 15, icon_color)
            text = f"{idx + 1:02d} {CATEGORY_NAME[slot.category]}"
            limit = row.w - 55
            while self.small.size(text)[0] > limit and len(text) > 4:
                text = text[:-1]
            self.text(text, (row.x + 29, row.y + 6), UI if selected else DIM,
                      self.small)
            pygame.draw.circle(self.screen, ui.GOOD if key else ui.LINE,
                               (row.right - 12, row.centery), 4)
            self.zones.append((row, "slot", idx))
        if len(slots) > visible:
            self.text(f"{first + 1}–{min(first + visible, len(slots))} / {len(slots)}",
                      (left.x + 13, left.bottom - 88), DIM, self.small)
        pygame.draw.line(self.screen, ui.LINE, (left.x + 12, left.bottom - 63),
                         (left.right - 12, left.bottom - 63))
        self.text("КЛИК — ВЫБРАТЬ", (left.x + 13, left.bottom - 55),
                  DIM, self.small)
        self.text("ПКМ — СНЯТЬ", (left.x + 13, left.bottom - 34),
                  DIM, self.small)

        chosen = None
        issue = None
        items = self.picker_items(world) if self.picker else []
        if self.picker and items:
            self.pick_sel = max(0, min(self.pick_sel, len(items) - 1))
            src, key = items[self.pick_sel]
            chosen = MODULES[key]
            issue = world.install_problem(self.slot, key,
                                          from_storage=(src == "storage"))
        candidate = None
        if chosen is not None:
            fit = list(p.fit)
            fit[self.slot] = chosen.key
            candidate = Ship(p.hull.key, (0, 0), fit=fit)
        self._fitting_hero(world, center, candidate.fit if candidate is not None else None)

        selected_slot = slots[active_index]
        self.text(f"УЗЕЛ {active_index + 1:02d} · {CATEGORY_NAME[selected_slot.category].upper()}",
                  (right.x + 16, right.y + 12), UI, self.small)
        self.text(f"РАЗМЕР {SIZE_NAME[selected_slot.size]}  /  "
                  f"{'ВЫБОР ОБОРУДОВАНИЯ' if self.picker else 'ТЕКУЩЕЕ ОСНАЩЕНИЕ'}",
                  (right.x + 16, right.y + 36), DIM, self.small)
        pygame.draw.line(self.screen, ui.LINE, (right.x + 14, right.y + 61),
                         (right.right - 14, right.y + 61))

        if self.picker:
            if items:
                lines = []
                for src, key in items:
                    module = MODULES[key]
                    label = f"{module.name} · {'СКЛАД' if src == 'storage' else str(module.price) + ' КК'}"
                    problem = world.install_problem(self.slot, key, from_storage=(src == "storage"))
                    lines.append((label + ("  ×" if problem else ""),
                                  ui.BAD if problem else ACCENT if src == "storage" else UI,
                                  ui.module_icon_kind(module)))
                visible_items = 6
                begin = max(0, min(self.pick_sel - visible_items + 1,
                                   len(lines) - visible_items))
                self._list(lines[begin:begin + visible_items],
                           right.x + 17, right.y + 80, right.w - 28,
                           self.pick_sel - begin, 30, zone="pick", first=begin)
                if len(lines) > visible_items:
                    self.text(f"{self.pick_sel + 1} / {len(lines)}  ·  W/S",
                              (right.right - 18, right.y + 258), DIM, self.small, right=True)
                self._fitting_impact(world, candidate, right, right.y + 282)
                notices = engineering_notices(candidate, world.cargo_used, DENSE)
                note = notices[0].short if notices else None
                yy = right.bottom - 73
                if issue:
                    self.text("× УСТАНОВКА НЕДОСТУПНА", (right.x + 16, yy),
                              ui.BAD, self.small)
                    # Full explanation remains available in the item's tooltip.
                elif note:
                    self.text("! " + note[:40], (right.x + 16, yy), WARN, self.small)
                else:
                    self.text("✓ МОЖНО УСТАНОВИТЬ", (right.x + 16, yy), ui.GOOD, self.small)
                self._btn((right.x + 15, right.bottom - 48, right.w - 30, 35),
                          "УСТАНОВИТЬ  ·  ENTER", "install",
                          ACCENT if not issue else ui.LINE, enabled=not issue)
            else:
                self.text("Для этого узла нет доступных модулей.",
                          (right.x + 16, right.y + 89), WARN, self.small)
            self._btn((right.right - 43, right.y + 7, 27, 26),
                      "×", "back", DIM)
        else:
            key = p.fit[self.sel]
            if key:
                module = MODULES[key]
                self.text(module.name, (right.x + 16, right.y + 86), ACCENT)
                self.wrapped(module.desc, (right.x + 16, right.y + 124),
                             right.w - 34, DIM, self.small)
                for j, line in enumerate(module_stats(module)[:5]):
                    self.text(line, (right.x + 16, right.y + 217 + j * 24),
                              UI, self.small)
            else:
                self.text("ПУСТОЙ СЛОТ", (right.x + 16, right.y + 92), WARN)
                self.text("Выберите совместимое оборудование.",
                          (right.x + 16, right.y + 124), DIM, self.small)
            self._btn((right.x + 15, right.bottom - 48, right.w - 30, 35),
                      "ВЫБРАТЬ МОДУЛЬ  ·  ENTER", "choose", ACCENT)
            if key:
                self._btn((right.x + 15, right.bottom - 88, right.w - 30, 31),
                          "СНЯТЬ В СКЛАД  ·  BACKSPACE", "remove", DIM)

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
