"""In-process authoritative single-pilot host (no sockets, no server claims).

The present World owns one player and shared single-player captain state.
This adapter deliberately refuses other owners rather than pretending that
multiple network clients can already share a World.
"""

from .clock import FixedTickClock
from .commands import PlayerCommand
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
        # One newest command per tick: bounded queue, no backlog of inputs.
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
