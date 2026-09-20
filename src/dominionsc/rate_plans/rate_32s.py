"""Rate 32S - Gas Residential Standard Service."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, FlatUsageCharge, MonthlyCharge, RatePlan, UsageUnit
from ._common import GAS_ADJUSTMENTS

RATE_32S: RatePlan = RatePlan(
    code="rate_32s",
    name="Rate 32S - Gas Residential Standard Service",
    commodity=Commodity.GAS,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("2.04149")),
    ),
    adjustments=GAS_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/rates/rate32s.pdf?rev=4498fa411c8d4bd2a440ba808162354a",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_32S,)
