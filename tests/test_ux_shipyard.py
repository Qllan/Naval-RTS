"""UX 2.1: shipyard selects, previews and explicitly buys a hull."""

import pygame

from nine.gfx import ui
from nine.hulls import PLAYER_HULLS
from nine.port_ui import PortUI, hull_purchase_issue, shipyard_layout_regions
from nine.ship import Ship
from nine.world import World


def prepare_shipyard():
    pygame.font.init()
    ui.Fonts.reset()
    world = World(seed=16, first_event=1e9)
    world.captain.credits = 30000
    world.player = Ship("manta", world.port)
    screen = pygame.Surface((1280, 720))
    port = PortUI(screen)
    port.tab = 1
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS) if h.key == "bastion")
    return world, port


def click(port, world, rect):
    return port.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1), world)


def test_ux_shipyard_regions_give_hero_dominant_width():
    left, center, right = shipyard_layout_regions(pygame.Rect(124, 156, 1032, 470))
    assert center.w > right.w > left.w
    assert left.right < center.left < center.right < right.left
    assert left.top == center.top == right.top
    assert right.right <= 1156


def test_selecting_hull_in_catalogue_does_not_spend_credits_or_replace_ship():
    world, port = prepare_shipyard()
    cash, original = world.captain.credits, world.player
    port.draw(world, 0.4)
    row = next(r for r, kind, idx in port.zones
               if kind == "row" and PLAYER_HULLS[idx].key == "needle")
    click(port, world, row)
    assert PLAYER_HULLS[port.sel].key == "needle"
    assert world.player is original
    assert world.captain.credits == cash


def test_hovering_catalogue_does_not_switch_selected_ship():
    world, port = prepare_shipyard()
    before = port.sel
    port.draw(world, 0.4)
    row = next(r for r, kind, idx in port.zones
               if kind == "row" and PLAYER_HULLS[idx].key == "needle")
    port.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=row.center), world)
    assert port.sel == before


def test_explicit_purchase_button_changes_hull_and_charges_exact_offer():
    world, port = prepare_shipyard()
    old_ship = world.player
    old_funds = world.captain.credits
    _, cost = world.hull_offer("bastion")
    port.draw(world, 0.4)
    purchase = next(r for r, kind, name in port.zones
                    if kind == "button" and name == "purchase_hull")
    click(port, world, purchase)
    assert world.player.hull.key == "bastion"
    assert world.player is not old_ship
    assert world.captain.credits == old_funds - cost
    assert len(world.captain.storage) >= sum(k is not None for k in old_ship.fit)


def test_ux_shipyard_blocks_owned_ship_debt_and_low_funds():
    world, port = prepare_shipyard()
    current = next(h for h in PLAYER_HULLS if h.key == "manta")
    target = next(h for h in PLAYER_HULLS if h.key == "bastion")
    assert hull_purchase_issue(world, current) == "УЖЕ В ВАШЕМ ФЛОТЕ"
    assert hull_purchase_issue(world, target) is None
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS) if h.key == "manta")
    port.draw(world, 0.4)
    assert not any(kind == "button" and idx == "purchase_hull" for _, kind, idx in port.zones)
    port.sel = next(i for i, h in enumerate(PLAYER_HULLS) if h.key == "bastion")
    world.captain.credits = 0
    assert "НЕ ХВАТАЕТ" in hull_purchase_issue(world, target)
    port.draw(world, 0.4)
    assert not any(kind == "button" and idx == "purchase_hull" for _, kind, idx in port.zones)
    world.captain.credits = 30000
    world.captain.debt = 100
    assert hull_purchase_issue(world, target) == "ПОГАСИТЕ ДОЛГ"


def test_ux_shipyard_enter_remains_explicit_keyboard_purchase():
    world, port = prepare_shipyard()
    port.handle_key(pygame.K_RETURN, world)
    assert world.player.hull.key == "bastion"


def test_ux_shipyard_review_png_is_real_ui(tmp_path):
    from tools.preview_ux_shipyard import render
    output = tmp_path / "shipyard-v2.png"
    render(output)
    assert output.exists() and output.stat().st_size > 25000
    img = pygame.image.load(str(output))
    assert img.get_size() == (2616, 1596)



def test_owned_ship_offer_is_not_described_as_a_trade_in_purchase():
    world, port = prepare_shipyard()
    port.sel = next(i for i, hull in enumerate(PLAYER_HULLS)
                    if hull.key == world.player.hull.key)
    seen = []
    original = port.text

    def record(value, pos, *args, **kwargs):
        seen.append(str(value))
        return original(value, pos, *args, **kwargs)

    port.text = record
    port.draw(world, 0.4)
    assert "ТЕКУЩИЙ КОРПУС" in seen
    assert "УЖЕ ВО ФЛОТЕ" in seen
    assert "К ДОПЛАТЕ С УЧЁТОМ ОБМЕНА" not in seen
    assert not any(kind == "button" and name == "purchase_hull"
                   for _, kind, name in port.zones)
