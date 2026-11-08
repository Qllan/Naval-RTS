"""R1.2 industrial ship module visual contracts, no game playtest."""

import pygame
import pytest

from nine.gfx.camera import Camera
from nine.gfx.ship_art import ShipArt, _indexed_modules, build_hull, hull_length
from nine.hulls import HULLS
from nine.modules import MODULES
from nine.ship import Ship, fit_problems
from tools.preview_module_fit import VARIANTS, render, ship_image, variants


@pytest.mark.parametrize("key", ("needle", "manta", "bastion"))
def test_r12_loadout_variants_are_compatible_and_keep_slot_geometry(key):
    baseline, refitted = variants(key)
    assert fit_problems(refitted.hull, refitted.fit) == []
    assert baseline.hull is refitted.hull
    assert baseline.hull.slots == refitted.hull.slots
    assert baseline.hull.shape == refitted.hull.shape
    assert baseline.fit != refitted.fit
    assert len(refitted.fit) == len(baseline.fit)


@pytest.mark.parametrize("key", ("needle", "manta", "bastion"))
def test_r12_static_components_are_rendered_at_real_slots_and_change_pixels(key):
    baseline, refitted = variants(key)
    images = []
    for ship in (baseline, refitted):
        modules = tuple((i, m) for i, _, m in ship.modules()
                        if m.category != "weapon")
        rendered, _ = build_hull(key, "player", modules, 0)
        images.append(pygame.image.tostring(rendered, "RGBA"))
    assert images[0] != images[1]
    assert pygame.image.tostring(ship_image(baseline), "RGBA") != pygame.image.tostring(
        ship_image(refitted), "RGBA")


def test_r12_master_cache_keys_contain_index_and_specific_module():
    ship = Ship("bastion", (0, 0))
    art = ShipArt()
    key_before, _ = art._hull_master(ship, "player")
    ship.set_module(5, "reactor_m2")
    key_after, _ = art._hull_master(ship, "player")
    assert key_before != key_after
    assert (5, "reactor_m") in key_before[2]
    assert (5, "reactor_m2") in key_after[2]

    # The same module keys exchanged between two utility slots must
    # invalidate a cached sprite rather than being sorted by category.
    ship.set_module(9, "smoke")
    ship.set_module(10, "ecm")
    key_a, _ = art._hull_master(ship, "player")
    ship.set_module(9, "ecm")
    ship.set_module(10, "smoke")
    key_b, _ = art._hull_master(ship, "player")
    assert key_a != key_b


def test_r12_indexed_conversion_supports_old_tool_callers():
    hull = HULLS["manta"]
    mods = [(i, MODULES[key]) for i, key in enumerate(hull.default_fit)
            if key and hull.slots[i].category != "weapon"]
    old_format = [(m.key, m) for _, m in mods]
    assert _indexed_modules("manta", old_format) == tuple(mods)
    assert _indexed_modules("manta", mods) == tuple(mods)


def test_r12_legacy_hulls_continue_to_render_with_their_original_modules():
    ship = Ship("cruiser", (0, 0))
    art = ShipArt()
    key, (sprite, shadow) = art._hull_master(ship, "player")
    assert key[0] == "cruiser"
    assert sprite.get_size() == shadow.get_size()
    assert sprite.get_bounding_rect().width > 0


def test_r12_tactical_lod_distinguishes_missile_and_gun_silhouettes():
    a = Ship("needle", (0, 0))
    fit = list(a.fit)
    fit[0] = "missile_s"
    b = Ship("needle", (0, 0), fit=fit)
    cam = Camera(220, 220, zoom=52 / hull_length("needle"))
    cam.snap((0, 0))
    images = []
    for ship in (a, b):
        stage = pygame.Surface((220, 220))
        stage.fill((5, 17, 27))
        art = ShipArt()
        art.draw(stage, cam, ship, "player", shadow=None)
        assert not art.masters
        images.append(pygame.image.tostring(stage, "RGB"))
    assert images[0] != images[1]


def test_r12_review_sheet_is_generated_from_live_renderer(tmp_path):
    output = tmp_path / "module-variants.png"
    render(output)
    assert output.exists() and output.stat().st_size > 10000
    image = pygame.image.load(str(output))
    assert image.get_size() == (1800, 1470)
