"""Rate 1 - Residential Service: Good Cents Rate."""

from datetime import date
from decimal import Decimal

from ..models.rate_plan import Commodity, DailyCharge, EligibilityRule, RatePlan
from ._common import ELECTRIC_ADJUSTMENTS, ELECTRIC_FIXED_CHARGES, seasonal_tiers

_ELIGIBILITY_RULES: tuple[EligibilityRule, ...] = (
    EligibilityRule(
        "closed_to_new_customers",
        "Closed effective January 15, 1996; not available to any new structure. "
        "Only dwellings already certified and receiving service under this schedule may remain on it.",
    ),
    EligibilityRule(
        "good_cents_certification",
        "The dwelling unit must be certified by the Company to meet or exceed the Good Cents "
        "Program requirements in force at the time of application.",
    ),
)

RATE_1: RatePlan = RatePlan(
    code="rate_1",
    name="Rate 1 - Residential Service: Good Cents Rate",
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
    source_url="https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate1.pdf?rev=aca16c10aadb414cb66ec43abf8809a6",
)

# Effective for bills rendered on and after July 23, 2025 (PSC Order No. 2021-570). The Basic Facilities Charge
# was $9.00 per month.
RATE_1_2025: RatePlan = RatePlan(
    code="rate_1",
    name="Rate 1 - Residential Service: Good Cents Rate",
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
    source_url="https://web.archive.org/web/20260307001402/https://cdn-dominionenergy-prd-001.azureedge.net/-/media/content/rates-and-tariffs/pdfs/south-carolina/electric/rates/rate1.pdf?hash=6CCA8572476FAD5398920AF012844E30&rev=ab28beafa92e49b99cd949aeaa9396a0",
)

# Every known period, oldest first, ending with the current plan.
HISTORY: tuple[RatePlan, ...] = (RATE_1_2025, RATE_1)
