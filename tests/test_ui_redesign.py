"""R1.4 shared HUD/port/shipyard design contracts and headless preview."""

import pygame

from nine.gfx import ui
from nine.gfx.style_tokens import contrast_ratio, rgb
from nine.port_ui import PortUI
from nine.hud import Hud
from nine.ship import Ship
from nine.world import World


def test_shared_ui_theme_matches_approved_style_tokens():
    assert ui.TEXT == rgb("ui_text")
    assert ui.DIM == rgb("ui_muted")
    assert ui.ACCENT == rgb("ui_focus")
    assert ui.LINE == rgb("ui_line")
    assert ui.PANEL_RGB == rgb("ui_panel")
    assert ui.WARN == rgb("ui_warning")
    assert ui.BAD == rgb("ui_error")
    assert ui.GOOD == rgb("ui_good")
    for token in ("ui_text", "ui_muted", "ui_warning", "ui_error", "ui_good"):
        for background in ("ui_bg", "ui_panel", "ui_raised"):
            assert contrast_ratio(token, background) >= 4.5


def test_selection_has_border_and_independent_focus_marker():
    pygame.font.init()
    surface = pygame.Surface((110, 65))
    surface.fill(ui.PANEL_RGB)
    rect = pygame.Rect(8, 10, 74, 32)
    ui.selection(surface, rect)
    assert surface.get_at(rect.topleft)[:3] == ui.ACCENT
    assert surface.get_at((rect.x + 10, rect.y + 10))[:3] == ui.SEL_BG


def test_port_redesign_keeps_shipyard_and_fitting_mouse_targets():
    pygame.font.init()
    ui.Fonts.reset()
    screen = pygame.Surface((1280, 720))
    world = World(seed=7, first_event=1e9)
    world.captain.credits = 10000
    world.player = Ship("manta", world.port)
    port = PortUI(screen)
    port.tab = 1
    port.draw(world, 0.4)
    assert len([z for z in port.zones if z[1] == "tab"]) == 4
    assert any(kind == "row" for _, kind, _ in port.zones)
    assert any(name == "leave" for _, kind, name in port.zones if kind == "button")
    port.tab = 2
    port.sel = next(i for i, s in enumerate(world.player.hull.slots)
                    if s.category == "reactor")
    port.slot = port.sel
    port.picker = True
    port.draw(world, 0.4)
    assert len([z for z in port.zones if z[1] == "slot"]) >= len(world.player.hull.slots)
    assert any(kind == "pick" for _, kind, _ in port.zones)
    assert len([z for z in port.zones if z[1] == "tab"]) == 4
    ui.Fonts.reset()


def test_hud_themed_minimap_and_pip_controls_keep_input_mapping():
    pygame.font.init()
    ui.Fonts.reset()
    world = World(seed=7, first_event=1e9)
    screen = pygame.Surface((1280, 720))
    hud = Hud(screen, world)
    hud.draw(world, False, mouse=(-50, -50))
    pip = next(r for r, a in hud.buttons if a == ("pip", "engines"))
    assert hud.action_at(pip.center) == ("pip", "engines")
    assert hud.over_ui(pip.center)
    assert len(hud.panels) >= 3
    ui.Fonts.reset()


def test_r14_real_four_screen_preview_created(tmp_path):
    from tools.preview_interface import render
    path = tmp_path / "ui-r14.png"
    render(path)
    assert path.exists() and path.stat().st_size > 30000
    pygame.init()
    img = pygame.image.load(str(path))
    assert img.get_size() == (2616, 1538)
    pygame.quit()



def test_shipyard_ux_does_not_overlap_description_comparison_price_or_action():
    """Shipyard's fixed stage sections occupy distinct vertical bands."""
    from nine.hulls import PLAYER_HULLS

    pygame.font.init()
    ui.Fonts.reset()
    surface = pygame.Surface((1280, 720))
    world = World(seed=5, first_event=1e9)
    world.captain.credits = 12000
    port = PortUI(surface)
    port.tab = 1
    for index, hull in enumerate(PLAYER_HULLS):
        port.sel = index
        recorded = []
        original = port.text

        def record(message, pos, *args, **kwargs):
            recorded.append((str(message), pos))
            return original(message, pos, *args, **kwargs)

        port.text = record
        port.draw(world, 0.4)
        port.text = original
        metric = next(y for text, (x, y) in recorded if text == "СРАВНЕНИЕ С ВАШИМ")
        price = next(y for text, (x, y) in recorded if text == "К ДОПЛАТЕ С УЧЁТОМ ОБМЕНА")
        assert price > metric + 130
        assert any(text == hull.name.upper() for text, _ in recorded)
        assert any(kind == "row" for _, kind, _ in port.zones)
        assert any(kind == "button" and name == "leave" for _, kind, name in port.zones)
    ui.Fonts.reset()
