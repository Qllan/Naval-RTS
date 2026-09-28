"""Порт беженцев: статичная часть рисуется один раз и кэшируется, краны и огни — каждый кадр.

Координаты — мировые единицы относительно центра порта (+Y — юг).
Север (−Y) — вход в гавань и пирсы.
"""

import math
import random
from collections import OrderedDict

import pygame
from pygame.math import Vector2

from .. import config as C
from . import palette as P

PX = 2.0
EXT = C.PORT_RADIUS + 50

CRANES = ((-52, -34), (52, -34))
LAMPS = [(-100, -26), (-50, -26), (0, -26), (50, -26), (100, -26), (-100, 58), (0, 60), (100, 58)]
TANKS = ((78, 14, 15), (78, 46, 13), (104, 30, 10))
BEACON = (-116, 56)


def _p(x, y):
    return ((x + EXT) * PX, (y + EXT) * PX)


def _rect(s, x, y, w, h, col, width=0, radius=0):
    r = pygame.Rect(0, 0, w * PX, h * PX)
    r.center = _p(x, y)
    pygame.draw.rect(s, col, r, int(width * PX) if width else 0, border_radius=int(radius * PX))
    return r


def build_port():
    n = int(EXT * 2 * PX)
    s = pygame.Surface((n, n), pygame.SRCALPHA)
    rng = random.Random(42)

    # волнорезы: каменные дуги на юго-западе и юго-востоке, вход с севера свободен
    for a0, a1 in ((100, 170), (10, 80), (190, 215), (325, 350)):
        for a in range(a0, a1, 3):
            r = C.PORT_RADIUS + rng.uniform(-6, 8)
            x, y = math.cos(math.radians(a)) * r, math.sin(math.radians(a)) * r
            pygame.draw.circle(s, P.mix((60, 62, 64), (96, 96, 92), rng.random()), _p(x, y), rng.uniform(4, 7) * PX)
    # мелководье гавани
    harbor = pygame.Surface((n, n), pygame.SRCALPHA)
    pygame.draw.circle(harbor, (30, 70, 84, 70), _p(0, 0), (C.PORT_RADIUS - 8) * PX)
    s.blit(harbor, (0, 0))

    # главная платформа
    plat = [(-122, -30), (122, -30), (130, -18), (130, 66), (-130, 66), (-130, -18)]
    pygame.draw.polygon(s, (22, 26, 30), [_p(x + 2, y + 3) for x, y in plat])          # тень
    pygame.draw.polygon(s, (62, 68, 72), [_p(x, y) for x, y in plat])
    for gx in range(-120, 130, 12):                                                   # плиты
        pygame.draw.line(s, (54, 60, 64), _p(gx, -28), _p(gx, 64), 1)
    for gy in range(-24, 66, 12):
        pygame.draw.line(s, (54, 60, 64), _p(-128, gy), _p(128, gy), 1)
    pygame.draw.polygon(s, (92, 98, 100), [_p(x, y) for x, y in plat], int(1.5 * PX))
    for x in range(-118, 122, 8):                                                     # жёлтая кромка
        pygame.draw.line(s, (200, 170, 60), _p(x, -26), _p(x + 4, -26), max(1, int(PX)))
    for x in range(-120, 124, 10):                                                    # кранцы-покрышки
        pygame.draw.circle(s, (24, 24, 26), _p(x, -31), 2 * PX)

    # пирсы с лодками
    for x in (-86, -34, 34, 86):
        pygame.draw.rect(s, (80, 68, 54), pygame.Rect(*_p(x - 6, -112), 12 * PX, 82 * PX))
        for k in range(0, 82, 3):
            pygame.draw.line(s, (62, 52, 42), _p(x - 6, -112 + k), _p(x + 6, -112 + k), 1)
        for k in range(4):
            for side in (-1, 1):
                pygame.draw.circle(s, (40, 40, 42), _p(x + side * 5, -104 + k * 20), PX)
    for x, side, col in ((-86, 1, (160, 150, 130)), (-34, -1, (120, 60, 50)), (86, -1, (70, 110, 130))):
        bx = x + side * 14
        hull = [(bx, -104), (bx + 4, -96), (bx + 4, -76), (bx - 4, -76), (bx - 4, -96)]
        pygame.draw.polygon(s, col, [_p(*q) for q in hull])
        pygame.draw.polygon(s, P.shade(col, 0.6), [_p(*q) for q in hull], 1)
        _rect(s, bx, -84, 5, 6, P.shade(col, 1.2), radius=1)

    # контейнеры
    colors = ((150, 60, 44), (44, 90, 130), (60, 120, 70), (190, 150, 50), (190, 190, 180), (110, 60, 110))
    for row in range(3):
        for col in range(6):
            x, y = -112 + col * 13, -12 + row * 8
            c = rng.choice(colors)
            r = _rect(s, x, y, 12, 7, c)
            for k in range(1, 6):
                pygame.draw.line(s, P.shade(c, 0.75), (r.x + k * r.w / 6, r.y), (r.x + k * r.w / 6, r.bottom), 1)
            pygame.draw.rect(s, P.shade(c, 0.55), r, 1)

    # склады с рифлёными крышами
    for x, y, w, h, c in ((-8, 20, 58, 32, (96, 104, 110)), (-78, 44, 40, 28, (120, 96, 72))):
        _rect(s, x + 1.5, y + 2, w, h, (20, 24, 28))
        r = _rect(s, x, y, w, h, c)
        for k in range(0, int(h), 3):
            pygame.draw.line(s, P.shade(c, 0.8 if k % 6 else 1.15), (r.x, r.y + k * PX), (r.right, r.y + k * PX), 1)
        pygame.draw.line(s, P.shade(c, 1.3), (r.x, r.centery), (r.right, r.centery), 2)            # конёк
        for k in range(3):
            pygame.draw.circle(s, (50, 54, 58), (r.x + (k + 1) * r.w / 4, r.centery - 5), 3)

    # нефтебаза: цистерны, трубы, лестницы
    for x, y, r in TANKS:
        pygame.draw.circle(s, (20, 24, 28), _p(x + 2, y + 3), r * PX)
        pygame.draw.circle(s, (170, 168, 158), _p(x, y), r * PX)
        pygame.draw.circle(s, (130, 128, 120), _p(x, y), r * PX, 2)
        pygame.draw.circle(s, (140, 138, 130), _p(x, y), r * 0.6 * PX, 1)
        pygame.draw.line(s, (90, 90, 86), _p(x + r * 0.7, y - r * 0.7), _p(x + r * 0.2, y - r * 0.2), 2)
    pygame.draw.line(s, (110, 90, 60), _p(78, 14), _p(78, 46), int(1.5 * PX))
    pygame.draw.line(s, (110, 90, 60), _p(78, 30), _p(104, 30), int(1.5 * PX))
    pygame.draw.line(s, (110, 90, 60), _p(63, 30), _p(20, -24), int(1.2 * PX))

    # заброшенная вертолётная площадка и ржавый вертолёт — со времён Пелены никто не летает
    hp = Vector2(40, 52)
    pygame.draw.circle(s, (72, 76, 78), _p(*hp), 13 * PX)
    pygame.draw.circle(s, (150, 140, 80), _p(*hp), 13 * PX, 1)
    for x in (-3, 3):
        pygame.draw.line(s, (130, 124, 80), _p(hp.x + x, hp.y - 5), _p(hp.x + x, hp.y + 5), 2)
    pygame.draw.line(s, (130, 124, 80), _p(hp.x - 3, hp.y), _p(hp.x + 3, hp.y), 2)
    heli = hp + Vector2(4, -2)
    pygame.draw.ellipse(s, (104, 70, 48), pygame.Rect(*_p(heli.x - 5, heli.y - 2.5), 10 * PX, 5 * PX))
    pygame.draw.line(s, (104, 70, 48), _p(heli.x - 4, heli.y), _p(heli.x - 12, heli.y + 1), 2)
    for a in (20, 110):
        d = Vector2(1, 0).rotate(a) * 9
        pygame.draw.line(s, (70, 50, 38), _p(*(heli - d)), _p(*(heli + d)), 1)
    for _ in range(12):                                                                # трещины
        c = hp + Vector2(1, 0).rotate(rng.uniform(0, 360)) * rng.uniform(2, 12)
        pygame.draw.line(s, (48, 50, 52), _p(*c), _p(*(c + Vector2(1, 0).rotate(rng.uniform(0, 360)) * 3)), 1)

    # маяк
    pygame.draw.circle(s, (220, 220, 214), _p(*BEACON), 5 * PX)
    pygame.draw.circle(s, (180, 60, 50), _p(*BEACON), 5 * PX, 2)
    return s


