"""Deterministic civilian cargo traffic between the two port hubs.

Visual neutral NPCs: their positions follow the simulation clock and their
route avoids island shorelines. No combat, cargo mutations or save fields.
"""

import heapq
import math
from dataclasses import dataclass

from pygame.math import Vector2

from . import config as C
from .islands import island_at


CELL = 160
CLEARANCE = 90
CRUISE_SPEED = 62.0
PORT_DWELL = 24.0
ESCORT_LAG_SECONDS = 9.0


@dataclass(frozen=True)
class Trader:
    pos: Vector2
    angle: float
    underway: bool
    name: str


@dataclass(frozen=True)
class Escort:
    """Visible convoy guard, following the same water-safe route."""
    pos: Vector2
    angle: float
    underway: bool
    name: str
    convoy: int


def _cell(pos):
    p = Vector2(pos)
    return (round(p.x / CELL), round(p.y / CELL))


def _route(start, finish, islands):
    """Find a compact offshore route on a deterministic 8-way grid."""
    origin, dest = _cell(start), _cell(finish)
    limit_x, limit_y = C.WORLD_W // CELL, C.WORLD_H // CELL

    def safe(node):
        x, y = node
        if not (1 <= x < limit_x and 1 <= y < limit_y):
            return False
        return not island_at(islands, Vector2(x * CELL, y * CELL), CLEARANCE)

    def h(node):
        return math.dist(node, dest)

    open_set = [(h(origin), 0.0, origin)]
    cost = {origin: 0.0}
    previous = {}
    visited = set()
    steps = ((1, 0), (0, 1), (-1, 0), (0, -1),
             (1, 1), (1, -1), (-1, 1), (-1, -1))
    while open_set:
        _, current_cost, node = heapq.heappop(open_set)
        if node in visited:
            continue
        visited.add(node)
        if node == dest:
            break
        for dx, dy in steps:
            nxt = (node[0] + dx, node[1] + dy)
            if nxt != dest and nxt != origin and not safe(nxt):
                continue
            # Avoid cutting a corner between two blocked grid cells.
            if dx and dy and (not safe((node[0] + dx, node[1]))
                              or not safe((node[0], node[1] + dy))):
                continue
            new_cost = current_cost + math.hypot(dx, dy)
            if new_cost < cost.get(nxt, float("inf")):
                cost[nxt] = new_cost
                previous[nxt] = node
                heapq.heappush(open_set, (new_cost + h(nxt), new_cost, nxt))
    if dest not in cost:
        # Conservative fallback: stay on a straight route rather than crash.
        return (Vector2(start), Vector2(finish))

    nodes = [dest]
    while nodes[-1] != origin:
        nodes.append(previous[nodes[-1]])
    nodes.reverse()
    return tuple([Vector2(start)] +
                 [Vector2(x * CELL, y * CELL) for x, y in nodes[1:-1]] +
                 [Vector2(finish)])


def _interpolate(route, distance):
    remaining = distance
    for a, b in zip(route, route[1:]):
        segment = b - a
        length = segment.length()
        if length <= 1e-6:
            continue
        if remaining <= length:
            return a + segment * (remaining / length), segment.as_polar()[1]
        remaining -= length
    direction = route[-1] - route[-2]
    return Vector2(route[-1]), direction.as_polar()[1]


class TradeTraffic:
    """Two neutral cargo craft cruising on staggered, reversible schedules."""

    def __init__(self, port, platform, islands):
        # Route endpoints sit outside the docking area so they don't obstruct F.
        self.route = _route(Vector2(port) + Vector2(0, -C.PORT_RADIUS - 65),
                            Vector2(platform) + Vector2(0, -C.PORT_RADIUS - 65),
                            islands)
        self.distance = sum((b - a).length() for a, b in
                            zip(self.route, self.route[1:]))
        self.sailing_time = self.distance / CRUISE_SPEED
        self.period = 2 * (self.sailing_time + PORT_DWELL)

    def snapshot(self, time):
        """Ships are pure functions of time; reloading restores same positions."""
        result = []
        for index, offset in enumerate((0.0, self.period / 2)):
            phase = (time + offset) % self.period
            if phase < PORT_DWELL:
                pos, angle, moving = Vector2(self.route[0]), 0.0, False
            elif phase < PORT_DWELL + self.sailing_time:
                pos, angle = _interpolate(
                    self.route, (phase - PORT_DWELL) * CRUISE_SPEED)
                moving = True
            elif phase < 2 * PORT_DWELL + self.sailing_time:
                pos, angle, moving = Vector2(self.route[-1]), 180.0, False
            else:
                reverse = tuple(reversed(self.route))
                pos, angle = _interpolate(
                    reverse,
                    (phase - 2 * PORT_DWELL - self.sailing_time) * CRUISE_SPEED)
                moving = True
            result.append(Trader(pos, angle, moving, f"Торговец {index + 1}"))
        return tuple(result)


    def escort_snapshot(self, time):
        """Each guard trails its trader on the exact same island-safe route.

        When the trader is docked, its guard also holds station at the
        route endpoint. No collision, combat AI, or persistent RNG state.
        """
        traders = self.snapshot(time)
        trailing = self.snapshot(time - ESCORT_LAG_SECONDS)
        escorts = []
        for index, (leader, previous) in enumerate(zip(traders, trailing)):
            escort = previous if leader.underway else leader
            escorts.append(Escort(Vector2(escort.pos), escort.angle,
                                  leader.underway, f"Патруль {index + 1}", index))
        return tuple(escorts)
