"""Tests for ``rate_at`` and ``price_usage``.

The fixed-price cases are ported from ha-dominion-sc's ``tests/test_cost.py`` and
``tests/test_current_rate.py`` with their expected values unchanged. There, electric quantities were Wh and
gas quantities ft³, which is what ``price_usage`` takes too.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from dominionsc import (
    RATE_2,
    RATE_5,
    RATE_5_2025,
    RATE_6,
    RATE_6_2025,
    RATE_7,
    RATE_8,
    RATE_8_2025,
    RATE_32S,
    RATE_32S_2025,
    RATE_32V,
    Commodity,
    DailyCharge,
    FlatUsageCharge,
    MeterUnit,
    RatePlan,
    RateQuote,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
    UsageCost,
    UsageTier,
    UsageUnit,
    price_net_usage,
    price_usage,
    rate_at,
)

ET = ZoneInfo("America/New_York")
WH = MeterUnit.WATT_HOUR
FT3 = MeterUnit.CUBIC_FOOT


def _cost(plan: RatePlan, when: datetime, quantity: float, unit: MeterUnit = WH, before: float = 0) -> float:
    """``price_usage(...).amount`` as a float, or 0.0 when nothing is in effect (the integration's convention)."""
    result: UsageCost | None = price_usage(plan, when, quantity, unit, cycle_usage_before=before)
    return 0.0 if result is None else float(result.amount)


# --- tiered -------------------------------------------------------------------


def test_tiered_before_all_known_periods_is_none() -> None:
    """Before the earliest tariff period there is nothing to price."""
    assert price_usage(RATE_8, datetime(2025, 7, 1), 100, WH) is None
    assert rate_at(RATE_8, datetime(1990, 1, 1, tzinfo=ET), 0) is None


def test_tiered_after_effective() -> None:
    """Usage in the current period has a cost."""
    assert _cost(RATE_8, datetime(2026, 8, 1), 100) > 0


def test_tiered_all_over_boundary() -> None:
    """Usage entirely above 800 kWh is priced at the upper tier."""
    assert _cost(RATE_8, datetime(2026, 8, 1), 1000, before=900_000) == pytest.approx(1000 * 0.17442 / 1000, abs=1e-12)


def test_tiered_straddles_boundary() -> None:
    """An interval crossing 800 kWh is split between the two tiers."""
    result = price_usage(RATE_8, datetime(2026, 8, 1), 2000, WH, cycle_usage_before=799_000)
    assert result is not None
    assert result.amount == Decimal("0.15878") + Decimal("0.17442")
    assert result.tiers == ("First 800 kWh", "Over 800 kWh")
    assert result.quantity == Decimal(2)
    assert result.season is Season.SUMMER
    assert result.period is None
    assert result.plan is RATE_8


@pytest.mark.parametrize(
    ("when", "quantity", "before", "expected"),
    [
        (datetime(2025, 10, 1), 100, 0, 100 * 0.14599 / 1000),  # historical, winter, under boundary
        (datetime(2025, 8, 15), 100, 0, 100 * 0.14599 / 1000),  # historical, summer
        (datetime(2025, 10, 1), 1000, 900_000, 1000 * 0.14045 / 1000),  # historical, over boundary
        (datetime(2025, 10, 1), 2000, 799_000, 1000 * 0.14599 / 1000 + 1000 * 0.14045 / 1000),
        (datetime(2026, 7, 15), 100, 0, 100 * 0.15878 / 1000),  # current period
        (datetime(2026, 6, 30), 100, 0, 100 * 0.14599 / 1000),  # last day of the historical period
        (datetime(2026, 5, 15), 100, 0, 100 * 0.14599 / 1000),  # May is summer
        (datetime(2026, 9, 15), 100, 0, 100 * 0.15878 / 1000),  # September is summer
    ],
)
def test_rate_8_periods_and_seasons(when: datetime, quantity: float, before: float, expected: float) -> None:
    """Rate 8 prices each date with its tariff period and season."""
    assert _cost(RATE_8, when, quantity, before=before) == pytest.approx(expected, abs=1e-12)


def test_historical_rate_6_winter_under() -> None:
    """A 2025 Rate 6 date uses RATE_6_2025's price."""
    result = price_usage(RATE_6, datetime(2025, 11, 1), 100, WH)
    assert result is not None
    assert result.plan is RATE_6_2025
    assert float(result.amount) == pytest.approx(100 * 0.14164 / 1000, abs=1e-12)


@pytest.mark.parametrize("when", [datetime(2026, 8, 1), datetime(2026, 12, 1)])
def test_rate_6_straddle_is_sum_of_parts(when: datetime) -> None:
    """A split interval costs the same as its two halves priced separately."""
    whole = _cost(RATE_6, when, 2000, before=799_000)
    under = _cost(RATE_6, when, 1000)
    over = _cost(RATE_6, when, 1000, before=800_001)
    assert whole == pytest.approx(under + over, abs=1e-12)


def test_rate_6_winter_cheaper_than_summer_over_boundary() -> None:
    """Rate 6's winter upper tier is cheaper than summer's."""
    assert _cost(RATE_6, datetime(2026, 12, 1), 2000, before=799_000) < _cost(
        RATE_6, datetime(2026, 8, 1), 2000, before=799_000
    )


def test_interval_ending_exactly_on_boundary_stays_in_first_tier() -> None:
    """An interval ending exactly at 800 kWh stays in the first tier."""
    result = price_usage(RATE_8, datetime(2026, 8, 1), 1000, WH, cycle_usage_before=799_000)
    assert result is not None
    assert result.tiers == ("First 800 kWh",)
    assert result.amount == Decimal("0.15878")


def test_interval_starting_exactly_on_boundary_is_second_tier() -> None:
    """An interval starting exactly at 800 kWh is in the second tier."""
    result = price_usage(RATE_8, datetime(2026, 8, 1), 1000, WH, cycle_usage_before=800_000)
    assert result is not None
    assert result.tiers == ("Over 800 kWh",)


def test_zero_quantity_reports_current_tier() -> None:
    """A zero quantity costs nothing and reports the tier usage is in."""
    under = price_usage(RATE_8, datetime(2026, 8, 1), 0, WH, cycle_usage_before=10)
    over = price_usage(RATE_8, datetime(2026, 8, 1), 0, WH, cycle_usage_before=900_000)
    assert under is not None
    assert over is not None
    assert under.amount == over.amount == 0
    assert under.tiers == ("First 800 kWh",)
    assert over.tiers == ("Over 800 kWh",)


@pytest.mark.parametrize(
    ("plan", "when", "before"),
    [
        (RATE_8, datetime(2026, 8, 1, 14), 0),  # well inside the first tier
        (RATE_8, datetime(2026, 8, 1, 14), 797_000),  # usage crosses 800 kWh, the net doesn't
        (RATE_8, datetime(2026, 8, 1, 14), 803_000),  # export takes the total back under 800 kWh
        (RATE_8, datetime(2026, 1, 15, 14), 798_000),  # winter, superseded period
        (RATE_5, datetime(2026, 7, 15, 17, tzinfo=ET), 0),  # on-peak
        (RATE_5, datetime(2026, 7, 15, 2, tzinfo=ET), 0),  # super-off-peak
        (RATE_2, datetime(2026, 8, 1, 14), 0),
    ],
)
def test_generation_offsets_usage_at_the_same_rate(plan: RatePlan, when: datetime, before: int) -> None:
    """10 kWh used and 5 kWh generated in one hour costs the same as 5 kWh net, whichever way it is priced."""
    used = price_usage(plan, when, 10_000, WH, cycle_usage_before=before)
    generated = price_usage(plan, when, -5_000, WH, cycle_usage_before=before + 10_000)
    net = price_usage(plan, when, 5_000, WH, cycle_usage_before=before)
    assert used is not None
    assert generated is not None
    assert net is not None
    assert generated.amount < 0
    assert used.amount + generated.amount == net.amount


def test_price_net_usage_returns_each_side_and_the_net() -> None:
    """10 kWh used and 5 kWh generated: each side is priced on its own and the net is 5 kWh's cost."""
    when = datetime(2026, 8, 1, 14)
    result = price_net_usage(RATE_8, when, 10_000, 5_000, WH)
    assert result is not None
    assert result.usage.amount == 10 * Decimal("0.15878")
    assert result.usage.quantity == Decimal(10)
    assert result.generation.amount == -5 * Decimal("0.15878")
    assert result.generation.quantity == Decimal(-5)
    assert result.amount == 5 * Decimal("0.15878")
    assert result.quantity == Decimal(5)
    assert result.amount == price_usage(RATE_8, when, 5_000, WH).amount  # type: ignore[union-attr]


def test_price_net_usage_across_tier_boundary() -> None:
    """Generation offsets the highest-tier usage first; the net still equals pricing the net quantity."""
    when = datetime(2026, 8, 1, 14)
    result = price_net_usage(RATE_8, when, 10_000, 5_000, WH, cycle_usage_before=797_000)
    assert result is not None
    assert result.usage.tiers == ("First 800 kWh", "Over 800 kWh")
    assert result.generation.tiers == ("Over 800 kWh",)
    assert result.generation.amount == -5 * Decimal("0.17442")
    net = price_usage(RATE_8, when, 5_000, WH, cycle_usage_before=797_000)
    assert net is not None
    assert result.amount == net.amount


def test_price_net_usage_accepts_negative_generation() -> None:
    """A solar-export register's negative read can be passed as is."""
    when = datetime(2026, 7, 15, 17, tzinfo=ET)
    assert price_net_usage(RATE_5, when, 2_000, -3_000, WH) == price_net_usage(RATE_5, when, 2_000, 3_000, WH)


def test_price_net_usage_net_export_is_a_credit() -> None:
    """Generating more than is used in the hour gives a net credit at that hour's rate."""
    result = price_net_usage(RATE_5, datetime(2026, 7, 15, 17, tzinfo=ET), 1_000, 4_000, WH)
    assert result is not None
    assert result.usage.amount == Decimal("0.29907")
    assert result.amount == -3 * Decimal("0.29907")
    assert result.usage.period == result.generation.period == "on_peak"


def test_price_net_usage_without_period_is_none() -> None:
    """Nothing is priced before the earliest tariff period."""
    assert price_net_usage(RATE_8, datetime(2025, 1, 1), 1_000, 500, WH) is None


def test_net_export_is_a_credit() -> None:
    """An hour that generates more than it uses is credited at that hour's rate."""
    when = datetime(2026, 7, 15, 17, tzinfo=ET)  # Rate 5 on-peak: 0.29907
    result = price_usage(RATE_5, when, -3_000, WH)
    assert result is not None
    assert result.amount == Decimal("-0.89721")


def test_negative_quantity_reverses_the_tier_split() -> None:
    """A negative quantity is the exact reverse of the positive one that would have led here."""
    forward = price_usage(RATE_8, datetime(2026, 8, 1), 2000, WH, cycle_usage_before=799_000)
    backward = price_usage(RATE_8, datetime(2026, 8, 1), -2000, WH, cycle_usage_before=801_000)
    assert forward is not None
    assert backward is not None
    assert backward.amount == -forward.amount
    assert backward.tiers == forward.tiers
    assert backward.quantity == Decimal(-2)


_THREE_TIERS = RatePlan(
    code="test_three_tiers",
    name="Three tiers",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 1, 1),
    effective_to=None,
    charges=(
        TieredUsageCharge(
            name="Energy",
            tiers_by_season={
                season: (
                    UsageTier("First 100", Decimal(100), Decimal("0.10")),
                    UsageTier("Next 100", Decimal(200), Decimal("0.20")),
                    UsageTier("Over 200", None, Decimal("0.30")),
                )
                for season in Season
            },
        ),
    ),
)


