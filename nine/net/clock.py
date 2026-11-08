"""Bounded fixed-step accumulator for future dedicated server use."""

import math


class FixedTickClock:
    def __init__(self, hz=60, max_catchup=5):
        if not isinstance(hz, int) or hz <= 0 or not isinstance(max_catchup, int) or max_catchup <= 0:
            raise ValueError("hz and max_catchup must be positive integers")
        self.dt = 1.0 / hz
        self.max_catchup = max_catchup
        self.accumulator = 0.0
        self.tick = 0
        self.skipped_seconds = 0.0

    def consume(self, elapsed):
        """Return number of simulation ticks due; discard excessive backlog."""
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("elapsed must be finite and non-negative")
        self.accumulator += elapsed
        maximum = self.dt * self.max_catchup
        if self.accumulator > maximum:
            self.skipped_seconds += self.accumulator - maximum
            self.accumulator = maximum
        due = min(self.max_catchup, int((self.accumulator + 1e-12) / self.dt))
        self.accumulator -= due * self.dt
        self.accumulator = max(0.0, self.accumulator)
        return due

    def mark_tick(self):
        self.tick += 1
        return self.tick
