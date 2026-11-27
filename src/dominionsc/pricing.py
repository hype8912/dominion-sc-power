"""Price meter usage under a rate plan.

Consumers pass a plan, a timestamp, a quantity in the meter's unit and (for tiered plans) cycle-to-date
usage; this module returns dollars. It owns every pricing decision: which tariff period is in effect, the
season, the tier split, the time-of-use period, unit conversion, and which charges cannot be priced per
interval.

Only usage charges (``FlatUsageCharge``, ``TieredUsageCharge``, ``TimeOfUseCharge``) are priced here.
``DemandCharge`` needs billing-period peak demand, so it is never included in an amount; its name is listed
in ``unpriced_charges`` instead. ``DailyCharge`` and ``MonthlyCharge`` are fixed per day or per cycle and are
also left out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from .local_time import utility_local_date
from .models.rate_plan import (
    Commodity,
    DemandCharge,
    FlatUsageCharge,
    RatePlan,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    UsageTier,
    UsageUnit,
)
from .rates import resolve_plan_for
from .time_of_use import TimeOfUseRate, get_time_of_use_rate, season_for
from .units import DEFAULT_THERMS_PER_CCF, to_billing_units, to_decimal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from .models.units import MeterUnit

__all__: list[str] = ["NetUsageCost", "RateQuote", "UsageCost", "price_net_usage", "price_usage", "rate_at"]

_LOGGER = logging.getLogger(__name__)

_ZERO: Decimal = Decimal(0)

# Billing unit for a plan with no usage charge to name one.
_BILLING_UNIT_FOR: dict[Commodity, UsageUnit] = {Commodity.ELECTRICITY: UsageUnit.KWH, Commodity.GAS: UsageUnit.THERM}

type _UsageCharge = FlatUsageCharge | TieredUsageCharge | TimeOfUseCharge


@dataclass(frozen=True, slots=True)
class RateQuote:
    """The price in force at one moment.

    Attributes:
        plan: The tariff period actually used (may be a superseded period of the plan passed in).
        price_per_unit: Dollars per billing unit (kWh or therm).
        usage_unit: The billing unit ``price_per_unit`` is per.
        season: The season at that moment, or ``None`` for plans whose usage charge is not seasonal (flat).
        period: Time-of-use period name (e.g. ``"on_peak"``), or ``None`` for non-time-of-use plans.
        tier: ``UsageTier.name`` of the tier in force, or ``None`` for non-tiered plans.
        tier_upper_bound: That tier's ``upper_bound`` (``None`` for the open-ended tier or non-tiered plans).
        unpriced_charges: Names of charges that are not part of ``price_per_unit`` because they cannot be
            priced per unit of usage (for example ``"On-Peak Billing Demand"`` on Rate 7).

    """

    plan: RatePlan
    price_per_unit: Decimal
    usage_unit: UsageUnit
    season: Season | None
    period: str | None
    tier: str | None
    tier_upper_bound: Decimal | None
    unpriced_charges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UsageCost:
    """The cost of one quantity of usage.

    Attributes:
        amount: Cost in dollars, unrounded. Negative when the quantity is negative.
        quantity: The quantity priced, in the plan's billing unit (kWh or therm), after conversion.
        plan: The tariff period actually used.
        season: The season, or ``None`` for plans whose usage charge is not seasonal (flat).
        period: Time-of-use period name, or ``None`` for non-time-of-use plans.
        tiers: Every tier name the quantity touched, in tier order. Empty for non-tiered plans. A zero
            quantity reports the tier the next unit would be priced in.
        unpriced_charges: Names of charges left out of ``amount`` (see ``RateQuote.unpriced_charges``).

    """

    amount: Decimal
    quantity: Decimal
    plan: RatePlan
    season: Season | None
    period: str | None
    tiers: tuple[str, ...]
    unpriced_charges: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NetUsageCost:
    """Usage and solar generation in one interval, each priced on its own and netted together.

    Generation is credited at the same rate usage costs at that moment, and is priced after the interval's
    usage, so on a tiered plan it offsets the most recently used (highest-tier) energy first. The net
    ``amount`` always equals pricing the net quantity directly.

    Attributes:
        usage: The cost of the energy used (``amount`` zero or positive).
        generation: The credit for the energy generated (``amount`` zero or negative, ``quantity`` negative).
        amount: ``usage.amount + generation.amount``: the net cost in dollars, negative for a net credit.
        quantity: Net quantity in the plan's billing unit: used minus generated.

    """

    usage: UsageCost
    generation: UsageCost
    amount: Decimal
    quantity: Decimal


def _usage_charge(plan: RatePlan) -> _UsageCharge | None:
    """Return *plan*'s single usage-based charge, or ``None`` if it has none.

    Raises:
        ValueError: If the plan has more than one usage-based charge, which pricing does not support.

    """
    charges: list[_UsageCharge] = [
        c for c in plan.charges if isinstance(c, FlatUsageCharge | TieredUsageCharge | TimeOfUseCharge)
    ]
    if len(charges) > 1:
        msg = f"{plan.code} has {len(charges)} usage charges; pricing supports exactly one"
        raise ValueError(msg)
    return charges[0] if charges else None


def _unpriced_charges(plan: RatePlan) -> tuple[str, ...]:
    """Return the names of *plan*'s charges that cannot be priced per unit of usage."""
    return tuple(c.name for c in plan.charges if isinstance(c, DemandCharge))


