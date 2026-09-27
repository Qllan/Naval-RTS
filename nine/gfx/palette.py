"""Цвета. Тёмный приглушённый океан + акцентные цвета сторон/фракций (GDD §12)."""

from dataclasses import dataclass


def mix(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def shade(c, k):
    return tuple(max(0, min(255, int(x * k))) for x in c)


@dataclass(frozen=True)
class ShipPalette:
    hull: tuple
    deck: tuple
    plank: tuple
    trim: tuple
    superstructure: tuple
    roof: tuple
    window: tuple
    accent: tuple
    turret: tuple
    armor: tuple


SHIP_PALETTES = {
    # Игрок: сталь, бирюзовый акцент
    "player": ShipPalette(hull=(52, 62, 74), deck=(88, 96, 102), plank=(74, 82, 88), trim=(30, 36, 44),
                          superstructure=(150, 158, 164), roof=(118, 126, 134), window=(250, 226, 150),
                          accent=(70, 205, 190), turret=(112, 120, 128), armor=(128, 120, 98)),
    # Ржавый Прилив: ржавчина, красно-ржавые акценты
    "pirate": ShipPalette(hull=(72, 46, 38), deck=(98, 74, 58), plank=(84, 62, 48), trim=(40, 26, 22),
                          superstructure=(138, 108, 88), roof=(112, 84, 66), window=(255, 170, 90),
                          accent=(214, 72, 46), turret=(104, 82, 70), armor=(120, 96, 70)),
    # Спасательная капсула
    "capsule": ShipPalette(hull=(200, 110, 40), deck=(230, 150, 70), plank=(210, 130, 60), trim=(90, 50, 20),
                           superstructure=(240, 200, 150), roof=(220, 170, 110), window=(255, 240, 200),
                           accent=(255, 230, 180), turret=(0, 0, 0), armor=(0, 0, 0)),
}

# Океан
OCEAN_DEEP = (5, 11, 20)
OCEAN_MID = (9, 20, 33)
OCEAN_LIGHT = (16, 33, 50)
FOAM = (170, 195, 210)
GLINT = (110, 150, 175)

# Пелена
VEIL_TINT = (84, 44, 128)
VEIL_WISP = (150, 96, 210)
SURGE = (190, 90, 255)

# Эффекты
MUZZLE = (255, 226, 160)
TRACER_PLAYER = (255, 232, 150)
TRACER_PIRATE = (255, 140, 80)
TRACER_EM = (140, 200, 255)
SHIELD_HIT = (110, 190, 255)
SPARK = (255, 200, 120)
FIRE = (255, 130, 40)
SMOKE = (70, 72, 76)
