"""Корабли, снаряды, ресурсы, лут. Чистая симуляция — без отрисовки."""

import math
from dataclasses import dataclass, field

from pygame.math import Vector2

from . import config as C


@dataclass(frozen=True)
class ShipClass:
    key: str
    name: str
    hull: float
    shield: float
    thrust: float          # ускорение, ед/с²
    max_speed: float
    turn_rate: float       # град/с на полном ходу
    cargo: int
    gun_damage: float
    reload: float
    radius: float
    price: int
    shape: tuple           # полигон корпуса (нос вдоль +X)


SHIP_CLASSES = {
    "scout": ShipClass("scout", "Скаут", 100, 60, 170, 230, 150, 20, 9, 0.30, 16, 0,
                       ((20, 0), (4, 8), (-14, 8), (-18, 0), (-14, -8), (4, -8))),
    "cruiser": ShipClass("cruiser", "Крейсер", 260, 140, 130, 185, 95, 35, 15, 0.26, 22, 2400,
                         ((28, 0), (10, 11), (-20, 12), (-26, 0), (-20, -12), (10, -11))),
    "barge": ShipClass("barge", "Барка добытчика", 220, 80, 90, 140, 70, 90, 7, 0.45, 26, 1800,
                       ((24, 0), (18, 14), (-26, 14), (-26, -14), (18, -14))),
    "capsule": ShipClass("capsule", "Спасательная капсула", 22, 0, 150, 200, 200, 0, 0, 99, 8, 0,
                         ((8, 0), (0, 6), (-7, 0), (0, -6))),
    "raider": ShipClass("raider", "Рейдер Прилива", 70, 20, 160, 210, 130, 0, 6, 0.55, 15, 0,
                        ((18, 0), (0, 10), (-14, 6), (-10, 0), (-14, -6), (0, -10))),
}


@dataclass(frozen=True)
class ResourceKind:
    key: str
    name: str
    price: int
    color: tuple


RESOURCES = {
    "salt": ResourceKind("salt", "Соль-металл", 6, (170, 190, 200)),
    "condensate": ResourceKind("condensate", "Конденсат Пелены", 22, (170, 110, 230)),
    "filament": ResourceKind("filament", "Окаменевшие филаменты", 60, (230, 200, 255)),
    "zero": ResourceKind("zero", "Изотоп «Ноль»", 320, (255, 255, 255)),
}


def heading(angle):
    return Vector2(1, 0).rotate(angle)


class Ship:
    def __init__(self, cls_key, pos, angle=0.0):
        self.cls = SHIP_CLASSES[cls_key]
        self.pos = Vector2(pos)
        self.vel = Vector2()
        self.angle = angle
        self.hull = self.cls.hull
        self.shield = self.cls.shield
        self.shield_cd = 0.0
        self.reload_timer = 0.0
        self.fouling = 0.0          # 0..1 — налёт филаментов на корпусе
        self.throttle = 0.0
        self.boosting = False

    @property
    def alive(self):
        return self.hull > 0

    @property
    def speed(self):
        return self.vel.length()

    def max_speed(self):
        s = self.cls.max_speed * (1.0 - 0.55 * self.fouling)
        return s * (1.45 if self.boosting else 1.0)

    def update(self, dt, throttle, turn, boost, density):
        self.throttle = throttle
        self.boosting = boost and throttle > 0
        fwd = heading(self.angle)

        # Поворот эффективнее на ходу — руль работает от набегающего потока
        speed_k = 0.35 + 0.65 * min(1.0, self.speed / max(1.0, self.cls.max_speed))
        self.angle = (self.angle + turn * self.cls.turn_rate * speed_k * dt) % 360

        accel = self.cls.thrust * (1.0 - 0.4 * self.fouling) * (1.6 if self.boosting else 1.0)
        if throttle < 0:
            accel *= 0.5
        self.vel += fwd * accel * throttle * dt

        # «Киль»: боковой снос гасится быстро, продольный — медленно
        fwd = heading(self.angle)
        along = fwd * self.vel.dot(fwd)
        lateral = self.vel - along
        self.vel = along * math.exp(-0.35 * dt) + lateral * math.exp(-3.0 * dt)

        vmax = self.max_speed()
        if self.vel.length() > vmax:
            self.vel.scale_to_length(vmax)
        self.pos += self.vel * dt
        self.pos.x = min(max(self.pos.x, 0), C.WORLD_W)
        self.pos.y = min(max(self.pos.y, 0), C.WORLD_H)

        # Налёт: быстро идёшь в Пелене — она полимеризуется на корпусе
        fast = self.speed > self.cls.max_speed * C.FOUL_SPEED_FRACTION
        if fast and density > C.FOUL_MIN_DENSITY:
            self.fouling += C.FOUL_RATE * density * (2.0 if self.boosting else 1.0) * dt
        else:
            self.fouling -= C.FOUL_DECAY * (1.0 - density) * dt
        self.fouling = min(1.0, max(0.0, self.fouling))

        # Щиты — электроника: в Пелене регенерация падает
        self.reload_timer = max(0.0, self.reload_timer - dt)
        if self.shield_cd > 0:
            self.shield_cd -= dt
        elif self.cls.shield > 0:
            regen = self.cls.shield * 0.12 * (1.0 - 0.85 * density)
            self.shield = min(self.cls.shield, self.shield + regen * dt)

    def damage(self, amount, ignore_shield=False):
        self.shield_cd = 3.0
        if not ignore_shield and self.shield > 0:
            absorbed = min(self.shield, amount)
            self.shield -= absorbed
            amount -= absorbed
        self.hull -= amount

    def drain_shield(self, amount):
        if amount > 0:
            self.shield = max(0.0, self.shield - amount)
            self.shield_cd = max(self.shield_cd, 1.0)


@dataclass
class Bullet:
    pos: Vector2
    vel: Vector2
    damage: float
    owner: str            # "player" | "pirate"
    life: float = 1.6


@dataclass
class ResourceNode:
    pos: Vector2
    kind: str
    amount: float


@dataclass
class Loot:
    pos: Vector2
    cargo: dict = field(default_factory=dict)
    credits: int = 0
    life: float = 60.0
