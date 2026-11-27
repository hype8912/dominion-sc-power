"""Frozen copy of ha-dominion-sc's 0.3.0-era pricing logic, for the equivalence test only.

Copied from ``ha-dominion-sc/custom_components/dominionsc/`` (working tree of 2026-11-27):
``cost.py`` (``_calculate_cost_for_wh`` and the helpers it dispatches to), ``billing.py``, and the
cycle-tracking loop of ``aggregation.py`` ``aggregate_hourly_data``. Home Assistant types, the ``none`` and
``fixed`` cost modes, hourly bucketing, ``existing_hours`` and ``cost_start_date`` are stripped; the pricing
arithmetic and cycle bookkeeping are unchanged.

Delete this package once the integration has migrated to ``dominionsc.UsagePricer``
(see docs/PRICING_API_PLAN.md, Phase 3).
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from dominionsc import (
    Commodity,
    FlatUsageCharge,
    RatePlan,
    TieredUsageCharge,
    TimeOfUseCharge,
    get_rate_plan_for_date,
    get_rate_plan_history,
    get_time_of_use_rate,
    season_for,
)
from dominionsc.time_of_use import LOCAL_TIMEZONE

if TYPE_CHECKING:
    from collections.abc import Iterable


# --- cost.py ------------------------------------------------------------------


def _utility_local_date(when: datetime) -> date:
    if when.tzinfo is None:
        return when.date()
    return when.astimezone(LOCAL_TIMEZONE).date()


def _calculate_tiered_cost(
    interval_wh: float, interval_dt: datetime, cumulative_wh_before: float, rate_plan: RatePlan
) -> float:
    for charge in rate_plan.charges:
        if not isinstance(charge, TieredUsageCharge):
            continue
        tiers = charge.tiers_by_season[season_for(_utility_local_date(interval_dt))]
        upper_bound = tiers[0].upper_bound
        assert upper_bound is not None
        boundary_wh = float(upper_bound) * 1000
        rate_under = float(tiers[0].price_per_unit) / 1000
        rate_over = float(tiers[1].price_per_unit) / 1000
        cumulative_after = cumulative_wh_before + interval_wh
        if cumulative_after <= boundary_wh:
            return interval_wh * rate_under
        if cumulative_wh_before >= boundary_wh:
            return interval_wh * rate_over
        wh_under = boundary_wh - cumulative_wh_before
        wh_over = interval_wh - wh_under
        return wh_under * rate_under + wh_over * rate_over
    return 0.0


def _calculate_flat_cost(interval_usage: float, rate_plan: RatePlan) -> float:
    for charge in rate_plan.charges:
        if not isinstance(charge, FlatUsageCharge):
            continue
        if rate_plan.commodity == Commodity.GAS:
            return interval_usage / 100.0 * float(charge.price_per_unit)
        return interval_usage / 1000.0 * float(charge.price_per_unit)
    return 0.0


def _calculate_tou_cost(interval_wh: float, interval_dt: datetime, rate_plan: RatePlan) -> float:
    try:
        rate = get_time_of_use_rate(rate_plan, interval_dt)
    except ValueError:
        return 0.0
    return interval_wh * float(rate.price_per_kwh) / 1000


def _calculate_plan_cost(interval_wh: float, interval_dt: datetime, cumulative_wh_before: float, rate_plan: RatePlan) -> float:
    if any(isinstance(c, TieredUsageCharge) for c in rate_plan.charges):
        return _calculate_tiered_cost(interval_wh, interval_dt, cumulative_wh_before, rate_plan)
    if any(isinstance(c, TimeOfUseCharge) for c in rate_plan.charges):
        return _calculate_tou_cost(interval_wh, interval_dt, rate_plan)
    if any(isinstance(c, FlatUsageCharge) for c in rate_plan.charges):
        return _calculate_flat_cost(interval_wh, rate_plan)
    return 0.0


def calculate_cost_for_wh(
    interval_wh: float, interval_dt: datetime, cumulative_wh_before: float, rate_plan: RatePlan
) -> float:
    """``_calculate_cost_for_wh`` for a rate-plan cost mode."""
    interval_date = _utility_local_date(interval_dt)
    plan_for_date: RatePlan | None
    if get_rate_plan_history(rate_plan.code):
        plan_for_date = get_rate_plan_for_date(rate_plan.code, interval_date)
    else:
        plan_for_date = rate_plan if interval_date >= rate_plan.effective_from else None
    if plan_for_date is not None:
        return _calculate_plan_cost(interval_wh, interval_dt, cumulative_wh_before, plan_for_date)
    return 0.0


# --- billing.py ---------------------------------------------------------------


def billing_cycle_get_gap(d: date) -> int:
    """``_billing_cycle_get_gap``."""
    gaps = {1: 30, 2: 31, 3: 30, 5: 30, 7: 30, 8: 31, 9: 31, 10: 30, 11: 31, 12: 30}
    m = d.month
    if m in gaps:
        return gaps[m]
    near_leap = calendar.isleap(d.year) or calendar.isleap(d.year + 1)
    if m == 4:
        return 31 if near_leap else 30
    if m == 6:
        return 30 if near_leap else 31
    return 30


def estimate_billing_cycles(
    anchor_start: date, anchor_end: date, earliest: date, latest: date | None = None
) -> list[tuple[date, date]]:
    """``_estimate_billing_cycles``."""
    starts: list[date] = [anchor_start]
    cur = anchor_start
    while cur > earliest:
        prev_month = cur.month - 1 or 12
        prev_year = cur.year - (1 if cur.month == 1 else 0)
        cur -= timedelta(days=billing_cycle_get_gap(date(prev_year, prev_month, 1)))
        starts.append(cur)
    starts.reverse()
    cycles = [(starts[i], starts[i + 1] - timedelta(days=1)) for i in range(len(starts) - 1)]
    cycles.append((anchor_start, anchor_end))
    if latest is not None and latest > anchor_end:
        cur = anchor_end + timedelta(days=1)
        while cur <= latest:
            gap = billing_cycle_get_gap(cur)
            cycle_end = cur + timedelta(days=gap - 1)
            cycles.append((cur, cycle_end))
            cur = cycle_end + timedelta(days=1)
    return cycles


def find_billing_cycle_for_date(target: date, billing_cycles: list[tuple[date, date]]) -> tuple[date, date] | None:
    """``_find_billing_cycle_for_date``."""
    for start, end in billing_cycles:
        if start <= target <= end:
            return (start, end)
    return None


# --- aggregation.py -----------------------------------------------------------


def price_stream(
    reads: Iterable[tuple[datetime, float]],
    rate_plan: RatePlan,
    billing_cycles: list[tuple[date, date]],
) -> list[float]:
    """Price *reads* with the cycle-tracking loop of ``aggregate_hourly_data``, one cost per read.

    *reads* are ``(start_time, consumption)`` pairs with local, aware timestamps, as the parser returns them.
    """
    cumulative_wh = 0.0
    current_cycle: tuple[date, date] | None = None
    costs: list[float] = []
    for start_time, consumption in sorted(reads, key=lambda r: r[0]):
        if billing_cycles:
            row_cycle = find_billing_cycle_for_date(start_time.date(), billing_cycles)
            if row_cycle != current_cycle:
                current_cycle = row_cycle
                cumulative_wh = 0.0
        costs.append(calculate_cost_for_wh(consumption, start_time, cumulative_wh, rate_plan))
        cumulative_wh += consumption
    return costs
