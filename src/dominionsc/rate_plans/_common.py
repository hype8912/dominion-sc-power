"""Values shared by more than one rate plan module."""

from datetime import time
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import (
    Adjustment,
    MonthlyCharge,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
    UsageTier,
    UsageUnit,
)

# Riders listed on every residential electric tariff. Only the DER charge is billed
# separately, so it is also modeled as a charge in ELECTRIC_FIXED_CHARGES.
ELECTRIC_ADJUSTMENTS: tuple[Adjustment, ...] = (
    Adjustment("fuel", "Fuel", "Included in the published energy charge; subject to adjustment.", True),
    Adjustment("dsm", "Demand Side Management", "Included in the published energy charge.", True),
    Adjustment("pension", "Pension Costs", "Included in the published energy charge.", True),
    Adjustment("storm_damage", "Storm Damage", "Included in the published energy charge.", True),
    Adjustment("der", "Distributed Energy Resource Program", "A $1.00 monthly charge is added separately.", False),
)
ELECTRIC_FIXED_CHARGES: tuple[MonthlyCharge, ...] = (
    MonthlyCharge(name="Distributed Energy Resource Program", amount=Decimal("1.00")),
)

GAS_ADJUSTMENTS: tuple[Adjustment, ...] = (
    Adjustment("gas_costs", "Gas Costs", "Included in the published energy charge; subject to adjustment.", True),
    Adjustment("dsm", "Demand Side Management", "Included in the published energy charge.", True),
    Adjustment(
        "weather_normalization", "Weather Normalization Adjustment", "Applies to November-April billing months.", False
    ),
)


def seasonal_tiers(summer_under: str, summer_over: str, winter_under: str, winter_over: str) -> TieredUsageCharge:
    """Build the two-tier (first 800 kWh, then over 800 kWh) energy charge shared by Rates 1, 6, and 8.

    Prices are decimal strings in $/kWh, as printed in the tariff, and are
    converted to ``Decimal`` here so no float rounding creeps in.

    Args:
        summer_under: Summer price for the first 800 kWh.
        summer_over: Summer price for usage above 800 kWh.
        winter_under: Winter price for the first 800 kWh.
        winter_over: Winter price for usage above 800 kWh.

    Returns:
        A ``TieredUsageCharge`` named ``"Energy"``.

    """
    return TieredUsageCharge(
        name="Energy",
        usage_unit=UsageUnit.KWH,
        tiers_by_season=MappingProxyType(
            {
                Season.SUMMER: (
                    UsageTier("First 800 kWh", Decimal("800"), Decimal(summer_under)),
                    UsageTier("Over 800 kWh", None, Decimal(summer_over)),
                ),
                Season.WINTER: (
                    UsageTier("First 800 kWh", Decimal("800"), Decimal(winter_under)),
                    UsageTier("Over 800 kWh", None, Decimal(winter_over)),
                ),
            }
        ),
    )


def time_of_use_charge(on_peak: str, off_peak: str, super_off_peak: str) -> TimeOfUseCharge:
    """Build the on-peak / off-peak / super-off-peak energy charge shared by Rates 5 and 7.

    The same three prices apply in both seasons; only the clock windows differ:

    - Summer: on-peak 4-8 PM; super-off-peak 1-5 AM.
    - Winter: on-peak 6-9 AM; super-off-peak 1-5 AM and 12-3 PM.
    - All other hours fall back to off-peak.

    Args:
        on_peak: On-peak price, $/kWh, as a decimal string.
        off_peak: Off-peak price, $/kWh, as a decimal string.
        super_off_peak: Super-off-peak price, $/kWh, as a decimal string.

    Returns:
        A ``TimeOfUseCharge`` named ``"Energy"``.

    """
    return TimeOfUseCharge(
        name="Energy",
        periods_by_season=MappingProxyType(
            {
                Season.SUMMER: (
                    TimeOfUsePeriod("on_peak", Decimal(on_peak), (TimeWindow(time(16), time(20)),)),
                    TimeOfUsePeriod("super_off_peak", Decimal(super_off_peak), (TimeWindow(time(1), time(5)),)),
                    TimeOfUsePeriod("off_peak", Decimal(off_peak), fallback=True),
                ),
                Season.WINTER: (
                    TimeOfUsePeriod("on_peak", Decimal(on_peak), (TimeWindow(time(6), time(9)),)),
                    TimeOfUsePeriod(
                        "super_off_peak",
                        Decimal(super_off_peak),
                        (TimeWindow(time(1), time(5)), TimeWindow(time(12), time(15))),
                    ),
                    TimeOfUsePeriod("off_peak", Decimal(off_peak), fallback=True),
                ),
            }
        ),
    )