def _seasonal_tiers(plan: RatePlan, charge: TieredUsageCharge, season: Season) -> tuple[UsageTier, ...] | None:
    tiers: tuple[UsageTier, ...] = charge.tiers_by_season.get(season, ())
    if not tiers:
        _LOGGER.debug("%s has no usage tiers for %s", plan.code, season)
        return None
    return tiers


def _tier_for(tiers: Sequence[UsageTier], usage: Decimal) -> UsageTier:
    """Return the tier that prices the next unit after *usage* cycle-to-date units.

    A tier covers usage below its ``upper_bound``; the first unbounded tier, or the last tier if all are
    bounded, takes everything beyond.
    """
    return next((t for t in tiers if t.upper_bound is None or usage < t.upper_bound), tiers[-1])


def _tier_split(tiers: Sequence[UsageTier], start: Decimal, end: Decimal) -> list[tuple[UsageTier, Decimal]]:
    """Split cumulative usage ``[start, end)`` across *tiers*, returning ``(tier, portion)`` pairs.

    Requires ``start <= end``. Handles any number of tiers. The first tier also covers usage below zero, and
    the first unbounded tier (or the last tier, if every tier is bounded) covers everything above.
    """
    # Tiers after the first unbounded one can never be reached.
    open_index: int = next((i for i, t in enumerate(tiers) if t.upper_bound is None), len(tiers) - 1)
    parts: list[tuple[UsageTier, Decimal]] = []
    lower: Decimal | None = None  # None: the first tier has no lower bound
    for index, tier in enumerate(tiers[: open_index + 1]):
        upper: Decimal | None = None if index == open_index else tier.upper_bound
        low: Decimal = start if lower is None else max(start, lower)
        high: Decimal = end if upper is None else min(end, upper)
        if high > low:
            parts.append((tier, high - low))
        lower = upper
    return parts