def test_three_tiers_crossing_two_boundaries_in_one_interval() -> None:
    """One interval can cross two tier boundaries."""
    # 50 kWh used; 300 kWh more: 50 @ 0.10 + 100 @ 0.20 + 150 @ 0.30.
    result = price_usage(_THREE_TIERS, datetime(2026, 3, 1), 300_000, WH, cycle_usage_before=50_000)
    assert result is not None
    assert result.amount == Decimal("5") + Decimal("20") + Decimal("45")
    assert result.tiers == ("First 100", "Next 100", "Over 200")


def test_usage_already_above_last_bound() -> None:
    """Usage already in the last tier stays there."""
    result = price_usage(_THREE_TIERS, datetime(2026, 3, 1), 1000, WH, cycle_usage_before=500_000)
    assert result is not None
    assert result.amount == Decimal("0.30")
    assert result.tiers == ("Over 200",)


def test_bounded_last_tier_takes_the_remainder() -> None:
    """A bounded last tier takes usage beyond its bound; a missing season prices nothing."""
    plan = RatePlan(
        code="test_bounded_last",
        name="Bounded last tier",
        commodity=Commodity.ELECTRICITY,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        charges=(
            TieredUsageCharge(
                tiers_by_season={
                    Season.WINTER: (
                        UsageTier("First 100", Decimal(100), Decimal("0.10")),
                        UsageTier("Up to 200", Decimal(200), Decimal("0.20")),
                    )
                }
            ),
        ),
    )
    result = price_usage(plan, datetime(2026, 1, 15), 300_000, WH)
    assert result is not None
    assert result.amount == Decimal("10") + Decimal("40")
    quote = rate_at(plan, datetime(2026, 1, 15), 500)
    assert quote is not None
    assert quote.tier == "Up to 200"
    # No tiers for summer: nothing to price.
    assert price_usage(plan, datetime(2026, 7, 15), 1000, WH) is None
    assert rate_at(plan, datetime(2026, 7, 15)) is None


