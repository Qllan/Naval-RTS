"""Слой мировых событий.

`WorldEventData` — аналог ScriptableObject из GDD: событие описано данными
(список модификаторов), логика общая. Новое событие = новая запись в EVENTS.
"""

import random
from dataclasses import dataclass, field

import numpy as np
from pygame.math import Vector2


@dataclass(frozen=True)
class Modifier:
    kind: str      # density (+), radar (множитель), shield_drain (ед/с), accuracy (+)
    value: float


@dataclass(frozen=True)
class WorldEventData:
    name: str
    duration: float
    radius: float
    warning_time: float          # сколько секунд до начала скаты уходят на глубину
    spawn_weight: float
    modifiers: tuple = field(default_factory=tuple)
    color: tuple = (150, 60, 200)
    telegraphed_by_rays: bool = False


SURGE = WorldEventData(
    name="Всплеск Пелены",
    duration=25.0,
    radius=950.0,
    warning_time=18.0,
    spawn_weight=3.0,
    modifiers=(Modifier("density", 0.5), Modifier("radar", 0.2), Modifier("shield_drain", 7.0)),
    color=(170, 70, 230),
    telegraphed_by_rays=True,
)

CALM = WorldEventData(
    name="Штиль",
    duration=30.0,
    radius=1100.0,
    warning_time=0.0,
    spawn_weight=2.0,
    modifiers=(Modifier("density", -0.45), Modifier("accuracy", 0.6)),
    color=(140, 200, 230),
)

EVENTS = (SURGE, CALM)


@dataclass
class ActiveEvent:
    data: WorldEventData
    pos: Vector2
    start: float                 # момент перехода в активную фазу
    announced: bool = False

    def phase(self, t):
        if t < self.start:
            return "warning"
        if t < self.start + self.data.duration:
            return "active"
        return "over"

    def strength(self, pos, t):
        """0..1: мягкий край по радиусу, плавный вход/выход по времени."""
        if self.phase(t) != "active":
            return 0.0
        dist = self.pos.distance_to(pos)
        if dist >= self.data.radius:
            return 0.0
        edge = 1.0 - dist / self.data.radius
        spatial = min(1.0, edge / 0.25)
        age = t - self.start
        left = self.start + self.data.duration - t
        temporal = min(1.0, age / 3.0, left / 3.0)
        return spatial * temporal

    def strength_grid(self, X, Y, t):
        """strength() для массивов координат (numpy)."""
        if self.phase(t) != "active":
            return 0.0
        dist = np.hypot(X - self.pos.x, Y - self.pos.y)
        spatial = np.clip((1.0 - dist / self.data.radius) / 0.25, 0.0, 1.0)
        age = t - self.start
        left = self.start + self.data.duration - t
        return spatial * min(1.0, age / 3.0, left / 3.0)

    def covers(self, pos):
        return self.pos.distance_to(pos) < self.data.radius


class EventDirector:
    def __init__(self, seed=1, first_delay=45.0, interval=(70.0, 120.0)):
        self.rng = random.Random(seed)
        self.interval = interval
        self.next_spawn = first_delay
        self.active: list[ActiveEvent] = []
        self.started: list[ActiveEvent] = []   # события, ставшие активными на этом кадре

    def pick(self):
        total = sum(e.spawn_weight for e in EVENTS)
        r = self.rng.uniform(0, total)
        for e in EVENTS:
            r -= e.spawn_weight
            if r <= 0:
                return e
        return EVENTS[-1]

    def spawn(self, data, pos, t):
        ev = ActiveEvent(data, Vector2(pos), t + data.warning_time)
        self.active.append(ev)
        return ev

    def update(self, t, player_pos):
        self.started = []
        if t >= self.next_spawn:
            data = self.pick()
            off = Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(150, 700)
            self.spawn(data, Vector2(player_pos) + off, t)
            self.next_spawn = t + self.rng.uniform(*self.interval)
        for e in self.active:
            if e.phase(t) == "active" and not e.announced:
                e.announced = True
                self.started.append(e)
        self.active = [e for e in self.active if e.phase(t) != "over"]

    def modifier(self, kind, pos, t):
        """Суммарный аддитивный модификатор (density, shield_drain, accuracy)."""
        total = 0.0
        for e in self.active:
            s = e.strength(pos, t)
            if s <= 0:
                continue
            for m in e.data.modifiers:
                if m.kind == kind:
                    total += m.value * s
        return total

    def modifier_grid(self, kind, X, Y, t):
        total = 0.0
        for e in self.active:
            for m in e.data.modifiers:
                if m.kind == kind:
                    total = total + m.value * e.strength_grid(X, Y, t)
        return total

    def multiplier(self, kind, pos, t):
        """Мультипликативный модификатор (radar)."""
        mult = 1.0
        for e in self.active:
            s = e.strength(pos, t)
            if s <= 0:
                continue
            for m in e.data.modifiers:
                if m.kind == kind:
                    mult *= 1.0 + (m.value - 1.0) * s
        return mult

    def warning_at(self, pos, t):
        """Есть ли надвигающееся событие, которое чувствуют скаты."""
        return any(
            e.phase(t) == "warning" and e.data.telegraphed_by_rays and e.covers(pos) for e in self.active
        )
