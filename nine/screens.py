"""Экраны поверх игры: главное меню, пауза, настройки, гибель, карта, кодекс.

Экраны лежат стеком в Game.stack. Верхний получает ввод; пока стек не пуст,
мир стоит на паузе (кроме экранов с `pauses = False`).
"""

import math

import numpy as np
import pygame
from pygame.math import Vector2

from . import config as C
from .codex import CATEGORIES, all_keys, entry
from .gfx import ui
from .settings import ACTIONS, default_keys


def ease(k):
    k = max(0.0, min(1.0, k))
    return 1 - (1 - k) ** 3


_dim_cache = {}


def dim(screen, alpha, color=(2, 4, 8)):
    key = (screen.get_size(), alpha // 4, color)
    surf = _dim_cache.get(key)
    if surf is None:
        surf = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        surf.fill((*color, alpha // 4 * 4))
        if len(_dim_cache) > 80:
            _dim_cache.clear()
        _dim_cache[key] = surf
    screen.blit(surf, (0, 0))


class Screen:
    pauses = True
    OPEN_TIME = 0.18

    def __init__(self, game):
        self.game = game
        self.screen = game.screen
        self.w, self.h = self.screen.get_size()
        self.age = 0.0

    @property
    def k(self):
        """Прогресс анимации открытия 0 → 1."""
        return ease(self.age / self.OPEN_TIME)

    def slide(self, rect, dy=26):
        r = pygame.Rect(rect)
        r.y += int((1 - self.k) * dy)
        return r

    def close(self):
        self.game.pop(self)

    def handle(self, e):
        pass

    def update(self, dt):
        self.age += dt

    def draw(self):
        pass

    def sound(self, name):
        self.game.audio.ui(name)


class Menu:
    """Вертикальный список кнопок: мышь (наведение, клик) и клавиатура (W/S, Enter)."""

    def __init__(self, items, sound):
        self.items = items          # [(подпись, действие)] ; действие None — неактивно
        self.sel = 0
        self.rects = []
        self.sound = sound

    def handle(self, e):
        n = len(self.items)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % n
                self.sound("ui_hover")
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % n
                self.sound("ui_hover")
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self._activate(self.sel)
        elif e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos) and i != self.sel:
                    self.sel = i
                    self.sound("ui_hover")
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    return self._activate(i)
        return None

    def _activate(self, i):
        action = self.items[i][1]
        if action is None:
            self.sound("ui_error")
            return None
        self.sound("ui_click")
        action()
        return True

    def draw(self, screen, x, y, w, size=24, gap=36, align="left"):
        self.rects = []
        for i, (label, action) in enumerate(self.items):
            r = pygame.Rect(x, y + i * gap, w, gap - 6)
            self.rects.append(r)
            sel = i == self.sel
            if sel:
                ui.selection(screen, r)
            col = ui.TEXT if sel else ui.DIM
            if action is None:
                col = ui.FAINT
            anchor, px = ("midleft", r.x + 16) if align == "left" else ("center", r.centerx)
            ui.text(screen, label, (px, r.centery), col, size, sel, anchor=anchor)


# --- главное меню и пауза ---------------------------------------------------------------

class MainMenu(Screen):
    OPEN_TIME = 0.6

    def __init__(self, game, can_resume=False):
        super().__init__(game)
        self.pauses = can_resume        # при запуске мир за меню живёт (корабль стоит у порта)
        items = []
        from .save import has_save
        if can_resume:
            items.append(("Продолжить", self.close))
        elif has_save():
            items.append(("Продолжить (сохранение)", self.load))
        items += [("Новая игра", self.new_game), ("Кодекс", lambda: game.push(CodexScreen(game))),
                  ("Настройки", lambda: game.push(SettingsScreen(game))), ("Выход", game.quit)]
        self.menu = Menu(items, self.sound)
        self.can_resume = can_resume

    def load(self):
        if self.game.load_game():
            self.close()
        else:
            self.sound("ui_error")

    def new_game(self):
        if self.can_resume:
            self.game.new_game()
        self.close()

    def handle(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE and self.can_resume:
            self.close()
            return
        self.menu.handle(e)

    def draw(self):
        s = self.screen
        dim(s, int(150 * self.k))
        # слева — тёмная полоса под меню
        band = pygame.Surface((440, self.h), pygame.SRCALPHA)
        for x in range(440):
            band.fill((3, 6, 10, int(230 * (1 - x / 440) ** 0.7 * self.k)), (x, 0, 1, self.h))
        s.blit(band, (0, 0))
        x = 64 - int((1 - self.k) * 40)
        ui.text(s, "ДЕВЯТКА", (x, 110), ui.TEXT, 88, True)
        ui.text(s, "KH-9  ·  ПЕЛЕНА  ·  ПРОТОТИП", (x + 4, 186), ui.ACCENT, 20, True)
        pygame.draw.line(s, ui.LINE, (x + 4, 214), (x + 330, 214))
        self.menu.draw(s, x, 250, 300, 26, 42)
        ui.text(s, "W/S или мышь — выбор   Enter — подтвердить", (x + 4, self.h - 40), ui.DIM, 15)


class PauseMenu(Screen):
    def __init__(self, game):
        super().__init__(game)
        self.menu = Menu([
            ("Продолжить", self.close),
            ("Карта", lambda: game.push(MapScreen(game))),
            ("Журнал капитана", lambda: game.push(CaptainsJournal(game))),
            ("Кодекс", lambda: game.push(CodexScreen(game))),
            ("Настройки", lambda: game.push(SettingsScreen(game))),
            ("Справка по управлению", self.help),
            ("Главное меню", lambda: game.push(MainMenu(game, can_resume=True))),
            ("Выйти из игры", game.quit),
        ], self.sound)

    def help(self):
        self.game.hud.show_help = True
        self.close()

    def handle(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.close()
            return
        self.menu.handle(e)

    def draw(self):
        dim(self.screen, int(150 * self.k))
        w, h = 360, 40 + 42 * len(self.menu.items)
        r = self.slide(((self.w - w) // 2, (self.h - h) // 2, w, h))
        ui.panel(self.screen, r, "Пауза")
        self.menu.draw(self.screen, r.x + 12, r.y + 34, w - 24, 22, 42)
        ui.text(self.screen, f"Время в море {int(self.game.world.t // 60)} мин  ·  потоплено {self.game.world.captain.kills}",
                (self.w // 2, r.bottom + 14), ui.DIM, 15, anchor="midtop")


# --- настройки -------------------------------------------------------------------------

TABS = ("Звук", "Графика", "Интерфейс", "Управление")
ROWS = {
    "Звук": [("slider", "Общая громкость", "master"), ("slider", "Эффекты", "sfx"),
             ("slider", "Окружение и гул Пелены", "ambient"), ("slider", "Интерфейс", "ui")],
    "Графика": [("toggle", "Высокое качество (F10)", "high_quality"),
                ("toggle", "Искажения в плотной Пелене", "distortion"),
                ("slider", "Тряска камеры", "shake"), ("toggle", "Счётчик FPS", "show_fps")],
    "Интерфейс": [("slider", "Непрозрачность панелей", "hud_opacity"), ("toggle", "Крупный шрифт", "large_font"),
                  ("toggle", "Палитра для дальтоников", "colorblind"), ("toggle", "Числа урона", "damage_numbers"),
                  ("toggle", "Подсказки", "hints"), ("toggle", "Миникарта", "show_minimap"),
                  ("toggle", "Журнал", "show_log")],
    "Управление": [("key", name, key) for key, name, _ in ACTIONS] + [("reset", "Сбросить по умолчанию", None)],
}


class SettingsScreen(Screen):
    ROW_H = 26
    VISIBLE = 14

    def __init__(self, game):
        super().__init__(game)
        self.tab = 0
        self.sel = 0
        self.scroll = 0
        self.waiting = None         # действие, ждущее новую клавишу
        self.row_rects = []
        self.tab_rects = []
        self.slider_rects = {}

    @property
    def rows(self):
        return ROWS[TABS[self.tab]]

    def _changed(self):
        self.game.apply_settings()
        self.game.settings.save()

    def _adjust(self, row, delta):
        kind, _, attr = row
        s = self.game.settings
        if kind == "slider":
            setattr(s, attr, round(max(0.0, min(1.0, getattr(s, attr) + delta)), 2))
            self.sound("ui_hover")
            self._changed()

    def _activate(self, row):
        kind, _, attr = row
        s = self.game.settings
        if kind == "toggle":
            setattr(s, attr, not getattr(s, attr))
        elif kind == "key":
            self.waiting = attr
        elif kind == "reset":
            s.keys = default_keys()
        elif kind == "slider":
            return
        self.sound("ui_click")
        self._changed()

    def handle(self, e):
        if self.waiting:
            if e.type == pygame.KEYDOWN:
                if e.key != pygame.K_ESCAPE:
                    self.game.settings.bind(self.waiting, e.key)
                    self._changed()
                    self.sound("ui_buy")
                self.waiting = None
            return
        rows = self.rows
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.close()
            elif e.key in (pygame.K_TAB, pygame.K_e, pygame.K_q, pygame.K_PAGEDOWN, pygame.K_PAGEUP):
                back = e.key in (pygame.K_q, pygame.K_PAGEUP) or (e.mod & pygame.KMOD_SHIFT)
                self._set_tab((self.tab + (-1 if back else 1)) % len(TABS))
            elif e.key in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % len(rows)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % len(rows)
            elif e.key in (pygame.K_LEFT, pygame.K_a):
                self._adjust(rows[self.sel], -0.1)
            elif e.key in (pygame.K_RIGHT, pygame.K_d):
                self._adjust(rows[self.sel], 0.1)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._activate(rows[self.sel])
            self._scroll_to_sel()
        elif e.type == pygame.MOUSEMOTION:
            for i, r in self.row_rects:
                if r.collidepoint(e.pos) and i != self.sel:
                    self.sel = i
                    self.sound("ui_hover")
            if e.buttons[0]:
                self._drag(e.pos)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.tab_rects):
                if r.collidepoint(e.pos):
                    self._set_tab(i)
                    self.sound("ui_click")
                    return
            if self._drag(e.pos):
                return
            for i, r in self.row_rects:
                if r.collidepoint(e.pos):
                    self.sel = i
                    self._activate(rows[i])
        elif e.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(max(0, len(rows) - self.VISIBLE), self.scroll - e.y))

    def _drag(self, pos):
        for attr, r in self.slider_rects.items():
            if r.inflate(0, 10).collidepoint(pos):
                v = round(max(0.0, min(1.0, (pos[0] - r.x) / r.w)) * 20) / 20
                if getattr(self.game.settings, attr) != v:
                    setattr(self.game.settings, attr, v)
                    self._changed()
                return True
        return False

    def _set_tab(self, i):
        self.tab, self.sel, self.scroll = i, 0, 0

    def _scroll_to_sel(self):
        if self.sel < self.scroll:
            self.scroll = self.sel
        elif self.sel >= self.scroll + self.VISIBLE:
            self.scroll = self.sel - self.VISIBLE + 1

    def draw(self):
        s, st = self.screen, self.game.settings
        dim(s, int(170 * self.k))
        w, h = 640, 480
        r = self.slide(((self.w - w) // 2, (self.h - h) // 2, w, h))
        ui.panel(s, r, "Настройки")
        # вкладки
        self.tab_rects = []
        x = r.x + 14
        for i, name in enumerate(TABS):
            tw = ui.text_width(name, 19, True) + 24
            tr = pygame.Rect(x, r.y + 30, tw, 26)
            self.tab_rects.append(tr)
            if i == self.tab:
                pygame.draw.rect(s, ui.SEL_BG, tr)
                pygame.draw.line(s, ui.ACCENT, tr.bottomleft, tr.bottomright, 2)
            ui.text(s, name, tr.center, ui.TEXT if i == self.tab else ui.DIM, 19, i == self.tab, anchor="center")
            x = tr.right + 4
        pygame.draw.line(s, ui.LINE, (r.x + 12, r.y + 58), (r.right - 12, r.y + 58))

        self.row_rects, self.slider_rects = [], {}
        rows = self.rows
        y = r.y + 68
        for i in range(self.scroll, min(len(rows), self.scroll + self.VISIBLE)):
            kind, label, attr = rows[i]
            rr = pygame.Rect(r.x + 12, y, w - 24, self.ROW_H - 2)
            self.row_rects.append((i, rr))
            sel = i == self.sel
            if sel:
                ui.selection(s, rr)
            ui.text(s, label, (rr.x + 14, rr.centery), ui.TEXT if sel else ui.DIM, 18, anchor="midleft")
            vx = rr.right - 12
            if kind == "slider":
                v = getattr(st, attr)
                br = pygame.Rect(vx - 250, rr.centery - 4, 200, 8)
                self.slider_rects[attr] = br
                ui.bar(s, br, v, ui.ACCENT if sel else ui.DIM, segments=20)
                ui.text(s, f"{int(v * 100)}%", (vx, rr.centery), ui.TEXT, 17, anchor="midright")
            elif kind == "toggle":
                on = getattr(st, attr)
                ui.chip(s, "ВКЛ" if on else "ВЫКЛ", (vx, rr.centery - 7), ui.ACCENT if on else ui.DIM, 15,
                        fill=(16, 50, 50) if on else None, anchor="topright")
            elif kind == "key":
                if self.waiting == attr:
                    blink = int(self.age * 3) % 2
                    ui.chip(s, "нажмите клавишу…", (vx, rr.centery - 7), ui.WARN if blink else ui.DIM, 15,
                            anchor="topright")
                else:
                    ui.chip(s, st.key_label(attr), (vx, rr.centery - 7), ui.TEXT, 15, anchor="topright")
            y += self.ROW_H
        if len(rows) > self.VISIBLE:
            frac = self.scroll / (len(rows) - self.VISIBLE)
            track = pygame.Rect(r.right - 8, r.y + 68, 3, self.VISIBLE * self.ROW_H)
            pygame.draw.rect(s, ui.FAINT, track)
            th = track.h * self.VISIBLE / len(rows)
            pygame.draw.rect(s, ui.ACCENT, (track.x, track.y + (track.h - th) * frac, 3, th))
        hint = {"slider": "A/D или мышь — изменить", "toggle": "Enter или клик — переключить",
                "key": "Enter или клик — назначить (Esc — отмена); занятая клавиша поменяется местами",
                "reset": "Enter — вернуть раскладку по умолчанию"}[rows[self.sel][0]]
        ui.text(s, hint, (r.x + 16, r.bottom - 26), ui.DIM, 15)
        ui.text(s, "Tab — вкладка   Esc — назад (сохраняется сразу)", (r.right - 16, r.bottom - 26), ui.DIM, 15,
                anchor="topright")


# --- гибель ---------------------------------------------------------------------------

class DeathScreen(Screen):
    OPEN_TIME = 0.8

    def __init__(self, game, loss):
        super().__init__(game)
        self.loss = loss
        self.menu = Menu([("Продолжить", self.close)], self.sound)

    def handle(self, e):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.close()
            return
        if self.age > 0.6:
            self.menu.handle(e)

    def draw(self):
        s, loss = self.screen, self.loss
        dim(s, int(170 * self.k), (30, 4, 6))
        w, h = 520, 300
        r = self.slide(((self.w - w) // 2, (self.h - h) // 2, w, h), 40)
        ui.panel(s, r, None, ui.BAD)
        t = loss["t"]
        if loss["kind"] == "ship":
            ui.text(s, "КОРАБЛЬ ПОТЕРЯН", (r.centerx, r.y + 22), ui.BAD, 42, True, anchor="midtop")
            ui.text(s, loss["hull"], (r.centerx, r.y + 62), ui.DIM, 18, anchor="midtop")
            rows = [("Груз потерян", f"~{loss['cargo']} КК", ui.BAD),
                    ("Осталось в обломках", f"~{loss['salvage']} КК", ui.WARN),
                    ("Страховка (в порту)", f"+{loss['insurance']} КК", ui.GOOD),
                    ("Потоплено рейдеров", str(loss["kills"]), ui.TEXT),
                    ("Время в море", f"{int(t // 60)} мин {int(t % 60)} с", ui.TEXT)]
            note = "Капсула отстрелена. Доберитесь до порта — F. Обломки отмечены на карте (M)."
        else:
            ui.text(s, "КАПСУЛА УНИЧТОЖЕНА", (r.centerx, r.y + 22), ui.BAD, 42, True, anchor="midtop")
            ui.text(s, "Спасатели вытащили вас и доставили в порт", (r.centerx, r.y + 62), ui.DIM, 18,
                    anchor="midtop")
            rows = [("Груз потерян", f"~{int(loss['cargo'])} КК", ui.BAD),
                    ("Долг спасателям", f"+{loss['debt']} КК", ui.BAD),
                    ("Травма", "перезарядка медленнее до лечения", ui.WARN)]
            note = "Долг гасится в порту. Пока он есть, новые модули не продают."
        y = r.y + 96
        for label, val, col in rows:
            ui.text(s, label, (r.x + 40, y), ui.DIM, 18)
            ui.text(s, val, (r.right - 40, y), col, 18, True, anchor="topright")
            y += 24
        for i, line in enumerate(ui.wrap(note, w - 60, 15)):
            ui.text(s, line, (r.centerx, r.bottom - 76 + i * 16), ui.DIM, 15, anchor="midtop")
        if self.age > 0.6:
            self.menu.draw(s, r.centerx - 100, r.bottom - 42, 200, 20, 36, align="center")


# --- карта -----------------------------------------------------------------------------

MAP_LAYERS = (("marks", "Отметки"), ("contacts", "Контакты радара"), ("events", "Явления"),
              ("route", "Путевая точка"), ("grid", "Сетка"))
MARK_COLOR = {"port": ui.ACCENT, "ruins": (200, 110, 90), "eye": (230, 220, 255), "wreck": ui.WARN}


def fog_surface(memory, size):
    """Туман неразведанного: чем слабее память о клетке, тем плотнее тёмная пелена."""
    h, w = memory.shape
    small = pygame.Surface((w, h), pygame.SRCALPHA)
    small.fill((6, 8, 16, 0))
    alpha = pygame.surfarray.pixels_alpha(small)
    alpha[:, :] = (235 * (1 - np.clip(memory, 0, 1)) ** 1.3).astype(np.uint8).T
    del alpha
    return pygame.transform.smoothscale(small, (size, size))


class MapScreen(Screen):
    SIZE = 600

    def __init__(self, game):
        super().__init__(game)
        n = self.SIZE
        self.bg = pygame.transform.smoothscale(game.hud.minimap_bg, (n, n))
        self.fog = fog_surface(game.world.memory, n)
        self.layers = {k: True for k, _ in MAP_LAYERS}
        self.origin = Vector2(40, (self.h - n) // 2 + 8)
        self.legend_rects = []
        self.hover = None

    def w2m(self, pos):
        return self.origin + Vector2(pos[0] / C.WORLD_W * self.SIZE, pos[1] / C.WORLD_H * self.SIZE)

    def m2w(self, p):
        q = (Vector2(p) - self.origin) / self.SIZE
        return Vector2(q.x * C.WORLD_W, q.y * C.WORLD_H)

    def map_rect(self):
        return pygame.Rect(self.origin, (self.SIZE, self.SIZE))

    def handle(self, e):
        world = self.game.world
        keys = self.game.settings
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, keys.key("map")):
                self.close()
            elif pygame.K_1 <= e.key <= pygame.K_5:
                k = MAP_LAYERS[e.key - pygame.K_1][0]
                self.layers[k] = not self.layers[k]
                self.sound("ui_click")
            elif e.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                world.waypoint = None
        elif e.type == pygame.MOUSEMOTION:
            self.hover = e.pos if self.map_rect().collidepoint(e.pos) else None
        elif e.type == pygame.MOUSEBUTTONDOWN:
            for k, r in self.legend_rects:
                if r.collidepoint(e.pos):
                    self.layers[k] = not self.layers[k]
                    self.sound("ui_click")
                    return
            if self.map_rect().collidepoint(e.pos):
                if e.button == 1:
                    world.waypoint = self.m2w(e.pos)
                    world.say("Путевая точка установлена.")
                    self.sound("ui_buy")
                elif e.button == 3:
                    world.waypoint = None
                    self.sound("ui_click")

    def update(self, dt):
        super().update(dt)
        if int(self.age * 4) != int((self.age - dt) * 4):
            self.fog = fog_surface(self.game.world.memory, self.SIZE)

    def draw(self):
        s, world = self.screen, self.game.world
        dim(s, int(200 * self.k))
        n = self.SIZE
        o = self.origin
        frame = ui.panel(s, (o.x - 8, o.y - 30, n + 16, n + 38), "Карта сектора")
        s.blit(self.bg, o)
        s.set_clip(pygame.Rect(o, (n, n)))
        if self.layers["grid"]:
            for i in range(9):
                x = o.x + i * n / 8
                pygame.draw.line(s, (40, 58, 70), (x, o.y), (x, o.y + n))
                pygame.draw.line(s, (40, 58, 70), (o.x, o.y + i * n / 8), (o.x + n, o.y + i * n / 8))
            for i in range(8):
                ui.text(s, "ABCDEFGH"[i], (o.x + (i + 0.5) * n / 8, o.y + 4), ui.DIM, 14, anchor="midtop")
                ui.text(s, str(i + 1), (o.x + 4, o.y + (i + 0.5) * n / 8), ui.DIM, 14, anchor="midleft")
        s.blit(self.fog, o)
        p = world.player
        eye = self.w2m(world.eye)
        if "eye" in world.codex:
            for r_, col in ((C.EYE_BELT_R, (90, 60, 130)), (C.EYE_WALL_R, (150, 90, 200))):
                pygame.draw.circle(s, col, eye, r_ / C.WORLD_W * n, 1)
        dead = world.veil.in_dead_zone(p.pos)
        if self.layers["events"] and not dead:
            for ev in world.events.active:
                if not (ev.covers(p.pos) or world.perceives(ev.pos) or world.on_radar(ev.pos)):
                    continue
                c = self.w2m(ev.pos)
                col = ev.data.color
                if ev.data.shape == "band":
                    d = ev.direction * (ev.data.radius / C.WORLD_W * n)
                    pygame.draw.line(s, col, c - d, c + d, max(2, int(ev.data.width * 2 / C.WORLD_W * n)))
                else:
                    pygame.draw.circle(s, col, c, ev.data.radius / C.WORLD_W * n, 1)
                ui.text(s, ev.data.name, c + Vector2(0, -8), col, 15, anchor="midbottom")
        if self.layers["marks"]:
            for m in world.marks.values():
                c = self.w2m(m["pos"])
                col = tuple(int(v * (0.3 + 0.7 * m["clarity"])) for v in MARK_COLOR.get(m["kind"], ui.TEXT))
                _mark_icon(s, m["kind"], c, col)
                label = m["label"] if m["clarity"] > 0.45 else "???"
                ui.text(s, label, c + Vector2(9, -2), col, 15, anchor="midleft")
        scout = world.contracts.get("scout")
        if scout and scout["status"] == "active" and not scout["explored"]:
            target = self.w2m(world.scout_position())
            radius = max(4, round(world.SCOUT_RADIUS * self.SIZE / C.WORLD_W))
            pygame.draw.circle(s, (110, 220, 205), target, radius, 2)
            ui.text(s, "РАЗВЕДКА", target + Vector2(0, -radius - 5),
                    (150, 240, 220), 15, anchor="midbottom")
        escort_task = world.contracts.get("escort")
        if escort_task and escort_task["status"] == "active" and not escort_task["arrived"]:
            trader = world.trade_traffic.snapshot(world.t)[escort_task["convoy"]]
            target = self.w2m(trader.pos)
            pygame.draw.circle(s, (145, 230, 150), target, 8, 2)
            ui.text(s, "КОНВОЙ", target + Vector2(0, -10),
                    (145, 230, 150), 15, anchor="midbottom")
        if self.layers["contacts"] and not dead:
            for trader in world.trade_traffic.snapshot(world.t):
                if world.perceives(trader.pos) or world.on_radar(trader.pos):
                    pygame.draw.circle(s, (95, 212, 190), self.w2m(trader.pos), 3)
            for escort in world.trade_traffic.escort_snapshot(world.t):
                if world.perceives(escort.pos) or world.on_radar(escort.pos):
                    pygame.draw.circle(s, (145, 180, 255), self.w2m(escort.pos), 3, 1)
            for pi in world.pirates:
                if world.on_radar(pi.ship.pos) or world.perceives(pi.ship.pos):
                    pygame.draw.circle(s, ui.BAD, self.w2m(pi.ship.pos), 3)
            for ph in world.phantoms:
                pygame.draw.circle(s, ui.BAD, self.w2m(ph["pos"]), 3)       # на радаре фантом неотличим
        pp = self.w2m(p.pos)
        pygame.draw.circle(s, (40, 110, 100), pp, max(2, world.radar_range() / C.WORLD_W * n), 1)
        pygame.draw.circle(s, (60, 80, 90), pp, max(2, world.visual_range() / C.WORLD_W * n), 1)
        if self.layers["route"] and world.waypoint is not None:
            wp = self.w2m(world.waypoint)
            _dashed(s, (230, 210, 120), pp, wp)
            pygame.draw.polygon(s, (240, 220, 120), [wp + Vector2(0, -7), wp + Vector2(6, 0), wp + Vector2(0, 7),
                                                     wp + Vector2(-6, 0)], 2)
            ui.text(s, f"{int(p.pos.distance_to(world.waypoint))} м", wp + Vector2(10, 6), (240, 220, 120), 15)
        tri = [pp + Vector2(8, 0).rotate(p.angle), pp + Vector2(-5, 5).rotate(p.angle), pp + Vector2(-5, -5).rotate(p.angle)]
        pygame.draw.polygon(s, (255, 255, 255), tri)
        if self.hover:
            hp = Vector2(self.hover)
            pygame.draw.line(s, ui.LINE, (hp.x, o.y), (hp.x, o.y + n))
            pygame.draw.line(s, ui.LINE, (o.x, hp.y), (o.x + n, hp.y))
        s.set_clip(None)
        if dead:
            ui.text(s, "НЕТ СВЯЗИ — только память", (o.x + n / 2, o.y + n / 2), ui.BAD, 24, True, anchor="center")

        # легенда и сводка справа
        lx = frame.right + 20
        box = self.slide((lx, frame.y, self.w - lx - 24, frame.h))
        ui.panel(s, box, "Легенда")
        y = box.y + 32
        self.legend_rects = []
        for i, (k, name) in enumerate(MAP_LAYERS):
            rr = pygame.Rect(box.x + 10, y, box.w - 20, 24)
            self.legend_rects.append((k, rr))
            on = self.layers[k]
            if self.hover is None and rr.collidepoint(pygame.mouse.get_pos()):
                ui.selection(s, rr)
            ui.chip(s, str(i + 1), (rr.x + 6, rr.y + 5), ui.DIM, 14)
            ui.text(s, name, (rr.x + 34, rr.centery), ui.TEXT if on else ui.FAINT, 18, anchor="midleft")
            ui.chip(s, "ВКЛ" if on else "ВЫКЛ", (rr.right - 6, rr.y + 5), ui.ACCENT if on else ui.DIM, 14,
                    anchor="topright")
            y += 26
        y += 10
        for kind, name in (("port", "Порт"), ("ruins", "Руины Эры I"), ("eye", "Око"), ("wreck", "Обломки")):
            _mark_icon(s, kind, (box.x + 22, y + 8), MARK_COLOR[kind])
            ui.text(s, name, (box.x + 38, y), ui.DIM, 16)
            y += 20
        pygame.draw.circle(s, ui.BAD, (box.x + 22, y + 8), 3)
        ui.text(s, "Контакт радара (или фантом)", (box.x + 38, y), ui.DIM, 16)
        y += 20
        pygame.draw.polygon(s, (240, 220, 120), [(box.x + 22, y + 2), (box.x + 28, y + 8), (box.x + 22, y + 14),
                                                 (box.x + 16, y + 8)], 2)
        ui.text(s, "Путевая точка", (box.x + 38, y), ui.DIM, 16)
        y += 30
        explored = float((world.memory > 0.5).mean())
        ui.text(s, f"Разведано: {int(explored * 100)}% сектора", (box.x + 14, y), ui.TEXT, 17)
        y += 22
        d = world.density_at(p.pos)
        if d > C.ZONE_DENSE:
            for line in ui.wrap("Пелена стирает память: разведанное выцветает, отметки тускнеют.", box.w - 28, 16):
                ui.text(s, line, (box.x + 14, y), (190, 150, 255), 16)
                y += 18
        if self.hover:
            wpos = self.m2w(self.hover)
            cell = world.memory[min(world.memory.shape[0] - 1, int(wpos.y // (C.WORLD_H / world.memory.shape[0]))),
                                min(world.memory.shape[1] - 1, int(wpos.x // (C.WORLD_W / world.memory.shape[1])))]
            state = "разведано" if cell > 0.6 else "смутно" if cell > 0.15 else "не разведано"
            sq = f"{'ABCDEFGH'[min(7, int(wpos.x / C.WORLD_W * 8))]}{min(8, int(wpos.y / C.WORLD_H * 8) + 1)}"
            ui.text(s, f"{sq}  ·  {int(p.pos.distance_to(wpos))} м  ·  {state}", (box.x + 14, box.bottom - 70),
                    ui.TEXT, 16)
        for i, line in enumerate(("ЛКМ — путевая точка   ПКМ — убрать", "1–5 — слои   M / Esc — закрыть")):
            ui.text(s, line, (box.x + 14, box.bottom - 46 + i * 18), ui.DIM, 15)


def _mark_icon(s, kind, c, col):
    c = Vector2(c)
    if kind == "port":
        pygame.draw.circle(s, col, c, 6, 2)
        pygame.draw.circle(s, col, c, 2)
    elif kind == "ruins":
        pygame.draw.rect(s, col, (c.x - 4, c.y - 4, 8, 8), 1)
        pygame.draw.line(s, col, c + Vector2(-4, 4), c + Vector2(4, -4))
    elif kind == "eye":
        pygame.draw.ellipse(s, col, (c.x - 7, c.y - 4, 14, 8), 1)
        pygame.draw.circle(s, col, c, 2)
    else:
        pygame.draw.line(s, col, c + Vector2(-5, -5), c + Vector2(5, 5), 2)
        pygame.draw.line(s, col, c + Vector2(-5, 5), c + Vector2(5, -5), 2)


def _dashed(s, col, a, b, dash=8):
    a, b = Vector2(a), Vector2(b)
    d = b - a
    n = int(d.length() / dash)
    if n == 0:
        return
    step = d / n
    for i in range(0, n, 2):
        pygame.draw.line(s, col, a + step * i, a + step * (i + 1))


# --- журнал капитана: текущие и завершённые контракты ----------------------------

def journal_entries(world):
    """Read-only mission snapshot. No claim/reward side effects."""
    entries = []
    for key, state in world.contracts.items():
        if key not in world.CONTRACTS or not isinstance(state, dict):
            continue
        name, target, reward = world.contract_terms(key)
        done = state.get("status") == "done"
        if key == "salt":
            current = min(target, int(world.captain.cargo.get("salt", 0)))
            objective = "Доставить соль-металл"
        elif key == "pirates":
            current = min(target, max(0, world.captain.kills - state.get("start_kills", 0)))
            objective = "Уничтожить рейдеров"
        elif key == "scout":
            current = int(bool(state.get("explored")))
            objective = "Посетить отмеченную область Пелены"
        elif key == "escort":
            current = int(bool(state.get("arrived")))
            origin = "Порта беженцев" if state["origin"] == "port" else "Платформы"
            objective = f"Сопроводить конвой №{state['convoy'] + 1} от {origin}"
        elif key == "urgent":
            current = min(target, int(world.captain.cargo.get(state["kind"], 0)))
            destination = "Порт беженцев" if state["destination"] == "port" else "Торговая платформа"
            objective = f"Доставить {state['kind']} в {destination}"
        elif key == "master":
            current = min(target, int(world.captain.cargo.get("condensate", 0)))
            destination = "Порт беженцев" if state["hub"] == "port" else "Торговая платформа"
            objective = f"Мастер: доставить конденсат в {destination}"
        elif key == "guild":
            current = min(target, int(world.captain.cargo.get("salt", 0)))
            destination = "Порт беженцев" if state["hub"] == "port" else "Торговая платформа"
            objective = f"Гильдия: доставить соль-металл в {destination}"
        else:
            continue
        status = "ЗАВЕРШЁН" if done else (
            "МОЖНО СДАТЬ В ПОРТ" if current >= target
            and (key != "urgent" or world.active_port == state["destination"])
            and (key not in ("guild", "master") or world.active_port == state["hub"])
            else "В РАБОТЕ"
        )
        entries.append((key, name, objective, current, target, reward, status))
    return entries


class CaptainsJournal(Screen):
    """Mission journal is available at sea (J) and from the pause menu."""

    def handle(self, e):
        if e.type == pygame.KEYDOWN and e.key in (
                pygame.K_ESCAPE, self.game.settings.key("journal")):
            self.close()

    def draw(self):
        s = self.screen
        dim(s, int(200 * self.k))
        w, h = min(820, self.w - 40), min(550, self.h - 40)
        r = self.slide(((self.w - w) // 2, (self.h - h) // 2, w, h))
        ui.panel(s, r, "Журнал капитана")
        entries = journal_entries(self.game.world)
        active = sum(1 for e in entries if e[6] != "ЗАВЕРШЁН")
        completed = len(entries) - active
        ui.text(s, f"Активных: {active}    Завершено: {completed}",
                (r.x + 22, r.y + 42), ui.DIM, 18)
        if not entries:
            ui.text(s, "Контрактов пока нет. Возьмите задание в порту.",
                    r.center, ui.DIM, 20, anchor="center")
        for i, (_, name, objective, current, target, reward, status) in enumerate(entries):
            row_gap = min(90, max(54, (r.h - 170) // max(1, len(entries))))
            y = r.y + 72 + i * row_gap
            if y + row_gap - 4 > r.bottom - 85:
                break
            row = pygame.Rect(r.x + 18, y, r.w - 36, row_gap - 4)
            pygame.draw.rect(s, ui.FAINT, row, 1)
            ui.text(s, name, (row.x + 14, row.y + 5), ui.TEXT, 19, True)
            ui.text(s, status, (row.right - 12, row.y + 12),
                    ui.ACCENT if status != "В РАБОТЕ" else ui.DIM,
                    16, anchor="topright")
            ui.text(s, objective, (row.x + 14, row.y + 28), ui.DIM, 16)
            progress = "Выполнено" if status == "ЗАВЕРШЁН" else f"{current}/{target}"
            ui.text(s, f"Прогресс: {progress}    Награда: {reward} КК",
                    (row.x + 14, row.y + 48), ui.TEXT, 15)
        rep = self.game.world.guild_reputation
        ui.text(s, f"Гильдия: Порт {rep['port']}/100 · Платформа {rep['platform']}/100",
                (r.x + 22, r.bottom - 82), ui.DIM, 15)
        ui.text(s, self.game.world.market_bulletin(),
                (r.x + 22, r.bottom - 63), ui.ACCENT, 15)
        ui.text(s, "J / Esc — закрыть. Награду можно получить в порту.",
                (r.centerx, r.bottom - 23), ui.DIM, 16, anchor="midtop")


# --- кодекс ----------------------------------------------------------------------------

class CodexScreen(Screen):
    LIST_ROWS = 20

    def __init__(self, game):
        super().__init__(game)
        world = game.world
        self.items = []             # [(категория, ключ | None)] — None для заголовка категории
        for cat in CATEGORIES:
            keys = [k for k in world.codex if (e := entry(k)) and e[0] == cat]
            if keys:
                self.items.append((cat, None))
                self.items += [(cat, k) for k in sorted(keys, key=lambda k: entry(k)[1])]
        self.sel = next((i for i, (_, k) in enumerate(self.items) if k and not world.codex[k]),
                        next((i for i, (_, k) in enumerate(self.items) if k), 0))
        self.scroll = 0
        self.rects = []
        self.total = len(all_keys())
        self._scroll_to_sel()

    def _move(self, d):
        i = self.sel
        for _ in range(len(self.items)):
            i = (i + d) % len(self.items)
            if self.items[i][1]:
                self.sel = i
                self.sound("ui_hover")
                break
        self._scroll_to_sel()

    def _scroll_to_sel(self):
        if self.sel - 1 < self.scroll:
            self.scroll = max(0, self.sel - 1)
        elif self.sel >= self.scroll + self.LIST_ROWS:
            self.scroll = self.sel - self.LIST_ROWS + 1

    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, self.game.settings.key("codex")):
                self.close()
            elif e.key in (pygame.K_UP, pygame.K_w):
                self._move(-1)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self._move(1)
        elif e.type == pygame.MOUSEMOTION:
            for i, r in self.rects:
                if r.collidepoint(e.pos) and self.items[i][1] and i != self.sel:
                    self.sel = i
                    self.sound("ui_hover")
        elif e.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(max(0, len(self.items) - self.LIST_ROWS), self.scroll - e.y))

    def draw(self):
        s, world = self.screen, self.game.world
        dim(s, int(200 * self.k))
        w, h = 980, 560
        r = self.slide(((self.w - w) // 2, (self.h - h) // 2, w, h))
        ui.panel(s, r, "Кодекс")
        found = len(world.codex)
        ui.text(s, f"открыто {found} из {self.total}", (r.right - 16, r.y + 7), ui.DIM, 15, anchor="topright")
        lst = pygame.Rect(r.x + 10, r.y + 32, 330, h - 44)
        pygame.draw.line(s, ui.LINE, (lst.right + 6, lst.y), (lst.right + 6, lst.bottom))
        self.rects = []
        if not self.items:
            ui.text(s, "Пока пусто", lst.center, ui.DIM, 18, anchor="center")
            return
        key = self.items[self.sel][1]
        if key and not world.codex.get(key, True):
            world.codex[key] = True            # открыли — больше не «новое»
        y = lst.y
        for i in range(self.scroll, min(len(self.items), self.scroll + self.LIST_ROWS)):
            cat, k = self.items[i]
            rr = pygame.Rect(lst.x, y, lst.w, 24)
            if k is None:
                ui.text(s, cat.upper(), (rr.x + 6, rr.y + 8), ui.ACCENT, 15, True)
            else:
                self.rects.append((i, rr))
                if i == self.sel:
                    ui.selection(s, rr)
                title = entry(k)[1]
                col = ui.TEXT if i == self.sel else ui.DIM
                ui.text(s, title, (rr.x + 18, rr.centery), col, 17, anchor="midleft")
                if not world.codex[k]:
                    ui.chip(s, "НОВОЕ", (rr.right - 6, rr.y + 5), ui.WARN, 13, anchor="topright")
            y += 25
        # текст записи
        cat, title, text, stats = entry(key)
        tx, tw = lst.right + 24, r.right - lst.right - 40
        ui.text(s, cat.upper(), (tx, r.y + 36), ui.DIM, 15, True)
        ui.text(s, title, (tx, r.y + 54), ui.TEXT, 30, True)
        y = r.y + 96
        for line in ui.wrap(text, tw, 19):
            ui.text(s, line, (tx, y), ui.TEXT, 19)
            y += 22
        if stats:
            y += 10
            pygame.draw.line(s, ui.LINE, (tx, y), (tx + tw, y))
            y += 10
            for line in stats:
                ui.text(s, "· " + line, (tx, y), ui.DIM, 17)
                y += 20
        ui.text(s, "W/S или мышь — выбор   K / Esc — закрыть", (tx, r.bottom - 26), ui.DIM, 15)


# --- подсказка при первом открытии ------------------------------------------------------

class Tip:
    """Плашка внизу по центру. Закрывается кликом, любой клавишей или сама через 12 с."""

    def __init__(self, game, text):
        self.game = game
        self.text = text
        self.age = 0.0
        self.done = False
        self.rect = pygame.Rect(0, 0, 0, 0)

    def handle(self, e):
        if self.age < 0.4:
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(e.pos):
            self.done = True
            return True
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.done = True
            return True
        return False

    def update(self, dt):
        self.age += dt
        if self.age > 12:
            self.done = True

    def draw(self):
        s = self.game.screen
        w, h = s.get_size()
        lines = ui.wrap(self.text, 560, 17)
        k = ease(self.age / 0.25) * min(1.0, (12 - self.age) / 0.5)
        r = pygame.Rect(0, 0, 600, 44 + 19 * len(lines))
        r.midbottom = (w // 2, h - 60 + int((1 - k) * 20))
        self.rect = r
        ui.panel(s, r, "Подсказка", ui.C_ENERGY)
        for i, line in enumerate(lines):
            ui.text(s, line, (r.x + 16, r.y + 28 + i * 19), ui.TEXT, 17)
        ui.text(s, "клик или Enter — понятно  ·  отключить: Настройки → Интерфейс", (r.right - 12, r.bottom - 16),
                ui.DIM, 13, anchor="topright")


# --- отладочная консоль -----------------------------------------------------------------

CONSOLE_HELP = [
    "credits N — выдать кредиты          tp port|eye|X Y — телепорт",
    "spawn [gunner|brawler|rocketeer|hunter] [N] — рейдеры рядом",
    "event surge|calm|storm|bloom|current — событие у корабля",
    "time ЧЧ — время суток               god — неуязвимость вкл/выкл",
    "fauna N — Тиходонты рядом           reveal — открыть карту и кодекс",
    "heal — починить всё                 goals — выполнить цели обучения",
]


class Console(Screen):
    """` или F1: отладочная консоль. Мир на паузе."""

    def __init__(self, game):
        super().__init__(game)
        self.line = ""
        self.out = ["Консоль отладки. help — список команд, Esc — закрыть."]
        pygame.key.start_text_input()

    def close(self):
        pygame.key.stop_text_input()
        super().close()

    def handle(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_BACKQUOTE, pygame.K_F1):
                self.close()
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                cmd, self.line = self.line.strip(), ""
                if cmd:
                    self.out.append("> " + cmd)
                    try:
                        self.out += self.run(cmd)
                    except (ValueError, IndexError, KeyError) as err:
                        self.out.append(f"ошибка: {err}")
                self.out = self.out[-14:]
            elif e.key == pygame.K_BACKSPACE:
                self.line = self.line[:-1]
        elif e.type == pygame.TEXTINPUT and e.text not in "`ё":
            self.line += e.text

    def run(self, cmd):
        from .ai import PIRATE_LOADOUTS, Pirate, Tihodont
        from .events import EVENTS
        world = self.game.world
        p = world.player
        args = cmd.split()
        name = args[0].lower()
        if name == "help":
            return list(CONSOLE_HELP)
        if name == "credits":
            n = int(args[1]) if len(args) > 1 else 1000
            world.captain.credits += n
            return [f"+{n} КК, всего {world.captain.credits}"]
        if name == "tp":
            if args[1] == "port":
                p.pos = world.port + Vector2(0, -260)
            elif args[1] == "eye":
                p.pos = world.eye + Vector2(0, C.EYE_WALL_R + 300)
            else:
                p.pos = Vector2(float(args[1]), float(args[2]))
            p.vel = Vector2()
            self.game.renderer.cam.snap(p.pos)
            return [f"телепорт: {int(p.pos.x)}, {int(p.pos.y)}"]
        if name == "spawn":
            kind = args[1] if len(args) > 1 else "gunner"
            if kind not in PIRATE_LOADOUTS:
                return ["виды: " + ", ".join(PIRATE_LOADOUTS)]
            n = int(args[2]) if len(args) > 2 else 1
            for i in range(n):
                pos = p.pos + Vector2(1, 0).rotate(world.rng.uniform(0, 360)) * 600
                world.pirates.append(Pirate(pos, world.rng, kind))
            return [f"рейдеров: {n} ({kind})"]
        if name == "event":
            keys = {"surge": 0, "calm": 1, "storm": 2, "bloom": 3, "current": 4}
            data = EVENTS[keys[args[1]]]
            world.events.spawn(data, Vector2(p.pos), world.t)
            return [f"событие: {data.name}"]
        if name == "time":
            hours = float(args[1])
            want = (hours / 24.0) % 1.0
            world.clock_offset += ((want - world.time_of_day) % 1.0) * C.DAY_LENGTH
            return [f"время: {world.clock()}"]
        if name == "god":
            world.god = not world.god
            return ["неуязвимость " + ("включена" if world.god else "выключена")]
        if name == "fauna":
            n = int(args[1]) if len(args) > 1 else 3
            for _ in range(n):
                world.tihodonts.append(Tihodont(p.pos + Vector2(1, 0).rotate(world.rng.uniform(0, 360)) * 500,
                                                world.rng))
            return [f"Тиходонтов рядом: +{n}"]
        if name == "reveal":
            world.memory[:, :] = 1.0
            from .codex import all_keys
            for k in all_keys():
                world.codex.setdefault(k, False)
            return ["карта и кодекс открыты"]
        if name == "heal":
            p.repair_all()
            p.fouling = 0.0
            p.recharge()
            return ["корабль как новый"]
        if name == "goals":
            from .world import GOALS
            for k, _, _ in GOALS:
                world.complete(k)
            return ["цели обучения выполнены"]
        return [f"неизвестная команда: {name} (help — список)"]

    def draw(self):
        s = self.screen
        h = 22 * 16 + 20
        r = pygame.Rect(0, int(-h * (1 - self.k)), self.w, h)
        ui.panel(s, r, "Консоль", ui.WARN, bg=(4, 6, 10, 235))
        y = r.bottom - 36 - len(self.out) * 20
        for line in self.out:
            col = ui.TEXT if line.startswith(">") else ui.WARN if line.startswith("ошибка") else ui.DIM
            ui.text(s, line, (r.x + 16, y), col, 17)
            y += 20
        caret = "_" if int(self.age * 2) % 2 == 0 else " "
        ui.text(s, "> " + self.line + caret, (r.x + 16, r.bottom - 28), ui.ACCENT, 19, True)