@pytest.mark.parametrize(
    ("when", "season"),
    [
        (datetime(2026, 5, 1, 3, 59, tzinfo=UTC), Season.WINTER),  # 2026-04-30 23:59 Eastern
        (datetime(2026, 5, 1, 4, 0, tzinfo=UTC), Season.SUMMER),  # 2026-05-01 00:00 Eastern
        (datetime(2026, 10, 1, 3, 59, tzinfo=UTC), Season.SUMMER),  # 2026-09-30 23:59 Eastern
        (datetime(2026, 10, 1, 4, 0, tzinfo=UTC), Season.WINTER),
    ],
)
def test_season_uses_local_date(when: datetime, season: Season) -> None:
    """Season boundaries follow the Eastern-time date, not the UTC date."""
    result = price_usage(RATE_8, when, 1000, WH, cycle_usage_before=900_000)
    assert result is not None
    assert result.season is season


# --- time of use ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("when", "period", "price"),
    [
        (datetime(2026, 7, 15, 17, 0, tzinfo=ET), "on_peak", "0.29907"),
        (datetime(2026, 7, 15, 2, 0, tzinfo=ET), "super_off_peak", "0.09623"),
        (datetime(2026, 7, 15, 12, 0, tzinfo=ET), "off_peak", "0.15074"),
        (datetime(2026, 12, 15, 7, 0, tzinfo=ET), "on_peak", "0.29907"),
        (datetime(2026, 12, 15, 13, 0, tzinfo=ET), "super_off_peak", "0.09623"),
    ],
)
def test_rate_5_current_periods(when: datetime, period: str, price: str) -> None:
    """Current Rate 5 periods and prices."""
    result = price_usage(RATE_5, when, 1000, WH)
    assert result is not None
    assert result.amount == Decimal(price)
    assert result.period == period
    assert result.tiers == ()


