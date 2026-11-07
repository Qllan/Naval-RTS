"""Первые проверяемые условия редизайна корпусов R0."""

import pytest

from nine.gfx.ship_art import PROFILES, build_hull, hull_length
from nine.hulls import HULLS, PLAYER_HULLS
from nine.ship import Ship, fit_problems


NEW_HULLS = ("needle", "manta", "bastion")


@pytest.mark.parametrize("key", NEW_HULLS)
def test_new_hulls_have_compatible_default_fit(key):
    hull = HULLS[key]
    assert hull in PLAYER_HULLS
    assert hull.series
    assert hull.visual_style == "industrial_sci_fi"
    assert len(hull.slots) == len(hull.default_fit)
    assert fit_problems(hull, hull.default_fit) == []
    ship = Ship(key, (0, 0))
    assert ship.engine is not None
    assert ship.reactor is not None
    assert ship.alive


@pytest.mark.parametrize("key", NEW_HULLS)
def test_new_hulls_render_without_old_hardcoded_profile(key):
    assert key in PROFILES
    assert len(PROFILES[key]) >= 5
    assert hull_length(key) > 30
    image, shadow = build_hull(key, "player", (), 0)
    assert image.get_width() > 0
    assert shadow.get_size() == image.get_size()


def test_new_hulls_are_different_footprints_and_slot_layouts():
    shapes = {HULLS[key].shape for key in NEW_HULLS}
    weapon_slots = {
        tuple((slot.size, slot.pos, slot.arc)
              for slot in HULLS[key].slots if slot.category == "weapon")
        for key in NEW_HULLS
    }
    assert len(shapes) == len(NEW_HULLS)
    assert len(weapon_slots) == len(NEW_HULLS)


def test_role_comes_from_fit_not_fixed_hull_class():
    hull = HULLS["needle"]
    gun_fit = list(hull.default_fit)
    missile_fit = list(gun_fit)
    missile_fit[0] = "missile_s"
    assert fit_problems(hull, gun_fit) == []
    assert fit_problems(hull, missile_fit) == []
    gun = Ship("needle", (0, 0), fit=gun_fit)
    missile = Ship("needle", (0, 0), fit=missile_fit)
    assert gun.hull is missile.hull
    assert gun.weapons[0].defn.key != missile.weapons[0].defn.key


def test_legacy_hull_keys_remain_available_for_saves():
    for key in ("scout", "corvette", "torpedo_boat", "cruiser", "barge", "raider", "capsule"):
        assert key in HULLS


def test_new_hulls_have_visual_blueprints():
    from nine.gfx.ship_art import half_width, mast_position, superstructures
    for key in NEW_HULLS:
        hull = HULLS[key]
        visual = hull.visual
        assert visual is not None
        assert superstructures(key) == visual.superstructures
        assert mast_position(key) == visual.mast
        assert visual.superstructures
        assert len(visual.deck_ribs) >= 4
        assert all(0 < y < 1 for y in visual.deck_strips)
        assert all(half_width(key, x) > 1 for x in visual.deck_ribs)


def test_legacy_art_still_uses_its_original_metadata():
    from nine.gfx.ship_art import mast_position, superstructures
    assert HULLS["scout"].visual is None
    assert mast_position("scout") == (-7.5, 0)
    assert len(superstructures("scout")) == 1


def test_fitting_diagram_has_clickable_mounts():
    import pygame
    from nine.port_ui import PortUI
    pygame.font.init()
    screen = pygame.Surface((1200, 800))
    port = PortUI(screen)
    hull = Ship("manta", (0, 0))
    port._hull_layout(hull, pygame.Rect(50, 100, 1000, 470), len(hull.hull.slots))
    displayed = {index for _, kind, index in port.zones if kind == "slot"}
    expected = {i for i, slot in enumerate(hull.hull.slots) if slot.category == "weapon"}
    assert displayed == expected


@pytest.mark.parametrize("key", NEW_HULLS)
def test_new_hulls_have_distinct_functional_deck_details(key):
    from dataclasses import replace
    import pygame

    hull = HULLS[key]
    visual = hull.visual
    assert visual is not None
    assert visual.details
    allowed = {"sensor_rail", "cargo_cell", "armor_plate", "radiator"}
    from nine.gfx.ship_art import half_width
    for detail in visual.details:
        assert detail.kind in allowed
        x, y = detail.pos
        length, width = detail.size
        assert length > 0 and width > 0
        for end in (x - length / 2, x, x + length / 2):
            assert abs(y) + width / 2 < half_width(key, end) + 0.05

    complete, _ = build_hull(key, "player", (), 0)
    without = replace(hull, visual=replace(visual, details=()))
    from nine.hulls import HULLS as registry
    original = registry[key]
    try:
        registry[key] = without
        plain, _ = build_hull(key, "player", (), 0)
    finally:
        registry[key] = original
    assert pygame.image.tostring(complete, "RGBA") != pygame.image.tostring(plain, "RGBA")


def test_new_hull_visual_kits_are_not_the_same():
    kits = {tuple(detail.kind for detail in HULLS[key].visual.details) for key in NEW_HULLS}
    assert len(kits) == len(NEW_HULLS)



@pytest.mark.parametrize("key", NEW_HULLS)
def test_compact_hull_is_rendered_at_distant_zoom(key):
    import pygame
    from nine.gfx.camera import Camera
    from nine.gfx.ship_art import ShipArt

    color = (7, 18, 25)
    canvas = pygame.Surface((160, 160))
    canvas.fill(color)
    camera = Camera(160, 160, zoom=0.55)
    camera.snap((0, 0))
    ship = Ship(key, (0, 0), -90)
    renderer = ShipArt()
    renderer.draw(canvas, camera, ship, "player", shadow=None)
    assert canvas.get_at((80, 80))[:3] != color
    assert not renderer.masters  # no expensive sprite assembly at far zoom

    camera.zoom = 1.75
    renderer.draw(canvas, camera, ship, "player", shadow=None)
    assert renderer.masters  # full detail is still used up close


def test_shipyard_window_supports_large_hull_catalog():
    from nine.port_ui import shipyard_window

    assert shipyard_window(0, 0) == (0, 0)
    assert shipyard_window(3, 2, 8) == (0, 3)
    for i in range(60):
        first, end = shipyard_window(60, i, 8)
        assert end - first == 8
        assert first <= i < end
    assert shipyard_window(60, 59, 8) == (52, 60)


def test_shipyard_display_preserves_global_row_indices(monkeypatch):
    import pygame
    import nine.port_ui as port_module
    from nine.port_ui import PortUI

    pygame.font.init()
    screen = pygame.Surface((1200, 800))
    ui = PortUI(screen)

    # Existing definitions are replicated for UI stress testing only.
    models = list(port_module.PLAYER_HULLS) * 8
    monkeypatch.setattr(port_module, "PLAYER_HULLS", models)
    ui.sel = 28

    class FakeWorld:
        t = 0.0
        player = Ship("needle", (0, 0))

        def hull_offer(self, key):
            return (1000, 1000)

    ui._shipyard(FakeWorld(), pygame.Rect(35, 90, 1050, 470))
    selected_rows = [idx for rect, kind, idx in ui.zones if kind == "row"]
    assert len(selected_rows) <= 8
    assert ui.sel in selected_rows
    assert max(selected_rows) - min(selected_rows) == len(selected_rows) - 1
