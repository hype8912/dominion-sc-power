"""RegisterReads data model.

Groups a set of interval readings by the physical meter register
(ESPI UsagePoint) they came from. A single Green Button response for
one measurement type (e.g. ELECTRIC) can contain multiple UsagePoints
-- for a net-metered solar account, one register meters grid delivery
and another meters solar export. These are separate billed meters and
must not be flattened together.

The library stays unopinionated: it does NOT decide which register is
"grid" vs "solar", and it preserves reading signs exactly as reported
(a solar-export register may carry negative values). Consumers decide
how to interpret each register, keyed on the stable usage_point_id.

See docs/REFACTOR_PLAN.md and the multi-register work.
"""

from dataclasses import dataclass, field

from .usage_read import UsageRead


@dataclass
class RegisterReads:
    """Interval readings for a single meter register (ESPI UsagePoint)."""

    usage_point_id: str
    """Stable ESPI UsagePoint identifier, verified constant across requests.

    Suitable as a durable key for downstream statistic IDs -- confirmed
    unchanged across separate exports months apart.
    """

    flow_direction: str | None = None
    """ESPI flowDirection from the register's ReadingType, if present.

    NOTE: observed unreliable for Dominion Energy SC (both grid and solar
    registers report flowDirection=1), so consumers should NOT depend on
    this to distinguish registers. Preserved for consumers of other
    utilities where it may be populated correctly.
    """

    reads: list[UsageRead] = field(default_factory=list)
    """Interval readings for this register, in the order encountered."""
