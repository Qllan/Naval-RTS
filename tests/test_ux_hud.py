"""UX 2.2 HUD: player urgency, limited alerts and original controls."""

from types import SimpleNamespace

import pygame

from nine.gfx import ui
from nine.hud import Hud, combat_focus
from nine.ship import Ship
from nine.world import World


def make_world():
    pygame.font.init()
    ui.Fonts.reset()
    w = World(seed=12, first_event=1e9)
    w.t = 120.0
    w.player = Ship("bastion", (1850, 6200), -90)
    w.pirates = []
    w.projectiles = []
    return w


def test_ux22_cruise_focus_is_not_persistent_emergency():
    world = make_world()
    assert combat_focus(world) == "cruise"


def test_ux22_ship_damage_and_hull_fire_gain_urgent_focus():
    world = make_world()
    world.player.hp = world.player.hull.hp * 0.24
    assert combat_focus(world) == "critical"
    world.player.hp = world.player.hull.hp
    world.player.fires = 2
    assert combat_focus(world) == "critical"


def test_ux22_missile_is_critical_even_when_ship_is_undamaged():
    world = make_world()
    p = world.player
    world.projectiles = [SimpleNamespace(kind="missile", target=p, lost=False)]
    assert combat_focus(world) == "critical"


def test_ux22_hud_prioritizes_incoming_missile_over_other_warnings():
    world = make_world()
    p = world.player
    p.hp = p.hull.hp * 0.22
    p.fires = 2
    world.projectiles = [SimpleNamespace(kind="missile", target=p, lost=False)]
    screen = pygame.Surface((1280, 720))
    hud = Hud(screen, world)
    hud.help_until = 0
    hud.draw(world, False, mouse=(-100, -100))
    assert hud.focus == "critical"
    assert len(hud.visible_alerts) <= 2
    assert hud.visible_alerts[0].startswith("Ракета на подлёте")
    assert len(hud.panels) >= 3
    assert not hud.over_ui((640, 360))


def test_ux22_original_pip_and_ammunition_controls_remain_clickable():
    world = make_world()
    screen = pygame.Surface((1280, 720))
    hud = Hud(screen, world)
    hud.help_until = 0
    hud.draw(world, False, mouse=(-100, -100))
    actions = [action for _, action in hud.buttons]
    for name in ("shields", "engines", "weapons"):
        target = next(rect for rect, action in hud.buttons
                      if action == ("pip", name))
        assert hud.action_at(target.center) == ("pip", name)
    if any(w.defn.kind == "gun" and w.defn.dmg_type == "kinetic"
           for w in world.player.weapons):
        assert ("ammo",) in actions
    assert hud.show_minimap
    assert len(hud.panels) >= 3


def test_ux22_log_and_tutorial_do_not_compete_with_emergency():
    world = make_world()
    screen = pygame.Surface((1280, 720))
    hud = Hud(screen, world)
    hud.help_until = 0
    world.player.hp = world.player.hull.hp * 0.2
    hud.draw(world, False, mouse=(-100, -100))
    assert hud.focus == "critical"
    assert any("КОРПУС" in alert for alert in hud.visible_alerts)


def test_ux22_gallery_comes_from_actual_hud_and_renderer(tmp_path):
    from tools.preview_ux_hud import render
    path = tmp_path / "real-hud.png"
    render(path)
    assert path.exists() and path.stat().st_size > 30000
    image = pygame.image.load(str(path))
    assert image.get_size() == (2616, 1596)



def test_ux22_health_channels_have_explicit_words_not_only_colors(monkeypatch):
    world = make_world()
    screen = pygame.Surface((1280, 720))
    hud = Hud(screen, world)
    recorded = []
    original = ui.text

    def capture(screen, content, pos, *args, **kwargs):
        recorded.append(str(content))
        return original(screen, content, pos, *args, **kwargs)

    monkeypatch.setattr(ui, "text", capture)
    hud._status(world, 1 / 60)
    assert {"КОРПУС", "БРОНЯ", "ЩИТ", "ЭНЕРГИЯ"}.issubset(set(recorded))


def test_ux22_compact_window_keeps_centre_clear_and_pip_clicks():
    world = make_world()
    p = world.player
    p.hp = p.hull.hp * 0.2
    p.fires = 2
    screen = pygame.Surface((960, 540))
    hud = Hud(screen, world)
    hud.help_until = 0
    hud.draw(world, False, mouse=(-100, -100))
    assert hud.focus == "critical"
    assert len(hud.visible_alerts) <= 2
    assert not hud.over_ui((480, 260))
    assert any(action == ("pip", "engines") for _, action in hud.buttons)
