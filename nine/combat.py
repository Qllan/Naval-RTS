"""Стрельба и снаряды: пушки, ракеты с захватом цели, торпеды."""

from dataclasses import dataclass

from pygame.math import Vector2

from .ship import heading, norm_angle


@dataclass
class Projectile:
    pos: Vector2
    vel: Vector2
    damage: float
    dtype: str
    owner: object                 # Ship
    kind: str = "shell"           # shell | missile | torpedo
    life: float = 1.0
    target: object = None         # Ship — для ракет
    turn_rate: float = 0.0
    speed: float = 0.0
    lost: bool = False            # ракета потеряла цель

    @property
    def side(self):
        return self.owner.side


def lead_point(shooter_pos, target, projectile_speed, noise=None):
    """Точка упреждения для снаряда с постоянной скоростью (две итерации достаточно)."""
    aim = Vector2(target.pos)
    for _ in range(2):
        t = shooter_pos.distance_to(aim) / max(1.0, projectile_speed)
        aim = target.pos + target.vel * t
    if noise:
        aim += noise
    return aim


def spread_for(defn, density, accuracy_bonus=0.0, smoke=False):
    s = defn.spread * (1.0 + 1.5 * density) - 3.0 * accuracy_bonus
    if smoke:
        s += 10.0
    return max(0.0, s)


def try_fire(ship, mount, rng, density, aim_point=None, accuracy_bonus=0.0, smoke=False):
    """Выстрел из установки, если она готова. Возвращает список снарядов (может быть пустым)."""
    d = mount.defn
    if mount.reload > 0 or not mount.has_ammo:
        return []
    if d.shot_energy and ship.capacitor < d.shot_energy:
        return []
    if d.kind == "missile" and (mount.lock < 1.0 or mount.lock_target is None or not mount.lock_target.alive):
        return []

    origin = mount.world_pos(ship)
    if d.kind == "gun":
        base = mount.world_angle(ship)
    else:
        base = ship.angle + mount.slot.facing       # пусковые и торпедные аппараты не поворачиваются

    out = []
    spread = spread_for(d, density, accuracy_bonus, smoke) if d.kind == "gun" else 0.0
    for _ in range(d.pellets):
        ang = base + (rng.uniform(-spread, spread) if spread else 0.0)
        direction = heading(ang)
        if d.kind == "missile":
            out.append(Projectile(origin + direction * 4, direction * d.speed * 0.6 + ship.vel * 0.5, d.damage,
                                  d.dmg_type, ship, "missile", d.range / d.speed, mount.lock_target,
                                  d.turn_rate, d.speed))
        elif d.kind == "torpedo":
            out.append(Projectile(origin + direction * 6, direction * d.speed, d.damage, d.dmg_type, ship,
                                  "torpedo", d.range / d.speed))
        else:
            # скорость стрелка не наследуется — иначе упреждение СУО врёт на ходу
            out.append(Projectile(origin + direction * 4, direction * d.speed, d.damage,
                                  d.dmg_type, ship, "shell", d.range / d.speed))
    mount.reload = d.reload * ship.reload_mult()
    if d.ammo:
        mount.ammo -= 1
    ship.capacitor -= d.shot_energy
    return out


def update_lock(mount, ship, target, visible, density, dt):
    """Захват цели ракетной установкой. Пелена растягивает захват."""
    if mount.defn.kind != "missile":
        return
    if target is None or not visible or not target.alive:
        mount.lock_target = None
        mount.lock = 0.0
        return
    if mount.lock_target is not target:
        mount.lock_target = target
        mount.lock = 0.0
    lock_time = mount.defn.lock_time * (1.0 + 2.0 * density) / (0.3 + 0.7 * ship.subsystems["sensors"])
    mount.lock = min(1.0, mount.lock + dt / lock_time)


def update_projectile(p, dt, density, rng, jammed=False):
    """Движение одного снаряда. Ракеты доворачивают на цель, пока не потеряют её в Пелене."""
    p.life -= dt
    if p.kind == "missile":
        if p.target is not None and not p.lost:
            if jammed or not p.target.alive or rng.random() < density * 0.45 * dt:
                p.lost = True
            else:
                to = p.target.pos - p.pos
                if to.length_squared() > 1:
                    cur = Vector2(1, 0).angle_to(p.vel)
                    want = Vector2(1, 0).angle_to(to)
                    diff = norm_angle(want - cur)
                    step = p.turn_rate * dt
                    cur += max(-step, min(step, diff))
                    p.vel = heading(cur) * p.vel.length()
        # разгон до маршевой скорости
        if p.vel.length() < p.speed:
            p.vel.scale_to_length(min(p.speed, p.vel.length() + p.speed * 1.5 * dt))
    p.pos += p.vel * dt
