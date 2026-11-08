"""Urgent delivery contracts are shortage-based, persistent, and single-use."""

import copy

import pygame

from nine import save
from nine.port_ui import PortUI, TABS
from nine.screens import journal_entries
from nine.world import World


def test_urgent_offer_is_created_from_real_shortage():
    w = World(seed=9, first_event=1e9)
    offer = w.urgent_offer()
    assert offer is not None
    assert offer["origin"] == "port"
    assert offer["destination"] == "platform"
    assert offer["kind"] == "salt"
    assert offer["amount"] == 10
    assert offer["reward"] > 300
    w.market_stock["platform"]["salt"] = 80
    assert w.urgent_offer() is None
    assert not w.contract_action("urgent")
    assert "нет" in w.contract_label("urgent")


def test_urgent_offer_is_frozen_when_accepted():
    w = World(seed=9, first_event=1e9)
    assert w.contract_action("urgent")
    saved_terms = w.contract_terms("urgent")
    saved_state = copy.deepcopy(w.contracts["urgent"])
    w.market_stock["platform"]["salt"] = 180
    assert w.contract_terms("urgent") == saved_terms
    assert w.contracts["urgent"] == saved_state
    assert w.contract_label("urgent").startswith("Срочная поставка")


def test_urgent_delivery_requires_destination_and_consumes_cargo_once():
    w = World(seed=9, first_event=1e9)
    w.captain.credits = 5000
    assert w.contract_action("urgent")
    terms = w.contracts["urgent"]
    assert w.buy_resource("salt")
    assert w.captain.cargo["salt"] == 10
    assert not w.contract_action("urgent")  # wrong destination
    w.active_port = "platform"
    stock = w.market_available("salt")
    credits = w.captain.credits
    reward = terms["reward"]
    assert w.contract_action("urgent")
    assert "salt" not in w.captain.cargo
    assert w.market_available("salt") == stock + 10
    assert w.captain.credits == credits + reward
    assert not w.contract_action("urgent")
    assert w.captain.credits == credits + reward


def test_platform_shortage_demand_uses_other_direction():
    w = World(seed=9, first_event=1e9)
    w.active_port = "platform"
    offer = w.urgent_offer()
    assert offer["kind"] == "filament"
    assert offer["destination"] == "port"
    assert w.contract_action("urgent")
    assert w.contracts["urgent"]["kind"] == "filament"
    w.captain.cargo["filament"] = 10
    w.active_port = "port"
    assert w.contract_action("urgent")


def test_urgent_can_renew_only_if_another_shortage_exists():
    w = World(seed=9, first_event=1e9)
    w.contract_action("urgent")
    w.captain.cargo["salt"] = 10
    w.active_port = "platform"
    assert w.contract_action("urgent")
    assert w.renew_contract("urgent")
    second = w.contracts["urgent"]
    assert second["cycle"] == 1
    assert second["origin"] == "platform"
    assert second["destination"] == "port"
    assert second["kind"] == "filament"
    assert not w.renew_contract("urgent")
    w.captain.cargo["filament"] = 10
    w.active_port = "port"
    assert w.contract_action("urgent")
    w.market_stock["platform"]["salt"] = 100
    assert not w.renew_contract("urgent")
    assert w.contracts["urgent"]["status"] == "done"


def test_urgent_save_migration_validation_and_journal():
    w = World(seed=9, first_event=1e9)
    w.contract_action("urgent")
    row = next(row for row in journal_entries(w) if row[0] == "urgent")
    assert row[6] == "В РАБОТЕ"
    assert "Торговая платформа" in row[2]
    restored = save.from_dict(save.to_dict(w))
    assert restored.contracts == w.contracts
    data = save.to_dict(w)
    data["contracts"]["urgent"]["reward"] = "infinite"
    assert "urgent" not in save.from_dict(data).contracts
    data = save.to_dict(w)
    data["contracts"]["urgent"]["destination"] = "port"
    assert "urgent" not in save.from_dict(data).contracts


def test_urgent_contract_row_can_be_accepted_by_keyboard():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Контракты")
    ui.sel = 4
    ui.draw(w, 0.4)
    assert len([z for z in ui.zones if z[1] == "row"]) == 7
    ui.handle_key(pygame.K_RETURN, w)
    assert w.contracts["urgent"]["status"] == "active"
