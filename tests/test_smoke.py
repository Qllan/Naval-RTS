import pygame

from nine.game import Game


def test_game_runs_headless_frames_and_port_screens():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen)
    for _ in range(90):
        g.handle_events()
        g.step(1 / 60)
    g.docked = True
    g.world.dock()
    g.port_ui.reset()
    g.world.captain.credits = 10_000
    ui, w = g.port_ui, g.world
    keys = [pygame.K_RETURN, pygame.K_DOWN, pygame.K_RETURN,           # сервис
            pygame.K_RIGHT, pygame.K_DOWN, pygame.K_RETURN,            # верфь: корвет
            pygame.K_RIGHT, pygame.K_RETURN, pygame.K_DOWN, pygame.K_RETURN,   # оснащение
            pygame.K_BACKSPACE, pygame.K_RIGHT]                         # снять, склад
    for key in keys:
        ui.handle_key(key, w)
        g.step(1 / 60)
    assert w.player.hull.key == "corvette"
    assert w.captain.storage
    assert ui.handle_key(pygame.K_ESCAPE, w) in ("leave", None)
    pygame.quit()


def test_picker_scrolls_to_selection():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen)
    w = g.world
    w.captain.storage = ["autocannon_s", "scatter_s", "missile_s"] * 4        # много позиций
    g.docked = True
    w.dock()
    ui = g.port_ui
    ui.reset()
    ui.tab = 2
    ui.handle_key(pygame.K_RETURN, w)                   # выбор для оружейного слота
    for _ in range(len(ui.picker_items(w)) - 1):
        ui.handle_key(pygame.K_DOWN, w)
    g.step(1 / 60)                                        # последняя позиция видна и рисуется без ошибок
    assert ui.pick_sel == len(ui.picker_items(w)) - 1
    pygame.quit()


def test_audio_synthesizes_and_reacts_to_events():
    from nine.audio import Audio
    from nine.world import Controls, World
    a = Audio()
    if not a.ok:                                  # без звукового устройства — тихо отключается
        return
    for name in ("gun_s", "gun_m", "explosion_l", "hum", "engine", "ui_buy", "hit_hull~"):
        assert name in a.sounds
    w = World(seed=1, first_event=1e9)
    w.update(1 / 60, Controls())
    a.update(w, [("muzzle", w.player.pos, 0, 1, "gun", "player"), ("explosion", w.player.pos, 3)], True, 1 / 60)
    a.ui("ui_click")


def test_hud_pip_click_moves_energy():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen)
    g.step(1 / 60)
    pip = next((r for r, a in g.hud.buttons if a == ("pip", "engines")), None)
    assert pip is not None
    assert g.hud.over_ui(pip.center)
    before = g.world.player.pips["engines"]
    g.hud_click(pip.center)
    g.step(1 / 60)
    assert g.world.player.pips["engines"] >= before
    assert not g.hud.over_ui((640, 360))
    pygame.quit()
