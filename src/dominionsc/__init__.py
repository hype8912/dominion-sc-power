"""dominionsc: async Python library for Dominion Energy South Carolina usage data.

This package provides an async Python client for retrieving historical and
forecasted energy usage and cost data from Dominion Energy South Carolina's
customer portal (``account.dominionenergysc.com``) and the Bidgely energy
analytics API (``desc-prodapi.bidgely.com``).

Quick start::

    import asyncio
    import aiohttp
    from datetime import datetime, timedelta
    from dominionsc import DominionSC, MfaChallenge, create_cookie_jar

    async def main():
        async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
            client = DominionSC(session, "your_username", "your_password")
            try:
                await client.async_login()
            except MfaChallenge as challenge:
                # Handle MFA interactively -- see README for full example
                handler = challenge.handler
                options = await handler.async_get_tfa_options()
                await handler.async_select_tfa_option(list(options)[0])
                login_data = await handler.async_submit_tfa_code(input("Code: "))
                client.login_data = login_data
                await client.async_login()

            forecast = await client.async_get_forecast()
            print(f"Forecasted bill: ${forecast.forecasted_cost:.2f}")

            measurement_types, address = await client.async_get_accounts()
            start = datetime.now() - timedelta(days=7)
            end = datetime.now()
            for service in measurement_types:  # "ELECTRIC" or "GAS"
                registers = await client.async_get_register_reads(service, start, end)
                for reg in registers:
                    for read in reg.reads:
                        print(f"{service}/{reg.usage_point_id}: {read.consumption}")

    asyncio.run(main())

Public surface
--------------
The stable public API is everything listed in ``__all__`` below. Import
directly from ``dominionsc``::

    from dominionsc import DominionSC, Forecast, UsageRead, MfaChallenge

See the README for detailed usage, the ``docs/`` directory for architecture
and API reference documentation, and ``CONTRIBUTING.md`` for contributor
setup instructions.
"""

from .dominionsc import DominionSC, DominionSCTFAHandler
from .exceptions import ApiException, CannotConnect, InvalidAuth, MfaChallenge
from .helpers import create_cookie_jar
from .models.forecast import Forecast
from .models.rate_plan import (
    Adjustment,
    Charge,
    Commodity,
    DailyCharge,
    DemandCharge,
    EligibilityRule,
    FlatUsageCharge,
    MonthlyCharge,
    RatePlan,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
    UsageTier,
    UsageUnit,
)
from .models.usage_read import UsageRead
from .rates import (
    RATE_2,
    RATE_5,
    RATE_6,
    RATE_7,
    RATE_8,
    RATE_32S,
    RATE_32V,
    RESIDENTIAL_ELECTRIC_RATE_PLANS,
    RESIDENTIAL_GAS_RATE_PLANS,
    RESIDENTIAL_RATE_PLANS,
    get_available_rate_plans,
    get_rate_plan,
)

__all__ = [
    "RATE_2",
    "RATE_5",
    "RATE_6",
    "RATE_7",
    "RATE_8",
    "RATE_32S",
    "RATE_32V",
    "RESIDENTIAL_ELECTRIC_RATE_PLANS",
    "RESIDENTIAL_GAS_RATE_PLANS",
    "RESIDENTIAL_RATE_PLANS",
    "Adjustment",
    "ApiException",
    "CannotConnect",
    "Charge",
    "Commodity",
    "DailyCharge",
    "DemandCharge",
    "DominionSC",
    "DominionSCTFAHandler",
    "EligibilityRule",
    "FlatUsageCharge",
    "Forecast",
    "InvalidAuth",
    "MfaChallenge",
    "MonthlyCharge",
    "RatePlan",
    "Season",
    "TieredUsageCharge",
    "TimeOfUseCharge",
    "TimeOfUsePeriod",
    "TimeWindow",
    "UsageRead",
    "UsageTier",
    "UsageUnit",
    "create_cookie_jar",
    "get_available_rate_plans",
    "get_rate_plan",
]
