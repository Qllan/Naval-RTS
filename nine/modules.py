"""Каталог модулей корабля. Только данные — логика в ship.py.

Каждый модуль занимает слот своей категории и размера (модуль ≤ слота),
весит (масса замедляет корабль) и потребляет энергию реактора (`upkeep`, ед/с).
Электроника (`electronic`) в Пелене потребляет больше — если реактор не
вытягивает, конденсатор садится, и первыми гаснут щиты и сенсоры.
"""

from dataclasses import dataclass

S, M, L = 1, 2, 3
SIZE_NAME = {S: "S", M: "M", L: "L"}

CATEGORY_NAME = {
    "weapon": "Оружие",
    "engine": "Двигатель",
    "reactor": "Реактор",
    "shield": "Щит",
    "armor": "Броня",
    "sensor": "Сенсор",
    "utility": "Утилита",
}

DAMAGE_NAME = {"kinetic": "кинетика", "explosive": "взрыв", "em": "ЭМ", "torpedo": "торпеда"}


@dataclass(frozen=True)
class ModuleDef:
    key: str
    name: str
    category: str
    size: int
    price: int
    mass: float
    upkeep: float = 0.0          # постоянное потребление энергии, ед/с
    electronic: bool = False     # потребление растёт с плотностью Пелены
    veil_resist: float = 0.0     # 0..1 — какая доля штрафа Пелены игнорируется
    desc: str = ""


@dataclass(frozen=True)
class WeaponDef(ModuleDef):
    kind: str = "gun"            # gun | missile | torpedo
    damage: float = 0.0
    dmg_type: str = "kinetic"
    reload: float = 1.0
    speed: float = 600.0
    range: float = 600.0
    spread: float = 3.0          # град
    pellets: int = 1
    traverse: float = 180.0      # скорость поворота турели, град/с; 0 — неповоротная установка
    arc: float = 300.0           # полный сектор обстрела, град
    ammo: int = 0                # 0 — без боезапаса
    ammo_price: int = 0
    lock_time: float = 0.0       # ракеты: время захвата цели
    turn_rate: float = 0.0       # ракеты: манёвренность, град/с
    shot_energy: float = 0.0
    heat: float = 0.0            # нагрев за выстрел; при 100 — перегрев до остывания


@dataclass(frozen=True)
class EngineDef(ModuleDef):
    thrust: float = 0.0
    top_speed: float = 0.0
    boost_mult: float = 1.45
    boost_drain: float = 12.0    # энергия/с на форсаже


@dataclass(frozen=True)
class ReactorDef(ModuleDef):
    output: float = 0.0          # ед/с
    capacitor: float = 0.0


@dataclass(frozen=True)
class ShieldDef(ModuleDef):
    capacity: float = 0.0
    regen: float = 0.0           # ед/с
    regen_cost: float = 0.6      # энергии на единицу щита


@dataclass(frozen=True)
class ArmorDef(ModuleDef):
    hp: float = 0.0
    reduction: float = 0.0       # плоское снижение кинетического урона за попадание


@dataclass(frozen=True)
class SensorDef(ModuleDef):
    radar: float = 0.0


@dataclass(frozen=True)
class UtilityDef(ModuleDef):
    effect: str = ""
    active: bool = False
    cooldown: float = 0.0
    energy: float = 0.0
    duration: float = 0.0
    charges: int = 0             # 0 — без зарядов (только кулдаун)
    charge_price: int = 0
    value: float = 0.0