class PortArt:
    def __init__(self):
        self.master = None
        self.scaled = OrderedDict()

    def draw(self, screen, cam, world, font):
        pos = world.port
        if not cam.visible(pos, EXT + 40):
            return
        if self.master is None:
            self.master = build_port()
        zq = round(cam.zoom / 0.02) * 0.02
        img = self.scaled.get(zq)
        if img is None:
            size = max(4, int(self.master.get_width() * cam.zoom / PX))
            img = pygame.transform.smoothscale(self.master, (size, size))
            self.scaled[zq] = img
            if len(self.scaled) > 8:
                self.scaled.popitem(last=False)
        screen.blit(img, img.get_rect(center=cam.w2s(pos)))
        t = world.t
        # буйки акватории
        for i in range(16):
            a = math.radians(i * 22.5 + t * 2)
            b = cam.w2s(pos + Vector2(math.cos(a), math.sin(a)) * C.PORT_RADIUS * 1.08)
            on = (int(t * 1.5) + i) % 4 == 0
            pygame.draw.circle(screen, (240, 200, 90) if on else (110, 90, 50), b, max(2, int(cam.px(2.2))))
        # краны: ферма, стрела, противовес
        for (cx, cy), phase in zip(CRANES, (0.0, 1.3)):
            ang = -90 + 35 * math.sin(t * 0.25 + phase)
            base = pos + Vector2(cx, cy)
            tip = base + Vector2(1, 0).rotate(ang) * 44
            back = base - Vector2(1, 0).rotate(ang) * 12
            w = max(2, int(cam.px(3)))
            pygame.draw.line(screen, (60, 52, 30), cam.w2s(back) + Vector2(2, 3), cam.w2s(tip) + Vector2(2, 3), w)
            pygame.draw.line(screen, (214, 170, 60), cam.w2s(back), cam.w2s(tip), w)
            for k in range(1, 8):                                                   # ферма
                q = base + Vector2(1, 0).rotate(ang) * (k * 5.5)
                d = Vector2(0, 1).rotate(ang) * 1.6
                pygame.draw.line(screen, (150, 120, 40), cam.w2s(q - d), cam.w2s(q + d), 1)
            rb = pygame.Rect(0, 0, cam.px(7), cam.px(7))
            rb.center = cam.w2s(back)
            pygame.draw.rect(screen, (70, 70, 72), rb)
            pygame.draw.circle(screen, (90, 80, 50), cam.w2s(base), max(2, int(cam.px(4))))
            pygame.draw.line(screen, (40, 40, 40), cam.w2s(tip), cam.w2s(tip + Vector2(0, 6)), 1)   # трос
        # фонари
        for lx, ly in LAMPS:
            pygame.draw.circle(screen, (250, 230, 170), cam.w2s(pos + Vector2(lx, ly)), max(1, int(cam.px(1.2))))
        if int(t * 1.2) % 2 == 0:
            pygame.draw.circle(screen, (255, 90, 70), cam.w2s(pos + Vector2(*BEACON)), max(2, int(cam.px(2.4))))
        lbl = font.render("ПОРТ БЕЖЕНЦЕВ", True, (130, 190, 200))
        screen.blit(lbl, lbl.get_rect(midtop=cam.w2s(pos + Vector2(0, 74))))


def port_lights(world):
    """Источники света порта: (позиция, цвет, радиус в мире)."""
    pos = world.port
    t = world.t
    out = [(pos + Vector2(lx, ly), (255, 226, 170), 95) for lx, ly in LAMPS]
    out += [(pos + Vector2(cx, cy), (255, 230, 170), 130) for cx, cy in CRANES]
    out.append((pos + Vector2(0, 20), (255, 200, 140), 70))
    if int(t * 1.2) % 2 == 0:
        out.append((pos + Vector2(*BEACON), (255, 80, 60), 110))
    for i in range(16):
        if (int(t * 1.5) + i) % 4 == 0:
            a = math.radians(i * 22.5 + t * 2)
            out.append((pos + Vector2(math.cos(a), math.sin(a)) * C.PORT_RADIUS * 1.08, (255, 200, 90), 40))
    return out
