"""Escort contract: player must accompany the assigned ship during one voyage."""

import pygame
from pygame.math import Vector2

from nine import save
from nine.port_ui import PortUI, TABS
from nine.screens import journal_entries
from nine.trade_traffic import PORT_DWELL
from nine.world import World


def accompany(world, departure, steps=17, index=0):
    """Move close to one merchant for successive in-world simulation seconds."""
    for second in range(steps):
        world.t = departure + second
        world.player.pos = Vector2(world.trade_traffic.snapshot(world.t)[index].pos)
        world._update_escort_contract(1.0)


def test_escort_requires_following_and_destination_arrival():
    world = World(seed=9, first_event=1e9)
    assert world.contract_action("escort")
    assert world.contracts["escort"]["convoy"] == 0
    assert not world.contract_action("escort")
    traffic = world.trade_traffic

    # Simply arriving at the port without accompanying the ship is not enough.
    world.t = PORT_DWELL + traffic.sailing_time + 1
    world.player.pos = Vector2(world.platform)
    world._update_escort_contract(1.0)
    assert not world.contracts["escort"]["arrived"]

    accompany(world, PORT_DWELL + 1)
    assert world.contracts["escort"]["close_seconds"] >= 15
    assert not world.contract_action("escort")
    world.t = PORT_DWELL + traffic.sailing_time + 1
    world.player.pos = Vector2(world.platform)
    world._update_escort_contract(1.0)
    assert world.contracts["escort"]["arrived"]
    before = world.captain.credits
    assert world.contract_action("escort")
    assert world.captain.credits == before + 450
    assert not world.contract_action("escort")
    assert world.captain.credits == before + 450


def test_escort_does_not_follow_from_distance_or_capsule():
    world = World(seed=9, first_event=1e9)
    assert world.contract_action("escort")
    for second in range(20):
        world.t = PORT_DWELL + 1 + second
        world.player.pos = Vector2(world.port)
        world._update_escort_contract(1.0)
    assert world.contracts["escort"]["close_seconds"] == 0
    world.in_capsule = True
    accompany(world, PORT_DWELL + 1)
    assert world.contracts["escort"]["close_seconds"] == 0
    assert not world.contract_action("escort")


def test_escort_renewal_from_platform_reverses_route():
    world = World(seed=9, first_event=1e9)
    world.active_port = "platform"
    assert world.contract_action("escort")
    state = world.contracts["escort"]
    assert state["origin"] == "platform"
    assert state["convoy"] == 0
    # Convoy 0 travels from platform to refuge in the second sailing leg.
    traffic = world.trade_traffic
    departure = 2 * PORT_DWELL + traffic.sailing_time + 1
    accompany(world, departure)
    world.t = traffic.period + 1
    world.player.pos = Vector2(world.port)
    world._update_escort_contract(1.0)
    assert state["arrived"]
    assert world.contract_action("escort")
    assert world.renew_contract("escort")
    again = world.contracts["escort"]
    assert again["cycle"] == 1 and again["convoy"] == 1
    assert again["origin"] == "platform"
    assert again["close_seconds"] == 0 and not again["arrived"]
    assert not world.contract_action("escort")


def test_escort_roundtrips_without_losing_voyage_progress():
    world = World(seed=9, first_event=1e9)
    world.contract_action("escort")
    accompany(world, PORT_DWELL + 1, steps=9)
    restored = save.from_dict(save.to_dict(world))
    assert restored.contracts == world.contracts
    accompany(restored, PORT_DWELL + 10, steps=9)
    restored.t = PORT_DWELL + restored.trade_traffic.sailing_time + 1
    restored.player.pos = Vector2(restored.platform)
    restored._update_escort_contract(1)
    assert restored.contracts["escort"]["arrived"]


def test_escort_rejects_corrupted_save_state_and_journal_shows_mission():
    world = World(seed=9, first_event=1e9)
    world.contract_action("escort")
    rows = {entry[0]: entry for entry in journal_entries(world)}
    assert rows["escort"][6] == "В РАБОТЕ"
    assert "конвой" in rows["escort"][2].lower()
    data = save.to_dict(world)
    data["contracts"]["escort"]["close_seconds"] = "1000"
    assert "escort" not in save.from_dict(data).contracts


def test_contract_board_has_five_missions_and_can_accept_escort():
    pygame.font.init()
    world = World(seed=9, first_event=1e9)
    port = PortUI(pygame.Surface((1280, 720)))
    port.tab = TABS.index("Контракты")
    port.sel = 3
    port.draw(world, 0.4)
    assert len([row for row in port.zones if row[1] == "row"]) == 5
    port.handle_key(pygame.K_RETURN, world)
    assert world.contracts["escort"]["status"] == "active"
