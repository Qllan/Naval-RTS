"""Port inventories, scheduled convoy deliveries and bounded supply-based prices.

All changes are deterministic, without randomness or wall-clock time.
Delivery counts use half-open intervals (previous, current], so save/load,
lag spikes, and replay cannot apply the same arrival twice.
"""

import math

from . import config as C
from .entities import RESOURCES
from .trade_traffic import PORT_DWELL


MAX_STOCK = 500
TARGET_STOCK = 80
INITIAL_STOCK = {
    "port": {"salt": 100, "condensate": 70, "filament": 35, "zero": 15},
    "platform": {"salt": 45, "condensate": 70, "filament": 90, "zero": 20},
}
ARRIVAL_CARGO = {
    "port": {"filament": 12, "condensate": 8},
    "platform": {"salt": 20, "condensate": 10},
}


def new_stocks():
    return {hub: dict(goods) for hub, goods in INITIAL_STOCK.items()}


def arrivals_between(traffic, previous, current):
    """Count arrivals at each port per convoy (even for large time steps).

    Trader offsets are 0 and period/2, following TradeTraffic.snapshot().
    Arrivals at the platform occur at the start of platform dwell, and
    arrivals at the refugee port at the next cycle boundary.
    """
    if current <= previous:
        return {"port": 0, "platform": 0}
    period = traffic.period
    platform_at = PORT_DWELL + traffic.sailing_time
    totals = {"port": 0, "platform": 0}
    for offset in (0.0, period / 2):
        for hub, phase in (("platform", platform_at), ("port", period)):
            first = phase - offset
            completed = (math.floor((current - first) / period)
                         - math.floor((previous - first) / period))
            totals[hub] += max(0, completed)
    return totals


def apply_deliveries(stock, traffic, previous, current):
    """Apply convoy cargo arrivals once, clamped to bounded warehouse space."""
    counts = arrivals_between(traffic, previous, current)
    for hub, count in counts.items():
        for kind, amount in ARRIVAL_CARGO[hub].items():
            stock[hub][kind] = min(MAX_STOCK, stock[hub][kind] + count * amount)
    return counts


def unit_price(hub, kind, stock, buying=False):
    """A scarcity multiplier keeps prices responsive but non-exploitable locally."""
    if hub not in C.MARKET_MULTIPLIERS or kind not in RESOURCES:
        raise ValueError("Неизвестный порт или товар")
    quantity = stock[hub][kind]
    scarcity = max(0.75, min(1.45, 1.0 + 0.55 * (TARGET_STOCK - quantity) / TARGET_STOCK))
    multiplier = C.MARKET_MULTIPLIERS[hub][kind]
    sale = max(1, round(RESOURCES[kind].price * multiplier * scarcity))
    return max(sale + 1, math.ceil(sale * C.MARKET_BUY_MARKUP)) if buying else sale


def valid_stocks(data):
    """Reject malformed/injected inventory data without partial replacement."""
    return (type(data) is dict
            and set(data) == set(INITIAL_STOCK)
            and all(type(data.get(hub)) is dict
                    and set(data[hub]) == set(RESOURCES)
                    and all(type(qty) is int and 0 <= qty <= MAX_STOCK
                            for qty in data[hub].values())
                    for hub in INITIAL_STOCK))
