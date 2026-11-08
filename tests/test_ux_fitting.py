"""UX 2.0 fitting decisions: ship first, no accidental purchase, real hitboxes."""

import pygame

from nine.gfx import ui
from nine.port_ui import PortUI, fitting_layout_regions
from nine.ship import Ship
from nine.world import World


def setup_port(hull="manta"):
    pygame.font.init()
    ui.Fonts.reset()
    screen = pygame.Surface((1280, 720))
    world = World(seed=11, first_event=1e9)
    world.captain.credits = 10000
    world.player = Ship(hull, world.port)
    port = PortUI(screen)
    port.tab = 2
    port.sel = next(i for i, s in enumerate(world.player.hull.slots)
                    if s.category == "reactor")
    return world, port


def mouse_event(kind, rect):
    return pygame.event.Event(kind, pos=rect.center, button=1)


def test_ux_fitting_has_largest_center_hero_and_separate_action_pane():
    body = pygame.Rect(124, 156, 1032, 470)
    left, center, right = fitting_layout_regions(body)
    assert center.w > right.w > left.w
    assert left.right < center.left and center.right < right.left
    assert left.top == center.top == right.top
    assert right.right <= body.right
    assert all(v.bottom <= body.bottom for v in (left, center, right))


def test_ux_slot_click_opens_choices_without_changing_inventory():
    world, port = setup_port()
    initial_fit = list(world.player.fit)
    original_credits = world.captain.credits
    port.draw(world, 0.4)
    first_slot = next(rect for rect, kind, index in port.zones
                      if kind == "slot" and index == port.sel)
    port.handle_event(mouse_event(pygame.MOUSEBUTTONDOWN, first_slot), world)
    assert port.picker and port.slot == port.sel
    assert world.captain.credits == original_credits
    assert list(world.player.fit) == initial_fit


def test_ux_clicking_a_candidate_is_preview_not_purchase_then_explicit_install():
    world, port = setup_port()
    port.picker = True
    port.slot = port.sel
    item = next(i for i, (src, key) in enumerate(port.picker_items(world))
                if key != world.player.fit[port.sel] and
                world.install_problem(port.slot, key, from_storage=(src == "storage")) is None)
    port.pick_sel = item
    old_fit = list(world.player.fit)
    old_cash = world.captain.credits
    port.draw(world, 0.4)
    candidate_zone = next(r for r, kind, index in port.zones
                          if kind == "pick" and index == item)
    port.handle_event(mouse_event(pygame.MOUSEBUTTONDOWN, candidate_zone), world)
    port.handle_event(mouse_event(pygame.MOUSEBUTTONUP, candidate_zone), world)
    assert list(world.player.fit) == old_fit
    assert world.captain.credits == old_cash
    port.draw(world, 0.4)
    action = next(r for r, kind, index in port.zones
                  if kind == "button" and index == "install")
    _, selected_key = port.picker_items(world)[item]
    port.handle_event(mouse_event(pygame.MOUSEBUTTONDOWN, action), world)
    assert world.player.fit[port.slot] == selected_key
    assert not port.picker


def test_ux_blocked_install_button_has_no_active_hitbox():
    world, port = setup_port()
    port.picker = True
    port.slot = port.sel
    blocked = [i for i, (src, key) in enumerate(port.picker_items(world))
               if world.install_problem(port.slot, key, from_storage=(src == "storage"))]
    if not blocked:
        # A depleted budget makes normal shop entries unavailable.
        world.captain.credits = 0
        blocked = [i for i, (src, key) in enumerate(port.picker_items(world))
                   if world.install_problem(port.slot, key, from_storage=(src == "storage"))]
    assert blocked
    port.pick_sel = blocked[0]
    port.draw(world, 0.4)
    assert not any(kind == "button" and name == "install" for _, kind, name in port.zones)


def test_ux_v_expands_diagnostics_and_preserves_module_input_zones():
    world, port = setup_port("bastion")
    port.draw(world, 0.4)
    assert len([z for z in port.zones if z[1] == "slot"]) >= len(world.player.hull.slots)
    port.handle_key(pygame.K_v, world)
    assert port.blueprint_focus
    port.draw(world, 0.4)
    assert len([z for z in port.zones if z[1] == "slot"]) >= len(world.player.hull.slots)
    assert any(name == "blueprint" for _, kind, name in port.zones if kind == "button")
    port.handle_key(pygame.K_v, world)
    assert not port.blueprint_focus
