"""Симуляция мира. Не знает про экран и клавиатуру — только Controls на входе."""

import math
import random
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from pygame.math import Vector2

from . import config as C
from .ai import PIRATE_LOADOUTS, Pirate, Ray, Tihodont
from .combat import lead_point, try_fire, update_lock, update_projectile
from .entities import RESOURCES, Loot, ResourceNode, Smoke
from .events import EventDirector
from .hulls import HULLS
from .islands import AGROUND_MIN_SPEED, avoid_turn, collide_ship, generate_islands, island_at
from .modules import AMMO, AMMO_ORDER, MODULES
from .ship import SUBSYSTEM_NAME, SUBSYSTEMS, Ship, fit_problems
from .spatial import ShipCollisionGrid, ship_overlaps
from .veil import Veil
from .trade_traffic import TradeTraffic
from .market import MAX_STOCK, apply_deliveries, new_stocks, unit_price
from .market_events import current_event, demand_multiplier, latest_news
from .reputation import (PARTNER_AT, add_reputation, discount, new_reputation, rank)

MODULE_RESALE = 0.5
HULL_RESALE = 0.5
SUBSYSTEM_REPAIR_COST = 80      # за 100% одной подсистемы
ARMOR_REPAIR_COST = 0.8         # за единицу брони
LOCK_PICK_RADIUS = 260.0        # насколько близко к курсору должна быть цель для захвата
FIRE_CONTROL_RADIUS = 140.0     # цель ближе к курсору — турели сами берут упреждение
AMMO_PACK = 100                 # снарядов в одной покупке
LEAK_REPAIR_COST = 40
# Обучение: первые цели (ключ, текст). Трекер на HUD показывает первую невыполненную.
GOALS = (
    ("mine", "Добыть ресурс", "Остановитесь у светящегося скопления и держите E"),
    ("sell", "Продать груз", "Вернитесь в порт (F) и продайте добычу (P)"),
    ("mist", "Заглянуть во Мглу", "Пелена гуще к северо-востоку. Следите за энергией"),
    ("install", "Поставить новый модуль", "Порт → Оснащение: перетащите модуль в слот"),
    ("sink", "Потопить рейдера", "Ржавый Прилив патрулирует Мглу. ЛКМ — огонь"),
)
MEMORY_CELL = 200               # клетка «памяти» карты, ед.
AMNESIA_RATE = 0.05             # скорость забывания карты в самой плотной Пелене, доля/с


@dataclass
class Controls:
    throttle: float = 0.0     # -1..1
    turn: float = 0.0         # -1..1, + = по часовой на экране
    boost: bool = False
    fire: bool = False        # пушки
    fire2: bool = False       # ракеты и торпеды
    aim: Vector2 | None = None
    mine: bool = False
    activate: list = field(default_factory=list)   # номера активных утилит, нажатые в этом кадре
    pips: list = field(default_factory=list)       # "shields" | "engines" | "weapons" | "reset"
    cycle_ammo: bool = False
    toggle_spotlight: bool = False


@dataclass
class Captain:
    """Всё, что переживает гибель корабля."""
    credits: int = C.START_CREDITS
    debt: int = 0
    trauma: bool = False
    cargo: dict = field(default_factory=dict)
    storage: list = field(default_factory=list)     # модули на складе порта
    ammo_stock: dict = field(default_factory=lambda: {"ap": 0, "he": 0})
    pending_insurance: int = 0
    kills: int = 0


