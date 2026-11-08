"""Векторные корабли: корпус рисуется один раз в высоком разрешении, поворот и масштаб кэшируются.

Координаты в «единицах корпуса» (как в hulls.py): нос вдоль +X, правый борт — +Y.
Мастер-спрайт рисуется с R пикселей на единицу и сглаживается при уменьшении.
"""

import math
import random
from collections import OrderedDict
from functools import lru_cache

import pygame
from pygame.math import Vector2

from ..hulls import HULLS
from .palette import SHIP_PALETTES, ShipPalette, mix, shade
from .style_tokens import lod_for_length, rgb

R = 6                    # пикселей на единицу в мастер-спрайте
ANGLE_STEP = 2.0         # шаг кэша по углу, град
ZOOM_STEP = 0.05
CACHE_LIMIT = 5000

# Полупрофили корпусов (нос → корма, y ≥ 0); зеркалятся на левый борт
PROFILES = {
    "scout": [(21, 0), (17, 2.6), (10, 5.6), (0, 7), (-12, 7), (-17, 5.6), (-19, 3), (-19, 0)],
    "corvette": [(26, 0), (20, 3.8), (10, 8), (-4, 9.6), (-18, 9.6), (-22, 7), (-23, 0)],
    "torpedo_boat": [(28, 0), (21, 2.8), (9, 6.4), (-10, 7.4), (-18, 7), (-21, 4.2), (-21, 0)],
    "cruiser": [(30, 0), (24, 4.6), (12, 10.2), (-6, 12), (-20, 12), (-26, 9), (-28, 0)],
    "barge": [(25, 0), (23.5, 8.5), (19, 13.5), (-24, 14), (-27, 12), (-27.5, 0)],
    "raider": [(20, 0), (13, 3.6), (4, 8.6), (-6, 9), (-11, 7), (-14, 6.4), (-13, 0)],
    "capsule": [(8.5, 0), (7, 3.6), (3, 5.8), (-3, 5.8), (-7, 3.6), (-8.5, 0)],
}

# Новые корпуса берут форму непосредственно из каталога, без второго
# перечня ключей в рендерере. Старые профили сохраняются для совместимости.
def _profile_from_shape(shape):
    half = [(float(x), float(y)) for x, y in shape if y >= 0]
    half.sort(key=lambda point: -point[0])
    return half


for _key, _definition in HULLS.items():
    visual = _definition.visual
    if visual is not None and visual.render_profile:
        PROFILES.setdefault(_key, list(visual.render_profile))
    else:
        PROFILES.setdefault(_key, _profile_from_shape(_definition.shape))


@lru_cache(maxsize=3)
def industrial_palette(pal_key):
    """Approved R1.0 metal palette for the three R1.1 industrial hulls.

    Legacy ship palettes stay untouched. The faction marking remains
    distinct from technical cyan and never recolors the entire hull.
    """
    signal = "signal_pirate" if pal_key == "pirate" else "signal_friendly"
    return ShipPalette(
        hull=rgb("steel_hull"), deck=rgb("steel_deck"),
        plank=rgb("steel_seam"), trim=rgb("steel_shadow"),
        superstructure=rgb("steel_roof"), roof=rgb("steel_edge"),
        window=rgb("signal_window"), accent=rgb(signal),
        turret=rgb("steel_armor"), armor=rgb("steel_armor"),
    )


# Надстройки: (x, y, длина, ширина, окна спереди)
SUPERSTRUCTURE = {
    "scout": [(-5, 0, 9, 7, True)],
    "corvette": [(0, 0, 9, 8.5, True)],
    "torpedo_boat": [(3, 0, 8, 6.5, True)],
    "cruiser": [(3, 0, 12, 10, True), (-5.5, 0, 4, 7, False)],
    "barge": [(-21, 0, 7, 22, True)],
    "raider": [(-9, 0, 6, 7.5, True)],
    "capsule": [(0, 0, 5, 5, True)],
}

FUNNELS = {"corvette": [(-6, 0, 2.2)], "cruiser": [(-5.5, 0, 2.6)], "barge": [(-21, 0, 2.4)]}
LIFEBOATS = {"corvette": [(-3, 1)], "cruiser": [(-2, 1), (-11, 1)], "barge": [(-16, 1)]}
HATCHES = {"barge": [(14, 0, 7, 18), (-8, 0, 7, 18)]}
MAST = {"scout": (-7.5, 0), "corvette": (-3, 0), "torpedo_boat": (1, 0), "cruiser": (5, 0), "barge": (-22.5, 0),
        "raider": (-10, 0), "capsule": (0, 0)}


def superstructures(hull_key):
    visual = HULLS[hull_key].visual
    return visual.superstructures if visual is not None else SUPERSTRUCTURE.get(hull_key, ())


def mast_position(hull_key):
    visual = HULLS[hull_key].visual
    return visual.mast if visual is not None else MAST.get(hull_key, (0, 0))


def outline(key):
    half = PROFILES[key]
    return half + [(x, -y) for x, y in reversed(half[1:-1])]


def _scaled(pts, sx, sy):
    return [(x * sx, y * sy) for x, y in pts]


class _Canvas:
    """Холст мастер-спрайта с переводом координат корпуса в пиксели."""

    def __init__(self, extent):
        self.extent = extent
        size = int(extent * 2 * R)
        self.surf = pygame.Surface((size, size), pygame.SRCALPHA)
        self.c = size / 2

    def p(self, x, y):
        return (self.c + x * R, self.c + y * R)

    def poly(self, pts, color, width=0):
        pygame.draw.polygon(self.surf, color, [self.p(x, y) for x, y in pts], int(width * R) if width else 0)

    def line(self, a, b, color, width=0.4):
        pygame.draw.line(self.surf, color, self.p(*a), self.p(*b), max(1, int(width * R)))

    def _blend(self, rect, draw):
        """Полупрозрачное рисование со смешиванием (draw.* на SRCALPHA перезаписывает альфу)."""
        rect = pygame.Rect(rect).inflate(4, 4)
        tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
        draw(tmp, rect.topleft)
        self.surf.blit(tmp, rect.topleft)

    def circle(self, x, y, r, color, width=0):
        rad = max(1, int(r * R))
        w = int(width * R) if width else 0
        c = self.p(x, y)
        if len(color) == 4 and color[3] < 255:
            self._blend((c[0] - rad, c[1] - rad, rad * 2, rad * 2),
                        lambda s, o: pygame.draw.circle(s, color, (c[0] - o[0], c[1] - o[1]), rad, w))
        else:
            pygame.draw.circle(self.surf, color, c, rad, w)

    def rect(self, x, y, lx, ly, color, width=0, radius=0.6):
        rr = pygame.Rect(0, 0, lx * R, ly * R)
        rr.center = self.p(x, y)
        w = int(width * R) if width else 0
        if len(color) == 4 and color[3] < 255:
            self._blend(rr, lambda s, o: pygame.draw.rect(s, color, rr.move(-o[0], -o[1]), w,
                                                          border_radius=int(radius * R)))
        else:
            pygame.draw.rect(self.surf, color, rr, w, border_radius=int(radius * R))
        return rr


