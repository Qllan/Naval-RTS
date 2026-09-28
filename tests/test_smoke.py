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


def _post_key(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def test_screens_open_and_close():
    from nine.screens import CodexScreen, DeathScreen, MainMenu, MapScreen, PauseMenu, SettingsScreen

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen, menu=True)
    assert isinstance(g.stack[-1], MainMenu)
    _post_key(pygame.K_RETURN)                       # «Новая игра» при запуске — просто закрыть меню
    g.handle_events()
    g.step(1 / 60)
    assert not g.stack
    _post_key(pygame.K_ESCAPE)
    g.handle_events()
    assert isinstance(g.stack[-1], PauseMenu)
    t = g.world.t
    for _ in range(10):
        g.step(1 / 60)
    assert g.world.t == t                            # пауза останавливает мир
    for cls in (SettingsScreen, CodexScreen, MapScreen):
        g.push(cls(g))
        for _ in range(12):
            g.step(1 / 60)
        _post_key(pygame.K_ESCAPE)
        g.handle_events()
        assert isinstance(g.stack[-1], PauseMenu)
    g.stack.clear()
    g.world.player.hp = 0
    for _ in range(int(2.0 * 60)):
        g.step(1 / 60)
    assert isinstance(g.stack[-1], DeathScreen)
    assert g.world.in_capsule
    pygame.quit()


def test_map_click_sets_waypoint_and_settings_persist():
    from nine.screens import MapScreen, SettingsScreen
    from nine.settings import Settings

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen)
    m = MapScreen(g)
    g.push(m)
    g.step(1 / 60)
    target = m.w2m((4000, 4000))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(int(target.x), int(target.y))))
    g.handle_events()
    assert g.world.waypoint is not None and g.world.waypoint.distance_to((4000, 4000)) < 40
    g.stack.clear()

    st = SettingsScreen(g)
    g.push(st)
    st.tab = 3                                       # управление
    st.sel = 0
    _post_key(pygame.K_RETURN)
    _post_key(pygame.K_i)
    g.handle_events()
    assert g.settings.key("forward") == pygame.K_i
    assert Settings.load().key("forward") == pygame.K_i
    g.settings.keys["forward"] = "w"
    g.settings.save()
    pygame.quit()


def test_amnesia_fades_memory_in_dense_veil():
    from nine.world import World

    w = World(3)
    assert w.memory.max() == 1.0
    w.memory[0, 0] = 1.0                             # далёкая разведанная клетка
    w._update_memory(10.0, 0.95)
    assert w.memory[0, 0] < 0.9                      # забывается
    cy, cx = int(w.player.pos.y // 200), int(w.player.pos.x // 200)
    assert w.memory[cy, cx] == 1.0                   # вокруг корабля — снова видно
    assert "amnesia" in w.codex
