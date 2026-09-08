"""Tests for parsers/greenbutton.py and parsers/forecast.py.

These tests exercise the parsers against static fixtures and synthetic
payloads -- no network, no credentials, no HTTP mocks required.
See docs/REFACTOR_PLAN.md Phase 3.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from dominionsc.exceptions import ApiException
from dominionsc.models.register_reads import RegisterReads
from dominionsc.parsers.forecast import parse_forecast
from dominionsc.parsers.greenbutton import (
    _extract_usage_point_id,
    parse_registers,
    parse_usage_reads,
)
from dominionsc.usage_read import UsageRead

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# UsagePoint ids used in the redacted fixture
GRID_UP = "REDACTED_UP_GRID"
SOLAR_UP = "REDACTED_UP_SOLAR"


# ---------------------------------------------------------------------------
# Green Button XML parser -- register-aware (parse_registers)
# ---------------------------------------------------------------------------


class TestParseRegisters:
    """Tests for parse_registers() -- the register-separating parser."""

    def _load_fixture(self, name: str) -> str:
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")

    def test_returns_two_registers(self):
        """A net-metered fixture yields exactly two RegisterReads (grid + solar)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = parse_registers(xml, "America/New_York")
        assert len(registers) == 2
        for reg in registers:
            assert isinstance(reg, RegisterReads)

    def test_registers_keyed_by_usage_point_id(self):
        """Each register carries its stable UsagePoint id from the link href."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = parse_registers(xml, "America/New_York")
        ids = {reg.usage_point_id for reg in registers}
        assert ids == {GRID_UP, SOLAR_UP}

    def test_daily_entries_merge_into_one_register(self):
        """Multiple daily entries for the same UsagePoint accumulate together.

        The grid register has a 2-reading day and a 1-reading day = 3 reads;
        this proves entries are grouped by UsagePoint, not returned per-entry.
        """
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = {r.usage_point_id: r for r in parse_registers(xml, "America/New_York")}
        assert len(registers[GRID_UP].reads) == 3
        assert len(registers[SOLAR_UP].reads) == 3

    def test_grid_values_positive(self):
        """Grid register readings preserve their positive values, in order."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = {r.usage_point_id: r for r in parse_registers(xml, "America/New_York")}
        consumptions = [r.consumption for r in registers[GRID_UP].reads]
        assert consumptions == [209, 328, 412]

    def test_solar_values_negative_preserved(self):
        """Solar-export register readings preserve negative values (sign kept)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = {r.usage_point_id: r for r in parse_registers(xml, "America/New_York")}
        consumptions = [r.consumption for r in registers[SOLAR_UP].reads]
        assert consumptions == [0, -128, -450]

    def test_registers_do_not_bleed_into_each_other(self):
        """Grid and solar readings stay in their own register (no cross-contamination)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        registers = {r.usage_point_id: r for r in parse_registers(xml, "America/New_York")}
        # No negative values should appear in the grid register
        assert all(r.consumption >= 0 for r in registers[GRID_UP].reads)
        # The solar register contains the negatives
        assert any(r.consumption < 0 for r in registers[SOLAR_UP].reads)

    def test_single_register_returns_one_element_list(self):
        """A single-UsagePoint response (gas, non-solar home) returns one register."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <link href="https://x/Customer/C/UsagePoint/ONLY_ONE/MeterReading/M/IntervalBlock/IB" rel="self"/>
    <title>Interval Consumption. Start: 2026-08-13</title>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod><espi:start>1786579200</espi:start><espi:duration>3600</espi:duration></espi:timePeriod>
          <espi:value>15</espi:value>
        </espi:IntervalReading>
      </espi:IntervalBlock>
    </content>
  </entry>
</feed>"""
        registers = parse_registers(xml, "America/New_York")
        assert len(registers) == 1
        assert registers[0].usage_point_id == "ONLY_ONE"
        assert len(registers[0].reads) == 1

    def test_entry_without_usage_point_grouped_under_empty_key(self):
        """An interval entry lacking a UsagePoint href is not dropped."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <title>Interval Consumption. Start: 2026-08-13</title>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod><espi:start>1786579200</espi:start><espi:duration>900</espi:duration></espi:timePeriod>
          <espi:value>42</espi:value>
        </espi:IntervalReading>
      </espi:IntervalBlock>
    </content>
  </entry>
</feed>"""
        registers = parse_registers(xml, "America/New_York")
        assert len(registers) == 1
        assert registers[0].usage_point_id == ""
        assert registers[0].reads[0].consumption == 42

    def test_empty_feed_returns_empty_list(self):
        """A feed with no Interval Consumption entries returns an empty list."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <title>ReadingType entry</title>
    <content><espi:ReadingType/></content>
  </entry>
</feed>"""
        assert parse_registers(xml, "America/New_York") == []

    def test_invalid_xml_raises_api_exception(self):
        """Malformed XML raises ApiException, not a bare xmltodict error."""
        with pytest.raises(ApiException, match="Unable to parse XML in parse_registers"):
            parse_registers("this is not xml", "America/New_York")

    def test_non_dict_link_is_skipped(self):
        """A link element that xmltodict renders as a bare string is skipped, not crashed on."""
        # When an <entry> has a single self-closing <link/> with no attributes,
        # xmltodict can yield None/str rather than a dict; the extractor must
        # tolerate that and fall through to the empty-key register.
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <link/>
    <title>Interval Consumption. Start: 2026-08-13</title>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod><espi:start>1786579200</espi:start><espi:duration>900</espi:duration></espi:timePeriod>
          <espi:value>7</espi:value>
        </espi:IntervalReading>
      </espi:IntervalBlock>
    </content>
  </entry>