# --- корпус -----------------------------------------------------------------

def _industrial_details(cv, visual, pal):
    """Крупные узнаваемые функциональные элементы без случайного декора.

    Отрисовка происходит до башен и надстроек: оружие и мостики физически
    перекрывают детали палубы, а не оказываются спрятаны за украшениями.
    """
    for detail in visual.details:
        x, y = detail.pos
        length, width = detail.size
        if detail.kind == "sensor_rail":
            cv.rect(x, y, length, width, shade(pal.trim, 1.15), radius=0.15)
            cv.line((x - length * 0.4, y), (x + length * 0.4, y),
                    pal.accent, 0.13)
            for offset in (-0.25, 0, 0.25):
                cv.line((x + length * offset, y - width * 0.35),
                        (x + length * offset, y + width * 0.35),
                        shade(pal.superstructure, 0.75), 0.18)
        elif detail.kind == "cargo_cell":
            cv.rect(x + 0.45, y + 0.45, length, width, (0, 0, 0, 65), radius=0.25)
            cv.rect(x, y, length, width, shade(pal.deck, 0.53), radius=0.3)
            cv.rect(x, y, length - 1, width - 1, shade(pal.roof, 0.78), radius=0.15)
            for offset in (-0.27, 0, 0.27):
                xx = x + length * offset
                cv.line((xx, y - width * 0.36), (xx, y + width * 0.36),
                        shade(pal.trim, 1.5), 0.2)
        elif detail.kind == "armor_plate":
            cv.rect(x + 0.45, y + 0.45, length, width, (0, 0, 0, 85), radius=0.2)
            cv.rect(x, y, length, width, pal.armor, radius=0.18)
            cv.rect(x, y, length - 0.7, width - 0.7,
                    shade(pal.armor, 0.7), width=0.18, radius=0.18)
            for sign in (-1, 1):
                cv.circle(x + sign * (length / 2 - 0.85), y,
                          0.25, shade(pal.trim, 1.35))
        elif detail.kind == "radiator":
            cv.rect(x, y, length, width, shade(pal.trim, 0.8), radius=0.15)
            count = max(2, int(length / 1.2))
            for i in range(count):
                xx = x - length / 2 + length * (i + 0.5) / count
                cv.line((xx, y - width * 0.37),
                        (xx, y + width * 0.37),
                        shade(pal.superstructure, 0.6), 0.22)
        elif detail.kind == "spine_channel":
            # Dark keel-service trench with two narrow reinforced shoulders.
            cv.rect(x + 0.25, y + 0.25, length, width + 1.1,
                    (0, 0, 0, 70), radius=0.12)
            cv.rect(x, y, length, width + 0.8, shade(pal.deck, 0.58), radius=0.15)
            for side in (-1, 1):
                cv.line((x - length * 0.48, y + side * width * 0.5),
                        (x + length * 0.48, y + side * width * 0.5),
                        shade(pal.superstructure, 0.85), 0.22)
            cv.line((x - length * 0.4, y), (x + length * 0.4, y),
                    shade(pal.trim, 1.3), 0.16)
        elif detail.kind == "shoulder_guard":
            # Real layered armor with a cast shadow, a bright beveled edge
            # and one service joint rather than randomized decoration.
            cv.rect(x + 0.35, y + 0.35, length, width, (0, 0, 0, 75), radius=0.16)
            cv.rect(x, y, length, width, pal.armor, radius=0.12)
            cv.line((x - length * 0.45, y - width * 0.32),
                    (x + length * 0.42, y - width * 0.32),
                    shade(pal.armor, 1.36), 0.17)
            cv.line((x, y - width * 0.38), (x, y + width * 0.38),
                    shade(pal.trim, 1.35), 0.14)
        elif detail.kind == "service_hatch":
            # Tactile access panel; the warm dot signifies maintenance.
            cv.rect(x + 0.28, y + 0.28, length, width, (0, 0, 0, 68), radius=0.18)
            cv.rect(x, y, length, width, shade(pal.roof, 0.72), radius=0.16)
            cv.rect(x, y, length - 0.6, width - 0.6,
                    shade(pal.superstructure, 0.65), width=0.12, radius=0.1)
            cv.circle(x - length * 0.28, y, 0.22, rgb("signal_amber"))
            cv.line((x, y - width * 0.25), (x, y + width * 0.25),
                    shade(pal.trim, 1.5), 0.16)
        else:
            raise ValueError(f"Unknown deck detail: {detail.kind}")



