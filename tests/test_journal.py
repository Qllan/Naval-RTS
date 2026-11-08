"""Journal has no gameplay side effects and can be opened during a voyage."""

from types import SimpleNamespace

import pygame

from nine.gfx import ui
from nine.screens import CaptainsJournal, journal_entries
from nine.settings import Settings
from nine.world import World


def test_journal_is_empty_before_accepting_contracts():
    world = World(seed=9, first_event=1e9)
    assert journal_entries(world) == []


def test_journal_shows_active_progress_and_ready_to_claim():
    world = World(seed=9, first_event=1e9)
    world.contract_action("salt")
    world.contract_action("pirates")
    world.contract_action("scout")
    world.captain.cargo["salt"] = 7
    world.captain.kills = 2
    world.contracts["scout"]["explored"] = True
    before = world.captain.credits
    rows = {row[0]: row for row in journal_entries(world)}
    assert rows["salt"][3:5] == (7, 10)
    assert rows["pirates"][6] == "МОЖНО СДАТЬ В ПОРТ"
    assert rows["scout"][6] == "МОЖНО СДАТЬ В ПОРТ"
    assert world.captain.credits == before
    assert all(state["status"] == "active" for state in world.contracts.values())


def test_journal_completed_contract_is_read_only():
    world = World(seed=9, first_event=1e9)
    world.contract_action("salt")
    world.captain.cargo["salt"] = 10
    world.contract_action("salt")
    before = world.captain.credits
    rows = journal_entries(world)
    assert rows[0][6] == "ЗАВЕРШЁН"
    assert world.captain.credits == before


def test_journal_screen_draw_and_close():
    pygame.font.init()
    ui.Fonts.reset()
    screen = pygame.Surface((1280, 720))
    world = World(seed=9, first_event=1e9)
    world.contract_action("scout")
    closed = []
    game = SimpleNamespace(
        screen=screen, world=world, settings=Settings(),
        pop=lambda screen: closed.append(screen),
    )
    journal = CaptainsJournal(game)
    journal.update(0.3)
    journal.draw()
    journal.handle(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_j}))
    assert closed == [journal]
