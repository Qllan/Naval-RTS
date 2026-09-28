"""Настройки игрока: хранятся отдельно от прогресса, в ~/.nine/settings.json.

Каталог можно переопределить переменной окружения NINE_HOME (так делают тесты).
"""

import json
import os
from dataclasses import asdict, dataclass, field

import pygame

# Действия, которые можно переназначить: (ключ, подпись, клавиша по умолчанию)
ACTIONS = (
    ("forward", "Ход вперёд", "w"),
    ("back", "Ход назад", "s"),
    ("left", "Руль влево", "a"),
    ("right", "Руль вправо", "d"),
    ("boost", "Форсаж", "left shift"),
    ("fire", "Огонь (группа 1)", "space"),
    ("mine", "Добыча", "e"),
    ("dock", "Войти в порт", "f"),
    ("spotlight", "Прожектор", "l"),
    ("ammo", "Тип снарядов", "t"),
    ("pip_shields", "Энергия в щиты", "z"),
    ("pip_engines", "Энергия в двигатель", "x"),
    ("pip_weapons", "Энергия в орудия", "c"),
    ("pip_reset", "Энергия поровну", "v"),
    ("util1", "Модуль 1", "1"),
    ("util2", "Модуль 2", "2"),
    ("util3", "Модуль 3", "3"),
    ("util4", "Модуль 4", "4"),
    ("map", "Карта", "m"),
    ("codex", "Кодекс", "k"),
    ("help", "Справка", "h"),
)
ACTION_NAME = {k: name for k, name, _ in ACTIONS}


def default_keys():
    return {k: key for k, _, key in ACTIONS}


def settings_dir():
    return os.environ.get("NINE_HOME") or os.path.join(os.path.expanduser("~"), ".nine")


@dataclass
class Settings:
    # звук
    master: float = 0.8
    sfx: float = 1.0
    ambient: float = 0.8
    ui: float = 0.7
    # графика
    high_quality: bool = True
    distortion: bool = True
    shake: float = 1.0
    show_fps: bool = False
    # интерфейс
    hud_opacity: float = 0.8
    large_font: bool = False
    colorblind: bool = False
    damage_numbers: bool = True
    hints: bool = True
    show_minimap: bool = True
    show_log: bool = True
    keys: dict = field(default_factory=default_keys)
    seen_tips: list = field(default_factory=list)

    # --- клавиши --------------------------------------------------------------

    def key(self, action):
        """Код клавиши pygame для действия."""
        name = self.keys.get(action) or default_keys()[action]
        try:
            return pygame.key.key_code(name)
        except ValueError:
            return pygame.key.key_code(default_keys()[action])

    def bind(self, action, code):
        """Назначает клавишу; если она была у другого действия — меняет их местами."""
        name = pygame.key.name(code)
        old = self.keys.get(action)
        for other, v in self.keys.items():
            if v == name and other != action:
                self.keys[other] = old
        self.keys[action] = name

    def key_label(self, action):
        return self.keys.get(action, "?").upper()

    # --- файл -----------------------------------------------------------------

    @classmethod
    def load(cls):
        path = os.path.join(settings_dir(), "settings.json")
        s = cls()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return s
        for k, v in data.items():
            if k == "seen_tips" and isinstance(v, list):
                s.seen_tips = [x for x in v if isinstance(x, str)]
                continue
            if k == "keys" and isinstance(v, dict):
                s.keys.update({a: n for a, n in v.items() if a in s.keys and isinstance(n, str)})
                continue
            cur = getattr(s, k, None)
            if isinstance(cur, bool):
                if isinstance(v, bool):
                    setattr(s, k, v)
            elif isinstance(cur, float) and isinstance(v, (int, float)) and not isinstance(v, bool):
                setattr(s, k, max(0.0, min(1.5, float(v))))
        return s

    def save(self):
        d = settings_dir()
        try:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=1)
        except OSError:
            pass
