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

    kind: sensor_rail | cargo_cell | armor_plate | radiator |
          spine_channel | shoulder_guard | service_hatch
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
    render_profile: tuple = ()   # художественный полупрофиль (нос +X, y>=0); физику не меняет


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
        visual=HullVisual(
            render_profile=((30, 0), (25, 1.35), (19, 3.2), (10, 4.1), (3, 4.8),
                            (-12, 4.8), (-19, 4.3), (-25, 2.8), (-28, 1.8), (-30, 0)),
            superstructures=((-5, 0, 10, 5.5, True), (5, 0, 5.6, 3.0, False)),
            mast=(-6, 0), deck_ribs=(-23, -14, -5, 4, 13, 22),
            deck_strips=(0.33,),
            details=(
                DeckDetail("spine_channel", (0, 0), (29, 1.6)),
                DeckDetail("shoulder_guard", (-5, -3.4), (9, 1.2)),
                DeckDetail("shoulder_guard", (-5, 3.4), (9, 1.2)),
                DeckDetail("sensor_rail", (6, -2.6), (10, 1.2)),
                DeckDetail("sensor_rail", (6, 2.6), (10, 1.2)),
                DeckDetail("service_hatch", (-16, 0), (3.4, 2.4)),
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
        visual=HullVisual(
            render_profile=((27, 0), (20, 5.6), (16, 9.1), (8, 12.4),
                            (3, 14), (-4, 13.8), (-13, 13.3),
                            (-21, 11.1), (-27, 7), (-29, 0)),
            superstructures=((-8, 0, 11, 10, True), (0, 0, 6, 5.6, False)),
            mast=(-8, 0), deck_ribs=(-23, -12, -1, 10, 21),
            deck_strips=(0.29, 0.65),
            details=(
                DeckDetail("spine_channel", (-2, 0), (24, 2.2)),
                DeckDetail("shoulder_guard", (-8, -11), (14, 1.6)),
                DeckDetail("shoulder_guard", (-8, 11), (14, 1.6)),
                DeckDetail("cargo_cell", (5, 0), (11, 9)),
                DeckDetail("cargo_cell", (-19, -7), (8, 3.5)),
                DeckDetail("cargo_cell", (-19, 7), (8, 3.5)),
                DeckDetail("service_hatch", (17, 0), (4.5, 4.0)),
            )),
        desc="Широкая модульная палуба: выбор между артиллерией, перевозками "
             "и вспомогательным оборудованием.",
    ),
    HullDef(
        "bastion", "B-31 «Оплот»", "Длинный линейный корпус с усиленной цитаделью",
        hp=340, mass=230, speed_mult=0.76, turn_rate=62, cargo=42, radius=58, price=3000,
        # Ровно 114 единиц по оси корабля и 24 по ширине (4.75:1).
        # radius = 58 нужен только для широкого поиска; точное попадание
        # в этот длинный корабль рассчитывается по повернутому контуру.
        shape=((58, 0), (53, 2), (45, 5.2), (34, 8.2), (20, 10.3),
               (6, 11.6), (-17, 12), (-34, 11.3), (-46, 8.2), (-53, 4), (-56, 0),
               (-53, -4), (-46, -8.2), (-34, -11.3), (-17, -12), (6, -11.6),
               (20, -10.3), (34, -8.2), (45, -5.2), (53, -2)),
        slots=(Slot("weapon", M, (35, 0), 0, 265),
               Slot("weapon", M, (-30, 0), 180, 265),
               Slot("weapon", S, (-4, -8.5), -90, 180),
               Slot("weapon", S, (-4, 8.5), 90, 180))
        + _core(M, M, M, M, M, diagram_positions=(
            (-46, 0), (-33, 0), (-11, 0), (14, 0), (45, 0)))
        + (Slot("utility", S, diagram_pos=(4, -6.2)),
           Slot("utility", S, diagram_pos=(4, 6.2))),
        default_fit=("cannon_m", "cannon_m", "autocannon_s", "autocannon_s",
                     "engine_m", "reactor_m", "shield_m", "armor_m", "sensor_s",
                     None, None),
        series="Конструкторское бюро «Рубеж»", visual_style="industrial_sci_fi",
        visual=HullVisual(
            # New capital-hull art matches the long physical envelope.
            # The central deck is slender; weight reads from axial
            # battery stations, side armor and a layered compact citadel.
            render_profile=((58, 0), (54, 1.45), (49, 3.6), (44, 5.8),
                            (36, 7.7), (23, 9.6), (7, 11.15), (-17, 11.5),
                            (-32, 10.6), (-43, 8.4), (-51, 4.8), (-56, 0)),
            superstructures=((-7, 0, 17, 7.8, True),
                             (-19, 0, 8, 6, False),
                             (16, 0, 8, 5.4, False)),
            mast=(-7, 0),
            deck_ribs=(-47, -37, -25, -13, 0, 13, 25, 39, 48),
            deck_strips=(0.28, 0.62),
            details=(
                DeckDetail("spine_channel", (0, 0), (57, 2.2)),
                DeckDetail("shoulder_guard", (-10, -9.8), (22, 1.4)),
                DeckDetail("shoulder_guard", (-10, 9.8), (22, 1.4)),
                DeckDetail("armor_plate", (24, -7.4), (8, 3.0)),
                DeckDetail("armor_plate", (24, 7.4), (8, 3.0)),
                DeckDetail("armor_plate", (-23, -8.3), (11, 3.0)),
                DeckDetail("armor_plate", (-23, 8.3), (11, 3.0)),
                DeckDetail("armor_plate", (-37, -7.4), (9, 2.2)),
                DeckDetail("armor_plate", (-37, 7.4), (9, 2.2)),
                DeckDetail("service_hatch", (44, 0), (4.2, 3.0)),
                DeckDetail("radiator", (-47, 0), (8, 3.2)),
            )),
        desc="Длинный узкий линейный корабль: две главные осевые батареи и "
             "две вторичные бортовые установки. Огневая роль задаётся оснащением.",
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
