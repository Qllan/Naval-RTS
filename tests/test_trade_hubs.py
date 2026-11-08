"""Two-hub trading prototype: docking, market spreads, and save migration."""

from pygame.math import Vector2

from nine import config as C
from nine import save
from nine.islands import island_at
from nine.world import World


def test_platform_is_marked_in_safe_water_for_normal_world_seeds():
    for seed in (9, 16, 42, 123):
        world = World(seed, first_event=1e9)
        assert world.platform.distance_to(world.port) > C.PORT_RADIUS * 2
        assert not island_at(world.islands, world.platform, C.PORT_RADIUS)
        assert world.marks["platform"]["pos"] == world.platform


def test_docking_switches_market_and_undocks_at_same_hub():
    world = World(9, first_event=1e9)
    world.player.pos = Vector2(world.platform)
    world.player.vel = Vector2()
    assert world.can_dock()
    assert world.dock()
    assert world.active_port == "platform"
    assert world.market_price("salt") > C.MARKET_MULTIPLIERS["port"]["salt"] * 6
    world.undock()
    assert world.player.pos.distance_to(world.platform) > C.PORT_RADIUS
    assert world.player.pos.distance_to(world.platform) < C.PORT_RADIUS + 70
    world.player.vel = Vector2(100, 0)
    assert not world.can_dock()


def test_buy_in_refugee_port_and_sell_at_platform_is_profitable():
    world = World(9, first_event=1e9)
    world.captain.credits = 5000
    cost = world.market_price("salt", buying=True) * 10
    assert world.buy_resource("salt")
    assert world.captain.credits == 5000 - cost
    assert world.captain.cargo["salt"] == 10
    world.player.pos = Vector2(world.platform)
    world.player.vel = Vector2()
    assert world.dock()
    value = world.cargo_value()
    assert value > cost
    assert world.sell_cargo() == value
    assert world.captain.credits == 5000 + value - cost


def test_market_prevents_local_buy_sell_exploit_and_overfilling():
    world = World(9, first_event=1e9)
    world.captain.credits = 100000
    for hub in ("port", "platform"):
        world.active_port = hub
        for kind in ("salt", "filament"):
            assert world.market_price(kind, True) > world.market_price(kind)
    world.captain.cargo["salt"] = world.cargo_capacity
    credits = world.captain.credits
    assert not world.buy_resource("salt")
    assert world.captain.credits == credits
    world.captain.cargo = {}
    world.captain.debt = 1
    assert not world.buy_resource("salt")
    assert not world.buy_resource("unknown")
    assert not world.buy_resource("salt", -1)
    assert world.captain.credits == credits


def test_old_save_keeps_new_platform_mark_and_ship_location():
    world = World(9, first_event=1e9)
    world.player.pos = Vector2(world.platform)
    old_data = save.to_dict(world)
    old_data["marks"].pop("platform")
    restored = save.from_dict(old_data)
    assert restored.player.pos == world.player.pos
    assert restored.marks["platform"]["pos"] == restored.platform
    assert restored.dock()
    assert restored.active_port == "platform"
