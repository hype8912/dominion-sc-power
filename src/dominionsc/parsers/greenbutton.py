"""Green Button ESPI XML parser.

Pure functions -- no network, no aiohttp, no DominionSC dependencies.
Takes raw XML text, returns parsed reading objects. This is the seam
that makes usage parsing testable without a live API call or HTTP mock.

Two entry points:
    parse_registers(xml)  -> list[RegisterReads]  (register-aware, preferred)
    parse_usage_reads(xml) -> list[UsageRead]     (flat, backward compat)

A single Green Button response for one measurement type can contain
multiple ESPI UsagePoints. For a net-metered solar account, one register
meters grid delivery and another meters solar export -- these are
separate billed meters. parse_registers() keeps them separate, keyed on
the stable UsagePoint id. parse_usage_reads() flattens everything into
one list and is retained only for single-register consumers and
backward compatibility.

See docs/REFACTOR_PLAN.md Phase 3 and the multi-register work.
"""

import re
import zoneinfo
from datetime import UTC, datetime

import xmltodict

from ..exceptions import ApiException
from ..models.register_reads import RegisterReads
from ..models.usage_read import UsageRead

_USAGE_POINT_RE = re.compile(r"/UsagePoint/([^/]+)")


def _ensure_list(value: object) -> list:
    """Wrap a single xmltodict dict in a list if needed.

    xmltodict returns a dict for a single child element and a list for
    multiple. This normalises both cases so callers always iterate.
    """
    if isinstance(value, list):
        return value
    return [value]


def _extract_usage_point_id(entry: dict) -> str | None:
    """Pull the ESPI UsagePoint id out of an entry's link hrefs.

    Each interval-consumption entry carries a list of <link> elements;
    the UsagePoint id appears in the href path as /UsagePoint/<id>.
    Returns None if no UsagePoint id can be found.
    """
    links = entry.get("link")
    if links is None:
        return None
    for link in _ensure_list(links):
        if not isinstance(link, dict):
            continue
        href = link.get("@href", "")
        match = _USAGE_POINT_RE.search(href)
        if match:
            return match.group(1)
    return None


def _parse_intervals(entry: dict, tz: zoneinfo.ZoneInfo) -> list[UsageRead]:
    """Parse all IntervalReading elements in one entry into UsageRead objects."""
    reads: list[UsageRead] = []
    intervals = _ensure_list(entry["content"]["espi:IntervalBlock"]["espi:IntervalReading"])
    for interval in intervals:
        time_start = int(interval["espi:timePeriod"]["espi:start"])
        duration = int(interval["espi:timePeriod"]["espi:duration"])
        time_end = time_start + duration - 1
        consumption = int(interval["espi:value"])
        reads.append(
            UsageRead(
                start_time=datetime.fromtimestamp(time_start, UTC).replace(tzinfo=tz),
                end_time=datetime.fromtimestamp(time_end, UTC).replace(tzinfo=tz),
                consumption=consumption,
            )
        )
    return reads


def parse_registers(xml_text: str, timezone: str, url: str | None = None) -> list[RegisterReads]:
    """Parse a Green Button ESPI XML response, grouped by meter register.

    A single response can contain multiple ESPI UsagePoints (e.g. grid
    delivery + solar export for a net-metered account). Each UsagePoint
    typically spans many daily entries; all of a UsagePoint's readings
    are accumulated into a single RegisterReads, keyed on its stable id.

    The library stays unopinionated: registers are returned in first-seen
    order, reading signs are preserved exactly as reported, and no attempt
    is made to label a register as "grid" vs "solar".

    Args:
        xml_text: Raw XML string from Bidgely's gb-download endpoint.
        timezone: IANA timezone name (e.g. "America/New_York"). Interval
            timestamps are UTC epoch seconds, converted to this zone.
        url: Optional request URL, included in ApiException if parsing fails.

    Returns:
        List of RegisterReads, one per distinct UsagePoint, in first-seen
        order. Empty list if the response contains no interval data.

    Raises:
        ApiException: if the XML cannot be parsed or has an unexpected structure.

    """
    tz = zoneinfo.ZoneInfo(timezone)

    try:
        energy_usage = xmltodict.parse(xml_text)
        entries = _ensure_list(energy_usage["feed"]["entry"])

        # Preserve first-seen order of UsagePoints while accumulating.
        registers: dict[str, RegisterReads] = {}
        # Entries with no resolvable UsagePoint id are grouped under a single
        # empty-string key so their data is never silently dropped.
        for entry in entries:
            title = entry.get("title", "")
            if not (isinstance(title, str) and title.startswith("Interval Consumption")):
                continue

            usage_point_id = _extract_usage_point_id(entry) or ""
            if usage_point_id not in registers:
                registers[usage_point_id] = RegisterReads(usage_point_id=usage_point_id)
            registers[usage_point_id].reads.extend(_parse_intervals(entry, tz))

        return list(registers.values())

    except Exception as err:
        raise ApiException(
            "Unable to parse XML in parse_registers.",
            url=url,
            response_text=xml_text,
        ) from err


def parse_usage_reads(xml_text: str, timezone: str, url: str | None = None) -> list[UsageRead]:
    """Parse a Green Button ESPI XML response into a flat list of UsageRead objects.

    Backward-compatible convenience wrapper around parse_registers(): it
    concatenates every register's readings into one list. Suitable for
    single-register accounts (most homes, and all gas). For multi-register
    accounts (net-metered solar) this flattens grid and solar-export
    readings together with overlapping timestamps -- use parse_registers()
    instead when register separation matters.

    Args:
        xml_text: Raw XML string from Bidgely's gb-download endpoint.
        timezone: IANA timezone name (e.g. "America/New_York").
        url: Optional request URL, included in ApiException if parsing fails.

    Returns:
        Flat list of UsageRead objects across all registers.

    Raises:
        ApiException: if the XML cannot be parsed or has an unexpected structure.

    """
    reads: list[UsageRead] = []
    for register in parse_registers(xml_text, timezone, url=url):
        reads.extend(register.reads)
    return reads
