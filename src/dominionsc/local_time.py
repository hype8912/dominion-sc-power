"""The utility's local time zone and helpers for converting into it.

Every date decision the tariffs make (which tariff period is in effect, the season, holidays, time-of-use
windows, billing cycles) is made in the service territory's local time, ``America/New_York``. This module is
the single place that converts a timestamp into that zone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from .config import DEFAULT_CONFIG

if TYPE_CHECKING:
    from datetime import date, datetime

UTILITY_TIMEZONE: ZoneInfo = ZoneInfo(DEFAULT_CONFIG.timezone)
"""The utility's local time zone (``America/New_York``). Tariff clock times and dates are local to it."""


def to_utility_local(when: datetime) -> datetime:
    """Return *when* as an aware datetime in the utility's time zone.

    A naive value is read as already local: its clock time is kept and the zone attached. An aware value is
    converted.
    """
    return when.replace(tzinfo=UTILITY_TIMEZONE) if when.tzinfo is None else when.astimezone(UTILITY_TIMEZONE)


def utility_local_date(when: datetime) -> date:
    """Return the calendar date of *when* in the utility's time zone.

    A naive value is read as already local. An aware value is converted first, so ``2026-07-01 02:00 UTC``
    gives ``2026-06-30``.
    """
    return to_utility_local(when).date()
