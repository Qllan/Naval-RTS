import random

from pygame.math import Vector2

from nine.combat import try_fire, update_lock, update_projectile
from nine.hulls import HULLS
from nine.ship import Ship, fit_problems

DT = 1 / 60


def run(ship, seconds, throttle=0.0, turn=0.0, boost=False, density=0.0):
    for _ in range(int(seconds / DT)):
        ship.update(DT, throttle, turn, boost, density)


def test_fit_validation_catches_wrong_slot_size_and_power():
    scout = HULLS["scout"]
    fit = list(scout.default_fit)
    fit[0] = "cannon_m"                                   # M в слот S
    assert any("слишком большой" in p for p in fit_problems(scout, fit))
    fit = list(scout.default_fit)
    fit[0] = "engine_s"                                   # двигатель в оружейный слот
    assert any("не тот тип" in p for p in fit_problems(scout, fit))
    cruiser = HULLS["cruiser"]
    assert fit_problems(cruiser, cruiser.default_fit) == []
    fit = list(cruiser.default_fit)
    fit[5] = "reactor_s"                                  # 10 эн/с
    fit[0], fit[1], fit[2] = "em_m", "missile_m", "missile_s"
    fit[4], fit[8] = "engine_m2", "sensor_m"              # итого 10.5 эн/с
    assert any("энергии" in p for p in fit_problems(cruiser, fit))


def test_ship_has_inertia():
    s = Ship("scout", (0, 0), 0)
    run(s, 2, throttle=1)
    v = s.speed
    assert v > 100
    run(s, 0.5)
    assert 0.5 * v < s.speed < v


def test_mass_and_cargo_slow_the_ship():
    light, loaded = Ship("barge", (0, 0)), Ship("barge", (0, 0))
    loaded.cargo_mass = 90
    assert loaded.base_top_speed() < light.base_top_speed()
    run(light, 1, throttle=1)
    run(loaded, 1, throttle=1)
    assert loaded.speed < light.speed


def test_boost_costs_energy_and_stops_when_empty():
    s = Ship("scout", (0, 0))
    run(s, 1, throttle=1, boost=True)
    assert s.capacitor < s.cap_max
    s.capacitor = 0
    s.update(DT, 1, 0, True, 0.0)
    # выработки хватает на кадр форсажа только если она больше расхода
    assert s.boosting == (s.power_balance(0) * DT > s.engine.boost_drain * DT)


def test_veil_raises_electronics_upkeep_and_can_cause_brownout():
    s = Ship("cruiser", (0, 0), fit=["em_m", "missile_m", "autocannon_s", "autocannon_s", "engine_m", "reactor_s",
                                     "shield_m", "armor_s", "sensor_m", "ecm", "ecm"])
    assert s.power_balance(0.8) < s.power_balance(0.0)
    assert s.power_balance(1.0) < 0
    s.shield = s.shield_max
    run(s, 30, density=1.0)
    assert s.brownout
    assert s.radar_range(1.0) == 0
    assert s.shield < s.shield_max


def test_resonant_shield_ignores_most_of_the_veil():
    a = Ship("cruiser", (0, 0))
    b = Ship("cruiser", (0, 0), fit=[k if k != "shield_m" else "shield_res_m" for k in HULLS["cruiser"].default_fit])
    loss_a = a.power_balance(0) - a.power_balance(1)
    loss_b = b.power_balance(0) - b.power_balance(1)
    assert loss_b < loss_a


def test_damage_layers():
    rng = random.Random(1)
    s = Ship("corvette", (0, 0))
    hp, armor, shield = s.hp, s.armor, s.shield
    s.apply_damage(10, "kinetic", rng)
    assert s.shield == shield - 10 and s.hp == hp and s.armor == armor
    s.apply_damage(10, "torpedo", rng)                    # мимо щита
    assert s.shield == shield - 10 and s.armor < armor
    s2 = Ship("corvette", (0, 0))
    s2.apply_damage(10, "em", rng)                        # ЭМ выжигает щит вдвое
    assert s2.shield == s2.shield_max - 20


