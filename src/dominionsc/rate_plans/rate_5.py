"""Rate 5 - Residential Service: Time of Use."""

from datetime import date, time
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import (
    Commodity,
    DailyCharge,
    RatePlan,
    Season,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
)
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES

RATE_5: RatePlan = RatePlan(
    code="rate_5",
    name="Rate 5 - Residential Service: Time of Use",
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
                        TimeOfUsePeriod("on_peak", Decimal("0.29907"), (TimeWindow(time(16), time(20)),)),
                        TimeOfUsePeriod("super_off_peak", Decimal("0.09623"), (TimeWindow(time(1), time(5)),)),
                        TimeOfUsePeriod("off_peak", Decimal("0.15074"), fallback=True),
                    ),
                    Season.WINTER: (
                        TimeOfUsePeriod("on_peak", Decimal("0.29907"), (TimeWindow(time(6), time(9)),)),
                        TimeOfUsePeriod(
                            "super_off_peak",
                            Decimal("0.09623"),
                            (TimeWindow(time(1), time(5)), TimeWindow(time(12), time(15))),
                        ),
                        TimeOfUsePeriod("off_peak", Decimal("0.15074"), fallback=True),
                    ),
                }
            ),
        ),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate5.pdf?rev=a67167d53f2542c4b67103d5aad1b9e6"
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_5,)
