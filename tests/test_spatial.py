"""Parity and scaling checks for the non-interactive spatial broad phase."""

import random
from types import SimpleNamespace

import pytest
from pygame.math import Vector2

from nine.combat import Projectile
from nine.ship import Ship
from nine.spatial import ShipCollisionGrid, ship_overlaps
from nine.world import World


def simple_ship(x, y, radius=20, alive=True):
    return SimpleNamespace(pos=Vector2(x, y), radius=radius, alive=alive)


def original_first_hit(ships, pos, padding):
    for ship in ships:
        if ship.alive and ship.pos.distance_to(pos) < ship.radius + padding:
            return ship
    return None


@pytest.mark.parametrize("padding", (0, 4))
def test_grid_has_exact_parity_with_original_scan_on_seeded_scenes(padding):
    rng = random.Random(2031)
    ships = [simple_ship(rng.uniform(-5000, 5000), rng.uniform(-5000, 5000),
                         rng.uniform(7, 48), alive=i % 11 != 0)
             for i in range(120)]
    probes = [Vector2(rng.uniform(-5000, 5000), rng.uniform(-5000, 5000))
              for _ in range(750)]
    # All precise boundary and overlap edge cases, not only random samples.
    probes += [Vector2(ship.pos) for ship in ships]
    probes += [ship.pos + Vector2(ship.radius + padding, 0) for ship in ships]
    grid = ShipCollisionGrid(ships)
    for point in probes:
        assert grid.first_hit(point, padding) is original_first_hit(ships, point, padding)


def test_overlap_keeps_original_priority_and_ignores_dead_ships():
    outer = simple_ship(63.9, 80, radius=13)
    closer = simple_ship(64.1, 80, radius=13)
    grid = ShipCollisionGrid([outer, closer])
    assert grid.first_hit(Vector2(64, 80)) is outer
    outer.alive = False
    assert grid.first_hit(Vector2(64, 80)) is closer


def test_grid_queries_handle_boundaries_and_extra_projectile_radius():
    ship = simple_ship(127, -128, radius=10)
    grid = ShipCollisionGrid([ship], cell_size=128)
    assert grid.first_hit(Vector2(140, -128), 4) is ship
    assert grid.first_hit(Vector2(140, -128), 0) is None
    assert grid.first_hit(Vector2(-2000, 4000), 4) is None
    assert not ship_overlaps(ship, ship.pos + Vector2(10, 0), 0)


def test_spatial_index_reduces_candidate_checks_in_distributed_scene():
    rng = random.Random(91)
    ships = [simple_ship(rng.uniform(0, 12000), rng.uniform(0, 12000))
             for _ in range(120)]
    probes = [Vector2(rng.uniform(0, 12000), rng.uniform(0, 12000))
              for _ in range(1400)]
    grid = ShipCollisionGrid(ships)
    candidate_checks = sum(len(grid.candidates(pos)) for pos in probes)
    brute_force_checks = len(ships) * len(probes)
    # Test number of narrow-phase candidates, not wall clock (CI-flaky).
    assert candidate_checks * 20 < brute_force_checks


def test_world_projectile_step_preserves_first_collision_and_enemy_side():
    world = World(seed=9, first_event=1e9)
    world.islands = []
    world.density_at = lambda pos: 0.0
    world.player = Ship("needle", (1000, 1000))

    first = Ship("scout", (1300, 1000), side="pirate")
    second = Ship("scout", (1301, 1000), side="pirate")
    world.pirates = [SimpleNamespace(ship=first), SimpleNamespace(ship=second)]
    world.projectiles = [
        Projectile(Vector2(1300, 1000), Vector2(0, 0), 9, "kinetic",
                   world.player, "shell", 3)
    ]
    first_shield, second_shield = first.shield, second.shield
    world._update_projectiles(0.0)
    assert first.shield < first_shield
    assert second.shield == second_shield

    # NPC-owned projectiles still select the player without the enemy grid.
    world.projectiles = [
        Projectile(Vector2(1000, 1000), Vector2(0, 0), 9, "kinetic",
                   first, "shell", 3)
    ]
    player_shield = world.player.shield
    world._update_projectiles(0.0)
    assert world.player.shield < player_shield
