"""NPC и фауна на простых конечных автоматах."""

import random

from pygame.math import Vector2

from .entities import Ship, heading


def steer_towards(ship, target, dt_turn_gain=0.05):
    """Возвращает turn в [-1, 1], чтобы нос смотрел на цель."""
    to = Vector2(target) - ship.pos
    if to.length_squared() < 1:
        return 0.0
    diff = (heading(ship.angle).angle_to(to) + 180) % 360 - 180
    return max(-1.0, min(1.0, diff * dt_turn_gain))


class Pirate:
    """Рейдер Ржавого Прилива: патруль → погоня → атака → бегство."""

    SENSOR = 700.0

    def __init__(self, pos, rng: random.Random):
        self.ship = Ship("raider", pos, rng.uniform(0, 360))
        self.rng = rng
        self.state = "patrol"
        self.home = Vector2(pos)
        self.waypoint = self._new_waypoint()
        self.lost_timer = 0.0

    def _new_waypoint(self):
        return self.home + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(100, 500)

    def think(self, player_pos, player_signature, density, dt):
        """Возвращает (throttle, turn, fire, aim)."""
        dist = self.ship.pos.distance_to(player_pos) if player_pos is not None else 1e9
        # Чем плотнее Пелена, тем хуже видят и пираты
        detect = self.SENSOR * (1.0 - 0.6 * density) * player_signature
        sees = dist < detect

        if self.ship.hull < self.ship.cls.hull * 0.25:
            self.state = "flee"
        elif sees:
            self.state = "attack" if dist < 360 else "chase"
            self.lost_timer = 4.0
        elif self.state in ("chase", "attack"):
            self.lost_timer -= dt
            if self.lost_timer <= 0:
                self.state = "patrol"

        if self.state == "patrol":
            if self.ship.pos.distance_to(self.waypoint) < 60:
                self.waypoint = self._new_waypoint()
            return 0.45, steer_towards(self.ship, self.waypoint), False, None
        if self.state == "chase":
            return 1.0, steer_towards(self.ship, player_pos), False, None
        if self.state == "attack":
            # кружит на дистанции и стреляет
            to = Vector2(player_pos) - self.ship.pos
            orbit = Vector2(player_pos) - to.normalize().rotate(40) * 220 if to.length() > 0 else player_pos
            return 0.8, steer_towards(self.ship, orbit), True, Vector2(player_pos)
        # flee
        away = self.ship.pos + (self.ship.pos - Vector2(player_pos if player_pos is not None else self.home))
        return 1.0, steer_towards(self.ship, away), False, None


class Tihodont:
    """Мирный гигант. Под ним не работают радары. Шум двигателя злит его."""

    RADIUS = 125.0

    def __init__(self, pos, rng: random.Random):
        self.pos = Vector2(pos)
        self.angle = rng.uniform(0, 360)
        self.rng = rng
        self.anger = 0.0
        self.turn_timer = 0.0

    def update(self, dt, player_pos, player_loud):
        near = player_pos is not None and self.pos.distance_to(player_pos) < self.RADIUS * 1.6
        if near and player_loud:
            self.anger = min(8.0, self.anger + dt * 3)
        else:
            self.anger = max(0.0, self.anger - dt)

        if self.anger > 2.0 and player_pos is not None:
            to = Vector2(player_pos) - self.pos
            if to.length() > 1:
                self.angle = Vector2(1, 0).angle_to(to)
            speed = 150.0
        else:
            self.turn_timer -= dt
            if self.turn_timer <= 0:
                self.angle += self.rng.uniform(-40, 40)
                self.turn_timer = self.rng.uniform(3, 7)
            speed = 18.0
        self.pos += heading(self.angle) * speed * dt

    @property
    def angry(self):
        return self.anger > 2.0


class Ray:
    """Скат-флюкс — живой индикатор. Перед Всплеском уходит на глубину."""

    def __init__(self, pos, rng: random.Random):
        self.pos = Vector2(pos)
        self.angle = rng.uniform(0, 360)
        self.rng = rng
        self.depth = 0.0            # 0 — у поверхности, 1 — ушёл
        self.diving = False

    def update(self, dt, warned):
        self.diving = warned
        target = 1.0 if warned else 0.0
        rate = 0.5 if warned else 0.15
        if self.depth < target:
            self.depth = min(target, self.depth + rate * dt)
        else:
            self.depth = max(target, self.depth - rate * dt)
        self.angle += self.rng.uniform(-30, 30) * dt
        self.pos += heading(self.angle) * (60.0 if warned else 25.0) * dt
