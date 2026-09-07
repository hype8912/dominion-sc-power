"""AMI usage-alert JSON parser.

Pure function -- no network, no aiohttp, no DominionSC dependencies.
Takes the already-decoded JSON payload dict, returns a Forecast object.

See docs/REFACTOR_PLAN.md Phase 3.
"""

from datetime import datetime

from ..exceptions import ApiException
from ..forecast import Forecast


def parse_forecast(payload: dict, url: str | None = None) -> Forecast:
    """Parse a decoded GetAccountAMIUsageAlerts JSON payload into a Forecast.

    Args:
        payload: The already-decoded JSON response dict (i.e. the result of
            json.loads(r1) from _async_get_forecast_internal).
        url: Optional request URL, included in ApiException if parsing fails.

    Returns:
        Forecast dataclass populated from the AMI alert data.

    Raises:
        ApiException: if expected fields are missing or malformed.

    """
    try:
        alert = payload["data"]["amiUsageAlert"]
        start_date = datetime.fromisoformat(alert["currentBillUsageStartDate"]).date()
        end_date = datetime.fromisoformat(alert["currentBillUsageEndDate"]).date()
        current_date = datetime.fromisoformat(alert["currentBillThroughDate"]).date()
        cost_to_date = alert["totalCostUnbilledConsumption"]
        forecasted_cost = round(
            alert["currentCostPerDay"] * alert["numberOfDaysInCurrentBill"],
            2,
        )
        typical_cost = alert["lastYearTotalAmount"] if alert["lastYearAmountExists"] else None
    except Exception as err:
        raise ApiException("Failed to decode forecast data.", url=url) from err

    return Forecast(
        start_date=start_date,
        end_date=end_date,
        current_date=current_date,
        cost_to_date=cost_to_date,
        forecasted_cost=forecasted_cost,
        typical_cost=typical_cost,
    )
