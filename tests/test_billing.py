"""Tests for billing-cycle estimation and ``UsagePricer``."""

import itertools
import math
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from dominionsc import (
    RATE_5,
    RATE_7,
    RATE_8,
    RATE_8_2025,
    RATE_32S,
    RESIDENTIAL_ELECTRIC_RATE_PLANS,
    RESIDENTIAL_GAS_RATE_PLANS,
    BillingCycle,
    Commodity,
    Forecast,
    MeterUnit,
    RatePlan,
    UsageCost,
    UsagePricer,
    billing_cycle_length,
    estimate_billing_cycles,
    find_billing_cycle,
    fixed_charges,
    price_usage,
)
from tests.legacy import ha_pricing as legacy

ET = ZoneInfo("America/New_York")
WH = MeterUnit.WATT_HOUR
FT3 = MeterUnit.CUBIC_FOOT


# --- billing_cycle_length (ported from ha-dominion-sc tests/test_coordinator.py) ---


def test_cycle_length_january() -> None:
    """January cycles are 30 days."""
    assert billing_cycle_length(date(2025, 1, 1)) == 30


def test_cycle_length_february() -> None:
    """February cycles are 31 days."""
    assert billing_cycle_length(date(2025, 2, 1)) == 31


def test_cycle_length_april_leap_vs_non_leap() -> None:
    """April cycles are 31 days near a leap year, else 30."""
    assert billing_cycle_length(date(2024, 4, 1)) == 31
    assert billing_cycle_length(date(2023, 4, 1)) == 31  # next year is a leap year
    assert billing_cycle_length(date(2025, 4, 1)) == 30


def test_cycle_length_june_leap_vs_non_leap() -> None:
    """June cycles are 30 days near a leap year, else 31."""
    assert billing_cycle_length(date(2024, 6, 1)) == 30
    assert billing_cycle_length(date(2025, 6, 1)) == 31


def test_cycle_length_matches_legacy_for_every_month() -> None:
    """Cycle lengths match the integration's table for every month of several years."""
    for year in range(2023, 2030):
        for month in range(1, 13):
            day = date(year, month, 1)
            assert billing_cycle_length(day) == legacy.billing_cycle_get_gap(day), day


# --- estimate_billing_cycles / find_billing_cycle ---------------------------------


def test_estimate_expansion() -> None:
    """Estimation covers both earliest and latest."""
    cycles = estimate_billing_cycles(BillingCycle(date(2025, 7, 1), date(2025, 7, 31)), date(2025, 5, 1), date(2025, 9, 1))
    assert cycles[0].start <= date(2025, 5, 1)
    assert cycles[-1].end >= date(2025, 9, 1)


def test_estimate_backward() -> None:
    """An anchor after earliest yields at least one cycle."""
    cycles = estimate_billing_cycles(BillingCycle(date(2025, 7, 31), date(2025, 7, 31)), date(2025, 7, 1))
    assert len(cycles) >= 1


def test_estimate_forward() -> None:
    """A latest date past the anchor projects cycles forward."""
    cycles = estimate_billing_cycles(
        BillingCycle(date(2025, 7, 1), date(2025, 7, 31)), date(2025, 7, 1), latest=date(2025, 8, 15)
    )
    assert any(c.end > date(2025, 7, 31) for c in cycles)


def test_estimate_single_month() -> None:
    """Earliest inside the anchor yields just the anchor."""
    anchor = BillingCycle(date(2025, 1, 1), date(2025, 1, 31))
    assert estimate_billing_cycles(anchor, date(2025, 1, 15)) == (anchor,)


def test_estimate_cycles_are_contiguous_and_include_anchor() -> None:
    """Estimated cycles leave no gaps and include the anchor unchanged."""
    anchor = BillingCycle(date(2026, 10, 15), date(2026, 11, 13))
    cycles = estimate_billing_cycles(anchor, date(2024, 1, 1), date(2027, 3, 1))
    assert anchor in cycles
    for earlier, later in itertools.pairwise(cycles):
        assert later.start == earlier.end + timedelta(days=1)


@pytest.mark.parametrize(
    ("anchor_start", "anchor_end", "earliest", "latest"),
    [
        (date(2025, 7, 1), date(2025, 7, 31), date(2025, 5, 1), date(2025, 9, 1)),
        (date(2026, 10, 15), date(2026, 11, 13), date(2024, 2, 1), date(2027, 6, 30)),
        (date(2024, 3, 3), date(2024, 4, 1), date(2023, 1, 1), None),
    ],
)
def test_estimate_matches_legacy(anchor_start: date, anchor_end: date, earliest: date, latest: date | None) -> None:
    """Estimation reproduces the integration's cycles exactly."""
    ours = estimate_billing_cycles(BillingCycle(anchor_start, anchor_end), earliest, latest)
    theirs = legacy.estimate_billing_cycles(anchor_start, anchor_end, earliest, latest)
    assert [(c.start, c.end) for c in ours] == theirs


