"""Data models for the dominionsc package.

Exports:
    AccountInfo    - named replacement for the positional [[types], addr] list
    Forecast       - billing forecast data
    UsageRead      - a single interval meter reading
    RegisterReads  - interval readings grouped by meter register (UsagePoint)
    MeterUnit      - the unit a reading's consumption is in (Wh, ft³)
    RatePlan, the Charge variants, and supporting types - declarative tariff
                     models (see rate_plan.py)
"""

from .account import AccountInfo
from .forecast import Forecast
from .rate_plan import (
    Adjustment,
    Charge,
    Commodity,
    DailyCharge,
    DemandCharge,
    EligibilityRule,
    FlatUsageCharge,
    Holiday,
    MonthlyCharge,
    RatePlan,
    Season,
    TieredUsageCharge,
    TimeOfUseCharge,
    TimeOfUsePeriod,
    TimeWindow,
    UsageTier,
    UsageUnit,
)
from .register_reads import RegisterReads
from .units import MeterUnit
from .usage_read import UsageRead

__all__: list[str] = [
    "AccountInfo",
    "Adjustment",
    "Charge",
    "Commodity",
    "DailyCharge",
    "DemandCharge",
    "EligibilityRule",
    "FlatUsageCharge",
    "Forecast",
    "Holiday",
    "MeterUnit",
    "MonthlyCharge",
    "RatePlan",
    "RegisterReads",
    "Season",
    "TieredUsageCharge",
    "TimeOfUseCharge",
    "TimeOfUsePeriod",
    "TimeWindow",
    "UsageRead",
    "UsageTier",
    "UsageUnit",
]