class World:
    def __init__(self, seed=9, first_event=45.0):
        self.seed = seed
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
        self.lock_candidate = None
        self.gun_target = None
        self.ammo_type = "std"
        self.spotlight = False

        self.phantoms = []          # галлюцинации: ложные отметки радара в плотной Пелене
        self.pirates: list[Pirate] = []
        self.tihodonts: list[Tihodont] = []
        self.rays: list[Ray] = []
        self.projectiles = []
        self.smokes: list[Smoke] = []
        self.nodes: list[ResourceNode] = []
        self.loot: list[Loot] = []
        self.log: deque = deque(maxlen=7)
        # События для визуальных эффектов (выстрелы, попадания, взрывы); их забирает отрисовка
        self.fx: deque = deque(maxlen=600)
        self.pirate_spawn_cd = 10.0

        self.islands = generate_islands(random.Random(seed + 77), self.port, self.eye)
        self.platform = next(
            (Vector2(pos) for pos in C.PLATFORM_CANDIDATES
             if not island_at(self.islands, pos, C.PORT_RADIUS + 100)),
            Vector2(C.PLATFORM_CANDIDATES[0]))
        self.active_port = "port"
        self.trade_traffic = TradeTraffic(self.port, self.platform, self.islands)
        self.market_stock = new_stocks()
        self.market_last_time = self.t
        self.guild_reputation = new_reputation()
        self._aground_cd = 0.0
        for _ in range(280):
            self._spawn_node()
        for i in range(4):
            off = Vector2(1, 0).rotate(i * 90 + 45) * 120
            self.nodes.append(ResourceNode(self.eye + off, "zero", 25))
        self._spawn_tihodonts(16)

        # Навигация и память: разведанная карта, отметки, путевая точка, кодекс
        self.memory = np.zeros((C.WORLD_H // MEMORY_CELL, C.WORLD_W // MEMORY_CELL), np.float32)
        self.marks = {
            "port": {"pos": Vector2(self.port), "label": "Порт беженцев", "kind": "port", "clarity": 1.0},
            "platform": {"pos": Vector2(self.platform), "label": "Торговая платформа", "kind": "port", "clarity": 1.0},
        }
        self.waypoint = None
        self.codex = {}             # ключ записи → прочитана ли
        self.goals_done = set()
        self.contracts = {}   # id -> {'status': 'active'|'done', 'start_kills': int}
        self.clock_offset = 0.0     # сдвиг суток (консоль: time)
        self.god = False            # консоль: неуязвимость
        self.last_loss = None       # сводка для экрана гибели
        self._memory_cd = 0.0
        for key in ("port", "veil", "ray", "tihodont"):
            self.codex[key] = False
        for key in self.player.fit:
            if key:
                self.codex[f"module:{key}"] = False
        self._reveal()
        self.say("Порт беженцев. Нейтральные воды. Удачи, капитан.")

    # --- служебное ------------------------------------------------------

    BAD_WORDS = ("Пожар", "Пробоина", "Повреждение", "Ракета!", "потерян", "уничтожена", "ЭМ-вспышка",
                 "Удар о скалы", "разбужен", "кончились")
    GOOD_WORDS = ("потоплен", "Трофей", "Страховка", "подобраны", "выполнена")

    def say(self, text, level=None):
        """Сообщение игроку. level: info | good | bad | event (по умолчанию — по ключевым словам)."""
        if level is None:
            if any(w in text for w in self.BAD_WORDS):
                level = "bad"
            elif any(w in text for w in self.GOOD_WORDS):
                level = "good"
            else:
                level = "info"
        self.log.append((text, self.t, level))

    def emit(self, *event):
        self.fx.append(event)

    def _fire(self, ship, mount, *args, **kwargs):
        """try_fire + событие вспышки для эффектов."""
        shots = try_fire(ship, mount, *args, **kwargs)
        if shots:
            ang = Vector2(1, 0).angle_to(shots[0].vel) if shots[0].vel.length_squared() else ship.angle
            self.emit("muzzle", Vector2(shots[0].pos), ang, mount.defn.size, mount.defn.kind, ship.side)
        return shots

    def density_at(self, pos):
        return self.veil.density(pos, self.t)

    def _random_pos(self, margin=150):
        return Vector2(self.rng.uniform(margin, C.WORLD_W - margin), self.rng.uniform(margin, C.WORLD_H - margin))

    def _spawn_node(self):
        for _ in range(20):
            pos = self._random_pos()
            if pos.distance_to(self.port) < C.PORT_RADIUS + 120 or pos.distance_to(self.eye) < C.EYE_WALL_R:
                continue
            if island_at(self.islands, pos, 60):
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
            if 0.25 < d < 0.7 and pos.distance_to(self.port) > 900 and not island_at(self.islands, pos, 200):
                self.tihodonts.append(Tihodont(pos, self.rng))

    # --- производные показатели игрока ---------------------------------

    @property
    def cargo_capacity(self):
        return self.player.cargo_capacity

    @property
    def cargo_used(self):
        return sum(self.captain.cargo.values())

    def radar_range(self):
        if self.emp_timer > 0:
            return 0.0
        p = self.player
        r = p.radar_range(self.density_at(p.pos))
        r *= self.events.multiplier("radar", p.pos, self.t)
        if self.captain.trauma:
            r *= C.TRAUMA_RADAR_MULT
        return r

    # --- сутки ------------------------------------------------------------

    @property
    def time_of_day(self):
        """0..1: 0 — полночь, 0.25 — рассвет, 0.5 — полдень, 0.75 — закат."""
        return (C.START_TIME_OF_DAY + (self.t + self.clock_offset) / C.DAY_LENGTH) % 1.0

    def sun_elevation(self):
        return math.sin(2 * math.pi * (self.time_of_day - 0.25))

    def daylight(self):
        """0 — ночь, 1 — день; плавные сумерки."""
        e = self.sun_elevation()
        k = min(1.0, max(0.0, (e + 0.15) / 0.4))
        return k * k * (3 - 2 * k)

    def clock(self):
        minutes = int(self.time_of_day * 24 * 60)
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    def visual_range(self):
        night = 1.0 - self.daylight()
        light = 1.0 - (1.0 - C.NIGHT_VISION) * night
        if self.spotlight and night > 0:
            light = max(light, 0.9)
        vision = self.events.multiplier("vision", self.player.pos, self.t)
        return C.VISUAL_RANGE * (1.0 - 0.55 * self.density_at(self.player.pos)) * light * vision

    def sheltering_tihodont(self):
        for tx in self.tihodonts:
            if tx.pos.distance_to(self.player.pos) < Tihodont.RADIUS:
                return tx
        return None

    def in_smoke(self, pos):
        return any(s.pos.distance_to(pos) < s.radius for s in self.smokes)

    def player_loud(self):
        p = self.player
        return p.boosting or p.speed > p.base_top_speed() * 0.55

    def player_signature(self):
        """Насколько игрока легко засечь (множитель к дальности сенсоров NPC)."""
        p = self.player
        if p.utility_active("bioscreen"):
            return 0.0
        sig = 0.6 + 0.4 * min(1.0, p.speed / max(1.0, p.base_top_speed()))
        sig *= 0.8 + 0.4 * min(1.0, p.mass / 250.0)          # крупный корабль заметнее
        if p.boosting:
            sig *= 1.3
        if self.in_capsule:
            sig *= 0.6
        if self.in_smoke(p.pos):
            sig *= 0.3
        night = 1.0 - self.daylight()
        if self.spotlight and not self.in_capsule:
            sig *= 1.0 + (C.SPOTLIGHT_SIGNATURE - 1.0) * night
        else:
            sig *= 1.0 - 0.35 * night            # ночью без огней корабль заметить труднее
        if self.sheltering_tihodont() and not self.player_loud():
            sig *= 0.05
        return sig

    def port_position(self, port_key=None):
        return self.platform if (port_key or self.active_port) == "platform" else self.port

    def dockable_port(self):
        """Dock only near a hub and below the speed limit."""
        if self.player.speed >= C.DOCK_MAX_SPEED:
            return None
        for key in ("port", "platform"):
            if self.player.pos.distance_to(self.port_position(key)) < C.PORT_RADIUS:
                return key
        return None

    def can_dock(self):
        return self.dockable_port() is not None

    def perceives(self, pos):
        """Игрок видит точку глазами или радаром."""
        d = self.player.pos.distance_to(pos)
        return d < self.visual_range() or d < self.radar_range()

    def on_radar(self, pos):
        return self.player.pos.distance_to(pos) < self.radar_range()

    # --- главный шаг -----------------------------------------------------

    def update(self, dt, ctl: Controls):
        self.t += dt
        self.update_market()
        p = self.player
        self.events.update(self.t, p.pos)
        for ev in self.events.started:
            if ev.covers(p.pos) or self.perceives(ev.pos):
                self.say(f"{ev.data.name}!", "event")
                if ev.data.name == "Штиль" and ev.covers(p.pos):
                    self.emit("sky")
            if ev.data.name == "Цветение":
                self._bloom_resources(ev)

        density = self.density_at(p.pos)
        p.cargo_mass = self.cargo_used
        p.reload_penalty = C.TRAUMA_RELOAD_MULT if self.captain.trauma else 1.0
        p.update(dt, ctl.throttle, ctl.turn, ctl.boost, density)
        self._weather(p, dt)
        self._aground_cd = max(0.0, self._aground_cd - dt)
        impact = collide_ship(p, self.islands, self.rng)
        if impact > AGROUND_MIN_SPEED:
            self.emit("aground", Vector2(p.pos), impact)
            if self._aground_cd <= 0:
                self.say("Удар о скалы! Пробоина ниже ватерлинии." if p.leaks else "Удар о скалы!")
                self._aground_cd = 2.0
        self._eye_effects(dt)
        p.drain_shield(self.events.modifier("shield_drain", p.pos, self.t) * dt)

        if not self.in_capsule:
            for sys_ in ctl.pips:
                if sys_ == "reset":
                    p.reset_pips()
                else:
                    p.add_pip(sys_)
            if ctl.cycle_ammo:
                self.cycle_ammo()
            if ctl.toggle_spotlight:
                self.spotlight = not self.spotlight
                self.say("Прожектор включён — вас видно издалека." if self.spotlight else "Прожектор выключен.")
            self._player_weapons(dt, ctl, density)
            for idx in ctl.activate:
                self._activate_utility(idx)
            if ctl.mine:
                self._mine(dt)

        self._update_phantoms(dt, density)
        self._update_pirates(dt)
        self._update_fauna(dt)
        self._update_projectiles(dt)
        self._update_loot(dt)
        for s in self.smokes:
            s.life -= dt
        self.smokes = [s for s in self.smokes if s.life > 0]

        self._update_memory(dt, density)
        self._update_escort_contract(dt)
        if self.god:
            p.hp = p.hull.hp
            p.fires = p.leaks = 0
            p.water = 0.0
        if not p.alive:
            self._on_player_destroyed()

    # --- память, карта и кодекс ----------------------------------------------

    @property
    def goal(self):
        """Текущая цель обучения: (номер, название, подсказка) или None, если всё выполнено."""
        for i, (key, title, hint) in enumerate(GOALS):
            if key not in self.goals_done:
                return i, title, hint
        return None

    def complete(self, key):
        if key in self.goals_done:
            return
        self.goals_done.add(key)
        title = next(t for k, t, _ in GOALS if k == key)
        self.say(f"Цель выполнена: {title}", "good")

    def discover(self, key):
        """Открывает запись кодекса. Возвращает True, если она новая."""
        if key in self.codex:
            return False
        self.codex[key] = False
        from .codex import entry
        e = entry(key)
        if e:
            self.say(f"Кодекс: {e[1]}", "event")
        return True

    def mark(self, key, pos, label, kind):
        m = self.marks.get(key)
        if m is None:
            self.marks[key] = {"pos": Vector2(pos), "label": label, "kind": kind, "clarity": 1.0}
        else:
            m["clarity"] = 1.0

    def _reveal(self):
        """Открывает на карте клетки в пределах видимости."""
        p = self.player
        r = max(self.visual_range(), 300.0)
        h, w = self.memory.shape
        cx, cy = p.pos.x / MEMORY_CELL, p.pos.y / MEMORY_CELL
        rc = r / MEMORY_CELL
        x0, x1 = max(0, int(cx - rc)), min(w, int(cx + rc) + 1)
        y0, y1 = max(0, int(cy - rc)), min(h, int(cy + rc) + 1)
        if x0 >= x1 or y0 >= y1:
            return
        ys, xs = np.mgrid[y0:y1, x0:x1]
        near = (xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2 <= rc * rc
        self.memory[y0:y1, x0:x1][near] = 1.0

    def _update_memory(self, dt, density):
        self._memory_cd -= dt
        if self._memory_cd > 0:
            return
        step = 0.25 - self._memory_cd
        self._memory_cd = 0.25
        p = self.player
        # амнезия: в плотной Пелене разведанное выцветает — и карта, и отметки
        if density > C.ZONE_DENSE:
            k = math.exp(-AMNESIA_RATE * step * (density - C.ZONE_DENSE) / (1 - C.ZONE_DENSE))
            self.memory *= k
            for m in self.marks.values():
                if m["kind"] != "port":
                    m["clarity"] = max(0.15, m["clarity"] * k)
            if density > 0.75:
                self.discover("amnesia")
        self._reveal()
        mission = self.contracts.get("scout")
        if (mission and mission["status"] == "active" and not mission["explored"]
                and not self.in_capsule
                and p.pos.distance_to(self.scout_position()) <= self.SCOUT_RADIUS):
            mission["explored"] = True
            self.say("Район разведан! Вернитесь в порт за наградой.", "good")
        if self.waypoint is not None and p.pos.distance_to(self.waypoint) < 120:
            self.waypoint = None
            self.say("Путевая точка достигнута.")
        # открытия для кодекса и отметок
        vis = self.visual_range()
        if density >= C.ZONE_MIST:
            self.discover("zone:mist")
            self.complete("mist")
        if density >= C.ZONE_DENSE:
            self.discover("zone:dense")
        if p.fouling > 0.05:
            self.discover("fouling")
        if self.phantoms:
            self.discover("phantoms")
        if p.pos.distance_to(self.eye) < C.EYE_WALL_R + vis:
            self.discover("eye")
            self.mark("eye", self.eye, "Око Девятки", "eye")
        for i, isl in enumerate(self.islands):
            if isl.ruins and p.pos.distance_to(isl.pos) < vis + isl.radius:
                self.discover("ruins")
                self.mark(f"ruins{i}", isl.pos, "Руины Эры I", "ruins")
        for pi in self.pirates:
            if self.perceives(pi.ship.pos) or self.on_radar(pi.ship.pos):
                self.discover(f"enemy:{pi.loadout}")
        for ev in self.events.active:
            if ev.phase(self.t) == "active" and (ev.covers(p.pos) or self.perceives(ev.pos)):
                self.discover(f"event:{ev.data.name}")
        for kind in self.captain.cargo:
            self.discover(f"res:{kind}")

    def _eye_effects(self, dt):
        p = self.player
        dist = p.pos.distance_to(self.eye)
        self.emp_timer = max(0.0, self.emp_timer - dt)
        if C.EYE_CALM_R < dist < C.EYE_BELT_R:
            # Гравитационная аномалия: течения тянут к центру, лёгких — сильнее
            pull = 40.0 * (1.0 - dist / C.EYE_BELT_R) * (140.0 / p.mass) ** 0.5
            p.vel += (self.eye - p.pos).normalize() * pull * dt
        if self.veil.in_wall(p.pos):
            p.apply_damage(6.0 * dt, "kinetic", self.rng)          # стихийный урон
            if self.emp_timer <= 0 and self.rng.random() < 0.08 * dt:
                self.emp_timer = 6.0
                p.shield = 0.0
                p.capacitor *= 0.3
                self.say("ЭМ-вспышка! Электроника отключена.")
                self.emit("lightning", Vector2(p.pos))

    # --- оружие игрока ----------------------------------------------------

    def _nearest_to_cursor(self, aim, radius, need_radar):
        if aim is None:
            return None
        best, best_d = None, radius
        for pr in self.pirates:
            pos = pr.ship.pos
            visible = self.on_radar(pos) if need_radar else self.perceives(pos)
            if not visible:
                continue
            d = pos.distance_to(aim)
            if d < best_d:
                best, best_d = pr.ship, d
        return best

    def _player_weapons(self, dt, ctl, density):
        p = self.player
        aim = ctl.aim if ctl.aim is not None else p.pos + Vector2(1, 0).rotate(p.angle) * 300
        acc = self.events.modifier("accuracy", p.pos, self.t)
        # Ракетам нужна цель на радаре; пушечной СУО хватает и глаз
        self.lock_candidate = self._nearest_to_cursor(aim, LOCK_PICK_RADIUS, need_radar=True)
        self.gun_target = self._nearest_to_cursor(aim, FIRE_CONTROL_RADIUS, need_radar=False)
        # Пелена сбивает расчёт упреждения
        noise = Vector2(self.rng.gauss(0, 1), self.rng.gauss(0, 1)) * 60 * density if self.gun_target else None
        for m in p.weapons:
            kind = m.defn.kind
            held = {1: ctl.fire, 2: ctl.fire2}.get(m.group, False)
            if kind == "gun":
                point = lead_point(m.world_pos(p), self.gun_target, m.defn.speed, noise) if self.gun_target else aim
                aimed = m.aim(p, point, dt)
                if held and aimed:
                    shots = self._fire(p, m, self.rng, density, point, acc, ammo=self.ammo_type)
                    self._spend_ammo(shots)
                    self.projectiles += shots
            elif kind == "missile":
                tgt = self.lock_candidate if held else None
                visible = tgt is not None and tgt.pos.distance_to(p.pos) < m.defn.range
                update_lock(m, p, tgt, visible, density, dt)
                if held:
                    shots = self._fire(p, m, self.rng, density)
                    if shots:
                        m.lock = 0.0
                    self.projectiles += shots
            elif kind == "torpedo" and held:
                self.projectiles += self._fire(p, m, self.rng, density)

    def cycle_ammo(self):
        """Следующий тип снарядов, на который есть запас."""
        i = AMMO_ORDER.index(self.ammo_type)
        for step in range(1, len(AMMO_ORDER) + 1):
            key = AMMO_ORDER[(i + step) % len(AMMO_ORDER)]
            if key == "std" or self.captain.ammo_stock.get(key, 0) > 0:
                self.ammo_type = key
                break
        self.say(f"Снаряды: {AMMO[self.ammo_type].name}")

    def _spend_ammo(self, shots):
        if self.ammo_type == "std" or not shots:
            return
        stock = self.captain.ammo_stock
        used = sum(1 for sh in shots if sh.ammo == self.ammo_type)
        stock[self.ammo_type] = max(0, stock[self.ammo_type] - used)
        if stock[self.ammo_type] == 0:
            self.say(f"{AMMO[self.ammo_type].name} снаряды кончились — стандартные.")
            self.ammo_type = "std"

    def _activate_utility(self, idx):
        p = self.player
        u = p.activate(idx)
        if u is None:
            return
        eff = u.defn.effect
        self.say(f"{u.defn.name}: включено")
        if eff == "smoke":
            self.smokes.append(Smoke(Vector2(p.pos), u.defn.value, u.defn.duration))
        elif eff == "ecm":
            self.emit("ecm", Vector2(p.pos), u.defn.value)
            for pr in self.projectiles:
                if pr.kind == "missile" and pr.target is p and pr.pos.distance_to(p.pos) < u.defn.value:
                    pr.lost = True
            for pi in self.pirates:
                if pi.ship.pos.distance_to(p.pos) < u.defn.value:
                    for m in pi.ship.weapons:
                        m.lock = 0.0

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
        rate = 6.0 * p.mining_mult(node.kind)
        take = min(rate * dt, node.amount, space)
        node.amount -= take
        self.captain.cargo[node.kind] = self.captain.cargo.get(node.kind, 0) + take
        if self.captain.cargo[node.kind] >= 1:
            self.complete("mine")
        if node.amount <= 0.01:
            self.nodes.remove(node)
            if node.kind != "zero":
                self._spawn_node()
            self.say(f"Точка выработана: {RESOURCES[node.kind].name}")

    # --- NPC ----------------------------------------------------------------

    def _pick_loadout(self, density):
        options = [k for k, (_, _, dmin) in PIRATE_LOADOUTS.items() if density >= dmin]
        weights = [1.0 + 2.0 * PIRATE_LOADOUTS[k][2] for k in options]
        return self.rng.choices(options, weights)[0]

    def _update_pirates(self, dt):
        p = self.player
        self.pirate_spawn_cd -= dt
        density = self.density_at(p.pos)
        wanted = 0 if p.pos.distance_to(self.port) < 1500 else 1 + int(4 * density)
        self.pirates = [pr for pr in self.pirates if pr.ship.pos.distance_to(p.pos) < 2600]
        if len(self.pirates) < wanted and self.pirate_spawn_cd <= 0:
            pos = p.pos + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(1100, 1500)
            if pos.distance_to(self.port) > 1400 and not island_at(self.islands, pos, 80):
                pos.x = min(max(pos.x, 50), C.WORLD_W - 50)
                pos.y = min(max(pos.y, 50), C.WORLD_H - 50)
                self.pirates.append(Pirate(pos, self.rng, self._pick_loadout(self.density_at(pos))))
            self.pirate_spawn_cd = 12.0

        sig = self.player_signature()
        for pr in self.pirates:
            s = pr.ship
            d = self.density_at(s.pos)
            # Простая тактика энергии: под огнём — в щиты, при погоне — в двигатель
            if pr.state == "attack":
                if s.shield_max and s.shield < s.shield_max * 0.3:
                    s.set_pips(4, 1, 1)
                else:
                    s.set_pips(1, 2, 3)
            elif pr.state in ("chase", "flee"):
                s.set_pips(1, 4, 1)
            else:
                s.set_pips(2, 2, 2)
            if island_at(self.islands, pr.waypoint, 80):
                pr.waypoint = pr._new_waypoint()
            throttle, turn, sees = pr.think(p.pos, sig, d, dt)
            dodge = avoid_turn(s, self.islands)
            if dodge:
                turn, throttle = dodge, max(throttle, 0.6)
            s.update(dt, throttle, turn, False, d)
            self._weather(s, dt)
            if collide_ship(s, self.islands, self.rng) > AGROUND_MIN_SPEED:
                self.emit("aground", Vector2(s.pos), 60)
            dist = s.pos.distance_to(p.pos)
            engaged = pr.state == "attack" and sees
            smoke = self.in_smoke(p.pos)
            for m in s.weapons:
                if m.defn.kind == "gun":
                    lead = lead_point(m.world_pos(s), p, m.defn.speed)
                    aimed = m.aim(s, lead, dt)
                    if engaged and aimed and dist < m.defn.range * 0.95:
                        self.projectiles += self._fire(s, m, self.rng, d, lead, 0.0, smoke)
                elif m.defn.kind == "missile":
                    update_lock(m, s, p if engaged else None, dist < m.defn.range, d, dt)
                    shots = self._fire(s, m, self.rng, d)
                    if shots:
                        m.lock = 0.0
                        self.say("Ракета! Захват на вас.")
                    self.projectiles += shots

    def _weather(self, ship, dt):
        """Снос ветром и течением; удары волн в шторм."""
        flow = self.events.flow(ship.pos, self.t)
        if flow.length_squared() > 0:
            ship.pos += flow * dt
        waves = self.events.modifier("wave_damage", ship.pos, self.t)
        if waves > 0 and self.rng.random() < 0.35 * dt:
            ship.apply_damage(waves, "kinetic", self.rng)
            if ship is self.player:
                self.emit("wave", Vector2(ship.pos))

    def _bloom_resources(self, ev):
        """Цветение выносит на поверхность редкие ресурсы."""
        for _ in range(6):
            pos = ev.pos + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(0, ev.data.radius * 0.8)
            if not island_at(self.islands, pos, 60):
                self.nodes.append(ResourceNode(pos, self.rng.choice(("filament", "condensate")), self.rng.uniform(20, 40)))

    def _update_phantoms(self, dt, density):
        """В плотной Пелене филаменты резонируют с мозгом: на радаре появляются несуществующие цели."""
        p = self.player
        radar, vis = self.radar_range(), self.visual_range()
        keep = []
        for ph in self.phantoms:
            ph["life"] -= dt
            ph["pos"] += ph["vel"] * dt
            d = ph["pos"].distance_to(p.pos)
            if ph["life"] > 0 and vis < d < max(radar, vis + 1):
                keep.append(ph)
        self.phantoms = keep
        if density > 0.6 and radar > vis and self.rng.random() < (density - 0.6) * 1.2 * dt:
            ang = self.rng.uniform(0, 360)
            pos = p.pos + Vector2(1, 0).rotate(ang) * self.rng.uniform(vis + 40, radar)
            vel = Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(40, 140)
            self.phantoms.append({"pos": pos, "vel": vel, "life": self.rng.uniform(3, 8)})

    def _update_fauna(self, dt):
        p = self.player
        loud = self.player_loud()
        for tx in self.tihodonts:
            was = tx.angry
            if tx.update(dt, p.pos, loud) and tx.pos.distance_to(p.pos) < 1400:
                self.emit("spout", tx.blowhole, tx.angry)
            if tx.angry and not was and tx.pos.distance_to(p.pos) < 400:
                self.say("Тиходонт разбужен шумом двигателя!")
            if tx.angry and tx.pos.distance_to(p.pos) < Tihodont.RADIUS * 0.7:
                p.apply_damage(30.0 * dt, "torpedo", self.rng)       # таран сквозь щиты

        self.rays = [r for r in self.rays if r.pos.distance_to(p.pos) < 1500]
        while len(self.rays) < 18:                   # стая 3–6 скатов с общим курсом
            center = p.pos + Vector2(1, 0).rotate(self.rng.uniform(0, 360)) * self.rng.uniform(250, 1000)
            self._school_id = getattr(self, "_school_id", 0) + 1
            heading_ = self.rng.uniform(0, 360)
            for _ in range(self.rng.randint(3, 6)):
                off = Vector2(self.rng.uniform(-50, 50), self.rng.uniform(-50, 50))
                self.rays.append(Ray(center + off, self.rng, self._school_id, heading_ + self.rng.uniform(-15, 15)))
        schools = {}
        for r in self.rays:
            schools.setdefault(r.school, []).append(r)
        for group in schools.values():
            if len(group) > 1:
                c = sum((r.pos for r in group), Vector2()) / len(group)
                mean = sum((Vector2(1, 0).rotate(r.angle) for r in group), Vector2())
                for r in group:
                    goal = mean + (c - r.pos) * 0.02            # выравнивание + сплочённость
                    for o in group:                              # не налезать друг на друга
                        d = r.pos - o.pos
                        if o is not r and 0 < d.length() < 22:
                            goal += d.normalize() * 1.5
                    if goal.length_squared() > 1e-6:
                        r.steer(Vector2(1, 0).angle_to(goal), 50, dt)
        for r in self.rays:
            r.update(dt, self.events.warning_at(r.pos, self.t))

    def _update_projectiles(self, dt):
        p = self.player
        keep = []
        # Broad phase is shared by all player projectiles this frame.
        # NPC positions are already updated; dead ships remain indexed but
        # are ignored by the exact live check, preserving hit order.
        target_grid = ShipCollisionGrid(x.ship for x in self.pirates) if self.projectiles else None
        for pr in self.projectiles:
            update_projectile(pr, dt, self.density_at(pr.pos), self.rng)
            if island_at(self.islands, pr.pos):                 # снаряд разбился о скалы
                if pr.kind == "missile":
                    self.emit("explosion", Vector2(pr.pos), 1)
                else:
                    self.emit("rock", Vector2(pr.pos))
                continue
            padding = 4 if pr.kind != "shell" else 0
            if pr.side == "player":
                hit = target_grid.first_hit(pr.pos, padding)
            else:
                hit = p if ship_overlaps(p, pr.pos, padding) else None
            if hit is not None:
                fires, leaks = hit.fires, hit.leaks
                armor, hp, shield = hit.armor, hit.hp, hit.shield
                sub = hit.apply_damage(pr.damage, pr.dtype, self.rng, pr.ammo)
                layer = "hull" if hit.hp < hp else "armor" if hit.armor < armor else "shield"
                dealt = (shield - hit.shield) + (armor - hit.armor) + (hp - hit.hp)
                self.emit("hit", Vector2(pr.pos), layer, pr.dtype, pr.kind, hit, dealt, Vector2(pr.owner.pos))
                if pr.kind != "shell":
                    self.emit("explosion", Vector2(pr.pos), 2 if pr.kind == "torpedo" else 1)
                if hit is p:
                    if sub:
                        self.say(f"Повреждение: {SUBSYSTEM_NAME[sub]}")
                    if hit.fires > fires:
                        self.say("Пожар на борту!")
                    if hit.leaks > leaks:
                        self.say("Пробоина! Корабль набирает воду.")
                continue
            if pr.life > 0:
                keep.append(pr)
            elif pr.kind == "missile":
                self.emit("explosion", Vector2(pr.pos), 1)      # самоликвидация
            else:
                self.emit("splash", Vector2(pr.pos), pr.kind)
        self.projectiles = keep

        for pi in [pi for pi in self.pirates if not pi.ship.alive]:
            self.pirates.remove(pi)
            self.captain.kills += 1
            self.complete("sink")
            self.emit("explosion", Vector2(pi.ship.pos), 3)
            self.emit("wreck", pi.ship, "pirate")
            kind = self.rng.choice(["salt", "condensate", "condensate", "filament"])
            loot = Loot(Vector2(pi.ship.pos), {kind: self.rng.randint(3, 8)}, self.rng.randint(40, 90))
            mods = [k for k in pi.ship.fit if k]
            if mods and self.rng.random() < 0.35:
                loot.modules.append(self.rng.choice(mods))
            self.loot.append(loot)
            self.say("Рейдер Прилива потоплен. Обломки на воде.")

    def _update_loot(self, dt):
        p, cap = self.player, self.captain
        keep = []
        for lt in self.loot:
            lt.life -= dt
            if not self.in_capsule and lt.pos.distance_to(p.pos) < 45:
                if lt.credits:
                    self.emit("coin")
                cap.credits += lt.credits
                lt.credits = 0
                for key in lt.modules:
                    cap.storage.append(key)
                    self.discover(f"module:{key}")
                    self.say(f"Трофей: {MODULES[key].name} (на склад порта)")
                lt.modules = []
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
        self.emit("explosion", pos, 3 if not self.in_capsule else 1)
        if not self.in_capsule:
            self.emit("wreck", self.player, "player")
        if self.in_capsule:
            self.last_loss = {"kind": "capsule", "debt": C.CAPSULE_DEBT, "t": self.t,
                              "cargo": sum(RESOURCES[k].price * v for k, v in cap.cargo.items())}
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
        self.last_loss = {"kind": "ship", "hull": self.player.hull.name, "t": self.t,
                          "cargo": int(sum(RESOURCES[k].price * v for k, v in cap.cargo.items())),
                          "salvage": int(sum(RESOURCES[k].price * v for k, v in salvage.items())),
                          "insurance": int(self.player.value * C.INSURANCE_RATE), "kills": cap.kills}
        cap.cargo = {}
        if salvage:
            self.mark("wreck", pos, "Обломки корабля", "wreck")
            self.discover("wreck")
        cap.pending_insurance = int(self.player.value * C.INSURANCE_RATE)
        self.player = Ship("capsule", pos, self.player.angle)
        self.in_capsule = True
        self.say("Корабль потерян! Капсула отстрелена — доберитесь до порта.")

    # --- контракты: первый игровой срез (порт) ----------------------------

    CONTRACTS = {
        "salt": ("Поставка соль-металла", 10, 250),
        "pirates": ("Охота на рейдеров", 2, 350),
        "scout": ("Разведка Пелены", 1, 300),
        "escort": ("Сопровождение конвоя", 1, 450),
        "urgent": ("Срочная поставка", 10, 300),
        "guild": ("Гильдейский заказ", 12, 600),
    }
    SCOUT_POS = (4000.0, 3600.0)
    SCOUT_RADIUS = 320.0
    SCOUT_ZONES = ((4000.0, 3600.0), (3500.0, 3200.0),
                   (4500.0, 4200.0), (3100.0, 4800.0))

    URGENT_THRESHOLD = 60
    URGENT_QUANTITY = 10
    GUILD_ORDER_QUANTITY = 12

    def guild_rank(self, port_key=None):
        return rank(self.guild_reputation[port_key or self.active_port])

    def service_discount(self, port_key=None):
        return discount(self.guild_reputation[port_key or self.active_port])

    def guild_order_available(self):
        return self.guild_reputation[self.active_port] >= PARTNER_AT

    def urgent_offer(self):
        """Pick a shortage in the *other* port; don't fabricate demand.

        Select only commodities stocked at the origin. Ordering is stable for
        identical inventories, so reopening the board doesn't reroll offers.
        """
        origin = self.active_port
        destination = "platform" if origin == "port" else "port"
        options = []
        for kind in ("salt", "filament"):
            missing = self.URGENT_THRESHOLD - self.market_available(kind, destination)
            if (missing > 0 and self.market_available(kind, origin) >= self.URGENT_QUANTITY):
                options.append((missing, kind))
        if not options:
            return None
        shortage, kind = max(options, key=lambda item: (item[0], item[1]))
        return {
            "origin": origin, "destination": destination, "kind": kind,
            "amount": self.URGENT_QUANTITY,
            "reward": 300 + 4 * shortage,
        }

    def contract_terms(self, key):
        """Deterministic offer for a cycle; no extra RNG state to save."""
        name, target, reward = self.CONTRACTS[key]
        if key == "urgent":
            offer = self.contracts.get(key) or self.urgent_offer()
            if offer is not None:
                return name, offer["amount"], offer["reward"]
            return name, target, reward
        if key == "guild":
            order = self.contracts.get(key)
            if order is not None:
                return name, order["amount"], order["reward"]
            return name, target, reward
        state = self.contracts.get(key) or {}
        cycle = state.get("cycle", 0)
        if cycle > 0:
            rng = random.Random(f"{self.seed}:{key}:{cycle}")
            if key == "salt":
                target = rng.choice((8, 10, 12, 15, 18))
                reward = 80 + target * 17
            elif key == "pirates":
                target = rng.randint(1, 3)
                reward = 170 * target
            elif key == "scout":
                reward = rng.choice((280, 320, 375, 420))
            elif key == "escort":
                reward = rng.choice((420, 480, 540, 600))
        return name, target, reward

    def scout_position(self):
        """Each reconnaissance contract cycle explores another sea region."""
        state = self.contracts.get("scout") or {}
        cycle = state.get("cycle", 0)
        if cycle <= 0:
            return Vector2(self.SCOUT_POS)
        rng = random.Random(f"{self.seed}:scout-position:{cycle}")
        return Vector2(self.SCOUT_ZONES[1 + rng.randrange(len(self.SCOUT_ZONES) - 1)])

    ESCORT_RADIUS = 240.0
    ESCORT_REQUIRED_SECONDS = 15.0
    ESCORT_ARRIVAL_RADIUS = 450.0

    def _new_escort_state(self, cycle):
        """Choose the convoy and the port it must depart from."""
        return {
            "status": "active", "start_kills": self.captain.kills,
            "cycle": cycle, "origin": self.active_port,
            "convoy": cycle % 2, "leg": -1,
            "close_seconds": 0.0, "arrived": False,
        }

    def _update_escort_contract(self, dt):
        state = self.contracts.get("escort")
        if not state or state["status"] != "active" or state["arrived"]:
            return
        if self.in_capsule or dt <= 0:
            return
        index = state["convoy"]
        # TradeTraffic reports the current scheduled leg (or docked stop).
        leg, direction, moving = self.trade_traffic.leg(index, self.t)
        expected = 1 if state["origin"] == "port" else -1
        merchant = self.trade_traffic.snapshot(self.t)[index]
        if moving and direction == expected:
            if state["leg"] != leg:
                state["leg"] = leg
                state["close_seconds"] = 0.0
            if self.player.pos.distance_to(merchant.pos) <= self.ESCORT_RADIUS:
                state["close_seconds"] += dt
        elif (not moving and state["leg"] >= 0
              and leg == state["leg"] and direction == expected
              and state["close_seconds"] >= self.ESCORT_REQUIRED_SECONDS):
            destination = self.platform if expected == 1 else self.port
            if self.player.pos.distance_to(destination) <= self.ESCORT_ARRIVAL_RADIUS:
                state["arrived"] = True
                self.say("Конвой прибыл! Контракт можно сдать в порту.", "good")

    def renew_contract(self, key):
        """Explicitly start a new job after the previous reward was claimed."""
        state = self.contracts.get(key)
        if key not in self.CONTRACTS or state is None or state["status"] != "done":
            return False
        cycle = state.get("cycle", 0) + 1
        if key == "guild":
            if not self.guild_order_available():
                return False
            self.contracts[key] = {
                "status": "active", "start_kills": self.captain.kills,
                "cycle": cycle, "hub": self.active_port,
                "amount": self.GUILD_ORDER_QUANTITY, "reward": 600,
            }
            self.say("Новый гильдейский заказ принят.")
            return True
        if key == "urgent":
            offer = self.urgent_offer()
            if offer is None:
                return False
            self.contracts[key] = {
                "status": "active", "start_kills": self.captain.kills,
                "cycle": cycle, **offer,
            }
            self.say(f"Новый срочный заказ: {offer['kind']} → {offer['destination']}")
            return True
        self.contracts[key] = {
            "status": "active", "start_kills": self.captain.kills, "cycle": cycle
        }
        if key == "scout":
            self.contracts[key]["explored"] = False
        elif key == "escort":
            self.contracts[key] = self._new_escort_state(cycle)
        self.say(f"Новый контракт: {self.CONTRACTS[key][0]} (заказ №{cycle + 1})")
        return True

    def contract_label(self, key):
        name, amount, reward = self.contract_terms(key)
        state = self.contracts.get(key)
        if key == "guild":
            if state is None:
                if not self.guild_order_available():
                    return f"Гильдейский заказ — доступен при репутации {PARTNER_AT}"
                return f"Гильдейский заказ: соль-металл ×{amount}, награда {reward} КК"
            if state["status"] == "done":
                return "Гильдейский заказ выполнен — получить новый"
            progress = min(amount, int(self.captain.cargo.get("salt", 0)))
            return (f"Гильдейский заказ ({state['hub']}): соль-металл "
                    f"{progress}/{amount}, {reward} КК")
        if key == "urgent":
            if state is None:
                offer = self.urgent_offer()
                if offer is None:
                    return "Срочная поставка — дефицитных заказов сейчас нет"
                return (f"Срочная поставка: {offer['kind']} ×{amount} → "
                        f"{offer['destination']}, награда {reward} КК")
            if state["status"] == "done":
                return "Срочная поставка выполнена — проверить новый заказ"
            have = int(self.captain.cargo.get(state["kind"], 0))
            return (f"Срочная поставка: {state['kind']} {min(have, amount)}/{amount}"
                    f" → {state['destination']} ({reward} КК)")
        if state is None:
            return f"Контракт: {name} ({amount}) — принять, награда {reward} КК"
        if state["status"] == "done":
            return f"Контракт: {name} — выполнен. Взять новый заказ"
        if key == "salt":
            progress = min(amount, int(self.captain.cargo.get("salt", 0)))
        elif key == "scout":
            progress = int(state["explored"])
        elif key == "escort":
            progress = int(state["arrived"])
            if not progress:
                seconds = min(self.ESCORT_REQUIRED_SECONDS, state["close_seconds"])
                return (f"Контракт: {name} — {seconds:.0f}/{self.ESCORT_REQUIRED_SECONDS:.0f} с "
                        f"рядом с конвоем №{state['convoy'] + 1}")
        else:
            progress = min(amount, max(0, self.captain.kills - state["start_kills"]))
        return f"Контракт: {name} {progress}/{amount} — сдать в порту"

    def contract_action(self, key):
        """Accept or turn in a contract. A reward can be claimed only once."""
        if key not in self.CONTRACTS:
            return False
        state = self.contracts.get(key)
        if state is None:
            if key == "guild":
                if not self.guild_order_available():
                    return False
                self.contracts[key] = {
                    "status": "active", "start_kills": self.captain.kills,
                    "cycle": 0, "hub": self.active_port,
                    "amount": self.GUILD_ORDER_QUANTITY, "reward": 600,
                }
                self.say("Принят гильдейский заказ.")
                return True
            if key == "urgent":
                offer = self.urgent_offer()
                if offer is None:
                    return False
                self.contracts[key] = {
                    "status": "active", "start_kills": self.captain.kills,
                    "cycle": 0, **offer,
                }
                self.say("Принят срочный заказ. Доставьте товар в другой порт.")
                return True
            self.contracts[key] = {"status": "active", "start_kills": self.captain.kills}
            if key == "scout":
                self.contracts[key]["explored"] = False
            elif key == "escort":
                self.contracts[key] = self._new_escort_state(0)
            self.say(f"Принят контракт: {self.CONTRACTS[key][0]}")
            return True
        if state["status"] != "active":
            return False
        _, amount, reward = self.contract_terms(key)
        if key == "salt":
            if self.captain.cargo.get("salt", 0) + 1e-6 < amount:
                return False
            self.captain.cargo["salt"] -= amount
            if self.captain.cargo["salt"] <= 1e-6:
                del self.captain.cargo["salt"]
        elif key == "scout":
            if not state["explored"]:
                return False
        elif key == "escort":
            if not state["arrived"]:
                return False
        elif key == "guild":
            if (self.active_port != state["hub"]
                    or self.captain.cargo.get("salt", 0) + 1e-6 < amount):
                return False
            self.captain.cargo["salt"] -= amount
            if self.captain.cargo["salt"] <= 1e-6:
                del self.captain.cargo["salt"]
            self.market_stock[self.active_port]["salt"] = min(
                MAX_STOCK, self.market_available("salt") + amount)
        elif key == "urgent":
            kind = state["kind"]
            if (self.active_port != state["destination"]
                    or self.captain.cargo.get(kind, 0) + 1e-6 < amount):
                return False
            self.captain.cargo[kind] -= amount
            if self.captain.cargo[kind] <= 1e-6:
                del self.captain.cargo[kind]
            self.market_stock[state["destination"]][kind] = min(
                MAX_STOCK, self.market_stock[state["destination"]][kind] + amount)
        elif self.captain.kills - state["start_kills"] < amount:
            return False
        state["status"] = "done"
        self.captain.credits += reward
        gained = add_reputation(self.guild_reputation, self.active_port, key)
        self.say(f"Контракт выполнен: +{reward} КК, доверие +{gained}", "good")
        return True

    # --- порт: сервис -----------------------------------------------------

    def dock(self):
        """Enter the nearby hub."""
        # The input layer checks can_dock(); direct World.dock() calls also
        # support existing scripted rescue/test flows away from the port.
        self.active_port = self.dockable_port() or "port"
        cap = self.captain
        if self.in_capsule:
            self.in_capsule = False
            self.player = Ship("scout", self.port_position(), -90)
            if cap.pending_insurance:
                cap.credits += cap.pending_insurance
                self.say(f"Страховка выплачена: {cap.pending_insurance} КК. Выдан Скаут.")
                cap.pending_insurance = 0
            else:
                self.say("Порт выдал вам списанный Скаут.")
        self.player.vel = Vector2()
        self.player.recharge()
        return True

    def undock_problems(self):
        p = self.player
        problems = fit_problems(p.hull, p.fit)
        if p.engine is None:
            problems.append("Нет двигателя")
        if p.reactor is None:
            problems.append("Нет реактора")
        if self.cargo_used > p.cargo_capacity + 1e-6:
            problems.append("Груз не помещается в трюм")
        return problems

    def undock(self):
        self.player.pos = self.port_position() + Vector2(0, -C.PORT_RADIUS - 40)
        self.player.angle = -90

    def update_market(self):
        """Count convoy arrivals once since the last market tick."""
        if self.t < self.market_last_time:
            # Console time travel cannot generate duplicate historic deliveries.
            self.market_last_time = self.t
            return
        arrivals = apply_deliveries(self.market_stock, self.trade_traffic,
                                    self.market_last_time, self.t, seed=self.seed)
        self.market_last_time = self.t
        if arrivals["port"] or arrivals["platform"]:
            self.say("Торговые конвои пополнили складские запасы.")

    def market_event(self):
        return current_event(self.seed, self.t)

    def market_bulletin(self):
        return latest_news(self.seed, self.t)

    def market_price(self, kind, buying=False, port_key=None):
        """Demand surges affect both bid and ask; local buying still costs more."""
        hub = port_key or self.active_port
        price = unit_price(hub, kind, self.market_stock)
        price = max(1, round(price * demand_multiplier(self.seed, self.t, hub, kind)))
        return max(price + 1, math.ceil(price * C.MARKET_BUY_MARKUP)) if buying else price

    def market_available(self, kind, port_key=None):
        if kind not in RESOURCES:
            return 0
        return self.market_stock[port_key or self.active_port][kind]

    def buy_resource(self, kind, quantity=C.MARKET_PACK_SIZE):
        """Purchase market cargo without exceeding credit or hold limits."""
        if (kind not in RESOURCES or type(quantity) is not int
                or not 1 <= quantity <= C.MARKET_PACK_SIZE
                or self.market_available(kind) < quantity):
            return False
        cost = self.market_price(kind, buying=True) * quantity
        if self.captain.debt or self.captain.credits < cost:
            return False
        if self.cargo_used + quantity > self.cargo_capacity:
            return False
        self.captain.credits -= cost
        self.captain.cargo[kind] = self.captain.cargo.get(kind, 0) + quantity
        self.market_stock[self.active_port][kind] -= quantity
        return True

    def sell_resource(self, kind, quantity=C.MARKET_PACK_SIZE):
        """Sell up to one pack, preserving the rest of the hold."""
        if kind not in RESOURCES or type(quantity) is not int or quantity <= 0:
            return False
        have = self.captain.cargo.get(kind, 0)
        if have <= 0:
            return False
        take = min(have, quantity)
        value = int(self.market_price(kind) * take)
        if value <= 0:
            return False
        self.captain.cargo[kind] = have - take
        if self.captain.cargo[kind] <= 1e-6:
            del self.captain.cargo[kind]
        self.captain.credits += value
        self.market_stock[self.active_port][kind] = min(
            MAX_STOCK, self.market_available(kind) + int(take))
        self.complete("sell")
        return True

    def cargo_value(self):
        return int(sum(self.market_price(k) * v for k, v in self.captain.cargo.items()))

    def sell_cargo(self):
        value = self.cargo_value()
        self.captain.credits += value
        for kind, amount in self.captain.cargo.items():
            if kind in RESOURCES:
                self.market_stock[self.active_port][kind] = min(
                    MAX_STOCK, self.market_available(kind) + int(amount))
        self.captain.cargo = {}
        if value > 0:
            self.complete("sell")
        return value

    def sell_cargo_action(self):
        return self.sell_cargo() > 0

    def pay_debt_action(self):
        return self.pay_debt() > 0

    def repair_cost(self):
        p = self.player
        cost = (p.hull.hp - p.hp) * C.REPAIR_COST_PER_HP + (p.armor_max - p.armor) * ARMOR_REPAIR_COST
        cost += sum(1.0 - p.subsystems[k] for k in SUBSYSTEMS) * SUBSYSTEM_REPAIR_COST
        cost += (p.leaks + p.water * 3) * LEAK_REPAIR_COST
        return int(math.ceil(cost * (1.0 - self.service_discount())))

    def repair(self):
        cost = self.repair_cost()
        if cost == 0 or self.captain.credits < cost:
            return False
        self.captain.credits -= cost
        self.player.repair_all()
        return True

    def rearm_cost(self):
        p = self.player
        cost = sum((w.defn.ammo - w.ammo) * w.defn.ammo_price for w in p.weapons if w.defn.ammo)
        cost += sum((u.defn.charges - u.charges) * u.defn.charge_price for u in p.utilities if u.defn.charges)
        return int(math.ceil(cost * (1.0 - self.service_discount())))

    def rearm(self):
        cost = self.rearm_cost()
        if cost == 0 or self.captain.credits < cost:
            return False
        self.captain.credits -= cost
        for w in self.player.weapons:
            w.ammo = w.defn.ammo
        for u in self.player.utilities:
            u.charges = u.defn.charges
        return True

    def ammo_pack_cost(self, kind):
        return AMMO[kind].price * AMMO_PACK

    def buy_ammo(self, kind):
        cost = self.ammo_pack_cost(kind)
        if self.captain.credits < cost:
            return False
        self.captain.credits -= cost
        self.captain.ammo_stock[kind] = self.captain.ammo_stock.get(kind, 0) + AMMO_PACK
        return True

    def cycle_group(self, slot_index):
        return self.player.cycle_group(slot_index)

    def service_all_cost(self):
        """Ремонт + боезапас + чистка налёта одной кнопкой."""
        clean = C.CLEAN_COST if self.player.fouling > 0.05 else 0
        return self.repair_cost() + self.rearm_cost() + clean

    def service_all(self):
        """Делает всё, на что хватает денег (сначала ремонт). Возвращает список сделанного."""
        done = []
        if self.repair_cost() and self.repair():
            done.append("ремонт")
        if self.rearm_cost() and self.rearm():
            done.append("боезапас")
        if self.player.fouling > 0.05 and self.clean_hull():
            done.append("чистка")
        return done

    def clean_hull(self):
        if self.player.fouling <= 0.01 or self.captain.credits < C.CLEAN_COST:
            return False
        self.captain.credits -= C.CLEAN_COST
        self.player.fouling = 0.0
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

    # --- порт: верфь и оснащение -----------------------------------------

    def hull_offer(self, key):
        """(полная цена с базовым оснащением, доплата с учётом сдачи текущего корпуса)."""
        hull = HULLS[key]
        full = hull.price + sum(MODULES[k].price for k in hull.default_fit if k)
        trade_in = int(self.player.hull.price * HULL_RESALE)
        return full, max(0, full - trade_in)

    def buy_hull(self, key):
        """Новый корпус с базовым оснащением. Модули старого корабля уходят на склад."""
        cap = self.captain
        if key == self.player.hull.key or cap.debt > 0 or not HULLS[key].purchasable:
            return "Сделка невозможна"
        _, cost = self.hull_offer(key)
        if cap.credits < cost:
            return "Не хватает кредитов"
        new = Ship(key, self.player.pos, -90)
        if self.cargo_used > new.cargo_capacity:
            return "Груз не поместится в трюм"
        cap.credits -= cost
        cap.storage += [k for k in self.player.fit if k]
        new.fouling = 0.0
        self.player = new
        return None

    def compatible(self, slot_index):
        slot = self.player.hull.slots[slot_index]
        return [m for m in MODULES.values() if m.category == slot.category and m.size <= slot.size]

    def install_problem(self, slot_index, key, from_storage=False):
        """Проверка установки без каких-либо изменений денег, склада или корабля.

        Используется и в интерфейсе предпросмотра, и в самой транзакции.
        """
        p, cap = self.player, self.captain
        slot = p.hull.slots[slot_index]
        m = MODULES[key]
        if m.category != slot.category or m.size > slot.size:
            return "Модуль не подходит к слоту"
        if from_storage and key not in cap.storage:
            return "Нет на складе"
        if not from_storage:
            if cap.debt > 0:
                return "Должникам не продают"
            if cap.credits < m.price:
                return "Не хватает кредитов"
        new_fit = list(p.fit)
        new_fit[slot_index] = key
        power = [e for e in fit_problems(p.hull, new_fit) if "энергии" in e]
        return power[0] if power else None

    def install(self, slot_index, key, from_storage=False):
        """Поставить модуль в слот. Возвращает None или текст ошибки."""
        issue = self.install_problem(slot_index, key, from_storage=from_storage)
        if issue:
            return issue
        p, cap = self.player, self.captain
        m = MODULES[key]
        if from_storage:
            cap.storage.remove(key)
        else:
            cap.credits -= m.price
        old = p.fit[slot_index]
        if old:
            cap.storage.append(old)
        p.set_module(slot_index, key)
        self.discover(f"module:{key}")
        if not from_storage:
            self.complete("install")
        # новые модули приходят заряженными
        for w in p.weapons:
            if w.index == slot_index:
                w.ammo = w.defn.ammo
        for u in p.utilities:
            if u.index == slot_index:
                u.charges = u.defn.charges
        p.recharge()
        return None

    def uninstall(self, slot_index):
        p = self.player
        old = p.fit[slot_index]
        if old is None:
            return "Слот пуст"
        self.captain.storage.append(old)
        p.set_module(slot_index, None)
        return None

    def sell_from_storage(self, key):
        cap = self.captain
        if key not in cap.storage:
            return 0
        cap.storage.remove(key)
        price = int(MODULES[key].price * MODULE_RESALE)
        cap.credits += price
        return price