@pytest.mark.parametrize(
    ("when", "price"),
    [
        (datetime(2025, 7, 19, 17, 0, tzinfo=ET), "0.13701"),  # Saturday: off-peak
        (datetime(2025, 9, 1, 17, 0, tzinfo=ET), "0.13701"),  # Labor Day: off-peak
        (datetime(2025, 12, 25, 7, 0, tzinfo=ET), "0.13701"),  # Christmas: off-peak
        (datetime(2025, 7, 21, 17, 0, tzinfo=ET), "0.26900"),  # Monday: on-peak
        (datetime(2026, 1, 15, 13, 0, tzinfo=ET), "0.13701"),  # no winter midday window
    ],
)
def test_rate_5_superseded_day_rules(when: datetime, price: str) -> None:
    """Superseded Rate 5 periods follow their weekday, holiday and window rules."""
    result = price_usage(RATE_5, when, 1000, WH)
    assert result is not None
    assert result.plan is RATE_5_2025
    assert result.amount == Decimal(price)


def test_rate_5_tariff_period_chosen_by_local_date() -> None:
    """02:00 UTC on 2026-07-01 is still 2026-06-30 in Eastern time, under the 2025 tariff."""
    quote = rate_at(RATE_5, datetime(2026, 7, 1, 2, 0, tzinfo=UTC))
    assert quote is not None
    assert quote.plan is RATE_5_2025
    assert quote.period == "off_peak"
    assert quote.price_per_unit == Decimal("0.13701")


