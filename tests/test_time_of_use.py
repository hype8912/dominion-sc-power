"""Tests for the time-of-use rate lookup."""

from collections import Counter
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from itertools import product
from types import MappingProxyType
from zoneinfo import ZoneInfo

import pytest

from dominionsc import (
    RATE_1,
    RATE_5,
    RATE_5_2024,
    RATE_5_2025,
    RATE_7,
    RATE_7_2025,
    RATE_32V,
    RatePlan,
    Season,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeOfUseRate,
    TimeWindow,
    get_time_of_use_rate,
    season_for,
)


def test_season_for() -> None:
    """Summer is May-September; winter is October-April."""
    assert season_for(date(2026, 4, 30)) is Season.WINTER
    assert season_for(date(2026, 5, 1)) is Season.SUMMER
    assert season_for(date(2026, 9, 30)) is Season.SUMMER
    assert season_for(date(2026, 10, 1)) is Season.WINTER


@pytest.mark.parametrize(
    ("when", "period", "price"),
    [
        (datetime(2025, 7, 15, 17), "on_peak", "0.26900"),  # summer weekday 5 PM
        (datetime(2025, 7, 15, 20), "off_peak", "0.13701"),  # 8 PM is outside [4, 8)
        (datetime(2025, 7, 15, 3), "super_off_peak", "0.09064"),
        (datetime(2025, 7, 19, 17), "off_peak", "0.13701"),  # Saturday
        (datetime(2025, 7, 4, 17), "off_peak", "0.13701"),  # Independence Day (Friday)
        (datetime(2025, 9, 1, 17), "off_peak", "0.13701"),  # Labor Day
        (datetime(2025, 11, 27, 7), "off_peak", "0.13701"),  # Thanksgiving, winter on-peak hour
        (datetime(2025, 11, 28, 7), "on_peak", "0.26900"),  # day after Thanksgiving
        (datetime(2025, 12, 10, 13), "off_peak", "0.13701"),  # no winter midday window in 2025
    ],
)
def test_rate_5_2025(when: datetime, period: str, price: str) -> None:
    """The 2025 tariff limits on-peak to weekdays excluding holidays and has no winter midday window."""
    rate = get_time_of_use_rate(RATE_5_2025, when)
    assert rate.period == period
    assert rate.price_per_kwh == Decimal(price)


def test_rate_5_2024_holiday() -> None:
    """The 2024 tariff treats Thanksgiving as off-peak."""
    assert get_time_of_use_rate(RATE_5_2024, datetime(2024, 11, 28, 7)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5_2024, datetime(2024, 11, 29, 7)).period == "on_peak"


def test_current_rate_5_applies_every_day() -> None:
    """The July 2026 tariff has on-peak every day and a winter midday super-off-peak."""
    saturday = get_time_of_use_rate(RATE_5, datetime(2026, 7, 18, 17))
    assert (saturday.period, saturday.price_per_kwh) == ("on_peak", Decimal("0.29907"))
    assert get_time_of_use_rate(RATE_5, datetime(2026, 11, 26, 7)).period == "on_peak"  # Thanksgiving
    midday = get_time_of_use_rate(RATE_5, datetime(2026, 12, 10, 13))
    assert (midday.period, midday.season) == ("super_off_peak", Season.WINTER)
    assert get_time_of_use_rate(RATE_5, datetime(2026, 7, 18, 13)).period == "off_peak"  # summer


def test_rate_7_lookup() -> None:
    """Rate 7 prices follow the same rules as Rate 5."""
    assert get_time_of_use_rate(RATE_7, datetime(2026, 8, 1, 16)).price_per_kwh == Decimal("0.17441")
    assert get_time_of_use_rate(RATE_7_2025, datetime(2026, 1, 3, 7)).period == "off_peak"  # Saturday


def test_window_boundaries_are_half_open() -> None:
    """A window includes its start and excludes its end."""
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 15, 45)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 16, 0)).period == "on_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 19, 45)).period == "on_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 20, 0)).period == "off_peak"


def test_aware_datetime_is_converted_to_local_time() -> None:
    """Aware datetimes are converted to America/New_York."""
    utc = datetime(2026, 8, 3, 20, 0, tzinfo=ZoneInfo("UTC"))  # 4 PM EDT
    assert get_time_of_use_rate(RATE_5, utc).period == "on_peak"


def test_rejects_plan_without_time_of_use_charge() -> None:
    """Plans with no time-of-use charge raise ValueError."""
    with pytest.raises(ValueError, match="no time-of-use charge"):
        get_time_of_use_rate(RATE_1, datetime(2026, 8, 3, 17))


def test_rejects_date_outside_plan_period() -> None:
    """Dates outside the plan's effective dates raise ValueError."""
    with pytest.raises(ValueError, match="outside"):
        get_time_of_use_rate(RATE_5, datetime(2026, 6, 30, 17))
    with pytest.raises(ValueError, match="outside"):
        get_time_of_use_rate(RATE_5_2025, datetime(2026, 7, 1, 17))


@pytest.mark.parametrize(
    "when",
    [
        datetime(2026, 1, 1, 7),  # New Year's Day
        datetime(2025, 5, 26, 17),  # Memorial Day
        datetime(2025, 12, 25, 7),  # Christmas Day
    ],
)
def test_remaining_holidays_are_off_peak_in_2025_plan(when: datetime) -> None:
    """Every holiday named in the 2025 tariff drops on-peak pricing."""
    assert get_time_of_use_rate(RATE_5_2025, when).period == "off_peak"


