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
