"""Корабль = корпус + модули в слотах. Все характеристики выводятся из оснащения.

Системы:
- энергия: реактор заряжает конденсатор, модули его расходуют; электроника в
  Пелене прожорливее; при нуле в конденсаторе — «просадка»: щиты гаснут, радар слепнет;
- масса: модули и груз снижают разгон, скорость и манёвренность;
- защита слоями: щит → броня → корпус, с разной реакцией на типы урона;
- подсистемы (двигатель, руль, сенсоры, орудия) деградируют от попаданий.
"""

import math

from pygame.math import Vector2

from . import config as C
from .hulls import HULLS
from .modules import (MODULES, ArmorDef, EngineDef, ReactorDef, SensorDef, ShieldDef, UtilityDef,
                      WeaponDef)

SUBSYSTEMS = ("engine", "rudder", "sensors", "weapons")
SUBSYSTEM_NAME = {"engine": "Двигатель", "rudder": "Руль", "sensors": "Сенсоры", "weapons": "Орудия"}
CARGO_MASS = 0.8          # масса единицы груза
VEIL_UPKEEP = 1.5         # +150% потребления электроники при плотности 1.0


def heading(angle):
    return Vector2(1, 0).rotate(angle)


def norm_angle(a):
    return (a + 180) % 360 - 180


def fit_problems(hull, fit):
    """Ошибки оснащения: неподходящие слоты и дефицит энергии в чистой воде."""
    problems = []
    if len(fit) != len(hull.slots):
        return ["Число модулей не совпадает со слотами"]
    upkeep = output = 0.0
    for slot, key in zip(hull.slots, fit):
        if key is None:
            continue
        m = MODULES[key]
        if m.category != slot.category:
            problems.append(f"{m.name}: не тот тип слота")
        elif m.size > slot.size:
            problems.append(f"{m.name}: слишком большой для слота")
        upkeep += m.upkeep
        if isinstance(m, ReactorDef):
            output += m.output
    if upkeep > output + 1e-6:
        problems.append(f"Не хватает энергии: {upkeep:g} > {output:g}")
    return problems


class WeaponMount:
    def __init__(self, index, slot, defn: WeaponDef):
        self.index = index
        self.slot = slot
        self.defn = defn
        self.rel = 0.0                    # угол турели относительно направления слота
        self.reload = 0.0
        self.ammo = defn.ammo
        self.lock_target = None
        self.lock = 0.0                   # 0..1

    @property
    def arc(self):
        return min(self.defn.arc, self.slot.arc)

    def world_pos(self, ship):
        return ship.pos + Vector2(self.slot.pos).rotate(ship.angle)

    def world_angle(self, ship):
        return ship.angle + self.slot.facing + self.rel

    def in_arc(self, ship, point):
        to = Vector2(point) - self.world_pos(ship)
        if to.length_squared() < 1:
            return True
        want = norm_angle(Vector2(1, 0).angle_to(to) - ship.angle - self.slot.facing)
        return abs(want) <= self.arc / 2

    def aim(self, ship, point, dt):
        """Доворачивает турель к точке с ограниченной скоростью. Возвращает True, если навелась."""
        if self.defn.traverse <= 0:
            return self.in_arc(ship, point)
        to = Vector2(point) - self.world_pos(ship)
        if to.length_squared() < 1:
            return True
        want = norm_angle(Vector2(1, 0).angle_to(to) - ship.angle - self.slot.facing)
        half = self.arc / 2
        target = max(-half, min(half, want))
        speed = self.defn.traverse * (0.3 + 0.7 * ship.subsystems["weapons"])
        step = speed * dt
        diff = target - self.rel
        self.rel += max(-step, min(step, diff))
        return abs(want) <= half and abs(want - self.rel) < 4.0

    @property
    def has_ammo(self):
        return self.defn.ammo == 0 or self.ammo > 0


