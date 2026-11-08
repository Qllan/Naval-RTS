"""Network state contracts: stable IDs, ownership, interest and deltas."""

import json
from types import SimpleNamespace

import pytest

from nine.net.host import AuthorityError, ServerSimulation
from nine.net.snapshots import EntityRegistry, SnapshotStream, sector_for
from nine.ship import Ship
from nine.world import World


def stub_pirate(x, y):
    return SimpleNamespace(ship=Ship("scout", (x, y), side="pirate"))


def test_stable_ids_across_reordering_and_entity_reentry():
    world = World(seed=9, first_event=1e9)
    world.player.pos.update(4000, 4000)
    first, second = stub_pirate(4030, 4000), stub_pirate(4060, 4000)
    world.pirates = [first, second]
    stream = SnapshotStream(radius=150)
    a = stream.build(world, 0)
    by_position = {tuple(e["pos"]): e["id"] for e in a["entities"]}
    assert len(by_position) == 3
    world.pirates.reverse()
    b = stream.build(world, 1)
    assert b["entities"] == [] and b["removed"] == []
    first.ship.pos.update(7000, 7000)
    c = stream.build(world, 2)
    assert c["removed"] == [by_position[(4030.0, 4000.0)]]
    first.ship.pos.update(4030, 4000)
    d = stream.build(world, 3)
    assert [e["id"] for e in d["entities"]] == [by_position[(4030.0, 4000.0)]]


def test_interest_filter_and_snapshot_budget_for_dense_sector():
    world = World(seed=9, first_event=1e9)
    world.player.pos.update(4000, 4000)
    world.pirates = [stub_pirate(4000 + i * 4, 4010) for i in range(200)]
    world.pirates.append(stub_pirate(8000, 8000))
    stream = SnapshotStream(radius=500, max_entities=32)
    frame = stream.build(world, 0)
    assert frame["full"] is True
    assert len(frame["entities"]) == 32
    assert all(e["id"] != "" for e in frame["entities"])
    assert all(e["pos"][0] < 4500 for e in frame["entities"])
    assert frame["pilot_id"] in {e["id"] for e in frame["entities"]}


def test_deltas_quantization_periodic_full_and_json():
    world = World(seed=9, first_event=1e9)
    world.player.pos.update(4000, 4000)
    world.pirates = [stub_pirate(4020, 4000)]
    stream = SnapshotStream(radius=1000, full_every=3)
    initial = stream.build(world, 0)
    assert len(initial["entities"]) == 2 and initial["full"]
    assert stream.build(world, 0) is initial
    assert stream.build(world, 1)["entities"] == []
    world.player.pos.x += 0.004
    assert stream.build(world, 2)["entities"] == []
    world.player.pos.x += 0.02
    next_frame = stream.build(world, 3)
    assert next_frame["full"] and len(next_frame["entities"]) == 2
    assert next_frame["removed"] == []
    assert json.loads(json.dumps(next_frame)) == next_frame
    for entity in next_frame["entities"]:
        assert not any(key in entity for key in ("credits", "cargo", "inventory", "rng", "fit"))
    with pytest.raises(ValueError):
        stream.build(world, 2)


def test_entity_death_and_out_of_interest_removes_without_reveal():
    world = World(seed=9, first_event=1e9)
    world.player.pos.update(4000, 4000)
    enemy = stub_pirate(4010, 4000)
    world.pirates = [enemy]
    stream = SnapshotStream(radius=500)
    first = stream.build(world, 0)
    pirate_id = next(e["id"] for e in first["entities"] if e["side"] == "pirate")
    enemy.ship.hp = 0
    removed = stream.build(world, 1)["removed"]
    assert removed == [pirate_id]


def test_host_snapshot_rejects_other_pilots_and_never_accepts_viewport():
    host = ServerSimulation(World(seed=9, first_event=1e9), owner_id="pilot")
    with pytest.raises(AuthorityError):
        host.snapshot("someone_else")
    host.world.player.pos.update(2999, 4000)
    first = host.snapshot("pilot")
    assert first["tick"] == 0
    assert first["sector"] == sector_for(host.world.player.pos)
    assert len(first["entities"]) == 1
    host.tick()
    second = host.snapshot("pilot")
    assert second["tick"] == 1


def test_sector_function_handles_negative_coordinates_and_rejects_zero():
    from pygame.math import Vector2
    assert sector_for(Vector2(2000, -1)) == "1:-1"
    with pytest.raises(ValueError):
        sector_for(Vector2(), size=0)