def rate_at(
    plan: RatePlan,
    when: datetime,
    cycle_usage: Decimal | float | None = None,
) -> RateQuote | None:
    """Return the price per billing unit under *plan* at *when*.

    The tariff period in effect at *when* is resolved first (``resolve_plan_for``), so passing the current
    plan for a past moment quotes the past period's price.

    Args:
        plan: Any period of the plan, usually the current one (e.g. ``RATE_8``).
        when: The moment to quote. Naive values are read as local time (``America/New_York``); aware values
            are converted to it.
        cycle_usage: Usage so far this billing cycle, in the plan's billing unit (kWh or therm). Picks the
            tier for tiered plans; ``None`` (unknown) reports the first tier. Ignored for other plans.

    Returns:
        A ``RateQuote``, or ``None`` when no tariff period is in effect at *when* or the plan's time-of-use or
        tier data cannot price that moment. A plan with no usage charge quotes a price of zero.

    Raises:
        ValueError: If the plan in effect has more than one usage-based charge.

    """
    resolved: RatePlan | None = resolve_plan_for(plan, when)
    if resolved is None:
        return None
    charge: _UsageCharge | None = _usage_charge(resolved)
    unpriced: tuple[str, ...] = _unpriced_charges(resolved)
    if charge is None:
        # Only fixed (or demand) charges: usage itself costs nothing.
        return RateQuote(resolved, _ZERO, _BILLING_UNIT_FOR[resolved.commodity], None, None, None, None, unpriced)

    if isinstance(charge, TimeOfUseCharge):
        tou: TimeOfUseRate | None = _time_of_use_rate(resolved, when)
        if tou is None:
            return None
        return RateQuote(resolved, tou.price_per_kwh, charge.usage_unit, tou.season, tou.period, None, None, unpriced)

    if isinstance(charge, TieredUsageCharge):
        season: Season = season_for(utility_local_date(when))
        tiers: tuple[UsageTier, ...] | None = _seasonal_tiers(resolved, charge, season)
        if tiers is None:
            return None
        usage: Decimal = _ZERO if cycle_usage is None else to_decimal(cycle_usage)
        tier: UsageTier = _tier_for(tiers, usage)
        return RateQuote(resolved, tier.price_per_unit, charge.usage_unit, season, None, tier.name, tier.upper_bound, unpriced)

    return RateQuote(resolved, charge.price_per_unit, charge.usage_unit, None, None, None, None, unpriced)


def price_usage(
    plan: RatePlan,
    when: datetime,
    quantity: Decimal | float,
    unit: MeterUnit,
    *,
    cycle_usage_before: Decimal | float = 0,
    therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF,
) -> UsageCost | None:
    """Return the cost of *quantity* of usage starting at *when*.

    Works for any interval length (15-minute reads, hourly rows). The whole interval is priced as of its
    start: its season, time-of-use period and tariff period are those in effect at *when*.

    Args:
        plan: Any period of the plan, usually the current one (e.g. ``RATE_8``).
        when: Start of the interval. Naive values are read as local time; aware values are converted.
        quantity: Usage in *unit* (Wh for electric, ft³ for gas).
        unit: The meter unit of *quantity* and *cycle_usage_before*.
        cycle_usage_before: Usage this billing cycle before this interval, in *unit*. For tiered plans it
            decides which tiers the quantity falls in; an interval crossing one or more tier boundaries is
            split across them. Ignored for other plans.
        therms_per_ccf: Therms per hundred cubic feet, used only for gas.

    Returns:
        A ``UsageCost``, or ``None`` when no tariff period is in effect at *when* or the plan's time-of-use or
        tier data cannot price that moment. A plan with no usage charge costs zero.

    Raises:
        ValueError: If *unit* does not measure the plan's commodity, or the plan in effect has more than one
            usage-based charge.

    """
    billing_quantity: Decimal = to_billing_units(quantity, unit, plan, therms_per_ccf=therms_per_ccf)
    billing_before: Decimal = to_billing_units(cycle_usage_before, unit, plan, therms_per_ccf=therms_per_ccf)
    return _price_billing_units(plan, when, billing_quantity, billing_before)


