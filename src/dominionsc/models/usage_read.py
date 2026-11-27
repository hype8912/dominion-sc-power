"""UsageRead data model (canonical location: models/usage_read.py).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from dataclasses import dataclass
from datetime import datetime

from .units import MeterUnit


@dataclass
class UsageRead:
    """A single interval meter reading with a consumption value.

    Each instance represents one time-window of energy usage as reported by
    Bidgely's Green Button ESPI endpoint. The interval length is determined
    by the meter configuration -- Dominion Energy SC reports 15-minute
    intervals for electric accounts and hourly intervals for gas.

    Attributes:
        start_time: Timezone-aware start of the measurement interval.
        end_time: Timezone-aware end of the measurement interval (inclusive,
            one second before the next interval's ``start_time``).
        consumption: Energy or volume consumed during the interval, in
            ``unit``:

            - **Electric**: Watt-hours (Wh).
            - **Gas**: Cubic feet (ft³).

            Use ``dominionsc.to_billing_units`` to convert to the plan's
            billing unit (kWh or therm), or ``dominionsc.price_usage`` to
            price it directly.

            Solar-export registers carry **negative** values representing
            energy pushed back to the grid.
        unit: The unit ``consumption`` is in, from the feed's ``espi:uom``.
            ``None`` when the feed doesn't declare a unit the library
            recognizes.

    Example::

        from dominionsc.models.usage_read import UsageRead
        from datetime import datetime, timezone

        read = UsageRead(
            start_time=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, 12, 14, 59, tzinfo=timezone.utc),
            consumption=350.0,  # 350 Wh = 0.35 kWh in 15 minutes
            unit=MeterUnit.WATT_HOUR,
        )

    """

    start_time: datetime
    end_time: datetime
    consumption: float
    unit: MeterUnit | None = None