_ALL = [
    # --- оружие -----------------------------------------------------------
    WeaponDef("autocannon_s", "Автопушка «Шквал»", "weapon", S, 150, 8, kind="gun", damage=6, reload=0.2,
              speed=680, range=560, spread=2, traverse=220, arc=300, shot_energy=0.4, heat=6,
              desc="Скорострельная, быстрая турель. Слаба против брони."),
    WeaponDef("scatter_s", "Картечница «Ёрш»", "weapon", S, 220, 9, kind="gun", damage=4, pellets=7, reload=0.9,
              speed=560, range=300, spread=13, traverse=170, arc=300, shot_energy=0.8, heat=14,
              desc="Веер картечи в упор. Хороша против лёгких рейдеров."),
    WeaponDef("missile_s", "Ракетная кассета «Оса»", "weapon", S, 380, 10, kind="missile", damage=24,
              dmg_type="explosive", reload=1.4, speed=330, range=1150, traverse=0, arc=360, ammo=12, ammo_price=12,
              lock_time=1.4, turn_rate=160, electronic=True, upkeep=0.5,
              desc="Самонаведение. Нужен захват цели на радаре; Пелена сбивает наведение."),
    WeaponDef("cannon_m", "Тяжёлое орудие «Молот»", "weapon", M, 650, 30, kind="gun", damage=30, reload=1.3,
              speed=780, range=820, spread=1.5, traverse=70, arc=240, shot_energy=3, heat=20,
              desc="Медленная турель, большой урон, пробивает броню."),
    WeaponDef("em_m", "ЭМ-разрядник «Гроза»", "weapon", M, 750, 18, kind="gun", damage=13, dmg_type="em", reload=0.55,
              speed=950, range=340, spread=2, traverse=150, arc=240, shot_energy=4, heat=12, upkeep=1, electronic=True,
              desc="Выжигает щиты и подсистемы. По корпусу почти не бьёт."),
    WeaponDef("missile_m", "Ракетный комплекс «Гарпун»", "weapon", M, 950, 24, kind="missile", damage=42,
              dmg_type="explosive", reload=2.4, speed=300, range=1450, traverse=0, arc=360, ammo=10, ammo_price=25,
              lock_time=2.0, turn_rate=115, electronic=True, upkeep=1,
              desc="Тяжёлые ракеты большой дальности."),
    WeaponDef("torpedo_m", "Торпедный аппарат «Нарвал»", "weapon", M, 850, 28, kind="torpedo", damage=85,
              dmg_type="torpedo", reload=5.0, speed=230, range=1000, traverse=0, arc=20, ammo=4, ammo_price=60,
              desc="Бьёт ниже ватерлинии — щиты не спасают. Стреляет только по курсу."),

    # --- двигатели --------------------------------------------------------
    EngineDef("engine_s", "Дизель «Тягач» S", "engine", S, 100, 15, thrust=170, top_speed=230,
              boost_mult=1.45, boost_drain=12, desc="Надёжный и простой."),
    EngineDef("engine_s2", "Форсажный «Стриж» S", "engine", S, 550, 14, upkeep=1, thrust=220, top_speed=265,
              boost_mult=1.6, boost_drain=18, desc="Быстрее, но прожорлив на форсаже."),
    EngineDef("engine_m", "Турбина «Кит» M", "engine", M, 700, 40, thrust=340, top_speed=215,
              boost_mult=1.4, boost_drain=18, desc="Тянет тяжёлые корпуса."),
    EngineDef("engine_m2", "Турбина «Шторм» M", "engine", M, 1500, 45, upkeep=2, thrust=430, top_speed=245,
              boost_mult=1.5, boost_drain=26, desc="Лучшая турбина порта."),

    # --- реакторы ---------------------------------------------------------
    ReactorDef("reactor_s", "Реактор «Искра» S", "reactor", S, 100, 10, output=10, capacitor=60),
    ReactorDef("reactor_s2", "Реактор «Факел» S", "reactor", S, 480, 12, output=14, capacitor=80),
    ReactorDef("reactor_m", "Реактор «Горн» M", "reactor", M, 800, 30, output=20, capacitor=140),
    ReactorDef("reactor_m2", "Реактор «Вулкан» M", "reactor", M, 1600, 36, output=28, capacitor=190),

    # --- щиты -------------------------------------------------------------
    ShieldDef("shield_s", "Щит «Купол» S", "shield", S, 100, 8, upkeep=2, electronic=True,
              capacity=60, regen=7, desc="Базовый щит."),
    ShieldDef("shield_m", "Щит «Бастион» M", "shield", M, 800, 20, upkeep=4, electronic=True,
              capacity=150, regen=12, desc="Мощный, но в Пелене прожорлив."),
    ShieldDef("shield_res_m", "Резонансный щит M", "shield", M, 1500, 22, upkeep=4, electronic=True,
              veil_resist=0.8, capacity=115, regen=10, regen_cost=0.5,
              desc="Решётка из окаменевших филаментов. Почти не замечает Пелену."),

    # --- броня ------------------------------------------------------------
    ArmorDef("armor_s", "Бронелисты S", "armor", S, 200, 20, hp=50, reduction=2),
    ArmorDef("armor_m", "Бронепояс M", "armor", M, 600, 55, hp=140, reduction=4, desc="Надёжно, но тяжело."),
    ArmorDef("armor_comp_m", "Композит филаментов M", "armor", M, 1500, 25, hp=120, reduction=5,
             desc="Лёгкий и прочный композит из ресурсов Пелены."),

    # --- сенсоры ----------------------------------------------------------
    SensorDef("sensor_s", "Радар «Взгляд» S", "sensor", S, 100, 4, upkeep=1, electronic=True, radar=800),
    SensorDef("sensor_m", "Радар «Дозор» M", "sensor", M, 650, 8, upkeep=2, electronic=True, radar=1100,
              desc="Дальний радар. В плотной Пелене слепнет как и все."),
    SensorDef("sonar_m", "Пассивный сонар «Слух» M", "sensor", M, 900, 10, upkeep=1, electronic=True,
              veil_resist=0.8, radar=650, desc="Недалеко, зато почти не глохнет в Пелене."),

    # --- утилиты ----------------------------------------------------------
    UtilityDef("repair_gel", "Ремонтный гель", "utility", S, 350, 6, effect="repair", active=True,
               cooldown=30, energy=20, duration=6, charges=3, charge_price=40, value=9,
               desc="Латает корпус и подсистемы в бою."),
    UtilityDef("smoke", "Дымовая завеса", "utility", S, 250, 5, effect="smoke", active=True,
               cooldown=20, energy=8, duration=9, charges=4, charge_price=15, value=170,
               desc="Облако дыма: вас хуже видно, по вам хуже целятся."),
    UtilityDef("ecm", "Глушилка «Шорох»", "utility", S, 600, 6, effect="ecm", active=True, electronic=True,
               cooldown=14, energy=30, value=550, desc="Срывает захват и сбивает ракеты рядом с вами."),
    UtilityDef("bioscreen", "Био-экран", "utility", M, 2200, 12, effect="bioscreen", active=True,
               cooldown=45, energy=50, duration=7, desc="Экранирование как у Тиходонта. Вас не видят."),
    UtilityDef("damage_control", "Аварийная партия", "utility", S, 400, 6, effect="damage_control", active=True,
               cooldown=25, energy=5, value=2, desc="Тушит пожары и заделывает до двух течей."),
    UtilityDef("cargo_ext", "Расширитель трюма", "utility", S, 300, 10, effect="cargo", value=20,
               desc="+20 к трюму. Добавляет массу."),
    UtilityDef("guild_hold_mk2", "Гильдейский грузовой блок II", "utility", S, 0, 9,
               effect="cargo", value=30,
               desc="Редкий гильдейский блок. +30 к трюму, только за сертификат."),
    UtilityDef("drill", "Бур «Керн»", "utility", M, 500, 18, effect="drill", value=1.8, upkeep=1,
               desc="Добыча твёрдых ресурсов быстрее."),
    UtilityDef("collector", "Сборщик конденсата", "utility", M, 650, 14, effect="collector", value=2.2, upkeep=1,
               electronic=True, desc="Добыча Конденсата Пелены быстрее."),
]

