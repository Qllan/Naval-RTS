"""JSON-safe interest snapshots with stable IDs and bounded entity counts.

This is transport-agnostic preparation for authoritative clients, not a
multiplayer transport, authentication service or visibility/stealth system.
"""

import math
from weakref import WeakKeyDictionary

from . import PROTOCOL_VERSION


def sector_for(pos, size=2000.0):
    """Coarse, stable sector label for future sharding and instrumentation."""
    if size <= 0:
        raise ValueError("Sector size must be positive")
    return f"{math.floor(pos.x / size)}:{math.floor(pos.y / size)}"


class EntityRegistry:
    """Process-lifetime IDs; never put Python id(object) on the wire."""

    def __init__(self):
        self._ids = WeakKeyDictionary()
        self._next_id = 1

    def id_for(self, entity):
        number = self._ids.get(entity)
        if number is None:
            number = self._next_id
            self._next_id += 1
            self._ids[entity] = number
        return f"s{number}"


def ship_state(ship, entity_id):
    """Allowlisted public ship telemetry, independent of renderer/Pygame UI."""
    return {
        "id": entity_id,
        "hull": ship.hull.key,
        "side": ship.side,
        "pos": [round(ship.pos.x, 2), round(ship.pos.y, 2)],
        "vel": [round(ship.vel.x, 2), round(ship.vel.y, 2)],
        "angle": round(ship.angle % 360, 2),
        "hp": round(max(0, ship.hp), 1),
        "shield": round(max(0, ship.shield), 1),
        "armor": round(max(0, ship.armor), 1),
    }


class SnapshotStream:
    """Stateful per-client delta stream with periodic full snapshots.

    The observer is always the World player: the caller never supplies a
    camera center or arbitrary player ID. Future real multiplayer sectors
    must enforce per-player visibility and independently ACK/resync packets.
    """

    def __init__(self, radius=1600, max_entities=128, full_every=60):
        if (radius <= 0 or type(max_entities) is not int or max_entities < 1 or
            type(full_every) is not int or full_every < 1):
            raise ValueError("Invalid snapshot bounds")
        self.radius = float(radius)
        self.max_entities = max_entities
        self.full_every = full_every
        self.registry = EntityRegistry()
        self._previous = {}
        self._last_tick = None
        self._last_frame = None

    def _visible_ships(self, world, index=None):
        player = world.player
        radius_sq = self.radius * self.radius
        if index is not None:
            candidates = [entry for entry in index.query_radius(player.pos, self.radius)
                          if entry[2] is not player and entry[2].alive]
        else:
            candidates = []
            for order, pirate in enumerate(world.pirates):
                ship = pirate.ship
                if ship is player or not ship.alive:
                    continue
                dx, dy = ship.pos.x - player.pos.x, ship.pos.y - player.pos.y
                distance_sq = dx * dx + dy * dy
                if distance_sq <= radius_sq:
                    candidates.append((distance_sq, order, ship))
            candidates.sort(key=lambda row: (row[0], row[1]))
        return [player] + [row[2] for row in candidates[:self.max_entities - 1]]

    def build(self, world, tick, index=None):
        if type(tick) is not int or tick < 0:
            raise ValueError("Tick must be a nonnegative integer")
        if self._last_tick is not None:
            if tick < self._last_tick:
                raise ValueError("Snapshot tick cannot go backwards")
            if tick == self._last_tick:
                return self._last_frame

        ships = self._visible_ships(world, index=index)
        states = {self.registry.id_for(s): ship_state(s, self.registry.id_for(s))
                  for s in ships}
        full = self._last_tick is None or tick % self.full_every == 0
        changed = [states[k] for k in sorted(states) if full or
                   self._previous.get(k) != states[k]]
        removed = [] if full else sorted(set(self._previous) - set(states))
        frame = {
            "protocol": PROTOCOL_VERSION,
            "tick": tick,
            "time": round(world.t, 3),
            "sector": sector_for(world.player.pos),
            "pilot_id": self.registry.id_for(world.player),
            "full": full,
            "entities": changed,
            "removed": removed,
        }
        self._previous = states
        self._last_tick = tick
        self._last_frame = frame
        return frame
