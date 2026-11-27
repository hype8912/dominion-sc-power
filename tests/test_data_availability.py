"""How the feed reports days whose data isn't available yet (docs/PRICING_API_PLAN.md, Q3 and Phase 4).

``greenbutton_gas_recent.xml`` is a real, redacted gb-download response requested through the day it was captured.
Days with no data yet are absent from the feed, not returned as zero-valued readings, so the library does not need
to filter anything, and consumers must not treat an all-zero day as "not available yet".
"""

import re
from collections import Counter
from datetime import date
from pathlib import Path

from dominionsc import MeterUnit
from dominionsc.parsers.greenbutton import parse_registers, parse_usage_reads

FIXTURE: Path = Path(__file__).parent / "fixtures" / "greenbutton_gas_recent.xml"
TZ = "America/New_York"


def _xml() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_most_recent_day_is_absent_not_zero_filled() -> None:
    """The capture day (2026-11-27) has no entry at all; the feed ends at the last day with data."""
    reads = parse_usage_reads(_xml(), TZ)
    days = Counter(read.start_time.date() for read in reads)
    assert sorted(days) == [date(2026, 11, 25), date(2026, 11, 26)]
    assert date(2026, 11, 27) not in days


def test_every_returned_day_is_complete() -> None:
    """Each day present has all 24 hourly gas readings: no partial or placeholder days."""
    days = Counter(read.start_time.date() for read in parse_usage_reads(_xml(), TZ))
    assert set(days.values()) == {24}


def test_zero_hours_are_real_readings_and_kept() -> None:
    """Hours with no gas use come back as zero-valued readings, and the parser keeps them."""
    (register,) = parse_registers(_xml(), TZ)
    assert register.unit is MeterUnit.CUBIC_FOOT
    zeros = [read for read in register.reads if read.consumption == 0]
    assert len(zeros) == 17
    assert len(register.reads) == 48


def test_all_zero_day_is_kept() -> None:
    """A day whose readings are all zero (a real no-usage day) is returned like any other day."""
    xml = _xml()
    day_start = xml.index("Interval Consumption. Start: 2026-11-25")
    day_end = xml.index("</entry>", day_start)
    zeroed = re.sub(r"<espi:value>-?\d+</espi:value>", "<espi:value>0</espi:value>", xml[day_start:day_end])
    reads = parse_usage_reads(xml[:day_start] + zeroed + xml[day_end:], TZ)

    first_day = [read for read in reads if read.start_time.date() == date(2026, 11, 25)]
    assert len(first_day) == 24
    assert all(read.consumption == 0 for read in first_day)
    assert any(read.consumption > 0 for read in reads if read.start_time.date() == date(2026, 11, 26))