MODULES = {m.key: m for m in _ALL}


@dataclass(frozen=True)
class AmmoDef:
    """Снаряды для кинетических пушек. Множители — к урону по каждому слою защиты."""
    key: str
    name: str
    short: str
    price: int                   # КК за снаряд (картечь — за каждую дробину)
    dmg_type: str = "kinetic"
    shield_mult: float = 1.0
    armor_mult: float = 1.0
    hull_mult: float = 1.0
    pierce: bool = False         # игнорирует плоское снижение брони
    fire_chance: float = 0.0     # шанс поджечь при уроне по корпусу
    sub_bonus: float = 0.0       # доп. шанс задеть подсистему
    desc: str = ""


AMMO = {
    "std": AmmoDef("std", "Стандартные", "СТД", 0, desc="Бесконечный запас."),
    "ap": AmmoDef("ap", "Бронебойные", "ББ", 1, shield_mult=0.7, armor_mult=1.4, pierce=True, sub_bonus=0.05,
                  desc="Пробивают броню, хуже по щитам."),
    "he": AmmoDef("he", "Фугасные", "ФУГ", 1, dmg_type="explosive", shield_mult=0.8, armor_mult=0.9,
                  hull_mult=1.25, fire_chance=0.2, sub_bonus=0.1,
                  desc="Рвут корпус, поджигают, калечат подсистемы. Слабы по щитам."),
}
AMMO_ORDER = ("std", "ap", "he")


def module_stats(m):
    """Короткие строки характеристик для UI."""
    out = []
    if isinstance(m, WeaponDef):
        dmg = f"{m.damage:g}×{m.pellets}" if m.pellets > 1 else f"{m.damage:g}"
        out.append(f"Урон {dmg} ({DAMAGE_NAME[m.dmg_type]}), перезарядка {m.reload:g} с")
        out.append(f"Дальность {m.range:g}, сектор {m.arc:g}°" + (f", поворот {m.traverse:g}°/с" if m.traverse else ""))
        if m.ammo:
            out.append(f"Боезапас {m.ammo} (по {m.ammo_price} КК)")
        if m.lock_time:
            out.append(f"Захват цели {m.lock_time:g} с")
        if m.heat:
            out.append(f"Нагрев {m.heat:g} за выстрел (перегрев на 100)")
    elif isinstance(m, EngineDef):
        out.append(f"Тяга {m.thrust:g}, скорость {m.top_speed:g}")
        out.append(f"Форсаж ×{m.boost_mult:g}, {m.boost_drain:g} эн/с")
    elif isinstance(m, ReactorDef):
        out.append(f"Выработка {m.output:g} эн/с, конденсатор {m.capacitor:g}")
    elif isinstance(m, ShieldDef):
        out.append(f"Ёмкость {m.capacity:g}, восстановление {m.regen:g}/с")
    elif isinstance(m, ArmorDef):
        out.append(f"Прочность {m.hp:g}, снижение кинетики −{m.reduction:g}")
    elif isinstance(m, SensorDef):
        out.append(f"Радар {m.radar:g} м")
    elif isinstance(m, UtilityDef):
        if m.active:
            parts = [f"перезарядка {m.cooldown:g} с", f"{m.energy:g} эн"]
            if m.charges:
                parts.append(f"{m.charges} заряда")
            out.append("Активный: " + ", ".join(parts))
        else:
            out.append("Пассивный")
    out.append(f"Масса {m.mass:g}, энергия {m.upkeep:g}/с" + (" (электроника)" if m.electronic else ""))
    if m.veil_resist:
        out.append(f"Устойчивость к Пелене {int(m.veil_resist * 100)}%")
    return out
