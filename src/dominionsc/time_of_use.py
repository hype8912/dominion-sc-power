"""Look up the time-of-use rate in force at a given moment."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from .local_time import UTILITY_TIMEZONE, to_utility_local
from .models.rate_plan import Season, TimeOfUseCharge

if TYPE_CHECKING:
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    from .models.rate_plan import RatePlan, TimeOfUsePeriod, TimeWindow

# The tariffs' clock times are local to the utility's service territory. Kept as an alias of
# ``dominionsc.UTILITY_TIMEZONE`` for code that imported it from here before 0.4.0.
LOCAL_TIMEZONE: ZoneInfo = UTILITY_TIMEZONE

# Summer is billing months May-September; every other month is winter.
_SUMMER_MONTHS: frozenset[int] = frozenset(range(5, 10))


@dataclass(frozen=True, slots=True)
class TimeOfUseRate:
    """The time-of-use price in force at one moment.

    Attributes:
        period: Name of the matching period (e.g. ``"on_peak"``, ``"off_peak"``, ``"super_off_peak"``).
        price_per_kwh: Dollar cost per kWh during that period.
        season: Season the moment falls in.

    """

    period: str
    price_per_kwh: Decimal
    season: Season


def season_for(day: date) -> Season:
    """Return the tariff season for ``day``: summer is May-September, winter is October-April.

    The tariffs define seasons by *billing* month. This uses the calendar month
    of ``day`` instead, so each interval is priced by the month it falls in. A
    billing cycle that spans a season boundary (for example April 20 to May 19)
    is therefore split between seasons. If you price by billing month, look up
    ``periods_by_season`` with the season of the billing month instead.
    """
    return Season.SUMMER if day.month in _SUMMER_MONTHS else Season.WINTER


def _in_window(clock: time, window: TimeWindow) -> bool:
    """Return whether ``clock`` falls in the half-open ``window``, which may cross midnight."""
    if window.start <= window.end:
        return window.start <= clock < window.end
    return clock >= window.start or clock < window.end


def get_time_of_use_rate(plan: RatePlan, when: datetime) -> TimeOfUseRate:
    """Return the time-of-use rate that applies to ``plan`` at ``when``.

    Handles the season, the clock windows, and each period's weekday and holiday
    rules (``TimeOfUsePeriod.applies_on``). Pass the plan that was in effect at
    ``when``: ``get_rate_plan_for_date(code, when.date())`` returns it. The rules
    differ between tariff periods, so using the current plan for a past date
    gives the wrong answer.

    Args:
        plan: A plan with a ``TimeOfUseCharge`` (Rate 5 or Rate 7).
        when: The moment to price. A naive value is read as local time
            (``America/New_York``); an aware value is converted to it.
            For 15-minute interval data, pass the interval's start time.

    Returns:
        The matching ``TimeOfUseRate``.

    Raises:
        ValueError: If ``plan`` has no time-of-use charge, ``when`` is outside the
            plan's effective dates, or the plan has no periods or no fallback
            period for the season.

    """
    local: datetime = to_utility_local(when)
    day: date = local.date()
    if day < plan.effective_from or (plan.effective_to is not None and day > plan.effective_to):
        msg = f"{day} is outside {plan.code}'s effective dates ({plan.effective_from} to {plan.effective_to})"
        raise ValueError(msg)

    charge: TimeOfUseCharge | None = next((c for c in plan.charges if isinstance(c, TimeOfUseCharge)), None)
    if charge is None:
        msg = f"{plan.code} has no time-of-use charge"
        raise ValueError(msg)

    season: Season = season_for(day)
    periods: tuple[TimeOfUsePeriod, ...] = charge.periods_by_season.get(season, ())
    if not periods:
        msg = f"{plan.code} has no time-of-use periods for {season}"
        raise ValueError(msg)

    clock: time = local.time()
    matched: TimeOfUsePeriod | None = next(
        (p for p in periods if p.applies_on(day) and any(_in_window(clock, w) for w in p.windows)),
        None,
    )
    if matched is None:
        matched = next((p for p in periods if p.fallback), None)

    if matched is None:
        msg = f"{plan.code} has no fallback time-of-use period for {season}"
        raise ValueError(msg)

    return TimeOfUseRate(period=matched.name, price_per_kwh=matched.price_per_unit, season=season)
