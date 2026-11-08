"""Read-only engineering advisories for modular ship fittings.

Fitting limits are enforced by fit_problems and World.install_problem, not
by these informational loadout notices.
"""

from dataclasses import dataclass

from .ship import CARGO_MASS

MASS_WARNING_RATIO = 1.40   # Advisory above 140% of the design reference
POWER_RESERVE_WARNING = 2.0  # Advisory below 2 energy units per second


@dataclass(frozen=True)
class EngineeringNotice:
    code: str
    text: str
    short: str


def engineering_notices(ship, cargo=0.0, veil_density=0.8):
    """Advisories for a hypothetical fit, without changing the live ship.

    Hull damage, flooding, positional cargo and fluctuations in anomaly
    density are not part of this static engineering estimate.
    """
    notices = []
    veil_balance = ship.power_balance(veil_density)
    if veil_balance < -1e-6:
        deficit = -veil_balance
        notices.append(EngineeringNotice(
            "veil_deficit",
            f"В плотной Пелене реактору не хватит {deficit:.1f} ед/с",
            f"Пелена: дефицит {deficit:.1f} ед/с"))

    clear_balance = ship.power_balance(0.0)
    if 0 <= clear_balance < POWER_RESERVE_WARNING:
        notices.append(EngineeringNotice(
            "low_reserve",
            f"Запас энергии в чистой воде ниже {POWER_RESERVE_WARNING:g} ед/с",
            f"Малый резерв: {clear_balance:.1f} ед/с"))

    total_mass = ship.hull.mass + ship.module_mass + cargo * CARGO_MASS
    reference_mass = ship.hull.mass * 1.6
    if reference_mass > 0 and total_mass > reference_mass * MASS_WARNING_RATIO:
        ratio = total_mass / reference_mass
        notices.append(EngineeringNotice(
            "heavy_fit",
            f"Масса составляет {ratio:.0%} проектного ориентира: скорость и разгон снизятся",
            f"Тяжёлая сборка: {ratio:.0%} нормы"))

    return tuple(notices)
