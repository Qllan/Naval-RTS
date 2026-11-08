"""UX 2.3: responsive port + accessible labels + screen-space controls."""

from types import SimpleNamespace

import pygame
import pytest

from nine.gfx import ui
from nine.hud import Hud
from nine.hulls import PLAYER_HULLS
from nine.port_ui import PortUI, port_viewport
from nine.ship import Ship
from nine.world import World


def staged(size, hull="manta"):
    pygame.font.init()
    ui.Fonts.reset()
    screen = pygame.Surface(size)
    world = World(seed=9, first_event=1e9)
    world.captain.credits = 30000
    world.player = Ship(hull, world.port)
    return screen, world


@pytest.mark.parametrize(("size", "expected"), [
    ((1280, 720), (0, 0, 1280, 720)),
    ((1024, 768), (0, 96, 1024, 576)),
    ((1600, 900), (0, 0, 1600, 900)),
    ((1440, 900), (0, 45, 1440, 810)),
])
def test_port_viewport_fits_without_stretch_or_cutting(size, expected):
    view = port_viewport(size)
    assert tuple(view) == expected
    assert view.left >= 0 and view.top >= 0
    assert view.right <= size[0] and view.bottom <= size[1]
    assert abs(view.w / view.h - 16 / 9) < 0.005


@pytest.mark.parametrize("size", [(1024, 768), (1280, 720), (1600, 900)])
def test_port_visual_buttons_are_clickable_at_physical_screen_coordinates(size):
    screen, world = staged(size)
    port = PortUI(screen)
    port.tab = 1
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS)
                    if h.key == "bastion")
    port.draw(world, 0.4)
    for rect, category, index in port.zones:
        location = port.to_display(rect.center)
        assert rect.inflate(2, 2).collidepoint(port.to_logical(location))
    initial = world.captain.credits
    row = next(rect for rect, kind, idx in port.zones
               if kind == "row" and PLAYER_HULLS[idx].key == "needle")
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": port.to_display(row.center), "button": 1}), world)
    assert world.player.hull.key == "manta"
    assert world.captain.credits == initial
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS) if h.key == "bastion")
    port.draw(world, 0.4)
    cta = next(rect for rect, kind, name in port.zones
               if kind == "button" and name == "purchase_hull")
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": port.to_display(cta.center), "button": 1}), world)
    assert world.player.hull.key == "bastion"
    assert world.captain.credits < initial


def test_letterbox_outside_click_never_activates_port_button():
    screen, world = staged((1024, 768))
    port = PortUI(screen)
    port.tab = 1
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS)
                    if h.key == "bastion")
    port.draw(world, 0.4)
    assert port.to_logical((500, 40)) == (-10000, -10000)
    cash = world.captain.credits
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": (500, 40), "button": 1}), world)
    assert world.captain.credits == cash
    assert world.player.hull.key == "manta"


def test_scaled_fitting_ship_nodes_select_without_instant_purchase():
    screen, world = staged((1024, 768), hull="bastion")
    port = PortUI(screen)
    port.tab = 2
    port.sel = next(i for i, s in enumerate(world.player.hull.slots)
                    if s.category == "reactor")
    port.draw(world, 0.4)
    before = (list(world.player.fit), world.captain.credits)
    node = next(r for r, kind, idx in port.zones
                if kind == "slot" and idx == port.sel)
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": port.to_display(node.center), "button": 1}), world)
    assert port.picker
    assert list(world.player.fit) == before[0]
    assert world.captain.credits == before[1]


