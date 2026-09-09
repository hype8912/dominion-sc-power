"""Data models for Dominion Energy South Carolina rate plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date, time


class Commodity(StrEnum):
    """Utility commodity billed by a rate plan."""

    ELECTRICITY = "electricity"
    GAS = "gas"


class UsageUnit(StrEnum):
    """Units used by usage-based charges."""

    KWH = "kWh"
    THERM = "therm"


class Season(StrEnum):
    """Billing seasons used by South Carolina residential tariffs."""

    SUMMER = "summer"
    WINTER = "winter"


@dataclass(frozen=True, slots=True)
class DailyCharge:
    """A fixed charge assessed for each calendar day of service.

    The total monthly charge equals ``amount * number_of_days_in_billing_period``.
    Dominion Energy SC uses daily (rather than monthly) fixed charges so that
    billing periods of different lengths all produce consistent per-day costs.

    Attributes:
        kind: Discriminant literal ``"daily"`` for type-narrowing.
        name: Human-readable charge name (e.g., ``"Basic Facilities Charge"``).
        amount: Dollar amount per service day.

    """

    kind: Literal["daily"] = "daily"
    name: str = ""
    amount: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class MonthlyCharge:
    """A fixed charge assessed once per billing cycle, regardless of usage.

    Attributes:
        kind: Discriminant literal ``"monthly"`` for type-narrowing.
        name: Human-readable charge name.
        amount: Dollar amount per billing cycle.

    """

    kind: Literal["monthly"] = "monthly"
    name: str = ""
    amount: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class FlatUsageCharge:
    """A single uniform price applied to every unit of consumption.

    Unlike ``TieredUsageCharge``, the rate does not change based on how
    much energy has been used.

    Attributes:
        kind: Discriminant literal ``"flat_usage"`` for type-narrowing.
        name: Human-readable charge name (e.g., ``"Energy"``).
        usage_unit: Unit of measurement for the consumption (``kWh`` or ``therm``).
        price_per_unit: Dollar cost for each unit consumed.

    """

    kind: Literal["flat_usage"] = "flat_usage"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    price_per_unit: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class UsageTier:
    """One cumulative usage tier within a tiered billing structure.

    Tiers are applied in order: the first tier covers usage from 0 to
    ``upper_bound``; the next tier covers usage above that limit; and so on.
    A ``None`` upper bound means "all remaining usage".

    Attributes:
        name: Human-readable tier label (e.g., ``"First 800 kWh"``).
        upper_bound: Cumulative kWh (or therm) threshold at which this tier
            ends. ``None`` means the tier is unbounded (the final tier).
        price_per_unit: Dollar rate for each unit of consumption within
            this tier.

    """

    name: str
    upper_bound: Decimal | None
    price_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class TieredUsageCharge:
    """A cumulative tiered usage charge that can vary by billing season.

    Dominion Energy SC separates summer (June-September) from winter
    (October-May) pricing. The ``tiers_by_season`` mapping provides a
    distinct sequence of ``UsageTier`` objects for each season.

    Attributes:
        kind: Discriminant literal ``"tiered_usage"`` for type-narrowing.
        name: Human-readable charge name.
        usage_unit: Unit of measurement (``kWh`` for electric, ``therm`` for gas).
        tiers_by_season: Maps ``Season.SUMMER`` and ``Season.WINTER`` to an
            ordered tuple of ``UsageTier`` objects applied cumulatively.

    """

    kind: Literal["tiered_usage"] = "tiered_usage"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    tiers_by_season: Mapping[Season, tuple[UsageTier, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open local-clock-time interval ``[start, end)``.

    Used by ``TimeOfUsePeriod`` to define which hours qualify for a given
    time-of-use price. Times are evaluated in the utility's local timezone
    (``America/New_York``).

    Attributes:
        start: Inclusive start time (local clock, e.g. ``time(16, 0)`` for 4 PM).
        end: Exclusive end time (e.g. ``time(20, 0)`` for 8 PM).

    """

    start: time
    end: time


