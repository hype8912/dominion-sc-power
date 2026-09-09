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
    """A fixed charge assessed for each service day."""

    kind: Literal["daily"] = "daily"
    name: str = ""
    amount: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class MonthlyCharge:
    """A fixed charge assessed once per billing cycle or month."""

    kind: Literal["monthly"] = "monthly"
    name: str = ""
    amount: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class FlatUsageCharge:
    """A single price applied to every unit of usage."""

    kind: Literal["flat_usage"] = "flat_usage"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    price_per_unit: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class UsageTier:
    """One cumulative usage tier within a billing period."""

    name: str
    upper_bound: Decimal | None
    price_per_unit: Decimal


@dataclass(frozen=True, slots=True)
class TieredUsageCharge:
    """A cumulative usage charge with optional seasonal tier schedules."""

    kind: Literal["tiered_usage"] = "tiered_usage"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    tiers_by_season: Mapping[Season, tuple[UsageTier, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open local-time interval used by a time-of-use period."""

    start: time
    end: time


@dataclass(frozen=True, slots=True)
class TimeOfUsePeriod:
    """A named time-of-use price and its matching windows."""

    name: str
    price_per_unit: Decimal
    windows: tuple[TimeWindow, ...] = ()
    fallback: bool = False


@dataclass(frozen=True, slots=True)
class TimeOfUseCharge:
    """A usage charge selected by local time and billing season."""

    kind: Literal["time_of_use"] = "time_of_use"
    name: str = ""
    usage_unit: UsageUnit = UsageUnit.KWH
    periods_by_season: Mapping[Season, tuple[TimeOfUsePeriod, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DemandCharge:
    """A charge based on measured demand rather than energy consumption."""

    kind: Literal["demand"] = "demand"
    name: str = ""
    price_per_kw: Decimal = Decimal("0")
    interval_minutes: int = 15
    qualifying_period: str = ""
    rolling_interval: bool = True


Charge: TypeAlias = DailyCharge | MonthlyCharge | FlatUsageCharge | TieredUsageCharge | TimeOfUseCharge | DemandCharge


@dataclass(frozen=True, slots=True)
class EligibilityRule:
    """Descriptive eligibility requirement from a published tariff."""

    code: str
    description: str
    parameters: Mapping[str, str | int | Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Adjustment:
    """Descriptive tariff adjustment or billing component."""

    code: str
    name: str
    description: str
    included_in_published_charge: bool = False


@dataclass(frozen=True, slots=True)
class RatePlan:
    """A versioned, declarative Dominion Energy South Carolina tariff."""

    code: str
    name: str
    commodity: Commodity
    effective_from: date
    effective_to: date | None
    charges: tuple[Charge, ...]
    eligibility_rules: tuple[EligibilityRule, ...] = ()
    adjustments: tuple[Adjustment, ...] = ()
    description: str = ""
