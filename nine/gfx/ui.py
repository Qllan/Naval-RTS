"""UI-кит: «тонкие линии, монохром + акцентный цвет» (GDD §12). Иконки рисуются кодом."""

import math

import pygame
from pygame.math import Vector2

TEXT = (192, 206, 212)
DIM = (100, 116, 124)
FAINT = (40, 52, 60)
LINE = (44, 62, 72)
ACCENT = (80, 205, 190)
WARN = (242, 162, 80)
BAD = (236, 86, 70)
GOOD = (120, 212, 130)
PANEL_BG = (5, 9, 14, 205)
SEL_BG = (18, 44, 52)

C_HULL = (212, 96, 76)
C_ARMOR = (190, 170, 120)
C_SHIELD = (90, 170, 240)
C_ENERGY = (236, 212, 96)
C_FOUL = (170, 100, 220)


_NORMAL = {"BAD": BAD, "GOOD": GOOD, "C_HULL": C_HULL}
_COLORBLIND = {"BAD": (240, 120, 30), "GOOD": (90, 170, 255), "C_HULL": (240, 140, 60)}


def configure(opacity=None, colorblind=None, large_font=None):
    """Настройки доступности: прозрачность панелей, палитра для дальтоников, крупный шрифт."""
    global PANEL_BG
    if opacity is not None:
        PANEL_BG = (5, 9, 14, int(80 + 175 * max(0.0, min(1.0, opacity))))
    if colorblind is not None:
        globals().update(_COLORBLIND if colorblind else _NORMAL)
    if large_font is not None and Fonts.scale != (1.15 if large_font else 1.0):
        Fonts.scale = 1.15 if large_font else 1.0
        Fonts.reset()


class Fonts:
    _cache = {}
    scale = 1.0

    @classmethod
    def reset(cls):
        """После pygame.quit()/init() старые шрифты недействительны."""
        cls._cache.clear()

    @classmethod
    def get(cls, size, bold=False):
        key = (size, bold)
        f = cls._cache.get(key)
        if f is None:
            f = pygame.font.Font(None, round(size * cls.scale))
            f.set_bold(bold)
            cls._cache[key] = f
        return f


def text(screen, s, pos, color=TEXT, size=18, bold=False, anchor="topleft"):
    img = Fonts.get(size, bold).render(str(s), True, color)
    r = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    screen.blit(img, r)
    return r


def text_width(s, size=18, bold=False):
    return Fonts.get(size, bold).size(str(s))[0]


def wrap(s, width, size=16):
    font = Fonts.get(size)
    lines, line = [], ""
    for word in str(s).split():
        test = f"{line} {word}".strip()
        if font.size(test)[0] > width and line:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    return lines


_bg_cache = {}


def panel(screen, rect, title=None, accent=ACCENT, bg=None):
    """Полупрозрачная панель с тонкой рамкой и уголками акцентного цвета."""
    rect = pygame.Rect(rect)
    bg = bg or PANEL_BG
    key = (rect.size, bg)
    surf = _bg_cache.get(key)
    if surf is None:
        surf = pygame.Surface(rect.size, pygame.SRCALPHA)
        surf.fill(bg)
        if len(_bg_cache) > 60:
            _bg_cache.clear()
        _bg_cache[key] = surf
    screen.blit(surf, rect.topleft)
    pygame.draw.rect(screen, LINE, rect, 1)
    c = 9
    for (x, y), (dx, dy) in ((rect.topleft, (1, 1)), ((rect.right - 1, rect.top), (-1, 1)),
                             ((rect.left, rect.bottom - 1), (1, -1)), ((rect.right - 1, rect.bottom - 1), (-1, -1))):
        pygame.draw.line(screen, accent, (x, y), (x + dx * c, y), 2)
        pygame.draw.line(screen, accent, (x, y), (x, y + dy * c), 2)
    if title:
        text(screen, title.upper(), (rect.x + 12, rect.y + 7), DIM, 15, bold=True)
        w = text_width(title.upper(), 15, True)
        pygame.draw.line(screen, LINE, (rect.x + 18 + w, rect.y + 13), (rect.right - 12, rect.y + 13), 1)
    return rect


