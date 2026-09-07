"""Usage read data model."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class UsageRead:
    """A read from the meter that has consumption data."""

    start_time: datetime
    end_time: datetime
    consumption: float  # units: Wh or Ft^3