def test_rate_5_2025_midnight_and_super_off_peak_edges() -> None:
    """Super-off-peak covers 1:00-4:59 AM; 5:00 AM falls back to off-peak."""
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 7, 15, 0, 59)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 7, 15, 1, 0)).period == "super_off_peak"
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 7, 15, 4, 59)).period == "super_off_peak"
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 7, 15, 5, 0)).period == "off_peak"


def test_season_boundaries_change_on_peak_hours() -> None:
    """April uses the winter 6-9 AM window; May uses the summer 4-8 PM window."""
    assert get_time_of_use_rate(RATE_5, datetime(2027, 4, 30, 7)).period == "on_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2027, 4, 30, 17)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2027, 5, 3, 7)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2027, 5, 3, 17)).period == "on_peak"


def test_returns_time_of_use_rate_value() -> None:
    """The result is a TimeOfUseRate carrying the season it was priced in."""
    rate = get_time_of_use_rate(RATE_7, datetime(2026, 12, 10, 7))
    assert rate == TimeOfUseRate("on_peak", Decimal("0.17441"), Season.WINTER)


def test_week_of_intervals_splits_into_expected_hours() -> None:
    """Each 15-minute interval in a week is priced, and each period gets the hours the tariff gives it."""
    counts: Counter[str] = Counter()
    for day, hour, minute in product(range(7, 14), range(24), (0, 15, 30, 45)):  # Mon Dec 7 - Sun Dec 13, 2026
        counts[get_time_of_use_rate(RATE_5, datetime(2026, 12, day, hour, minute)).period] += 1
    # Winter 2026: on-peak 6-9 AM and super-off-peak 1-5 AM + 12-3 PM, every day.
    assert counts == {"on_peak": 7 * 3 * 4, "super_off_peak": 7 * 7 * 4, "off_peak": 7 * 14 * 4}


def test_2025_week_excludes_weekends_and_thanksgiving() -> None:
    """Thanksgiving week 2025 has on-peak only on Mon, Tue, Wed, and Fri."""
    counts: Counter[str] = Counter()
    for day, hour, minute in product(range(24, 31), range(24), (0, 15, 30, 45)):  # Mon Nov 24 - Sun Nov 30, 2025
        counts[get_time_of_use_rate(RATE_5_2025, datetime(2025, 11, day, hour, minute)).period] += 1
    assert counts == {"on_peak": 4 * 3 * 4, "super_off_peak": 7 * 4 * 4, "off_peak": 7 * 96 - 4 * 3 * 4 - 7 * 4 * 4}


def test_rejects_gas_plan() -> None:
    """Gas plans have no time-of-use charge."""
    with pytest.raises(ValueError, match="no time-of-use charge"):
        get_time_of_use_rate(RATE_32V, datetime(2026, 8, 3, 17))


def _plan_with_periods(periods_by_season: dict[Season, tuple[TimeOfUsePeriod, ...]]) -> RatePlan:
    """Build a minimal time-of-use plan for exercising edge cases."""
    return replace(
        RATE_5,
        charges=(TimeOfUseCharge(name="Energy", periods_by_season=MappingProxyType(periods_by_season)),),
    )


def test_window_crossing_midnight() -> None:
    """A window whose end is before its start wraps past midnight."""
    overnight = (
        TimeOfUsePeriod("night", Decimal("0.05"), (TimeWindow(time(22), time(2)),)),
        TimeOfUsePeriod("day", Decimal("0.10"), fallback=True),
    )
    plan = _plan_with_periods({Season.SUMMER: overnight, Season.WINTER: overnight})
    assert get_time_of_use_rate(plan, datetime(2026, 8, 3, 21, 45)).period == "day"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 3, 22, 0)).period == "night"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 3, 23, 45)).period == "night"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 4, 0, 0)).period == "night"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 4, 1, 45)).period == "night"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 4, 2, 0)).period == "day"


def test_window_ending_at_midnight() -> None:
    """``time(0)`` as an end means midnight, so 10 PM to midnight is matched."""
    late = (
        TimeOfUsePeriod("late", Decimal("0.05"), (TimeWindow(time(22), time(0)),)),
        TimeOfUsePeriod("rest", Decimal("0.10"), fallback=True),
    )
    plan = _plan_with_periods({Season.SUMMER: late, Season.WINTER: late})
    assert get_time_of_use_rate(plan, datetime(2026, 8, 3, 23, 45)).period == "late"
    assert get_time_of_use_rate(plan, datetime(2026, 8, 4, 0, 0)).period == "rest"


def test_rejects_plan_missing_season() -> None:
    """A plan with no periods for the season raises ValueError, not KeyError."""
    periods = (TimeOfUsePeriod("all", Decimal("0.10"), fallback=True),)
    plan = _plan_with_periods({Season.WINTER: periods})
    with pytest.raises(ValueError, match="no time-of-use periods for summer"):
        get_time_of_use_rate(plan, datetime(2026, 8, 3, 12))


def test_rejects_plan_without_fallback() -> None:
    """An unmatched interval in a plan with no fallback raises ValueError, not StopIteration."""
    periods = (TimeOfUsePeriod("peak", Decimal("0.30"), (TimeWindow(time(16), time(20)),)),)
    plan = _plan_with_periods({Season.SUMMER: periods, Season.WINTER: periods})
    assert get_time_of_use_rate(plan, datetime(2026, 8, 3, 17)).period == "peak"
    with pytest.raises(ValueError, match="no fallback"):
        get_time_of_use_rate(plan, datetime(2026, 8, 3, 12))
