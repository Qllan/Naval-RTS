"""Regressions for v1/v2 saves, modular hull reloads and repeat fitting."""

import json

import pytest
from pygame.math import Vector2

from nine import save
from nine.hulls import HULLS
from nine.ship import Ship
from nine.world import World


def loaded_world(monkeypatch, tmp_path, world):
    path = tmp_path / "save.json"
    monkeypatch.setattr(save, "save_path", lambda: str(path))
    save.save(world)
    return save.load(), path


@pytest.mark.parametrize("hull_key", ("needle", "manta", "bastion"))
def test_v2_roundtrip_keeps_ship_design_pips_and_live_state(monkeypatch, tmp_path, hull_key):
    world = World(seed=9, first_event=1e9)
    original = Ship(hull_key, (3200, 4100), -37)
    world.player = original
    world.spotlight = True
    original.vel = Vector2(18, -7)
    original.set_pips(3, 1, 2)
    original.hp -= 12
    original.armor = max(0, original.armor - 9)
    original.shield = max(0, original.shield_max - 24)
    original.capacitor = original.cap_max * 0.35
    original.shield_cd = 2.5
    original.fires = 1
    original.leaks = 2
    original.water = 0.25
    original.fouling = 0.1
    if original.weapons:
        original.groups[original.weapons[0].index] = 2
    world.captain.credits = 1234
    world.captain.storage = ["sensor_s", "repair_gel"]
    restored, path = loaded_world(monkeypatch, tmp_path, world)
    assert restored is not None
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 2
    p = restored.player
    assert p.hull.key == hull_key and p.fit == original.fit
    assert p.groups == original.groups and p.pips == original.pips
    assert p.pos == original.pos and p.vel == original.vel
    assert p.hp == original.hp and p.armor == original.armor
    assert p.shield == original.shield and p.capacitor == pytest.approx(original.capacitor)
    assert p.fires == 1 and p.leaks == 2 and p.water == 0.25
    assert p.shield_cd == 2.5 and p.fouling == pytest.approx(0.1)
    assert restored.spotlight and restored.captain.credits == 1234
    assert restored.captain.storage == ["sensor_s", "repair_gel"]
    assert p.layout_turn_factor == pytest.approx(original.layout_turn_factor)


def test_v2_slot_indexed_munitions_and_utilities_survive_reload(monkeypatch, tmp_path):
    world = World(seed=9, first_event=1e9)
    hull = HULLS["bastion"]
    fit = list(hull.default_fit)
    fit[0], fit[1] = "missile_m", "torpedo_m"
    fit[-2], fit[-1] = "repair_gel", "smoke"
    world.player = Ship("bastion", (3000, 3000), fit=fit)
    weapons = {w.index: w for w in world.player.weapons}
    utils = {u.index: u for u in world.player.utilities}
    weapons[0].ammo, weapons[1].ammo = 4, 2
    utils[len(fit) - 2].charges = 1
    utils[len(fit) - 1].charges = 3

    restored, path = loaded_world(monkeypatch, tmp_path, world)
    assert restored is not None
    s = json.loads(path.read_text(encoding="utf-8"))["ship"]
    assert s["ammo_by_slot"]["0"]["module"] == "missile_m"
    assert s["ammo_by_slot"]["1"]["module"] == "torpedo_m"
    restored_weapons = {w.index: w for w in restored.player.weapons}
    restored_utils = {u.index: u for u in restored.player.utilities}
    assert restored_weapons[0].ammo == 4
    assert restored_weapons[1].ammo == 2
    assert restored_utils[len(fit) - 2].charges == 1
    assert restored_utils[len(fit) - 1].charges == 3


def test_legacy_v1_save_loads_with_defaults(monkeypatch, tmp_path):
    world = World(seed=9, first_event=1e9)
    world.player = Ship("cruiser", (2400, 3000))
    d = save.to_dict(world)
    s = d["ship"]
    d["version"] = 1
    for k in ("ammo_by_slot", "charges_by_slot", "pips", "shield", "capacitor",
              "shield_cd", "water", "fires", "leaks", "vel"):
        s.pop(k, None)
    d.pop("spotlight", None)
    s["ammo"] = [max(0, w.ammo - 1) for w in world.player.weapons]
    s["charges"] = [max(0, u.charges - 1) for u in world.player.utilities]
    path = tmp_path / "save.json"
    monkeypatch.setattr(save, "save_path", lambda: str(path))
    path.write_text(json.dumps(d), encoding="utf-8")
    restored = save.load()
    assert restored is not None
    assert restored.player.hull.key == "cruiser"
    assert restored.player.pips == {"shields": 2, "engines": 2, "weapons": 2}
    assert restored.player.shield == restored.player.shield_max
    assert restored.player.capacitor == restored.player.cap_max
    assert restored.player.vel == Vector2()
    assert [w.ammo for w in restored.player.weapons] == s["ammo"]
    assert [u.charges for u in restored.player.utilities] == s["charges"]


@pytest.mark.parametrize("tamper", ("unknown_hull", "wrong_fit_length", "invalid_module",
                                     "wrong_module_type", "unsupported_version"))
def test_broken_saves_fail_gracefully(monkeypatch, tmp_path, tamper):
    d = save.to_dict(World(seed=9, first_event=1e9))
    s = d["ship"]
    if tamper == "unknown_hull":
        s["hull"] = "not_a_real_hull"
    elif tamper == "wrong_fit_length":
        s["fit"].pop()
    elif tamper == "invalid_module":
        s["fit"][0] = "no_such_module"
    elif tamper == "wrong_module_type":
        s["fit"][0] = "engine_s"
    else:
        d["version"] = 99
    path = tmp_path / "save.json"
    monkeypatch.setattr(save, "save_path", lambda: str(path))
    path.write_text(json.dumps(d), encoding="utf-8")
    assert save.load() is None


def test_reinstall_from_storage_after_v2_load(monkeypatch, tmp_path):
    world = World(seed=9, first_event=1e9)
    world.player = Ship("needle", (3000, 3000))
    world.captain.credits = 10000
    assert world.install(0, "missile_s") is None
    assert "autocannon_s" in world.captain.storage
    restored, _ = loaded_world(monkeypatch, tmp_path, world)
    assert restored is not None
    before = restored.captain.credits
    assert restored.install(0, "autocannon_s", from_storage=True) is None
    assert restored.player.fit[0] == "autocannon_s"
    assert "missile_s" in restored.captain.storage
    assert restored.captain.credits == before
    assert restored.player.layout_turn_factor > 0



def test_v2_bastion_save_survives_capital_hull_reframe(monkeypatch, tmp_path):
    """Existing slot-indexed saves follow the new mount coordinates."""
    world = World(seed=9, first_event=1e9)
    ship = Ship("bastion", (3000, 3500))
    world.player = ship
    ship.weapons[0].ammo = max(0, ship.weapons[0].ammo - 2)
    world.captain.storage = ["missile_m", "repair_gel"]
    restored, _ = loaded_world(monkeypatch, tmp_path, world)
    assert restored is not None
    p = restored.player
    assert len(p.fit) == 11 and p.fit == ship.fit
    assert [w.index for w in p.weapons] == [w.index for w in ship.weapons]
    assert [tuple(w.slot.pos) for w in p.weapons] == [
        (35, 0), (-30, 0), (-4, -8.5), (-4, 8.5)]
    assert [w.ammo for w in p.weapons] == [w.ammo for w in ship.weapons]
    assert restored.captain.storage == ["missile_m", "repair_gel"]
