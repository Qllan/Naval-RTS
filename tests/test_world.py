import pytest
from pygame.math import Vector2

from nine import config as C
from nine.ai import Pirate, Tihodont
from nine.combat import Projectile
from nine.hulls import HULLS
from nine.modules import MODULES
from nine.ship import Ship
from nine.world import Controls, World


@pytest.fixture
def world():
    return World(seed=9, first_event=1e9)


def step(w, ctl, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        w.update(dt, ctl)


def test_boost_in_veil_fouls_hull_but_not_in_clear_water():
    a, b = Ship("scout", (4000, 4000)), Ship("scout", (4000, 4000))
    for _ in range(600):
        a.capacitor = b.capacitor = a.cap_max
        a.update(1 / 60, 1.0, 0.0, True, 0.8)
        b.update(1 / 60, 1.0, 0.0, True, 0.05)
    assert a.fouling > 0.3
    assert b.fouling == 0.0


def test_dense_veil_shrinks_radar(world):
    world.player.pos = Vector2(C.PORT_POS) + Vector2(0, -300)
    clear = world.radar_range()
    world.player.pos = Vector2(C.EYE_POS) + Vector2(-C.EYE_WALL_R - 150, 0)
    assert world.radar_range() < clear * 0.6


def test_tihodont_hides_quiet_player_and_bioscreen_hides_completely(world):
    world.player.pos = Vector2(3000, 3000)
    world.tihodonts = [Tihodont(world.player.pos, world.rng)]
    assert world.player_signature() < 0.1
    world.player.vel = Vector2(world.player.base_top_speed(), 0)
    assert world.player_signature() > 0.5
    world.player = Ship("scout", (3000, 3000), fit=["autocannon_s", "engine_s", "reactor_s2", "shield_s", None,
                                                    "sensor_s", None])
    assert world.player_signature() > 0


def test_mining_rate_depends_on_modules(world):
    node = world.nodes[0]
    node.kind, node.amount = "salt", 100
    world.player.pos = Vector2(node.pos)
    step(world, Controls(mine=True), 2.0)
    scout_rate = world.captain.cargo["salt"]
    world.captain.cargo = {}
    world.player = Ship("barge", node.pos)                # бур ×1.8
    step(world, Controls(mine=True), 2.0)
    assert world.captain.cargo["salt"] > scout_rate * 1.5


def test_selling(world):
    world.captain.cargo = {"condensate": 10}
    credits = world.captain.credits
    assert world.sell_cargo() == 220
    assert world.captain.credits == credits + 220 and world.cargo_used == 0


def test_death_capsule_insurance_and_debt(world):
    world.player = Ship("cruiser", (3000, 3000))
    value = world.player.value
    world.captain.cargo = {"condensate": 20}
    world.player.hp = 0
    step(world, Controls(), 1 / 60)
    assert world.in_capsule
    assert world.captain.pending_insurance == int(value * C.INSURANCE_RATE)
    assert any(lt.cargo for lt in world.loot)
    world.player.hp = 0
    step(world, Controls(), 1 / 60)
    assert not world.in_capsule
    assert world.captain.debt == C.CAPSULE_DEBT and world.captain.trauma
    world.captain.credits = 10_000
    assert world.install(0, "scatter_s") == "Должникам не продают"
    world.pay_debt()
    assert world.install(0, "scatter_s") is None
    assert world.heal() and not world.captain.trauma


def test_capsule_docking_pays_insurance(world):
    world.player = Ship("cruiser", (3000, 3000))
    value = world.player.value
    world.player.hp = 0
    step(world, Controls(), 1 / 60)
    credits = world.captain.credits
    world.dock()
    assert not world.in_capsule and world.player.hull.key == "scout"
    assert world.captain.credits == credits + int(value * C.INSURANCE_RATE)


def test_pirates_spawn_away_from_port_and_drop_loot(world):
    world.player.pos = Vector2(C.PORT_POS) + Vector2(0, -300)
    step(world, Controls(), 15)
    assert world.pirates == []
    world.player.pos = Vector2(4500, 3500)
    world.pirate_spawn_cd = 0
    step(world, Controls(), 0.1)
    assert world.pirates
    pr = world.pirates[0]
    pr.ship.hp = 0
    step(world, Controls(), 1 / 60)
    assert pr not in world.pirates and world.loot and world.captain.kills == 1


def test_pirate_loadouts_are_valid_and_fight():
    import random
    rng = random.Random(1)
    for key in ("gunner", "brawler", "rocketeer", "hunter"):
        pr = Pirate((0, 0), rng, key)
        assert pr.ship.weapons and pr.ship.engine


def test_player_guns_hit_pirates(world):
    world.player.pos = Vector2(4000, 4000)
    world.player.angle = 0
    pr = Pirate(Vector2(4250, 4000), world.rng)
    pr.ship.vel = Vector2()
    world.pirates = [pr]
    world.pirate_spawn_cd = 1e9
    start = pr.ship.shield + pr.ship.hp
    step(world, Controls(fire=True, aim=Vector2(pr.ship.pos)), 1.0)
    assert pr.ship.shield + pr.ship.hp < start or pr not in world.pirates


def test_buy_hull_trade_in_moves_modules_to_storage(world):
    world.captain.credits = 10_000
    old_fit = [k for k in world.player.fit if k]
    full, cost = world.hull_offer("corvette")
    assert cost == full - HULLS["scout"].price // 2
    assert world.buy_hull("corvette") is None
    assert world.player.hull.key == "corvette"
    assert world.captain.credits == 10_000 - cost
    assert sorted(world.captain.storage) == sorted(old_fit)


def test_no_money_from_buying_and_reselling_a_hull(world):
    """Купить корабль и сразу всё сдать — всегда в минус."""
    world.captain.credits = 20_000
    world.buy_hull("cruiser")
    world.buy_hull("scout")
    for key in list(world.captain.storage):
        world.sell_from_storage(key)
    assert world.captain.credits < 20_000


def test_install_from_shop_and_storage(world):
    cap = world.captain
    cap.credits = 5000
    assert world.install(0, "scatter_s") is None
    assert world.player.fit[0] == "scatter_s" and "autocannon_s" in cap.storage
    assert cap.credits == 5000 - MODULES["scatter_s"].price
    assert world.install(0, "autocannon_s", from_storage=True) is None
    assert "scatter_s" in cap.storage and "autocannon_s" not in cap.storage
    assert world.install(0, "cannon_m") == "Модуль не подходит к слоту"


def test_install_rejects_power_deficit(world):
    world.captain.credits = 50_000
    world.buy_hull("cruiser")
    for slot, key in ((5, "reactor_s"), (0, "em_m"), (1, "missile_m"), (4, "engine_m2"), (8, "sensor_m")):
        assert world.install(slot, key) is None           # ровно 10 из 10 эн/с
    err = world.install(2, "missile_s")
    assert err is not None and "энергии" in err
    assert world.player.fit[2] == "autocannon_s"
    world.uninstall(5)                                    # без реактора в море не выйти
    assert any("реактор" in p.lower() for p in world.undock_problems())


def test_rearm_restores_ammo(world):
    world.captain.credits = 5000
    world.install(0, "missile_s")
    m = world.player.weapons[0]
    m.ammo = 2
    cost = world.rearm_cost()
    assert cost == 10 * MODULES["missile_s"].ammo_price
    assert world.rearm() and m.ammo == m.defn.ammo


def test_loot_modules_go_to_storage(world):
    from nine.entities import Loot
    world.loot = [Loot(Vector2(world.player.pos), {}, 0, modules=["em_m"])]
    step(world, Controls(), 1 / 60)
    assert "em_m" in world.captain.storage


def test_ecm_breaks_incoming_missiles(world):
    world.player = Ship("scout", (4000, 4000), fit=["autocannon_s", "engine_s", "reactor_s", "shield_s", None,
                                                    "sensor_s", "ecm"])
    shooter = Ship("raider", (4300, 4000), side="pirate")
    missile = Projectile(Vector2(4200, 4000), Vector2(-300, 0), 20, "explosive", shooter, "missile", 3,
                         world.player, 150, 330)
    world.projectiles = [missile]
    step(world, Controls(activate=[0]), 1 / 60)
    assert missile.lost


def test_trauma_slows_reload(world):
    world.captain.trauma = True
    step(world, Controls(), 1 / 60)
    assert world.player.reload_mult() == pytest.approx(C.TRAUMA_RELOAD_MULT)
    world.captain.credits = 1000
    world.heal()
    step(world, Controls(), 1 / 60)
    assert world.player.reload_mult() == pytest.approx(1.0)


def test_day_night_cycle_changes_vision_and_spotlight_trades_stealth(world):
    world.player.pos = Vector2(C.PORT_POS)
    world.t = (0.5 - C.START_TIME_OF_DAY) * C.DAY_LENGTH          # полдень
    assert world.daylight() == pytest.approx(1.0)
    day_vis, day_sig = world.visual_range(), world.player_signature()
    world.t = (1.0 - C.START_TIME_OF_DAY) * C.DAY_LENGTH          # полночь
    assert world.daylight() == pytest.approx(0.0)
    assert world.clock() == "00:00"
    assert world.visual_range() < day_vis * 0.6
    assert world.player_signature() < day_sig
    step(world, Controls(toggle_spotlight=True), 1 / 60)
    assert world.spotlight
    assert world.visual_range() > day_vis * 0.8
    assert world.player_signature() > day_sig


def test_phantoms_appear_in_dense_veil_and_cannot_be_locked(world):
    world.player.pos = Vector2(C.EYE_POS) + Vector2(-C.EYE_WALL_R - 200, 300)
    world.pirate_spawn_cd = 1e9
    for _ in range(60 * 30):
        world._update_phantoms(1 / 60, 0.95)
        if world.phantoms:
            break
    assert world.phantoms
    ph = world.phantoms[0]
    assert world._nearest_to_cursor(ph["pos"], 400, need_radar=True) is None     # не цель


def test_calm_start_near_player_opens_the_sky(world):
    from nine.events import CALM
    world.events.spawn(CALM, world.player.pos, world.t)
    step(world, Controls(), 0.1)
    assert any(ev[0] == "sky" for ev in world.fx)
