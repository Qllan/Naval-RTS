"""Объекты мира: порт, ресурсные точки, лут, фауна, дымовые завесы."""

import math

import pygame
from pygame.math import Vector2

from ..ai import Tihodont
from ..entities import RESOURCES
from . import palette as P


def _pts(cam, pos, angle, shape, scale=1.0):
    return [cam.w2s(pos + Vector2(x, y).rotate(angle) * scale) for x, y in shape]


def draw_node(screen, cam, node, t, fx):
    kind = node.kind
    col = RESOURCES[kind].color
    s = cam.w2s(node.pos)
    size = 4 + node.amount / 10
    bob = math.sin(t * 1.6 + node.pos.x * 0.01) * 0.15 + 1
    if kind == "salt":
        # плавучие обломки металла
        for i in range(4):
            a = i * 90 + node.pos.x % 90
            off = Vector2(1, 0).rotate(a) * size * 0.6
            shard = [(-2, -1.2), (2.2, -0.6), (1.6, 1.2), (-1.8, 1)]
            pygame.draw.polygon(screen, P.shade(col, 0.6 + 0.1 * i), _pts(cam, node.pos + off, a, shard, 1.3))
        pygame.draw.circle(screen, P.shade(col, 0.4), s, int(cam.px(size + 3)), 1)
    elif kind == "condensate":
        img = fx.glow(P.shade(col, 0.5), cam.px(size * 2.2) * bob)
        screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(screen, P.shade(col, 0.8), s, max(2, int(cam.px(size * 0.7))))
        for i in range(3):
            ph = (t * 0.7 + i / 3) % 1
            pygame.draw.circle(screen, P.shade(col, 1 - ph), s, max(1, int(cam.px(size * (0.8 + ph * 1.4)))), 1)
    elif kind == "filament":
        img = fx.glow(P.shade(col, 0.35), cam.px(size * 2) * bob)
        screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)
        for i in range(6):
            a = i * 60 + node.pos.y % 60
            spike = [(0, -1), (size * 1.2, 0), (0, 1)]
            pygame.draw.polygon(screen, P.shade(col, 0.7 + 0.05 * i), _pts(cam, node.pos, a, spike))
    else:  # zero
        img = fx.glow((255, 255, 255), cam.px(size * 3) * bob)
        screen.blit(img, img.get_rect(center=s), special_flags=pygame.BLEND_ADD)
        pygame.draw.circle(screen, (255, 255, 255), s, max(2, int(cam.px(size * 0.5))))


def draw_loot(screen, cam, loot, t):
    s = cam.w2s(loot.pos)
    bob = math.sin(t * 2 + loot.pos.x) * cam.px(0.8)
    for i, off in enumerate(((-3, -2), (2, 1), (-1, 3))[:1 + min(2, len(loot.cargo) + len(loot.modules))]):
        rr = pygame.Rect(0, 0, cam.px(6), cam.px(5))
        rr.center = s + Vector2(off) * cam.zoom + Vector2(0, bob)
        pygame.draw.rect(screen, (120, 92, 56), rr, border_radius=1)
        pygame.draw.rect(screen, (190, 150, 90), rr, 1, border_radius=1)
    if int(t * 2) % 2 == 0:
        pygame.draw.circle(screen, (255, 210, 100), s + Vector2(0, -cam.px(5)), max(1, int(cam.px(1.2))))


def draw_ray(screen, cam, ray, t):
    """Скат: ромб с машущими крыльями и хвостом-хлыстом; кончики крыльев светятся."""
    k = 1.0 - ray.depth
    if k <= 0.05:
        return
    sz = getattr(ray, "size", 1.0)
    ph = getattr(ray, "phase", ray.pos.x * 0.1)
    flap = math.sin(t * 4 + ph) * 3.0
    body = [(9, 0), (3, 3.5), (-1, 12 + flap), (-5, 4), (-8, 1), (-8, -1), (-5, -4), (-1, -12 - flap), (3, -3.5)]
    body = [(x * sz, y * sz) for x, y in body]
    col = P.mix(P.OCEAN_MID, (120, 190, 200), k)
    pygame.draw.polygon(screen, col, _pts(cam, ray.pos, ray.angle, body))
    pygame.draw.lines(screen, P.mix(P.OCEAN_MID, (170, 225, 230), k), False,
                      _pts(cam, ray.pos, ray.angle, [(6 * sz, 0), (-5 * sz, 0)]), 1)
    tail = [(-8 * sz - i * 3 * sz, math.sin(t * 6 + ph + i * 0.9) * i * 0.6) for i in range(6)]
    pygame.draw.lines(screen, col, False, _pts(cam, ray.pos, ray.angle, tail), 1)
    tip = P.mix(P.OCEAN_MID, (200, 255, 240), k * (0.6 + 0.4 * math.sin(t * 2 + ph)))
    for side in (1, -1):
        pygame.draw.circle(screen, tip, _pts(cam, ray.pos, ray.angle, [(-1 * sz, side * (12 + flap) * sz)])[0],
                           max(1, int(cam.px(0.9))))


