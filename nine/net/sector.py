"""Isolated multi-pilot movement prototype; no sockets, combat or economy.

This is a migration seam for a future SectorWorld. It deliberately never
pretends to run the existing single-player World for several captains.
"""

from dataclasses import dataclass
from types import SimpleNamespace

from pygame.math import Vector2

from .. import config as C
from ..hulls import HULLS
from ..ship import Ship
from ..spatial import PositionGrid
from .clock import FixedTickClock
from .commands import PlayerCommand, coalesce_commands
from .host import AuthorityError
from .snapshots import EntityRegistry, SnapshotStream


@dataclass
class Pilot:
    ship: Ship
    stream: SnapshotStream
    last_seq: int = -1
    pending: PlayerCommand | None = None


class SectorSimulation:
    """Deterministic multi-ship movement under authoritative local controls.

    A future transport must authenticate every caller and server-assign
    the hull/spawn position; no one can select another pilot via a packet.
    Weapons, shared damage, NPCs, docking and trading are not implemented.
    """

    def __init__(self, hz=60, radius=1600, max_entities=128):
        self.clock = FixedTickClock(hz)
        self.radius = radius
        self.max_entities = max_entities
        self.pilots = {}
        self.registry = EntityRegistry()
        self._interest_tick = None
        self._interest_index = None
        self._roster_view = None

    def _invalidate(self):
        self._interest_tick = None
        self._interest_index = None
        self._roster_view = None
        for pilot in self.pilots.values():
            pilot.stream.invalidate()

    def add_pilot(self, owner_id, hull_key, position):
        """Trusted server-side allocation only, not a client message."""
        if not isinstance(owner_id, str) or not owner_id or owner_id in self.pilots:
            raise ValueError("Invalid or duplicate pilot ID")
        if hull_key not in HULLS:
            raise ValueError("Unknown hull")
        pos = Vector2(position)
        if not 0 <= pos.x <= C.WORLD_W or not 0 <= pos.y <= C.WORLD_H:
            raise ValueError("Spawn outside sector bounds")
        ship = Ship(hull_key, pos)
        stream = SnapshotStream(radius=self.radius,
                                max_entities=self.max_entities, registry=self.registry)
        self.pilots[owner_id] = Pilot(ship, stream)
        self._invalidate()
        return ship

    def remove_pilot(self, owner_id):
        if owner_id not in self.pilots:
            raise AuthorityError("Unknown pilot")
        self.pilots.pop(owner_id)
        self._invalidate()

    def submit(self, owner_id, payload):
        pilot = self.pilots.get(owner_id)
        if pilot is None:
            raise AuthorityError("Unknown or unauthenticated pilot")
        command = PlayerCommand.parse(payload)
        if command.seq <= pilot.last_seq:
            return False
        pilot.last_seq = command.seq
        pilot.pending = coalesce_commands(pilot.pending, command)
        return True

    def tick(self):
        """Stable update order, independent of dict insertion order."""
        for owner_id in sorted(self.pilots):
            pilot = self.pilots[owner_id]
            command, pilot.pending = pilot.pending, None
            if command is None:
                pilot.ship.update(self.clock.dt, 0, 0, False, 0.0)
            else:
                # Movement-only migration surface; no client authorizes combat.
                pilot.ship.update(self.clock.dt, command.throttle,
                                  command.turn, command.boost, 0.0)
        return self.clock.mark_tick()

    def advance(self, elapsed):
        count = self.clock.consume(elapsed)
        for _ in range(count):
            self.tick()
        return count

    def snapshot(self, owner_id):
        pilot = self.pilots.get(owner_id)
        if pilot is None:
            raise AuthorityError("Unknown or unauthenticated pilot")
        if self._interest_tick != self.clock.tick:
            ships = [self.pilots[key].ship for key in sorted(self.pilots)]
            self._interest_index = PositionGrid(ships)
            self._roster_view = [SimpleNamespace(ship=ship) for ship in ships]
            self._interest_tick = self.clock.tick
        view = SimpleNamespace(player=pilot.ship,
                               pirates=self._roster_view,
                               t=self.clock.tick * self.clock.dt)
        return pilot.stream.build(view, self.clock.tick,
                                  index=self._interest_index)
