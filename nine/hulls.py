"""Каталог корпусов. Корпус задаёт прочность, массу, манёвренность, трюм и слоты.

Слоты оружия — это точки на корпусе (`pos`, нос вдоль +X) с направлением
(`facing`) и предельным сектором (`arc`): кормовая турель не стреляет вперёд
сквозь надстройку, бортовые — только на свой борт.
"""

from dataclasses import dataclass

from .modules import M, S


@dataclass(frozen=True)
class Slot:
    category: str
    size: int
    pos: tuple = (0.0, 0.0)
    facing: float = 0.0
    arc: float = 360.0
    diagram_pos: tuple | None = None   # внутренний узел на схеме, НЕ координата стрельбы


@dataclass(frozen=True)
class DeckDetail:
    """Элемент художественной палубы; координаты в единицах корпуса.

    kind: sensor_rail | cargo_cell | armor_plate | radiator
    size: длина по оси нос-корма и поперечная ширина.
    """
    kind: str
    pos: tuple
    size: tuple


@dataclass(frozen=True)
class HullVisual:
    """Визуальные элементы корпуса; координаты: нос по +X."""
    superstructures: tuple = ()  # x, y, length, width, front_windows
    mast: tuple = (0.0, 0.0)
    deck_ribs: tuple = ()        # x поперечных швов
    deck_strips: tuple = ()      # доля полуширины продольных швов
    details: tuple = ()          # отличительные технические элементы на палубе


@dataclass(frozen=True)
class HullDef:
    """`price` — цена голого корпуса; базовое оснащение оплачивается отдельно."""
    key: str
    name: str
    role: str
    hp: float
    mass: float
    speed_mult: float
    turn_rate: float        # град/с на ходу
    cargo: int
    radius: float
    price: int
    shape: tuple
    slots: tuple
    default_fit: tuple       # ключ модуля (или None) на каждый слот
    purchasable: bool = True
    desc: str = ""
    series: str = ""          # линейка/производитель вместо игрового класса
    visual_style: str = "legacy"  # стиль художника; старые корпуса остаются совместимыми
    visual: HullVisual | None = None


def _core(engine, reactor, shield, armor, sensor, *, diagram_positions=None):
    """Пять внутренних узлов. Старые корпуса сохраняют прежнюю компоновку.

    diagram_positions — реальные проектные точки в корпусе, а не логика
    оружейных установок. Без неё узел виден только в списке.
    """
    pairs = (("engine", engine), ("reactor", reactor), ("shield", shield),
             ("armor", armor), ("sensor", sensor))
    if diagram_positions is None:
        return tuple(Slot(cat, size) for cat, size in pairs)
    if len(diagram_positions) != len(pairs):
        raise ValueError("Нужно ровно пять координат внутренних узлов")
    return tuple(Slot(cat, size, diagram_pos=pos)
                 for (cat, size), pos in zip(pairs, diagram_positions))


