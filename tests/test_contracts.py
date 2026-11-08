"""Port-contract regression tests: acceptance, delivery, bounties, and save compatibility."""

from nine import save
from nine.world import World


def test_salt_contract_requires_cargo_and_consumes_only_required_amount():
    w = World(seed=9, first_event=1e9)
    assert w.contract_action("salt")
    assert not w.contract_action("salt")
    before = w.captain.credits
    w.captain.cargo["salt"] = 9
    assert not w.contract_action("salt")
    w.captain.cargo["salt"] = 13
    assert w.contract_action("salt")
    assert w.captain.cargo["salt"] == 3
    assert w.captain.credits == before + 250
    assert not w.contract_action("salt")
    assert w.captain.credits == before + 250


def test_bounty_counts_kills_only_after_acceptance():
    w = World(seed=9, first_event=1e9)
    w.captain.kills = 5
    assert w.contract_action("pirates")
    assert not w.contract_action("pirates")
    w.captain.kills += 1
    assert not w.contract_action("pirates")
    w.captain.kills += 1
    before = w.captain.credits
    assert w.contract_action("pirates")
    assert w.captain.credits == before + 350
    assert not w.contract_action("pirates")


def test_contracts_survive_save_and_legacy_defaults():
    w = World(seed=9, first_event=1e9)
    w.contract_action("salt")
    w.contract_action("pirates")
    w.captain.kills = 1
    data = save.to_dict(w)
    restored = save.from_dict(data)
    assert restored.contracts == w.contracts
    assert restored.contract_action("pirates") is False
    restored.captain.kills = 2
    assert restored.contract_action("pirates")
    assert save.from_dict({k: v for k, v in data.items() if k != "contracts"}).contracts == {}


def test_untrusted_contract_data_is_ignored():
    w = World(seed=9, first_event=1e9)
    data = save.to_dict(w)
    data["contracts"] = {
        "unknown": {"status": "active", "start_kills": 0},
        "pirates": {"status": "active", "start_kills": -3},
        "salt": {"status": "done", "start_kills": 0},
    }
    restored = save.from_dict(data)
    assert restored.contracts == {"salt": {"status": "done", "start_kills": 0}}
