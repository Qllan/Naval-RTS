"""Contract tests for the offline authority boundary, not multiplayer playtests."""

import json
import math

import pytest
from pygame.math import Vector2

from nine.net.clock import FixedTickClock
from nine.net.commands import InvalidCommand, PlayerCommand
from nine.net.host import AuthorityError, ServerSimulation
from nine.world import World


@pytest.mark.parametrize("payload", [
    {}, {"seq": True}, {"seq": -1}, {"seq": 1.0},
    {"seq": 1, "pos": [123, 456]}, {"seq": 1, "credits": 1000},
    {"seq": 1, "throttle": float("nan")}, {"seq": 1, "turn": float("inf")},
    {"seq": 1, "fire": 1}, {"seq": 1, "aim": [1e100, 0]},
    {"seq": 1, "aim": [0]}, {"seq": 1, "activate": [0, 0]},
    {"seq": 1, "activate": [4]}, {"seq": 1, "pips": ["unknown"]},
])
def test_command_rejects_untrusted_or_malformed_fields(payload):
    with pytest.raises(InvalidCommand):
        PlayerCommand.parse(payload)


def test_command_clamps_axes_and_is_json_friendly():
    cmd = PlayerCommand.parse({"seq": 12, "throttle": 8, "turn": -3,
                               "boost": True, "aim": [1200, 800],
                               "activate": [0, 2], "pips": ["engines"]})
    assert cmd.throttle == 1.0 and cmd.turn == -1.0
    assert cmd.aim == (1200.0, 800.0)
    assert json.loads(json.dumps({"seq": cmd.seq, "aim": cmd.aim})) == {
        "seq": 12, "aim": [1200.0, 800.0]}
    controls = cmd.to_controls()
    assert controls.aim == Vector2(1200, 800)
    controls.activate.append(1)
    assert cmd.activate == (0, 2)
    assert cmd.to_controls(impulses=False).activate == []


def test_clock_tracks_fixed_ticks_and_limits_catchup():
    clock = FixedTickClock(hz=60, max_catchup=5)
    assert clock.consume(1 / 120) == 0
    assert clock.consume(1 / 120) == 1
    assert clock.consume(1.0) == 5
    assert clock.skipped_seconds > 0
    assert clock.consume(0.0) == 0
    assert clock.mark_tick() == 1
    with pytest.raises(ValueError):
        clock.consume(float("nan"))


def test_owner_and_sequence_replay_validation_and_bounded_input():
    host = ServerSimulation(World(seed=9, first_event=1e9), owner_id="pilot")
    with pytest.raises(AuthorityError):
        host.submit("intruder", {"seq": 1, "throttle": 1})
    assert host.submit("pilot", {"seq": 1, "throttle": 1}) is True
    assert host.submit("pilot", {"seq": 1, "throttle": 1}) is False
    assert host.submit("pilot", {"seq": 2, "throttle": -1}) is True
    before = host.world.t
    assert host.tick() == 1
    assert host.world.t == pytest.approx(before + 1 / 60)
    assert host._pending is None
    assert host.clock.tick == 1
    assert host.accepted == 2 and host.rejected == 2


def test_authoritative_host_has_repeatable_headless_steps():
    def run():
        host = ServerSimulation(World(seed=912, first_event=1e9))
        for index in range(90):
            host.submit("local", {"seq": index,
                                   "throttle": 1 if index < 60 else 0,
                                   "turn": 0.3})
            host.tick()
        ship = host.world.player
        return (round(ship.pos.x, 6), round(ship.pos.y, 6),
                round(ship.angle, 6), round(ship.capacitor, 6),
                host.clock.tick, round(host.world.t, 6))

    assert run() == run()



def test_coalescing_keeps_early_one_shot_actions_without_repeating_them():
    host = ServerSimulation(World(seed=9, first_event=1e9))
    host.submit("local", {"seq": 1, "throttle": 1.0, "activate": [0],
                          "toggle_spotlight": True, "pips": ["engines"]})
    host.submit("local", {"seq": 2, "throttle": 0.25, "activate": [1],
                          "pips": ["weapons"]})
    queued = host._pending
    assert queued.throttle == 0.25
    assert queued.activate == (0, 1)
    assert queued.pips == ("engines", "weapons")
    assert queued.toggle_spotlight
    host.tick()
    assert host.world.spotlight
    assert host._pending is None
    host.tick()
    assert host.world.spotlight  # one-shot toggle is not repeated
