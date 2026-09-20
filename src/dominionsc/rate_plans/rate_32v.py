"""Rate 32V - Gas Residential Value Service."""

from datetime import date
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import Commodity, EligibilityRule, FlatUsageCharge, MonthlyCharge, RatePlan, UsageUnit
from ._common import GAS_ADJUSTMENTS

RATE_32V: RatePlan = RatePlan(
    code="rate_32v",
    name="Rate 32V - Gas Residential Value Service",
    commodity=Commodity.GAS,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("1.91847")),
    ),
    eligibility_rules=(
        EligibilityRule(
            "summer_average_minimum",
            "Average usage during June, July, and August must be at least 10 therms.",
            MappingProxyType({"months": "6,7,8", "minimum_usage": Decimal("10"), "usage_unit": "therm"}),
        ),
        EligibilityRule(
            "annual_reassignment", "Accounts not meeting the standard are placed on Rate 32S beginning in November."
        ),
    ),
    adjustments=GAS_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/rates/rate32v.pdf?rev=4a6876e2c4d04ded811832c64c96c4db"
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_32V,)
