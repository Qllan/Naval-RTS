"""Market deliveries react to convoys, purchases, scarcity and save/load."""

import copy

import pygame
from nine import save
from nine.market import MAX_STOCK, arrivals_between
from nine.port_ui import PortUI, TABS
from nine.trade_traffic import PORT_DWELL
from nine.world import World


def test_convoy_arrival_replenishes_destination_once():
    world = World(seed=9, first_event=1e9)
    port_before = world.market_available("filament", "port")
    platform_before = world.market_available("salt", "platform")
    arrival = PORT_DWELL + world.trade_traffic.sailing_time
    world.t = arrival - 0.2
    world.market_last_time = arrival - 0.2
    world.t = arrival + 0.2
    world.update_market()
    assert world.market_available("salt", "platform") == platform_before + 20
    assert world.market_available("filament", "port") == port_before
    once = copy.deepcopy(world.market_stock)
    world.update_market()
    assert world.market_stock == once
    assert arrivals_between(world.trade_traffic, arrival - 0.2, arrival + 0.2)["platform"] == 1


def test_crossing_multiple_arrivals_counts_each_convoy_once():
    world = World(seed=9, first_event=1e9)
    traffic = world.trade_traffic
    world.t = traffic.period + 0.5
    world.update_market()
    # Two arrivals at each hub during the first complete traffic period.
    assert world.market_available("salt", "platform") == 45 + 2 * 20
    assert world.market_available("filament", "port") == 35 + 2 * 12
    unchanged = copy.deepcopy(world.market_stock)
    world.update_market()
    assert world.market_stock == unchanged


def test_stock_controls_purchases_and_reactive_prices():
    world = World(seed=9, first_event=1e9)
    world.captain.credits = 10000
    before = world.market_price("salt")
    world.market_stock["port"]["salt"] = 10
    shortage = world.market_price("salt")
    assert shortage > before
    assert world.buy_resource("salt")
    assert world.market_available("salt") == 0
    assert not world.buy_resource("salt")
    assert world.market_price("salt") >= shortage
    assert world.sell_resource("salt")
    assert world.market_available("salt") == 10
    assert world.market_price("salt", True) > world.market_price("salt")
    assert not world.buy_resource("salt", 11)


def test_market_save_roundtrip_and_legacy_migration():
    world = World(seed=9, first_event=1e9)
    world.t = world.trade_traffic.period / 2 + 1
    world.update_market()
    world.market_stock["port"]["salt"] = 13
    data = save.to_dict(world)
    restored = save.from_dict(data)
    assert restored.market_stock == world.market_stock
    assert restored.market_last_time == world.market_last_time
    restored.update_market()
    assert restored.market_stock == world.market_stock
    old = copy.deepcopy(data)
    del old["market"]
    legacy = save.from_dict(old)
    assert legacy.market_last_time == legacy.t
    first = copy.deepcopy(legacy.market_stock)
    legacy.update_market()
    assert legacy.market_stock == first


def test_invalid_saved_market_does_not_poison_inventory():
    world = World(seed=9, first_event=1e9)
    data = save.to_dict(world)
    data["market"]["stock"]["port"]["salt"] = -1
    restored = save.from_dict(data)
    assert restored.market_available("salt", "port") > 0
    data = save.to_dict(world)
    data["market"]["last_time"] = -10
    restored = save.from_dict(data)
    assert restored.market_last_time == restored.t


def test_trade_screen_displays_inventory_and_preserves_actions():
    pygame.font.init()
    world = World(seed=9, first_event=1e9)
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Торговля")
    rows = ui.trade_items(world)
    assert len(rows) == 8
    assert any("склад: 100" in label for label, _ in rows)
    world.captain.credits = 1000
    ui.sel = 0
    ui._activate(world)
    assert world.market_available("salt") == 90
    ui.draw(world, 0.4)


def test_delivery_capacity_is_bounded_even_after_long_time_skip():
    world = World(seed=9, first_event=1e9)
    world.t = world.trade_traffic.period * 100
    world.update_market()
    assert all(0 <= count <= MAX_STOCK for stock in world.market_stock.values()
               for count in stock.values())
