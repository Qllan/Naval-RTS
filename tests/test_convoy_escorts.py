"""Convoy escorts stay deterministic and remain noncombat contacts."""

from nine import save
from nine.islands import island_at
from nine.trade_traffic import ESCORT_LAG_SECONDS, TradeTraffic
from nine.world import Controls, World


def test_each_trader_has_a_neutral_escort():
    world = World(seed=9, first_event=1e9)
    traffic = world.trade_traffic
    for moment in (0.0, 25.0, 50.0, traffic.period * 0.75):
        traders = traffic.snapshot(moment)
        escorts = traffic.escort_snapshot(moment)
        assert len(traders) == len(escorts) == 2
        assert [escort.convoy for escort in escorts] == [0, 1]
        assert all(escort.name.startswith("Патруль") for escort in escorts)


def test_patrol_guards_trail_convoys_without_cutting_across_islands():
    for seed in (9, 16, 42):
        world = World(seed=seed, first_event=1e9)
        traffic = world.trade_traffic
        for step in range(50):
            t = traffic.period * step / 50
            traders = traffic.snapshot(t)
            guards = traffic.escort_snapshot(t)
            previous = traffic.snapshot(t - ESCORT_LAG_SECONDS)
            for leader, guard, trailing in zip(traders, guards, previous):
                expected = trailing.pos if leader.underway else leader.pos
                assert guard.pos == expected
                assert island_at(world.islands, guard.pos, 20) is None


def test_escort_positions_survive_save_load_and_are_repeatable():
    world = World(seed=9, first_event=1e9)
    world.t = 184.25
    before = world.trade_traffic.escort_snapshot(world.t)
    restored = save.from_dict(save.to_dict(world))
    assert restored.trade_traffic.escort_snapshot(restored.t) == before
    assert restored.trade_traffic.escort_snapshot(restored.t) == before


def test_escorts_do_not_join_combat_or_change_economy():
    world = World(seed=9, first_event=1e9)
    world.captain.credits = 1500
    original = (len(world.pirates), len(world.projectiles),
                world.captain.credits, dict(world.captain.cargo))
    _ = world.trade_traffic.escort_snapshot(world.t)
    assert original == (len(world.pirates), len(world.projectiles),
                        world.captain.credits, dict(world.captain.cargo))
    world.update(0.1, Controls())
    assert world.captain.credits == 1500
    assert world.captain.cargo == {}
