"""Headless checks for the distinct sea trading-platform artwork."""

import pygame
from pygame.math import Vector2

from nine import config as C
from nine.gfx.platform_art import TradePlatformArt, platform_lights, platform_activity
from nine.world import World


class CameraStub:
    zoom = 1.0

    def __init__(self, center):
        self.center = Vector2(center)

    def visible(self, pos, radius=0):
        return Vector2(pos).distance_to(self.center) < 750 + radius

    def px(self, distance):
        return float(distance) * self.zoom

    def w2s(self, pos):
        return Vector2(pos) - self.center + Vector2(400, 400)


def test_platform_sprite_has_distinct_silhouette_and_lamps():
    pygame.font.init()
    art = TradePlatformArt()
    image = art._build()
    assert image.get_width() > 600 and image.get_height() > 600
    assert image.get_at((0, 0)).a == 0
    assert image.get_bounding_rect().width > 200
    assert image.get_bounding_rect().height > 200
    assert art.master is None


def test_platform_renders_nearby_but_not_offscreen():
    pygame.font.init()
    world = World(seed=9, first_event=1e9)
    art = TradePlatformArt()
    screen = pygame.Surface((800, 800))
    font = pygame.font.Font(None, 18)
    cam = CameraStub(world.platform)
    art.draw(screen, cam, world, font)
    assert art.master is not None
    center = screen.get_at((400, 400))
    assert center != (0, 0, 0, 255)
    assert len(art.scaled) == 1
    previous = len(art.scaled)
    art.draw(screen, cam, world, font)
    assert len(art.scaled) == previous
    away = CameraStub(world.port)
    old = screen.copy()
    art.draw(screen, away, world, font)
    assert pygame.image.tostring(screen, "RGBA") == pygame.image.tostring(old, "RGBA")


def test_station_lights_follow_platform_not_refugee_port():
    world = World(seed=16, first_event=1e9)
    lights = platform_lights(world)
    assert len(lights) >= 4
    assert all(pos.distance_to(world.platform) < C.PORT_RADIUS for pos, _, _ in lights)
    assert all(pos.distance_to(world.port) > 500 for pos, _, _ in lights)
    world.t += 3
    assert len(platform_lights(world)) >= 4


def test_platform_activity_is_deterministic_and_moves_over_time():
    first = platform_activity(0.0)
    assert platform_activity(0.0) == first
    later = platform_activity(6.0)
    assert first != later
    cranes, craft, heading = first
    assert len(cranes) == 2 and len(craft) == 2
    assert 0 <= heading < 360


def test_dynamic_platform_changes_pixels_without_rebuilding_master():
    pygame.font.init()
    world = World(seed=9, first_event=1e9)
    art = TradePlatformArt()
    cam = CameraStub(world.platform)
    font = pygame.font.Font(None, 18)
    screen_at_start = pygame.Surface((800, 800))
    art.draw(screen_at_start, cam, world, font)
    first_master = art.master
    first_cache = len(art.scaled)
    world.t = 6.0
    screen_later = pygame.Surface((800, 800))
    art.draw(screen_later, cam, world, font)
    assert art.master is first_master
    assert len(art.scaled) == first_cache
    assert pygame.image.tostring(screen_at_start, "RGB") != pygame.image.tostring(
        screen_later, "RGB"
    )
