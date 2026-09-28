from pygame.math import Vector2

from nine import config as C
from nine.events import CALM, SURGE, EventDirector
from nine.veil import Veil


def test_density_grows_toward_eye():
    v = Veil(seed=9)
    port = v.density(C.PORT_POS, 0)
    mid = v.density(((C.PORT_POS[0] + C.EYE_POS[0]) / 2, (C.PORT_POS[1] + C.EYE_POS[1]) / 2), 0)
    belt = v.density((C.EYE_POS[0] - C.EYE_WALL_R - 100, C.EYE_POS[1]), 0)
    assert port < 0.2
    assert port < mid < belt


def test_mirror_is_calm_inside_wall():
    v = Veil(seed=9)
    assert v.density(C.EYE_POS, 5.0) < 0.1
    assert v.zone(C.EYE_POS, 0.0) == "Око / Зеркало"
    wall = (C.EYE_POS[0] + (C.EYE_CALM_R + C.EYE_WALL_R) / 2, C.EYE_POS[1])
    assert v.in_wall(wall) and v.in_dead_zone(wall)


def test_density_is_clamped():
    v = Veil(seed=3)
    for x in range(0, C.WORLD_W, 400):
        for y in range(0, C.WORLD_H, 400):
            assert 0.0 <= v.density((x, y), 12.3) <= 1.0


def test_surge_raises_density_and_blinds_radar_only_when_active():
    v = Veil(seed=9)
    ev = EventDirector(first_delay=1e9)
    v.events = ev
    pos = Vector2(3000, 5000)
    e = ev.spawn(SURGE, pos, 0)
    assert ev.warning_at(pos, 1.0)                  # скаты уже чувствуют...
    assert ev.modifier("density", pos, 1.0) == 0    # ...а Пелена ещё спокойна
    t = e.start + 5
    assert v.density(pos, t) > v.static_density(pos.x, pos.y) + 0.3 or v.density(pos, t) == 1.0
    assert ev.multiplier("radar", pos, t) < 0.5
    assert ev.modifier("shield_drain", pos, t) > 0
    assert ev.modifier("shield_drain", pos + Vector2(SURGE.radius + 10, 0), t) == 0


def test_director_announces_event_once():
    ev = EventDirector(first_delay=1e9)
    ev.spawn(CALM, (0, 0), 0)
    ev.update(0.1, (0, 0))
    assert len(ev.started) == 1
    ev.update(0.2, (0, 0))
    assert ev.started == []
    ev.update(CALM.duration + 1, (0, 0))
    assert ev.active == []


def test_density_grid_matches_pointwise_density():
    import numpy as np
    v = Veil(seed=9)
    ev = EventDirector(first_delay=1e9)
    v.events = ev
    e = ev.spawn(SURGE, (4000, 3000), 0)
    t = e.start + 4
    xs = np.linspace(100, 7900, 17)
    ys = np.linspace(100, 7900, 13)
    grid = v.density_grid(xs, ys, t)
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            assert abs(grid[j, i] - v.density((x, y), t)) < 1e-9


def test_band_event_covers_a_strip_and_pushes_along_it():
    from nine.events import CURRENT, STORM
    from pygame.math import Vector2
    ev = EventDirector(first_delay=1e9)
    e = ev.spawn(CURRENT, (0, 0), 0, angle=0)
    t = e.start + 5
    assert e.covers((1000, 0)) and not e.covers((0, 400))
    f = ev.flow(Vector2(0, 0), t)
    assert f.x > 50 and abs(f.y) < 1e-6
    import numpy as np
    xs, ys = np.array([0.0, 1000.0, 0.0]), np.array([0.0, 400.0])
    grid = e.strength_grid(*np.meshgrid(xs, ys), t)
    assert grid[0, 0] > 0.9 and grid[1, 0] == 0
    s = ev.spawn(STORM, (5000, 5000), 0, angle=90)
    assert ev.multiplier("vision", Vector2(5000, 5000), s.start + 5) < 0.7
