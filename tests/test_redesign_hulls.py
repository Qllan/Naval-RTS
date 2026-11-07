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
    assert displayed == set(range(len(hull.hull.slots)))


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
        cargo_used = 0
        player = Ship("needle", (0, 0))

        def hull_offer(self, key):
            return (1000, 1000)

    ui._shipyard(FakeWorld(), pygame.Rect(35, 90, 1050, 470))
    selected_rows = [idx for rect, kind, idx in ui.zones if kind == "row"]
    assert len(selected_rows) <= 8
    assert ui.sel in selected_rows
    assert max(selected_rows) - min(selected_rows) == len(selected_rows) - 1


def test_weapon_arc_geometry_is_consistent_with_hull_directions():
    from nine.port_ui import weapon_arc_points

    forward = weapon_arc_points((100, 100), 0, 0, 20)
    starboard = weapon_arc_points((100, 100), 90, 0, 20)
    aft = weapon_arc_points((100, 100), 180, 0, 20)
    port = weapon_arc_points((100, 100), -90, 0, 20)
    assert forward[-1] == (100, 80)
    assert starboard[-1] == (120, 100)
    assert aft[-1] == (100, 120)
    assert port[-1] == (80, 100)
    wide = weapon_arc_points((100, 100), 0, 270, 20)
    assert len(wide) > 15
    assert wide[0] == (100, 100)


def test_fitting_schematic_draws_selected_weapon_arc():
    import pygame
    from nine.port_ui import PortUI

    pygame.font.init()
    screen = pygame.Surface((1200, 800))
    ui = PortUI(screen)
    ship = Ship("bastion", (0, 0))
    body = pygame.Rect(50, 100, 1000, 470)
    ui.sel = 0
    ui._hull_layout(ship, body, len(ship.hull.slots))
    assert any(kind == "slot" for _, kind, _ in ui.zones)
    # Candidate arc can be narrower than the hardpoint, but without
    # modifying the live ship or the fitting.
    candidate = list(ship.fit)
    candidate[0] = "torpedo_m"
    assert candidate[0] != ship.fit[0]
    ui._hull_layout(ship, body, len(ship.hull.slots), candidate)
    assert ship.fit[0] == "cannon_m"



@pytest.mark.parametrize("key", NEW_HULLS)
def test_all_new_ship_systems_have_real_schematic_coordinates(key):
    from nine.gfx.ship_art import half_width

    hull = HULLS[key]
    for slot in hull.slots:
        if slot.category == "weapon":
            assert slot.diagram_pos is None
            continue
        assert slot.diagram_pos is not None
        x, y = slot.diagram_pos
        assert abs(y) < half_width(key, x) - 0.1


@pytest.mark.parametrize("key", NEW_HULLS)
def test_entire_ship_schematic_is_clickable_and_preview_safe(key):
    import pygame
    from nine.port_ui import PortUI

    pygame.font.init()
    screen = pygame.Surface((1280, 720))
    port = PortUI(screen)
    ship = Ship(key, (0, 0))
    body = pygame.Rect(140, 156, 1032, 470)
    port.sel = next(i for i, slot in enumerate(ship.hull.slots)
                    if slot.category == "reactor")
    saved_fit = tuple(ship.fit)
    port._hull_layout(ship, body, len(ship.hull.slots))
    zones = {idx: rect for rect, kind, idx in port.zones if kind == "slot"}
    assert set(zones) == set(range(len(ship.hull.slots)))
    assert port._zone_at(zones[port.sel].center) == ("slot", port.sel)
    assert ship.fit == list(saved_fit)

    candidate = list(ship.fit)
    candidate[port.sel] = None
    port.zones.clear()
    port._hull_layout(ship, body, len(ship.hull.slots), candidate)
    assert port._zone_at(zones[port.sel].center) == ("slot", port.sel)
    assert ship.fit == list(saved_fit)


def test_legacy_hulls_have_unchanged_internal_layout_defaults():
    for key in ("scout", "corvette", "torpedo_boat", "cruiser", "barge"):
        assert all(slot.diagram_pos is None for slot in HULLS[key].slots
                   if slot.category != "weapon")


@pytest.mark.parametrize("key", NEW_HULLS)
def test_schematic_labels_follow_longitudinal_mount_order(key):
    from nine.port_ui import schematic_side_slots

    hull = HULLS[key]
    columns = schematic_side_slots(hull.slots)
    assert len(columns) == 2
    displayed = {i for col in columns for i, _ in col}
    expected = {i for i, slot in enumerate(hull.slots) if slot.category != "weapon"}
    assert displayed == expected
    for column in columns:
        x = [slot.diagram_pos[0] for _, slot in column]
        assert x == sorted(x, reverse=True)


def test_legacy_hull_schematic_falls_back_to_slot_order():
    from nine.port_ui import schematic_side_slots

    for key in ("scout", "corvette", "barge"):
        columns = schematic_side_slots(HULLS[key].slots)
        for column in columns:
            indices = [i for i, _ in column]
            assert indices == sorted(indices)