def _tou_plan(periods: tuple[TimeOfUsePeriod, ...]) -> RatePlan:
    return RatePlan(
        code="test_tou",
        name="Test TOU",
        commodity=Commodity.ELECTRICITY,
        effective_from=date(2026, 7, 1),
        effective_to=None,
        charges=(TimeOfUseCharge(name="Energy", periods_by_season={Season.SUMMER: periods, Season.WINTER: ()}),),
    )


def test_tou_midnight_crossing_window() -> None:
    """A window crossing midnight matches late-evening intervals."""
    plan = _tou_plan(
        (
            TimeOfUsePeriod("late_night", Decimal("0.10"), (TimeWindow(time(22), time(6)),)),
            TimeOfUsePeriod("day", Decimal("0.20"), fallback=True),
        )
    )
    assert _cost(plan, datetime(2026, 7, 15, 23, 0, tzinfo=ET), 1000) == pytest.approx(0.10)


def test_tou_without_fallback_is_none() -> None:
    """A time-of-use plan with no matching or fallback period cannot price the moment."""
    plan = _tou_plan((TimeOfUsePeriod("late", Decimal("0.10"), (TimeWindow(time(22), time(23)),)),))
    hit = rate_at(plan, datetime(2026, 7, 15, 22, 30, tzinfo=ET))
    assert hit is not None
    assert hit.period == "late"
    assert rate_at(plan, datetime(2026, 7, 15, 12, 0, tzinfo=ET)) is None
    assert price_usage(plan, datetime(2026, 7, 15, 12, 0, tzinfo=ET), 1000, WH) is None
    assert rate_at(plan, datetime(2026, 6, 1, tzinfo=ET)) is None  # before effective_from


def test_rate_7_demand_is_unpriced() -> None:
    """Rate 7's demand charge is named in unpriced_charges and left out of the amount."""
    when = datetime(2026, 7, 15, 17, 0, tzinfo=ET)
    result = price_usage(RATE_7, when, 1000, WH)
    assert result is not None
    assert result.unpriced_charges == ("On-Peak Billing Demand",)
    assert result.amount == Decimal("0.17441")  # energy only
    quote = rate_at(RATE_7, when)
    assert quote is not None
    assert quote.unpriced_charges == ("On-Peak Billing Demand",)
    assert price_usage(RATE_5, when, 1000, WH).unpriced_charges == ()  # type: ignore[union-attr]


# --- flat -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("plan", "quantity", "unit", "expected"),
    [
        (RATE_2, 1000, WH, "0.13111"),
        (RATE_2, 500, WH, "0.065555"),
        (RATE_32S, 100.0, FT3, "2.04149"),
        (RATE_32V, 100.0, FT3, "1.91847"),
    ],
)
def test_flat(plan: RatePlan, quantity: float, unit: MeterUnit, expected: str) -> None:
    """Flat electric and gas plans multiply the converted quantity by the price.

    The expected gas values are the integration's, which converts at exactly 1 therm per CCF, so the factor is
    pinned to 1 here. The library's default factor is tested separately.
    """
    result = price_usage(plan, datetime(2026, 9, 1), quantity, unit, therms_per_ccf=Decimal(1))
    assert result is not None
    assert result.amount == Decimal(expected)
    assert result.season is None
    assert result.period is None
    assert result.tiers == ()


def test_flat_before_effective_is_none() -> None:
    """Flat plans before their earliest period price nothing."""
    assert price_usage(RATE_2, datetime(2025, 6, 1), 500, WH) is None
    assert price_usage(RATE_32S, datetime(2025, 8, 31), 100, FT3) is None


