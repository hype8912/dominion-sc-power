"""Forecast data model (canonical location: models/forecast.py).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class Forecast:
    """Forecast data for an account. Includes both electric and gas (where applicable)."""

    start_date: date
    end_date: date
    current_date: date
    cost_to_date: float
    forecasted_cost: float
    typical_cost: float
