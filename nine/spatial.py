"""Uniform spatial grid for broad-phase ship collision lookups.

This is an acceleration structure, not new collision physics: exact
radius checks and original list-order priority are preserved.
"""

import math


class ShipCollisionGrid:
    """Static index built once per simulation frame for a set of ships.

    Ships may cover multiple cells. A small generous boundary (4 game
    units) covers the extra radius used by missiles/torpedoes, while exact
    filtering is still performed by first_hit().
    """

    def __init__(self, ships, cell_size=128.0, max_padding=4.0):
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = float(cell_size)
        self.cells = {}
        for ship in ships:
            margin = max(0.0, ship.radius + max_padding)
            x, y = ship.pos
            x0 = math.floor((x - margin) / self.cell_size)
            x1 = math.floor((x + margin) / self.cell_size)
            y0 = math.floor((y - margin) / self.cell_size)
            y1 = math.floor((y + margin) / self.cell_size)
            for cx in range(x0, x1 + 1):
                for cy in range(y0, y1 + 1):
                    self.cells.setdefault((cx, cy), []).append(ship)

    def candidates(self, pos):
        return self.cells.get((math.floor(pos.x / self.cell_size),
                               math.floor(pos.y / self.cell_size)), ())

    def first_hit(self, pos, padding=0.0):
        """First living intersecting ship in the *original* ship order."""
        for ship in self.candidates(pos):
            if ship_overlaps(ship, pos, padding):
                return ship
        return None


def ship_overlaps(ship, pos, padding=0.0):
    """Match the old strict circle collision (< radius), without sqrt."""
    if not ship.alive:
        return False
    dx = ship.pos.x - pos.x
    dy = ship.pos.y - pos.y
    radius = ship.radius + padding
    return dx * dx + dy * dy < radius * radius



class PositionGrid:
    """Per-tick positional index for many observers querying the same sector.

    Each object appears in one cell and retains its input ordinal. This
    broad phase is not a collision or a visibility authority: callers
    must still enforce permissions and line-of-sight rules.
    """

    def __init__(self, objects, cell_size=256.0):
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = float(cell_size)
        self.cells = {}
        for order, obj in enumerate(objects):
            x, y = obj.pos
            cell = (math.floor(x / self.cell_size), math.floor(y / self.cell_size))
            self.cells.setdefault(cell, []).append((order, obj))

    def cell_candidates(self, pos, radius):
        """Objects inside overlapping cells, before the distance test."""
        if radius < 0:
            raise ValueError("radius must be nonnegative")
        xmin = math.floor((pos.x - radius) / self.cell_size)
        xmax = math.floor((pos.x + radius) / self.cell_size)
        ymin = math.floor((pos.y - radius) / self.cell_size)
        ymax = math.floor((pos.y + radius) / self.cell_size)
        for x in range(xmin, xmax + 1):
            for y in range(ymin, ymax + 1):
                yield from self.cells.get((x, y), ())

    def query_radius(self, pos, radius):
        """Return (squared distance, original index, object), ordered.

        This ordering reproduces the existing nearest-first NPC interest
        selection when many ships are at the same distance.
        """
        radius_sq = radius * radius
        matches = []
        for index, obj in self.cell_candidates(pos, radius):
            dx, dy = obj.pos.x - pos.x, obj.pos.y - pos.y
            distance_sq = dx * dx + dy * dy
            if distance_sq <= radius_sq:
                matches.append((distance_sq, index, obj))
        matches.sort(key=lambda row: (row[0], row[1]))
        return matches
