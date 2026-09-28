"""Главный цикл: ввод → симуляция → отрисовка."""

import time

import pygame

from . import config as C
from .audio import Audio
from .gfx import ui
from .hud import Hud
from .port_ui import PortUI
from .render import Renderer
from .world import Controls, World

UTILITY_KEYS = {pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3}
PIP_KEYS = {pygame.K_z: "shields", pygame.K_x: "engines", pygame.K_c: "weapons", pygame.K_v: "reset"}


class Game:
    def __init__(self, seed=9, screen=None):
        if screen is None:
            pygame.display.init()
            pygame.font.init()
            screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
            pygame.display.set_caption("Девятка — прототип")
        ui.Fonts.reset()
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.world = World(seed)
        self.renderer = Renderer(screen)
        self.hud = Hud(screen, self.world)
        self.audio = Audio()
        self.port_ui = PortUI(screen, self.audio)
        self.docked = False
        self.running = True
        self.pending_activate = []
        self.pending_pips = []
        self.pending_ammo = False
        self.pending_spot = False

    # --------------------------------------------------------------------

    def controls(self):
        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed()
        ctl = Controls()
        ctl.throttle = (1.0 if keys[pygame.K_w] or keys[pygame.K_UP] else 0.0) - (1.0 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0.0)
        ctl.turn = (1.0 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0.0) - (1.0 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0.0)
        ctl.boost = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        over_ui = self.hud.over_ui(pygame.mouse.get_pos())   # клик по панели не стреляет
        ctl.fire = (mouse[0] and not over_ui) or keys[pygame.K_SPACE]
        ctl.fire2 = mouse[2] and not over_ui
        ctl.mine = keys[pygame.K_e]
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
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and not self.docked:
                self.hud_click(e.pos)
            elif e.type == pygame.MOUSEWHEEL and not self.docked:
                self.renderer.cam.zoom_by(e.y)
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F12:
                    path = f"screenshot_{int(time.time())}.png"
                    pygame.image.save(self.screen, path)
                    self.world.say(f"Скриншот: {path}")
                elif self.docked:
                    if self.port_ui.handle_key(e.key, self.world) == "leave":
                        self.docked = False
                        self.world.undock()
                elif e.key == pygame.K_h:
                    self.hud.show_help = not self.hud.show_help
                    self.hud.help_until = 0
                elif e.key == pygame.K_ESCAPE:
                    self.running = False
                elif e.key == pygame.K_f and self.world.can_dock():
                    self.docked = True
                    self.hud.show_help = False
                    self.hud.help_until = 0
                    self.world.dock()
                    self.port_ui.reset()
                elif e.key in UTILITY_KEYS:
                    self.pending_activate.append(UTILITY_KEYS[e.key])
                elif e.key in PIP_KEYS:
                    self.pending_pips.append(PIP_KEYS[e.key])
                elif e.key == pygame.K_t:
                    self.pending_ammo = True
                elif e.key == pygame.K_l:
                    self.pending_spot = True
                elif e.key == pygame.K_F10:
                    self.renderer.toggle_quality()
                    self.world.say(f"Графика: {'высокое' if self.renderer.high_quality else 'низкое'} качество")

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
        if not self.docked:
            self.world.update(dt, self.controls())
        self.renderer.draw(self.world)
        self.audio.update(self.world, self.renderer.last_events, self.renderer.lightning, dt, paused=self.docked)
        if self.docked:
            self.port_ui.draw(self.world)
        else:
            self.hud.draw(self.world, self.docked, self.renderer.cam, self.renderer.last_events)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 0.05)
            self.handle_events()
            self.step(dt)
            pygame.display.flip()
        pygame.quit()
