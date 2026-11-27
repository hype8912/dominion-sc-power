"""Convert meter quantities (Wh, ft³) into the units rate plans bill in (kWh, therm)."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .models.rate_plan import Commodity
from .models.units import MeterUnit

if TYPE_CHECKING:
    from .models.rate_plan import RatePlan

__all__: list[str] = ["DEFAULT_THERMS_PER_CCF", "MeterUnit", "to_billing_units"]

DEFAULT_THERMS_PER_CCF: Decimal = Decimal("1.036")
"""Therms per hundred cubic feet (CCF) of gas used when no other factor is given.

Dominion bills gas in therms while the meter reports cubic feet. Its Gas General Terms and Conditions
(section III.B) convert by the weighted average heat content (BTU per cubic foot) of the gas entering its system
over the days of the customer's billing cycle, divided by 1,000. So the true factor is that average BTU / 1,000
therms per CCF. It changes every billing cycle, is not in the tariff or in the Green Button feed, and is normally
within 0.95 to 1.40 (the tariff's stated range of 950 to 1,400 BTU per cubic foot).

The default, ``1.036``, is an estimate: the average heat content of natural gas delivered to South Carolina
consumers over September 2024 to August 2026 was 1,036 BTU per cubic foot (U.S. Energy Information Administration
monthly series ``NGA_EPG0_VGTH_SSC_BTUCF``; every month was between 1,033 and 1,041). Dominion's own figure for a
cycle isn't published. The integration's historical ``ft³ / 100`` is a factor of exactly ``1``, which is Dominion's
rounded comparison-chart figure of 1,000 BTU per cubic foot. Override the default with the ``therms_per_ccf``
argument when you know the factor for a cycle; a gas bill shows the therms and CCF billed, and their ratio is the
factor.
"""

_WH_PER_KWH: Decimal = Decimal(1000)
_FT3_PER_CCF: Decimal = Decimal(100)

# The meter unit each commodity is measured in.
_METER_UNIT_FOR: dict[Commodity, MeterUnit] = {
    Commodity.ELECTRICITY: MeterUnit.WATT_HOUR,
    Commodity.GAS: MeterUnit.CUBIC_FOOT,
}


def to_decimal(value: Decimal | float) -> Decimal:
    """Return *value* as a ``Decimal``. Floats go through ``str`` so ``0.1`` becomes ``Decimal("0.1")``."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


def to_billing_units(
    quantity: Decimal | float,
    unit: MeterUnit,
    plan: RatePlan,
    *,
    therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF,
) -> Decimal:
    """Convert a meter quantity into *plan*'s billing unit: kWh for electric plans, therms for gas plans.

    Args:
        quantity: The amount in *unit*. Negative values (for example solar export) convert the same way.
        unit: The meter unit *quantity* is in.
        plan: The rate plan; its ``commodity`` picks the billing unit.
        therms_per_ccf: Therms per hundred cubic feet, used only for gas.

    Returns:
        The quantity in kWh (electric) or therms (gas).

    Raises:
        ValueError: If *unit* does not measure *plan*'s commodity (for example ``CUBIC_FOOT`` on an electric
            plan).

    """
    expected: MeterUnit = _METER_UNIT_FOR[plan.commodity]
    if unit != expected:
        msg = f"{plan.code} bills {plan.commodity} measured in {expected}, not {unit}"
        raise ValueError(msg)
    amount: Decimal = to_decimal(quantity)
    if unit == MeterUnit.WATT_HOUR:
        return amount / _WH_PER_KWH
    return amount / _FT3_PER_CCF * therms_per_ccf
