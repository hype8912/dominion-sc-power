"""Rate 6 - Residential Service: Energy Saver/Conservation Rate."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, EligibilityRule, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, seasonal_tiers

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
    eligibility_rules=(
        EligibilityRule(
            "energy_conservation_requirements",
            "The dwelling must satisfy the published insulation, equipment, and efficiency requirements.",
        ),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate6.pdf?rev=64b90aac474744098247aa6daf78c5a3"
)

# Superseded tariff period. It carries only the usage charge: the fixed daily/monthly charges in force at the
# time were not recorded, so none are defined here.
RATE_6_2025: RatePlan = RatePlan(
    code="rate_6",
    name="Rate 6 - Residential Service: Energy Saver/Conservation Rate",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 7, 23),
    effective_to=date(2026, 6, 30),
    charges=(seasonal_tiers("0.14164", "0.15505", "0.14164", "0.13628"),),
    adjustments=ELECTRIC_ADJUSTMENTS,
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_6_2025, RATE_6)
