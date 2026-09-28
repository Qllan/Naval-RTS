"""Сохранение прогресса в ~/.nine/save.json (настройки — отдельно, в settings.json).

Мир восстанавливается из сида; в файл пишется только то, что изменил игрок:
капитан, корабль, позиция, время, память карты, отметки, кодекс, цели.
"""

import base64
import json
import os

import numpy as np
from pygame.math import Vector2

from .settings import settings_dir
from .ship import Ship

VERSION = 1


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
        "ship": {"hull": p.hull.key, "fit": p.fit, "groups": {str(k): v for k, v in p.groups.items()},
                 "pos": [p.pos.x, p.pos.y], "angle": p.angle, "hp": p.hp, "armor": p.armor,
                 "fouling": p.fouling, "subsystems": p.subsystems,
                 "ammo": [w.ammo for w in p.weapons], "charges": [u.charges for u in p.utilities]},
        "in_capsule": world.in_capsule,
        "ammo_type": world.ammo_type,
        "memory": {"shape": list(mem.shape), "data": base64.b64encode(mem.tobytes()).decode()},
        "marks": {k: {**m, "pos": [m["pos"].x, m["pos"].y]} for k, m in world.marks.items()},
        "waypoint": [world.waypoint.x, world.waypoint.y] if world.waypoint is not None else None,
        "codex": world.codex,
        "goals": sorted(world.goals_done),
    }


def from_dict(d):
    from .world import World
    world = World(d["seed"])
    world.t = d["t"]
    world.clock_offset = d.get("clock_offset", 0.0)
    cap = world.captain
    for k, v in d["captain"].items():
        setattr(cap, k, v)
    s = d["ship"]
    p = Ship(s["hull"], Vector2(s["pos"]), s["angle"], fit=s["fit"])
    p.groups.update({int(k): v for k, v in s["groups"].items()})
    p.hp, p.armor, p.fouling = s["hp"], s["armor"], s["fouling"]
    p.subsystems.update(s["subsystems"])
    for w, a in zip(p.weapons, s["ammo"]):
        w.ammo = a
    for u, c in zip(p.utilities, s["charges"]):
        u.charges = c
    world.player = p
    world.in_capsule = d["in_capsule"]
    world.ammo_type = d.get("ammo_type", "std")
    m = d["memory"]
    mem = np.frombuffer(base64.b64decode(m["data"]), np.uint8).reshape(m["shape"])
    if mem.shape == world.memory.shape:
        world.memory = mem.astype(np.float32) / 255
    world.marks = {k: {**v, "pos": Vector2(v["pos"])} for k, v in d["marks"].items()}
    world.waypoint = Vector2(d["waypoint"]) if d["waypoint"] else None
    world.codex = dict(d["codex"])
    world.goals_done = set(d["goals"])
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
        if d.get("version") != VERSION:
            return None
        return from_dict(d)
    except (OSError, ValueError, KeyError, TypeError):
        return None
