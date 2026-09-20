"""Rate 8 - Residential Service."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, seasonal_tiers

RATE_8: RatePlan = RatePlan(
    code="rate_8",
    name="Rate 8 - Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.36164")),
        *ELECTRIC_FIXED_CHARGES,
        seasonal_tiers("0.15878", "0.17442", "0.15878", "0.15253"),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate8.pdf?rev=64972c8dc44e46b4805ec08a9a03e43b"
)

# Superseded tariff period. It carries only the usage charge: the fixed daily/monthly charges in force at the
# time were not recorded, so none are defined here.
RATE_8_2025: RatePlan = RatePlan(
    code="rate_8",
    name="Rate 8 - Residential Service",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 7, 23),
    effective_to=date(2026, 6, 30),
    charges=(seasonal_tiers("0.14599", "0.15983", "0.14599", "0.14045"),),
    adjustments=ELECTRIC_ADJUSTMENTS,
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_8_2025, RATE_8)
