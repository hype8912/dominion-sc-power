"""Rate 7 - Residential Service: Time-of-Use Demand."""

from datetime import date, time
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import (
    Commodity,
    DailyCharge,
    DemandCharge,
    RatePlan,
    Season,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
)
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES

RATE_7: RatePlan = RatePlan(
    code="rate_7",
    name="Rate 7 - Residential Service: Time-of-Use Demand",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        TimeOfUseCharge(
            name="Energy",
            periods_by_season=MappingProxyType(
                {
                    Season.SUMMER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.17441"), (TimeWindow(time(16), time(20)),)),
                        TimeOfUsePeriod("super_off_peak", Decimal("0.08841"), (TimeWindow(time(1), time(5)),)),
                        TimeOfUsePeriod("off_peak", Decimal("0.10124"), fallback=True),
                    ),
                    Season.WINTER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.17441"), (TimeWindow(time(6), time(9)),)),
                        TimeOfUsePeriod(
                            "super_off_peak",
                            Decimal("0.08841"),
                            (TimeWindow(time(1), time(5)), TimeWindow(time(12), time(15))),
                        ),
                        TimeOfUsePeriod("off_peak", Decimal("0.10124"), fallback=True),
                    ),
                }
            ),
        ),
        DemandCharge(
            name="On-Peak Billing Demand",
            price_per_kw=Decimal("10.90"),
            interval_minutes=15,
            qualifying_period="on_peak",
            rolling_interval=True,
        ),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate7.pdf?rev=fc1e5b65b9df4361ba532e8282dc4d68"
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_7,)
