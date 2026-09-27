"""Глобальные константы прототипа. Всё, что хочется крутить при балансе, — здесь."""

SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

# Мир — квадрат в мировых единицах (1 ед. ~ 1 м)
WORLD_W, WORLD_H = 8000, 8000

# Порт беженцев — нейтральный хаб, стартовая точка
PORT_POS = (1200.0, 6800.0)
PORT_RADIUS = 170.0
DOCK_MAX_SPEED = 60.0

# Око Девятки — центр Пелены
EYE_POS = (6400.0, 1600.0)
EYE_CALM_R = 230.0     # Око / Зеркало — штиль внутри бури
EYE_WALL_R = 720.0     # Стена Рёва
EYE_BELT_R = 1700.0    # Пояс Разлома
VEIL_REACH = 6800.0    # на этом расстоянии от Ока базовая плотность падает до нуля

# Сетка предрасчёта плотности (ед. на ячейку)
VEIL_CELL = 50

# Пороги зон по плотности
ZONE_MIST = 0.30
ZONE_DENSE = 0.60

# Сенсоры
VISUAL_RANGE = 420.0          # «глазами», без электроники
RADAR_BASE = 950.0
RADAR_PER_LEVEL = 220.0
RADAR_DENSITY_PENALTY = 0.75  # доля дальности, съедаемая плотной Пеленой

# Налёт филаментов: быстрый ход в Пелене полимеризует её на корпусе
FOUL_SPEED_FRACTION = 0.75    # от базовой макс. скорости
FOUL_MIN_DENSITY = 0.30
FOUL_RATE = 0.05
FOUL_DECAY = 0.012

# Экономика
START_CREDITS = 300
INSURANCE_RATE = 0.4
CAPSULE_DEBT = 400
TRAUMA_RELOAD_MULT = 1.15
TRAUMA_RADAR_MULT = 0.8
MEDICAL_COST = 150
REPAIR_COST_PER_HP = 1.5
CLEAN_COST = 60