def test_estimate_from_forecast() -> None:
    """A Forecast anchors estimation by its start and end dates."""
    forecast = Forecast(date(2026, 10, 15), date(2026, 11, 13), date(2026, 11, 1), 50.0, 100.0, None)
    cycles = estimate_billing_cycles(forecast, date(2026, 9, 1))
    assert cycles[-1] == BillingCycle(date(2026, 10, 15), date(2026, 11, 13))


def test_find_billing_cycle() -> None:
    """Lookup is inclusive at both ends and misses outside the cycle."""
    cycle = BillingCycle(date(2025, 7, 1), date(2025, 7, 31))
    assert find_billing_cycle(date(2025, 7, 15), [cycle]) == cycle
    assert find_billing_cycle(date(2025, 7, 1), [cycle]) == cycle
    assert find_billing_cycle(date(2025, 7, 31), [cycle]) == cycle
    assert find_billing_cycle(date(2025, 8, 1), [cycle]) is None
    assert cycle.contains(date(2025, 7, 31))
    assert not cycle.contains(date(2025, 6, 30))


# --- UsagePricer ------------------------------------------------------------------

_JULY = BillingCycle(date(2026, 7, 1), date(2026, 7, 30))
_AUGUST = BillingCycle(date(2026, 7, 31), date(2026, 8, 30))


def test_pricer_resets_at_cycle_boundary() -> None:
    """Cycle-to-date usage resets on the first read of a new cycle."""
    pricer = UsagePricer(RATE_8, [_JULY, _AUGUST])
    pricer.price(datetime(2026, 7, 30, 23, 0, tzinfo=ET), 900_000, WH)
    assert pricer.cycle_usage == Decimal(900)
    # First read of the next cycle is back in the first tier.
    cost = pricer.price(datetime(2026, 7, 31, 0, 0, tzinfo=ET), 1000, WH)
    assert cost is not None
    assert cost.tiers == ("First 800 kWh",)
    assert pricer.cycle_usage == Decimal(1)


def test_pricer_splits_15_minute_stream_across_tier() -> None:
    """A stream of reads crosses the 800 kWh tier mid-cycle and is split correctly."""
    pricer = UsagePricer(RATE_8, [_JULY])
    start = datetime(2026, 7, 1, tzinfo=ET)
    costs: list[UsageCost] = []
    for i in range(100):  # 100 x 9 kWh = 900 kWh; the 89th read crosses 800 kWh
        cost = pricer.price(start + timedelta(minutes=15 * i), 9000, WH)
        assert cost is not None
        costs.append(cost)
    assert costs[87].tiers == ("First 800 kWh",)
    assert costs[88].tiers == ("First 800 kWh", "Over 800 kWh")  # 792 -> 801 kWh
    assert costs[89].tiers == ("Over 800 kWh",)
    total = sum((c.amount for c in costs), Decimal(0))
    assert total == 800 * Decimal("0.15878") + 100 * Decimal("0.17442")


def test_pricer_observe_counts_without_pricing() -> None:
    """Observed usage moves later reads into higher tiers."""
    pricer = UsagePricer(RATE_8, [_JULY])
    pricer.observe(datetime(2026, 7, 2, tzinfo=ET), 850_000, WH)
    assert pricer.cycle_usage == Decimal(850)
    cost = pricer.price(datetime(2026, 7, 3, tzinfo=ET), 1000, WH)
    assert cost is not None
    assert cost.tiers == ("Over 800 kWh",)


def test_pricer_rejects_out_of_order_reads() -> None:
    """A read earlier than the previous one raises ValueError."""
    pricer = UsagePricer(RATE_8, [_JULY])
    pricer.price(datetime(2026, 7, 2, 12, tzinfo=ET), 100, WH)
    pricer.price(datetime(2026, 7, 2, 12, tzinfo=ET), 100, WH)  # same timestamp is fine
    with pytest.raises(ValueError, match="time order"):
        pricer.observe(datetime(2026, 7, 2, 11, tzinfo=ET), 100, WH)
    # Naive and aware timestamps compare in local time rather than raising TypeError.
    with pytest.raises(ValueError, match="time order"):
        pricer.price(datetime(2026, 7, 2, 11), 100, WH)
    pricer.price(datetime(2026, 7, 2, 17, tzinfo=UTC), 100, WH)  # 13:00 Eastern


