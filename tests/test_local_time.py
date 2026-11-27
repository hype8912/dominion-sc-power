"""Tests for the utility-local time helpers and ``resolve_plan_for``."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from dominionsc import (
    RATE_5,
    RATE_5_2024,
    RATE_5_2025,
    RATE_8,
    RATE_8_2025,
    UTILITY_TIMEZONE,
    Commodity,
    FlatUsageCharge,
    RatePlan,
    resolve_plan_for,
    utility_local_date,
)
from dominionsc.time_of_use import LOCAL_TIMEZONE

ET = ZoneInfo("America/New_York")


def test_utility_timezone_is_eastern_and_aliased() -> None:
    """UTILITY_TIMEZONE is Eastern time and LOCAL_TIMEZONE still points at it."""
    assert ZoneInfo("America/New_York") == UTILITY_TIMEZONE
    assert LOCAL_TIMEZONE is UTILITY_TIMEZONE


@pytest.mark.parametrize(
    ("when", "expected"),
    [
        # 02:00 UTC on July 1 is still June 30 in Eastern (daylight) time.
        (datetime(2026, 7, 1, 2, 0, tzinfo=UTC), date(2026, 6, 30)),
        (datetime(2026, 7, 1, 4, 0, tzinfo=UTC), date(2026, 7, 1)),
        # Winter: UTC-5, so 04:59 UTC is still the previous day.
        (datetime(2026, 1, 2, 4, 59, tzinfo=UTC), date(2026, 1, 1)),
        (datetime(2026, 1, 2, 5, 0, tzinfo=UTC), date(2026, 1, 2)),
        # A naive value is read as already local.
        (datetime(2026, 7, 1, 2, 0), date(2026, 7, 1)),
        (datetime(2026, 6, 30, 23, 59), date(2026, 6, 30)),
        # Fixed offsets other than UTC are converted too.
        (datetime(2026, 7, 1, 1, 0, tzinfo=ZoneInfo("America/Los_Angeles")), date(2026, 7, 1)),
    ],
)
def test_utility_local_date(when: datetime, expected: date) -> None:
    """Aware values are converted to Eastern time; naive values are read as local."""
    assert utility_local_date(when) == expected


@pytest.mark.parametrize(
    "transition",
    [datetime(2026, 3, 8, 7, 0, tzinfo=UTC), datetime(2026, 11, 1, 6, 0, tzinfo=UTC)],
    ids=["spring-forward", "fall-back"],
)
def test_utility_local_date_across_dst(transition: datetime) -> None:
    """Every UTC minute around a DST change maps to the date Eastern clocks show."""
    for minutes in range(-180, 181, 15):
        moment: datetime = transition + timedelta(minutes=minutes)
        assert utility_local_date(moment) == moment.astimezone(ET).date()
    assert utility_local_date(transition) == transition.date()


# --- resolve_plan_for -------------------------------------------------------


@pytest.mark.parametrize(
    ("plan", "when", "expected"),
    [
        (RATE_8, date(2025, 7, 22), None),  # before the earliest recorded period
        (RATE_8, date(2025, 7, 23), RATE_8_2025),
        (RATE_8, date(2026, 6, 30), RATE_8_2025),
        (RATE_8, date(2026, 7, 1), RATE_8),
        (RATE_8, date(2030, 1, 1), RATE_8),
        # Any period of the code resolves the same way.
        (RATE_8_2025, date(2026, 7, 1), RATE_8),
        (RATE_5, RATE_5_2024.effective_from, RATE_5_2024),
        (RATE_5, RATE_5_2025.effective_from - timedelta(days=1), RATE_5_2024),
        (RATE_5, RATE_5_2025.effective_from, RATE_5_2025),
    ],
)
def test_resolve_catalog_plan(plan: RatePlan, when: date, expected: RatePlan | None) -> None:
    """Catalog plans resolve to the period in effect, boundaries inclusive."""
    assert resolve_plan_for(plan, when) is expected


def test_resolve_uses_local_date_for_datetimes() -> None:
    """Datetimes resolve by their Eastern-time date."""
    # 02:00 UTC on 2026-07-01 is 2026-06-30 in Eastern time, under the 2025 tariff.
    assert resolve_plan_for(RATE_8, datetime(2026, 7, 1, 2, 0, tzinfo=UTC)) is RATE_8_2025
    assert resolve_plan_for(RATE_8, datetime(2026, 7, 1, 4, 0, tzinfo=UTC)) is RATE_8
    assert resolve_plan_for(RATE_8, datetime(2026, 7, 1, 0, 0)) is RATE_8


_CUSTOM = RatePlan(
    code="custom_plan",
    name="Custom",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 1, 1),
    effective_to=date(2026, 12, 31),
    charges=(FlatUsageCharge(name="Energy", price_per_unit=Decimal("0.1")),),
)


@pytest.mark.parametrize(
    ("when", "in_effect"),
    [
        (date(2025, 12, 31), False),
        (date(2026, 1, 1), True),
        (date(2026, 12, 31), True),
        (date(2027, 1, 1), False),  # effective_to is honoured for non-catalog plans
    ],
)
def test_resolve_non_catalog_plan(when: date, in_effect: bool) -> None:
    """Non-catalog plans resolve to themselves only within their effective dates."""
    assert resolve_plan_for(_CUSTOM, when) is (_CUSTOM if in_effect else None)


def test_resolve_open_ended_non_catalog_plan() -> None:
    """A non-catalog plan with no effective_to stays in effect."""
    open_ended = RatePlan("custom_open", "Open", Commodity.ELECTRICITY, date(2026, 1, 1), None, ())
    assert resolve_plan_for(open_ended, date(2099, 1, 1)) is open_ended


def test_closed_to_new_customers() -> None:
    """Only Rate 1 is closed to new customers."""
    from dominionsc import RATE_1, get_available_rate_plans

    assert RATE_1.closed_to_new_customers is True
    assert [p.code for p in get_available_rate_plans() if p.closed_to_new_customers] == ["rate_1"]