def test_armor_reduces_kinetic_hits():
    rng = random.Random(1)
    s = Ship("corvette", (0, 0))
    s.shield = 0
    s.apply_damage(6, "kinetic", rng)
    assert s.armor_max - s.armor == 6 - s.armor_def.reduction


def test_subsystem_damage_slows_turning():
    a, b = Ship("scout", (0, 0), 0), Ship("scout", (0, 0), 0)
    b.subsystems["rudder"] = 0.0
    run(a, 0.5, throttle=1, turn=1)
    run(b, 0.5, throttle=1, turn=1)
    assert 0 < b.angle < a.angle


def test_turret_traverse_is_limited_and_arcs_block_fire():
    s = Ship("cruiser", (0, 0), 0)
    front = s.weapons[0]                                  # «Молот» на носу, 70°/с, сектор 270°
    target = Vector2(0, 500)                              # на правом траверзе: 90°
    assert not front.aim(s, target, DT)                   # за кадр не успеть
    for _ in range(120):
        aimed = front.aim(s, target, DT)
    assert aimed
    behind = Vector2(-500, 0)
    assert not front.in_arc(s, behind)


def test_missile_lock_is_slower_in_the_veil_and_missile_tracks_target():
    rng = random.Random(3)
    shooter = Ship("scout", (0, 0), 0, fit=["missile_s", "engine_s", "reactor_s", "shield_s", None, "sensor_s", None])
    target = Ship("raider", (600, 200), side="pirate")
    m = shooter.weapons[0]
    update_lock(m, shooter, target, True, 0.0, 1.0)
    clear = m.lock
    m.lock_target = None
    update_lock(m, shooter, target, True, 0.9, 1.0)
    assert m.lock < clear
    for _ in range(200):
        update_lock(m, shooter, target, True, 0.0, DT)
    shots = try_fire(shooter, m, rng, 0.0)
    assert len(shots) == 1 and m.ammo == m.defn.ammo - 1
    missile = shots[0]
    for _ in range(300):
        update_projectile(missile, DT, 0.0, rng)
        if missile.pos.distance_to(target.pos) < target.radius + 4:
            break
    assert missile.pos.distance_to(target.pos) < target.radius + 4


def test_missiles_lose_track_in_dense_veil():
    rng = random.Random(5)
    shooter = Ship("scout", (0, 0), 0, fit=["missile_s", "engine_s", "reactor_s", "shield_s", None, "sensor_s", None])
    target = Ship("raider", (900, 600), side="pirate")
    m = shooter.weapons[0]
    m.lock_target, m.lock = target, 1.0
    missile = try_fire(shooter, m, rng, 1.0)[0]
    for _ in range(int(missile.life / DT)):
        update_projectile(missile, DT, 1.0, rng)
    assert missile.lost


def test_torpedo_fires_straight_along_the_hull_and_ignores_turret_aim():
    rng = random.Random(1)
    s = Ship("torpedo_boat", (0, 0), 90)
    torp = next(w for w in s.weapons if w.defn.kind == "torpedo")
    shot = try_fire(s, torp, rng, 0.0, aim_point=Vector2(-500, 0))[0]
    assert abs(shot.vel.normalize().y - 1.0) < 1e-6      # курс 90° = вниз по экрану
    assert torp.ammo == torp.defn.ammo - 1


def test_repair_gel_heals_and_uses_charges():
    s = Ship("scout", (0, 0), fit=["autocannon_s", "engine_s", "reactor_s", "shield_s", None, "sensor_s",
                                   "repair_gel"])
    s.hp = 40
    s.subsystems["engine"] = 0.5
    u = s.activate(0)
    assert u is not None and u.charges == u.defn.charges - 1
    assert s.activate(0) is None                          # кулдаун
    run(s, 6)
    assert s.hp > 80 and s.subsystems["engine"] > 0.8