@pytest.mark.parametrize(
    "stamps",
    [
        # Fall-back, stepping in real time: 01:45 EDT is followed by 01:00 EST.
        [datetime(2026, 11, 1, 5, 45, tzinfo=UTC), datetime(2026, 11, 1, 6, 0, tzinfo=UTC)],
        # Spring-forward as Green Button labels it: a nonexistent 02:45, then 03:00 EDT (an earlier instant).
        [datetime(2026, 3, 8, 2, 45, tzinfo=ET), datetime(2026, 3, 8, 3, 0, tzinfo=ET)],
        # Fall-back as Green Button labels it: the repeated hour appears twice with the same labels.
        [datetime(2026, 11, 1, 1, 45, tzinfo=ET), datetime(2026, 11, 1, 1, 0, fold=1, tzinfo=ET)],
    ],
    ids=["fall-back-utc", "spring-forward-wall-clock", "fall-back-wall-clock"],
)
def test_pricer_accepts_dst_transitions(stamps: list[datetime]) -> None:
    """Both labellings of the hours around a DST change are accepted as in order."""
    pricer = UsagePricer(RATE_8)
    for when in stamps:
        pricer.price(when, 100, WH)


def test_pricer_dates_outside_every_cycle_form_their_own_cycle() -> None:
    """Dates outside every cycle reset once and then accumulate together."""
    pricer = UsagePricer(RATE_8, [_JULY])
    pricer.price(datetime(2026, 7, 30, tzinfo=ET), 500_000, WH)
    pricer.price(datetime(2026, 8, 1, tzinfo=ET), 400_000, WH)  # outside: reset
    assert pricer.cycle_usage == Decimal(400)
    pricer.price(datetime(2026, 8, 2, tzinfo=ET), 500_000, WH)  # still outside: no reset
    assert pricer.cycle_usage == Decimal(900)


def test_pricer_without_cycles_never_resets() -> None:
    """With no cycles, usage accumulates indefinitely."""
    pricer = UsagePricer(RATE_8)
    pricer.price(datetime(2026, 7, 1, tzinfo=ET), 500_000, WH)
    pricer.price(datetime(2026, 9, 1, tzinfo=ET), 500_000, WH)
    assert pricer.cycle_usage == Decimal(1000)


def test_pricer_counts_usage_it_cannot_price() -> None:
    """Reads with no tariff period in effect still count toward the cycle."""
    pricer = UsagePricer(RATE_8)
    assert pricer.price(datetime(2025, 1, 1, tzinfo=ET), 1000, WH) is None
    assert pricer.cycle_usage == Decimal(1)


def test_pricer_gas_and_unit_checks() -> None:
    """Gas reads use the pricer's therm factor and reject electric units."""
    pricer = UsagePricer(RATE_32S, therms_per_ccf=Decimal(2))
    cost = pricer.price(datetime(2026, 9, 1, tzinfo=ET), 100, FT3)
    assert cost is not None
    assert cost.quantity == Decimal(2)
    with pytest.raises(ValueError, match="measured in"):
        pricer.price(datetime(2026, 9, 2, tzinfo=ET), 100, WH)


@pytest.mark.parametrize("plan", [RATE_8, RATE_5], ids=lambda p: p.code)
def test_pricer_nets_grid_and_solar_registers(plan: RatePlan) -> None:
    """Feeding grid and solar reads into one pricer gives the same total as pricing the netted hours."""
    start = datetime(2026, 7, 1, tzinfo=ET)
    hours = [start + timedelta(hours=h) for h in range(24 * 29)]  # stays inside _JULY
    grid = [(when, 1300.0 + 200 * (when.hour % 5)) for when in hours]  # ~1.3-2.1 kWh/hour, crosses 800 kWh
    solar = [(when, -1800.0 if 10 <= when.hour < 16 else 0.0) for when in hours]

    separate = UsagePricer(plan, [_JULY])
    separate_total = Decimal(0)
    for (when, used), (_, generated) in zip(grid, solar, strict=True):
        for quantity in (used, generated):
            cost = separate.price(when, quantity, WH)
            assert cost is not None
            separate_total += cost.amount

    netted = UsagePricer(plan, [_JULY])
    netted_total = Decimal(0)
    for (when, used), (_, generated) in zip(grid, solar, strict=True):
        cost = netted.price(when, used + generated, WH)
        assert cost is not None
        netted_total += cost.amount

    assert separate.cycle_usage == netted.cycle_usage
    assert separate_total == netted_total


