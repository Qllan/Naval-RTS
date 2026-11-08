"""R1.3 ocean and cold-Veil visual contracts, not a gameplay playtest."""

from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from nine.gfx.camera import Camera
from nine.gfx.ocean import Ocean, MASK_CELL_PX
from nine.gfx import palette as P
from nine.gfx.style_tokens import rgb
from nine.gfx.wake import Wakes
from nine.ship import Ship


class FlatVeil:
    def __init__(self, value):
        self.value = value

    def density_grid(self, xs, ys, t):
        return np.full((len(xs), len(ys)), self.value, dtype=float)


@pytest.mark.parametrize("high", (True, False))
def test_dense_veil_is_translucent_and_quality_grid_changes(high):
    ocean = Ocean(seed=23)
    ocean.set_quality(high)
    cam = Camera(320, 200, zoom=1.0)
    cam.snap((4000, 4000))
    surface = pygame.Surface((320, 200))
    surface.fill(P.OCEAN_MID)
    world = SimpleNamespace(veil=FlatVeil(0.95), t=128.0)
    ocean.draw_veil(surface, cam, world)
    alpha = pygame.surfarray.array_alpha(ocean.tint_big)
    assert 0 < int(alpha.max()) <= 86
    assert ocean.density_view.min() == pytest.approx(0.95)
    assert ocean.mask_small.get_width() == 320 // (MASK_CELL_PX if high else 44) + 3
    assert ocean.wisps_enabled is high


def test_water_low_quality_omits_secondary_shimmer():
    ocean = Ocean(seed=26)
    cam = Camera(320, 200, zoom=1.0)
    cam.snap((2600, 2700))
    a, b = pygame.Surface((320, 200)), pygame.Surface((320, 200))
    ocean.draw_water(a, cam, 22.2)
    ocean.set_quality(False)
    ocean.draw_water(b, cam, 22.2)
    assert pygame.image.tostring(a, "RGB") != pygame.image.tostring(b, "RGB")


def test_scaled_ocean_tile_cache_has_hard_limit():
    ocean = Ocean(seed=27)
    cam = Camera(320, 200, zoom=1.0)
    surface = pygame.Surface((320, 200))
    for i in range(22):
        cam.zoom = 0.70 + i * 0.07
        ocean.draw_water(surface, cam, i / 20)
    assert 0 < len(ocean._scaled) <= 16


def test_low_quality_wake_uses_fewer_visual_samples():
    ship = Ship("bastion", (400, 400))
    ship.vel = pygame.Vector2(0, -90)
    high, low = Wakes(), Wakes()
    low.high_quality = False
    for i in range(18):
        ship.pos.y -= 3
        high.update([ship], i * 0.08, 0.08)
        low.update([ship], i * 0.08, 0.08)
    assert len(high.trails[id(ship)]) > len(low.trails[id(ship)]) >= 2


def test_quality_switch_controls_ocean_and_wakes():
    from nine.render import Renderer
    renderer = Renderer(pygame.Surface((320, 200)))
    assert renderer.ocean.high_quality and renderer.wakes.high_quality
    renderer.toggle_quality()
    assert not renderer.ocean.high_quality
    assert not renderer.wakes.high_quality
    assert not renderer.ocean.wisps_enabled
    renderer.toggle_quality()
    assert renderer.ocean.high_quality and renderer.wakes.high_quality


def test_live_ocean_palette_matches_style_bible():
    assert (P.OCEAN_DEEP, P.OCEAN_MID, P.OCEAN_LIGHT, P.FOAM) == (
        rgb("water_deep"), rgb("water_mid"),
        rgb("water_ridge"), rgb("water_foam"))
    assert (P.VEIL_TINT, P.VEIL_WISP, P.VEIL_GLOW, P.VEIL_FRINGE) == (
        rgb("veil_depth"), rgb("veil_mist"),
        rgb("veil_glow"), rgb("veil_fringe"))
