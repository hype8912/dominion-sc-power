"""Rate 7 - Residential Service: Time-of-Use Demand."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, DemandCharge, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, time_of_use_charge

RATE_7: RatePlan = RatePlan(
    code="rate_7",
    name="Rate 7 - Residential Service: Time-of-Use Demand",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2026, 7, 1),
    effective_to=None,
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        time_of_use_charge("0.17441", "0.10124", "0.08841"),
        DemandCharge(
            name="On-Peak Billing Demand",
            price_per_kw=Decimal("10.90"),
            interval_minutes=15,
            qualifying_period="on_peak",
            rolling_interval=True,
        ),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate7.pdf?rev=fc1e5b65b9df4361ba532e8282dc4d68",
)

# Effective for bills rendered on and after July 23, 2025 (PSC Order No. 2021-570). The Basic Facilities Charge
# was $13.00 per month, and the on-peak windows and 15-minute rolling demand interval were unchanged.
RATE_7_2025: RatePlan = RatePlan(
    code="rate_7",
    name="Rate 7 - Residential Service: Time-of-Use Demand",
    commodity=Commodity.ELECTRICITY,
    effective_from=date(2025, 7, 23),
    effective_to=date(2026, 6, 30),
    charges=(
        DailyCharge(name="Basic Facilities Charge", amount=Decimal("0.42740")),
        *ELECTRIC_FIXED_CHARGES,
        time_of_use_charge("0.15983", "0.09161", "0.08372"),
        DemandCharge(
            name="On-Peak Billing Demand",
            price_per_kw=Decimal("9.80"),
            interval_minutes=15,
            qualifying_period="on_peak",
            rolling_interval=True,
        ),
    ),
    adjustments=ELECTRIC_ADJUSTMENTS,
    source_url="https://web.archive.org/web/20260308051539/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate7.pdf?rev=20ac09ccf7124fb286c84e4458a86054&hash=891787487BEA4E645AC36581EDA2AC06",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_7_2025, RATE_7)
