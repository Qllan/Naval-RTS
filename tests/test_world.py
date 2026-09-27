import pytest
from pygame.math import Vector2

from nine import config as C
from nine.ai import Tihodont
from nine.entities import Ship
from nine.world import Controls, World


@pytest.fixture
def world():
    return World(seed=9, first_event=1e9)


def step(w, ctl, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        w.update(dt, ctl)


def test_ship_has_inertia():
    s = Ship("scout", (0, 0), 0)
    for _ in range(120):
        s.update(1 / 60, 1.0, 0.0, False, 0.0)
    v = s.speed
    assert v > 100
    for _ in range(30):
        s.update(1 / 60, 0.0, 0.0, False, 0.0)
    assert 0.5 * v < s.speed < v      # по инерции продолжает идти


def test_boost_in_veil_fouls_hull_but_not_in_clear_water():
    a, b = Ship("scout", (0, 0)), Ship("scout", (0, 0))
    for _ in range(600):
        a.update(1 / 60, 1.0, 0.0, True, 0.8)
        b.update(1 / 60, 1.0, 0.0, True, 0.05)
    assert a.fouling > 0.3
    assert b.fouling == 0.0
    assert a.max_speed() < b.max_speed()


def test_dense_veil_shrinks_radar(world):
    world.player.pos = Vector2(C.PORT_POS) + Vector2(0, -300)
    clear = world.radar_range()
    world.player.pos = Vector2(C.EYE_POS) + Vector2(-C.EYE_WALL_R - 150, 0)
    assert world.radar_range() < clear * 0.6


def test_tihodont_hides_quiet_player(world):
    world.player.pos = Vector2(3000, 3000)
    world.tihodonts = [Tihodont(world.player.pos, world.rng)]
    world.player.vel = Vector2()
    assert world.player_signature() < 0.1
    world.player.vel = Vector2(world.player.cls.max_speed, 0)
    assert world.player_signature() > 0.5


def test_mining_and_selling(world):
    node = world.nodes[0]
    world.player.pos = Vector2(node.pos)
    kind, amount = node.kind, node.amount
    step(world, Controls(mine=True), 2.0)
    assert world.captain.cargo.get(kind, 0) > 5
    assert node.amount < amount
    value = world.cargo_value()
    credits = world.captain.credits
    assert world.sell_cargo() == value
    assert world.captain.credits == credits + value
    assert world.cargo_used == 0


def test_death_capsule_insurance_and_debt(world):
    world.player = Ship("cruiser", (3000, 3000))
    world.captain.cargo = {"condensate": 20}
    world.player.hull = 0
    step(world, Controls(), 1 / 60)
    assert world.in_capsule
    assert world.captain.pending_insurance == int(2400 * C.INSURANCE_RATE)
    assert any(lt.cargo for lt in world.loot)              # часть груза в обломках

    world.player.hull = 0                                   # капсулу тоже сбили
    step(world, Controls(), 1 / 60)
    assert not world.in_capsule
    assert world.captain.debt == C.CAPSULE_DEBT and world.captain.trauma
    world.captain.credits = 10_000
    assert not world.buy_upgrade("sensor")                  # должнику не продают
    world.pay_debt()
    assert world.buy_upgrade("sensor")
    assert world.heal() and not world.captain.trauma


def test_capsule_docking_pays_insurance(world):
    world.player = Ship("cruiser", (3000, 3000))
    world.player.hull = 0
    step(world, Controls(), 1 / 60)
    credits = world.captain.credits
    world.dock()
    assert not world.in_capsule and world.player.cls.key == "scout"
    assert world.captain.credits == credits + int(2400 * C.INSURANCE_RATE)


def test_pirates_spawn_away_from_port_and_can_be_killed(world):
    world.player.pos = Vector2(C.PORT_POS) + Vector2(0, -300)
    step(world, Controls(), 15)
    assert world.pirates == []                              # у порта безопасно
    world.player.pos = Vector2(4500, 3500)
    world.pirate_spawn_cd = 0
    step(world, Controls(), 0.1)
    assert world.pirates
    pr = world.pirates[0]
    pr.ship.hull = 0
    step(world, Controls(), 1 / 60)
    assert pr not in world.pirates and world.loot and world.captain.kills == 1


def test_buy_ship_with_trade_in(world):
    world.captain.credits = 5000
    assert world.buy_ship("cruiser")
    assert world.player.cls.key == "cruiser"
    assert world.captain.credits == 5000 - 2400
