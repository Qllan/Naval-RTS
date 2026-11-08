"""Scheduled trade events, derived from world seed and simulation time.

Events are pure functions: the active event and its news text survive a
save/load without storing mutable clocks or rerolling randomness.
"""

import random

EVENT_PERIOD = 480.0
EVENT_START = 120.0
EVENT_DURATION = 150.0
EVENT_GOODS = ("salt", "filament", "condensate")
EVENT_HUBS = ("port", "platform")
HUB_NAMES = {"port": "Порт беженцев", "platform": "Торговая платформа"}
GOOD_NAMES = {"salt": "соль-металл", "filament": "филаменты",
              "condensate": "конденсат"}


def event_for_cycle(seed, cycle):
    """A stable, bounded demand surge or temporary convoy disruption."""
    if cycle < 0:
        return None
    rng = random.Random(f"market-event:{seed}:{cycle}")
    kind = "demand" if cycle % 2 == 0 else "disruption"
    hub, good = (rng.choice(EVENT_HUBS), rng.choice(EVENT_GOODS)) if kind == "demand" else rng.choice((
        ("port", "filament"), ("port", "condensate"),
        ("platform", "salt"), ("platform", "condensate")))
    return {
        "cycle": cycle,
        "type": kind,
        "hub": hub,
        "kind": good,
        "start": EVENT_START + cycle * EVENT_PERIOD,
        "end": EVENT_START + cycle * EVENT_PERIOD + EVENT_DURATION,
    }


def current_event(seed, time):
    """Only report an event while its window is currently active."""
    if time < EVENT_START:
        return None
    cycle = int((time - EVENT_START) // EVENT_PERIOD)
    event = event_for_cycle(seed, cycle)
    return event if event["start"] <= time < event["end"] else None


def latest_news(seed, time):
    """Keep the last announced market bulletin available between events."""
    if time < EVENT_START:
        return "Рынок: обстановка спокойная, ждём сводки торговой гильдии."
    cycle = int((time - EVENT_START) // EVENT_PERIOD)
    event = event_for_cycle(seed, cycle)
    name = HUB_NAMES[event["hub"]]
    good = GOOD_NAMES[event["kind"]]
    if event["type"] == "demand":
        headline = f"Всплеск спроса: {name}, {good} дорожает"
    else:
        headline = f"Перебой поставок: {name}, {good} поступает в меньшем объёме"
    return ("СЕЙЧАС: " if time < event["end"] else "Архив: ") + headline


def demand_multiplier(seed, time, hub, kind):
    event = current_event(seed, time)
    return (1.35 if event and event["type"] == "demand"
            and event["hub"] == hub and event["kind"] == kind else 1.0)


def delivery_fraction(seed, arrival_time, hub, kind):
    event = current_event(seed, arrival_time)
    return (0.5 if event and event["type"] == "disruption"
            and event["hub"] == hub and event["kind"] == kind else 1.0)
