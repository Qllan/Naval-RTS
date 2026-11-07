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
