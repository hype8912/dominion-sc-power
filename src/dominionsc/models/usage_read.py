"""UsageRead data model (canonical location: models/usage_read.py).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class UsageRead:
    """A read from the meter that has consumption data."""

    start_time: datetime
    end_time: datetime
    consumption: float  # units: Wh or Ft^3
