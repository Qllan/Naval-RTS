"""Ресурсы и лут. Корабли — в ship.py, снаряды — в combat.py."""

from dataclasses import dataclass, field

from pygame.math import Vector2


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
    modules: list = field(default_factory=list)   # трофейные модули — уходят на склад порта


@dataclass
class Smoke:
    pos: Vector2
    radius: float
    life: float