def test_large_font_changes_port_native_fonts_without_changing_hit_geometry():
    screen, world = staged((1600, 900))
    try:
        ui.configure(large_font=False)
        port = PortUI(screen)
        port.tab = 2
        port.draw(world, 0.4)
        normal = port.small.get_height()
        baseline = [(r.x, r.y, r.w, r.h, typ, str(idx))
                    for r, typ, idx in port.zones if typ == "tab"]
        ui.configure(large_font=True)
        port.draw(world, 0.4)
        assert port.small.get_height() > normal
        after = [(r.x, r.y, r.w, r.h, typ, str(idx))
                 for r, typ, idx in port.zones if typ == "tab"]
        # Tab widths grow with text; their physical hitboxes still match.
        assert len(after) == len(baseline) == 5
        for rect, kind, idx in port.zones:
            loc = port.to_display(rect.center)
            assert rect.collidepoint(port.to_logical(loc))
    finally:
        ui.configure(large_font=False)
        ui.Fonts.reset()


@pytest.mark.parametrize("size", [(960, 600), (1024, 768), (1600, 900)])
def test_hud_compact_zone_is_separate_from_status_and_minimap(size):
    screen, world = staged(size)
    hud = Hud(screen, world)
    hud.help_until = 0
    hud.draw(world, False, mouse=(-100, -100))
    status = hud.panels[0]
    # HUD widgets are physically scaled on high-resolution displays.
    # Draw order: status, zone, minimap, arsenal.
    zone = hud.panels[1]
    assert status.right < zone.left, (status, zone)
    if hud.minimap_rect is not None:
        assert zone.right < hud.minimap_rect.left
    for rect, action in hud.buttons:
        assert screen.get_rect().contains(rect), action
        assert hud.action_at(rect.center) == action or hud.action_at(rect.center) is not None


def test_resp_review_contains_real_varied_resolution_screenshots(tmp_path):
    from tools.preview_ux_responsive import render

    results = render(tmp_path / "screens")
    assert len(results) == 4
    sizes = [pygame.image.load(str(f)).get_size() for f in results]
    assert sizes == [(1024, 768), (1600, 900), (1024, 768), (1600, 900)]
    assert all(f.stat().st_size > 20000 for f in results)



@pytest.mark.parametrize("size", [(1600, 900), (1920, 1080), (1440, 900)])
def test_large_window_hud_scales_its_entire_ui_and_click_zones(size):
    screen, world = staged(size, hull="bastion")
    hud = Hud(screen, world)
    hud.help_until = 0
    hud.draw(world, False, mouse=(-100, -100))
    assert hud.virtual
    status = hud.panels[0]
    assert status.w >= 330 * min(size[0] / 1280, size[1] / 720) - 2
    assert screen.get_rect().contains(status)
    assert hud.minimap_rect is not None
    assert screen.get_rect().contains(hud.minimap_rect)
    assert hud.over_ui(hud.minimap_rect.center)
    assert not hud.over_ui((size[0] // 2, size[1] // 2))
    for system in ("shields", "engines", "weapons"):
        rect = next(rect for rect, action in hud.buttons if action == ("pip", system))
        assert hud.action_at(rect.center) == ("pip", system)
        assert screen.get_rect().contains(rect)
    assert hud._overlay.get_size() == hud.viewport.size


def test_hud_large_text_and_colorblind_controls_keep_real_hitboxes():
    screen, world = staged((1600, 900), hull="bastion")
    try:
        ui.configure(large_font=False, colorblind=False)
        normal_height = ui.Fonts.get(18).get_height()
        ui.configure(large_font=True, colorblind=True)
        hud = Hud(screen, world)
        hud.help_until = 0
        hud.draw(world, False, mouse=(-100, -100))
        assert hud.virtual
        assert ui.Fonts.get(18).get_height() > normal_height
        assert ui.BAD == (240, 120, 30)
        assert hud.action_at(next(r.center for r, action in hud.buttons
                                  if action == ("pip", "engines"))) == ("pip", "engines")
        # A virtual HUD must not falsely block clicks in empty sea.
        assert not hud.over_ui((screen.get_width() // 2,
                                screen.get_height() // 2))
    finally:
        ui.configure(large_font=False, colorblind=False)
        ui.Fonts.reset()
