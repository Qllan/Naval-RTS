"""NPC и фауна на простых конечных автоматах."""

import math
import random

from pygame.math import Vector2

from .ship import Ship, heading


def steer_towards(ship, target, gain=0.05):
    """Возвращает turn в [-1, 1], чтобы нос смотрел на цель."""
    to = Vector2(target) - ship.pos
    if to.length_squared() < 1:
        return 0.0
    diff = (heading(ship.angle).angle_to(to) + 180) % 360 - 180
    return max(-1.0, min(1.0, diff * gain))


# Варианты оснащения рейдеров: (корпус, модули, минимальная плотность для появления)
PIRATE_LOADOUTS = {
    "gunner": ("raider", ("autocannon_s", None, "engine_s2", "reactor_s", "shield_s", None, "sensor_s"), 0.0),
    "brawler": ("raider", ("scatter_s", None, "engine_s2", "reactor_s", "shield_s", None, "sensor_s"), 0.2),
    "rocketeer": ("raider", ("autocannon_s", "missile_s", "engine_s2", "reactor_s", "shield_s", None,
                             "sensor_s"), 0.35),
    "hunter": ("corvette", ("scatter_s", "autocannon_s", "engine_s", "reactor_s2", "shield_s", "armor_s",
                            "sensor_s", None, None), 0.5),
}


class Pirate:
    """Рейдер Ржавого Прилива: патруль → погоня → атака → бегство."""

    SENSOR = 700.0

    def __init__(self, pos, rng: random.Random, loadout="gunner"):
        hull, fit, _ = PIRATE_LOADOUTS[loadout]
        self.loadout = loadout
        self.ship = Ship(hull, pos, rng.uniform(0, 360), fit=fit, side="pirate")
        self.rng = rng
        self.state = "patrol"
        self.home = Vector2(pos)
        self.waypoint = self._new_waypoint()
        self.lost_timer = 0.0
        guns = [w.defn.range for w in self.ship.weapons if w.defn.kind == "gun"]
        self.engage_range = min(guns) * 0.75 if guns else 400

    def _new_waypoint(self):
        return self.home + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(100, 500)

    def think(self, player_pos, player_signature, density, dt):
        """Возвращает (throttle, turn, sees_player)."""
        ship = self.ship
        dist = ship.pos.distance_to(player_pos) if player_pos is not None else 1e9
        # Чем плотнее Пелена, тем хуже видят и пираты
        detect = self.SENSOR * (1.0 - 0.6 * density) * player_signature
        sees = dist < detect

        if ship.hp < ship.hull.hp * 0.25 or ship.subsystems["weapons"] < 0.2:
            self.state = "flee"
        elif sees:
            self.state = "attack" if dist < self.engage_range * 1.3 else "chase"
            self.lost_timer = 4.0
        elif self.state in ("chase", "attack"):
            self.lost_timer -= dt
            if self.lost_timer <= 0:
                self.state = "patrol"

        if self.state == "patrol":
            if ship.pos.distance_to(self.waypoint) < 60:
                self.waypoint = self._new_waypoint()
            return 0.45, steer_towards(ship, self.waypoint), sees
        if self.state == "chase":
            return 1.0, steer_towards(ship, player_pos), sees
        if self.state == "attack":
            # кружит на дистанции своего оружия
            to = Vector2(player_pos) - ship.pos
            if to.length() > 0:
                orbit = Vector2(player_pos) - to.normalize().rotate(40) * self.engage_range
            else:
                orbit = Vector2(player_pos)
            return 0.8, steer_towards(ship, orbit), sees
        away = ship.pos + (ship.pos - Vector2(player_pos if player_pos is not None else self.home))
        return 1.0, steer_towards(ship, away), sees


class Tihodont:
    """Мирный гигант. Под ним не работают радары. Шум двигателя злит его."""

    RADIUS = 145.0

    def __init__(self, pos, rng: random.Random):
        self.pos = Vector2(pos)
        self.angle = rng.uniform(0, 360)
        self.rng = rng
        self.anger = 0.0
        self.turn_timer = 0.0
        self.breath = rng.uniform(4, 20)      # до следующего выдоха (фонтан над дыхалом)
        self.swim = rng.uniform(0, 10)        # фаза взмахов хвоста

    @property
    def blowhole(self):
        return self.pos + heading(self.angle) * self.RADIUS * 0.55

    def update(self, dt, player_pos, player_loud):
        """Возвращает True, если в этот кадр Тиходонт выдохнул."""
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
        self.swim += dt * (0.8 + speed / 60)
        self.pos += heading(self.angle) * speed * dt
        self.breath -= dt * (3.0 if self.angry else 1.0)
        if self.breath <= 0:
            self.breath = self.rng.uniform(14, 30)
            return True
        return False

    @property
    def angry(self):
        return self.anger > 2.0


class Ray:
    """Скат-флюкс — живой индикатор. Перед Всплеском уходит на глубину."""

    def __init__(self, pos, rng: random.Random, school=0, angle=None):
        self.pos = Vector2(pos)
        self.angle = rng.uniform(0, 360) if angle is None else angle
        self.rng = rng
        self.depth = 0.0            # 0 — у поверхности, 1 — ушёл
        self.diving = False
        self.school = school        # скаты держатся стаями
        self.size = rng.uniform(0.9, 1.5)
        self.phase = rng.uniform(0, math.tau)

    def steer(self, goal_angle, rate, dt):
        diff = (goal_angle - self.angle + 180) % 360 - 180
        self.angle += max(-rate * dt, min(rate * dt, diff))

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