def test_schematic_focus_rect_remains_large_for_many_slots():
    import pygame
    from nine.port_ui import schematic_layout_rect

    body = pygame.Rect(148, 156, 1032, 470)
    assert schematic_layout_rect(body, 11).h >= 105
    assert schematic_layout_rect(body, 30).h < 105
    expanded = schematic_layout_rect(body, 30, focus=True)
    assert expanded.height >= 400
    assert expanded.left == body.x - 8
    assert expanded.bottom <= body.bottom


def test_blueprint_mode_toggle_keyboard_and_button():
    import pygame
    from nine.port_ui import PortUI, TABS
    from nine.world import World

    pygame.font.init()
    screen = pygame.Surface((1280, 720))
    world = World(seed=9, first_event=1e9)
    world.player = Ship("manta", world.port)
    port = PortUI(screen)
    port.tab = TABS.index("Оснащение")
    assert not port.blueprint_focus
    assert port.handle_key(pygame.K_v, world) is None
    assert port.blueprint_focus
    body = pygame.Rect(148, 156, 1032, 470)
    port._fitting(world, body)
    schematic = {index for rect,kind,index in port.zones if kind == "slot"}
    assert schematic == set(range(len(world.player.hull.slots)))
    button = next(rect for rect, kind, name in port.zones
                  if kind == "button" and name == "blueprint")
    port.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                       {"pos":button.center, "button":1}),world)
    assert not port.blueprint_focus
    assert port.handle_key(pygame.K_v, world) is None
    assert port.blueprint_focus


def test_blueprint_focus_expands_all_three_schematics():
    import pygame
    from nine.port_ui import PortUI

    pygame.font.init()
    screen = pygame.Surface((1280, 720))
    body = pygame.Rect(148, 156, 1032, 470)
    for key in NEW_HULLS:
        port = PortUI(screen)
        port.blueprint_focus = True
        ship = Ship(key, (0, 0))
        port._hull_layout(ship, body, len(ship.hull.slots), focus=True)
        click_zones = {index:rect for rect,kind,index in port.zones if kind == "slot"}
        assert set(click_zones) == set(range(len(ship.hull.slots)))
        for index, zone in click_zones.items():
            assert zone.width > 0 and zone.height > 0


@pytest.mark.parametrize("key", NEW_HULLS)
def test_engineering_snapshot_matches_ship_simulation_without_mutation(key):
    from nine.port_ui import engineering_snapshot
    from nine.ship import CARGO_MASS

    ship = Ship(key, (0, 0))
    before = (ship.cargo_mass, ship.mass, ship.power_balance(0.0),
              tuple(ship.fit), dict(ship.pips))
    data = engineering_snapshot(ship, 12)
    assert data["hull_mass"] == ship.hull.mass
    assert data["module_mass"] == ship.module_mass
    assert data["cargo_mass"] == pytest.approx(12 * CARGO_MASS)
    assert data["total_mass"] == pytest.approx(ship.hull.mass + ship.module_mass + 12 * CARGO_MASS)
    assert data["balance_clear"] == pytest.approx(ship.power_balance(0.0))
    assert data["balance_veil"] == pytest.approx(ship.power_balance(0.8))
    assert (ship.cargo_mass, ship.mass, ship.power_balance(0.0),
            tuple(ship.fit), dict(ship.pips)) == before
    assert engineering_snapshot(ship, 0)["speed"] == pytest.approx(ship.base_top_speed())


def test_engineering_snapshot_shows_reactor_and_engine_tradeoffs():
    from nine.port_ui import engineering_snapshot

    ship = Ship("manta", (0, 0))
    reactor = next(i for i, slot in enumerate(ship.hull.slots) if slot.category == "reactor")
    engine = next(i for i, slot in enumerate(ship.hull.slots) if slot.category == "engine")
    pips = 4
    current = engineering_snapshot(ship, 0, engine_pips=pips)

    fit = list(ship.fit)
    fit[reactor] = "reactor_m2"
    reactor_up = engineering_snapshot(Ship("manta", (0, 0), fit=fit), 0, engine_pips=pips)
    assert reactor_up["power_output"] > current["power_output"]
    assert reactor_up["balance_clear"] > current["balance_clear"]
    assert reactor_up["total_mass"] > current["total_mass"]

    fit = list(ship.fit)
    fit[engine] = "engine_m2"
    faster = engineering_snapshot(Ship("manta", (0, 0), fit=fit), 0, engine_pips=pips)
    assert faster["speed"] > current["speed"]
    assert faster["upkeep_clear"] > current["upkeep_clear"]


def test_engineering_panel_renders_without_modifying_world():
    import pygame
    from nine.port_ui import PortUI
    from nine.world import World

    pygame.font.init()
    surface = pygame.Surface((1280, 720))
    port = PortUI(surface)
    world = World(seed=9, first_event=1e9)
    world.player = Ship("bastion", world.port)
    world.captain.credits = 12000
    before = (world.captain.credits, list(world.player.fit), world.player.cargo_mass)
    slot = next(i for i, s in enumerate(world.player.hull.slots) if s.category == "reactor")
    fit = list(world.player.fit)
    fit[slot] = "reactor_m2"
    preview = Ship("bastion", world.port, fit=fit)
    port._engineering_panel(world, pygame.Rect(148, 156, 1032, 470), preview)
    assert (world.captain.credits, list(world.player.fit), world.player.cargo_mass) == before
