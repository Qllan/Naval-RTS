"""Сохранение прогресса в ~/.nine/save.json (настройки — отдельно, в settings.json).

Мир восстанавливается из сида; в файл пишется только то, что изменил игрок:
капитан, корабль, позиция, время, память карты, отметки, кодекс, цели.
"""

import base64
import json
import os
import math

import numpy as np
from pygame.math import Vector2

from .settings import settings_dir
from .hulls import HULLS
from .modules import MODULES
from .ship import PIP_MAX, PIP_SYSTEMS, PIP_TOTAL, Ship

VERSION = 2
SUPPORTED_VERSIONS = (1, 2)


def save_path():
    return os.path.join(settings_dir(), "save.json")


def has_save():
    return os.path.exists(save_path())


def to_dict(world):
    cap, p = world.captain, world.player
    mem = (np.clip(world.memory, 0, 1) * 255).astype(np.uint8)
    return {
        "version": VERSION,
        "seed": world.seed,
        "t": world.t,
        "clock_offset": world.clock_offset,
        "captain": {"credits": cap.credits, "debt": cap.debt, "trauma": cap.trauma, "cargo": cap.cargo,
                    "storage": cap.storage, "ammo_stock": cap.ammo_stock,
                    "pending_insurance": cap.pending_insurance, "kills": cap.kills},
        "ship": {
            "hull": p.hull.key, "fit": p.fit, "groups": {str(k): v for k, v in p.groups.items()},
            "pos": [p.pos.x, p.pos.y], "angle": p.angle, "vel": [p.vel.x, p.vel.y],
            "hp": p.hp, "armor": p.armor, "shield": p.shield, "capacitor": p.capacitor,
            "fouling": p.fouling, "shield_cd": p.shield_cd,
            "subsystems": p.subsystems, "pips": dict(p.pips),
            "fires": p.fires, "leaks": p.leaks, "water": p.water,
            # Slot-indexed state keeps sparse and different-sized hull layouts stable.
            "ammo_by_slot": {str(w.index): {"module": w.defn.key, "ammo": w.ammo}
                             for w in p.weapons},
            "charges_by_slot": {str(u.index): {"module": u.defn.key, "charges": u.charges}
                                for u in p.utilities},
        },
        "in_capsule": world.in_capsule,
        "ammo_type": world.ammo_type,
        "spotlight": world.spotlight,
        "memory": {"shape": list(mem.shape), "data": base64.b64encode(mem.tobytes()).decode()},
        "marks": {k: {**m, "pos": [m["pos"].x, m["pos"].y]} for k, m in world.marks.items()},
        "waypoint": [world.waypoint.x, world.waypoint.y] if world.waypoint is not None else None,
        "codex": world.codex,
        "goals": sorted(world.goals_done),
        "contracts": world.contracts,
        "market": {"stock": world.market_stock,
                   "last_time": world.market_last_time},
    }


def _validate_fit(hull_key, fit):
    """Reject incompatible or partial loadouts before constructing a ship."""
    hull = HULLS[hull_key]
    if not isinstance(fit, list) or len(fit) != len(hull.slots):
        raise ValueError("Неверное число слотов в сохранении")
    for slot, key in zip(hull.slots, fit):
        if key is None:
            continue
        if not isinstance(key, str) or key not in MODULES:
            raise ValueError("Неизвестный модуль в сохранении")
        m = MODULES[key]
        if m.category != slot.category or m.size > slot.size:
            raise ValueError("Несовместимый модуль в сохранении")


def _restore_slot_state(states, units, legacy, name, maximum):
    """Version 2 maps state to slot+module; v1 uses arrays in module order."""
    if isinstance(states, dict):
        for unit in units:
            entry = states.get(str(unit.index))
            if not isinstance(entry, dict) or entry.get("module") != unit.defn.key:
                continue
            value = entry.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(unit, name, max(0, min(maximum(unit), int(value))))
    else:
        for unit, value in zip(units, legacy):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                setattr(unit, name, max(0, min(maximum(unit), int(value))))


