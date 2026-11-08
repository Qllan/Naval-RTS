"""Neutral freighters are deterministic, safe, and unaffected by saving/loading."""

import math

from nine import save
from nine.islands import island_at
from nine.trade_traffic import CELL, CLEARANCE, PORT_DWELL, TradeTraffic
from nine.world import Controls, World


def test_two_trade_vessels_follow_repeatable_schedules():
    world = World(seed=9, first_event=1e9)
    traffic = world.trade_traffic
    assert len(traffic.snapshot(0)) == 2
    assert traffic.period > 2 * PORT_DWELL
    assert traffic.snapshot(10) == traffic.snapshot(10 + traffic.period)
    assert traffic.snapshot(0)[0].underway is False
    assert traffic.snapshot(PORT_DWELL + 8)[0].underway is True
    assert traffic.snapshot(PORT_DWELL + traffic.sailing_time + 5)[0].underway is False


def test_freighters_arrive_at_both_hubs_and_reverse():
    world = World(seed=42, first_event=1e9)
    traffic = world.trade_traffic
    origin, destination = traffic.route[0], traffic.route[-1]
    assert traffic.snapshot(0)[0].pos == origin
    inbound = traffic.snapshot(PORT_DWELL + traffic.sailing_time / 2)[0]
    assert inbound.pos != origin
    assert inbound.pos != destination
    assert traffic.snapshot(PORT_DWELL + traffic.sailing_time)[0].pos == destination
    assert traffic.snapshot(traffic.period - 1)[0].underway
    assert traffic.snapshot(traffic.period)[0].pos == origin


def test_trade_route_is_in_water_near_islands():
    for seed in (9, 16, 42, 123):
        world = World(seed=seed, first_event=1e9)
        route = world.trade_traffic.route
        assert len(route) >= 2
        for start, end in zip(route, route[1:]):
            segment = end - start
            steps = max(1, math.ceil(segment.length() / (CELL / 4)))
            for index in range(steps + 1):
                pos = start + segment * (index / steps)
                assert island_at(world.islands, pos, CLEARANCE / 3) is None


def test_save_load_reconstructs_same_trade_contacts():
    world = World(seed=9, first_event=1e9)
    world.t = 246.7
    before = world.trade_traffic.snapshot(world.t)
    restored = save.from_dict(save.to_dict(world))
    assert restored.t == world.t
    assert restored.trade_traffic.snapshot(restored.t) == before
    original_credits = restored.captain.credits
    original_cargo = dict(restored.captain.cargo)
    restored.update(0.1, Controls())
    assert restored.captain.credits == original_credits
    assert restored.captain.cargo == original_cargo


def test_traders_do_not_change_player_collision_or_weapon_target_lists():
    world = World(seed=9, first_event=1e9)
    initial = (len(world.pirates), len(world.projectiles))
    _ = world.trade_traffic.snapshot(world.t)
    assert (len(world.pirates), len(world.projectiles)) == initial
