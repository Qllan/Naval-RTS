import pygame

from nine.game import Game


def test_game_runs_headless_frames():
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    g = Game(seed=4, screen=screen)
    for _ in range(90):
        g.handle_events()
        g.step(1 / 60)
    g.docked = True
    g.world.dock()
    g.step(1 / 60)
    for key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_0, pygame.K_m):
        g.dock_action(key)
    assert g.world.t > 1.0
    pygame.quit()