def half_width(hull_key, x):
    """Полуширина корпуса в точке x (интерполяция по профилю)."""
    prof = PROFILES[hull_key]
    if x >= prof[0][0] or x <= prof[-1][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(prof, prof[1:]):
        if x1 <= x <= x0:
            t = (x0 - x) / (x0 - x1) if x0 != x1 else 0.0
            return y0 + (y1 - y0) * t
    return 0.0


def _blocked(hull_key, x, y, pad=3.5):
    """Занято ли место надстройкой или установкой оружия (чтобы не ставить туда мелочь)."""
    for sx, sy, lx, ly, _ in superstructures(hull_key):
        if abs(x - sx) < lx / 2 + 1 and abs(y - sy) < ly / 2 + 1:
            return True
    for slot in HULLS[hull_key].slots:
        if slot.category == "weapon" and math.hypot(x - slot.pos[0], y - slot.pos[1]) < pad + 1:
            return True
    return False


def _indexed_modules(hull_key, static_modules):
    """Normalize old (key, module) and new (slot_index, module) callers.

    The slot index is part of the sprite identity, so a module moved to
    another fitting slot cannot reuse an incorrect cached hull image.
    """
    occupied = set()
    result = []
    slots = HULLS[hull_key].slots
    for locator, module in static_modules:
        if type(locator) is int:
            index = locator
        else:
            index = next((i for i, slot in enumerate(slots)
                          if i not in occupied and slot.category == module.category
                          and module.size <= slot.size), None)
        if index is None or not 0 <= index < len(slots) or index in occupied:
            raise ValueError("Invalid duplicate/unknown installation slot")
        slot = slots[index]
        if slot.category != module.category or module.size > slot.size:
            raise ValueError("Module incompatible with visual slot")
        occupied.add(index)
        result.append((index, module))
    return tuple(result)


def _industrial_fit_modules(cv, hull_key, pal, installations):
    """R1.2: actual fitted components on their own schematic deck positions.

    The position is taken only from the hull's non-weapon Slot.diagram_pos.
    All pictograms are low-cost deterministic vector geometry and are drawn
    atop the superstructure, so their functional identity survives a refit.
    """
    accent = rgb("signal_cyan")
    low = rgb("signal_cyan_low")
    amber = rgb("signal_amber")
    for index, mod in installations:
        slot = HULLS[hull_key].slots[index]
        if slot.diagram_pos is None:
            continue
        x, y = slot.diagram_pos
        category = slot.category
        # Short sides of narrow hulls use thinner housings. Panels remain
        # local to the actual illustrated outline, including B-31's keel.
        max_width = max(1.4, 2 * (half_width(hull_key, x) - abs(y) - 0.35))
        length = (6.4 if mod.size > 1 else 4.0)
        width = min((4.6 if mod.size > 1 else 2.8), max_width)
        small = width < 2.3
        cv.rect(x + 0.25, y + 0.25, length + 0.45, width + 0.3,
                (0, 0, 0, 95), radius=0.25)
        cv.rect(x, y, length, width, shade(pal.trim, 1.35), radius=0.26)
        cv.rect(x, y, length - 0.5, width - 0.45,
                shade(pal.deck, 0.73), radius=0.18)
        cv.line((x - length * 0.36, y - width * 0.35),
                (x + length * 0.36, y - width * 0.35),
                shade(pal.roof, 1.15), 0.16)
        if category == "engine":
            # A visible multi-channel turbine or high-output intake.
            count = 3 if mod.key.endswith("2") else 2
            for k in range(count):
                yy = y + (k - (count - 1) / 2) * width * 0.47
                cv.line((x - length * 0.33, yy), (x + length * 0.25, yy),
                        shade(pal.trim, 1.65), 0.36)
                cv.circle(x - length * 0.32, yy, 0.28, amber)
            cv.rect(x + length * 0.32, y, 0.5, width * 0.6, amber, radius=0.1)
        elif category == "reactor":
            # Circular shielded core with output-class-dependent rings.
            r = min(width * 0.38, 1.65)
            cv.circle(x, y, r, shade(pal.armor, 0.68))
            cv.circle(x, y, r * 0.67, accent if mod.key.endswith("2") else low)
            if mod.key.endswith("2"):
                cv.circle(x, y, r * 1.17, amber, width=0.15)
            for side in (-1, 1):
                cv.rect(x + side * length * 0.35, y, 0.48, width * 0.55,
                        shade(pal.roof, 0.85), radius=0.1)
        elif category == "shield":
            # Regular emitter = twin fins; veil-resistant = cross lattice.
            for sign in (-1, 1):
                cv.line((x - length * 0.28, y + sign * width * 0.28),
                        (x + length * 0.28, y + sign * width * 0.28),
                        accent if mod.key == "shield_res_m" else low, 0.28)
            if mod.key == "shield_res_m":
                cv.line((x - length * 0.2, y - width * 0.25),
                        (x + length * 0.2, y + width * 0.25),
                        rgb("veil_fringe"), 0.27)
                cv.line((x - length * 0.2, y + width * 0.25),
                        (x + length * 0.2, y - width * 0.25),
                        rgb("veil_fringe"), 0.27)
            else:
                cv.circle(x, y, width * 0.22, accent, width=0.24)
        elif category == "armor":
            # Stacked armor blocks vs visibly lighter fiber composite.
            count = 3 if mod.key == "armor_comp_m" else 2
            for k in range(count):
                xx = x + (k - (count - 1) / 2) * length * 0.29
                cv.rect(xx, y, max(0.6, length * 0.2), width * 0.75,
                        shade(pal.armor, 1.1), radius=0.12)
                if mod.key == "armor_comp_m":
                    cv.line((xx - 0.4, y - width * 0.3),
                            (xx + 0.4, y + width * 0.3), low, 0.16)
        elif category == "sensor":
            if mod.key == "sonar_m":
                for sign in (-1, 1):
                    cv.circle(x + sign * length * 0.17, y, width * 0.19, low,
                              width=0.22)
                cv.line((x - length * 0.25, y), (x + length * 0.25, y),
                        shade(pal.roof, 1.2), 0.18)
            else:
                span = length * (0.36 if mod.key == "sensor_m" else 0.24)
                cv.line((x, y - width * 0.38), (x, y + width * 0.38),
                        shade(pal.roof, 1.3), 0.32)
                cv.line((x - span, y), (x + span, y), accent, 0.34)
                for sign in (-1, 1):
                    cv.circle(x + sign * span, y, 0.3, low)
        elif category == "utility":
            effect = mod.effect
            if effect == "cargo":
                for sign in (-1, 0, 1):
                    cv.rect(x + sign * length * 0.25, y, 0.75, width * 0.67,
                            shade(pal.armor, 1.1), radius=0.08)
            elif effect in ("repair", "damage_control"):
                cv.line((x - 1.0, y), (x + 1.0, y), amber, 0.5)
                cv.line((x, y - width * 0.35), (x, y + width * 0.35), amber, 0.5)
            elif effect == "smoke":
                for shift in (-0.85, 0, 0.85):
                    cv.circle(x + shift, y, 0.38, shade(pal.roof, 0.8))
            elif effect == "ecm":
                cv.line((x - 1.2, y - width * 0.22), (x, y + width * 0.25), accent, 0.3)
                cv.line((x, y + width * 0.25), (x + 1.2, y - width * 0.22), accent, 0.3)
                cv.circle(x, y, 0.33, accent)
            elif effect == "bioscreen":
                cv.circle(x, y, width * 0.29, low, width=0.23)
                cv.circle(x, y, width * 0.13, rgb("veil_fringe"))
            elif effect == "drill":
                cv.poly([(x - 1.3, y - width * 0.27), (x + 1.5, y),
                         (x - 1.3, y + width * 0.27)], amber)
            elif effect == "collector":
                for sign in (-1, 0, 1):
                    cv.circle(x + sign * 1.0, y, 0.35, low)
            else:
                cv.rect(x, y, 1.5, width * 0.5, amber, radius=0.1)
        if not small:
            cv.circle(x - length * 0.42, y - width * 0.27, 0.17, amber)


def build_hull(hull_key, pal_key, static_modules, damage_level):
    """Мастер-спрайт корпуса со статичными модулями и следами повреждений."""
    industrial = HULLS[hull_key].visual_style == "industrial_sci_fi"
    installations = _indexed_modules(hull_key, static_modules)
    pal = industrial_palette(pal_key) if industrial else SHIP_PALETTES[pal_key]
    pts = outline(hull_key)
    extent = max(max(abs(x), abs(y)) for x, y in pts) + 10
    cv = _Canvas(extent)
    bow = PROFILES[hull_key][0][0]
    stern = PROFILES[hull_key][-1][0]
    hw = max(y for _, y in PROFILES[hull_key])
    small = hull_key == "capsule"
    rng = random.Random(f"{hull_key}:{pal_key}") if HULLS[hull_key].visual is not None else (
        random.Random(hash((hull_key, pal_key)) & 0xffffff))
    pirate = pal_key == "pirate"
    # --- борт: ватерлиния (сурик), обшивка, затенение правого борта
    cv.poly(pts, (37, 55, 63) if industrial else (116, 42, 36) if not pirate else (92, 44, 30))
    inner = _scaled(pts, 0.985, 0.94)
    cv.poly(inner, pal.hull)
    cv.poly([(x, y) for x, y in inner if y >= 0] + [(stern * 0.985, 0)], shade(pal.hull, 0.8))
    if not small:
        # пояса обшивки и шпангоуты
        for k in (0.9, 0.84):
            cv.poly(_scaled(pts, 0.99, k), shade(pal.hull, 0.72), width=0.1)
        x = stern + 1.5
        while x < bow - 2:
            h = half_width(hull_key, x)
            for side in (-1, 1):
                cv.line((x, side * h * 0.93), (x, side * h * 0.8), shade(pal.hull, 0.7), 0.1)
                if rng.random() < 0.9:
                    cv.circle(x + 0.6, side * h * 0.87, 0.12, shade(pal.hull, 1.35))
            x += 2.4
    cv.poly(pts, pal.trim, width=0.35)

    # --- палуба: доски со стыками, леера
    deck = _scaled(pts, 0.9, 0.78)
    half_w = hw * 0.78
    # доски рисуем на отдельном слое и обрезаем по форме палубы
    layer = _Canvas(extent)
    layer.poly(deck, pal.deck)
    if industrial:
        # Швы и линии палубы из визуального чертежа.
        visual = HULLS[hull_key].visual
        for x in (visual.deck_ribs if visual else ()):
            width = half_width(hull_key, x) * 0.68
            if width > 2:
                layer.line((x, -width), (x, width), shade(pal.deck, 0.64), 0.22)
                for side in (-1, 1):
                    layer.line((x + 1.1, side * (width - 1.2)),
                               (x + 3.3, side * (width - 1.2)), shade(pal.deck, 1.23), 0.16)
        for fraction in (visual.deck_strips if visual else ()):
            for side in (-1, 1):
                layer.line((stern + 7, side * half_w * fraction),
                           (bow - 7, side * half_w * fraction), shade(pal.deck, 0.8), 0.14)
    else:
        y = -half_w + 1.1
        row = 0
        while y < half_w:
            layer.line((stern, y), (bow, y), pal.plank, 0.1)
            x = stern + (row % 3) * 2.3
            while x < bow:
                layer.line((x, y), (x, y + 1.1), pal.plank, 0.08)
                x += 7
            y += 1.1
            row += 1
    mask = pygame.Surface(layer.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), [cv.p(x, y) for x, y in deck])
    layer.surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    cv.surf.blit(layer.surf, (0, 0))
    cv.poly(deck, shade(pal.deck, 0.65), width=0.25)
    if not small:
        rail = _scaled(pts, 0.86, 0.72)
        cv.poly(rail, shade(pal.superstructure, 0.85), width=0.1)
        for i in range(0, len(rail)):
            cv.circle(*rail[i], 0.16, shade(pal.superstructure, 0.9))

    # --- полоса стороны, пиратские заплаты и таран
    if not small:
        x0 = bow * 0.62
        hb = half_width(hull_key, x0) * 0.78
        band = [(x0, -hb * 0.95), (x0 + 2.2, -hb * 0.7), (x0 + 2.2, hb * 0.7), (x0, hb * 0.95)]
        cv.poly(band, pal.accent)
    if pirate and not small:
        for _ in range(9):
            x = rng.uniform(stern * 0.8, bow * 0.6)
            yy = rng.choice((-1, 1)) * rng.uniform(0.3, 0.8) * half_width(hull_key, x)
            col = mix(pal.deck, (140, 70, 40), rng.uniform(0.2, 0.7))
            cv.rect(x, yy, rng.uniform(1.5, 3.5), rng.uniform(1, 2.5), col, radius=0.1)
            cv.rect(x, yy, rng.uniform(1.5, 3.5), rng.uniform(1, 2.5), shade(col, 0.6), width=0.08, radius=0.1)
        for _ in range(7):
            x = rng.uniform(stern * 0.8, bow * 0.7)
            side = rng.choice((-1, 1))
            h = half_width(hull_key, x)
            cv.line((x, side * h * 0.95), (x - rng.uniform(0.5, 2), side * h * 0.7), (130, 66, 36), 0.25)
        cv.poly([(bow - 1, -1.8), (bow + 3.5, 0), (bow - 1, 1.8)], (120, 110, 100))           # таран
        cv.poly([(bow - 1, -1.8), (bow + 3.5, 0), (bow - 1, 1.8)], (60, 54, 50), width=0.15)
        for i in range(-2, 3):                                                               # «зубы»
            cv.poly([(x0 + 2.2, i * 1.6 - 0.6), (x0 + 3.6, i * 1.6), (x0 + 2.2, i * 1.6 + 0.6)], pal.accent)

    # --- люки
    for hx, hy, lx, ly in HATCHES.get(hull_key, []):
        cv.rect(hx, hy, lx, ly, shade(pal.deck, 0.62), radius=0.4)
        cv.rect(hx, hy, lx, ly, shade(pal.deck, 0.45), width=0.15, radius=0.4)
        for k in range(1, 4):
            cv.line((hx - lx / 2, hy - ly / 2 + k * ly / 4), (hx + lx / 2, hy - ly / 2 + k * ly / 4),
                    shade(pal.deck, 0.5), 0.15)

    # --- носовая аппаратура: индустриальные корпуса вместо якорной цепи
    if industrial:
        tx = bow * 0.74
        cv.rect(tx, 0, 4.5, 3.0, shade(pal.superstructure, 0.62), radius=0.25)
        cv.line((tx - 1.4, -0.85), (tx + 1.4, -0.85), pal.accent, 0.22)
        for side in (-1, 1):
            py = side * half_width(hull_key, stern * 0.52) * 0.58
            for ix in range(3):
                x = stern * 0.53 + ix * 2.0
                cv.line((x, py - 0.6), (x + 0.5, py + 0.6),
                        shade(pal.trim, 1.6), 0.28)
    elif not small:
        wx = bow * 0.74
        cv.rect(wx, 0, 1.4, 2.6, shade(pal.trim, 1.3), radius=0.2)
        for side in (-1, 1):
            cv.circle(wx, side * 0.9, 0.45, shade(pal.trim, 0.9))
            hx = bow * 0.84
            hy = side * half_width(hull_key, hx) * 0.75
            for k in range(6):                                                    # звенья цепи
                t = k / 5
                cv.circle(wx + (hx - wx) * t, side * 0.9 + (hy - side * 0.9) * t, 0.14, (40, 40, 44))
            ay = side * (half_width(hull_key, hx) + 0.4)
            cv.line((hx - 0.8, ay), (hx + 0.8, ay), (46, 46, 50), 0.25)          # якорь
            cv.line((hx, ay), (hx, ay + side * 0.9), (46, 46, 50), 0.2)

    # --- характерные функциональные элементы для нового поколения корпусов
    if industrial and HULLS[hull_key].visual is not None:
        _industrial_details(cv, HULLS[hull_key].visual, pal)

    # --- основания башен
    for slot in HULLS[hull_key].slots:
        if slot.category != "weapon":
            continue
        r = 4.3 if slot.size > 1 else 3.1
        cv.circle(*slot.pos, r, shade(pal.deck, 0.55))
        cv.circle(*slot.pos, r, shade(pal.trim, 1.2), width=0.18)
        cv.circle(*slot.pos, r * 0.75, shade(pal.deck, 0.42))

    # --- вентиляторы и кнехты
    if not small:
        for fx_, fy_ in ((bow * 0.45, 0.5), (bow * 0.45, -0.5), (stern * 0.35, 0.55), (stern * 0.35, -0.55),
                         (stern * 0.78, 0.45), (stern * 0.78, -0.45), (bow * 0.2, 0.6), (bow * 0.2, -0.6)):
            vy = fy_ * half_width(hull_key, fx_)
            if not _blocked(hull_key, fx_, vy):
                cv.circle(fx_, vy, 0.7, shade(pal.superstructure, 0.8))
                cv.circle(fx_, vy, 0.35, (26, 26, 30))
        for bx in (bow * 0.35, stern * 0.55, stern * 0.85):
            for side in (-1, 1):
                by = side * half_width(hull_key, bx) * 0.7
                cv.circle(bx, by, 0.3, shade(pal.trim, 1.6))
                cv.circle(bx + 0.8, by, 0.3, shade(pal.trim, 1.6))

    if not industrial:
        _static_modules(cv, hull_key, pal,
                        tuple((m.key, m) for _, m in installations), bow, stern, half_w)

    # --- надстройки: тень, корпус, крыша с оборудованием, крылья мостика, окна
    for sx, sy, lx, ly, windows in superstructures(hull_key):
        cv.rect(sx + 0.6, sy + 0.8, lx, ly, (0, 0, 0, 90), radius=0.8)
        if windows and not small:
            cv.rect(sx + lx / 2 - 1, sy, 2, ly + 2.4, pal.superstructure, radius=0.3)          # крылья мостика
        cv.rect(sx, sy, lx, ly, pal.superstructure, radius=0.8)
        cv.rect(sx - 0.3, sy - 0.3, lx - 1.4, ly - 1.4, pal.roof, radius=0.6)
        cv.rect(sx - 0.3, sy - 0.3, lx - 1.4, ly - 1.4, shade(pal.roof, 0.75), width=0.12, radius=0.6)
        if not small and lx > 5:
            cv.rect(sx - lx * 0.2, sy - ly * 0.2, 1.4, 1.1, shade(pal.roof, 0.7), radius=0.1)     # кондиционер
            cv.rect(sx - lx * 0.2, sy + ly * 0.2, 1.0, 1.0, shade(pal.roof, 1.2), radius=0.1)
            cv.line((sx - lx * 0.35, sy + ly * 0.3), (sx - lx * 0.35 - 1.8, sy + ly * 0.3), (40, 40, 44), 0.1)
        if windows:
            n = max(2, int(ly / 1.3))
            for k in range(n):
                wy = sy - ly / 2 + (k + 0.5) * ly / n
                cv.rect(sx + lx / 2 - 0.45, wy, 0.6, ly / n * 0.62, pal.window, radius=0.1)
            for side in (-1, 1):
                for k in range(max(1, int(lx / 2.2))):
                    cv.rect(sx - lx / 2 + 1 + k * 2.2, sy + side * (ly / 2 - 0.35), 0.8, 0.35,
                            shade(pal.window, 0.75), radius=0.05)
    if industrial:
        _industrial_fit_modules(cv, hull_key, pal, installations)

    for fx_, fy_, r in FUNNELS.get(hull_key, []):
        cv.circle(fx_ + 0.5, fy_ + 0.6, r, (0, 0, 0, 80))
        cv.circle(fx_, fy_, r, shade(pal.trim, 0.9))
        cv.circle(fx_, fy_, r, pal.accent, width=0.3)
        cv.circle(fx_, fy_, r * 0.65, (18, 18, 20))
        for k in (-1, 0, 1):
            cv.line((fx_ - r * 0.5, fy_ + k * r * 0.25), (fx_ + r * 0.5, fy_ + k * r * 0.25), (46, 46, 48), 0.1)
    for lx, ly in LIFEBOATS.get(hull_key, []):
        for side in (-1, 1):
            by = side * (half_width(hull_key, lx) * 0.78 - 0.9)
            for dx in (-1.4, 1.4):
                cv.line((lx + dx, by), (lx + dx, by - side * 1.2), (60, 60, 64), 0.15)          # шлюпбалки
            cv.rect(lx, by, 4, 1.4, (215, 120, 60), radius=0.7)
            cv.line((lx - 1.6, by), (lx + 1.6, by), (240, 170, 110), 0.12)

    # --- мачта и сенсоры (на новой серии без парусного такелажа)
    mx, my = mast_position(hull_key)
    if not small and not industrial:
        yard = half_width(hull_key, mx) * 0.55
        rig = shade(pal.deck, 0.55)
        for tx_, ty_ in ((bow - 1, 0), (stern + 1, 0), (mx, -half_width(hull_key, mx) * 0.9),
                         (mx, half_width(hull_key, mx) * 0.9)):
            cv.line((mx, my), (tx_, ty_), rig, 0.07)
        cv.line((mx, -yard), (mx, yard), shade(pal.trim, 1.1), 0.22)
    if industrial:
        cv.line((mx - 3, my), (mx + 3, my), shade(pal.trim, 1.4), 0.35)
        cv.circle(mx, my, 1.3, shade(pal.superstructure, 0.68))
        cv.circle(mx, my, 0.65, pal.accent)
    else:
        cv.circle(mx, my, 0.9, shade(pal.trim, 1.2))

    # --- грязь и износ
    for _ in range(8 if industrial else 25 if not small else 5):
        x = rng.uniform(stern * 0.9, bow * 0.8)
        yy = rng.uniform(-1, 1) * half_width(hull_key, x) * 0.8
        r = rng.uniform(0.3, 1.1)
        cv.circle(x, yy, r, (20, 18, 16, rng.randint(18, 40)))

    _damage(cv, hull_key, damage_level, pts, half_w, bow, stern)

    shadow = pygame.Surface(cv.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(shadow, (0, 0, 0, 120), [cv.p(x, y) for x, y in pts])
    small_s = pygame.transform.smoothscale(shadow, (shadow.get_width() // 6, shadow.get_height() // 6))
    shadow = pygame.transform.smoothscale(small_s, shadow.get_size())
    return cv.surf, shadow


def _static_modules(cv, hull_key, pal, static_modules, bow, stern, half_w):
    for key, m in static_modules:
        cat = m.category
        if cat == "armor":
            # бронеплиты вдоль бортов
            th = 0.9 if m.size > 1 else 0.55
            for side in (-1, 1):
                x = stern * 0.8
                while x < bow * 0.55:
                    local_width = (half_width(hull_key, x + 1.4)
                                   if HULLS[hull_key].visual is not None else half_w)
                    if local_width > 0.8:
                        cv.rect(x + 1.4, side * (local_width * 0.85), 2.6, th,
                                pal.armor, radius=0.15)
                    x += 3.2
        elif cat == "engine":
            n = 1 if m.size == 1 else 2
            for k in range(n):
                off = 0 if n == 1 else (-2.2 if k == 0 else 2.2)
                cv.rect(stern + 0.4, off, 1.6, 1.8, (26, 26, 28), radius=0.4)
        elif cat == "utility":
            if m.effect == "drill":
                cv.poly([(bow - 0.5, -1.6), (bow + 5.5, 0), (bow - 0.5, 1.6)], (150, 140, 118))
                for k in range(3):
                    cv.line((bow + k * 1.6, -1.2 + k * 0.35), (bow + k * 1.6 + 0.8, 1.2 - k * 0.35),
                            (100, 92, 76), 0.2)
            elif m.effect == "collector":
                for side in (-1, 1):
                    cv.circle(bow * 0.15, side * half_w * 0.62, 1.4, (60, 40, 90))
                    cv.circle(bow * 0.15, side * half_w * 0.62, 1.4, (170, 110, 230), width=0.3)
            elif m.effect == "cargo":
                for k, col in enumerate(((160, 90, 60), (70, 110, 150), (140, 130, 70))):
                    cv.rect(stern * 0.55 + k * 2.4, 0, 2, half_w * 1.1, col, radius=0.2)
            elif m.effect in ("repair", "damage_control"):
                cv.rect(stern * 0.35, half_w * 0.5, 1.6, 1.6, (200, 60, 60), radius=0.3)
            elif m.effect == "smoke":
                cv.circle(stern * 0.8, -half_w * 0.5, 0.9, (90, 90, 92))
            elif m.effect in ("ecm", "bioscreen"):
                col = (120, 200, 255) if m.effect == "ecm" else (90, 220, 190)
                cv.circle(stern * 0.3, -half_w * 0.45, 1.0, col, width=0.3)


def _damage(cv, hull_key, level, pts, half_w, bow, stern):
    if level <= 0:
        return
    rng = random.Random(hash(hull_key) & 0xffff)
    for _ in range(4 * level):
        x = rng.uniform(stern * 0.8, bow * 0.7)
        y = rng.uniform(-half_w * 0.8, half_w * 0.8)
        r = rng.uniform(0.8, 1.8)
        s = pygame.Surface((int(r * 2 * R), int(r * 2 * R)), pygame.SRCALPHA)
        pygame.draw.circle(s, (12, 10, 10, 150), (r * R, r * R), r * R)
        px, py = cv.p(x, y)
        cv.surf.blit(s, (px - r * R, py - r * R))
    if level >= 2:
        for _ in range(3):
            x = rng.uniform(stern * 0.6, bow * 0.5)
            y = rng.uniform(-half_w * 0.6, half_w * 0.6)
            cv.line((x, y), (x + rng.uniform(-3, 3), y + rng.uniform(-2, 2)), (20, 16, 14), 0.3)


# --- турели ------------------------------------------------------------------

def build_turret(module_key, pal_key, industrial=False):
    """Башня/установка: ствол вдоль +X. Единый материал с корпусом R1.1."""
    pal = industrial_palette(pal_key) if industrial else SHIP_PALETTES[pal_key]
    cv = _Canvas(10)
    body, dark = pal.turret, shade(pal.turret, 0.5)
    light = shade(pal.turret, 1.3)
    edge = shade(pal.turret, 0.7)
    if module_key == "autocannon_s":
        cv.rect(4.2, 0, 7.4, 1.0, dark, radius=0.3)
        cv.rect(7.9, 0, 1.4, 1.5, shade(dark, 0.8), radius=0.2)                 # дульный тормоз
        cv.rect(2.2, 0, 1.6, 1.5, edge, radius=0.2)                              # кожух
        cv.circle(0, 0, 2.7, edge)
        cv.circle(0, 0, 2.4, body)
        cv.circle(-0.6, -0.7, 0.9, light)                                        # люк
        cv.circle(-0.9, 1.0, 0.35, dark)
    elif module_key == "scatter_s":
        for a in (-14, 0, 14):
            d = Vector2(1, 0).rotate(a)
            cv.line((d.x * 1.4, d.y * 1.4), (d.x * 5.6, d.y * 5.6), dark, 1.0)
            cv.circle(d.x * 5.6, d.y * 5.6, 0.55, shade(dark, 0.8))
        cv.circle(0, 0, 3.0, edge)
        cv.circle(0, 0, 2.7, body)
        cv.rect(-0.8, 0, 2.2, 3.2, light, radius=0.6)
    elif module_key == "cannon_m":
        for y in (-1.15, 1.15):
            cv.rect(6.6, y, 9.6, 1.05, dark, radius=0.3)
            cv.rect(11.0, y, 1.2, 1.4, shade(dark, 0.8), radius=0.2)             # дульные тормоза
            cv.rect(3.6, y, 1.8, 1.5, edge, radius=0.3)                          # маски стволов
        cv.rect(-0.2, 0, 8.4, 7.6, edge, radius=2.4)
        cv.rect(-0.2, 0, 7.8, 7.0, body, radius=2.2)
        cv.rect(-0.9, -0.7, 4.6, 4.0, light, radius=1.3)
        cv.rect(-3.0, 0, 1.4, 5.8, shade(body, 0.8), radius=0.4)                 # задняя ниша
        for side in (-1, 1):
            cv.rect(-0.5, side * 4.2, 1.8, 0.9, edge, radius=0.3)               # «уши» дальномера
        cv.circle(0.6, -1.9, 0.55, dark)                                         # командирский люк
        cv.circle(0.6, 1.9, 0.45, dark)
    elif module_key == "em_m":
        cv.rect(5.2, 0, 7.4, 1.8, dark, radius=0.6)
        for k in range(4):
            cv.circle(2.8 + k * 1.8, 0, 1.35, (90, 150, 210), width=0.3)
        cv.circle(9.2, 0, 1.1, (170, 225, 255))
        cv.circle(0, 0, 3.6, edge)
        cv.circle(0, 0, 3.3, body)
        cv.circle(-0.6, -0.6, 1.5, (110, 170, 225))
        cv.circle(-0.6, -0.6, 0.7, (200, 235, 255))
    elif module_key in ("missile_s", "missile_m"):
        n = 2 if module_key == "missile_s" else 3
        size = 5.6 if n == 2 else 7.8
        cv.rect(0.3, 0.3, size, size, (0, 0, 0, 90), radius=0.8)
        cv.rect(0, 0, size, size, edge, radius=0.8)
        cv.rect(0, 0, size - 0.5, size - 0.5, body, radius=0.7)
        cv.rect(-0.4, -0.4, size - 1.8, size - 1.8, light, radius=0.5)
        step = size / n
        for i in range(n):
            for j in range(n):
                cx, cy = -size / 2 + step * (i + 0.5), -size / 2 + step * (j + 0.5)
                cv.circle(cx, cy, step * 0.34, (28, 28, 32))
                cv.circle(cx, cy, step * 0.18, (200, 70, 50))                    # головки ракет
    elif module_key == "torpedo_m":
        cv.rect(0.4, 0.4, 11.5, 3.4, (0, 0, 0, 90), radius=1.6)
        cv.rect(0, 0, 11.5, 3.4, edge, radius=1.6)
        cv.rect(0, 0, 11, 2.9, body, radius=1.4)
        cv.rect(-0.3, -0.5, 9.5, 1.1, light, radius=0.5)
        for k in (-3, 0, 3):
            cv.line((k, -1.45), (k, 1.45), dark, 0.18)                           # бандажи
        cv.circle(5.4, 0, 1.2, (18, 22, 28))
    else:
        cv.circle(0, 0, 2.5, body)
    return cv.surf



def draw_compact_hull(screen, cam, ship, pal_key, tier="tactical"):
    """Far/tactical vector LODs selected by screen-space silhouette length."""
    pal = industrial_palette(pal_key)
    geom = outline(ship.hull.key)
    pts = [cam.w2s(ship.pos + Vector2(x, y).rotate(ship.angle)) for x, y in geom]
    if len(pts) < 3:
        return
    pygame.draw.polygon(screen, pal.trim, pts)
    inner = [cam.w2s(ship.pos + Vector2(x * 0.96, y * 0.92).rotate(ship.angle))
             for x, y in geom]
    pygame.draw.polygon(screen, pal.hull, inner)
    pygame.draw.aalines(screen, shade(pal.superstructure, 0.87), True, pts)

    bow, stern = PROFILES[ship.hull.key][0][0], PROFILES[ship.hull.key][-1][0]
    forward = Vector2(1, 0).rotate(ship.angle)
    tip = cam.w2s(ship.pos + forward * (bow * 0.8))
    if tier == "far":
        # No turret clutter on silhouettes under 24 pixels.
        pygame.draw.circle(screen, pal.accent, tip, 1)
        return

    # Primary raised deck, with real outline-dependent side shoulders.
    def point(x, y):
        return cam.w2s(ship.pos + Vector2(x, y).rotate(ship.angle))

    pygame.draw.line(screen, shade(pal.deck, 1.1),
                     point(stern * 0.56, 0), point(bow * 0.62, 0), 2)
    for x, y, length, width, _ in superstructures(ship.hull.key):
        corners = ((x - length * 0.5, y - width * 0.5),
                   (x + length * 0.5, y - width * 0.5),
                   (x + length * 0.5, y + width * 0.5),
                   (x - length * 0.5, y + width * 0.5))
        pygame.draw.polygon(screen, pal.superstructure,
                            [point(px, py) for px, py in corners])
    # A few identity-bearing side elements remain at tactical zoom.
    if ship.hull.key == "needle":
        for side in (-1, 1):
            pygame.draw.line(screen, pal.armor, point(-12, side * 3.6),
                             point(7, side * 3.6), 1)
    elif ship.hull.key == "manta":
        for side in (-1, 1):
            pygame.draw.line(screen, shade(pal.armor, 1.18),
                             point(-22, side * 9.4), point(5, side * 11.6), 2)
    elif ship.hull.key == "bastion":
        for side in (-1, 1):
            pygame.draw.line(screen, shade(pal.armor, 1.15),
                             point(-23, side * 10), point(18, side * 9.2), 3)
    pygame.draw.circle(screen, pal.accent, tip, 2)
    # At tactical size weapon stations are functional silhouettes, not
    # detailed rotating sprite images. Far LOD omits them entirely.
    for weapon in ship.weapons:
        pos = cam.w2s(weapon.world_pos(ship))
        radius = 3 if weapon.defn.size > 1 else 2
        kind = weapon.defn.kind
        pygame.draw.circle(screen, shade(pal.trim, 1.4), pos, radius + 1)
        if kind == "missile":
            pygame.draw.rect(screen, pal.turret,
                             (round(pos.x - radius), round(pos.y - radius),
                              radius * 2, radius * 2))
            pygame.draw.circle(screen, rgb("signal_amber"), pos, 1)
        elif kind == "torpedo":
            direction = Vector2(1, 0).rotate(ship.angle + weapon.slot.facing)
            pygame.draw.line(screen, pal.turret, pos - direction * radius,
                             pos + direction * (radius + 2), 3)
        else:
            pygame.draw.circle(screen, pal.turret, pos, radius)
            direction = Vector2(1, 0).rotate(ship.angle + weapon.slot.facing)
            pygame.draw.line(screen, pal.roof, pos,
                             pos + direction * (radius + 2), 1)
    if ship.hp < ship.hull.hp * 0.35:
        pygame.draw.circle(screen, rgb("signal_amber"), cam.w2s(ship.pos), 2)

# --- кэш и отрисовка ------------------------------------------------------

class ShipArt:
    def __init__(self):
        self.masters = {}
        self.turrets = {}
        self.cache = OrderedDict()

    def _rotated(self, key, master, angle, zoom):
        ab = round(angle / ANGLE_STEP) * ANGLE_STEP
        zb = max(ZOOM_STEP, round(zoom / ZOOM_STEP) * ZOOM_STEP)
        ck = (key, ab % 360, zb)
        img = self.cache.get(ck)
        if img is None:
            img = pygame.transform.rotozoom(master, -ab, zb / R)
            self.cache[ck] = img
            if len(self.cache) > CACHE_LIMIT:
                self.cache.popitem(last=False)
        else:
            self.cache.move_to_end(ck)
        return img

    def _hull_master(self, ship, pal_key):
        static = tuple((i, m) for i, _, m in ship.modules() if m.category != "weapon")
        dmg = 0 if ship.hp > ship.hull.hp * 0.6 else 1 if ship.hp > ship.hull.hp * 0.3 else 2
        key = (ship.hull.key, pal_key, tuple((i, m.key) for i, m in static), dmg)
        m = self.masters.get(key)
        if m is None:
            m = self.masters[key] = build_hull(ship.hull.key, pal_key, static, dmg)
        return key, m

    def wreck_pieces(self, ship, pal_key):
        """Две половины разбитого корпуса (нос и корма) — мастер-спрайты того же размера."""
        static = tuple((i, m) for i, _, m in ship.modules() if m.category != "weapon")
        hull_img, _ = build_hull(ship.hull.key, pal_key, static, 2)
        w, h = hull_img.get_size()
        cut = w // 2 + int(R * 2)
        bow = hull_img.copy()
        bow.fill((0, 0, 0, 0), (0, 0, cut, h))
        stern = hull_img.copy()
        stern.fill((0, 0, 0, 0), (cut, 0, w - cut, h))
        for piece in (bow, stern):                    # тёмный рваный край
            piece.fill((150, 140, 140, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return bow, stern

    def rotated(self, key, master, angle, zoom):
        return self._rotated(key, master, angle, zoom)

    def draw(self, screen, cam, ship, pal_key, t=0.0, alpha=255, shadow=Vector2(3, 4)):
        """shadow — смещение тени в пикселях (по солнцу); None — без тени (ночь)."""
        if ship.hull.visual_style == "industrial_sci_fi" and alpha == 255:
            tier = lod_for_length(hull_length(ship.hull.key) * cam.zoom)
            if tier != "inspection":
                draw_compact_hull(screen, cam, ship, pal_key, tier=tier)
                return
        key, (hull_img, shadow_img) = self._hull_master(ship, pal_key)
        center = cam.w2s(ship.pos)
        if shadow is not None:
            sh = self._rotated(("shadow",) + key, shadow_img, ship.angle, cam.zoom)
            screen.blit(sh, sh.get_rect(center=center + shadow))
        img = self._rotated(key, hull_img, ship.angle, cam.zoom)
        if ship.water > 0.05 or alpha < 255:
            img = img.copy()
            if ship.water > 0.05:
                k = int(255 * (1 - 0.45 * ship.water))
                img.fill((k, k, min(255, k + 20), 255), special_flags=pygame.BLEND_RGBA_MULT)
            if alpha < 255:
                img.set_alpha(alpha)
        screen.blit(img, img.get_rect(center=center))

        for w in ship.weapons:
            tk = (w.defn.key, pal_key, ship.hull.visual_style == "industrial_sci_fi")
            master = self.turrets.get(tk)
            if master is None:
                master = self.turrets[tk] = build_turret(*tk)
            ang = w.world_angle(ship) if w.defn.kind == "gun" else ship.angle + w.slot.facing
            timg = self._rotated(("t",) + tk, master, ang, cam.zoom)
            if alpha < 255:
                timg = timg.copy()
                timg.set_alpha(alpha)
            pos = cam.w2s(w.world_pos(ship))
            if w.defn.kind == "gun" and w.defn.reload > 0:
                # откат: сразу после выстрела установка «отскакивает» назад
                k = w.reload / (w.defn.reload * ship.reload_mult())
                kick = max(0.0, (k - 0.7) / 0.3)
                if kick > 0:
                    pos = pos - Vector2(1, 0).rotate(ang) * cam.px(kick * (1.4 if w.defn.size > 1 else 0.7))
            screen.blit(timg, timg.get_rect(center=pos))
            if w.overheated or w.heat > 70:
                glow = min(1.0, w.heat / 100)
                pygame.draw.circle(screen, mix((120, 40, 20), (255, 120, 40), glow), cam.w2s(w.world_pos(ship)),
                                   max(1, int(cam.px(1.2))))

        # вращающаяся антенна радара
        if ship.sensor and (ship.hull.visual is not None or ship.hull.key in MAST):
            mx, my = mast_position(ship.hull.key)
            base = cam.w2s(ship.pos + Vector2(mx, my).rotate(ship.angle))
            if ship.sensor.veil_resist:
                pygame.draw.circle(screen, (110, 180, 190), base, max(2, int(cam.px(2.0))), 1)
            else:
                d = Vector2(1, 0).rotate(t * 220) * cam.px(2.6)
                pygame.draw.line(screen, (170, 200, 205), base - d, base + d, max(1, int(cam.px(0.6))))


NAV_RED, NAV_GREEN, NAV_WHITE = (255, 60, 50), (60, 255, 120), (255, 245, 220)


def nav_lights(ship):
    """Ходовые огни: красный — левый борт, зелёный — правый, белый — топовый и кормовой."""
    key = ship.hull.key
    prof = PROFILES[key]
    half = max(y for _, y in prof)
    mid = next((x for x, y in prof if y >= half * 0.95), 0)
    stern = prof[-1][0]
    mx, my = mast_position(key)
    pts = [((mid, -half), NAV_RED), ((mid, half), NAV_GREEN), ((stern, 0), NAV_WHITE), ((mx, my), NAV_WHITE)]
    return [(ship.pos + Vector2(x, y).rotate(ship.angle), col) for (x, y), col in pts]


def window_lights(ship):
    """Центры освещённых окон надстроек (для света ночью)."""
    out = []
    for sx, sy, lx, ly, windows in superstructures(ship.hull.key):
        if windows:
            out.append(ship.pos + Vector2(sx + lx / 2, sy).rotate(ship.angle))
    return out


def hull_length(hull_key):
    xs = [x for x, _ in PROFILES[hull_key]]
    return max(xs) - min(xs)


def stern_points(ship):
    """Точки у кормы в мире — для кильватерного следа."""
    stern = PROFILES[ship.hull.key][-1][0]
    w = max(y for _, y in PROFILES[ship.hull.key]) * 0.6
    return [ship.pos + Vector2(stern, s * w).rotate(ship.angle) for s in (-1, 1)]


def bow_point(ship):
    return ship.pos + Vector2(PROFILES[ship.hull.key][0][0], 0).rotate(ship.angle)


def hull_radius_px(ship, cam):
    return cam.px(ship.radius)


__all__ = ["ShipArt", "outline", "stern_points", "bow_point", "hull_length", "math"]
