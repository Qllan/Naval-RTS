"""Master contract certificates redeem into a unique, non-retail module."""

import copy

import pygame

from nine import save
from nine.modules import MODULES
from nine.port_ui import PortUI, TABS
from nine.world import World


KEY = "guild_hold_mk2"


def master_reward(world):
    world.guild_reputation["port"] = 75
    assert world.contract_action("master")
    world.captain.cargo["condensate"] = 18
    assert world.contract_action("master")


def test_master_contract_earns_certificate_only_on_completion():
    w = World(seed=9, first_event=1e9)
    w.guild_reputation["port"] = 75
    assert w.contract_action("master")
    assert w.captain.guild_certificates == 0
    w.captain.cargo["condensate"] = 18
    assert w.contract_action("master")
    assert w.captain.guild_certificates == 1
    credits = w.captain.credits
    assert not w.contract_action("master")
    assert w.captain.credits == credits
    assert w.captain.guild_certificates == 1


def test_exchange_requires_rank_certificate_and_deducts_once():
    w = World(seed=9, first_event=1e9)
    assert not w.redeem_guild_certificate()
    master_reward(w)
    w.guild_reputation["port"] = 74
    assert not w.redeem_guild_certificate()
    w.guild_reputation["port"] = 75
    w.captain.debt = 1
    assert not w.redeem_guild_certificate()
    w.captain.debt = 0
    assert w.redeem_guild_certificate()
    assert w.captain.guild_certificates == 0
    assert w.captain.storage.count(KEY) == 1
    assert not w.redeem_guild_certificate()


def test_rare_module_cannot_be_bought_or_sold_for_credits():
    w = World(seed=9, first_event=1e9)
    assert KEY in MODULES
    assert MODULES[KEY].value == 30
    assert KEY not in [m.key for m in w.compatible(
        next(i for i, s in enumerate(w.player.hull.slots)
             if s.category == "utility"))]
    slot = next(i for i, s in enumerate(w.player.hull.slots)
                if s.category == "utility")
    assert "сертификат" in w.install_problem(slot, KEY)
    master_reward(w)
    assert w.redeem_guild_certificate()
    credits = w.captain.credits
    assert w.sell_from_storage(KEY) == 0
    assert KEY in w.captain.storage
    assert w.captain.credits == credits


def test_earned_module_installs_from_storage_and_adds_capacity():
    w = World(seed=9, first_event=1e9)
    master_reward(w)
    assert w.redeem_guild_certificate()
    slot = next(i for i, s in enumerate(w.player.hull.slots)
                if s.category == "utility")
    before = w.cargo_capacity
    old_module = w.player.fit[slot]
    assert w.install(slot, KEY, from_storage=True) is None
    assert w.cargo_capacity == before + 30 - (
        MODULES[old_module].value if old_module and
        getattr(MODULES[old_module], "effect", "") == "cargo" else 0)
    assert KEY not in w.captain.storage
    assert w.player.fit[slot] == KEY
    assert w.install_problem(slot, KEY) != None


def test_certificates_and_rare_module_survive_saving_and_migration():
    w = World(seed=9, first_event=1e9)
    master_reward(w)
    data = save.to_dict(w)
    loaded = save.from_dict(data)
    assert loaded.captain.guild_certificates == 1
    assert loaded.contracts == w.contracts
    w.redeem_guild_certificate()
    loaded = save.from_dict(save.to_dict(w))
    assert KEY in loaded.captain.storage
    old = copy.deepcopy(data)
    old["captain"].pop("guild_certificates")
    assert save.from_dict(old).captain.guild_certificates == 0
    corrupt = copy.deepcopy(data)
    corrupt["captain"]["guild_certificates"] = -10
    assert save.from_dict(corrupt).captain.guild_certificates == 0
    corrupt["captain"]["guild_certificates"] = "999"
    assert save.from_dict(corrupt).captain.guild_certificates == 0


def test_guild_certificate_action_visible_to_master_only():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    ui = PortUI(pygame.Surface((1280, 720)))
    ui.tab = TABS.index("Торговля")
    assert len(ui.trade_items(w)) == 8
    w.guild_reputation["port"] = 75
    assert len(ui.trade_items(w)) == 11
    master_reward(w)
    ui.sel = 10
    ui.draw(w, 0.4)
    assert len([z for z in ui.zones if z[1] == "row"]) == 11
    ui.handle_key(pygame.K_RETURN, w)
    assert w.captain.guild_certificates == 0
    assert KEY in w.captain.storage
    w.active_port = "platform"
    assert len(ui.trade_items(w)) == 8
