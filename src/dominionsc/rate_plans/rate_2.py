"""Rate 2 - Low Use Residential Service."""

from datetime import date
from decimal import Decimal
from types import MappingProxyType

from ..models.rate_plan import Commodity, DailyCharge, EligibilityRule, FlatUsageCharge, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES

_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    EligibilityRule(
        "preceding_billing_periods_below_threshold",
        "Usage must not exceed 400 kWh in each of the preceding twelve billing periods.",
        MappingProxyType({"period_count": 12, "usage_threshold": Decimal("400"), "usage_unit": "kWh"}),
    ),
    EligibilityRule("second_exceedance_terminates", "The second billing period exceeding 400 kWh terminates eligibility."),
)

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
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate2.pdf?rev=af6e0117a2214ef1858d977ab7b7b7b3",
)

# Effective for bills rendered on and after July 23, 2025 (PSC Order No. 2021-570). The Basic Facilities Charge
# was $9.00 per month.
RATE_2_2025: RatePlan = RatePlan(
    code="rate_2",
    name="Rate 2 - Low Use Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 7, 23),
    effective_to=date(2026, 6, 30),
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.29589")),
        *ELECTRIC_FIXED_CHARGES,
        FlatUsageCharge(name="Energy", price_per_unit=Decimal("0.12445")),
    ),
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20260308123527/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate2.pdf?rev=8e506986e8b24f10aed642402c943be0&hash=2E00C47C49AFCA66DD1C181887D1FAEB",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_2_2025, RATE_2)
