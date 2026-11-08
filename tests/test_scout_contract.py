"""Reconnaissance contract: accept, visit marked zone, return for payout."""

from pygame.math import Vector2

from nine import save
from nine.world import World


def test_scout_contract_requires_visit_after_acceptance():
    w = World(seed=9, first_event=1e9)
    w.player.pos = Vector2(w.SCOUT_POS)
    w._update_memory(0.25, w.density_at(w.player.pos))
    assert not w.contracts
    w.player.pos = Vector2(w.port)
    assert w.contract_action("scout")
    assert not w.contract_action("scout")
    w.player.pos = Vector2(w.SCOUT_POS)
    w._memory_cd = 0
    w._update_memory(0.25, w.density_at(w.player.pos))
    assert w.contracts["scout"]["explored"]
    before = w.captain.credits
    assert w.contract_action("scout")
    assert w.captain.credits == before + 300
    assert not w.contract_action("scout")
    assert w.captain.credits == before + 300


def test_scout_does_not_complete_from_nearby_or_capsule():
    w = World(seed=9, first_event=1e9)
    assert w.contract_action("scout")
    w.player.pos = Vector2(w.SCOUT_POS) + Vector2(w.SCOUT_RADIUS + 30, 0)
    w._update_memory(0.25, 0)
    assert not w.contracts["scout"]["explored"]
    w.in_capsule = True
    w.player.pos = Vector2(w.SCOUT_POS)
    w._memory_cd = 0
    w._update_memory(0.25, 0)
    assert not w.contracts["scout"]["explored"]


def test_scout_progress_roundtrip_and_legacy_contracts():
    w = World(seed=9, first_event=1e9)
    w.contract_action("scout")
    w.contract_action("salt")
    w.player.pos = Vector2(w.SCOUT_POS)
    w._update_memory(0.25, 0)
    loaded = save.from_dict(save.to_dict(w))
    assert loaded.contracts == w.contracts
    assert loaded.contract_action("scout")
    assert not loaded.contract_action("scout")
    data = save.to_dict(w)
    data["contracts"]["scout"]["explored"] = "yes"
    loaded = save.from_dict(data)
    assert "scout" not in loaded.contracts
    assert "salt" in loaded.contracts
