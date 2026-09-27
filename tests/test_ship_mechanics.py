"""Энергораспределение, группы огня, нагрев, снаряды, пожары и затопление."""

import random

import pytest
from pygame.math import Vector2

from nine.combat import spread_for, try_fire
from nine.modules import MODULES
from nine.ship import CREW_FIRE_TIME, HEAT_RECOVER, Ship
from nine.world import AMMO_PACK, Controls, World

DT = 1 / 60


def run(ship, seconds, **kw):
    for _ in range(int(seconds / DT)):
        ship.update(DT, kw.get("throttle", 0.0), 0.0, False, kw.get("density", 0.0))


# --- энергия -------------------------------------------------------------

def test_pips_move_from_the_richest_system_and_cap_at_four():
    s = Ship("scout", (0, 0))
    assert s.add_pip("weapons")
    assert s.pips["weapons"] == 3 and s.pips["shields"] + s.pips["engines"] == 3
    s.add_pip("weapons")
    assert s.pips["weapons"] == 4
    assert not s.add_pip("weapons")
    assert sum(s.pips.values()) == 6
    s.reset_pips()
    assert s.pips == {"shields": 2, "engines": 2, "weapons": 2}


def test_pips_change_speed_reload_and_shield_regen():
    fast, slow = Ship("scout", (0, 0)), Ship("scout", (0, 0))
    fast.set_pips(1, 4, 1)
    slow.set_pips(4, 0, 2)
    assert fast.base_top_speed() > slow.base_top_speed()
    guns = Ship("scout", (0, 0))
    guns.set_pips(1, 1, 4)
    assert guns.reload_mult() < Ship("scout", (0, 0)).reload_mult()
    a, b = Ship("scout", (0, 0)), Ship("scout", (0, 0))
    b.set_pips(4, 1, 1)
    a.shield = b.shield = 0
    run(a, 2)
    run(b, 2)
    assert b.shield > a.shield


# --- группы огня ------------------------------------------------------------

def test_default_groups_and_cycling():
    s = Ship("cruiser", (0, 0), fit=["cannon_m", "missile_m", "autocannon_s", "autocannon_s", "engine_m",
                                     "reactor_m", "shield_m", "armor_s", "sensor_s", None, None])
    groups = {w.defn.key: w.group for w in s.weapons}
    assert groups["cannon_m"] == 1 and groups["missile_m"] == 2
    assert s.cycle_group(0) == 2 and s.cycle_group(0) == 0 and s.cycle_group(0) == 1
    assert s.cycle_group(4) is None                       # двигатель — не оружие
    s.cycle_group(0)
    s.set_module(0, "em_m")                               # новая установка — группа по умолчанию
    assert s.weapons[0].group == 1


def test_world_fires_only_the_held_group():
    w = World(seed=1, first_event=1e9)
    w.player = Ship("scout", (4000, 4000), 0)
    w.pirate_spawn_cd = 1e9
    w.player.cycle_group(0)                               # автопушка → ПКМ
    for _ in range(30):
        w.update(DT, Controls(fire=True, aim=Vector2(4400, 4000)))
    assert not [p for p in w.projectiles if p.side == "player"]
    for _ in range(30):
        w.update(DT, Controls(fire2=True, aim=Vector2(4400, 4000)))
    assert [p for p in w.projectiles if p.side == "player"]


# --- нагрев -----------------------------------------------------------------

def test_sustained_fire_overheats_and_recovers():
    rng = random.Random(1)
    s = Ship("scout", (0, 0), 0)
    m = s.weapons[0]
    shots = 0
    for _ in range(int(20 / DT)):
        s.update(DT, 0, 0, False, 0.0)
        s.capacitor = s.cap_max
        shots += len(try_fire(s, m, rng, 0.0))
        if m.overheated:
            break
    assert m.overheated and shots > 10
    assert try_fire(s, m, rng, 0.0) == []
    while m.overheated:
        s.update(DT, 0, 0, False, 0.0)
    assert m.heat <= HEAT_RECOVER


def test_weapon_pips_cool_guns_faster():
    a, b = Ship("scout", (0, 0)), Ship("scout", (0, 0))
    b.set_pips(1, 1, 4)
    a.weapons[0].heat = b.weapons[0].heat = 80
    run(a, 1)
    run(b, 1)
    assert b.weapons[0].heat < a.weapons[0].heat


# --- снаряды ----------------------------------------------------------------

def _armored(shield=0):
    s = Ship("corvette", (0, 0))
    s.shield = shield
    return s


def test_ap_beats_armor_and_he_beats_hull():
    rng = random.Random(1)
    std, ap = _armored(), _armored()
    std.apply_damage(6, "kinetic", rng, "std")
    ap.apply_damage(6, "kinetic", rng, "ap")
    assert (ap.armor_max - ap.armor) > (std.armor_max - std.armor)
    bare_std, bare_he = _armored(), _armored()
    bare_std.armor = bare_he.armor = 0
    bare_std.apply_damage(10, "kinetic", rng, "std")
    bare_he.apply_damage(10, "explosive", rng, "he")
    assert bare_he.hp < bare_std.hp


