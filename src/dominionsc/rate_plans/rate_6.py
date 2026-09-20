"""Rate 6 - Residential Service: Energy Saver/Conservation Rate."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, EligibilityRule, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, seasonal_tiers

_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    EligibilityRule(
        "energy_conservation_requirements",
        "The dwelling must satisfy the published insulation, equipment, and efficiency requirements.",
    ),
)

RATE_6: RatePlan = RatePlan(
    code="rate_6",
    name="Rate 6 - Residential Service: Energy Saver/Conservation Rate",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *ELECTRIC_FIXED_CHARGES,
        seasonal_tiers("0.15333", "0.16842", "0.15333", "0.14729"),
    ),
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate6.pdf?rev=64b90aac474744098247aa6daf78c5a3",
)

# Effective for bills rendered on and after July 23, 2025 (PSC Order No. 2021-570). The Basic Facilities Charge
# was $9.00 per month.
RATE_6_2025: RatePlan = RatePlan(
    code="rate_6",
    name="Rate 6 - Residential Service: Energy Saver/Conservation Rate",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 7, 23),
    effective_to=date(2026, 6, 30),
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.29589")),
        *ELECTRIC_FIXED_CHARGES,
        seasonal_tiers("0.14164", "0.15505", "0.14164", "0.13628"),
    ),
    eligibility_rules=_ELIGIBILITY_RULES,
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20250920065222/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate6.pdf?rev=ab5a34bf37ca4877849498452f19d0b7&hash=E5DB93C6660924E651A2BCC506AB920B",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_6_2025, RATE_6)
