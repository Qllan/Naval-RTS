"""Headless checks for the future many-pilot authoritative sector boundary."""

import pytest

from nine.net.host import AuthorityError
from nine.net.sector import SectorSimulation


def test_sector_multiple_pilots_have_isolated_input_ownership_and_shared_ids():
    sector = SectorSimulation()
    a = sector.add_pilot("alice", "needle", (3000, 3000))
    b = sector.add_pilot("bob", "manta", (3020, 3000))
    assert a is not b
    assert sector.submit("alice", {"seq": 1, "throttle": 1.0})
    assert sector.submit("bob", {"seq": 1, "turn": 1.0})
    with pytest.raises(AuthorityError):
        sector.submit("charlie", {"seq": 1, "throttle": 1})
    with pytest.raises(ValueError):
        sector.submit("alice", {"seq": 2, "owner_id": "bob", "throttle": 1})
    sector.tick()
    assert a.speed > 0
    assert b.angle != a.angle
    alice_view = sector.snapshot("alice")
    bob_view = sector.snapshot("bob")
    assert len(alice_view["entities"]) == 2
    assert len(bob_view["entities"]) == 2
    assert {e["id"] for e in alice_view["entities"]} == {
        e["id"] for e in bob_view["entities"]}
    assert alice_view["pilot_id"] != bob_view["pilot_id"]


def test_sector_has_bounded_interest_and_reconnect_full_frame():
    sector = SectorSimulation(radius=300, max_entities=3)
    sector.add_pilot("one", "needle", (3000, 3000))
    sector.add_pilot("two", "manta", (3010, 3000))
    sector.add_pilot("three", "bastion", (3030, 3000))
    sector.add_pilot("far", "needle", (6000, 6000))
    frame = sector.snapshot("one")
    assert frame["full"] and len(frame["entities"]) == 3
    assert not any(tuple(e["pos"]) == (6000.0, 6000.0) for e in frame["entities"])
    sector.tick()
    assert not sector.snapshot("one")["full"]
    sector.remove_pilot("three")
    refreshed = sector.snapshot("one")
    assert refreshed["full"]
    assert len(refreshed["entities"]) == 2
    with pytest.raises(AuthorityError):
        sector.snapshot("three")


def test_sector_steps_are_deterministic_regardless_of_join_order():
    def simulate(order):
        sector = SectorSimulation()
        for key in order:
            sector.add_pilot(key, "needle", (3000, 3000))
        for seq in range(50):
            for key in ("a", "b"):
                sector.submit(key, {"seq": seq, "throttle": 1,
                                    "turn": 0.1 if key == "a" else -0.2})
            sector.tick()
        return {key: (round(sector.pilots[key].ship.pos.x, 6),
                      round(sector.pilots[key].ship.pos.y, 6),
                      round(sector.pilots[key].ship.angle, 6))
                for key in ("a", "b")}
    assert simulate(("a", "b")) == simulate(("b", "a"))


def test_sector_roster_cannot_be_joined_twice():
    sector = SectorSimulation()
    sector.add_pilot("a", "needle", (100, 100))
    with pytest.raises(ValueError):
        sector.add_pilot("a", "needle", (100, 100))
    with pytest.raises(ValueError):
        sector.add_pilot("b", "missing", (100, 100))
    with pytest.raises(ValueError):
        sector.add_pilot("b", "manta", (-5, 100))
