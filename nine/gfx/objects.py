"""Объекты мира: порт, ресурсные точки, лут, фауна, дымовые завесы."""

import math

import pygame
from pygame.math import Vector2

from .. import config as C
from ..ai import Tihodont
from ..entities import RESOURCES
from . import palette as P


def _pts(cam, pos, angle, shape, scale=1.0):
    return [cam.w2s(pos + Vector2(x, y).rotate(angle) * scale) for x, y in shape]


def draw_port(screen, cam, world, font):
    pos = world.port
    if not cam.visible(pos, C.PORT_RADIUS + 80):
        return
    t = world.t
    s = cam.w2s(pos)
    r = cam.px(C.PORT_RADIUS)
    # акватория с буйками
    pygame.draw.circle(screen, (12, 28, 40), s, int(r))
    for i in range(16):
        a = math.radians(i * 22.5 + t * 2)
        b = s + Vector2(math.cos(a), math.sin(a)) * r
        on = (int(t * 1.5) + i) % 4 == 0
        pygame.draw.circle(screen, (240, 200, 90) if on else (110, 90, 50), b, max(2, int(cam.px(2.5))))
    # платформа: причалы, склады, краны
    plat = [(-70, -40), (70, -40), (78, -20), (78, 40), (-78, 40), (-78, -20)]
    pygame.draw.polygon(screen, (46, 56, 64), _pts(cam, pos, 0, plat))
    pygame.draw.polygon(screen, (80, 94, 102), _pts(cam, pos, 0, plat), max(1, int(cam.px(1.5))))
    for x in (-60, -20, 20, 60):                        # пирсы
        pier = [(x - 5, -40), (x + 5, -40), (x + 5, -95), (x - 5, -95)]
        pygame.draw.polygon(screen, (70, 62, 52), _pts(cam, pos, 0, pier))
        for k in range(6):
            a, b = cam.w2s(pos + Vector2(x - 5, -45 - k * 9)), cam.w2s(pos + Vector2(x + 5, -45 - k * 9))
            pygame.draw.line(screen, (52, 46, 40), a, b, 1)
    for bx, by, lx, ly, col in ((-50, 10, 34, 36, (94, 104, 110)), (0, 12, 28, 30, (120, 96, 72)),
                                (45, 8, 36, 40, (84, 98, 108))):
        rr = pygame.Rect(0, 0, cam.px(lx), cam.px(ly))
        rr.center = cam.w2s(pos + Vector2(bx, by))
        pygame.draw.rect(screen, col, rr, border_radius=max(1, int(cam.px(2))))
        pygame.draw.rect(screen, P.shade(col, 1.25), rr.inflate(-cam.px(8), -cam.px(8)),
                         border_radius=max(1, int(cam.px(2))))
    for cx, ang in ((-40, -30 + 20 * math.sin(t * 0.3)), (40, 200 + 15 * math.sin(t * 0.4 + 1))):
        base = cam.w2s(pos + Vector2(cx, -30))
        arm = base + Vector2(1, 0).rotate(ang) * cam.px(38)
        pygame.draw.line(screen, (210, 170, 70), base, arm, max(2, int(cam.px(3))))
        pygame.draw.circle(screen, (60, 60, 60), base, max(2, int(cam.px(5))))
    # огни окон
    for i in range(10):
        on = (i * 7 + int(t)) % 5 != 0
        wp = cam.w2s(pos + Vector2(-62 + i * 13, 34))
        pygame.draw.circle(screen, (250, 220, 150) if on else (70, 60, 40), wp, max(1, int(cam.px(1.4))))
    lbl = font.render("ПОРТ БЕЖЕНЦЕВ", True, (130, 190, 200))
    screen.blit(lbl, lbl.get_rect(midtop=cam.w2s(pos + Vector2(0, 48))))


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
    k = 1.0 - ray.depth
    if k <= 0.05:
        return
    flap = math.sin(t * 5 + ray.pos.x * 0.1) * 2.5
    body = [(8, 0), (1, 3), (-3, 10 + flap), (-5, 3), (-12, 0.5), (-12, -0.5), (-5, -3), (-3, -10 - flap), (1, -3)]
    col = P.mix(P.OCEAN_MID, (120, 190, 200), k)
    pygame.draw.polygon(screen, col, _pts(cam, ray.pos, ray.angle, body))
    pygame.draw.circle(screen, P.mix(P.OCEAN_MID, (200, 255, 240), k), cam.w2s(ray.pos), max(1, int(cam.px(1))))


def draw_tihodont(screen, cam, tx, t, fx):
    R = Tihodont.RADIUS
    body_col = (70, 36, 34) if tx.angry else (16, 34, 42)
    und = [math.sin(t * 1.2 + i * 0.8) * 4 for i in range(8)]
    half = [(R * 1.15, 0), (R * 0.9, R * 0.35), (R * 0.4, R * 0.55 + und[0]), (-R * 0.2, R * 0.5 + und[1]),
            (-R * 0.7, R * 0.3 + und[2]), (-R * 1.1, R * 0.12), (-R * 1.35, R * 0.45 + und[3]),
            (-R * 1.3, 0)]
    shape = half + [(x, -y) for x, y in reversed(half[1:-1])]
    pts = _pts(cam, tx.pos, tx.angle, shape)
    x0 = min(p.x for p in pts) - 4
    y0 = min(p.y for p in pts) - 4
    w = int(max(p.x for p in pts) - x0 + 8)
    h = int(max(p.y for p in pts) - y0 + 8)
    layer = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    local = [(p.x - x0, p.y - y0) for p in pts]
    pygame.draw.polygon(layer, (*body_col, 205), local)
    pygame.draw.polygon(layer, (*P.shade(body_col, 1.8), 120), local, max(1, int(cam.px(2))))
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