</feed>"""
        registers = parse_registers(xml, "America/New_York")
        assert len(registers) == 1
        assert registers[0].usage_point_id == ""
        assert registers[0].reads[0].consumption == 7

    def test_link_without_usage_point_href_yields_empty_id(self):
        """A link whose href has no /UsagePoint/ segment yields the empty-key register."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <link href="https://x/Customer/C/SomethingElse/123" rel="self"/>
    <title>Interval Consumption. Start: 2026-08-13</title>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod><espi:start>1786579200</espi:start><espi:duration>900</espi:duration></espi:timePeriod>
          <espi:value>9</espi:value>
        </espi:IntervalReading>
      </espi:IntervalBlock>
    </content>
  </entry>
</feed>"""
        registers = parse_registers(xml, "America/New_York")
        assert len(registers) == 1
        assert registers[0].usage_point_id == ""
        assert registers[0].reads[0].consumption == 9


# ---------------------------------------------------------------------------
# Green Button XML parser -- flat wrapper (parse_usage_reads)
# ---------------------------------------------------------------------------


class TestParseUsageReads:
    """Tests for parse_usage_reads() -- the backward-compat flat wrapper."""

    def _load_fixture(self, name: str) -> str:
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")

    def test_flattens_all_registers(self):
        """Flat wrapper concatenates every register's readings (3 grid + 3 solar = 6)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")
        assert len(reads) == 6
        for r in reads:
            assert isinstance(r, UsageRead)

    def test_all_values_present_across_registers(self):
        """Every reading value from both registers appears in the flat list."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        values = sorted(r.consumption for r in parse_usage_reads(xml, "America/New_York"))
        assert values == sorted([209, 328, 412, 0, -128, -450])

    def test_interval_duration_correct(self):
        """end_time - start_time reflects the espi:duration field (900s -> 899s span)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")
        assert reads[0].end_time - reads[0].start_time == timedelta(seconds=899)

    def test_timestamps_are_timezone_aware(self):
        """Returned datetimes are timezone-aware."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        for r in parse_usage_reads(xml, "America/New_York"):
            assert r.start_time.tzinfo is not None
            assert r.end_time.tzinfo is not None

    def test_single_interval_reading_not_a_list(self):
        """Xmltodict returns a dict (not list) for a single child -- _ensure_list handles it."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <title>Interval Consumption. Start: 2026-08-13</title>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod>
            <espi:start>1786579200</espi:start>
            <espi:duration>900</espi:duration>
          </espi:timePeriod>
          <espi:value>500</espi:value>
        </espi:IntervalReading>
      </espi:IntervalBlock>
    </content>
  </entry>
