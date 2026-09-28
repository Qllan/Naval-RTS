import random

from pygame.math import Vector2

from nine import config as C
from nine.islands import avoid_turn, collide_ship, generate_islands, island_at, make_island
from nine.ship import Ship
from nine.world import Controls, World


def test_generation_keeps_port_and_eye_clear():
    rng = random.Random(1)
    isl = generate_islands(rng, Vector2(C.PORT_POS), Vector2(C.EYE_POS))
    assert len(isl) > 10
    for i in isl:
        assert i.pos.distance_to(C.PORT_POS) > 800
        assert i.pos.distance_to(C.EYE_POS) > C.EYE_BELT_R
        assert not i.contains(C.PORT_POS, 300)


def test_ship_bounces_off_and_takes_hull_damage_at_speed():
    rng = random.Random(1)
    isl = make_island(rng, (0, 0), 100)
    s = Ship("scout", (-isl.r_at(3.14159) + 5, 0), 0)
    s.vel = Vector2(200, 0)
    shield = s.shield
    impact = collide_ship(s, [isl], rng)
    assert impact > 100
    assert not isl.contains(s.pos, s.radius * 0.5)
    assert s.vel.x < 0                                    # отскок
    assert s.hp < s.hull.hp and s.shield == shield        # мимо щита
    slow = Ship("scout", (-isl.r_at(3.14159) + 5, 0), 0)
    slow.vel = Vector2(20, 0)
    collide_ship(slow, [isl], rng)
    assert slow.hp == slow.hull.hp                        # мягко причалить можно


def test_avoid_turn_steers_away():
    rng = random.Random(2)
    isl = make_island(rng, (300, 30), 90)                 # чуть правее курса
    s = Ship("raider", (0, 0), 0)
    assert avoid_turn(s, [isl], look=300) == -1.0         # отвернуть влево
    far = Ship("raider", (0, -600), 0)
    assert avoid_turn(far, [isl]) == 0.0


def test_world_nodes_not_on_islands_and_shells_stop_at_rocks():
    w = World(seed=3, first_event=1e9)
    for n in w.nodes:
        assert island_at(w.islands, n.pos) is None
    isl = w.islands[0]
    w.player.pos = isl.pos + Vector2(isl.r_max + 120, 0)
    w.player.angle = 180
    w.pirate_spawn_cd = 1e9
    for _ in range(60):
        w.update(1 / 60, Controls(fire=True, aim=Vector2(isl.pos)))
    assert w.projectiles == [] or all(not island_at(w.islands, p.pos) for p in w.projectiles)
    assert any(ev[0] == "rock" for ev in w.fx)
