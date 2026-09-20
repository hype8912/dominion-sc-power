"""Declarative residential rate plans for Dominion Energy South Carolina.

The plan definitions live one per module in ``dominionsc.rate_plans``. This module is the public entry point:
it brings them together into the catalog mappings, the per-code history, and the lookup functions.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from .rate_plans import rate_1, rate_2, rate_5, rate_6, rate_7, rate_8, rate_32s, rate_32v
from .rate_plans.rate_1 import RATE_1
from .rate_plans.rate_2 import RATE_2
from .rate_plans.rate_5 import RATE_5
from .rate_plans.rate_6 import RATE_6, RATE_6_2025
from .rate_plans.rate_7 import RATE_7
from .rate_plans.rate_8 import RATE_8, RATE_8_2025
from .rate_plans.rate_32s import RATE_32S
from .rate_plans.rate_32v import RATE_32V

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from .models.rate_plan import RatePlan

__all__: list[str] = [
    "RATE_1",
    "RATE_2",
    "RATE_5",
    "RATE_6",
    "RATE_6_2025",
    "RATE_7",
    "RATE_8",
    "RATE_8_2025",
    "RATE_32S",
    "RATE_32V",
    "RATE_PLAN_HISTORY",
    "RESIDENTIAL_ELECTRIC_RATE_PLANS",
    "RESIDENTIAL_GAS_RATE_PLANS",
    "RESIDENTIAL_RATE_PLANS",
    "get_available_rate_plans",
    "get_rate_plan",
    "get_rate_plan_for_date",
    "get_rate_plan_history",
]

RESIDENTIAL_ELECTRIC_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {plan.code: plan for plan in (RATE_1, RATE_2, RATE_5, RATE_6, RATE_7, RATE_8)}
)
RESIDENTIAL_GAS_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType({plan.code: plan for plan in (RATE_32S, RATE_32V)})
RESIDENTIAL_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {**RESIDENTIAL_ELECTRIC_RATE_PLANS, **RESIDENTIAL_GAS_RATE_PLANS}
)

# Every known tariff period per plan code, ascending by ``effective_from`` (the last entry is the current plan).
# Each plan module supplies its own ``HISTORY``; plans with no superseded periods have a single entry.
RATE_PLAN_HISTORY: Mapping[str, tuple[RatePlan, ...]] = MappingProxyType(
    {
        history[-1].code: history
        for history in (
            rate_1.HISTORY,
            rate_2.HISTORY,
            rate_5.HISTORY,
            rate_6.HISTORY,
            rate_7.HISTORY,
            rate_8.HISTORY,
            rate_32s.HISTORY,
            rate_32v.HISTORY,
        )
    }
)


def get_rate_plan(code: str) -> RatePlan | None:
    """Return a residential rate plan by code, or ``None`` when unknown."""
    return RESIDENTIAL_RATE_PLANS.get(code)


def get_available_rate_plans() -> tuple[RatePlan, ...]:
    """Return all currently cataloged residential rate plans."""
    return tuple(RESIDENTIAL_RATE_PLANS.values())


def get_rate_plan_history(code: str) -> tuple[RatePlan, ...]:
    """Return every known tariff period for a rate code, oldest first.

    The last entry is the current plan (the one ``get_rate_plan`` returns).
    Returns an empty tuple when the code is unknown.
    """
    return RATE_PLAN_HISTORY.get(code, ())


def get_rate_plan_for_date(code: str, on: date) -> RatePlan | None:
    """Return the plan for *code* that was in effect on *on*.

    Returns ``None`` when the code is unknown or *on* falls before the earliest
    recorded tariff period (or in a gap between periods).
    """
    for plan in get_rate_plan_history(code):
        if plan.effective_from <= on and (plan.effective_to is None or on <= plan.effective_to):
            return plan
    return None
