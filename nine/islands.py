"""Острова и скалы: форма, генерация, столкновения. Без графики.

Форма острова — «клякса»: радиус как функция угла, r(θ) = R·(1 + Σ aᵢ·sin(kᵢθ + φᵢ)).
Так столкновение считается одной формулой, а контур легко нарисовать.
"""

import math
from dataclasses import dataclass, field

from pygame.math import Vector2

from . import config as C

RUIN_CHANCE = 0.45
AGROUND_DAMAGE = 0.35       # урона за единицу скорости удара (сверх порога)
AGROUND_MIN_SPEED = 35.0


@dataclass
class Island:
    pos: Vector2
    radius: float
    seed: int
    ruins: bool = False
    lobes: tuple = field(default_factory=tuple)      # (амплитуда, частота, фаза)

    def r_at(self, angle_rad):
        return self.radius * (1.0 + sum(a * math.sin(k * angle_rad + ph) for a, k, ph in self.lobes))

    @property
    def r_max(self):
        return self.radius * (1.0 + sum(a for a, _, _ in self.lobes))

    def surface_point(self, pos):
        """Расстояние до центра, угол и радиус берега в направлении pos."""
        d = Vector2(pos) - self.pos
        dist = d.length()
        ang = math.atan2(d.y, d.x)
        return dist, ang, self.r_at(ang)

    def contains(self, pos, pad=0.0):
        if self.pos.distance_squared_to(pos) > (self.r_max + pad) ** 2:
            return False
        dist, _, r = self.surface_point(pos)
        return dist < r + pad

    def push_out(self, pos, pad):
        """Если точка ближе pad к берегу — (новая позиция, нормаль наружу), иначе None."""
        if self.pos.distance_squared_to(pos) > (self.r_max + pad) ** 2:
            return None
        dist, ang, r = self.surface_point(pos)
        if dist >= r + pad:
            return None
        normal = Vector2(math.cos(ang), math.sin(ang))
        return self.pos + normal * (r + pad), normal


def make_island(rng, pos, radius):
    lobes = tuple((rng.uniform(0.04, 0.16) / (i + 1) ** 0.5, k, rng.uniform(0, math.tau))
                  for i, k in enumerate(rng.sample((2, 3, 4, 5, 7, 9), 4)))
    return Island(Vector2(pos), radius, rng.randrange(1 << 30), rng.random() < RUIN_CHANCE, lobes)


def generate_islands(rng, port, eye, count=24):
    """Острова вдали от порта и от Стены Рёва, не налезающие друг на друга."""
    islands = []
    tries = 0
    while len(islands) < count and tries < 4000:
        tries += 1
        r = rng.uniform(60, 210)
        pos = Vector2(rng.uniform(300, C.WORLD_W - 300), rng.uniform(300, C.WORLD_H - 300))
        if pos.distance_to(port) < 800 + r or pos.distance_to(eye) < C.EYE_BELT_R + r:
            continue
        if any(pos.distance_to(o.pos) < (r + o.radius) * 1.6 + 120 for o in islands):
            continue
        islands.append(make_island(rng, pos, r))
    return islands


def island_at(islands, pos, pad=0.0):
    for isl in islands:
        if isl.contains(pos, pad):
            return isl
    return None


def collide_ship(ship, islands, rng):
    """Выталкивает корабль на воду. Возвращает скорость удара (0 — не было столкновения).

    The B-31's length would make a radius-58 island collision disk
    wildly oversized at the sides. Model its keel with overlapping
    probes instead; other hulls retain their original circle logic.
    """
    for isl in islands:
        if ship.hull.key == "bastion":
            forward = Vector2(1, 0).rotate(ship.angle)
            # 9 circles along the keel, radius 11.5, encompass the
            # 114x24 hull without turning the whole ship into a disk.
            hit = None
            for offset in (50, 38, 26, 14, 0, -14, -26, -38, -50):
                local_offset = forward * offset
                contact = isl.push_out(ship.pos + local_offset, 11.5)
                if contact is not None:
                    new_probe_pos, normal = contact
                    hit = new_probe_pos - local_offset, normal
                    break
        else:
            hit = isl.push_out(ship.pos, ship.radius * 0.8)
        if hit is None:
            continue
        new_pos, normal = hit
        ship.pos.update(new_pos)
        vn = ship.vel.dot(normal)
        if vn < 0:
            ship.vel -= normal * vn * 1.4
            ship.vel *= 0.6
            impact = -vn
            if impact > AGROUND_MIN_SPEED:
                ship.apply_damage((impact - AGROUND_MIN_SPEED) * AGROUND_DAMAGE, "torpedo", rng)
            return impact
    return 0.0


def avoid_turn(ship, islands, look=140.0):
    """Если по курсу остров — в какую сторону отвернуть (−1/1), иначе 0."""
    fwd = Vector2(1, 0).rotate(ship.angle)
    for dist in (look * 0.5, look):
        probe = ship.pos + fwd * dist
        isl = island_at(islands, probe, ship.radius + 20)
        if isl is not None:
            to_center = isl.pos - ship.pos
            side = fwd.cross(to_center)
            return -1.0 if side > 0 else 1.0
    return 0.0