def draw_tihodont(screen, cam, tx, t, fx):
    R = Tihodont.RADIUS
    body_col = (92, 48, 44) if tx.angry else (40, 72, 84)
    sw = getattr(tx, "swim", t)
    und = [math.sin(sw * 1.2 + i * 0.8) * 4 for i in range(8)]
    # хвостовой плавник: два лопасти, машут вбок
    swing = math.sin(sw * 1.6) * 0.35
    root = Vector2(-R * 1.3, 0)
    tail_dir = Vector2(-1, 0).rotate(math.degrees(swing))
    fluke = [root, root + tail_dir * R * 0.35 + tail_dir.rotate(90) * R * 0.45,
             root + tail_dir * R * 0.22, root + tail_dir * R * 0.35 - tail_dir.rotate(90) * R * 0.45]
    fins = []
    for side in (1, -1):                                   # грудные плавники, медленно гребут
        a = math.sin(sw * 1.1 + side) * 10
        base = Vector2(R * 0.35, side * R * 0.45)
        fins.append([base, base + Vector2(-R * 0.45, side * R * 0.35).rotate(a), base + Vector2(-R * 0.25, 0)])
    half = [(R * 1.15, 0), (R * 0.9, R * 0.35), (R * 0.4, R * 0.55 + und[0]), (-R * 0.2, R * 0.5 + und[1]),
            (-R * 0.7, R * 0.3 + und[2]), (-R * 1.1, R * 0.12), (-R * 1.35, R * 0.45 + und[3]),
            (-R * 1.3, 0)]
    shape = half + [(x, -y) for x, y in reversed(half[1:-1])]
    pts = _pts(cam, tx.pos, tx.angle, shape)
    extra = [_pts(cam, tx.pos, tx.angle, fluke)] + [_pts(cam, tx.pos, tx.angle, f) for f in fins]
    allp = pts + [q for poly in extra for q in poly]
    x0 = min(p.x for p in allp) - 4
    y0 = min(p.y for p in allp) - 4
    w = int(max(p.x for p in allp) - x0 + 8)
    h = int(max(p.y for p in allp) - y0 + 8)
    layer = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    for poly in extra:
        pygame.draw.polygon(layer, (*P.shade(body_col, 0.85), 185), [(p.x - x0, p.y - y0) for p in poly])
    local = [(p.x - x0, p.y - y0) for p in pts]
    pygame.draw.polygon(layer, (*body_col, 205), local)
    pygame.draw.polygon(layer, (*P.shade(body_col, 1.8), 120), local, max(1, int(cam.px(2))))
    ridge = _pts(cam, tx.pos, tx.angle, [(R * 0.8, 0), (-R * 1.2, 0)])     # хребет
    pygame.draw.line(layer, (*P.shade(body_col, 1.5), 90), (ridge[0].x - x0, ridge[0].y - y0),
                     (ridge[1].x - x0, ridge[1].y - y0), max(1, int(cam.px(3))))
    bh = _pts(cam, tx.pos, tx.angle, [(R * 0.55, 0)])[0]                  # дыхало
    pygame.draw.circle(layer, (*P.shade(body_col, 0.5), 220), (bh.x - x0, bh.y - y0), max(1, int(cam.px(3))))
    screen.blit(layer, (x0, y0))
    # биолюминесцентные пятна
    for i in range(12):
        x = R * (0.9 - i * 0.16)
        y = R * 0.28 * math.sin(i * 1.9)
        a = 0.5 + 0.5 * math.sin(t * 1.5 + i)
        img = fx.glow(P.mix((0, 0, 0), (60, 220, 190) if not tx.angry else (240, 90, 60), a), cam.px(3.5))
        screen.blit(img, img.get_rect(center=cam.w2s(tx.pos + Vector2(x, y).rotate(tx.angle))),
                    special_flags=pygame.BLEND_ADD)


def draw_smoke_screen(screen, cam, sm, fx, t):
    k = min(1.0, sm.life / 2.0)
    for i in range(9):
        a = i * 40 + t * 8
        off = Vector2(1, 0).rotate(a) * sm.radius * (0.25 + 0.45 * ((i * 37) % 10) / 10)
        img = fx.puff((110, 114, 118), cam.px(sm.radius * 0.55), 150 * k)
        screen.blit(img, img.get_rect(center=cam.w2s(sm.pos + off)))

