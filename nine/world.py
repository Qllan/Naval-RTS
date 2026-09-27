"""Симуляция мира. Не знает про экран и клавиатуру — только Controls на входе.

Благодаря этому мир можно гонять в тестах без окна, а позже — на сервере.
"""

import math
import random
from collections import deque
from dataclasses import dataclass, field

from pygame.math import Vector2

from . import config as C
from .ai import Pirate, Ray, Tihodont
from .entities import RESOURCES, SHIP_CLASSES, Bullet, Loot, ResourceNode, Ship, heading
from .events import EventDirector
from .veil import Veil


@dataclass
class Controls:
    throttle: float = 0.0     # -1..1
    turn: float = 0.0         # -1..1, + = по часовой на экране
    boost: bool = False
    fire: bool = False
    aim: Vector2 | None = None
    mine: bool = False


@dataclass
class Captain:
    """Всё, что переживает гибель корабля."""
    credits: int = C.START_CREDITS
    debt: int = 0
    trauma: bool = False
    upgrades: dict = field(default_factory=lambda: {"sensor": 0, "cargo": 0, "gun": 0})
    cargo: dict = field(default_factory=dict)
    pending_insurance: int = 0
    kills: int = 0


class World:
    def __init__(self, seed=9, first_event=45.0):
        self.rng = random.Random(seed)
        self.t = 0.0
        self.veil = Veil(seed)
        self.events = EventDirector(seed, first_delay=first_event)
        self.veil.events = self.events

        self.port = Vector2(C.PORT_POS)
        self.eye = Vector2(C.EYE_POS)
        self.captain = Captain()
        self.player = Ship("scout", self.port + Vector2(0, -260), -90)
        self.in_capsule = False
        self.emp_timer = 0.0

        self.pirates: list[Pirate] = []
        self.tihodonts: list[Tihodont] = []
        self.rays: list[Ray] = []
        self.bullets: list[Bullet] = []
        self.nodes: list[ResourceNode] = []
        self.loot: list[Loot] = []
        self.log: deque = deque(maxlen=7)
        self.pirate_spawn_cd = 10.0

        for _ in range(280):
            self._spawn_node()
        for i in range(4):
            off = Vector2(1, 0).rotate(i * 90 + 45) * 120
            self.nodes.append(ResourceNode(self.eye + off, "zero", 25))
        self._spawn_tihodonts(16)
        self.say("Порт беженцев. Нейтральные воды. Удачи, капитан.")

    # --- служебное ------------------------------------------------------

    def say(self, text):
        self.log.append((text, self.t))

    def density_at(self, pos):
        return self.veil.density(pos, self.t)

    def _random_pos(self, margin=150):
        return Vector2(self.rng.uniform(margin, C.WORLD_W - margin), self.rng.uniform(margin, C.WORLD_H - margin))

    def _spawn_node(self):
        for _ in range(20):
            pos = self._random_pos()
            if pos.distance_to(self.port) < C.PORT_RADIUS + 120:
                continue
            if pos.distance_to(self.eye) < C.EYE_WALL_R:
                continue
            d = self.veil.static_density(pos.x, pos.y)
            kind = "salt" if d < C.ZONE_MIST else "condensate" if d < C.ZONE_DENSE else "filament"
            self.nodes.append(ResourceNode(pos, kind, self.rng.uniform(25, 60)))
            return

    def _spawn_tihodonts(self, n):
        tries = 0
        while len(self.tihodonts) < n and tries < 2000:
            tries += 1
            pos = self._random_pos()
            d = self.veil.static_density(pos.x, pos.y)
            if 0.25 < d < 0.7 and pos.distance_to(self.port) > 900:
                self.tihodonts.append(Tihodont(pos, self.rng))

    # --- производные показатели игрока ---------------------------------

    @property
    def cargo_capacity(self):
        return self.player.cls.cargo + 15 * self.captain.upgrades["cargo"]

    @property
    def cargo_used(self):
        return sum(self.captain.cargo.values())

    def radar_range(self):
        if self.emp_timer > 0:
            return 0.0
        d = self.density_at(self.player.pos)
        r = C.RADAR_BASE + C.RADAR_PER_LEVEL * self.captain.upgrades["sensor"]
        r *= 1.0 - C.RADAR_DENSITY_PENALTY * d
        r *= self.events.multiplier("radar", self.player.pos, self.t)
        if self.captain.trauma:
            r *= C.TRAUMA_RADAR_MULT
        return r

    def visual_range(self):
        return C.VISUAL_RANGE * (1.0 - 0.55 * self.density_at(self.player.pos))

    def sheltering_tihodont(self):
        for tx in self.tihodonts:
            if tx.pos.distance_to(self.player.pos) < Tihodont.RADIUS:
                return tx
        return None

    def player_loud(self):
        p = self.player
        return p.boosting or p.speed > p.cls.max_speed * 0.55

    def player_signature(self):
        """Насколько игрока легко засечь (множитель к дальности сенсоров NPC)."""
        p = self.player
        sig = 0.6 + 0.4 * min(1.0, p.speed / p.cls.max_speed)
        if p.boosting:
            sig *= 1.3
        if self.in_capsule:
            sig *= 0.6
        if self.sheltering_tihodont() and not self.player_loud():
            sig *= 0.05
        return sig

    def can_dock(self):
        return self.player.pos.distance_to(self.port) < C.PORT_RADIUS and self.player.speed < C.DOCK_MAX_SPEED

    def perceives(self, pos):
        """Игрок видит точку глазами или радаром."""
        d = self.player.pos.distance_to(pos)
        return d < self.visual_range() or d < self.radar_range()

    # --- главный шаг -----------------------------------------------------

    def update(self, dt, ctl: Controls):
        self.t += dt
        p = self.player
        self.events.update(self.t, p.pos)
        for ev in self.events.started:
            if ev.covers(p.pos) or self.perceives(ev.pos):
                self.say(f"{ev.data.name}!")

        density = self.density_at(p.pos)
        p.update(dt, ctl.throttle, ctl.turn, ctl.boost, density)
        self._eye_effects(dt)
        p.drain_shield(self.events.modifier("shield_drain", p.pos, self.t) * dt)

        if ctl.fire and not self.in_capsule and p.reload_timer <= 0 and ctl.aim is not None:
            self._player_fire(ctl.aim, density)
        if ctl.mine and not self.in_capsule:
            self._mine(dt)

        self._update_pirates(dt)
        self._update_fauna(dt)
        self._update_bullets(dt)
        self._update_loot(dt)

        if not p.alive:
            self._on_player_destroyed()

    def _eye_effects(self, dt):
        p = self.player
        dist = p.pos.distance_to(self.eye)
        self.emp_timer = max(0.0, self.emp_timer - dt)
        if dist < C.EYE_BELT_R and dist > C.EYE_CALM_R:
            # Гравитационная аномалия: течения тянут к центру, слабых — сильнее
            pull = 40.0 * (1.0 - dist / C.EYE_BELT_R) * (140.0 / p.cls.hull) ** 0.5
            p.vel += (self.eye - p.pos).normalize() * pull * dt
        if self.veil.in_wall(p.pos):
            p.damage(6.0 * dt)                            # стихийный урон
            if self.emp_timer <= 0 and self.rng.random() < 0.08 * dt:
                self.emp_timer = 6.0
                p.shield = 0.0
                self.say("ЭМ-вспышка! Электроника отключена.")

    def _player_fire(self, aim, density):
        p, cap = self.player, self.captain
        spread = 3.0 + 12.0 * density - 3.0 * self.events.modifier("accuracy", p.pos, self.t)
        direction = (Vector2(aim) - p.pos)
        if direction.length_squared() < 1:
            direction = heading(p.angle)
        direction = direction.normalize().rotate(self.rng.uniform(-spread, spread) if spread > 0 else 0)
        dmg = p.cls.gun_damage * (1.0 + 0.25 * cap.upgrades["gun"])
        self.bullets.append(Bullet(p.pos + direction * p.cls.radius, direction * 620 + p.vel * 0.5, dmg, "player"))
        reload = p.cls.reload * (1.0 - 0.12 * cap.upgrades["gun"])
        if cap.trauma:
            reload *= C.TRAUMA_RELOAD_MULT
        p.reload_timer = reload

    def _mine(self, dt):
        p = self.player
        if p.speed > 80:
            return
        node = min(self.nodes, key=lambda n: n.pos.distance_squared_to(p.pos), default=None)
        if node is None or node.pos.distance_to(p.pos) > 75:
            return
        space = self.cargo_capacity - self.cargo_used
        if space <= 0:
            return
        rate = 6.0 * (1.8 if p.cls.key == "barge" else 1.0)
        take = min(rate * dt, node.amount, space)
        node.amount -= take
        self.captain.cargo[node.kind] = self.captain.cargo.get(node.kind, 0) + take
        if node.amount <= 0.01:
            self.nodes.remove(node)
            if node.kind != "zero":
                self._spawn_node()
            self.say(f"Точка выработана: {RESOURCES[node.kind].name}")

    def _update_pirates(self, dt):
        p = self.player
        self.pirate_spawn_cd -= dt
        density = self.density_at(p.pos)
        wanted = 0 if p.pos.distance_to(self.port) < 1500 else 1 + int(4 * density)
        alive = [pr for pr in self.pirates if pr.ship.pos.distance_to(p.pos) < 2600]
        self.pirates = alive
        if len(self.pirates) < wanted and self.pirate_spawn_cd <= 0:
            pos = p.pos + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(1100, 1500)
            if pos.distance_to(self.port) > 1400:
                pos.x = min(max(pos.x, 50), C.WORLD_W - 50)
                pos.y = min(max(pos.y, 50), C.WORLD_H - 50)
                self.pirates.append(Pirate(pos, self.rng))
            self.pirate_spawn_cd = 12.0

        sig = self.player_signature()
        for pr in self.pirates:
            d = self.density_at(pr.ship.pos)
            throttle, turn, fire, aim = pr.think(p.pos, sig, d, dt)
            pr.ship.update(dt, throttle, turn, False, d)
            if fire and aim is not None and pr.ship.reload_timer <= 0:
                direction = aim - pr.ship.pos
                if direction.length() > 1:
                    spread = 6.0 + 15.0 * d
                    direction = direction.normalize().rotate(self.rng.uniform(-spread, spread))
                    self.bullets.append(Bullet(pr.ship.pos + direction * 16, direction * 520, pr.ship.cls.gun_damage, "pirate"))
                    pr.ship.reload_timer = pr.ship.cls.reload

    def _update_fauna(self, dt):
        p = self.player
        loud = self.player_loud()
        for tx in self.tihodonts:
            was = tx.angry
            tx.update(dt, p.pos, loud)
            if tx.angry and not was and tx.pos.distance_to(p.pos) < 400:
                self.say("Тиходонт разбужен шумом двигателя!")
            if tx.angry and tx.pos.distance_to(p.pos) < Tihodont.RADIUS * 0.7:
                p.damage(30.0 * dt, ignore_shield=True)

        self.rays = [r for r in self.rays if r.pos.distance_to(p.pos) < 1500]
        while len(self.rays) < 14:
            pos = p.pos + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(150, 900)
            self.rays.append(Ray(pos, self.rng))
        for r in self.rays:
            r.update(dt, self.events.warning_at(r.pos, self.t))

    def _update_bullets(self, dt):
        p = self.player
        keep = []
        for b in self.bullets:
            b.pos += b.vel * dt
            b.life -= dt
            hit = False
            if b.owner == "player":
                for pr in self.pirates:
                    if pr.ship.pos.distance_to(b.pos) < pr.ship.cls.radius:
                        pr.ship.damage(b.damage)
                        hit = True
                        break
            elif p.pos.distance_to(b.pos) < p.cls.radius:
                p.damage(b.damage)
                hit = True
            if not hit and b.life > 0:
                keep.append(b)
        self.bullets = keep

        for pr in [pr for pr in self.pirates if not pr.ship.alive]:
            self.pirates.remove(pr)
            self.captain.kills += 1
            kind = self.rng.choice(["salt", "condensate", "condensate", "filament"])
            self.loot.append(Loot(Vector2(pr.ship.pos), {kind: self.rng.randint(3, 8)}, self.rng.randint(40, 90)))
            self.say("Рейдер Прилива потоплен. Обломки на воде.")

    def _update_loot(self, dt):
        p, cap = self.player, self.captain
        keep = []
        for lt in self.loot:
            lt.life -= dt
            if not self.in_capsule and lt.pos.distance_to(p.pos) < 45:
                cap.credits += lt.credits
                lt.credits = 0
                for kind, qty in list(lt.cargo.items()):
                    take = min(qty, self.cargo_capacity - self.cargo_used)
                    if take > 0:
                        cap.cargo[kind] = cap.cargo.get(kind, 0) + take
                        lt.cargo[kind] = qty - take
                lt.cargo = {k: v for k, v in lt.cargo.items() if v > 0.01}
                if not lt.cargo:
                    self.say("Обломки подобраны.")
                    continue
            if lt.life > 0:
                keep.append(lt)
        self.loot = keep

    # --- смерть и капсула -----------------------------------------------

    def _on_player_destroyed(self):
        cap = self.captain
        pos = Vector2(self.player.pos)
        if self.in_capsule:
            cap.debt += C.CAPSULE_DEBT
            cap.trauma = True
            cap.cargo = {}
            self.in_capsule = False
            self.player = Ship("scout", self.port + Vector2(0, -260), -90)
            self.say(f"Капсула уничтожена. Спасатели вытащили вас. Долг +{C.CAPSULE_DEBT} КК, травма.")
            return
        # Корабль потерян: часть груза остаётся в обломках, капитан — в капсуле
        salvage = {k: v * 0.5 for k, v in cap.cargo.items() if v * 0.5 >= 1}
        if salvage:
            self.loot.append(Loot(pos, salvage, 0, life=40.0))
        cap.cargo = {}
        cap.pending_insurance = int(self.player.cls.price * C.INSURANCE_RATE)
        self.player = Ship("capsule", pos, self.player.angle)
        self.in_capsule = True
        self.say("Корабль потерян! Капсула отстрелена — доберитесь до порта.")

    # --- действия в порту -----------------------------------------------

    def dock(self):
        """Вызывается при заходе в порт. Капсула получает новый корабль."""
        cap = self.captain
        if self.in_capsule:
            self.in_capsule = False
            self.player = Ship("scout", self.port, -90)
            if cap.pending_insurance:
                cap.credits += cap.pending_insurance
                self.say(f"Страховка выплачена: {cap.pending_insurance} КК. Выдан Скаут.")
                cap.pending_insurance = 0
            else:
                self.say("Порт выдал вам списанный Скаут.")
        self.player.vel = Vector2()
        self.player.shield = self.player.cls.shield

    def undock(self):
        self.player.pos = self.port + Vector2(0, -C.PORT_RADIUS - 40)
        self.player.angle = -90

    def cargo_value(self):
        return int(sum(RESOURCES[k].price * v for k, v in self.captain.cargo.items()))

    def sell_cargo(self):
        value = self.cargo_value()
        self.captain.credits += value
        self.captain.cargo = {}
        return value

    def repair_cost(self):
        return int((self.player.cls.hull - self.player.hull) * C.REPAIR_COST_PER_HP)

    def repair(self):
        cap, p = self.captain, self.player
        missing = p.cls.hull - p.hull
        affordable = cap.credits / C.REPAIR_COST_PER_HP
        hp = min(missing, affordable)
        cap.credits -= int(math.ceil(hp * C.REPAIR_COST_PER_HP))
        p.hull += hp
        return hp

    def clean_hull(self):
        if self.player.fouling <= 0.01 or self.captain.credits < C.CLEAN_COST:
            return False
        self.captain.credits -= C.CLEAN_COST
        self.player.fouling = 0.0
        return True

    def upgrade_cost(self, kind):
        lvl = self.captain.upgrades[kind]
        costs = C.UPGRADE_COSTS[kind]
        return costs[lvl] if lvl < len(costs) else None

    def buy_upgrade(self, kind):
        cap = self.captain
        cost = self.upgrade_cost(kind)
        if cost is None or cap.debt > 0 or cap.credits < cost:
            return False
        cap.credits -= cost
        cap.upgrades[kind] += 1
        return True

    def ship_cost(self, key):
        return max(0, SHIP_CLASSES[key].price - self.player.cls.price // 2)

    def buy_ship(self, key):
        cap = self.captain
        if key == self.player.cls.key or cap.debt > 0:
            return False
        cost = self.ship_cost(key)
        if cap.credits < cost:
            return False
        if self.cargo_used > SHIP_CLASSES[key].cargo + 15 * cap.upgrades["cargo"]:
            return False
        cap.credits -= cost
        pos = Vector2(self.player.pos)
        self.player = Ship(key, pos, -90)
        return True

    def pay_debt(self):
        cap = self.captain
        pay = min(cap.debt, cap.credits)
        cap.debt -= pay
        cap.credits -= pay
        return pay

    def heal(self):
        cap = self.captain
        if not cap.trauma or cap.credits < C.MEDICAL_COST:
            return False
        cap.credits -= C.MEDICAL_COST
        cap.trauma = False
        return True
