"""Tests for meter units: parsing ``espi:uom`` and ``to_billing_units``."""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from dominionsc import (
    DEFAULT_THERMS_PER_CCF,
    RATE_8,
    RATE_32S,
    MeterUnit,
    UsageRead,
    to_billing_units,
)
from dominionsc.parsers.greenbutton import _extract_uom, _resolve_unit, parse_registers, parse_usage_reads

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _reading_type(uom: str | None) -> dict[str, object]:
    body: dict[str, object] = {"espi:kind": "12"}
    if uom is not None:
        body["espi:uom"] = uom
    return {"content": {"espi:ReadingType": body}}


# --- parser -----------------------------------------------------------------


def test_electric_fixture_is_watt_hours() -> None:
    """The electric fixture's registers and reads are in Wh."""
    xml = (FIXTURE_DIR / "greenbutton_multi_register.xml").read_text(encoding="utf-8")
    registers = parse_registers(xml, "America/New_York")
    assert registers
    for register in registers:
        assert register.unit is MeterUnit.WATT_HOUR
        assert all(read.unit is MeterUnit.WATT_HOUR for read in register.reads)


def test_gas_fixture_is_cubic_feet() -> None:
    """The gas fixture's reads are in ft³."""
    xml = (FIXTURE_DIR / "greenbutton_gas_scaled.xml").read_text(encoding="utf-8")
    reads = parse_usage_reads(xml, "America/New_York")
    assert reads
    assert {read.unit for read in reads} == {MeterUnit.CUBIC_FOOT}


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (_reading_type("72"), "72"),
        (_reading_type(" 119 "), "119"),
        (_reading_type(None), None),
        ({"content": {"espi:ReadingType": None}}, None),  # self-closing <espi:ReadingType/>
        ({"content": "text"}, None),
        ({}, None),
    ],
)
def test_extract_uom(entry: dict[str, object], expected: str | None) -> None:
    """The uom code is read from ReadingType entries and missing otherwise."""
    assert _extract_uom(entry) == expected


def test_resolve_unit_known_codes() -> None:
    """Known uom codes map to their MeterUnit."""
    assert _resolve_unit([_reading_type("72"), _reading_type("72")]) is MeterUnit.WATT_HOUR
    assert _resolve_unit([{}, _reading_type("119")]) is MeterUnit.CUBIC_FOOT


def test_resolve_unit_missing_is_none_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A feed with no uom gives None without a warning."""
    with caplog.at_level(logging.WARNING):
        assert _resolve_unit([{}, _reading_type(None)]) is None
    assert not caplog.records


def test_resolve_unit_unknown_code_warns_once(caplog: pytest.LogCaptureFixture) -> None:
    """An unknown uom gives None and one warning per feed."""
    with caplog.at_level(logging.WARNING):
        assert _resolve_unit([_reading_type("38"), _reading_type("38")]) is None
    assert len(caplog.records) == 1
    assert "Unknown ReadingType uom 38" in caplog.text


def test_resolve_unit_conflicting_codes_warns(caplog: pytest.LogCaptureFixture) -> None:
    """Conflicting uom codes give None and a warning."""
    with caplog.at_level(logging.WARNING):
        assert _resolve_unit([_reading_type("72"), _reading_type("119")]) is None
    assert "Multiple distinct ReadingType uom values" in caplog.text


def test_unknown_uom_in_feed_leaves_reads_without_unit(caplog: pytest.LogCaptureFixture) -> None:
    """A feed with an unknown uom parses with unit None."""
    xml = (FIXTURE_DIR / "greenbutton_gas_scaled.xml").read_text(encoding="utf-8")
    xml = xml.replace("<espi:uom>119</espi:uom>", "<espi:uom>999</espi:uom>")
    with caplog.at_level(logging.WARNING):
        reads = parse_usage_reads(xml, "America/New_York")
    assert reads
    assert all(read.unit is None for read in reads)
    assert caplog.text.count("Unknown ReadingType uom 999") == 1


def test_usage_read_positional_construction_still_works() -> None:
    """UsageRead's new unit field is optional and last."""
    start = datetime(2026, 7, 1, tzinfo=UTC)
    read = UsageRead(start, start, 1.0)
    assert read.unit is None


# --- to_billing_units -------------------------------------------------------


def test_watt_hours_to_kwh() -> None:
    """Wh convert to kWh, including floats and negatives."""
    assert to_billing_units(1500, MeterUnit.WATT_HOUR, RATE_8) == Decimal("1.5")
    assert to_billing_units(Decimal("250"), MeterUnit.WATT_HOUR, RATE_8) == Decimal("0.25")
    assert to_billing_units(0.1, MeterUnit.WATT_HOUR, RATE_8) == Decimal("0.0001")
    assert to_billing_units(-128, MeterUnit.WATT_HOUR, RATE_8) == Decimal("-0.128")


def test_cubic_feet_to_therms_default_factor() -> None:
    """ft³ convert to therms at the default 1.036 therms per CCF (about 1,036 BTU per cubic foot)."""
    assert Decimal("1.036") == DEFAULT_THERMS_PER_CCF
    assert to_billing_units(100, MeterUnit.CUBIC_FOOT, RATE_32S) == Decimal("1.036")
    assert to_billing_units(250.5, MeterUnit.CUBIC_FOOT, RATE_32S) == Decimal("2.59518")
    # A factor of exactly 1 is the integration's historical ft³ / 100.
    assert to_billing_units(250.5, MeterUnit.CUBIC_FOOT, RATE_32S, therms_per_ccf=Decimal(1)) == Decimal("2.505")


def test_cubic_feet_to_therms_custom_factor() -> None:
    """A custom therm factor is applied."""
    assert to_billing_units(100, MeterUnit.CUBIC_FOOT, RATE_32S, therms_per_ccf=Decimal("1.05")) == Decimal("1.05")


def test_plain_string_unit_is_accepted() -> None:
    """``MeterUnit`` is a ``StrEnum``, so its string value compares equal."""
    assert to_billing_units(1000, "Wh", RATE_8) == Decimal(1)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("unit", "plan"),
    [(MeterUnit.CUBIC_FOOT, RATE_8), (MeterUnit.WATT_HOUR, RATE_32S)],
)
def test_commodity_mismatch_raises(unit: MeterUnit, plan: object) -> None:
    """A unit for the wrong commodity raises ValueError."""
    with pytest.raises(ValueError, match="measured in"):
        to_billing_units(100, unit, plan)  # type: ignore[arg-type]
