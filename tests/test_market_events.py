"""Market bulletins, price surges and disrupted convoy deliveries."""

import copy

import pygame

from nine import save
from nine.market import ARRIVAL_CARGO, apply_deliveries, new_stocks
from nine.market_events import (
    EVENT_DURATION, EVENT_PERIOD, EVENT_START,
    current_event, delivery_fraction, event_for_cycle, latest_news,
)
from nine.port_ui import PortUI, TABS
from nine.world import World


def test_market_news_cycle_and_expiration_are_deterministic():
    assert current_event(9, 0) is None
    first = event_for_cycle(9, 0)
    assert first["type"] == "demand"
    assert current_event(9, first["start"] + 1) == first
    assert current_event(9, first["end"]) is None
    assert "СЕЙЧАС" in latest_news(9, first["start"] + 1)
    assert "Архив" in latest_news(9, first["end"] + 1)
    second = event_for_cycle(9, 1)
    assert second["type"] == "disruption"
    assert event_for_cycle(9, 1) == second
    assert second["start"] == EVENT_START + EVENT_PERIOD
    assert second["end"] - second["start"] == EVENT_DURATION


def test_demand_surges_only_affect_target_good_and_hub():
    world = World(seed=9, first_event=1e9)
    event = event_for_cycle(9, 0)
    world.t = event["start"] - 1
    before = world.market_price(event["kind"], port_key=event["hub"])
    world.t = event["start"] + 1
    during = world.market_price(event["kind"], port_key=event["hub"])
    assert during > before
    other = "port" if event["hub"] == "platform" else "platform"
    world.t = event["start"] - 1
    other_before = world.market_price(event["kind"], port_key=other)
    world.t = event["start"] + 1
    assert world.market_price(event["kind"], port_key=other) == other_before
    assert world.market_price(event["kind"], buying=True,
                              port_key=event["hub"]) > during
    world.t = event["end"]
    assert world.market_price(event["kind"], port_key=event["hub"]) == before


def test_disruption_halves_matching_convoy_delivery_and_never_duplicates():
    world = World(seed=9, first_event=1e9)
    traffic = world.trade_traffic
    ev = event_for_cycle(9, 1)
    # Find a real arrival inside the event window for the target good and hub.
    period = traffic.period
    offset_arrivals = ((0.0, period / 2),)
    from nine.trade_traffic import PORT_DWELL
    arrival_phase = (PORT_DWELL + traffic.sailing_time
                     if ev["hub"] == "platform" else period)
    arrivals = [arrival_phase - offset + n * period
                for offset in (0, period / 2)
                for n in range(12)]
    match = next(a for a in arrivals if ev["start"] < a < ev["end"])
    assert delivery_fraction(9, match, ev["hub"], ev["kind"]) == 0.5
    stock = new_stocks()
    old = copy.deepcopy(stock)
    counts = apply_deliveries(stock, traffic, match - 0.01, match + 0.01, seed=9)
    assert counts[ev["hub"]] == 1
    assert stock[ev["hub"]][ev["kind"]] == (
        old[ev["hub"]][ev["kind"]] + ARRIVAL_CARGO[ev["hub"]][ev["kind"]] // 2)
    same = copy.deepcopy(stock)
    again = apply_deliveries(stock, traffic, match + 0.01, match + 0.01, seed=9)
    assert stock == same
    assert sum(again.values()) == 0


def test_save_load_retains_prices_event_phase_and_delivery_cursor():
    world = World(seed=9, first_event=1e9)
    world.t = EVENT_START + 10
    world.update_market()
    price = world.market_price(event_for_cycle(9, 0)["kind"],
                               port_key=event_for_cycle(9, 0)["hub"])
    restored = save.from_dict(save.to_dict(world))
    assert restored.market_event() == world.market_event()
    assert restored.market_bulletin() == world.market_bulletin()
    assert restored.market_stock == world.market_stock
    assert restored.market_last_time == world.market_last_time
    assert restored.market_price(event_for_cycle(9, 0)["kind"],
                                 port_key=event_for_cycle(9, 0)["hub"]) == price
    snapshot = copy.deepcopy(restored.market_stock)
    restored.update_market()
    assert restored.market_stock == snapshot


def test_market_news_appears_in_trade_terminal_without_side_effects():
    pygame.font.init()
    world = World(seed=9, first_event=1e9)
    world.t = EVENT_START + 2
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Торговля")
    prior = (world.captain.credits, copy.deepcopy(world.market_stock))
    ui.draw(world, 0.4)
    assert world.market_bulletin().startswith("СЕЙЧАС")
    assert prior == (world.captain.credits, world.market_stock)