def test_ap_is_worse_against_shields():
    rng = random.Random(1)
    std, ap = _armored(60), _armored(60)
    std.apply_damage(20, "kinetic", rng, "std")
    ap.apply_damage(20, "kinetic", rng, "ap")
    assert ap.shield > std.shield


def test_special_ammo_only_for_kinetic_guns():
    rng = random.Random(1)
    s = Ship("cruiser", (0, 0), 0, fit=["em_m", None, "autocannon_s", "autocannon_s", "engine_m", "reactor_m",
                                        "shield_m", "armor_s", "sensor_s", None, None])
    em = s.weapons[0]
    shot = try_fire(s, em, rng, 0.0, ammo="he")[0]
    assert shot.ammo == "std" and shot.dtype == "em"


def test_world_spends_special_ammo_and_falls_back():
    w = World(seed=1, first_event=1e9)
    w.player = Ship("scout", (4000, 4000), 0)
    w.pirate_spawn_cd = 1e9
    w.captain.credits = 1000
    assert w.buy_ammo("ap")
    assert w.captain.ammo_stock["ap"] == AMMO_PACK
    w.cycle_ammo()
    assert w.ammo_type == "ap"
    w.captain.ammo_stock["ap"] = 2
    for _ in range(120):
        w.update(DT, Controls(fire=True, aim=Vector2(4400, 4000)))
    assert w.captain.ammo_stock["ap"] == 0 and w.ammo_type == "std"


def test_cycle_ammo_skips_empty_types():
    w = World(seed=1, first_event=1e9)
    w.captain.ammo_stock = {"ap": 0, "he": 5}
    w.cycle_ammo()
    assert w.ammo_type == "he"
    w.cycle_ammo()
    assert w.ammo_type == "std"


# --- пожары и затопление ----------------------------------------------------

def test_he_can_start_fires_that_burn_until_crew_puts_them_out():
    rng = random.Random(2)
    s = Ship("cruiser", (0, 0))
    s.shield = s.armor = 0
    for _ in range(40):
        s.apply_damage(15, "explosive", rng, "he")
        if s.fires:
            break
    assert s.fires >= 1
    s.hp = s.hull.hp
    fires = s.fires
    run(s, 2)
    assert s.hp < s.hull.hp                               # горит
    run(s, CREW_FIRE_TIME)
    assert s.fires < fires                                # экипаж потушил очаг


def test_torpedo_opens_leaks_water_slows_ship_and_lists_it():
    rng = random.Random(1)
    s = Ship("cruiser", (0, 0))
    dry_speed = s.base_top_speed()
    s.apply_damage(85, "torpedo", rng)
    assert s.leaks >= 1
    run(s, 10)
    assert s.water > 0.2
    assert s.base_top_speed() < dry_speed
    assert s.list_angle > 0
    d = MODULES["autocannon_s"]
    assert spread_for(d, 0.0, list_angle=s.list_angle) > spread_for(d, 0.0)


def test_full_of_water_ship_sinks():
    s = Ship("scout", (0, 0))
    s.leaks, s.water = 3, 1.0
    run(s, 1)
    assert s.hp < s.hull.hp - 5


def test_damage_control_and_port_repair():
    s = Ship("scout", (0, 0), fit=["autocannon_s", "engine_s", "reactor_s", "shield_s", None, "sensor_s",
                                   "damage_control"])
    s.fires, s.leaks = 2, 3
    assert s.activate(0) is not None
    assert s.fires == 0 and s.leaks == 1
    s.water = 0.5
    s.repair_all()
    assert s.leaks == 0 and s.water == 0


def test_repair_cost_includes_leaks():
    w = World(seed=1, first_event=1e9)
    base = w.repair_cost()
    w.player.leaks, w.player.water = 2, 0.5
    assert w.repair_cost() > base


def test_pirates_shift_power_to_shields_under_fire():
    from nine.ai import Pirate
    w = World(seed=1, first_event=1e9)
    w.player = Ship("cruiser", (4000, 4000), 0)
    w.pirate_spawn_cd = 1e9
    pr = Pirate(Vector2(4300, 4000), random.Random(1))
    pr.ship.shield = 1
    w.pirates = [pr]
    for _ in range(5):
        w.update(DT, Controls())
    assert pr.state == "attack"
    assert pr.ship.pips["shields"] == 4


@pytest.mark.parametrize("hull", ["scout", "corvette", "torpedo_boat", "cruiser", "barge"])
def test_every_hull_renders_its_modules(hull):
    import pygame
    from nine.render import Renderer
    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((320, 240))
    r = Renderer(screen)
    fit = list(Ship(hull, (0, 0)).fit)
    s = Ship(hull, (0, 0), fit=fit)
    s.fires, s.water, s.throttle = 2, 0.5, 1.0
    r._ship(s, (200, 200, 200))
    r._target_info(s, (10, 10))
