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

import logging
import re
import zoneinfo
from datetime import UTC, datetime
from typing import Any

import xmltodict

from ..exceptions import ApiException
from ..models.register_reads import RegisterReads
from ..models.usage_read import UsageRead

_LOGGER = logging.getLogger(__name__)

_USAGE_POINT_RE = re.compile(r"/UsagePoint/([^/]+)")


def _ensure_list(value: object) -> list[Any]:
    """Wrap a single xmltodict dict in a list if needed.

    xmltodict returns a dict for a single child element and a list for
    multiple. This normalizes both cases so callers always iterate.
    """
    if isinstance(value, list):
        return value
    return [value]


def _extract_usage_point_id(entry: dict[str, Any]) -> str | None:
    """Pull the ESPI UsagePoint id out of an entry's link hrefs.

    Each interval-consumption entry carries a list of <link> elements;
    the UsagePoint id appears in the href path as /UsagePoint/<id>.
    Returns None if no UsagePoint id can be found.
    """
    links: Any = entry.get("link")
    if links is None:
        return None
    for link in _ensure_list(links):
        if not isinstance(link, dict):
            continue
        href: Any = link.get("@href", "")
        match: re.Match[str] | None = _USAGE_POINT_RE.search(href)
        if match:
            return match.group(1)
    return None


def _extract_power_of_ten_multiplier(entry: dict[str, Any]) -> int | None:
    """Pull ``powerOfTenMultiplier`` out of a ``ReadingType`` entry, if present.

    ESPI's ``ReadingType`` declares the scale factor a reading's raw
    ``espi:value`` must be multiplied by (``10 ** powerOfTenMultiplier``) to
    reach the unit named in ``espi:uom`` -- it is *not* implied by the unit
    itself. Dominion's gas feed reports ``uom=119`` (cubic feet) with
    ``powerOfTenMultiplier=-3``, meaning raw values are thousandths of a
    cubic foot; ignoring this inflated stored gas consumption exactly 1000x
    (real bill: 5 CCF over 33 days; stored: ~500,000 ft³ over the same
    window). Electric's ReadingType has no multiplier element at all, which
    is why electric was unaffected and this went unnoticed for gas.

    Returns:
        The multiplier as an int, or ``None`` if this entry has no
        ``ReadingType`` content or no multiplier element (per the ESPI
        schema, a missing multiplier means 0 -- callers should default to
        that, not treat ``None`` as "unknown").

    """
    content: Any = entry.get("content")
    if not isinstance(content, dict):
        return None
    reading_type: Any = content.get("espi:ReadingType")
    if not isinstance(reading_type, dict):
        return None
    raw: Any = reading_type.get("espi:powerOfTenMultiplier")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resolve_scale_factor(entries: list[dict[str, Any]]) -> float:
    """Determine the consumption scale factor for a Green Button feed.

    Collects every distinct ``powerOfTenMultiplier`` declared anywhere in
    the feed's ``ReadingType`` entries. In every real feed observed so far
    (all gas, and single- or multi-register electric) there has been at
    most one distinct multiplier for the whole feed, so applying it
    uniformly to every interval reading is correct. If a future feed
    somehow declares different multipliers for different registers, per-
    register association isn't implemented -- rather than silently
    guessing which value applies where, this falls back to no scaling
    (1.0) and logs a warning so the discrepancy is visible instead of
    producing another silent, hard-to-diagnose inflation bug.

    Args:
        entries: All ``<entry>`` dicts from the parsed feed (not just the
                 interval-consumption ones -- ``ReadingType`` entries are
                 filtered out by the caller's main loop, so this must see
                 the full list before that filtering happens).

    Returns:
        The multiplicative scale factor (``10 ** multiplier``) to apply to
        every raw ``espi:value`` in this feed.

    """
    multipliers: set[int] = {m for entry in entries if (m := _extract_power_of_ten_multiplier(entry)) is not None}
    if len(multipliers) > 1:
        _LOGGER.warning(
            "Multiple distinct ReadingType powerOfTenMultiplier values found "
            "in one feed (%s) -- per-register association isn't implemented, "
            "so no scaling is applied as a safe fallback. Consumption values "
            "may be wrong; please report this.",
            sorted(multipliers),
        )
        return 1.0
    multiplier: int = next(iter(multipliers), 0)
    return float(10**multiplier)


def _parse_intervals(entry: dict[str, Any], tz: zoneinfo.ZoneInfo, scale: float) -> list[UsageRead]:
    """Parse all IntervalReading elements in one entry into UsageRead objects.

    ``scale`` (from :func:`_resolve_scale_factor`) converts each raw
    ``espi:value`` into the unit named by the feed's ``ReadingType`` --
    e.g. Dominion's gas feed requires ``scale=0.001`` to convert raw
    thousandths-of-a-cubic-foot into cubic feet.

    Args:
        entry: One "Interval Consumption" ``<entry>`` dict from xmltodict.
        tz: Timezone attached to each reading's timestamps.
        scale: Multiplier applied to every raw ``espi:value``.

    Returns:
        One ``UsageRead`` per ``espi:IntervalReading``, in document order.

    """
    reads: list[UsageRead] = []
    intervals: list[Any] = _ensure_list(entry["content"]["espi:IntervalBlock"]["espi:IntervalReading"])
    for interval in intervals:
        time_start: int = int(interval["espi:timePeriod"]["espi:start"])
        duration: int = int(interval["espi:timePeriod"]["espi:duration"])
        # End is inclusive: one second before the next interval starts.
        time_end: int = time_start + duration - 1
        consumption: float = int(interval["espi:value"]) * scale
        # replace(tzinfo=...) relabels the UTC clock time with the local zone; it does
        # not convert it (astimezone would). The stored clock time is the UTC one.
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
            timestamps are epoch seconds; each reading is tagged with this
            zone without shifting its clock time (see ``_parse_intervals``).
        url: Optional request URL, included in ApiException if parsing fails.

    Returns:
        List of RegisterReads, one per distinct UsagePoint, in first-seen
        order. Empty list if the response contains no interval data.

    Raises:
        ApiException: if the XML cannot be parsed or has an unexpected structure.

    """
    tz: zoneinfo.ZoneInfo = zoneinfo.ZoneInfo(timezone)

    try:
        energy_usage: Any = xmltodict.parse(xml_text)
        entries: list[Any] = _ensure_list(energy_usage["feed"]["entry"])

        # Computed once per feed from every ReadingType entry present (not
        # just interval-consumption ones) -- see _resolve_scale_factor.
        scale: float = _resolve_scale_factor(entries)

        # Preserve first-seen order of UsagePoints while accumulating.
        registers: dict[str, RegisterReads] = {}
        # Entries with no resolvable UsagePoint id are grouped under a single
        # empty-string key so their data is never silently dropped.
        for entry in entries:
            title: Any = entry.get("title", "")
            if not (isinstance(title, str) and title.startswith("Interval Consumption")):
                continue

            usage_point_id: str = _extract_usage_point_id(entry) or ""
            if usage_point_id not in registers:
                registers[usage_point_id] = RegisterReads(usage_point_id=usage_point_id)
            registers[usage_point_id].reads.extend(_parse_intervals(entry, tz, scale))

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
