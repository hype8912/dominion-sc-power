"""Rate 5 - Residential Service: Time of Use."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, time_of_use_charge

RATE_5: RatePlan = RatePlan(
    code="rate_5",
    name="Rate 5 - Residential Service: Time of Use",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        time_of_use_charge("0.29907", "0.15074", "0.09623"),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate5.pdf?rev=a67167d53f2542c4b67103d5aad1b9e6",
)

# The May 2025 tariff (bills rendered on and after the first billing cycle of May 2025; PSC Order Nos. 2025-242,
# 2025-269, and 2025-245) and the July 23, 2025 revision (PSC Order No. 2021-570) publish the same prices, so they
# are one period. The May tariff gives no calendar date, so the first of the month is used.
RATE_5_2025: RatePlan = RatePlan(
    code="rate_5",
    name="Rate 5 - Residential Service: Time of Use",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 5, 1),
    effective_to=date(2026, 6, 30),
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        time_of_use_charge("0.26900", "0.13701", "0.09064"),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20251205175001/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate5.pdf?rev=3e32c127f0434e63a729bdb04e4bb2cc&hash=0D18F5DA9531447A7C88E31E4296C79B",
)

# Superseded tariff periods. The published Basic Facilities Charge was $13.00 per month in all of them (the same
# 0.42740 per day used by the current plan), and the on-peak / off-peak / super-off-peak windows were unchanged.

# Effective for service rendered on and after September 1, 2024 (PSC Order No. 2024-610).
RATE_5_2024: RatePlan = RatePlan(
    code="rate_5",
    name="Rate 5 - Residential Service: Time of Use",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2024, 9, 1),
    effective_to=date(2025, 4, 30),
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        time_of_use_charge("0.26139", "0.12940", "0.08303"),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://etariff.psc.sc.gov/Uploads/tariffFile/0969f054-7572-49cb-89df-9bbff8ce58ea",
)


# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_5_2024, RATE_5_2025, RATE_5)