</feed>"""
        reads = parse_usage_reads(xml, "America/New_York")
        assert len(reads) == 1
        assert reads[0].consumption == 500

    def test_invalid_xml_raises_api_exception(self):
        """Malformed XML raises ApiException."""
        with pytest.raises(ApiException, match="Unable to parse XML"):
            parse_usage_reads("this is not xml", "America/New_York")

    def test_missing_feed_key_raises_api_exception(self):
        """Valid XML that lacks the expected ESPI structure raises ApiException."""
        with pytest.raises(ApiException):
            parse_usage_reads("<root><something/></root>", "America/New_York")

    def test_url_included_in_exception(self):
        """The url argument is forwarded to the raised ApiException."""
        sentinel = "https://example.com/test-url"
        with pytest.raises(ApiException) as exc_info:
            parse_usage_reads("bad xml", "America/New_York", url=sentinel)
        assert exc_info.value.url == sentinel

    def test_empty_feed_returns_empty_list(self):
        """A feed with no Interval Consumption entries returns an empty list."""
        xml = """<?xml version="1.0"?>
<feed>
  <entry>
    <title>ReadingType entry</title>
    <content><espi:ReadingType/></content>
  </entry>
</feed>"""
        reads = parse_usage_reads(xml, "America/New_York")
        assert reads == []

    def test_extract_skips_non_dict_link(self):
        """Line 57: non-dict link entries are skipped, dict links still match."""
        entry = {"link": ["bad-string", {"@href": "/UsagePoint/UP99"}]}
        assert _extract_usage_point_id(entry) == "UP99"


# ---------------------------------------------------------------------------
# Forecast JSON parser
# ---------------------------------------------------------------------------


class TestParseForecast:
    """Tests for parse_forecast()."""

    def _make_payload(self, **overrides):
        """Build a minimal valid AMI usage-alert payload."""
        alert = {
            "currentBillUsageStartDate": "2026-08-13",
            "currentBillUsageEndDate": "2026-09-10",
            "currentBillThroughDate": "2026-09-07",
            "totalCostUnbilledConsumption": 56.78,
            "currentCostPerDay": 4.50,
            "numberOfDaysInCurrentBill": 28,
            "lastYearAmountExists": True,
            "lastYearTotalAmount": 112.34,
        }
        alert.update(overrides)
        return {"data": {"amiUsageAlert": alert}}

    def test_parses_valid_payload(self):
        """Happy path: all fields present and valid."""
        from dominionsc.forecast import Forecast

        result = parse_forecast(self._make_payload())
        assert isinstance(result, Forecast)
        assert result.start_date == date(2026, 8, 13)
        assert result.end_date == date(2026, 9, 10)
        assert result.current_date == date(2026, 9, 7)
        assert result.cost_to_date == 56.78
        assert result.forecasted_cost == round(4.50 * 28, 2)
        assert result.typical_cost == 112.34

    def test_no_typical_cost_when_last_year_absent(self):
        """typical_cost is None when lastYearAmountExists is False."""
        result = parse_forecast(self._make_payload(lastYearAmountExists=False))
        assert result.typical_cost is None

    def test_missing_field_raises_api_exception(self):
        """A payload missing a required field raises ApiException."""
        bad_payload = {"data": {"amiUsageAlert": {}}}
        with pytest.raises(ApiException, match="Failed to decode forecast data"):
            parse_forecast(bad_payload)

    def test_url_included_in_exception(self):
        """The url argument is forwarded to the raised ApiException."""
        sentinel = "https://example.com/test-forecast-url"
        with pytest.raises(ApiException) as exc_info:
            parse_forecast({}, url=sentinel)
        assert exc_info.value.url == sentinel

    def test_forecasted_cost_is_rounded(self):
        """forecasted_cost is rounded to two decimal places."""
        result = parse_forecast(
            self._make_payload(
                currentCostPerDay=3.333,
                numberOfDaysInCurrentBill=30,
            )
        )
        assert result.forecasted_cost == round(3.333 * 30, 2)
