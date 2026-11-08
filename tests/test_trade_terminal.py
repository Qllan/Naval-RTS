"""Trade terminal regressions: independent rows, fair pricing, and mouse input."""

import pygame

from nine.gfx import ui
from nine.port_ui import PortUI, TABS
from nine.world import World


def setup_market():
    pygame.font.init()
    ui.Fonts.reset()
    world = World(seed=9, first_event=1e9)
    world.captain.credits = 20000
    port = PortUI(pygame.Surface((1280, 720)))
    port.tab = TABS.index("Торговля")
    return world, port


def test_trade_tab_lists_buy_and_sell_for_each_resource():
    world, port = setup_market()
    assert len(port.service_items(world)) == 8
    assert len(port.trade_items(world)) == 8
    assert port._count(world) == 8
    port.draw(world, 0.4)
    assert len([z for z in port.zones if z[1] == "tab"]) == len(TABS) == 6
    assert len([z for z in port.zones if z[1] == "row"]) == 8


def test_keyboard_buy_and_sell_only_selected_commodity():
    world, port = setup_market()
    initial = world.captain.credits
    port.sel = 0  # buy salt
    port.handle_key(pygame.K_RETURN, world)
    assert world.captain.cargo["salt"] == 10
    assert world.captain.credits < initial
    port.sel = 1  # sell salt
    port.handle_key(pygame.K_RETURN, world)
    assert "salt" not in world.captain.cargo
    assert world.captain.credits < initial  # same-port spread prevents arbitrage


def test_trade_mouse_selects_row_and_changes_cargo():
    world, port = setup_market()
    port.draw(world, 0.4)
    buy = next(r for r, kind, idx in port.zones if kind == "row" and idx == 2)
    port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, {"pos": buy.center, "button": 1}), world)
    assert world.captain.cargo.get("condensate") == 10


def test_partial_sale_does_not_empty_other_cargo():
    world, _ = setup_market()
    world.captain.cargo = {"salt": 13, "filament": 2}
    initial = world.captain.credits
    value = 10 * world.market_price("salt")
    assert world.sell_resource("salt")
    assert world.captain.cargo == {"salt": 3, "filament": 2}
    assert world.captain.credits == initial + value
    assert not world.sell_resource("unknown")


def test_price_comparison_is_read_only_and_save_compatible():
    from nine import save
    world, port = setup_market()
    initial = world.captain.credits
    other = "platform"
    assert world.market_price("salt", port_key=other) > world.market_price("salt")
    port.draw(world, 0.4)
    assert world.captain.credits == initial
    restored = save.from_dict(save.to_dict(world))
    assert restored.captain.credits == initial
