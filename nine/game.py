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
from . import save as saves
from .screens import CodexScreen, Console, DeathScreen, MainMenu, MapScreen, PauseMenu, Tip
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
        self.show_debug = False
        self.played = False         # сохраняем только если действительно играли
        self.tip = None
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
        self._set_world(World(random.randrange(1, 10_000)))

    def load_game(self):
        world = saves.load()
        if world is None:
            return False
        self._set_world(world)
        self.played = True
        self.world.say("Сохранение загружено.")
        return True

    def save_game(self):
        if self.played:
            try:
                saves.save(self.world)
            except OSError:
                self.world.say("Не удалось сохранить игру.", "bad")

    def show_tip(self, key, text):
        """Контекстная подсказка при первом открытии экрана (отключается в настройках)."""
        if self.settings.hints and key not in self.settings.seen_tips:
            self.settings.seen_tips.append(key)
            self.settings.save()
            self.tip = Tip(self, text)

    def _set_world(self, world):
        self.world = world
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
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F3:
                self.show_debug = not self.show_debug
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_F12:
                path = f"screenshot_{int(time.time())}.png"
                pygame.image.save(self.screen, path)
                self.world.say(f"Скриншот: {path}")
            elif self.tip and self.tip.handle(e):
                pass
            elif self.stack:
                self.stack[-1].handle(e)
            elif self.docked:
                if self.port_ui.handle_event(e, self.world) == "leave":
                    self.docked = False
                    self.world.undock()
                    self.save_game()
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
            elif key in (pygame.K_BACKQUOTE, pygame.K_F1):
                self.push(Console(self))
            elif key == k("help"):
                self.hud.show_help = not self.hud.show_help
                self.hud.help_until = 0
            elif key == k("map"):
                self.audio.ui("ui_click")
                self.push(MapScreen(self))
                self.show_tip("map", "Карта: ЛКМ — путевая точка (стрелка появится на HUD), ПКМ — убрать. "
                                     "В плотной Пелене разведанное выцветает — это амнезия.")
            elif key == k("codex"):
                self.audio.ui("ui_click")
                self.push(CodexScreen(self))
            elif key == k("dock") and self.world.can_dock():
                self.docked = True
                self.hud.show_help = False
                self.hud.help_until = 0
                self.world.dock()
                self.port_ui.reset()
                self.save_game()
                self.show_tip("port", "Порт: всё кликабельно. R — починить и пополнить всё, P — продать груз. "
                                      "В «Оснащении» модули можно перетаскивать в слоты мышью.")
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
            if not self.stack:
                self.played = True
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
        if self.tip:
            self.tip.update(dt)
            self.tip.draw()
            if self.tip.done:
                self.tip = None
        if self.show_debug:
            self.draw_debug_overlay(dt)
        if self.settings.show_fps:
            self._fps += (1 / max(dt, 1e-3) - self._fps) * 0.05
            ui.text(self.screen, f"{self._fps:3.0f} FPS", (self.screen.get_width() // 2, self.screen.get_height() - 18),
                    ui.DIM, 15, anchor="midtop")

    def draw_debug_overlay(self, dt):
        """F3: diagnostics for playtests; never changes simulation state."""
        w, p = self.world, self.world.player
        fps = self.clock.get_fps() or 1.0 / max(dt, 1e-3)
        lines = (
            f"DEBUG | FPS {fps:.0f} | frame {dt * 1000:.1f} ms",
            f"Seed {w.seed} | t {w.t:.1f}s | x {p.pos.x:.0f} y {p.pos.y:.0f}",
            f"Speed {p.speed:.1f} | Veil {w.density_at(p.pos):.2f}",
            f"Radar {w.radar_range():.0f} | Vision {w.visual_range():.0f}",
            f"Pirates {len(w.pirates)} | Rays {len(w.rays)} | Tihodonts {len(w.tihodonts)}",
            f"Shots {len(w.projectiles)} | Resources {len(w.nodes)} | Loot {len(w.loot)}",
        )
        font = pygame.font.Font(None, 22)
        width = max(font.size(line)[0] for line in lines) + 24
        height = len(lines) * 23 + 14
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        panel.fill((5, 12, 20, 220))
        for i, line in enumerate(lines):
            panel.blit(font.render(line, True, (194, 222, 230)), (12, 7 + i * 23))
        self.screen.blit(panel, (12, 12))

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
        self.save_game()
        pygame.quit()
