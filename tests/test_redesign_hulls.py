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
    allowed = {"sensor_rail", "cargo_cell", "armor_plate", "radiator",
               "spine_channel", "shoulder_guard", "service_hatch"}
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


@pytest.mark.parametrize("key", NEW_HULLS)
def test_engineering_panel_reports_gameplay_layout_factor(key):
    from nine.port_ui import engineering_snapshot

    ship = Ship(key, (0, 0))
    engineering = engineering_snapshot(ship)
    assert engineering["layout_turn_pct"] == pytest.approx(ship.layout_turn_factor * 100)
    assert engineering["side_shift"] == pytest.approx(abs(ship.side_balance) * 100)
    assert engineering["turn"] == pytest.approx(
        ship.hull.turn_rate * min(1.15, ship.mass_factor()) * ship.layout_turn_factor)
    assert engineering["layout_turn_pct"] <= 100


def test_manta_bilateral_weapon_fit_improves_mass_symmetry():
    from nine.port_ui import engineering_snapshot

    ship = Ship("manta", (0, 0))
    new_fit = list(ship.fit)
    new_fit[1] = "cannon_m"
    modified = Ship("manta", (0, 0), fit=new_fit)
    a, b = engineering_snapshot(ship), engineering_snapshot(modified)
    assert b["side_shift"] < a["side_shift"]
    assert b["module_mass"] > a["module_mass"]
    # Better bilateral balance does not guarantee a faster ship: mass matters.
    assert b["speed"] < a["speed"]


def test_engineering_notices_are_read_only_and_use_real_power_model():
    from nine.engineering import engineering_notices

    hull = HULLS["manta"]
    reactor = next(i for i, s in enumerate(hull.slots) if s.category == "reactor")
    fit = list(hull.default_fit)
    fit[reactor] = "reactor_s"
    ship = Ship("manta", (0, 0), fit=fit)
    original = (list(ship.fit), ship.module_mass, ship.capacitor, ship.cargo_mass)
    notices = engineering_notices(ship)
    assert "veil_deficit" in {n.code for n in notices}
    assert any("Пелене" in n.text for n in notices)
    assert all(n.text and n.short for n in notices)
    assert (list(ship.fit), ship.module_mass, ship.capacitor, ship.cargo_mass) == original


def test_heavy_fit_advisory_is_not_a_new_fitting_limit():
    from nine.engineering import engineering_notices
    from nine.ship import fit_problems

    ship = Ship("manta", (0, 0))
    notices = engineering_notices(ship, cargo=50)
    assert "heavy_fit" in {n.code for n in notices}
    assert fit_problems(ship.hull, ship.fit) == []


def test_veil_risk_does_not_automatically_block_installation():
    from nine.engineering import engineering_notices
    from nine.world import World

    world = World(seed=9, first_event=1e9)
    world.player = Ship("manta", world.port)
    world.captain.credits = 10000
    index = next(i for i,s in enumerate(world.player.hull.slots)
                 if s.category == "reactor")
    fit = list(world.player.fit)
    fit[index] = "reactor_s"
    candidate = Ship("manta", world.port, fit=fit)
    assert "veil_deficit" in {n.code for n in engineering_notices(candidate)}
    assert world.install_problem(index, "reactor_s") is None
    assert world.player.fit[index] != "reactor_s"


def test_missing_reactor_in_preview_is_not_installed():
    from nine.engineering import engineering_notices

    ship = Ship("needle", (0, 0))
    fit = list(ship.fit)
    reactor = next(i for i,s in enumerate(ship.hull.slots) if s.category == "reactor")
    fit[reactor] = None
    candidate = Ship("needle", (0, 0), fit=fit)
    assert "veil_deficit" in {n.code for n in engineering_notices(candidate)}
    assert ship.fit[reactor] is not None


def test_engineering_risk_preview_does_not_purchase_module():
    import pygame
    from nine.port_ui import PortUI
    from nine.world import World

    pygame.font.init()
    screen = pygame.Surface((1280, 720))
    world = World(seed=9, first_event=1e9)
    world.player = Ship("manta", world.port)
    world.captain.credits = 10000
    port = PortUI(screen)
    port.tab = 2
    port.picker = True
    port.sel = next(i for i,s in enumerate(world.player.hull.slots)
                    if s.category == "reactor")
    port.slot = port.sel
    port.pick_sel = next(i for i,(_,key) in enumerate(port.picker_items(world))
                         if key == "reactor_s")
    before = (tuple(world.player.fit), tuple(world.captain.storage),
              world.captain.credits)
    port.draw(world, dt=0.4)
    assert (tuple(world.player.fit), tuple(world.captain.storage),
            world.captain.credits) == before
    assert any(kind == "pick" for _,kind,_ in port.zones)


