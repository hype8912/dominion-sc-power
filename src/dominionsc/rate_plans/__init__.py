"""One module per residential rate plan.

Each ``rate_*`` module defines the plan's current ``RATE_*`` constant, any archived earlier periods, and a
``HISTORY`` tuple of every known period (oldest first, ending with the current plan). Values shared by several
plans live in ``_common``. ``dominionsc.rates`` imports these modules and assembles the public catalog, mappings,
and lookup functions; import plans from there (or from ``dominionsc``), not from this package.

Electric tariffs publish the Basic Facilities Charge per month, but it is stored as a ``DailyCharge``. The daily
amount is the monthly one times 12 divided by 365, to five decimals: $9.00 -> 0.29589, $9.50 -> 0.31233,
$11.00 -> 0.36164, $13.00 -> 0.42740.
"""
