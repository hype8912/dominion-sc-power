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

# Effective for bills rendered on and after the 1st billing cycle of September 2025. The tariff gives no calendar
# date, so the first of the month is used. The Basic Facilities Charge was unchanged at $10.90 per month; the
# published gas cost component was $1.10619 per therm and DSM $0.00210 per therm, both already included in the
# energy charge below.
RATE_32S_2025: RatePlan = RatePlan(
    code="rate_32s",
    name="Rate 32S - Gas Residential Standard Service",
    commodity=Commodity.GAS,
    effective_from=date(2025, 9, 1),
    effective_to=date(2026, 6, 30),
    charges=(
        MonthlyCharge(name="Basic Facilities Charge", amount=Decimal("10.90")),
        FlatUsageCharge(name="Energy", usage_unit=UsageUnit.THERM, price_per_unit=Decimal("1.81026")),
    ),
    adjustments=GAS_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20250920084814/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/natural-gas/rates/rate32s.ashx?rev=-1&hash=6AF3536E6D28E72F16E86653D28CFF62",
)

# Every known period, oldest first, ending with the current plan. Dates before 2025-09-01 resolve to None.
HISTORY: tuple[RatePlan, ...] = (RATE_32S_2025, RATE_32S)