@pytest.mark.parametrize("plan", [RATE_8, RATE_5], ids=lambda p: p.code)
def test_pricer_price_net_matches_pricing_the_net(plan: RatePlan) -> None:
    """price_net reports each side separately, and its nets match pricing the netted hours."""
    start = datetime(2026, 7, 1, tzinfo=ET)
    hours = [start + timedelta(hours=h) for h in range(24 * 29)]
    reads = [(when, 1300.0 + 200 * (when.hour % 5), -1800.0 if 10 <= when.hour < 16 else 0.0) for when in hours]

    paired = UsagePricer(plan, [_JULY])
    netted = UsagePricer(plan, [_JULY])
    for when, used, generated in reads:
        both = paired.price_net(when, used, generated, WH)
        net = netted.price(when, used + generated, WH)
        assert both is not None
        assert net is not None
        assert both.usage.amount >= 0 >= both.generation.amount
        assert both.amount == net.amount
    assert paired.cycle_usage == netted.cycle_usage


def test_pricer_price_net_counts_net_usage_it_cannot_price() -> None:
    """Net usage is counted even when no tariff period is in effect."""
    pricer = UsagePricer(RATE_8)
    assert pricer.price_net(datetime(2025, 1, 1, tzinfo=ET), 3000, 1000, WH) is None
    assert pricer.cycle_usage == Decimal(2)


def test_pricer_matches_price_usage_for_time_of_use() -> None:
    """For time-of-use plans the pricer gives the same result as price_usage."""
    pricer = UsagePricer(RATE_5, [_JULY])
    when = datetime(2026, 7, 15, 17, tzinfo=ET)
    assert pricer.price(when, 1000, WH) == price_usage(RATE_5, when, 1000, WH)


# --- equivalence with the integration's 0.3.0-era logic --------------------------


def _synthetic_reads(start: datetime, end: datetime, step: timedelta, scale: float, seed: int) -> list[tuple[datetime, float]]:
    """Return ``(local start, consumption)`` pairs stepping in UTC (so DST changes are covered) from *start*."""
    rng = random.Random(seed)  # noqa: S311 -- deterministic test data, not security
    reads: list[tuple[datetime, float]] = []
    moment = start.astimezone(UTC)
    while moment < end:
        reads.append((moment.astimezone(ET), round(rng.uniform(0, scale), 3)))
        moment += step
    return reads


_ANCHOR = BillingCycle(date(2026, 10, 15), date(2026, 11, 13))
_START = datetime(2025, 7, 1, tzinfo=ET)  # before every plan's earliest period
_END = datetime(2026, 11, 14, tzinfo=ET)


@pytest.mark.slow
@pytest.mark.parametrize(
    ("plan", "unit", "step", "scale"),
    [
        *((p, WH, timedelta(minutes=15), 2000.0) for p in RESIDENTIAL_ELECTRIC_RATE_PLANS.values()),
        *((p, FT3, timedelta(hours=1), 40.0) for p in RESIDENTIAL_GAS_RATE_PLANS.values()),
    ],
    ids=lambda v: getattr(v, "code", None) or "",
)
def test_usage_pricer_matches_legacy(plan: RatePlan, unit: MeterUnit, step: timedelta, scale: float) -> None:
    """``UsagePricer`` reproduces ha-dominion-sc's pricing for every catalog plan over more than a year."""
    # Sorted the way the integration sorts reads before pricing them.
    reads = sorted(_synthetic_reads(_START, _END, step, scale, seed=sum(map(ord, plan.code))), key=lambda r: r[0])
    cycles = estimate_billing_cycles(_ANCHOR, _START.date(), _END.date())

    expected = legacy.price_stream(reads, plan, [(c.start, c.end) for c in cycles])

    # The frozen legacy code converts gas at exactly 1 therm per CCF (ft³ / 100), so pin the factor to match it.
    pricer = UsagePricer(plan, cycles, therms_per_ccf=Decimal(1))
    actual: list[float] = []
    for when, consumption in reads:
        cost = pricer.price(when, consumption, unit)
        actual.append(0.0 if cost is None else float(cost.amount))

    assert len(actual) == len(expected)
    worst = max(abs(a - e) for a, e in zip(actual, expected, strict=True))
    assert worst < 1e-9
    assert abs(math.fsum(actual) - math.fsum(expected)) < 1e-9
    assert math.fsum(actual) > 0


# --- fixed_charges ----------------------------------------------------------------


