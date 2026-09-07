"""Green Button ESPI XML parser.

Pure function -- no network, no aiohttp, no DominionSC dependencies.
Takes raw XML text, returns UsageRead objects. This is the seam that
makes usage parsing testable without a live API call or HTTP mock.

See docs/REFACTOR_PLAN.md Phase 3.

Known limitation: for accounts with multiple electric registers (e.g.
net-metered solar), this flattens all UsagePoint entries into one list
with no register discrimination. Readings from separate registers will
share overlapping timestamps with no distinguishing attribute. This is
documented behaviour pending the multi-register follow-up issue -- do
not silently hide it by dropping duplicate timestamps.
"""

import zoneinfo
from datetime import UTC, datetime

import xmltodict

from ..exceptions import ApiException
from ..usage_read import UsageRead


def _ensure_list(value: object) -> list:
    """Wrap a single xmltodict dict in a list if needed.

    xmltodict returns a dict for a single child element and a list for
    multiple. This normalises both cases so callers always iterate.
    """
    if isinstance(value, list):
        return value
    return [value]


def parse_usage_reads(xml_text: str, timezone: str, url: str | None = None) -> list[UsageRead]:
    """Parse a Green Button ESPI XML response into a flat list of UsageRead objects.

    Args:
        xml_text: Raw XML string from Bidgely's gb-download endpoint.
        timezone: IANA timezone name for the utility (e.g. "America/New_York").
            Timestamps in the XML are UTC epoch seconds; this is used to
            convert them to timezone-aware datetimes in the utility's local
            zone, matching what the original code produced.
        url: Optional request URL, included in ApiException if parsing fails.

    Returns:
        Flat list of UsageRead objects, one per interval reading.

    Raises:
        ApiException: if the XML cannot be parsed or has an unexpected structure.

    """
    result: list[UsageRead] = []
    tz = zoneinfo.ZoneInfo(timezone)

    try:
        energy_usage = xmltodict.parse(xml_text)
        entries = _ensure_list(energy_usage["feed"]["entry"])

        for entry in entries:
            if not entry["title"].startswith("Interval Consumption"):
                continue

            intervals = _ensure_list(
                entry["content"]["espi:IntervalBlock"]["espi:IntervalReading"]
            )

            for interval in intervals:
                time_start = int(interval["espi:timePeriod"]["espi:start"])
                duration = int(interval["espi:timePeriod"]["espi:duration"])
                time_end = time_start + duration - 1
                consumption = int(interval["espi:value"])

                result.append(
                    UsageRead(
                        start_time=datetime.fromtimestamp(time_start, UTC).replace(tzinfo=tz),
                        end_time=datetime.fromtimestamp(time_end, UTC).replace(tzinfo=tz),
                        consumption=consumption,
                    )
                )

    except Exception as err:
        raise ApiException(
            "Unable to parse XML in parse_usage_reads.",
            url=url,
            response_text=xml_text,
        ) from err

    return result
