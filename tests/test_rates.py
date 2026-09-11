"""Tests for the declarative residential rate-plan catalog."""

from datetime import date, time
from decimal import Decimal

from dominionsc import (
    RATE_2,
    RATE_5,
    RATE_6,
    RATE_7,
    RATE_8,
    RATE_32V,
    Commodity,
    DailyCharge,
    DemandCharge,
    FlatUsageCharge,
    MonthlyCharge,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    UsageUnit,
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
    """Rate 8 has the July 2026 seasonal 800 kWh tier schedules — both tiers, both seasons."""
    charge = next(charge for charge in RATE_8.charges if isinstance(charge, TieredUsageCharge))
    summer = charge.tiers_by_season[Season.SUMMER]
    winter = charge.tiers_by_season[Season.WINTER]

    assert RATE_8.commodity is Commodity.ELECTRICITY
    assert RATE_8.effective_from == date(2026, 7, 1)
    # Summer: first 800 kWh, then over-800
    assert summer[0].upper_bound == Decimal("800")
    assert summer[0].price_per_unit == Decimal("0.15878")
    assert summer[1].upper_bound is None
    assert summer[1].price_per_unit == Decimal("0.17442")
    # Winter: same 800 kWh threshold, different over-800 price
    assert winter[0].upper_bound == Decimal("800")
    assert winter[0].price_per_unit == Decimal("0.15878")
    assert winter[1].upper_bound is None
    assert winter[1].price_per_unit == Decimal("0.15253")


def test_rate_6_uses_seasonal_tiers():
    """Rate 6 has the July 2026 seasonal 800 kWh tier schedules — both tiers, both seasons."""
    charge = next(charge for charge in RATE_6.charges if isinstance(charge, TieredUsageCharge))
    summer = charge.tiers_by_season[Season.SUMMER]
    winter = charge.tiers_by_season[Season.WINTER]

    assert RATE_6.commodity is Commodity.ELECTRICITY
    # First-tier price is identical summer and winter for Rate 6
    assert summer[0].upper_bound == Decimal("800")
    assert summer[0].price_per_unit == Decimal("0.15333")
    assert summer[1].upper_bound is None
    assert summer[1].price_per_unit == Decimal("0.16842")
    assert winter[0].upper_bound == Decimal("800")
    assert winter[0].price_per_unit == Decimal("0.15333")
    assert winter[1].upper_bound is None
    assert winter[1].price_per_unit == Decimal("0.14729")


def test_rate_5_uses_time_of_use_pricing_with_fallback():
    """Rate 5 TOU prices and clock windows for all periods in both seasons."""
    charge = next(charge for charge in RATE_5.charges if isinstance(charge, TimeOfUseCharge))
    summer = charge.periods_by_season[Season.SUMMER]
    winter = charge.periods_by_season[Season.WINTER]

    # --- prices ---
    assert summer[0].price_per_unit == Decimal("0.29907")   # on_peak
    assert summer[1].price_per_unit == Decimal("0.09623")   # super_off_peak
    assert summer[2].price_per_unit == Decimal("0.15074")   # off_peak (fallback)
    assert winter[0].price_per_unit == Decimal("0.29907")   # on_peak
    assert winter[1].price_per_unit == Decimal("0.09623")   # super_off_peak
    assert winter[2].price_per_unit == Decimal("0.15074")   # off_peak (fallback)

    # --- fallback flags ---
    assert summer[0].fallback is False
    assert summer[1].fallback is False
    assert summer[2].fallback is True
    assert winter[2].fallback is True

    # --- summer windows ---
    assert summer[0].windows[0].start == time(16)           # on_peak 16:00–20:00
    assert summer[0].windows[0].end == time(20)
    assert summer[1].windows[0].start == time(1)            # super_off_peak 1:00–5:00
    assert summer[1].windows[0].end == time(5)

    # --- winter windows ---
    assert winter[0].windows[0].start == time(6)            # on_peak 6:00–9:00
    assert winter[0].windows[0].end == time(9)
    assert winter[1].windows[0].start == time(1)            # super_off_peak 1:00–5:00
    assert winter[1].windows[0].end == time(5)
    assert winter[1].windows[1].start == time(12)           # super_off_peak 12:00–15:00
    assert winter[1].windows[1].end == time(15)


def test_rate_7_combines_time_of_use_and_demand_charges():
    """Rate 7 energy prices, all windows, and demand charge configuration for both seasons."""
    tou = next(charge for charge in RATE_7.charges if isinstance(charge, TimeOfUseCharge))
    demand = next(charge for charge in RATE_7.charges if isinstance(charge, DemandCharge))
    summer = tou.periods_by_season[Season.SUMMER]
    winter = tou.periods_by_season[Season.WINTER]

    # --- energy prices ---
    assert summer[0].price_per_unit == Decimal("0.17441")   # on_peak
    assert summer[1].price_per_unit == Decimal("0.08841")   # super_off_peak
    assert summer[2].price_per_unit == Decimal("0.10124")   # off_peak (fallback)
    assert winter[0].price_per_unit == Decimal("0.17441")
    assert winter[1].price_per_unit == Decimal("0.08841")
    assert winter[2].price_per_unit == Decimal("0.10124")

    # --- fallback flags ---
    assert summer[2].fallback is True
    assert winter[2].fallback is True

    # --- summer windows ---
    assert summer[0].windows[0].start == time(16)           # on_peak 16:00–20:00
    assert summer[0].windows[0].end == time(20)
    assert summer[1].windows[0].start == time(1)            # super_off_peak 1:00–5:00
    assert summer[1].windows[0].end == time(5)

    # --- winter windows ---
    assert winter[0].windows[0].start == time(6)            # on_peak 6:00–9:00
    assert winter[0].windows[0].end == time(9)
    assert winter[1].windows[0].start == time(1)
    assert winter[1].windows[0].end == time(5)
    assert winter[1].windows[1].start == time(12)
    assert winter[1].windows[1].end == time(15)

    # --- demand charge ---
    assert demand.price_per_kw == Decimal("10.90")
    assert demand.interval_minutes == 15
    assert demand.qualifying_period == "on_peak"
    assert demand.rolling_interval is True


def test_gas_rate_uses_therm_flat_charge():
    """Rate 32S is a flat gas rate denominated in therms."""
    rate = get_rate_plan("rate_32s")
    assert rate is not None
    charge = next(charge for charge in rate.charges if isinstance(charge, FlatUsageCharge))

    assert rate.commodity is Commodity.GAS
    assert charge.price_per_unit == Decimal("2.04149")
    assert charge.usage_unit.value == "therm"


def test_rate_2_uses_flat_usage_charge_and_daily_fixed_charge():
    """Rate 2 applies a flat per-kWh energy charge and a daily basic facilities charge."""
    daily_charge = next(charge for charge in RATE_2.charges if isinstance(charge, DailyCharge))
    flat_charge = next(charge for charge in RATE_2.charges if isinstance(charge, FlatUsageCharge))

    assert RATE_2.commodity is Commodity.ELECTRICITY
    assert RATE_2.effective_from == date(2026, 7, 1)
    assert daily_charge.amount == Decimal("0.36164")
    assert flat_charge.price_per_unit == Decimal("0.13111")
    assert flat_charge.usage_unit is UsageUnit.KWH


def test_rate_2_has_two_eligibility_rules_with_400_kwh_threshold():
    """Rate 2 caps eligibility at 400 kWh for twelve preceding billing periods."""
    threshold_rule = next(
        rule for rule in RATE_2.eligibility_rules if rule.code == "preceding_billing_periods_below_threshold"
    )

    assert len(RATE_2.eligibility_rules) == 2
    assert threshold_rule.parameters["usage_threshold"] == Decimal("400")
    assert threshold_rule.parameters["period_count"] == 12
    assert threshold_rule.parameters["usage_unit"] == "kWh"


def test_rate_32v_has_lower_price_per_therm_than_rate_32s():
    """Rate 32V is a value-tier gas service with a lower per-therm price than Rate 32S."""
    rate_32s = get_rate_plan("rate_32s")
    assert rate_32s is not None

    standard_price = next(c for c in rate_32s.charges if isinstance(c, FlatUsageCharge)).price_per_unit
    value_price = next(c for c in RATE_32V.charges if isinstance(c, FlatUsageCharge)).price_per_unit

    assert RATE_32V.commodity is Commodity.GAS
    assert value_price == Decimal("1.91847")
    assert value_price < standard_price


def test_rate_32v_requires_summer_average_minimum():
    """Rate 32V requires an average of at least 10 therms during the summer months."""
    rule = next(r for r in RATE_32V.eligibility_rules if r.code == "summer_average_minimum")

    assert len(RATE_32V.eligibility_rules) == 2
    assert rule.parameters["minimum_usage"] == Decimal("10")
    assert rule.parameters["usage_unit"] == "therm"


def test_gas_rates_use_monthly_fixed_charge():
    """Gas rates use a monthly (not daily) basic facilities charge."""
    rate_32s = get_rate_plan("rate_32s")
    assert rate_32s is not None
    monthly_32s = next(c for c in rate_32s.charges if isinstance(c, MonthlyCharge))
    monthly_32v = next(c for c in RATE_32V.charges if isinstance(c, MonthlyCharge))

    assert monthly_32s.amount == Decimal("10.90")
    assert monthly_32v.amount == Decimal("10.90")


def test_electric_plans_carry_fuel_adjustment_included_in_published_charge():
    """All electric rate plans embed the fuel-cost adjustment in their published energy charge."""
    fuel_adj = next(adj for adj in RATE_8.adjustments if adj.code == "fuel")

    assert fuel_adj.included_in_published_charge is True
    assert len(RATE_8.adjustments) == 5


def test_rate_2_der_adjustment_is_not_included_in_published_charge():
    """The DER program adjustment is billed as a separate monthly line item, not embedded."""
    der_adj = next(adj for adj in RATE_2.adjustments if adj.code == "der")

    assert der_adj.included_in_published_charge is False
