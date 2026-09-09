"""Declarative residential rate plans for Dominion Energy South Carolina."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING

from .models.rate_plan import (
    Adjustment,
    Commodity,
    DailyCharge,
    DemandCharge,
    EligibilityRule,
    FlatUsageCharge,
    MonthlyCharge,
    RatePlan,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
    UsageTier,
    UsageUnit,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


_EFFECTIVE_FROM = date(2026, 7, 1)
_ELECTRIC_ADJUSTMENTS = (
    Adjustment("fuel", "Fuel", "Included in the published energy charge; subject to adjustment.", True),
    Adjustment("dsm", "Demand Side Management", "Included in the published energy charge.", True),
    Adjustment("pension", "Pension Costs", "Included in the published energy charge.", True),
    Adjustment("storm_damage", "Storm Damage", "Included in the published energy charge.", True),
    Adjustment("der", "Distributed Energy Resource Program", "A $1.00 monthly charge is added separately.", False),
)
_ELECTRIC_FIXED_CHARGES = (MonthlyCharge(name="Distributed Energy Resource Program", amount=Decimal("1.00")),)


def _seasonal_tiers(summer_under: str, summer_over: str, winter_under: str, winter_over: str) -> TieredUsageCharge:
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


RATE_2 = RatePlan(
    code="rate_2",
    name="Rate 2 - Low Use Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *_ELECTRIC_FIXED_CHARGES,
        FlatUsageCharge(name="Energy", price_per_unit=Decimal("0.13111")),
    ),
    eligibility_rules=(
        EligibilityRule(
            "preceding_billing_periods_below_threshold",
            "Usage must not exceed 400 kWh in each of the preceding twelve billing periods.",
            MappingProxyType({"period_count": 12, "usage_threshold": Decimal("400"), "usage_unit": "kWh"}),
        ),
        EligibilityRule("second_exceedance_terminates", "The second billing period exceeding 400 kWh terminates eligibility."),
    ),
    adjustments=_ELECTRIC_ADJUSTMENTS,
)

RATE_5 = RatePlan(
    code="rate_5",
    name="Rate 5 - Residential Service: Time of Use",
    commodity=Commodity.ELECTRICITY,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *_ELECTRIC_FIXED_CHARGES,
        TimeOfUseCharge(
            name="Energy",
            periods_by_season=MappingProxyType(
                {
                    Season.SUMMER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.29907"), (TimeWindow(time(16), time(20)),)),
                        TimeOfUsePeriod("super_off_peak", Decimal("0.09623"), (TimeWindow(time(1), time(5)),)),
                        TimeOfUsePeriod("off_peak", Decimal("0.15074"), fallback=True),
                    ),
                    Season.WINTER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.29907"), (TimeWindow(time(6), time(9)),)),
                        TimeOfUsePeriod(
                            "super_off_peak",
                            Decimal("0.09623"),
                            (TimeWindow(time(1), time(5)), TimeWindow(time(12), time(15))),
                        ),
                        TimeOfUsePeriod("off_peak", Decimal("0.15074"), fallback=True),
                    ),
                }
            ),
        ),
    ),
    adjustments=_ELECTRIC_ADJUSTMENTS,
)

RATE_6 = RatePlan(
    code="rate_6",
    name="Rate 6 - Residential Service: Energy Saver/Conservation Rate",
    commodity=Commodity.ELECTRICITY,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *_ELECTRIC_FIXED_CHARGES,
        _seasonal_tiers("0.15333", "0.16842", "0.15333", "0.14729"),
    ),
    eligibility_rules=(
        EligibilityRule(
            "energy_conservation_requirements",
            "The dwelling must satisfy the published insulation, equipment, and efficiency requirements.",
        ),
    ),
    adjustments=_ELECTRIC_ADJUSTMENTS,
)

RATE_7 = RatePlan(
    code="rate_7",
    name="Rate 7 - Residential Service: Time-of-Use Demand",
    commodity=Commodity.ELECTRICITY,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *_ELECTRIC_FIXED_CHARGES,
        TimeOfUseCharge(
            name="Energy",
            periods_by_season=MappingProxyType(
                {
                    Season.SUMMER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.17441"), (TimeWindow(time(16), time(20)),)),
                        TimeOfUsePeriod("super_off_peak", Decimal("0.08841"), (TimeWindow(time(1), time(5)),)),
                        TimeOfUsePeriod("off_peak", Decimal("0.10124"), fallback=True),
                    ),
                    Season.WINTER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.17441"), (TimeWindow(time(6), time(9)),)),
                        TimeOfUsePeriod(
                            "super_off_peak",
                            Decimal("0.08841"),
                            (TimeWindow(time(1), time(5)), TimeWindow(time(12), time(15))),
                        ),
                        TimeOfUsePeriod("off_peak", Decimal("0.10124"), fallback=True),
                    ),
                }
            ),
        ),
        DemandCharge(
            name="On-Peak Billing Demand",
            price_per_kw=Decimal("10.90"),
            interval_minutes=15,
            qualifying_period="on_peak",
            rolling_interval=True,
        ),
    ),
    adjustments=_ELECTRIC_ADJUSTMENTS,
)

RATE_8 = RatePlan(
    code="rate_8",
    name="Rate 8 - Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *_ELECTRIC_FIXED_CHARGES,
        _seasonal_tiers("0.15878", "0.17442", "0.15878", "0.15253"),
    ),
    adjustments=_ELECTRIC_ADJUSTMENTS,
)

_GAS_ADJUSTMENTS = (
    Adjustment("gas_costs", "Gas Costs", "Included in the published energy charge; subject to adjustment.", True),
    Adjustment("dsm", "Demand Side Management", "Included in the published energy charge.", True),
    Adjustment(
        "weather_normalization", "Weather Normalization Adjustment", "Applies to November-April billing months.", False
    ),
)

RATE_32S = RatePlan(
    code="rate_32s",
    name="Rate 32S - Gas Residential Standard Service",
    commodity=Commodity.GAS,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("2.04149")),
    ),
    adjustments=_GAS_ADJUSTMENTS,
)

RATE_32V = RatePlan(
    code="rate_32v",
    name="Rate 32V - Gas Residential Value Service",
    commodity=Commodity.GAS,
    effective_from=_EFFECTIVE_FROM,
    effective_to=None,
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("1.91847")),
    ),
    eligibility_rules=(
        EligibilityRule(
            "summer_average_minimum",
            "Average usage during June, July, and August must be at least 10 therms.",
            MappingProxyType({"months": "6,7,8", "minimum_usage": Decimal("10"), "usage_unit": "therm"}),
        ),
        EligibilityRule(
            "annual_reassignment", "Accounts not meeting the standard are placed on Rate 32S beginning in November."
        ),
    ),
    adjustments=_GAS_ADJUSTMENTS,
)

RESIDENTIAL_ELECTRIC_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {plan.code: plan for plan in (RATE_2, RATE_5, RATE_6, RATE_7, RATE_8)}
)
RESIDENTIAL_GAS_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType({plan.code: plan for plan in (RATE_32S, RATE_32V)})
RESIDENTIAL_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {**RESIDENTIAL_ELECTRIC_RATE_PLANS, **RESIDENTIAL_GAS_RATE_PLANS}
)


def get_rate_plan(code: str) -> RatePlan | None:
    """Return a residential rate plan by code, or ``None`` when unknown."""
    return RESIDENTIAL_RATE_PLANS.get(code)


def get_available_rate_plans() -> tuple[RatePlan, ...]:
    """Return all currently catalogued residential rate plans."""
    return tuple(RESIDENTIAL_RATE_PLANS.values())