@pytest.mark.parametrize(
    ("when", "expected", "plan"),
    [
        (datetime(2025, 9, 1), "1.81026", RATE_32S_2025),
        (datetime(2026, 6, 30), "1.81026", RATE_32S_2025),
        (datetime(2026, 7, 1), "2.04149", RATE_32S),
    ],
)
def test_gas_uses_period_for_date(when: datetime, expected: str, plan: RatePlan) -> None:
    """Each Rate 32S period prices the dates inside it."""
    result = price_usage(RATE_32S, when, 100, FT3, therms_per_ccf=Decimal(1))  # the integration's factor
    assert result is not None
    assert result.amount == Decimal(expected)
    assert result.plan is plan


def test_gas_default_therm_factor() -> None:
    """Gas is priced at the default 1.036 therms per CCF unless told otherwise."""
    default = price_usage(RATE_32S, datetime(2026, 9, 1), 100, FT3)
    explicit = price_usage(RATE_32S, datetime(2026, 9, 1), 100, FT3, therms_per_ccf=Decimal("1.036"))
    assert default is not None
    assert default == explicit
    assert default.quantity == Decimal("1.036")
    assert default.amount == Decimal("1.036") * Decimal("2.04149")


def test_gas_therm_factor() -> None:
    """A custom therm factor changes the billed quantity."""
    result = price_usage(RATE_32S, datetime(2026, 9, 1), 100, FT3, therms_per_ccf=Decimal("1.05"))
    assert result is not None
    assert result.quantity == Decimal("1.05")
    assert result.amount == Decimal("1.05") * Decimal("2.04149")


def test_unit_mismatch_raises() -> None:
    """A meter unit that doesn't match the plan's commodity raises ValueError."""
    with pytest.raises(ValueError, match="measured in"):
        price_usage(RATE_8, datetime(2026, 9, 1), 100, FT3)
    with pytest.raises(ValueError, match="measured in"):
        price_usage(RATE_32S, datetime(2020, 1, 1), 100, WH)  # checked even when no period is in effect


# --- plan shape ---------------------------------------------------------------


def test_plan_without_usage_charge_costs_zero() -> None:
    """A plan with only fixed charges prices usage at zero."""
    plan = RatePlan(
        code="test_no_usage_charge",
        name="No usage charge",
        commodity=Commodity.ELECTRICITY,
        effective_from=date(2026, 7, 1),
        effective_to=None,
        charges=(DailyCharge(name="Facilities", amount=Decimal("0.36164")),),
    )
    cost = price_usage(plan, datetime(2026, 8, 1), 1000, WH)
    assert cost is not None
    assert cost.amount == 0
    assert cost.quantity == Decimal(1)
    assert cost.plan is plan
    quote = rate_at(plan, datetime(2026, 8, 1))
    assert quote is not None
    assert quote.price_per_unit == 0
    assert quote.usage_unit is UsageUnit.KWH
    # Still nothing to price before the plan takes effect.
    assert price_usage(plan, datetime(2026, 6, 1), 1000, WH) is None


def test_gas_plan_without_usage_charge_quotes_therms() -> None:
    """A gas plan with no usage charge quotes zero per therm."""
    plan = RatePlan("test_gas_fixed", "Gas fixed", Commodity.GAS, date(2026, 7, 1), None, ())
    quote = rate_at(plan, datetime(2026, 8, 1))
    assert quote is not None
    assert quote.usage_unit is UsageUnit.THERM


def test_plan_with_two_usage_charges_raises() -> None:
    """Plans with two usage charges are rejected rather than half-priced."""
    plan = RatePlan(
        code="test_two_usage_charges",
        name="Two usage charges",
        commodity=Commodity.ELECTRICITY,
        effective_from=date(2026, 7, 1),
        effective_to=None,
        charges=(FlatUsageCharge(price_per_unit=Decimal("0.1")), FlatUsageCharge(price_per_unit=Decimal("0.2"))),
    )
    with pytest.raises(ValueError, match="2 usage charges"):
        price_usage(plan, datetime(2026, 8, 1), 1000, WH)
    with pytest.raises(ValueError, match="2 usage charges"):
        rate_at(plan, datetime(2026, 8, 1))


