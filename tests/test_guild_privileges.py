"""Rank-gated guild merchandise and a persistent current-hull cargo refit."""

import copy
import math

import pygame

from nine import save
from nine.port_ui import PortUI, TABS
from nine.world import World


def test_goods_locked_until_trusted_and_have_normal_market_coverage():
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 20000
    stock = w.market_available("filament")
    assert not w.buy_guild_goods()
    assert w.market_available("filament") == stock
    w.guild_reputation["port"] = 50
    original_buy_price = w.market_price("filament", buying=True)
    assert w.guild_goods_cost() == math.ceil(original_buy_price * 5 * 0.9)
    spent = w.guild_goods_cost()
    assert w.buy_guild_goods()
    assert w.market_available("filament") == stock - 5
    assert w.captain.cargo["filament"] == 5
    assert w.captain.credits == 20000 - spent
    assert w.guild_goods_cost() > w.market_price("filament") * 5


def test_guild_goods_refuse_empty_stock_debt_and_full_hold():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = 50
    w.captain.credits = 10000
    w.market_stock["port"]["filament"] = 4
    assert not w.buy_guild_goods()
    w.market_stock["port"]["filament"] = 20
    w.captain.debt = 1
    assert not w.buy_guild_goods()
    w.captain.debt = 0
    w.captain.cargo["salt"] = w.cargo_capacity - 4
    assert not w.buy_guild_goods()
    assert w.market_available("filament") == 20


def test_hold_upgrade_is_rank_gated_once_and_ship_specific():
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 20000
    capacity = w.cargo_capacity
    assert not w.buy_guild_hold_upgrade()
    w.guild_reputation["port"] = 75
    assert w.buy_guild_hold_upgrade()
    assert w.player.guild_hold_upgrade
    assert w.cargo_capacity == capacity + 12
    balance = w.captain.credits
    assert not w.buy_guild_hold_upgrade()
    assert w.captain.credits == balance
    new_hull = next(k for k, hull in __import__(
        "nine.hulls", fromlist=["HULLS"]).HULLS.items()
                    if hull.purchasable and k != w.player.hull.key)
    assert w.buy_hull(new_hull) is None
    assert not w.player.guild_hold_upgrade


def test_hold_upgrade_save_and_invalid_legacy_values():
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 10000
    w.guild_reputation["port"] = 75
    assert w.buy_guild_hold_upgrade()
    old_capacity = w.cargo_capacity
    restored = save.from_dict(save.to_dict(w))
    assert restored.player.guild_hold_upgrade
    assert restored.cargo_capacity == old_capacity
    assert not restored.buy_guild_hold_upgrade()
    legacy = save.to_dict(w)
    legacy["ship"].pop("guild_hold_upgrade")
    assert not save.from_dict(legacy).player.guild_hold_upgrade
    tampered = save.to_dict(w)
    tampered["ship"]["guild_hold_upgrade"] = "true"
    assert not save.from_dict(tampered).player.guild_hold_upgrade


def test_guild_trade_rows_are_rank_local_and_clickable():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 20000
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Торговля")
    assert len(ui.trade_items(w)) == 8
    w.guild_reputation["port"] = 50
    assert len(ui.trade_items(w)) == 9
    w.guild_reputation["port"] = 75
    assert len(ui.trade_items(w)) == 11
    ui.sel = 9
    ui.draw(w, 0.4)
    assert len([z for z in ui.zones if z[1] == "row"]) == 11
    ui.handle_key(pygame.K_RETURN, w)
    assert w.player.guild_hold_upgrade
    w.active_port = "platform"
    assert len(ui.trade_items(w)) == 8


def test_hold_upgrade_makes_extra_cargo_space_usable():
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 20000
    w.guild_reputation["port"] = 75
    old = w.cargo_capacity
    w.captain.cargo["salt"] = old
    assert not w.buy_resource("salt")
    assert w.buy_guild_hold_upgrade()
    assert w.buy_resource("salt", quantity=10)
    assert w.cargo_used == old + 10
    assert not w.undock_problems()