def bar(screen, rect, frac, color, segments=0, back=FAINT, ghost=None):
    """Шкала. `segments` — число делений (0 — сплошная). `ghost` — недавнее значение (показ урона)."""
    rect = pygame.Rect(rect)
    frac = max(0.0, min(1.0, frac))
    if segments:
        gap = 2
        sw = (rect.w - gap * (segments - 1)) / segments
        for i in range(segments):
            x = rect.x + i * (sw + gap)
            k = min(1.0, max(0.0, frac * segments - i))
            pygame.draw.rect(screen, back, (x, rect.y, sw, rect.h))
            if ghost is not None and ghost > frac:
                gk = min(1.0, max(0.0, ghost * segments - i))
                if gk > k:
                    pygame.draw.rect(screen, (230, 230, 230), (x + sw * k, rect.y, sw * (gk - k), rect.h))
            if k > 0:
                pygame.draw.rect(screen, color, (x, rect.y, sw * k, rect.h))
    else:
        pygame.draw.rect(screen, back, rect)
        if frac > 0:
            pygame.draw.rect(screen, color, (rect.x, rect.y, rect.w * frac, rect.h))


def chip(screen, s, pos, color=TEXT, size=15, fill=None, anchor="topleft"):
    """Маленькая метка в рамке: клавиша, статус."""
    w = text_width(s, size, True) + 10
    h = size - 1
    r = pygame.Rect(0, 0, w, h)
    setattr(r, anchor, (int(pos[0]), int(pos[1])))
    if fill:
        pygame.draw.rect(screen, fill, r, border_radius=2)
    pygame.draw.rect(screen, color, r, 1, border_radius=2)
    text(screen, s, r.center, color, size, True, anchor="center")
    return r


def selection(screen, rect):
    rect = pygame.Rect(rect)
    pygame.draw.rect(screen, SEL_BG, rect)
    pygame.draw.line(screen, ACCENT, rect.topleft, rect.bottomleft, 2)


# --- иконки ---------------------------------------------------------------------

