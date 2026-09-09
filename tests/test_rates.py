"""Tests for the declarative residential rate-plan catalog."""

from datetime import date, time
from decimal import Decimal

from dominionsc import (
    RATE_5,
    RATE_6,
    RATE_7,
    RATE_8,
    Commodity,
    DemandCharge,
    FlatUsageCharge,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    get_available_rate_plans,
    get_rate_plan,
)


def test_catalog_contains_all_residential_plans():
    """The catalog exposes every residential plan currently defined."""
    assert [plan.code for plan in get_available_rate_plans()] == [
        "rate_2",
        "rate_5",
        "rate_6",
        "rate_7",
        "rate_8",
        "rate_32s",
        "rate_32v",
    ]
    assert get_rate_plan("rate_8") is RATE_8
    assert get_rate_plan("not_a_rate") is None


def test_rate_8_uses_seasonal_tiers():
    """Rate 8 has the July 2026 seasonal 800 kWh tier schedules."""
    charge = next(charge for charge in RATE_8.charges if isinstance(charge, TieredUsageCharge))

    assert RATE_8.commodity is Commodity.ELECTRICITY
    assert RATE_8.effective_from == date(2026, 7, 1)
    assert charge.tiers_by_season[Season.SUMMER][0].upper_bound == Decimal("800")
    assert charge.tiers_by_season[Season.SUMMER][1].price_per_unit == Decimal("0.17442")
    assert charge.tiers_by_season[Season.WINTER][1].price_per_unit == Decimal("0.15253")


def test_rate_6_uses_seasonal_tiers():
    """Rate 6 has the July 2026 seasonal 800 kWh tier schedules."""
    charge = next(charge for charge in RATE_6.charges if isinstance(charge, TieredUsageCharge))

    assert RATE_6.commodity is Commodity.ELECTRICITY
    assert charge.tiers_by_season[Season.SUMMER][1].price_per_unit == Decimal("0.16842")
    assert charge.tiers_by_season[Season.WINTER][1].price_per_unit == Decimal("0.14729")


def test_rate_5_uses_time_of_use_pricing_with_fallback():
    """Rate 5 represents off-peak as the unmatched-time fallback."""
    charge = next(charge for charge in RATE_5.charges if isinstance(charge, TimeOfUseCharge))
    winter_super_off_peak = charge.periods_by_season[Season.WINTER][1]

    assert charge.periods_by_season[Season.SUMMER][2].fallback is True
    assert winter_super_off_peak.windows == (
        (window := winter_super_off_peak.windows[0]),
        winter_super_off_peak.windows[1],
    )
    assert window.start == time(1)
    assert winter_super_off_peak.windows[1].end == time(15)


def test_rate_7_combines_time_of_use_and_demand_charges():
    """Rate 7 has distinct energy and on-peak fifteen-minute demand charges."""
    demand_charge = next(charge for charge in RATE_7.charges if isinstance(charge, DemandCharge))

    assert any(isinstance(charge, TimeOfUseCharge) for charge in RATE_7.charges)
    assert demand_charge.price_per_kw == Decimal("10.90")
    assert demand_charge.interval_minutes == 15
    assert demand_charge.qualifying_period == "on_peak"


def test_gas_rate_uses_therm_flat_charge():
    """Rate 32S is a flat gas rate denominated in therms."""
    rate = get_rate_plan("rate_32s")
    assert rate is not None
    charge = next(charge for charge in rate.charges if isinstance(charge, FlatUsageCharge))

    assert rate.commodity is Commodity.GAS
    assert charge.price_per_unit == Decimal("2.04149")
    assert charge.usage_unit.value == "therm"
