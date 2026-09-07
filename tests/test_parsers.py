"""Tests for parsers/greenbutton.py and parsers/forecast.py.

These tests exercise the parsers against static fixtures and synthetic
payloads -- no network, no credentials, no HTTP mocks required.
See docs/REFACTOR_PLAN.md Phase 3.
"""

from datetime import date
from pathlib import Path

import pytest

from dominionsc.exceptions import ApiException
from dominionsc.parsers.forecast import parse_forecast
from dominionsc.parsers.greenbutton import parse_usage_reads
from dominionsc.usage_read import UsageRead

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Green Button XML parser
# ---------------------------------------------------------------------------


class TestParseUsageReads:
    """Tests for parse_usage_reads()."""

    def _load_fixture(self, name: str) -> str:
        return (FIXTURE_DIR / name).read_text(encoding="utf-8")

    def test_parses_multi_register_fixture(self):
        """Parse the committed multi-register fixture without error."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        # Two UsagePoint entries x 2 intervals each = 4 readings total.
        # Known limitation: all four are in one flat list regardless of register.
        assert len(reads) == 4
        for r in reads:
            assert isinstance(r, UsageRead)

    def test_grid_delivery_values_preserved(self):
        """Grid-delivery register values (positive Wh) are parsed correctly."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        # Grid readings are the first two (from UsagePoint 1, register :1)
        assert reads[0].consumption == 209
        assert reads[1].consumption == 328

    def test_solar_export_negative_values_preserved(self):
        """Solar-export register values (negative Wh) survive the int() cast."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        # Solar readings are the second two (from UsagePoint 3, register :3)
        assert reads[2].consumption == 0
        assert reads[3].consumption == -128

    def test_interval_duration_correct(self):
        """end_time - start_time should reflect the espi:duration field (900s = 14:59)."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        r = reads[0]
        # duration=900 seconds; end = start + 899
        delta = r.end_time - r.start_time
        assert delta.seconds == 899

    def test_timestamps_are_timezone_aware(self):
        """Returned datetimes are timezone-aware in the supplied utility timezone."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        for r in reads:
            assert r.start_time.tzinfo is not None
            assert r.end_time.tzinfo is not None

    def test_non_interval_entries_skipped(self):
        """ReadingType and other non-Interval Consumption entries are ignored."""
        xml = self._load_fixture("greenbutton_multi_register.xml")
        reads = parse_usage_reads(xml, "America/New_York")

        # Fixture has 1 ReadingType entry that should be skipped -- if not skipped
        # we would get a KeyError and the test would fail with ApiException, not 4.
        assert len(reads) == 4

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
        """Malformed XML raises ApiException, not a bare xmltodict error."""
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
        result = parse_forecast(self._make_payload(
            currentCostPerDay=3.333,
            numberOfDaysInCurrentBill=30,
        ))
        assert result.forecasted_cost == round(3.333 * 30, 2)
