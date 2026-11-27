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
    assert {"UsageRead", "Forecast", "RegisterReads", "RatePlan"} <= names


def test_charge_union_supports_isinstance() -> None:
    """``Charge`` is documented for ``isinstance()`` dispatch, so it must be a runtime union."""
    assert RATE_1.charges
    for charge in RATE_1.charges:
        assert isinstance(charge, Charge)
    assert not isinstance(object(), Charge)