_ALL = [
    HullDef(
        "scout", "Скаут", "Разведка, добыча, лёгкий бой", hp=90, mass=50, speed_mult=1.0, turn_rate=150,
        cargo=20, radius=16, price=400,
        shape=((20, 0), (4, 8), (-14, 8), (-18, 0), (-14, -8), (4, -8)),
        slots=(Slot("weapon", S, (6, 0), 0, 300),) + _core(S, S, S, S, M) + (Slot("utility", S),),
        default_fit=("autocannon_s", "engine_s", "reactor_s", "shield_s", None, "sensor_s", None),
        desc="Быстрый и хрупкий. Большой слот сенсора — глаза флота.",
    ),
    HullDef(
        "corvette", "Корвет", "Охотник на рейдеров", hp=150, mass=85, speed_mult=0.97, turn_rate=125,
        cargo=25, radius=18, price=900,
        shape=((24, 0), (8, 10), (-18, 10), (-22, 0), (-18, -10), (8, -10)),
        slots=(Slot("weapon", S, (10, 0), 0, 300), Slot("weapon", S, (-10, 0), 180, 300))
        + _core(S, S, S, M, S) + (Slot("utility", S), Slot("utility", S)),
        default_fit=("autocannon_s", "autocannon_s", "engine_s", "reactor_s2", "shield_s", "armor_s", "sensor_s",
                     None, None),
        desc="Две турели — нос и корма. Первый настоящий боевой корабль.",
    ),
    HullDef(
        "torpedo_boat", "Торпедный катер", "Засады и удары по крупным целям", hp=110, mass=65, speed_mult=1.05,
        turn_rate=135, cargo=15, radius=17, price=1000,
        shape=((26, 0), (6, 7), (-18, 8), (-20, 0), (-18, -8), (6, -7)),
        slots=(Slot("weapon", M, (14, 0), 0, 20), Slot("weapon", S, (-6, 0), 180, 300))
        + _core(S, S, S, S, S) + (Slot("utility", S), Slot("utility", S)),
        default_fit=("torpedo_m", "autocannon_s", "engine_s2", "reactor_s", "shield_s", None, "sensor_s",
                     "smoke", None),
        desc="Носовой торпедный аппарат бьёт по курсу. Наводись корпусом.",
    ),
    HullDef(
        "cruiser", "Крейсер", "Универсал, основной боевой", hp=240, mass=150, speed_mult=0.92, turn_rate=90,
        cargo=35, radius=22, price=1800,
        shape=((28, 0), (10, 11), (-20, 12), (-26, 0), (-20, -12), (10, -11)),
        slots=(Slot("weapon", M, (14, 0), 0, 270), Slot("weapon", M, (-14, 0), 180, 270),
               Slot("weapon", S, (0, -10), -90, 180), Slot("weapon", S, (0, 10), 90, 180))
        + _core(M, M, M, M, M) + (Slot("utility", S), Slot("utility", S)),
        default_fit=("cannon_m", None, "autocannon_s", "autocannon_s", "engine_m", "reactor_m", "shield_m",
                     "armor_s", "sensor_s", None, None),
        desc="Две тяжёлые башни и два бортовых орудия.",
    ),
    HullDef(
        "barge", "Барка добытчика", "Добыча и перевозки", hp=220, mass=140, speed_mult=0.82, turn_rate=70,
        cargo=90, radius=26, price=1400,
        shape=((24, 0), (18, 14), (-26, 14), (-26, -14), (18, -14)),
        slots=(Slot("weapon", S, (4, 0), 0, 360),) + _core(M, M, S, M, S)
        + (Slot("utility", M), Slot("utility", M), Slot("utility", S)),
        default_fit=("autocannon_s", "engine_m", "reactor_m", "shield_s", "armor_s", "sensor_s", "drill",
                     "collector", None),
        desc="Огромный трюм и слоты под добычу. Гружёная — медленная.",
    ),
    # --- R0: проекты корпусов без фиксированных игровых классов ----------
    # Техническая специализация задаётся геометрией и узлами; роль — сборкой.
    HullDef(
        "needle", "N-17 «Игла»", "Узкий корпус, лёгкое оснащение, высокая манёвренность",
        hp=105, mass=58, speed_mult=1.07, turn_rate=145, cargo=28, radius=18, price=850,
        shape=((30, 0), (20, 3), (4, 5), (-17, 5), (-28, 2), (-30, 0),
               (-28, -2), (-17, -5), (4, -5), (20, -3)),
        slots=(Slot("weapon", S, (15, 0), 0, 300),
               Slot("weapon", S, (-12, 0), 180, 300))
        + _core(S, S, S, S, M, diagram_positions=(
            (-24, 0), (-18, 0), (-3, 1.8), (-3, -1.8), (9, 0)))
        + (Slot("utility", S, diagram_pos=(3, -2)),
           Slot("utility", S, diagram_pos=(3, 2))),
        default_fit=("autocannon_s", None, "engine_s2", "reactor_s2", "shield_s",
                     None, "sensor_s", None, None),
        series="Верфи «Северный контур»", visual_style="industrial_sci_fi",
        visual=HullVisual(superstructures=((-5, 0, 10, 5.5, True),),
                          mast=(-6, 0), deck_ribs=(-23, -14, -5, 4, 13, 22),
                          deck_strips=(0.33,),
                          details=(
                              DeckDetail("sensor_rail", (6, -2.6), (10, 1.2)),
                              DeckDetail("sensor_rail", (6, 2.6), (10, 1.2)),
                              DeckDetail("radiator", (-23, 0), (6, 2.8)),
                          )),
        desc="Узкий индустриальный корпус с открытыми универсальными узлами. "
             "Подходит для разных лёгких сборок без обязательной роли.",
    ),
    HullDef(
        "manta", "M-08 «Манта»", "Широкая палуба, разнесённое вооружение, большой трюм",
        hp=205, mass=145, speed_mult=0.91, turn_rate=92, cargo=56, radius=26, price=1900,
        shape=((27, 0), (17, 9), (5, 14), (-18, 13), (-28, 7), (-29, 0),
               (-28, -7), (-18, -13), (5, -14), (17, -9)),
        slots=(Slot("weapon", M, (13, -8), -40, 200),
               Slot("weapon", M, (13, 8), 40, 200),
               Slot("weapon", S, (-20, 0), 180, 260))
        + _core(M, M, M, M, M, diagram_positions=(
            (-23, 0), (-15, 0), (-2, 0), (-5, 9), (10, 0)))
        + (Slot("utility", S, diagram_pos=(3, -7)),
           Slot("utility", M, diagram_pos=(3, 7))),
        default_fit=("cannon_m", None, "autocannon_s", "engine_m", "reactor_m",
                     "shield_m", "armor_s", "sensor_s", "cargo_ext", None),
        series="Промышленная серия «Атлас»", visual_style="industrial_sci_fi",
        visual=HullVisual(superstructures=((-8, 0, 11, 10, True),),
                          mast=(-8, 0), deck_ribs=(-23, -12, -1, 10, 21),
                          deck_strips=(0.29, 0.65),
                          details=(
                              DeckDetail("cargo_cell", (5, 0), (11, 9)),
                              DeckDetail("cargo_cell", (-19, -7), (8, 3.5)),
                              DeckDetail("cargo_cell", (-19, 7), (8, 3.5)),
                          )),
        desc="Широкая модульная палуба: выбор между артиллерией, перевозками "
             "и вспомогательным оборудованием.",
    ),
    HullDef(
        "bastion", "B-31 «Оплот»", "Жёсткая броневая платформа, четыре оружейных узла",
        hp=280, mass=185, speed_mult=0.82, turn_rate=76, cargo=42, radius=30, price=2500,
        shape=((35, 0), (27, 8), (13, 13), (-23, 14), (-34, 8), (-36, 0),
               (-34, -8), (-23, -14), (13, -13), (27, -8)),
        slots=(Slot("weapon", M, (19, 0), 0, 265),
               Slot("weapon", M, (-22, 0), 180, 265),
               Slot("weapon", S, (0, -11), -90, 180),
               Slot("weapon", S, (0, 11), 90, 180))
        + _core(M, M, M, M, M, diagram_positions=(
            (-30, 0), (-17, 0), (-4, 0), (13, 0), (27, 0)))
        + (Slot("utility", S, diagram_pos=(-10, -9)),
           Slot("utility", S, diagram_pos=(-10, 9))),
        default_fit=("cannon_m", "cannon_m", "autocannon_s", "autocannon_s",
                     "engine_m", "reactor_m", "shield_m", "armor_m", "sensor_s",
                     None, None),
        series="Конструкторское бюро «Рубеж»", visual_style="industrial_sci_fi",
        visual=HullVisual(superstructures=((-5, 0, 15, 10, True),
                                         (-17, 0, 6, 7, False)),
                          mast=(-5, 0), deck_ribs=(-30, -20, -10, 0, 10, 20, 30),
                          deck_strips=(0.38, 0.72),
                          details=(
                              DeckDetail("armor_plate", (10, -8.5), (9, 4)),
                              DeckDetail("armor_plate", (10, 8.5), (9, 4)),
                              DeckDetail("armor_plate", (-10, -8.5), (9, 4)),
                              DeckDetail("armor_plate", (-10, 8.5), (9, 4)),
                              DeckDetail("radiator", (-30, 0), (6, 4)),
                          )),
        desc="Тяжёлая силовая рама с разнесёнными башнями. Оружие и защиту "
             "можно заменить поддерживающими системами.",
    ),
    # --- только для NPC и особых случаев ---------------------------------
    HullDef(
        "raider", "Рейдер Прилива", "Пират", hp=70, mass=45, speed_mult=1.0, turn_rate=135, cargo=0, radius=15,
        price=300, purchasable=False,
        shape=((18, 0), (0, 10), (-14, 6), (-10, 0), (-14, -6), (0, -10)),
        slots=(Slot("weapon", S, (4, 0), 0, 300), Slot("weapon", S, (-4, 0), 0, 360))
        + _core(S, S, S, S, S),
        default_fit=("autocannon_s", None, "engine_s2", "reactor_s", "shield_s", None, "sensor_s"),
    ),
    HullDef(
        "capsule", "Спасательная капсула", "", hp=22, mass=20, speed_mult=0.9, turn_rate=200, cargo=0, radius=8,
        price=0, purchasable=False,
        shape=((8, 0), (0, 6), (-7, 0), (0, -6)),
        slots=(Slot("engine", S), Slot("reactor", S)),
        default_fit=("engine_s", "reactor_s"),
    ),
]

HULLS = {h.key: h for h in _ALL}
PLAYER_HULLS = [h for h in _ALL if h.purchasable]
