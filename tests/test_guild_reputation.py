"""Per-port guild reputation, premium job unlocks, save safety and discounts."""

import copy
import math

import pygame

from nine import save
from nine.port_ui import PortUI, TABS
from nine.reputation import PARTNER_AT, TRUSTED_AT, rank, discount
from nine.screens import journal_entries
from nine.world import World


def test_reputation_earned_once_from_contract_completion():
    w = World(seed=9, first_event=1e9)
    assert w.guild_reputation == {"port": 0, "platform": 0}
    assert w.contract_action("salt")
    assert w.guild_reputation["port"] == 0
    w.captain.cargo["salt"] = 10
    assert w.contract_action("salt")
    credits = w.captain.credits
    assert w.guild_reputation["port"] == 5
    assert not w.contract_action("salt")
    assert w.guild_reputation["port"] == 5
    assert w.captain.credits == credits


def test_port_reputation_is_independent_and_capped():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = 99
    w.guild_reputation["platform"] = 9
    w.active_port = "port"
    assert w.contract_action("salt")
    w.captain.cargo["salt"] = 10
    assert w.contract_action("salt")
    assert w.guild_reputation == {"port": 100, "platform": 9}
    assert w.guild_rank() == "Мастер гильдии"
    w.active_port = "platform"
    assert w.guild_rank() == "Новичок"
    assert w.service_discount() == 0


def test_service_tiers_discount_repairs_and_rearming():
    w = World(seed=9, first_event=1e9)
    w.player.hp = max(1, w.player.hp - 40)
    cost = w.repair_cost()
    assert cost > 0
    assert rank(0) == "Новичок"
    assert discount(PARTNER_AT) == 0.05
    assert discount(TRUSTED_AT) == 0.10
    w.guild_reputation["port"] = PARTNER_AT
    assert w.repair_cost() == math.ceil(cost * 0.95)
    w.guild_reputation["port"] = TRUSTED_AT
    assert w.repair_cost() == math.ceil(cost * 0.9)
    w.captain.credits = 5000
    old = w.captain.credits
    assert w.repair()
    assert w.captain.credits == old - math.ceil(cost * 0.9)
    w.player.hp -= 10
    w.active_port = "platform"
    assert w.service_discount() == 0


def test_guild_job_unlocks_at_20_and_pays_only_once():
    w = World(seed=9, first_event=1e9)
    assert not w.contract_action("guild")
    assert "20" in w.contract_label("guild")
    w.guild_reputation["port"] = PARTNER_AT
    assert w.contract_action("guild")
    state = copy.deepcopy(w.contracts["guild"])
    assert state["amount"] == 12
    assert state["hub"] == "port"
    assert w.contract_terms("guild")[2] == 600
    w.captain.cargo["salt"] = 12
    w.active_port = "platform"
    assert not w.contract_action("guild")
    w.active_port = "port"
    credits = w.captain.credits
    stock = w.market_available("salt")
    assert w.contract_action("guild")
    assert w.captain.credits == credits + 600
    assert w.market_available("salt") == stock + 12
    assert w.guild_reputation["port"] == PARTNER_AT + 10
    assert not w.contract_action("guild")
    assert w.captain.credits == credits + 600
    assert w.renew_contract("guild")
    assert w.contracts["guild"]["cycle"] == 1
    assert not w.renew_contract("guild")


def test_save_roundtrip_legacy_and_invalid_reputation():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation = {"port": 50, "platform": 24}
    w.contract_action("guild")
    restored = save.from_dict(save.to_dict(w))
    assert restored.guild_reputation == w.guild_reputation
    assert restored.contracts == w.contracts
    old = save.to_dict(w)
    old.pop("guild_reputation")
    assert save.from_dict(old).guild_reputation == {"port": 0, "platform": 0}
    data = save.to_dict(w)
    data["guild_reputation"]["port"] = -1
    assert save.from_dict(data).guild_reputation == {"port": 0, "platform": 0}
    data = save.to_dict(w)
    data["guild_reputation"]["port"] = True
    assert save.from_dict(data).guild_reputation == {"port": 0, "platform": 0}
    data = save.to_dict(w)
    data["contracts"]["guild"]["amount"] = 999
    assert "guild" not in save.from_dict(data).contracts


def test_guild_order_visible_in_journal_and_board():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = 25
    assert w.contract_action("guild")
    entries = {row[0]: row for row in journal_entries(w)}
    assert entries["guild"][1] == "Гильдейский заказ"
    assert entries["guild"][6] == "В РАБОТЕ"
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Контракты")
    ui.sel = 5
    ui.draw(w, 0.5)
    assert len([v for v in ui.zones if v[1] == "row"]) == 7
    assert w.contracts["guild"]["status"] == "active"