# --- rate_at --------------------------------------------------------------------

_SUMMER_NOON = datetime(2026, 7, 15, 12, 0, tzinfo=ET)
_WINTER_NIGHT = datetime(2026, 1, 15, 2, 0, tzinfo=ET)


@pytest.mark.parametrize(
    ("when", "usage", "tier", "price"),
    [
        (_SUMMER_NOON, 10.0, "First 800 kWh", "0.15878"),
        (_SUMMER_NOON, 799.9, "First 800 kWh", "0.15878"),
        (_SUMMER_NOON, 800.0, "Over 800 kWh", "0.17442"),
        (datetime(2026, 12, 15, 2, 0, tzinfo=ET), 5000.0, "Over 800 kWh", "0.15253"),
        (_WINTER_NIGHT, Decimal(5000), "Over 800 kWh", "0.14045"),  # superseded period
    ],
)
def test_rate_at_tiered(when: datetime, usage: float, tier: str, price: str) -> None:
    """rate_at picks the tier from cycle-to-date usage."""
    quote = rate_at(RATE_8, when, usage)
    assert quote is not None
    assert quote.tier == tier
    assert quote.price_per_unit == Decimal(price)
    assert quote.usage_unit is UsageUnit.KWH
    assert quote.period is None


def test_rate_at_tiered_unknown_usage_is_first_tier() -> None:
    """Unknown cycle usage reports the first tier."""
    quote = rate_at(RATE_8, _SUMMER_NOON)
    assert quote == rate_at(RATE_8, _SUMMER_NOON, 0)
    assert quote is not None
    assert quote.tier == "First 800 kWh"
    assert quote.tier_upper_bound == Decimal(800)
    assert quote.season is Season.SUMMER
    assert quote.plan is RATE_8


def test_rate_at_open_tier_has_no_bound() -> None:
    """The open-ended tier reports no upper bound."""
    quote = rate_at(RATE_8_2025, _WINTER_NIGHT, 900)
    assert quote is not None
    assert quote.tier_upper_bound is None


@pytest.mark.parametrize(
    ("when", "period"),
    [
        (datetime(2026, 7, 15, 16, 0, tzinfo=ET), "on_peak"),
        (datetime(2026, 7, 15, 19, 59, tzinfo=ET), "on_peak"),
        (datetime(2026, 7, 15, 20, 0, tzinfo=ET), "off_peak"),
        (datetime(2026, 7, 15, 2, 0, tzinfo=ET), "super_off_peak"),
        (datetime(2026, 1, 15, 7, 0, tzinfo=ET), "on_peak"),
        (datetime(2026, 12, 15, 13, 0, tzinfo=ET), "super_off_peak"),
        (datetime(2026, 1, 15, 13, 0, tzinfo=ET), "off_peak"),
        (datetime(2026, 7, 18, 17, 0, tzinfo=ET), "on_peak"),
        (datetime(2025, 7, 19, 17, 0, tzinfo=ET), "off_peak"),
        (datetime(2025, 9, 1, 17, 0, tzinfo=ET), "off_peak"),
        (datetime(2025, 7, 21, 17, 0, tzinfo=ET), "on_peak"),
        (datetime(2026, 7, 15, 21, 0, tzinfo=UTC), "on_peak"),
    ],
)
def test_rate_at_time_of_use(when: datetime, period: str) -> None:
    """rate_at reports the time-of-use period in force."""
    quote = rate_at(RATE_5, when, 12345)  # cycle usage is ignored for time-of-use plans
    assert quote is not None
    assert quote.period == period
    assert quote.tier is None
    assert quote.season is not None


def test_rate_at_flat() -> None:
    """Flat electric and gas plans quote their single price."""
    electric = rate_at(RATE_2, _WINTER_NIGHT)
    gas = rate_at(RATE_32S, _WINTER_NIGHT)
    assert electric is not None
    assert gas is not None
    assert electric.price_per_unit > 0
    assert gas.usage_unit is UsageUnit.THERM
    assert gas.season is None
    assert isinstance(gas, RateQuote)
