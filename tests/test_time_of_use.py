"""Tests for the time-of-use rate lookup."""

from collections import Counter
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
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


UTC = ZoneInfo("UTC")


def test_aware_winter_datetime_uses_standard_time_offset() -> None:
    """In winter the local offset is UTC-5 (EST), not the summer UTC-4."""
    assert get_time_of_use_rate(RATE_5, datetime(2026, 12, 10, 11, 0, tzinfo=UTC)).period == "on_peak"  # 6:00 AM EST
    assert get_time_of_use_rate(RATE_5, datetime(2026, 12, 10, 10, 30, tzinfo=UTC)).period == "off_peak"  # 5:30 AM EST


def test_plan_effective_dates_use_local_date() -> None:
    """2026-07-01 03:00 UTC is June 30 at 11 PM locally, so it belongs to the 2025 plan, not the July 2026 one."""
    instant = datetime(2026, 7, 1, 3, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="2026-06-30 is outside"):
        get_time_of_use_rate(RATE_5, instant)
    assert get_time_of_use_rate(RATE_5_2025, instant).period == "off_peak"


def test_holiday_uses_local_date() -> None:
    """Thanksgiving 2025 at 12:00 UTC is 7 AM EST on Thanksgiving, so on-peak does not apply."""
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 11, 27, 12, 0, tzinfo=UTC)).period == "off_peak"
    assert get_time_of_use_rate(RATE_5_2025, datetime(2025, 11, 28, 12, 0, tzinfo=UTC)).period == "on_peak"


def test_effective_dates_are_inclusive_at_plan_handover() -> None:
    """The last moment of the 2025 plan and the first of the July 2026 plan are both accepted."""
    assert get_time_of_use_rate(RATE_5_2025, datetime(2026, 6, 30, 23, 59, 59)).price_per_kwh == Decimal("0.13701")
    assert get_time_of_use_rate(RATE_5, datetime(2026, 7, 1, 0, 0)).price_per_kwh == Decimal("0.15074")


def test_repeated_hour_at_fall_back() -> None:
    """Both 1:30 AM instants on 2026-11-01 (EDT, then EST) are super-off-peak."""
    first = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 1:30 AM EDT
    second = datetime(2026, 11, 1, 6, 30, tzinfo=UTC)  # 1:30 AM EST, one hour later
    assert get_time_of_use_rate(RATE_5, first).period == "super_off_peak"
    assert get_time_of_use_rate(RATE_5, second).period == "super_off_peak"


def test_sub_second_time_before_window_end() -> None:
    """A moment a microsecond before a window's end is still inside it."""
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 19, 59, 59, 999999)).period == "on_peak"


def test_fixed_offset_timezone() -> None:
    """A fixed-offset tzinfo is converted the same way as a ZoneInfo."""
    edt = timezone(timedelta(hours=-4))
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 16, 0, tzinfo=edt)).period == "on_peak"
    assert get_time_of_use_rate(RATE_5, datetime(2026, 8, 3, 15, 59, tzinfo=edt)).period == "off_peak"


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


# Holiday coverage for the older tariff periods is deliberately partial: of the 2024 plan's holidays only
# Thanksgiving is tested, and Memorial Day 2026 under the 2025 plan is not tested. The Home Assistant
# integration imports at most 365 days of history, so 2024-era intervals are not priced in practice, and the
# holiday rule itself is shared by every pre-July-2026 plan through time_of_use_charge(on_peak_weekdays_only=True).
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