def test_fixed_charges_electric_cycle() -> None:
    """Rate 8 from July 2026: the daily charge for every day, plus the $1.00 DER charge once."""
    cycle = BillingCycle(date(2026, 8, 1), date(2026, 8, 30))  # 30 days, both ends counted
    assert fixed_charges(RATE_8, cycle) == 30 * Decimal("0.36164") + Decimal("1.00")


def test_fixed_charges_der_is_once_per_cycle_not_per_day_or_length() -> None:
    """The monthly charge is the same for a 28-day and a 31-day cycle; only the daily charge scales."""
    short = fixed_charges(RATE_8, BillingCycle(date(2026, 8, 1), date(2026, 8, 28)))
    long = fixed_charges(RATE_8, BillingCycle(date(2026, 8, 1), date(2026, 8, 31)))
    assert long - short == 3 * Decimal("0.36164")


def test_fixed_charges_gas_is_flat_per_cycle() -> None:
    """The gas connection charge is $10.90 for any cycle length, whatever the usage."""
    assert fixed_charges(RATE_32S, BillingCycle(date(2026, 8, 1), date(2026, 8, 28))) == Decimal("10.90")
    assert fixed_charges(RATE_32S, BillingCycle(date(2026, 8, 1), date(2026, 8, 31))) == Decimal("10.90")


def test_fixed_charges_single_day_cycle() -> None:
    """A one-day cycle counts that day once."""
    day = date(2026, 8, 1)
    assert fixed_charges(RATE_8, BillingCycle(day, day)) == Decimal("0.36164") + Decimal("1.00")


def test_fixed_charges_cycle_spanning_a_tariff_change() -> None:
    """Each day uses the period in force that day; the monthly charge comes from the period at the cycle's end."""
    cycle = BillingCycle(date(2026, 6, 15), date(2026, 7, 14))
    old_days = 16  # June 15-30
    new_days = 14  # July 1-14
    expected = old_days * RATE_8_2025.charges[0].amount + new_days * Decimal("0.36164") + Decimal("1.00")  # type: ignore[union-attr]
    assert fixed_charges(RATE_8, cycle) == expected
    assert RATE_8_2025.charges[0].amount == Decimal("0.31233")  # type: ignore[union-attr]


def test_fixed_charges_days_before_the_first_period_cost_nothing() -> None:
    """Days before the earliest recorded tariff period aren't charged; a cycle wholly before it costs nothing."""
    assert fixed_charges(RATE_8, BillingCycle(date(2025, 1, 1), date(2025, 1, 30))) == 0
    straddle = BillingCycle(date(2025, 7, 13), date(2025, 8, 11))  # RATE_8_2025 starts 2025-07-23
    assert fixed_charges(RATE_8, straddle) == 20 * Decimal("0.31233") + Decimal("1.00")


def test_fixed_charges_exclude_demand_and_usage_charges() -> None:
    """Rate 7's demand charge and every usage charge stay out; only the daily and monthly charges count."""
    cycle = BillingCycle(date(2026, 8, 1), date(2026, 8, 30))
    assert fixed_charges(RATE_7, cycle) == 30 * Decimal("0.42740") + Decimal("1.00")


def test_fixed_charges_plan_without_fixed_charges_is_zero() -> None:
    """A plan with only usage charges has none."""
    plan = RatePlan("test_usage_only", "Usage only", Commodity.ELECTRICITY, date(2026, 1, 1), None, ())
    assert fixed_charges(plan, BillingCycle(date(2026, 8, 1), date(2026, 8, 30))) == 0


def test_fixed_charges_rejects_a_backwards_cycle() -> None:
    """A cycle that ends before it starts is an error, not zero days."""
    with pytest.raises(ValueError, match="before it starts"):
        fixed_charges(RATE_8, BillingCycle(date(2026, 8, 30), date(2026, 8, 1)))


def test_fixed_charges_all_catalog_plans_over_a_year_of_cycles() -> None:
    """Twelve estimated cycles cost about twelve DER charges plus a year of daily charges, to within a day or two."""
    cycles = estimate_billing_cycles(BillingCycle(date(2026, 10, 15), date(2026, 11, 13)), date(2025, 11, 14))
    year = [c for c in cycles if c.start >= date(2025, 11, 14)]
    total = sum((fixed_charges(RATE_8, c) for c in year), Decimal(0))
    days = (year[-1].end - year[0].start).days + 1
    assert total > days * Decimal("0.3") + len(year)  # lower bound: all at the cheaper 2025 daily rate
    assert total < days * Decimal("0.37") + len(year)  # upper bound: all at the 2026 daily rate