def from_dict(d):
    if d.get("version") not in SUPPORTED_VERSIONS:
        raise ValueError("Неподдерживаемая версия сохранения")
    from .world import World
    s = d["ship"]
    _validate_fit(s["hull"], s["fit"])
    world = World(d["seed"])
    world.t = d["t"]
    # Legacy saves start from fresh local stocks, without replaying older trips.
    from .market import valid_stocks
    market = d.get("market")
    if isinstance(market, dict):
        last = market.get("last_time")
        if (valid_stocks(market.get("stock"))
                and type(last) in (int, float) and math.isfinite(last)
                and 0 <= last <= world.t):
            world.market_stock = {k: dict(v) for k, v in market["stock"].items()}
            world.market_last_time = float(last)
        else:
            world.market_last_time = world.t
    else:
        world.market_last_time = world.t
    world.clock_offset = d.get("clock_offset", 0.0)
    cap = world.captain
    for k, v in d["captain"].items():
        setattr(cap, k, v)
    p = Ship(s["hull"], Vector2(s["pos"]), s["angle"], fit=s["fit"])
    weapon_indices = {w.index for w in p.weapons}
    p.groups.update({int(k): int(v) for k, v in s.get("groups", {}).items()
                     if int(k) in weapon_indices and type(v) is int and v in (0, 1, 2)})
    p.hp = max(0.0, min(p.hull.hp, s["hp"]))
    p.armor = max(0.0, min(p.armor_max, s["armor"]))
    p.fouling = max(0.0, min(1.0, s["fouling"]))
    p.subsystems.update(s["subsystems"])
    p.shield = max(0.0, min(p.shield_max, s.get("shield", p.shield_max)))
    p.capacitor = max(0.0, min(p.cap_max, s.get("capacitor", p.cap_max)))
    p.shield_cd = max(0.0, s.get("shield_cd", 0.0))
    p.brownout = p.cap_max > 0 and p.capacitor <= 0
    p.vel = Vector2(s.get("vel", (0, 0)))
    p.water = max(0.0, min(1.0, s.get("water", 0.0)))
    p.fires = max(0, min(3, int(s.get("fires", 0))))
    p.leaks = max(0, min(4, int(s.get("leaks", 0))))
    pips = s.get("pips")
    if isinstance(pips, dict) and set(pips) == set(PIP_SYSTEMS):
        values = [pips[k] for k in PIP_SYSTEMS]
        if all(type(v) is int and 0 <= v <= PIP_MAX for v in values) and sum(values) == PIP_TOTAL:
            p.pips = dict(pips)
    _restore_slot_state(s.get("ammo_by_slot"), p.weapons, s.get("ammo", ()),
                        "ammo", lambda w: w.defn.ammo)
    _restore_slot_state(s.get("charges_by_slot"), p.utilities, s.get("charges", ()),
                        "charges", lambda u: u.defn.charges)
    world.player = p
    world.in_capsule = d["in_capsule"]
    world.ammo_type = d.get("ammo_type", "std")
    world.spotlight = bool(d.get("spotlight", False))
    m = d["memory"]
    mem = np.frombuffer(base64.b64decode(m["data"]), np.uint8).reshape(m["shape"])
    if mem.shape == world.memory.shape:
        world.memory = mem.astype(np.float32) / 255
    world.marks.update({k: {**v, "pos": Vector2(v["pos"])} for k, v in d["marks"].items()})
    # New trade platform remains visible when loading pre-platform saves.
    world.marks["platform"] = {
        "pos": Vector2(world.platform), "label": "Торговая платформа",
        "kind": "port", "clarity": 1.0,
    }
    world.waypoint = Vector2(d["waypoint"]) if d["waypoint"] else None
    world.codex = dict(d["codex"])
    world.goals_done = set(d["goals"])
    # Старые сохранения не содержат контрактов; неизвестные id игнорируем.
    contracts = d.get("contracts", {})
    if isinstance(contracts, dict):
        for key, entry in contracts.items():
            if (key in world.CONTRACTS and isinstance(entry, dict)
                    and entry.get("status") in ("active", "done")
                    and type(entry.get("start_kills")) is int
                    and 0 <= entry["start_kills"] <= cap.kills):
                if key == "scout" and type(entry.get("explored")) is not bool:
                    continue
                if key == "escort":
                    if (entry.get("origin") not in ("port", "platform")
                            or type(entry.get("convoy")) is not int
                            or entry["convoy"] not in (0, 1)
                            or type(entry.get("leg")) is not int
                            or entry["leg"] < -1
                            or type(entry.get("close_seconds")) not in (int, float)
                            or not 0 <= entry["close_seconds"] <= 100000
                            or type(entry.get("arrived")) is not bool):
                        continue
                if key == "urgent":
                    if (entry.get("origin") not in ("port", "platform")
                            or entry.get("destination") not in ("port", "platform")
                            or entry["origin"] == entry["destination"]
                            or entry.get("kind") not in ("salt", "filament")
                            or type(entry.get("amount")) is not int
                            or entry["amount"] != world.URGENT_QUANTITY
                            or type(entry.get("reward")) is not int
                            or not 300 <= entry["reward"] <= 1000):
                        continue
                cycle = entry.get("cycle", 0)
                if type(cycle) is not int or not 0 <= cycle <= 9999:
                    continue
                world.contracts[key] = {
                    "status": entry["status"], "start_kills": entry["start_kills"]
                }
                if "cycle" in entry:
                    world.contracts[key]["cycle"] = cycle
                if key == "scout":
                    world.contracts[key]["explored"] = entry["explored"]
                elif key == "urgent":
                    world.contracts[key].update({
                        name: entry[name] for name in (
                            "origin", "destination", "kind", "amount", "reward")
                    })
                elif key == "escort":
                    world.contracts[key].update({
                        "origin": entry["origin"], "convoy": entry["convoy"],
                        "leg": entry["leg"], "close_seconds": entry["close_seconds"],
                        "arrived": entry["arrived"],
                    })
    # враги и события не сохраняются — после загрузки море спокойное
    world.events.next_spawn = world.t + 45.0
    return world


def save(world):
    os.makedirs(settings_dir(), exist_ok=True)
    tmp = save_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(to_dict(world), f, ensure_ascii=False)
    os.replace(tmp, save_path())


def load():
    """World или None, если сохранения нет или оно повреждено."""
    try:
        with open(save_path(), encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") not in SUPPORTED_VERSIONS:
            return None
        return from_dict(d)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None