@dataclass(frozen=True, slots=True)
class TimeOfUsePeriod:
    """A named time-of-use price tier and the clock windows that activate it.

    A ``TimeOfUseCharge`` groups several ``TimeOfUsePeriod`` objects per
    season. During billing, each 15-minute interval is matched against the
    active ``TimeOfUsePeriod`` by checking whether the interval's local
    start time falls inside any of the period's ``windows``. If no
    ``windows`` match, the period with ``fallback=True`` is used.

    Attributes:
        name: Stable identifier for this period (e.g., ``"on_peak"``,
            ``"off_peak"``, ``"super_off_peak"``).
        price_per_unit: Dollar cost per kWh during this period.
        windows: Clock-time ranges that activate this period. Empty tuple
            means the period has no explicit windows (use only as fallback).
        fallback: If ``True``, this period applies to all intervals that
            do not match any other period's ``windows``. Exactly one period
            per season should set this to ``True``.

    """

    name: str
    price_per_unit: Decimal
    windows: tuple[TimeWindow, ...] = ()
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class TimeOfUseCharge:
    """A usage charge whose per-unit rate depends on the time of day and season.

    Rates differ by ``Season`` (summer vs. winter) and by ``TimeOfUsePeriod``
    (on-peak, off-peak, super-off-peak). Each 15-minute interval is billed
    at the rate for the period that was active at the interval's local start time.

    Attributes:
        kind: Discriminant literal ``"time_of_use"`` for type-narrowing.
        name: Human-readable charge name.
        usage_unit: Always ``kWh`` for Dominion Energy SC electric TOU rates.
        periods_by_season: Maps ``Season`` to an ordered tuple of
            ``TimeOfUsePeriod`` objects. Exactly one period per season must
            have ``fallback=True``.

    """

    kind: Literal["time_of_use"] = "time_of_use"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    periods_by_season: Mapping[Season, tuple[TimeOfUsePeriod, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DemandCharge:
    """A charge based on peak measured demand rather than total energy consumption.

    Demand is measured as the highest average power (in kW) observed during
    any qualifying ``interval_minutes``-minute window within an on-peak period
    during the billing cycle.

    Attributes:
        kind: Discriminant literal ``"demand"`` for type-narrowing.
        name: Human-readable charge name.
        price_per_kw: Dollar cost per kW of measured peak demand.
        interval_minutes: Length of the measurement window in minutes.
            Dominion Energy SC uses 15-minute intervals.
        qualifying_period: The ``TimeOfUsePeriod.name`` that must be active
            for an interval to qualify toward the demand measurement
            (e.g., ``"on_peak"``).
        rolling_interval: If ``True``, the demand is the maximum average
            power over any overlapping 15-minute window; if ``False``, it is
            the maximum of non-overlapping fixed windows.

    """

    kind: Literal["demand"] = "demand"
    name: str = ""
    price_per_kw: Decimal = Decimal("0")
    interval_minutes: int = 15
    qualifying_period: str = ""
    rolling_interval: bool = True


Charge: TypeAlias = DailyCharge | MonthlyCharge | FlatUsageCharge | TieredUsageCharge | TimeOfUseCharge | DemandCharge
"""Union of all concrete charge types that can appear in a ``RatePlan``.

Use this alias with ``isinstance()`` or ``match/case`` to dispatch on
charge kind::

    from dominionsc.models.rate_plan import Charge, DailyCharge

    for charge in rate_plan.charges:
        if isinstance(charge, DailyCharge):
            monthly_fixed = charge.amount * days_in_period
"""


@dataclass(frozen=True, slots=True)
class EligibilityRule:
    """A descriptive eligibility requirement copied from the published tariff.

    These are informational only -- the library does not enforce eligibility.
    Consumers can present these rules to users to help them understand whether
    they qualify for a given rate plan.

    Attributes:
        code: Short machine-readable identifier for the rule
            (e.g., ``"preceding_billing_periods_below_threshold"``).
        description: Human-readable rule description as written in the tariff.
        parameters: Optional key-value pairs that quantify the rule (e.g.,
            ``{"usage_threshold": Decimal("400"), "usage_unit": "kWh"}``).
            Empty dict when the rule has no quantifiable parameters.

    """

    code: str
    description: str
    parameters: Mapping[str, str | int | Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Adjustment:
    """A descriptive billing adjustment or pricing component from the tariff.

    Adjustments describe factors that affect the final bill but are not
    separately itemized as discrete charges. This is informational only.

    Attributes:
        code: Short machine-readable identifier (e.g., ``"fuel"``, ``"dsm"``).
        name: Human-readable adjustment name.
        description: Plain-language explanation of how the adjustment works.
        included_in_published_charge: ``True`` if this adjustment is already
            embedded in the published charge rates in ``rates.py`` (so it
            does not need to be added separately); ``False`` if it appears
            as a distinct line item on the bill.

    """

    code: str
    name: str
    description: str
    included_in_published_charge: bool = False


@dataclass(frozen=True, slots=True)
class RatePlan:
    """A versioned, declarative Dominion Energy South Carolina residential tariff.

    All rate plans are defined in ``rates.py`` and exported from the
    ``dominionsc`` package. Use ``get_rate_plan(code)`` to look up by code
    or ``get_available_rate_plans()`` to iterate all plans.

    Attributes:
        code: Short lowercase identifier matching the key in
            ``RESIDENTIAL_RATE_PLANS`` (e.g., ``"rate_8"``).
        name: Official tariff name (e.g., ``"Rate 8 - Residential Service"``).
        commodity: The utility commodity billed (``Commodity.ELECTRICITY``
            or ``Commodity.GAS``).
        effective_from: First date this rate schedule is in effect.
        effective_to: Last date in effect, or ``None`` if still current.
        charges: Ordered tuple of charge objects that together define the
            bill calculation. See the ``Charge`` union type for all variants.
        eligibility_rules: Zero or more eligibility requirements a customer
            must meet to qualify for this plan. Informational only.
        adjustments: Zero or more billing adjustments described in the tariff.
            Informational only.
        description: Optional free-text description of the plan.

    Example::

        from dominionsc import get_rate_plan, RATE_8

        plan = get_rate_plan("rate_8")
        print(plan.name)              # "Rate 8 - Residential Service"
        print(plan.commodity)         # "electricity"
        print(plan.effective_from)    # datetime.date(2026, 7, 1)
        for charge in plan.charges:
            print(charge.kind, charge.name)

    """

    code: str
    name: str
    commodity: Commodity
    effective_from: date
    effective_to: date | None
    charges: tuple[Charge, ...]
    eligibility_rules: tuple[EligibilityRule, ...] = ()
    adjustments: tuple[Adjustment, ...] = ()
    description: str = ""