@pytest.mark.parametrize("key", NEW_HULLS)
def test_r11_visual_profile_is_separate_from_gameplay_geometry(key):
    from nine.gfx.ship_art import half_width, outline

    hull = HULLS[key]
    visual = hull.visual
    assert visual is not None and len(visual.render_profile) >= 9
    profile = visual.render_profile
    assert profile[0] == (max(x for x, _ in hull.shape), 0)
    assert profile[-1] == (min(x for x, _ in hull.shape), 0)
    assert all(profile[i][0] > profile[i + 1][0] for i in range(len(profile) - 1))
    assert all(y >= 0 for x, y in profile)
    assert len(outline(key)) >= 16
    assert tuple(hull.shape) == {
        "needle": ((30, 0), (20, 3), (4, 5), (-17, 5), (-28, 2),
                   (-30, 0), (-28, -2), (-17, -5), (4, -5), (20, -3)),
        "manta": ((27, 0), (17, 9), (5, 14), (-18, 13), (-28, 7),
                  (-29, 0), (-28, -7), (-18, -13), (5, -14), (17, -9)),
        "bastion": ((58, 0), (53, 2), (45, 5.2), (34, 8.2), (20, 10.3),
                    (6, 11.6), (-17, 12), (-34, 11.3), (-46, 8.2), (-53, 4), (-56, 0),
                    (-53, -4), (-46, -8.2), (-34, -11.3), (-17, -12), (6, -11.6),
                    (20, -10.3), (34, -8.2), (45, -5.2), (53, -2)),
    }[key]
    for slot in hull.slots:
        if slot.category == "weapon":
            x, y = slot.pos
            assert abs(y) <= half_width(key, x) + 0.5


@pytest.mark.parametrize("key", NEW_HULLS)
def test_r11_new_citadels_and_service_details_are_functional(key):
    from nine.gfx.ship_art import superstructures

    visual = HULLS[key].visual
    kinds = {d.kind for d in visual.details}
    assert {"spine_channel", "shoulder_guard", "service_hatch"} <= kinds
    assert len(superstructures(key)) >= 2


def test_r11_palette_is_style_bible_for_new_hulls_but_not_legacy():
    from nine.gfx.palette import SHIP_PALETTES
    from nine.gfx.ship_art import industrial_palette
    from nine.gfx.style_tokens import rgb

    approved = industrial_palette("player")
    pirate = industrial_palette("pirate")
    assert approved.hull == rgb("steel_hull")
    assert approved.deck == rgb("steel_deck")
    assert approved.armor == rgb("steel_armor")
    assert approved.accent == rgb("signal_friendly")
    assert pirate.accent == rgb("signal_pirate")
    assert SHIP_PALETTES["player"].hull != approved.hull


@pytest.mark.parametrize("key", NEW_HULLS)
def test_r11_lod_switches_at_screen_space_thresholds(key):
    import pygame
    from nine.gfx.camera import Camera
    from nine.gfx.ship_art import ShipArt, hull_length
    from nine.gfx.style_tokens import lod_for_length

    background = (8, 25, 35)
    canvas = pygame.Surface((180, 180))
    cam = Camera(180, 180, zoom=0.2)
    cam.snap((0, 0))
    art = ShipArt()
    ship = Ship(key, (0, 0), -90)

    for target_length, expected in ((18, "far"), (48, "tactical"), (110, "inspection")):
        cam.zoom = target_length / hull_length(key)
        canvas.fill(background)
        assert lod_for_length(hull_length(key) * cam.zoom) == expected
        art.draw(canvas, cam, ship, "player", shadow=None)
        assert canvas.get_at((90, 90))[:3] != background
        if expected != "inspection":
            assert not art.masters
        else:
            assert art.masters


def test_r11_three_hull_master_sprites_have_distinct_pixels():
    import pygame
    images = [build_hull(key, "player", (), 0)[0] for key in NEW_HULLS]
    assert len({(img.get_size(), pygame.image.tostring(img, "RGBA")) for img in images}) == 3


