"""Звук, синтезированный кодом (numpy): без внешних файлов.

- Эффекты: выстрелы, попадания, взрывы, всплески, гром, удары волн.
- Петли: двигатель (громкость от хода), дождь, гул Пелены — низкий тон, пульсирующий
  с частотой 6 Гц (тета-ритм из лора: филаменты резонируют на 4–8 Гц).
- В плотной Пелене звуки глохнут: играется приглушённый (низкочастотный) вариант.
- Интерфейс: клик, наведение, ошибка, покупка, монеты, тревога.

Если звуковое устройство недоступно, всё молча отключается.
"""

import math

import numpy as np
import pygame
from pygame.math import Vector2

SR = 22050
HEAR_RANGE = 1100.0


def _t(sec):
    return np.arange(int(SR * sec)) / SR


def _env(n, attack=0.005, decay=0.2, curve=3.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = np.exp(-np.maximum(t - attack, 0) / max(decay, 1e-4) * curve / 3)
    return a * d


def _noise(n, rng):
    return rng.uniform(-1, 1, n)


def _lowpass(x, k):
    """Скользящее среднее — грубый ФНЧ; k — ширина окна в сэмплах."""
    if k <= 1:
        return x
    kernel = np.ones(k) / k
    return np.convolve(x, kernel, mode="same")


def _brown(n, rng):
    b = np.cumsum(rng.uniform(-1, 1, n))
    b -= _lowpass(b, 400)
    return b / (np.abs(b).max() + 1e-6)


class Audio:
    def __init__(self):
        self.ok = False
        self.volume = {"master": 0.8, "sfx": 0.8, "ambient": 0.6, "ui": 0.7}
        self.muffle = 0.0
        self._ui_cd = 0.0
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(SR, -16, 2, 512)
            pygame.mixer.set_num_channels(40)
            pygame.mixer.set_reserved(4)
            self.ok = True
        except pygame.error:
            return
        self.freq, _, self.channels = pygame.mixer.get_init()
        rng = np.random.default_rng(7)
        self.sounds = {}
        self._build(rng)
        self.loops = {name: pygame.mixer.Channel(i) for i, name in enumerate(("engine", "hum", "rain", "wind"))}
        for name, ch in self.loops.items():
            ch.play(self.sounds[name], loops=-1)
            ch.set_volume(0.0)

    # --- синтез ---------------------------------------------------------------

    def _make(self, x, gain=0.8):
        x = np.clip(x * gain, -1, 1)
        if self.freq != SR:                                   # пересэмплинг под частоту микшера
            idx = np.linspace(0, len(x) - 1, int(len(x) * self.freq / SR))
            x = np.interp(idx, np.arange(len(x)), x)
        a = (x * 32000).astype(np.int16)
        if self.channels == 2:
            a = np.column_stack((a, a))
        return pygame.sndarray.make_sound(np.ascontiguousarray(a))

    def _add(self, name, x, gain=0.8, muffled=True):
        self.sounds[name] = self._make(x, gain)
        if muffled:
            self.sounds[name + "~"] = self._make(_lowpass(x, 28), gain * 0.7)

    def _build(self, rng):
        def shot(dur, lp, pitch, body):
            n = int(SR * dur)
            t = np.arange(n) / SR
            x = _lowpass(_noise(n, rng), lp) * _env(n, 0.001, dur * 0.35)
            x += body * np.sin(2 * math.pi * pitch * t * (1 - t)) * _env(n, 0.001, dur * 0.5)
            return x

        self._add("gun_s", shot(0.18, 3, 180, 0.4), 0.45)
        self._add("gun_m", shot(0.55, 9, 70, 0.8), 0.8)
        self._add("scatter", shot(0.3, 2, 140, 0.3), 0.55)
        t = _t(0.25)
        self._add("em", (np.sin(2 * math.pi * (900 - 2600 * t) * t) * 0.6 + _noise(len(t), rng) * 0.2)
                  * _env(len(t), 0.002, 0.08), 0.4)
        t = _t(0.9)
        self._add("missile", _lowpass(_noise(len(t), rng), 6) * _env(len(t), 0.05, 0.5)
                  * (0.6 + 0.4 * np.sin(2 * math.pi * 30 * t)), 0.6)
        t = _t(0.8)
        self._add("torpedo", (_lowpass(_noise(len(t), rng), 30) + 0.4 * np.sin(2 * math.pi * 60 * t))
                  * _env(len(t), 0.02, 0.4), 0.7)
        t = _t(0.18)
        self._add("hit_shield", np.sin(2 * math.pi * (1400 - 1500 * t) * t) * _env(len(t), 0.001, 0.06), 0.35)
        t = _t(0.3)
        self._add("hit_hull", (np.sin(2 * math.pi * 320 * t) * 0.5 + np.sin(2 * math.pi * 510 * t) * 0.3
                               + _lowpass(_noise(len(t), rng), 2) * 0.5) * _env(len(t), 0.001, 0.09), 0.45)
        t = _t(1.2)
        self._add("explosion_s", _lowpass(_noise(len(t), rng), 14) * _env(len(t), 0.004, 0.45)
                  + 0.5 * np.sin(2 * math.pi * 45 * t) * _env(len(t), 0.004, 0.3), 0.9)
        t = _t(2.6)
        self._add("explosion_l", _lowpass(_noise(len(t), rng), 30) * _env(len(t), 0.01, 1.2)
                  + 0.7 * np.sin(2 * math.pi * 32 * t) * _env(len(t), 0.01, 0.8), 1.0)
        t = _t(0.6)
        self._add("splash", _lowpass(_noise(len(t), rng), 4) * _env(len(t), 0.01, 0.2), 0.35)
        t = _t(3.0)
        self._add("thunder", _lowpass(_brown(len(t), rng), 40) * _env(len(t), 0.05, 1.4)
                  * (0.7 + 0.3 * np.sin(2 * math.pi * 3 * t)), 1.0, muffled=False)
        t = _t(0.9)
        self._add("wave", _lowpass(_noise(len(t), rng), 18) * np.sin(math.pi * t / t[-1]) ** 2, 0.6)
        t = _t(0.35)
        self._add("rock", _lowpass(_noise(len(t), rng), 6) * _env(len(t), 0.001, 0.1), 0.5)
        # интерфейс
        t = _t(0.05)
        self._add("ui_click", np.sin(2 * math.pi * 1800 * t) * _env(len(t), 0.001, 0.02), 0.35, muffled=False)
        t = _t(0.03)
        self._add("ui_hover", np.sin(2 * math.pi * 2600 * t) * _env(len(t), 0.001, 0.01), 0.15, muffled=False)
        t = _t(0.28)
        self._add("ui_error", np.sign(np.sin(2 * math.pi * 150 * t)) * 0.4 * _env(len(t), 0.005, 0.15), 0.4,
                  muffled=False)
        t = _t(0.35)
        chime = sum(np.sin(2 * math.pi * f * t) * _env(len(t), 0.002, 0.2) * (t > d)
                    for f, d in ((880, 0), (1320, 0.08)))
        self._add("ui_buy", chime, 0.35, muffled=False)
        t = _t(0.25)
        self._add("coin", (np.sin(2 * math.pi * 1970 * t) + np.sin(2 * math.pi * 2630 * t) * 0.6)
                  * _env(len(t), 0.001, 0.08), 0.3, muffled=False)
        t = _t(0.6)
        self._add("alarm", np.sin(2 * math.pi * (700 + 200 * np.sign(np.sin(2 * math.pi * 6 * t))) * t)
                  * _env(len(t), 0.01, 0.5) * 0.6, 0.35, muffled=False)
        t = _t(0.4)
        self._add("lock", np.sin(2 * math.pi * 1200 * t) * (np.sin(2 * math.pi * 16 * t) > 0) * 0.4
                  * _env(len(t), 0.001, 0.3), 0.3, muffled=False)
        # петли (длина — целое число периодов модуляции, чтобы не щёлкало)
        t = _t(2.0)
        eng = _lowpass(_brown(len(t), rng), 20) * 0.7 + 0.3 * np.sign(np.sin(2 * math.pi * 38 * t)) * 0.4
        self.sounds["engine"] = self._make(_lowpass(eng, 30), 0.7)
        t = _t(1.0)
        theta = 0.35 + 0.65 * (0.5 + 0.5 * np.sin(2 * math.pi * 6 * t)) ** 2            # 6 Гц
        hum = (np.sin(2 * math.pi * 55 * t) + 0.5 * np.sin(2 * math.pi * 110 * t)
               + 0.25 * np.sin(2 * math.pi * 165 * t)) * theta
        self.sounds["hum"] = self._make(hum / 1.8, 0.8)
        t = _t(2.0)
        self.sounds["rain"] = self._make(_lowpass(_noise(len(t), rng), 3) * 0.5, 0.6)
        self.sounds["wind"] = self._make(_lowpass(_brown(len(t), rng), 60), 0.6)

    # --- воспроизведение --------------------------------------------------------

    def _vol(self, kind):
        return self.volume["master"] * self.volume[kind]

    def play(self, name, pos=None, listener=None, volume=1.0):
        if not self.ok or name not in self.sounds:
            return
        left = right = 1.0
        if pos is not None and listener is not None:
            d = Vector2(pos) - listener
            dist = d.length()
            if dist > HEAR_RANGE:
                return
            att = (1.0 - dist / HEAR_RANGE) ** 1.5
            pan = max(-1.0, min(1.0, d.x / 600))
            left, right = att * min(1.0, 1 - pan), att * min(1.0, 1 + pan)
        if self.muffle > 0.5 and name + "~" in self.sounds:
            name += "~"
        v = volume * self._vol("sfx") * (1.0 - 0.35 * self.muffle)
        ch = self.sounds[name].play()
        if ch is not None:
            ch.set_volume(left * v, right * v)

    def ui(self, name):
        if not self.ok:
            return
        if name == "ui_hover":
            if self._ui_cd > 0:
                return
            self._ui_cd = 0.04
        ch = self.sounds[name].play()
        if ch is not None:
            v = self._vol("ui")
            ch.set_volume(v, v)

    def update(self, world, events, lightning, dt, paused=False):
        """Громкость петель по состоянию мира и звуки событий кадра."""
        if not self.ok:
            return
        self._ui_cd = max(0.0, self._ui_cd - dt)
        p = world.player
        d = world.density_at(p.pos)
        self.muffle = max(0.0, (d - 0.4) / 0.6)
        amb = self._vol("ambient")
        if paused:
            for ch in self.loops.values():
                ch.set_volume(0)
            return
        eng = 0.15 + 0.85 * min(1.0, p.speed / max(1.0, p.base_top_speed()))
        self.loops["engine"].set_volume(eng * 0.5 * self._vol("sfx") * (1 - 0.4 * self.muffle))
        self.loops["hum"].set_volume(amb * max(0.0, (d - 0.2) / 0.8) ** 1.2 * 0.9)
        from .gfx.events_fx import storm_strength
        storm = storm_strength(world)
        self.loops["rain"].set_volume(amb * storm * 0.7)
        dist_eye = p.pos.distance_to(world.eye)
        self.loops["wind"].set_volume(amb * (storm * 0.5 + max(0.0, 1 - dist_eye / 1800) * 0.7))
        if lightning:
            self.play("thunder", volume=0.9)
        me = p.pos
        for ev in events:
            kind = ev[0]
            if kind == "muzzle":
                _, pos, _, size, wkind, side = ev
                name = {"missile": "missile", "torpedo": "torpedo"}.get(wkind, "gun_m" if size > 1 else "gun_s")
                self.play(name, pos, me, 0.9 if side == "player" else 0.6)
            elif kind == "hit":
                _, pos, layer, dtype, pkind, ship = ev[:6]
                self.play("hit_shield" if layer == "shield" else "hit_hull", pos, me, 1.0 if ship is p else 0.6)
                if ship is p and layer == "hull" and p.hp < p.hull.hp * 0.3:
                    self.play("alarm", volume=0.5)
            elif kind == "explosion":
                _, pos, size = ev
                self.play("explosion_l" if size >= 3 else "explosion_s", pos, me)
            elif kind == "splash":
                self.play("splash", ev[1], me, 0.5)
            elif kind == "rock":
                self.play("rock", ev[1], me, 0.6)
            elif kind in ("wave", "aground"):
                self.play("wave", ev[1], me, 0.8)
            elif kind == "ecm":
                self.play("em", ev[1], me, 1.0)
            elif kind == "coin":
                self.ui("coin")

    def silence(self):
        if self.ok:
            for ch in self.loops.values():
                ch.set_volume(0)
