"""Tests for the declarative residential rate-plan catalog."""

from datetime import date, time, timedelta
from decimal import Decimal
from itertools import pairwise

from dominionsc import (
    RATE_1,
    RATE_1_2025,
    RATE_2,
    RATE_2_2025,
    RATE_5,
    RATE_5_2024,
    RATE_5_2025,
    RATE_6,
    RATE_6_2025,
    RATE_7,
    RATE_7_2025,
    RATE_8,
    RATE_8_2025,
    RATE_32S,
    RATE_32S_2025,
    RATE_32V,
    RATE_32V_2025,
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
    get_rate_plan_for_date,
    get_rate_plan_history,
)


def test_catalog_contains_all_residential_plans():
    """The catalog exposes every residential plan currently defined."""
    assert [plan.code for plan in get_available_rate_plans()] == [
        "rate_1",
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


def test_rate_1_uses_seasonal_tiers():
    """Rate 1 (Good Cents) has the same July 2026 seasonal tier schedule as Rate 6."""
    charge = next(charge for charge in RATE_1.charges if isinstance(charge, TieredUsageCharge))
    summer = charge.tiers_by_season[Season.SUMMER]
    winter = charge.tiers_by_season[Season.WINTER]

    assert RATE_1.commodity is Commodity.ELECTRICITY
    assert RATE_1.effective_from == date(2026, 7, 1)
    assert summer[0].upper_bound == Decimal("800")
    assert summer[0].price_per_unit == Decimal("0.15333")
    assert summer[1].upper_bound is None
    assert summer[1].price_per_unit == Decimal("0.16842")
    assert winter[0].upper_bound == Decimal("800")
    assert winter[0].price_per_unit == Decimal("0.15333")
    assert winter[1].upper_bound is None
    assert winter[1].price_per_unit == Decimal("0.14729")


def test_rate_1_is_closed_to_new_customers():
    """Rate 1 is closed to new structures but remains available to grandfathered dwellings."""
    closed_rule = next(rule for rule in RATE_1.eligibility_rules if rule.code == "closed_to_new_customers")

    assert len(RATE_1.eligibility_rules) == 2
    assert "1996" in closed_rule.description


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
    assert summer[0].price_per_unit == Decimal("0.29907")  # on_peak
    assert summer[1].price_per_unit == Decimal("0.09623")  # super_off_peak
    assert summer[2].price_per_unit == Decimal("0.15074")  # off_peak (fallback)
    assert winter[0].price_per_unit == Decimal("0.29907")  # on_peak
    assert winter[1].price_per_unit == Decimal("0.09623")  # super_off_peak
    assert winter[2].price_per_unit == Decimal("0.15074")  # off_peak (fallback)

    # --- fallback flags ---
    assert summer[0].fallback is False
    assert summer[1].fallback is False
    assert summer[2].fallback is True
    assert winter[2].fallback is True

    # --- summer windows ---
    assert summer[0].windows[0].start == time(16)  # on_peak 16:00-20:00
    assert summer[0].windows[0].end == time(20)
    assert summer[1].windows[0].start == time(1)  # super_off_peak 1:00-5:00
    assert summer[1].windows[0].end == time(5)

    # --- winter windows ---
    assert winter[0].windows[0].start == time(6)  # on_peak 6:00-9:00
    assert winter[0].windows[0].end == time(9)
    assert winter[1].windows[0].start == time(1)  # super_off_peak 1:00-5:00
    assert winter[1].windows[0].end == time(5)
    assert winter[1].windows[1].start == time(12)  # super_off_peak 12:00-15:00
    assert winter[1].windows[1].end == time(15)


def test_rate_7_combines_time_of_use_and_demand_charges():
    """Rate 7 energy prices, all windows, and demand charge configuration for both seasons."""
    tou = next(charge for charge in RATE_7.charges if isinstance(charge, TimeOfUseCharge))
    demand = next(charge for charge in RATE_7.charges if isinstance(charge, DemandCharge))
    summer = tou.periods_by_season[Season.SUMMER]
    winter = tou.periods_by_season[Season.WINTER]

    # --- energy prices ---
    assert summer[0].price_per_unit == Decimal("0.17441")  # on_peak
    assert summer[1].price_per_unit == Decimal("0.08841")  # super_off_peak
    assert summer[2].price_per_unit == Decimal("0.10124")  # off_peak (fallback)
    assert winter[0].price_per_unit == Decimal("0.17441")
    assert winter[1].price_per_unit == Decimal("0.08841")
    assert winter[2].price_per_unit == Decimal("0.10124")

    # --- fallback flags ---
    assert summer[2].fallback is True
    assert winter[2].fallback is True

    # --- summer windows ---
    assert summer[0].windows[0].start == time(16)  # on_peak 16:00-20:00
    assert summer[0].windows[0].end == time(20)
    assert summer[1].windows[0].start == time(1)  # super_off_peak 1:00-5:00
    assert summer[1].windows[0].end == time(5)

    # --- winter windows ---
    assert winter[0].windows[0].start == time(6)  # on_peak 6:00-9:00
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


def _tier_prices(plan, season):
    charge = next(c for c in plan.charges if isinstance(c, TieredUsageCharge))
    return [(tier.upper_bound, tier.price_per_unit) for tier in charge.tiers_by_season[season]]


def test_rate_8_2025_values_and_dates():
    """Rate 8's July 2025 tariff is archived with its own dates and prices."""
    assert RATE_8_2025.code == "rate_8"
    assert RATE_8_2025.effective_from == date(2025, 7, 23)
    assert RATE_8_2025.effective_to == date(2026, 6, 30)
    assert _tier_prices(RATE_8_2025, Season.SUMMER) == [
        (Decimal("800"), Decimal("0.14599")),
        (None, Decimal("0.15983")),
    ]
    assert _tier_prices(RATE_8_2025, Season.WINTER) == [
        (Decimal("800"), Decimal("0.14599")),
        (None, Decimal("0.14045")),
    ]


def test_rate_6_2025_values_and_dates():
    """Rate 6's July 2025 tariff is archived with its own dates and prices."""
    assert RATE_6_2025.code == "rate_6"
    assert RATE_6_2025.effective_from == date(2025, 7, 23)
    assert RATE_6_2025.effective_to == date(2026, 6, 30)
    assert _tier_prices(RATE_6_2025, Season.SUMMER) == [
        (Decimal("800"), Decimal("0.14164")),
        (None, Decimal("0.15505")),
    ]
    assert _tier_prices(RATE_6_2025, Season.WINTER) == [
        (Decimal("800"), Decimal("0.14164")),
        (None, Decimal("0.13628")),
    ]


def _tou_charge(plan):
    return next(c for c in plan.charges if isinstance(c, TimeOfUseCharge))


def _tou_prices(plan, season):
    charge = _tou_charge(plan)
    return {period.name: period.price_per_unit for period in charge.periods_by_season[season]}


def test_rate_5_archived_periods_values_and_dates():
    """Rate 5's archived tariffs carry their own dates and prices; May and July 2025 are one period."""
    assert (RATE_5_2024.effective_from, RATE_5_2024.effective_to) == (date(2024, 9, 1), date(2025, 4, 30))
    assert (RATE_5_2025.effective_from, RATE_5_2025.effective_to) == (date(2025, 5, 1), date(2026, 6, 30))
    for plan, prices in (
        (RATE_5_2024, {"on_peak": "0.26139", "off_peak": "0.12940", "super_off_peak": "0.08303"}),
        (RATE_5_2025, {"on_peak": "0.26900", "off_peak": "0.13701", "super_off_peak": "0.09064"}),
    ):
        assert plan.code == "rate_5"
        for season in (Season.SUMMER, Season.WINTER):
            assert _tou_prices(plan, season) == {name: Decimal(price) for name, price in prices.items()}
        assert plan.charges[:2] == RATE_5.charges[:2]
        assert _tou_charge(plan).periods_by_season.keys() == _tou_charge(RATE_5).periods_by_season.keys()


def test_rate_7_2025_values_and_dates():
    """Rate 7's July 2025 tariff has its own energy prices and on-peak demand price."""
    assert (RATE_7_2025.effective_from, RATE_7_2025.effective_to) == (date(2025, 7, 23), date(2026, 6, 30))
    for season in (Season.SUMMER, Season.WINTER):
        assert _tou_prices(RATE_7_2025, season) == {
            "on_peak": Decimal("0.15983"),
            "off_peak": Decimal("0.09161"),
            "super_off_peak": Decimal("0.08372"),
        }
    demand = next(c for c in RATE_7_2025.charges if isinstance(c, DemandCharge))
    assert demand.price_per_kw == Decimal("9.80")
    assert RATE_7_2025.charges[:2] == RATE_7.charges[:2]


def test_rate_1_and_2_2025_values_and_dates():
    """Rate 1 and Rate 2's July 2025 tariffs are archived with their own dates and prices."""
    for plan in (RATE_1_2025, RATE_2_2025):
        assert (plan.effective_from, plan.effective_to) == (date(2025, 7, 23), date(2026, 6, 30))
        assert plan.eligibility_rules
    assert _tier_prices(RATE_1_2025, Season.SUMMER) == [
        (Decimal("800"), Decimal("0.14164")),
        (None, Decimal("0.15505")),
    ]
    assert _tier_prices(RATE_1_2025, Season.WINTER) == [
        (Decimal("800"), Decimal("0.14164")),
        (None, Decimal("0.13628")),
    ]
    flat = next(c for c in RATE_2_2025.charges if isinstance(c, FlatUsageCharge))
    assert flat.price_per_unit == Decimal("0.12445")


def test_rate_32s_2025_values_and_dates():
    """Rate 32S's September 2025 tariff is archived with its own dates, price, and fixed charge."""
    assert (RATE_32S_2025.effective_from, RATE_32S_2025.effective_to) == (date(2025, 9, 1), date(2026, 6, 30))
    assert RATE_32S_2025.commodity == Commodity.GAS
    assert RATE_32S_2025.code == "rate_32s"
    assert RATE_32S_2025.source_url
    monthly = next(c for c in RATE_32S_2025.charges if isinstance(c, MonthlyCharge))
    assert monthly.amount == Decimal("10.90")
    energy = next(c for c in RATE_32S_2025.charges if isinstance(c, FlatUsageCharge))
    assert (energy.usage_unit, energy.price_per_unit) == (UsageUnit.THERM, Decimal("1.81026"))


def test_rate_32s_periods_are_contiguous():
    """Each 32S period starts the day after the previous one ends, so no date falls in a gap."""
    history = get_rate_plan_history("rate_32s")
    for earlier, later in pairwise(history):
        assert earlier.effective_to is not None
        assert later.effective_from == earlier.effective_to + timedelta(days=1)


def test_rate_32v_2025_values_and_dates():
    """Rate 32V's September 2025 tariff is archived with its own dates, prices, and fixed charge."""
    assert (RATE_32V_2025.effective_from, RATE_32V_2025.effective_to) == (date(2025, 9, 1), date(2026, 6, 30))
    assert RATE_32V_2025.commodity == Commodity.GAS
    assert RATE_32V_2025.eligibility_rules == RATE_32V.eligibility_rules
    assert RATE_32V_2025.source_url
    monthly = next(c for c in RATE_32V_2025.charges if isinstance(c, MonthlyCharge))
    assert monthly.amount == Decimal("10.90")
    energy = next(c for c in RATE_32V_2025.charges if isinstance(c, FlatUsageCharge))
    assert (energy.usage_unit, energy.price_per_unit) == (UsageUnit.THERM, Decimal("1.71886"))


def test_archived_2025_plans_record_fixed_charges():
    """Every July 2025 archive carries the Basic Facilities Charge (published monthly, stored per day) and DER."""
    expected_daily = (
        (RATE_1_2025, "0.29589"),
        (RATE_2_2025, "0.29589"),
        (RATE_5_2025, "0.42740"),
        (RATE_6_2025, "0.29589"),
        (RATE_7_2025, "0.42740"),
        (RATE_8_2025, "0.31233"),
    )
    for plan, daily in expected_daily:
        daily_charge = next(c for c in plan.charges if isinstance(c, DailyCharge))
        assert daily_charge.amount == Decimal(daily)
        assert any(isinstance(c, MonthlyCharge) and c.amount == Decimal("1.00") for c in plan.charges)
        assert plan.source_url


def test_archived_plans_are_not_in_the_current_catalog():
    """get_rate_plan / get_available_rate_plans only ever return current plans."""
    assert get_rate_plan("rate_6") is RATE_6
    assert RATE_6_2025 not in get_available_rate_plans()
    assert RATE_8_2025 not in get_available_rate_plans()
    for plan in (RATE_1_2025, RATE_2_2025, RATE_5_2024, RATE_5_2025, RATE_7_2025, RATE_32S_2025, RATE_32V_2025):
        assert plan not in get_available_rate_plans()


def test_rate_plan_history_is_ascending_and_ends_with_current_plan():
    """History runs oldest to newest, ends at the current plan, and is empty for unknown codes."""
    assert get_rate_plan_history("rate_8") == (RATE_8_2025, RATE_8)
    assert get_rate_plan_history("rate_6") == (RATE_6_2025, RATE_6)
    assert get_rate_plan_history("rate_5") == (RATE_5_2024, RATE_5_2025, RATE_5)
    assert get_rate_plan_history("rate_1") == (RATE_1_2025, RATE_1)
    assert get_rate_plan_history("rate_2") == (RATE_2_2025, RATE_2)
    assert get_rate_plan_history("rate_7") == (RATE_7_2025, RATE_7)
    assert get_rate_plan_history("rate_32v") == (RATE_32V_2025, RATE_32V)
    assert get_rate_plan_history("rate_32s") == (RATE_32S_2025, RATE_32S)
    assert get_rate_plan_history("not_a_rate") == ()


def test_rate_plan_for_date_selects_period():
    """The plan is chosen by date; boundaries are inclusive and gaps or unknown codes give None."""
    assert get_rate_plan_for_date("rate_8", date(2025, 7, 22)) is None
    assert get_rate_plan_for_date("rate_8", date(2025, 7, 23)) is RATE_8_2025
    assert get_rate_plan_for_date("rate_8", date(2026, 6, 30)) is RATE_8_2025
    assert get_rate_plan_for_date("rate_8", date(2026, 7, 1)) is RATE_8
    assert get_rate_plan_for_date("rate_8", date(2030, 1, 1)) is RATE_8
    assert get_rate_plan_for_date("rate_5", date(2024, 8, 31)) is None
    assert get_rate_plan_for_date("rate_5", date(2024, 9, 1)) is RATE_5_2024
    assert get_rate_plan_for_date("rate_5", date(2025, 4, 30)) is RATE_5_2024
    assert get_rate_plan_for_date("rate_5", date(2025, 5, 1)) is RATE_5_2025
    assert get_rate_plan_for_date("rate_5", date(2025, 7, 23)) is RATE_5_2025
    assert get_rate_plan_for_date("rate_5", date(2026, 6, 30)) is RATE_5_2025
    assert get_rate_plan_for_date("rate_5", date(2026, 7, 1)) is RATE_5
    assert get_rate_plan_for_date("rate_2", date(2025, 8, 1)) is RATE_2_2025
    assert get_rate_plan_for_date("rate_2", date(2025, 7, 22)) is None
    assert get_rate_plan_for_date("not_a_rate", date(2026, 8, 1)) is None
