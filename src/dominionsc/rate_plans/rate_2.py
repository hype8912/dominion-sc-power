"""Rate 2 - Low Use Residential Service."""

from datetime import date
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import Commodity, DailyCharge, EligibilityRule, FlatUsageCharge, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES

RATE_2: RatePlan = RatePlan(
    code="rate_2",
    name="Rate 2 - Low Use Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *ELECTRIC_FIXED_CHARGES,
        FlatUsageCharge(name="Energy", price_per_unit=Decimal("0.13111")),
    ),
    eligibility_rules=(
        EligibilityRule(
            "preceding_billing_periods_below_threshold",
            "Usage must not exceed 400 kWh in each of the preceding twelve billing periods.",
            MappingProxyType({"period_count": 12, "usage_threshold": Decimal("400"), "usage_unit": "kWh"}),
        ),
        EligibilityRule("second_exceedance_terminates", "The second billing period exceeding 400 kWh terminates eligibility."),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate2.pdf?rev=af6e0117a2214ef1858d977ab7b7b7b3"
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_2,)
