"""Units that meter readings are reported in."""

from enum import StrEnum


class MeterUnit(StrEnum):
    """The unit a meter reading's quantity is in, as declared by the Green Button feed's ``espi:uom``.

    This is the meter's unit, not the billing unit: electric plans bill per kWh and gas plans per therm. Use
    ``dominionsc.to_billing_units`` to convert.
    """

    WATT_HOUR = "Wh"
    """Watt-hours (ESPI ``uom`` 72). Electric meters."""

    CUBIC_FOOT = "ft3"
    """Cubic feet (ESPI ``uom`` 119). Gas meters."""
