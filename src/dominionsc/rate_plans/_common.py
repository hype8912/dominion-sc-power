"""Values shared by more than one rate plan module."""

from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import Adjustment, MonthlyCharge, Season, TieredUsageCharge, UsageTier, UsageUnit

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
    """Build the two-tier (first 800 kWh, then over 800 kWh) energy charge shared by Rates 1, 6, and 8."""
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
