"""Rate 32V - Gas Residential Value Service."""

from datetime import date
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import Commodity, EligibilityRule, FlatUsageCharge, MonthlyCharge, RatePlan, UsageUnit
from ._common import GAS_ADJUSTMENTS

_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    EligibilityRule(
        "summer_average_minimum",
        "Average usage during June, July, and August must be at least 10 therms.",
        MappingProxyType({"months": "6,7,8", "minimum_usage": Decimal("10"), "usage_unit": "therm"}),
    ),
    EligibilityRule("annual_reassignment", "Accounts not meeting the standard are placed on Rate 32S beginning in November."),
)

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
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=GAS_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/rates/rate32v.pdf?rev=4a6876e2c4d04ded811832c64c96c4db",
)

# Effective for bills rendered on and after the 1st billing cycle of September 2025. The tariff gives no calendar
# date, so the first of the month is used.
RATE_32V_2025: RatePlan = RatePlan(
    code="rate_32v",
    name="Rate 32V - Gas Residential Value Service",
    commodity=Commodity.GAS,
    effective_from=date(2025, 9, 1),
    effective_to=date(2026, 6, 30),
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("1.71886")),
    ),
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=GAS_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20250920065232/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/rates/rate32v.pdf?rev=8ce91c8612fb4ce0bd9d4b63abaf5aab&hash=ADA329E56B8CEA3479F5AB4318E67934",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_32V_2025, RATE_32V)
