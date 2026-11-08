"""Master guild tier, local service discounts and repeatable elite deliveries."""

import copy
import math

import pygame

from nine import save
from nine.port_ui import PortUI, TABS
from nine.reputation import MASTER_AT, discount, next_rank, rank
from nine.screens import journal_entries
from nine.world import World


def test_master_rank_and_progress_milestones():
    assert rank(49) == "Партнёр гильдии"
    assert rank(50) == "Доверенный партнёр"
    assert rank(MASTER_AT) == "Мастер гильдии"
    assert discount(74) == 0.10
    assert discount(75) == 0.15
    assert discount(100) == 0.15
    assert next_rank(19) == (20, "Партнёр")
    assert next_rank(25) == (50, "Доверенный")
    assert next_rank(50) == (75, "Мастер")
    assert next_rank(90) == (100, "Максимальный ранг")


def test_master_discount_is_local_and_matches_paid_repair():
    w = World(seed=9, first_event=1e9)
    w.player.hp = max(1, w.player.hp - 40)
    base_cost = w.repair_cost()
    w.guild_reputation["port"] = MASTER_AT
    w.guild_reputation["platform"] = 10
    assert w.service_discount() == 0.15
    assert w.repair_cost() == math.ceil(base_cost * 0.85)
    w.captain.credits = 5000
    balance = w.captain.credits
    assert w.repair()
    assert w.captain.credits == balance - math.ceil(base_cost * 0.85)
    w.player.hp -= 20
    w.active_port = "platform"
    assert w.service_discount() == 0


def test_master_job_requires_local_reputation_and_fulfills_once():
    w = World(seed=9, first_event=1e9)
    assert not w.contract_action("master")
    assert "75" in w.contract_label("master")
    w.guild_reputation["port"] = MASTER_AT
    assert w.contract_action("master")
    state = w.contracts["master"]
    assert state["hub"] == "port"
    assert state["amount"] == 18
    assert w.contract_terms("master")[2] == 900
    w.captain.cargo["condensate"] = 18
    w.active_port = "platform"
    assert not w.contract_action("master")
    w.active_port = "port"
    prior_balance = w.captain.credits
    prior_stock = w.market_available("condensate")
    assert w.contract_action("master")
    assert w.captain.credits == prior_balance + 900
    assert w.market_available("condensate") == prior_stock + 18
    assert "condensate" not in w.captain.cargo
    assert w.guild_reputation["port"] == 87
    assert not w.contract_action("master")
    assert w.captain.credits == prior_balance + 900


def test_master_job_renewal_freezes_hub_and_disallows_double_claim():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = MASTER_AT
    assert w.contract_action("master")
    w.captain.cargo["condensate"] = 18
    assert w.contract_action("master")
    assert w.renew_contract("master")
    state = copy.deepcopy(w.contracts["master"])
    assert state["cycle"] == 1 and state["hub"] == "port"
    assert not w.renew_contract("master")
    w.active_port = "platform"
    assert not w.contract_action("master")
    assert w.contracts["master"] == state


def test_master_save_roundtrip_legacy_reputation_and_tampering():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = MASTER_AT
    w.contract_action("master")
    data = save.to_dict(w)
    reloaded = save.from_dict(data)
    assert reloaded.contracts == w.contracts
    assert reloaded.guild_reputation == w.guild_reputation
    invalid = copy.deepcopy(data)
    invalid["contracts"]["master"]["reward"] = 900000
    assert "master" not in save.from_dict(invalid).contracts
    invalid = copy.deepcopy(data)
    invalid["contracts"]["master"]["hub"] = "unknown"
    assert "master" not in save.from_dict(invalid).contracts
    old = copy.deepcopy(data)
    old.pop("guild_reputation")
    old["contracts"].pop("master")
    assert save.from_dict(old).guild_reputation == {"port": 0, "platform": 0}


def test_master_contract_journal_and_seventh_port_row():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = MASTER_AT
    assert w.contract_action("master")
    rows = {row[0]: row for row in journal_entries(w)}
    assert "master" in rows
    assert rows["master"][6] == "В РАБОТЕ"
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Контракты")
    ui.sel = 6
    ui.draw(w, 0.4)
    entries = [z for z in ui.zones if z[1] == "row"]
    assert len(entries) == 7
    assert entries[-1][0].bottom < 700
    assert ui._count(w) == 7
