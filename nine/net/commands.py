"""Explicit, bounded command contract. No client-owned world state is accepted."""

from dataclasses import dataclass, replace
import math

from pygame.math import Vector2

from .. import config as C
from ..world import Controls


class InvalidCommand(ValueError):
    """Untrusted input failed schema/range validation."""


MAX_SEQUENCE = 2 ** 53 - 1
COMMAND_FIELDS = frozenset({
    "seq", "throttle", "turn", "boost", "fire", "fire2", "mine",
    "aim", "activate", "pips", "cycle_ammo", "toggle_spotlight",
})
PIP_ACTIONS = frozenset(("shields", "engines", "weapons", "reset"))


@dataclass(frozen=True)
class PlayerCommand:
    """Validated frame input. No credits, position, fit, HP or entity ID fields."""

    seq: int
    throttle: float = 0.0
    turn: float = 0.0
    boost: bool = False
    fire: bool = False
    fire2: bool = False
    mine: bool = False
    aim: tuple | None = None
    activate: tuple = ()
    pips: tuple = ()
    cycle_ammo: bool = False
    toggle_spotlight: bool = False

    @classmethod
    def parse(cls, payload):
        if not isinstance(payload, dict) or set(payload) - COMMAND_FIELDS:
            raise InvalidCommand("Unknown command fields")
        sequence = payload.get("seq")
        if type(sequence) is not int or not 0 <= sequence <= MAX_SEQUENCE:
            raise InvalidCommand("Invalid command sequence")

        def axis(key):
            value = payload.get(key, 0.0)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise InvalidCommand("Invalid axis: " + key)
            return float(max(-1.0, min(1.0, value)))

        def switch(key):
            value = payload.get(key, False)
            if type(value) is not bool:
                raise InvalidCommand("Invalid boolean: " + key)
            return value

        aim = payload.get("aim")
        if aim is not None:
            if (not isinstance(aim, (list, tuple)) or len(aim) != 2 or
                any(type(x) not in (int, float) or not math.isfinite(x) for x in aim) or
                not 0 <= aim[0] <= C.WORLD_W or not 0 <= aim[1] <= C.WORLD_H):
                raise InvalidCommand("Invalid aim point")
            aim = (float(aim[0]), float(aim[1]))

        activate = payload.get("activate", [])
        if (not isinstance(activate, (list, tuple)) or len(activate) > 4 or
            any(type(v) is not int or not 0 <= v <= 3 for v in activate) or
            len(set(activate)) != len(activate)):
            raise InvalidCommand("Invalid utility actions")
        pips = payload.get("pips", [])
        if (not isinstance(pips, (list, tuple)) or len(pips) > 4 or
            any(not isinstance(p, str) or p not in PIP_ACTIONS for p in pips)):
            raise InvalidCommand("Invalid energy actions")

        return cls(seq=sequence, throttle=axis("throttle"), turn=axis("turn"),
                   boost=switch("boost"), fire=switch("fire"), fire2=switch("fire2"),
                   mine=switch("mine"), aim=aim, activate=tuple(activate),
                   pips=tuple(pips), cycle_ammo=switch("cycle_ammo"),
                   toggle_spotlight=switch("toggle_spotlight"))

    def to_controls(self, *, impulses=True):
        """Reconstruct a fresh mutable Controls object for one simulation step."""
        return Controls(throttle=self.throttle, turn=self.turn, boost=self.boost,
                        fire=self.fire, fire2=self.fire2, mine=self.mine,
                        aim=Vector2(self.aim) if self.aim is not None else None,
                        activate=list(self.activate) if impulses else [],
                        pips=list(self.pips) if impulses else [],
                        cycle_ammo=self.cycle_ammo if impulses else False,
                        toggle_spotlight=self.toggle_spotlight if impulses else False)



def coalesce_commands(previous, newest):
    """Bounded newest state plus accumulated single-frame input impulses.

    Snapshot-based movement uses the newest message, while actions received
    earlier within the same tick are preserved. This is an in-memory
    adapter, not a reliable network transport or ACK protocol.
    """
    if previous is None:
        return newest
    return replace(
        newest,
        activate=tuple(dict.fromkeys(previous.activate + newest.activate))[:4],
        pips=(previous.pips + newest.pips)[:4],
        cycle_ammo=previous.cycle_ammo or newest.cycle_ammo,
        toggle_spotlight=previous.toggle_spotlight or newest.toggle_spotlight,
    )
