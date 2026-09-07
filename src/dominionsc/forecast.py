"""Backward-compatible re-export shim.

Forecast has moved to models/forecast.py. This shim keeps
``from dominionsc.forecast import Forecast`` working for existing callers
(tests, ha-dominion-sc, downstream code).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from .models.forecast import Forecast

__all__ = ["Forecast"]
