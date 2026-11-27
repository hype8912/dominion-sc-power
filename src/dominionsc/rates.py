"""Declarative residential rate plans for Dominion Energy South Carolina.

The plan definitions live one per module in ``dominionsc.rate_plans``. This module is the public entry point:
it brings them together into the catalog mappings, the per-code history, and the lookup functions.
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING

from .local_time import utility_local_date
from .rate_plans import rate_1, rate_2, rate_5, rate_6, rate_7, rate_8, rate_32s, rate_32v
from .rate_plans.rate_1 import RATE_1, RATE_1_2025
from .rate_plans.rate_2 import RATE_2, RATE_2_2025
from .rate_plans.rate_5 import RATE_5, RATE_5_2024, RATE_5_2025
from .rate_plans.rate_6 import RATE_6, RATE_6_2025
from .rate_plans.rate_7 import RATE_7, RATE_7_2025
from .rate_plans.rate_8 import RATE_8, RATE_8_2025
from .rate_plans.rate_32s import RATE_32S, RATE_32S_2025
from .rate_plans.rate_32v import RATE_32V, RATE_32V_2025

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from .models.rate_plan import RatePlan

__all__: list[str] = [
    "RATE_1",
    "RATE_1_2025",
    "RATE_2",
    "RATE_2_2025",
    "RATE_5",
    "RATE_5_2024",
    "RATE_5_2025",
    "RATE_6",
    "RATE_6_2025",
    "RATE_7",
    "RATE_7_2025",
    "RATE_8",
    "RATE_8_2025",
    "RATE_32S",
    "RATE_32S_2025",
    "RATE_32V",
    "RATE_32V_2025",
    "RATE_PLAN_HISTORY",
    "RESIDENTIAL_ELECTRIC_RATE_PLANS",
    "RESIDENTIAL_GAS_RATE_PLANS",
    "RESIDENTIAL_RATE_PLANS",
    "get_available_rate_plans",
    "get_rate_plan",
    "get_rate_plan_for_date",
    "get_rate_plan_history",
    "resolve_plan_for",
]

# Catalogs of the *current* period of each plan, keyed by plan code. Wrapped in
# MappingProxyType so callers cannot mutate the shared module-level catalog.
RESIDENTIAL_ELECTRIC_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {plan.code: plan for plan in (RATE_1, RATE_2, RATE_5, RATE_6, RATE_7, RATE_8)}
)
"""Current residential electric plans, keyed by code (e.g. ``"rate_8"``)."""

RESIDENTIAL_GAS_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType({plan.code: plan for plan in (RATE_32S, RATE_32V)})
"""Current residential gas plans, keyed by code (e.g. ``"rate_32s"``)."""

RESIDENTIAL_RATE_PLANS: Mapping[str, RatePlan] = MappingProxyType(
    {**RESIDENTIAL_ELECTRIC_RATE_PLANS, **RESIDENTIAL_GAS_RATE_PLANS}
)
"""All current residential plans (electric and gas), keyed by code."""

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
    # Both ends are inclusive; an open-ended (current) period has effective_to=None.
    for plan in get_rate_plan_history(code):
        if plan.effective_from <= on and (plan.effective_to is None or on <= plan.effective_to):
            return plan
    return None


def resolve_plan_for(plan: RatePlan, when: datetime | date) -> RatePlan | None:
    """Return the tariff period of *plan* in effect at *when*, or ``None`` when none is.

    Pass any period of a plan (usually the current one, such as ``RATE_8``) and this returns the period that
    applied at *when*, so pricing a 2025 date with ``RATE_5`` uses ``RATE_5_2025``'s prices and rules.

    - **Catalog plans** (``plan.code`` has a history in ``RATE_PLAN_HISTORY``): the catalog period in effect
      on *when*'s local date, from ``get_rate_plan_for_date``. The catalog is authoritative for its codes, so
      the period returned may be a different object from *plan*.
    - **Other plans**: *plan* itself when the local date is within ``effective_from`` to ``effective_to``
      (both inclusive), otherwise ``None``.

    Args:
        plan: Any period of the plan to resolve.
        when: A ``datetime`` (naive values are read as local time, aware values are converted to
            ``America/New_York``) or a ``date``, which is used as is.

    Returns:
        The ``RatePlan`` in effect, or ``None`` before the earliest known period or in a gap between periods.

    """
    day: date = utility_local_date(when) if isinstance(when, datetime) else when
    if get_rate_plan_history(plan.code):
        return get_rate_plan_for_date(plan.code, day)
    if plan.effective_from <= day and (plan.effective_to is None or day <= plan.effective_to):
        return plan
    return None