def price_net_usage(
    plan: RatePlan,
    when: datetime,
    used: Decimal | float,
    generated: Decimal | float,
    unit: MeterUnit,
    *,
    cycle_usage_before: Decimal | float = 0,
    therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF,
) -> NetUsageCost | None:
    """Price an interval's usage and generation separately, and net them.

    Args:
        plan: Any period of the plan, usually the current one (e.g. ``RATE_8``).
        when: Start of the interval. Naive values are read as local time; aware values are converted.
        used: Energy taken from the grid in *unit* (the grid register's read).
        generated: Energy sent to the grid in *unit*. Only its size counts, so a solar-export register's
            negative read can be passed as is.
        unit: The meter unit of *used*, *generated* and *cycle_usage_before*.
        cycle_usage_before: Net usage this billing cycle before this interval, in *unit*.
        therms_per_ccf: Therms per hundred cubic feet, used only for gas.

    Returns:
        A ``NetUsageCost``, or ``None`` when ``price_usage`` would return ``None`` for this moment.

    Raises:
        ValueError: As for ``price_usage``.

    """
    convert = to_billing_units
    return _price_net_billing_units(
        plan,
        when,
        convert(used, unit, plan, therms_per_ccf=therms_per_ccf),
        abs(convert(generated, unit, plan, therms_per_ccf=therms_per_ccf)),
        convert(cycle_usage_before, unit, plan, therms_per_ccf=therms_per_ccf),
    )


def _price_net_billing_units(
    plan: RatePlan, when: datetime, used: Decimal, generated: Decimal, before: Decimal
) -> NetUsageCost | None:
    """Price *used* then the credit for *generated* (both billing units, *generated* not negative)."""
    usage: UsageCost | None = _price_billing_units(plan, when, used, before)
    if usage is None:
        return None
    generation: UsageCost | None = _price_billing_units(plan, when, -generated, before + used)
    assert generation is not None  # same plan, same moment: priceable if usage was
    return NetUsageCost(usage, generation, usage.amount + generation.amount, used - generated)


def _price_billing_units(plan: RatePlan, when: datetime, quantity: Decimal, before: Decimal) -> UsageCost | None:
    """Price *quantity* billing units at *when* with *before* billing units already used this cycle."""
    resolved: RatePlan | None = resolve_plan_for(plan, when)
    if resolved is None:
        return None
    charge: _UsageCharge | None = _usage_charge(resolved)
    unpriced: tuple[str, ...] = _unpriced_charges(resolved)
    if charge is None:
        # Only fixed (or demand) charges: usage itself costs nothing.
        return UsageCost(_ZERO, quantity, resolved, None, None, (), unpriced)

    if isinstance(charge, TimeOfUseCharge):
        tou: TimeOfUseRate | None = _time_of_use_rate(resolved, when)
        if tou is None:
            return None
        return UsageCost(quantity * tou.price_per_kwh, quantity, resolved, tou.season, tou.period, (), unpriced)

    if isinstance(charge, TieredUsageCharge):
        season: Season = season_for(utility_local_date(when))
        tiers: tuple[UsageTier, ...] | None = _seasonal_tiers(resolved, charge, season)
        if tiers is None:
            return None
        after: Decimal = before + quantity
        parts: list[tuple[UsageTier, Decimal]] = _tier_split(tiers, min(before, after), max(before, after))
        amount: Decimal = sum((portion * tier.price_per_unit for tier, portion in parts), _ZERO)
        if quantity < 0:
            amount = -amount
        names: tuple[str, ...] = tuple(tier.name for tier, _ in parts) or (_tier_for(tiers, before).name,)
        return UsageCost(amount, quantity, resolved, season, None, names, unpriced)

    return UsageCost(quantity * charge.price_per_unit, quantity, resolved, None, None, (), unpriced)


def _time_of_use_rate(plan: RatePlan, when: datetime) -> TimeOfUseRate | None:
    """Return the library's time-of-use rate, or ``None`` (logged at debug) when it cannot price *when*."""
    try:
        return get_time_of_use_rate(plan, when)
    except ValueError as err:
        _LOGGER.debug("No time-of-use rate for %s at %s: %s", plan.code, when, err)
        return None
