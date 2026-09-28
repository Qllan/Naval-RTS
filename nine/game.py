"""Главный цикл: ввод → симуляция → отрисовка. Поверх игры — стек экранов (меню, карта, …)."""

import random
import time

import pygame

from . import config as C
from .audio import Audio
from .gfx import ui
from .hud import Hud
from .port_ui import PortUI
from .render import Renderer
from .screens import CodexScreen, DeathScreen, MainMenu, MapScreen, PauseMenu
from .settings import Settings
from .world import Controls, World

UTILITY_ACTIONS = {"util1": 0, "util2": 1, "util3": 2, "util4": 3}
PIP_ACTIONS = {"pip_shields": "shields", "pip_engines": "engines", "pip_weapons": "weapons", "pip_reset": "reset"}
DEATH_DELAY = 1.4          # секунд между взрывом и экраном гибели


class Game:
    def __init__(self, seed=9, screen=None, menu=False, settings=None):
        if screen is None:
            pygame.display.init()
            pygame.font.init()
            screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
            pygame.display.set_caption("Девятка — прототип")
        ui.Fonts.reset()
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.settings = settings or Settings.load()
        self.world = World(seed)
        self.renderer = Renderer(screen)
        self.hud = Hud(screen, self.world)
        self.audio = Audio()
        self.port_ui = PortUI(screen, self.audio)
        self.docked = False
        self.running = True
        self.stack = []
        self.pending_activate = []
        self.pending_pips = []
        self.pending_ammo = False
        self.pending_spot = False
        self._seen_loss = None
        self._death_timer = 0.0
        self._fps = 60.0
        self.apply_settings()
        if menu:
            self.push(MainMenu(self))

    # --- экраны и настройки -------------------------------------------------

    def push(self, screen):
        self.stack.append(screen)

    def pop(self, screen=None):
        if self.stack and (screen is None or self.stack[-1] is screen):
            self.stack.pop()
        elif screen in self.stack:
            self.stack.remove(screen)

    @property
    def paused(self):
        return any(s.pauses for s in self.stack)

    def quit(self):
        self.running = False

    def new_game(self):
        self.world = World(random.randrange(1, 10_000))
        self.hud = Hud(self.screen, self.world)
        self.renderer = Renderer(self.screen)
        self.docked = False
        self._seen_loss = None
        self.apply_settings()
        self.stack = [s for s in self.stack if isinstance(s, MainMenu)]

    def apply_settings(self):
        s = self.settings
        ui.configure(opacity=s.hud_opacity, colorblind=s.colorblind, large_font=s.large_font)
        self.audio.volume.update(master=s.master, sfx=s.sfx, ambient=s.ambient, ui=s.ui)
        r = self.renderer
        if r.high_quality != s.high_quality:
            r.toggle_quality()
        r.distortion = s.distortion
        r.cam.shake_scale = s.shake
        r.fx.numbers = s.damage_numbers
        self.hud.hints = s.hints
        self.hud.show_minimap = s.show_minimap
        self.hud.show_log = s.show_log
        self.hud.keys = s

    # --------------------------------------------------------------------

    def controls(self):
        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed()
        k = self.settings.key
        ctl = Controls()
        ctl.throttle = (1.0 if keys[k("forward")] or keys[pygame.K_UP] else 0.0) - \
                       (1.0 if keys[k("back")] or keys[pygame.K_DOWN] else 0.0)
        ctl.turn = (1.0 if keys[k("right")] or keys[pygame.K_RIGHT] else 0.0) - \
                   (1.0 if keys[k("left")] or keys[pygame.K_LEFT] else 0.0)
        ctl.boost = keys[k("boost")] or keys[pygame.K_RSHIFT]
        over_ui = self.hud.over_ui(pygame.mouse.get_pos())   # клик по панели не стреляет
        ctl.fire = (mouse[0] and not over_ui) or keys[k("fire")]
        ctl.fire2 = mouse[2] and not over_ui
        ctl.mine = keys[k("mine")]
        ctl.aim = self.renderer.s2w(pygame.mouse.get_pos())
        ctl.activate, self.pending_activate = self.pending_activate, []
        ctl.pips, self.pending_pips = self.pending_pips, []
        ctl.cycle_ammo, self.pending_ammo = self.pending_ammo, False
        ctl.toggle_spotlight, self.pending_spot = self.pending_spot, False
        return ctl

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F12:
                path = f"screenshot_{int(time.time())}.png"
                pygame.image.save(self.screen, path)
                self.world.say(f"Скриншот: {path}")
            elif self.stack:
                self.stack[-1].handle(e)
            elif self.docked:
                if self.port_ui.handle_event(e, self.world) == "leave":
                    self.docked = False
                    self.world.undock()
            else:
                self.handle_sea_event(e)

    def handle_sea_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.hud.minimap_rect and self.hud.minimap_rect.collidepoint(e.pos):
                self.audio.ui("ui_click")
                self.push(MapScreen(self))
            else:
                self.hud_click(e.pos)
        elif e.type == pygame.MOUSEWHEEL:
            self.renderer.cam.zoom_by(e.y)
        elif e.type == pygame.KEYDOWN:
            key, k = e.key, self.settings.key
            if key == pygame.K_ESCAPE:
                self.audio.ui("ui_click")
                self.push(PauseMenu(self))
            elif key == k("help"):
                self.hud.show_help = not self.hud.show_help
                self.hud.help_until = 0
            elif key == k("map"):
                self.audio.ui("ui_click")
                self.push(MapScreen(self))
            elif key == k("codex"):
                self.audio.ui("ui_click")
                self.push(CodexScreen(self))
            elif key == k("dock") and self.world.can_dock():
                self.docked = True
                self.hud.show_help = False
                self.hud.help_until = 0
                self.world.dock()
                self.port_ui.reset()
            elif key == k("ammo"):
                self.pending_ammo = True
            elif key == k("spotlight"):
                self.pending_spot = True
            elif key == pygame.K_F10:
                self.settings.high_quality = not self.settings.high_quality
                self.apply_settings()
                self.settings.save()
                self.world.say(f"Графика: {'высокое' if self.renderer.high_quality else 'низкое'} качество")
            else:
                for action, idx in UTILITY_ACTIONS.items():
                    if key == k(action):
                        self.pending_activate.append(idx)
                for action, sys_ in PIP_ACTIONS.items():
                    if key == k(action):
                        self.pending_pips.append(sys_)

    def hud_click(self, pos):
        action = self.hud.action_at(pos)
        if action is None:
            return
        self.audio.ui("ui_click")
        if action[0] == "pip":
            self.pending_pips.append(action[1])
        elif action[0] == "ammo":
            self.pending_ammo = True
        elif action[0] == "utility":
            self.pending_activate.append(action[1])

    def step(self, dt):
        paused = self.paused
        if not self.docked and not paused:
            self.world.update(dt, Controls() if self.stack else self.controls())
            self._check_loss(dt)
        for s in self.stack:
            s.update(dt)
        self.renderer.draw(self.world)
        self.audio.update(self.world, [] if paused else self.renderer.last_events, self.renderer.lightning, dt,
                          paused=self.docked or paused)
        if self.docked:
            self.port_ui.draw(self.world, dt)
        elif not any(isinstance(s, MainMenu) for s in self.stack):
            self.hud.draw(self.world, self.docked, self.renderer.cam, self.renderer.last_events)
        for s in self.stack:
            s.draw()
        if self.settings.show_fps:
            self._fps += (1 / max(dt, 1e-3) - self._fps) * 0.05
            ui.text(self.screen, f"{self._fps:3.0f} FPS", (self.screen.get_width() // 2, self.screen.get_height() - 18),
                    ui.DIM, 15, anchor="midtop")

    def _check_loss(self, dt):
        loss = self.world.last_loss
        if loss is not None and loss is not self._seen_loss:
            if self._death_timer <= 0:
                self._death_timer = DEATH_DELAY
            self._death_timer -= dt
            if self._death_timer <= 0:
                self._seen_loss = loss
                self.push(DeathScreen(self, loss))

    def run(self):
        while self.running:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 0.05)
            self.handle_events()
            self.step(dt)
            pygame.display.flip()
        self.settings.save()
        pygame.quit()
