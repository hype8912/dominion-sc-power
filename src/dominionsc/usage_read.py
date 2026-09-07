"""Backward-compatible re-export shim.

UsageRead has moved to models/usage_read.py. This shim keeps
``from dominionsc.usage_read import UsageRead`` working for existing callers
(tests, ha-dominion-sc, downstream code).

See docs/REFACTOR_PLAN.md Phase 4.
"""

from .models.usage_read import UsageRead

__all__ = ["UsageRead"]
