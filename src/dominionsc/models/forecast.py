"""Forecast data model (canonical location: models/forecast.py).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class Forecast:
    """Bill forecast for the current monthly billing period.

    Populated from Dominion Energy SC's ``GetAccountAMIUsageAlerts`` API
    endpoint. The forecast combines electric and gas (where the account has
    both) into a single combined dollar amount.

    Attributes:
        start_date: First day of the current billing period.
        end_date: Last day (projected) of the current billing period.
        current_date: The most recent date through which usage has been
            included in ``cost_to_date`` (typically 1-2 days behind real time
            due to metering latency).
        cost_to_date: Actual dollar cost accrued from ``start_date``
            through ``current_date``.
        forecasted_cost: Projected total dollar cost for the entire billing
            period, calculated as ``currentCostPerDay * numberOfDaysInCurrentBill``.
        typical_cost: Last year's total dollar cost for the equivalent billing
            period, or ``None`` if no prior-year data is available. Useful as
            a year-over-year comparison baseline.

    Example::

        forecast = await client.async_get_forecast()
        print(f"Bill period: {forecast.start_date} - {forecast.end_date}")
        print(f"Spent so far: ${forecast.cost_to_date:.2f}")
        print(f"Projected total: ${forecast.forecasted_cost:.2f}")
        if forecast.typical_cost is not None:
            delta = forecast.forecasted_cost - forecast.typical_cost
            print(f"vs. last year: {delta:+.2f}")

    """

    start_date: date
    end_date: date
    current_date: date
    cost_to_date: float
    forecasted_cost: float
    typical_cost: float | None
