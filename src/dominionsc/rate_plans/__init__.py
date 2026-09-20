"""One module per residential rate plan.

Each ``rate_*`` module defines the plan's current ``RATE_*`` constant, any archived earlier periods, and a
``HISTORY`` tuple of every known period (oldest first, ending with the current plan). Values shared by several
plans live in ``_common``. ``dominionsc.rates`` imports these modules and assembles the public catalog, mappings,
and lookup functions; import plans from there (or from ``dominionsc``), not from this package.
"""
