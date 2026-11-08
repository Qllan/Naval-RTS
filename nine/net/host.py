"""In-process authoritative single-pilot host (no sockets, no server claims).

The present World owns one player and shared single-player captain state.
This adapter deliberately refuses other owners rather than pretending that
multiple network clients can already share a World.
"""

from dataclasses import replace

from .clock import FixedTickClock
from .commands import PlayerCommand
from .snapshots import SnapshotStream
from ..spatial import PositionGrid
from ..world import Controls, World


class AuthorityError(PermissionError):
    pass


class ServerSimulation:
    """Fixed-rate simulation that accepts only validated, sequenced input."""

    def __init__(self, world=None, owner_id="local", hz=60):
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("owner_id must be a nonempty string")
        self.world = world if world is not None else World()
        self.owner_id = owner_id
        self.clock = FixedTickClock(hz=hz)
        self.stream = SnapshotStream()
        self._interest_index_tick = None
        self._interest_index = None
        self._last_seq = -1
        self._pending = None
        self.accepted = 0
        self.rejected = 0

    def submit(self, caller_id, payload):
        """Caller identity comes from a trusted transport, never the payload."""
        if caller_id != self.owner_id:
            self.rejected += 1
            raise AuthorityError("Only the pilot may control this ship")
        command = PlayerCommand.parse(payload)
        if command.seq <= self._last_seq:
            self.rejected += 1
            return False
        self._last_seq = command.seq
        # Keep latest movement, but preserve one-shot actions from packets
        # received within the same tick. The coalesced input stays bounded.
        if self._pending is not None:
            before = self._pending
            command = replace(
                command,
                activate=tuple(dict.fromkeys(before.activate + command.activate))[:4],
                pips=(before.pips + command.pips)[:4],
                cycle_ammo=before.cycle_ammo or command.cycle_ammo,
                toggle_spotlight=before.toggle_spotlight or command.toggle_spotlight,
            )
        self._pending = command
        self.accepted += 1
        return True

    def tick(self):
        command, self._pending = self._pending, None
        controls = command.to_controls() if command is not None else Controls()
        self.world.update(self.clock.dt, controls)
        return self.clock.mark_tick()

    def advance(self, elapsed):
        count = self.clock.consume(elapsed)
        for _ in range(count):
            self.tick()
        return count

    def snapshot(self, caller_id):
        """Authoritative interest-filtered state for the current owner.

        This identity check does not authenticate connections. A future
        transport must authenticate the caller before invoking the host.
        """
        if caller_id != self.owner_id:
            raise AuthorityError("Only the pilot can view this stream")
        if self._interest_index_tick != self.clock.tick:
            self._interest_index = PositionGrid(p.ship for p in self.world.pirates)
            self._interest_index_tick = self.clock.tick
        return self.stream.build(self.world, self.clock.tick, index=self._interest_index)
