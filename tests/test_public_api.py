"""Runtime-introspection guards for the public API.

Python 3.14 evaluates annotations lazily, so a type that is imported only under
``TYPE_CHECKING`` still lets a class be defined, but breaks anything that reads
its annotations at runtime. These tests keep the exported models usable by
serializers and by ``isinstance()`` dispatch.
"""

import dataclasses
import typing

import pytest

import dominionsc
from dominionsc import RATE_1, Charge

_EXPORTED_DATACLASSES = [
    obj for name in dominionsc.__all__ if dataclasses.is_dataclass(obj := getattr(dominionsc, name)) and isinstance(obj, type)
]


@pytest.mark.parametrize("cls", _EXPORTED_DATACLASSES, ids=lambda cls: cls.__name__)
def test_exported_dataclass_type_hints_resolve(cls: type) -> None:
    """Every exported dataclass has annotations that resolve at runtime."""
    hints = typing.get_type_hints(cls)
    assert {f.name for f in dataclasses.fields(cls)} <= hints.keys()


def test_exported_dataclasses_found() -> None:
    """The parametrized test above actually covers the core models."""
    names = {cls.__name__ for cls in _EXPORTED_DATACLASSES}
    assert {"UsageRead", "Forecast", "RegisterReads", "RatePlan", "RateQuote", "UsageCost", "BillingCycle"} <= names


# Names added for the pricing API (docs/PRICING_API_PLAN.md, 0.4.0).
_PRICING_API = [
    "DEFAULT_THERMS_PER_CCF",
    "UTILITY_TIMEZONE",
    "BillingCycle",
    "MeterUnit",
    "NetUsageCost",
    "RateQuote",
    "UsageCost",
    "UsagePricer",
    "billing_cycle_length",
    "estimate_billing_cycles",
    "find_billing_cycle",
    "fixed_charges",
    "price_net_usage",
    "price_usage",
    "rate_at",
    "resolve_plan_for",
    "to_billing_units",
    "utility_local_date",
]


@pytest.mark.parametrize("name", _PRICING_API)
def test_pricing_api_is_exported(name: str) -> None:
    """Each pricing name is in ``__all__`` and importable from the package root."""
    assert name in dominionsc.__all__
    assert getattr(dominionsc, name) is not None


def test_all_names_resolve() -> None:
    """Everything in ``__all__`` exists on the package."""
    missing = [name for name in dominionsc.__all__ if not hasattr(dominionsc, name)]
    assert missing == []


def test_charge_union_supports_isinstance() -> None:
    """``Charge`` is documented for ``isinstance()`` dispatch, so it must be a runtime union."""
    assert RATE_1.charges
    for charge in RATE_1.charges:
        assert isinstance(charge, Charge)
    assert not isinstance(object(), Charge)