class UtilityState:
    def __init__(self, index, defn: UtilityDef):
        self.index = index
        self.defn = defn
        self.cooldown = 0.0
        self.active_time = 0.0
        self.charges = defn.charges

    @property
    def ready(self):
        return self.cooldown <= 0 and (self.defn.charges == 0 or self.charges > 0)


class Ship:
    def __init__(self, hull_key, pos, angle=0.0, fit=None, side="player"):
        self.hull = HULLS[hull_key]
        self.fit = list(fit if fit is not None else self.hull.default_fit)
        self.side = side
        self.pos = Vector2(pos)
        self.vel = Vector2()
        self.angle = angle
        self.throttle = 0.0
        self.boosting = False
        self.fouling = 0.0
        self.cargo_mass = 0.0
        self.shield_cd = 0.0
        self.brownout = False
        self.reload_penalty = 1.0          # внешние штрафы (травма капитана)
        self.subsystems = {k: 1.0 for k in SUBSYSTEMS}
        self.rebuild()
        self.hp = self.hull.hp
        self.armor = self.armor_max
        self.shield = self.shield_max
        self.capacitor = self.cap_max

    # --- сборка -----------------------------------------------------------

    def modules(self, cls=None):
        for i, (slot, key) in enumerate(zip(self.hull.slots, self.fit)):
            if key is None:
                continue
            m = MODULES[key]
            if cls is None or isinstance(m, cls):
                yield i, slot, m

    def _first(self, cls):
        return next((m for _, _, m in self.modules(cls)), None)

    def rebuild(self):
        """Пересчитать производные характеристики после смены оснащения."""
        old_weapons = {w.index: w for w in getattr(self, "weapons", [])}
        old_utils = {u.index: u for u in getattr(self, "utilities", [])}

        self.engine = self._first(EngineDef)
        self.reactor = self._first(ReactorDef)
        self.shield_def = self._first(ShieldDef)
        self.armor_def = self._first(ArmorDef)
        self.sensor = self._first(SensorDef)
        self.module_mass = sum(m.mass for _, _, m in self.modules())

        self.shield_max = self.shield_def.capacity if self.shield_def else 0.0
        self.armor_max = self.armor_def.hp if self.armor_def else 0.0
        self.cap_max = self.reactor.capacitor if self.reactor else 0.0
        self.output = self.reactor.output if self.reactor else 0.0

        self.weapons = []
        for i, slot, m in self.modules(WeaponDef):
            w = WeaponMount(i, slot, m)
            old = old_weapons.get(i)
            if old and old.defn is m:
                w.ammo, w.rel = old.ammo, old.rel
            self.weapons.append(w)
        self.utilities = []
        for i, _, m in self.modules(UtilityDef):
            u = UtilityState(i, m)
            old = old_utils.get(i)
            if old and old.defn is m:
                u.charges = old.charges
            self.utilities.append(u)
        self.cargo_bonus = sum(m.value for _, _, m in self.modules(UtilityDef) if m.effect == "cargo")

        for attr, cap in (("hp", self.hull.hp), ("armor", self.armor_max), ("shield", self.shield_max),
                          ("capacitor", self.cap_max)):
            if hasattr(self, attr):
                setattr(self, attr, min(getattr(self, attr), cap))

    def set_module(self, slot_index, key):
        self.fit[slot_index] = key
        self.rebuild()

    # --- производные показатели ------------------------------------------

    @property
    def alive(self):
        return self.hp > 0

    @property
    def radius(self):
        return self.hull.radius

    @property
    def speed(self):
        return self.vel.length()

    @property
    def mass(self):
        return self.hull.mass + self.module_mass + self.cargo_mass * CARGO_MASS

    @property
    def cargo_capacity(self):
        return int(self.hull.cargo + self.cargo_bonus)

    @property
    def value(self):
        return self.hull.price + sum(m.price for _, _, m in self.modules())

    def mass_factor(self):
        """<1, если корабль тяжелее «проектной» массы (корпус + 60% его веса в модулях)."""
        design = self.hull.mass * 1.6
        return min(1.1, (design / self.mass) ** 0.5)

    def base_top_speed(self):
        if not self.engine:
            return 0.0
        return self.engine.top_speed * self.hull.speed_mult * self.mass_factor()

    def max_speed(self):
        s = self.base_top_speed() * (1.0 - 0.55 * self.fouling) * (0.35 + 0.65 * self.subsystems["engine"])
        if self.boosting and self.engine:
            s *= self.engine.boost_mult
        return s

    def upkeep(self, density):
        total = 0.0
        for _, _, m in self.modules():
            u = m.upkeep
            if m.electronic:
                u *= 1.0 + VEIL_UPKEEP * density * (1.0 - m.veil_resist)
            total += u
        return total

    def power_balance(self, density):
        return self.output - self.upkeep(density)

    def radar_range(self, density):
        if not self.sensor or self.brownout:
            return 0.0
        penalty = C.RADAR_DENSITY_PENALTY * density * (1.0 - self.sensor.veil_resist)
        return self.sensor.radar * (1.0 - penalty) * (0.25 + 0.75 * self.subsystems["sensors"])

    def mining_mult(self, kind):
        mult = 1.0
        for _, _, m in self.modules(UtilityDef):
            if m.effect == "drill" and kind in ("salt", "filament", "zero"):
                mult = max(mult, m.value)
            if m.effect == "collector" and kind == "condensate":
                mult = max(mult, m.value)
        return mult

    def utility_active(self, effect):
        return any(u.defn.effect == effect and u.active_time > 0 for u in self.utilities)

    # --- шаг симуляции ----------------------------------------------------

    def update(self, dt, throttle, turn, boost, density):
        self.throttle = throttle

        # Энергия
        self.capacitor += self.power_balance(density) * dt
        want_boost = boost and throttle > 0 and self.engine is not None
        self.boosting = False
        if want_boost and self.capacitor > self.engine.boost_drain * dt:
            self.capacitor -= self.engine.boost_drain * dt
            self.boosting = True
        self.capacitor = min(self.cap_max, self.capacitor)
        self.brownout = self.capacitor <= 0 and self.cap_max > 0
        if self.capacitor < 0:
            self.capacitor = 0.0
        if self.brownout:
            self.shield = max(0.0, self.shield - self.shield_max * 0.15 * dt)

        # Движение
        fwd = heading(self.angle)
        speed_k = 0.35 + 0.65 * min(1.0, self.speed / max(1.0, self.base_top_speed()))
        rudder = 0.3 + 0.7 * self.subsystems["rudder"]
        turn_rate = self.hull.turn_rate * min(1.15, self.mass_factor()) * rudder
        self.angle = (self.angle + turn * turn_rate * speed_k * dt) % 360

        if self.engine:
            accel = self.engine.thrust * 100.0 / self.mass
            accel *= (1.0 - 0.4 * self.fouling) * (0.35 + 0.65 * self.subsystems["engine"])
            accel *= 1.6 if self.boosting else 1.0
            if throttle < 0:
                accel *= 0.5
            self.vel += fwd * accel * throttle * dt

        fwd = heading(self.angle)
        along = fwd * self.vel.dot(fwd)
        lateral = self.vel - along
        self.vel = along * math.exp(-0.35 * dt) + lateral * math.exp(-3.0 * dt)
        vmax = self.max_speed()
        if self.vel.length() > vmax and vmax > 0:
            self.vel.scale_to_length(vmax)
        self.pos += self.vel * dt
        self.pos.x = min(max(self.pos.x, 0), C.WORLD_W)
        self.pos.y = min(max(self.pos.y, 0), C.WORLD_H)

        # Налёт филаментов
        fast = self.speed > self.base_top_speed() * C.FOUL_SPEED_FRACTION
        if fast and density > C.FOUL_MIN_DENSITY:
            self.fouling += C.FOUL_RATE * density * (2.0 if self.boosting else 1.0) * dt
        else:
            self.fouling -= C.FOUL_DECAY * (1.0 - density) * dt
        self.fouling = min(1.0, max(0.0, self.fouling))

        # Щиты тратят энергию на восстановление
        if self.shield_cd > 0:
            self.shield_cd -= dt
        elif self.shield_def and self.shield < self.shield_max and not self.brownout:
            amount = min(self.shield_def.regen * dt, self.shield_max - self.shield)
            cost = amount * self.shield_def.regen_cost
            if self.capacitor >= cost:
                self.shield += amount
                self.capacitor -= cost

        for w in self.weapons:
            w.reload = max(0.0, w.reload - dt)
        for u in self.utilities:
            u.cooldown = max(0.0, u.cooldown - dt)
            if u.active_time > 0:
                u.active_time = max(0.0, u.active_time - dt)
                if u.defn.effect == "repair":
                    self.hp = min(self.hull.hp, self.hp + u.defn.value * dt)
                    for k in SUBSYSTEMS:
                        self.subsystems[k] = min(1.0, self.subsystems[k] + 0.06 * dt)

    # --- действия ---------------------------------------------------------

    def activate(self, index):
        """Включить активную утилиту по порядковому номеру. Возвращает UtilityState или None."""
        actives = [u for u in self.utilities if u.defn.active]
        if index >= len(actives):
            return None
        u = actives[index]
        if not u.ready or self.capacitor < u.defn.energy:
            return None
        self.capacitor -= u.defn.energy
        u.cooldown = u.defn.cooldown
        u.active_time = u.defn.duration
        if u.defn.charges:
            u.charges -= 1
        return u

    def reload_mult(self):
        return self.reload_penalty / (0.4 + 0.6 * self.subsystems["weapons"])

    # --- урон -------------------------------------------------------------

    def apply_damage(self, amount, dtype, rng):
        """Щит → броня → корпус. Возвращает имя повреждённой подсистемы или None."""
        self.shield_cd = 3.0
        if dtype != "torpedo" and self.shield > 0:
            mult = 2.0 if dtype == "em" else 1.0
            absorbed = min(self.shield, amount * mult)
            self.shield -= absorbed
            amount -= absorbed / mult
        if amount <= 0:
            return None

        sub_chance = 0.0
        if dtype == "em":
            sub_chance += 0.35
            amount *= 0.35
        if self.armor > 0:
            if dtype == "kinetic":
                amount = max(amount * 0.25, amount - self.armor_def.reduction)
            absorbed = min(self.armor, amount)
            self.armor -= absorbed
            amount -= absorbed
        if amount > 0:
            self.hp -= amount
            sub_chance += min(0.7, amount / self.hull.hp * 4)
        if sub_chance > 0 and rng.random() < sub_chance:
            weights = {"engine": 3, "rudder": 2, "sensors": 3 if dtype == "em" else 2,
                       "weapons": 3 if dtype == "em" else 2}
            if dtype == "torpedo":
                weights["rudder"] = 4
            r = rng.uniform(0, sum(weights.values()))
            for k, wgt in weights.items():
                r -= wgt
                if r <= 0:
                    self.subsystems[k] = max(0.0, self.subsystems[k] - rng.uniform(0.15, 0.35))
                    return k
        return None

    def drain_shield(self, amount):
        if amount > 0:
            self.shield = max(0.0, self.shield - amount)
            self.shield_cd = max(self.shield_cd, 1.0)

    def repair_all(self):
        self.hp = self.hull.hp
        self.armor = self.armor_max
        self.subsystems = {k: 1.0 for k in SUBSYSTEMS}

    def recharge(self):
        self.shield = self.shield_max
        self.capacitor = self.cap_max
        self.brownout = False
