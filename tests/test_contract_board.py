"""Interactive contract-board UX regressions."""

import pygame

from nine.gfx import ui
from nine.port_ui import PortUI, TABS
from nine.world import World


def setup_board():
    pygame.font.init()
    ui.Fonts.reset()
    world = World(seed=9, first_event=1e9)
    screen = pygame.Surface((1280, 720))
    port = PortUI(screen)
    port.tab = TABS.index("Контракты")
    return world, port


def test_contracts_are_on_a_separate_tab_not_service():
    world, port = setup_board()
    assert len(port.service_items(world)) == 10
    assert len(port.contract_items(world)) == 3
    assert port._count(world) == 3


def test_keyboard_acceptance_and_turn_in():
    world, port = setup_board()
    port.handle_key(pygame.K_RETURN, world)
    assert world.contracts["salt"]["status"] == "active"
    world.captain.cargo["salt"] = 10
    port.handle_key(pygame.K_RETURN, world)
    assert world.contracts["salt"]["status"] == "done"
    assert world.captain.credits == 550


def test_mouse_contract_row_is_clickable():
    world, port = setup_board()
    port.draw(world, 0.4)
    rows = sorted((idx, rect) for rect, kind, idx in port.zones if kind == "row")
    assert len(rows) == 3
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": rows[1][1].center, "button": 1}), world)
    assert world.contracts["pirates"]["status"] == "active"


def test_contract_row_does_not_reaward_completed_mission():
    world, port = setup_board()
    port._activate(world)
    world.captain.cargo["salt"] = 10
    port._activate(world)
    credits = world.captain.credits
    port._activate(world)
    assert world.captain.credits == credits
