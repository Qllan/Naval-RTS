"""Repeatable contracts must change goals without duplicating payouts."""

from pygame.math import Vector2

from nine import save
from nine.world import World
from nine.port_ui import PortUI, TABS
import pygame


def test_salt_contract_can_be_renewed_after_claim_only():
    w = World(seed=17, first_event=1e9)
    assert not w.renew_contract("salt")
    assert w.contract_action("salt")
    assert not w.renew_contract("salt")
    w.captain.cargo["salt"] = 10
    assert w.contract_action("salt")
    credits = w.captain.credits
    assert not w.contract_action("salt")
    assert w.captain.credits == credits
    assert w.renew_contract("salt")
    assert w.contracts["salt"]["cycle"] == 1
    name, amount, reward = w.contract_terms("salt")
    assert 8 <= amount <= 18 and reward > 0
    assert not w.renew_contract("salt")
    w.captain.cargo["salt"] = amount
    assert w.contract_action("salt")
    assert w.captain.credits == credits + reward
    assert not w.contract_action("salt")


def test_renewed_bounty_counts_new_kills_only_and_saves():
    w = World(seed=21, first_event=1e9)
    assert w.contract_action("pirates")
    w.captain.kills = 2
    assert w.contract_action("pirates")
    assert w.renew_contract("pirates")
    amount = w.contract_terms("pirates")[1]
    assert w.contracts["pirates"]["start_kills"] == 2
    assert not w.contract_action("pirates")
    restored = save.from_dict(save.to_dict(w))
    assert restored.contracts == w.contracts
    assert restored.contract_terms("pirates") == w.contract_terms("pirates")
    restored.captain.kills += amount
    assert restored.contract_action("pirates")


def test_repeated_scout_moves_target_and_requires_revisit():
    w = World(seed=9, first_event=1e9)
    assert w.contract_action("scout")
    original = w.scout_position()
    w.player.pos = Vector2(original)
    w._update_memory(0.3, 0.0)
    assert w.contracts["scout"]["explored"]
    assert w.contract_action("scout")
    assert w.renew_contract("scout")
    new_target = w.scout_position()
    assert new_target != original
    assert not w.contracts["scout"]["explored"]
    assert not w.contract_action("scout")
    w.player.pos = new_target
    w._memory_cd = 0
    w._update_memory(0.3, 0.0)
    assert w.contract_action("scout")


def test_contract_board_renews_only_completed_job():
    pygame.font.init()
    w = World(seed=9, first_event=1e9)
    p = PortUI(pygame.Surface((1280, 720)))
    p.tab = TABS.index("Контракты")
    p._activate(w)
    w.captain.cargo["salt"] = 10
    p._activate(w)
    paid = w.captain.credits
    p._activate(w)
    assert w.captain.credits == paid
    assert w.contracts["salt"]["status"] == "active"
    assert w.contracts["salt"]["cycle"] == 1


def test_invalid_cycle_does_not_corrupt_save():
    w = World(seed=9, first_event=1e9)
    w.contract_action("salt")
    d = save.to_dict(w)
    d["contracts"]["salt"]["cycle"] = "999"
    assert save.from_dict(d).contracts == {}
