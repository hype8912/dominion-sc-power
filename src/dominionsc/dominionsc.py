"""Backward-compatible import path for dominionsc's core classes.

The actual implementations now live in:
- client.py    -> DominionSC
- auth.py      -> DominionSCTFAHandler, LoginFlow
- transport.py -> DominionSCURLHandler

This module exists so `from dominionsc.dominionsc import ...` keeps
working unchanged for existing callers and tests. See
docs/REFACTOR_PLAN.md Phase 2.
"""

from .auth import DominionSCTFAHandler
from .client import DominionSC
from .transport import DominionSCURLHandler

__all__ = ["DominionSC", "DominionSCTFAHandler", "DominionSCURLHandler"]