def icon(screen, kind, center, size=14, color=TEXT):
    """Простые линейные иконки. kind: gun, missile, torpedo, engine, reactor, shield, armor, sensor,
    utility, hull, cargo, credits, fire, water, rudder, weapons."""
    c = Vector2(center)
    s = size / 2
    w = max(1, size // 9)
    if kind in ("gun", "weapon", "weapons"):
        pygame.draw.circle(screen, color, c, s * 0.7, w)
        for a in (0, 90, 180, 270):
            d = Vector2(1, 0).rotate(a)
            pygame.draw.line(screen, color, c + d * s * 0.35, c + d * s, w)
    elif kind == "missile":
        pts = [c + Vector2(s, 0), c + Vector2(s * 0.3, -s * 0.3), c + Vector2(-s, -s * 0.3),
               c + Vector2(-s * 0.7, 0), c + Vector2(-s, s * 0.3), c + Vector2(s * 0.3, s * 0.3)]
        pygame.draw.polygon(screen, color, [c + (p - c).rotate(-40) for p in pts], w)
    elif kind == "torpedo":
        pygame.draw.rect(screen, color, (c.x - s, c.y - s * 0.28, s * 1.7, s * 0.56), w, border_radius=int(s * 0.3))
        pygame.draw.line(screen, color, (c.x - s, c.y - s * 0.5), (c.x - s, c.y + s * 0.5), w)
    elif kind == "engine":
        for k in (-0.45, 0.15):
            pygame.draw.lines(screen, color, False, [c + Vector2(k * s, -s * 0.7), c + Vector2((k + 0.5) * s, 0),
                                                     c + Vector2(k * s, s * 0.7)], w + 1)
    elif kind == "reactor":
        pts = [c + Vector2(s * 0.2, -s), c + Vector2(-s * 0.5, s * 0.1), c + Vector2(0, s * 0.1),
               c + Vector2(-s * 0.2, s), c + Vector2(s * 0.5, -s * 0.1), c + Vector2(0, -s * 0.1)]
        pygame.draw.polygon(screen, color, pts, w)
    elif kind == "shield":
        pts = [c + Vector2(0, -s), c + Vector2(s * 0.8, -s * 0.6), c + Vector2(s * 0.7, s * 0.2),
               c + Vector2(0, s), c + Vector2(-s * 0.7, s * 0.2), c + Vector2(-s * 0.8, -s * 0.6)]
        pygame.draw.polygon(screen, color, pts, w)
    elif kind == "armor":
        for dx, dy in ((-0.45, -0.4), (0.45, -0.4), (0, 0.4)):
            hc = c + Vector2(dx, dy) * s
            pts = [hc + Vector2(1, 0).rotate(60 * i + 30) * s * 0.45 for i in range(6)]
            pygame.draw.polygon(screen, color, pts, w)
    elif kind == "sensor":
        pygame.draw.circle(screen, color, c + Vector2(-s * 0.5, s * 0.5), max(1, s * 0.18))
        for r in (0.6, 1.1):
            rect = pygame.Rect(0, 0, s * 2 * r, s * 2 * r)
            rect.center = c + Vector2(-s * 0.5, s * 0.5)
            pygame.draw.arc(screen, color, rect, 0.1, math.pi / 2 - 0.1, w)
    elif kind == "utility":
        pygame.draw.line(screen, color, c + Vector2(-s * 0.7, s * 0.7), c + Vector2(s * 0.3, -s * 0.3), w + 1)
        pygame.draw.circle(screen, color, c + Vector2(s * 0.45, -s * 0.45), s * 0.4, w)
    elif kind == "hull":
        pts = [c + Vector2(0, -s), c + Vector2(s * 0.55, -s * 0.3), c + Vector2(s * 0.5, s),
               c + Vector2(-s * 0.5, s), c + Vector2(-s * 0.55, -s * 0.3)]
        pygame.draw.polygon(screen, color, pts, w)
    elif kind == "cargo":
        pygame.draw.rect(screen, color, (c.x - s * 0.8, c.y - s * 0.6, s * 1.6, s * 1.3), w)
        pygame.draw.line(screen, color, (c.x - s * 0.8, c.y - s * 0.1), (c.x + s * 0.8, c.y - s * 0.1), w)
    elif kind == "credits":
        pygame.draw.circle(screen, color, c, s * 0.85, w)
        text(screen, "К", c, color, int(size * 0.9), True, anchor="center")
    elif kind == "fire":
        pts = [c + Vector2(0, -s), c + Vector2(s * 0.6, 0), c + Vector2(s * 0.4, s * 0.8),
               c + Vector2(-s * 0.4, s * 0.8), c + Vector2(-s * 0.6, 0), c + Vector2(-s * 0.1, -s * 0.3)]
        pygame.draw.polygon(screen, color, pts, w)
    elif kind == "water":
        pts = [c + Vector2(0, -s)] + [c + Vector2(0, s * 0.3) + Vector2(1, 0).rotate(a) * s * 0.6
                                      for a in range(-10, 200, 30)]
        pygame.draw.polygon(screen, color, pts, w)
    elif kind == "rudder":
        pygame.draw.line(screen, color, c + Vector2(0, -s), c + Vector2(0, s * 0.3), w + 1)
        pygame.draw.polygon(screen, color, [c + Vector2(-s * 0.4, s * 0.1), c + Vector2(s * 0.4, s * 0.1),
                                            c + Vector2(0, s)], w)
    elif kind == "sun":
        pygame.draw.circle(screen, color, c, s * 0.45)
        for a in range(0, 360, 45):
            d = Vector2(1, 0).rotate(a)
            pygame.draw.line(screen, color, c + d * s * 0.65, c + d * s, w)
    elif kind == "moon":
        pygame.draw.circle(screen, color, c, s * 0.8)
        pygame.draw.circle(screen, (5, 9, 14), c + Vector2(s * 0.4, -s * 0.25), s * 0.7)
    else:
        pygame.draw.circle(screen, color, c, s * 0.6, w)


MODULE_ICON = {"weapon": "gun", "engine": "engine", "reactor": "reactor", "shield": "shield", "armor": "armor",
               "sensor": "sensor", "utility": "utility"}


def module_icon_kind(m):
    if m.category == "weapon":
        return {"gun": "gun", "missile": "missile", "torpedo": "torpedo"}[m.kind]
    return MODULE_ICON[m.category]