def test_r11_equipment_turret_respects_hull_material_without_recoloring_legacy():
    import pygame
    from nine.gfx.ship_art import build_turret

    regular = build_turret("cannon_m", "player", industrial=False)
    industrial = build_turret("cannon_m", "player", industrial=True)
    assert regular.get_size() == industrial.get_size()
    assert pygame.image.tostring(regular, "RGBA") != pygame.image.tostring(industrial, "RGBA")
    # Existing gameplay module key remains identical; only pigments change.
    assert "cannon_m" in Ship("manta", (0, 0)).fit


def test_bastion_r113_is_real_long_narrow_capital_hull():
    from nine.gfx.ship_art import PROFILES, half_width

    hull = HULLS["bastion"]
    xs = [x for x, _ in hull.shape]
    ys = [y for _, y in hull.shape]
    assert max(xs) - min(xs) == 114
    assert max(ys) - min(ys) == 24
    assert (max(xs) - min(xs)) / (max(ys) - min(ys)) == pytest.approx(4.75)
    assert max(y for _, y in PROFILES["bastion"]) == 11.5
    assert half_width("bastion", 49) < half_width("bastion", 0)
    assert half_width("bastion", -51) < half_width("bastion", -10)
    assert max(xs) - min(xs) > 1.9 * (max(x for x, _ in HULLS["manta"].shape)
                                    - min(x for x, _ in HULLS["manta"].shape))


def test_bastion_r113_relocated_mounts_stay_inside_new_body():
    from nine.gfx.ship_art import half_width

    hull = HULLS["bastion"]
    assert hull.radius == 58
    assert (hull.hp, hull.mass, hull.speed_mult, hull.turn_rate) == (340, 230, 0.76, 62)
    assert [slot.pos for slot in hull.slots if slot.category == "weapon"] == [
        (35, 0), (-30, 0), (-4, -8.5), (-4, 8.5)]
    assert len(hull.default_fit) == len(hull.slots)
    assert fit_problems(hull, hull.default_fit) == []
    for slot in hull.slots:
        pos = slot.pos if slot.category == "weapon" else slot.diagram_pos
        if pos is None:
            continue
        assert abs(pos[1]) <= half_width("bastion", pos[0]) + 0.1


def test_bastion_r113_deck_details_fit_narrow_art_outline():
    from nine.gfx.ship_art import half_width

    visual = HULLS["bastion"].visual
    assert visual is not None
    for detail in visual.details:
        px, py = detail.pos
        lx, ly = detail.size
        for x in (px - lx / 2, px, px + lx / 2):
            assert abs(py) + ly / 2 < half_width("bastion", x) + 0.05


def test_bastion_r112_before_after_preview_restores_catalog_state(tmp_path):
    from nine.gfx.ship_art import PROFILES
    from tools.preview_bastion_compare import OLD_PROFILE, render

    hull_before, profile_before = HULLS["bastion"], tuple(PROFILES["bastion"])
    assert tuple(profile_before) != OLD_PROFILE
    dest = tmp_path / "bastion-comparison.png"
    render(dest)
    assert dest.exists() and dest.stat().st_size > 1000
    assert HULLS["bastion"] is hull_before
    assert tuple(PROFILES["bastion"]) == profile_before


def test_bastion_r113_projectile_hit_matches_rotated_hull_not_huge_disk():
    from pygame.math import Vector2
    from nine.spatial import ship_overlaps, ShipCollisionGrid

    ship = Ship("bastion", (500, 500), 0)
    assert ship_overlaps(ship, Vector2(540, 500))
    assert not ship_overlaps(ship, Vector2(500, 540))
    assert ship_overlaps(ship, Vector2(500, 513), padding=4)
    ship.angle = 90
    assert ship_overlaps(ship, Vector2(500, 540))
    assert not ship_overlaps(ship, Vector2(540, 500))
    grid = ShipCollisionGrid([ship])
    assert grid.first_hit(Vector2(500, 540)) is ship
    assert grid.first_hit(Vector2(540, 500)) is None


def test_bastion_r113_keel_island_collision_without_phantom_side_contact():
    import random
    from pygame.math import Vector2
    from nine.islands import Island, collide_ship

    bastion = Ship("bastion", (500, 500), 0)
    off_side = Island(Vector2(500, 540), 6, 0)
    assert collide_ship(bastion, [off_side], random.Random(1)) == 0
    assert bastion.pos == Vector2(500, 500)
    bow_rock = Island(Vector2(552, 500), 8, 0)
    bastion.vel = Vector2(70, 0)
    impact = collide_ship(bastion, [bow_rock], random.Random(1))
    assert impact > 0
    assert bastion.pos.x < 500
