"""Главный цикл: ввод → симуляция → отрисовка."""

import time

import pygame
from pygame.math import Vector2

from . import config as C
from .hud import Hud
from .render import Renderer
from .world import Controls, World


class Game:
    def __init__(self, seed=9, screen=None):
        if screen is None:
            pygame.display.init()
            pygame.font.init()
            screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H))
            pygame.display.set_caption("Девятка — прототип")
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.world = World(seed)
        self.renderer = Renderer(screen)
        self.hud = Hud(screen, self.world)
        self.docked = False
        self.running = True

    # --------------------------------------------------------------------

    def controls(self):
        keys = pygame.key.get_pressed()
        mouse = pygame.mouse.get_pressed()
        ctl = Controls()
        ctl.throttle = (1.0 if keys[pygame.K_w] or keys[pygame.K_UP] else 0.0) - (1.0 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0.0)
        ctl.turn = (1.0 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0.0) - (1.0 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0.0)
        ctl.boost = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        ctl.fire = mouse[0] or keys[pygame.K_SPACE]
        ctl.mine = keys[pygame.K_e]
        ctl.aim = Vector2(pygame.mouse.get_pos()) + self.renderer.cam
        return ctl

    def dock_action(self, key):
        w = self.world
        name = pygame.key.name(key)
        actions = {
            "1": lambda: w.say(f"Продано на {w.sell_cargo()} КК."),
            "2": lambda: w.say(f"Отремонтировано {int(w.repair())} ед. корпуса."),
            "3": lambda: w.say("Корпус очищен от налёта." if w.clean_hull() else "Чистка не нужна или не по карману."),
            "4": lambda: w.say("Сенсоры улучшены." if w.buy_upgrade("sensor") else "Не удалось купить."),
            "5": lambda: w.say("Трюм расширен." if w.buy_upgrade("cargo") else "Не удалось купить."),
            "6": lambda: w.say("Орудия улучшены." if w.buy_upgrade("gun") else "Не удалось купить."),
            "7": lambda: w.say("Новый корабль: Крейсер." if w.buy_ship("cruiser") else "Сделка не состоялась."),
            "8": lambda: w.say("Новый корабль: Барка." if w.buy_ship("barge") else "Сделка не состоялась."),
            "9": lambda: w.say("Новый корабль: Скаут." if w.buy_ship("scout") else "Сделка не состоялась."),
            "0": lambda: w.say(f"Выплачено по долгу: {w.pay_debt()} КК."),
            "m": lambda: w.say("Травма вылечена." if w.heal() else "Лечение недоступно."),
        }
        if name in actions:
            actions[name]()

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_F12:
                    path = f"screenshot_{int(time.time())}.png"
                    pygame.image.save(self.screen, path)
                    self.world.say(f"Скриншот: {path}")
                elif e.key == pygame.K_h:
                    self.hud.show_help = not self.hud.show_help
                    self.hud.help_until = 0
                elif self.docked:
                    if e.key in (pygame.K_f, pygame.K_ESCAPE):
                        self.docked = False
                        self.world.undock()
                    else:
                        self.dock_action(e.key)
                elif e.key == pygame.K_ESCAPE:
                    self.running = False
                elif e.key == pygame.K_f and self.world.can_dock():
                    self.docked = True
                    self.hud.show_help = False
                    self.hud.help_until = 0
                    self.world.dock()

    def step(self, dt):
        if not self.docked:
            self.world.update(dt, self.controls())
        self.renderer.draw(self.world)
        self.hud.draw(self.world, self.docked)

    def run(self):
        while self.running:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 0.05)
            self.handle_events()
            self.step(dt)
            pygame.display.flip()
        pygame.quit()
