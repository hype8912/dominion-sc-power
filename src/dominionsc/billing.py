"""Billing-cycle estimation, and pricing a stream of reads across billing cycles.

Dominion Energy SC does not expose historical billing-cycle boundaries. The current cycle's start and end
dates are available from the forecast (``DominionSC.async_get_forecast``), and earlier or later cycles are
*estimated* from that single anchor using the observed meter-read schedule (see
:func:`billing_cycle_length`).

Why this matters
----------------
Tiered plans (Rates 1, 6 and 8) reset their tiers each billing cycle: the first 800 kWh of each cycle is
billed at one price and the rest at another. Pricing historical usage correctly needs to know which cycle
each interval belongs to, so the cycle-to-date usage counter can be reset at each boundary.
:class:`UsagePricer` does that bookkeeping.

Accuracy
--------
The cycle-length table is based on observed cycle lengths and approximates the actual meter-read schedule.
It is accurate enough for cost estimation but is not ground truth: real cycle boundaries may differ by a day
or two, so costs near a boundary may be split between tiers slightly differently from the bill.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from .local_time import to_utility_local
from .models.forecast import Forecast
from .models.rate_plan import DailyCharge, MonthlyCharge
from .pricing import _price_billing_units, _price_net_billing_units
from .rates import resolve_plan_for
from .units import DEFAULT_THERMS_PER_CCF, to_billing_units

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .models.rate_plan import RatePlan
    from .models.units import MeterUnit
    from .pricing import NetUsageCost, UsageCost

__all__: list[str] = [
    "BillingCycle",
    "UsagePricer",
    "billing_cycle_length",
    "estimate_billing_cycles",
    "find_billing_cycle",
    "fixed_charges",
]

_LOGGER = logging.getLogger(__name__)

# Observed billing-cycle lengths by the month the cycle starts in. April and June depend on leap years and
# are handled in billing_cycle_length.
_CYCLE_LENGTHS: dict[int, int] = {1: 30, 2: 31, 3: 30, 5: 30, 7: 30, 8: 31, 9: 31, 10: 30, 11: 31, 12: 30}


@dataclass(frozen=True, slots=True)
class BillingCycle:
    """One billing cycle.

    Attributes:
        start: First day of the cycle.
        end: Last day of the cycle (inclusive).

    """

    start: date
    end: date

    def contains(self, day: date) -> bool:
        """Return whether *day* falls within this cycle (both ends inclusive)."""
        return self.start <= day <= self.end


def billing_cycle_length(start: date) -> int:
    """Return the estimated number of days in the billing cycle that starts on *start*.

    Dominion's meter-read schedule gives cycles of different lengths depending on the month. By the month
    the cycle starts in:

        Jan=30, Feb=31, Mar=30, Apr=31*, May=30, Jun=30†, Jul=30,
        Aug=31, Sep=31, Oct=30, Nov=31, Dec=30

        * April: 31 if this year or next year is a leap year, else 30.
        † June:  30 if this year or next year is a leap year, else 31.
    """
    length: int | None = _CYCLE_LENGTHS.get(start.month)
    if length is not None:
        return length
    near_leap: bool = calendar.isleap(start.year) or calendar.isleap(start.year + 1)
    if start.month == 4:
        return 31 if near_leap else 30
    return 30 if near_leap else 31  # June


def estimate_billing_cycles(
    anchor: BillingCycle | Forecast,
    earliest: date,
    latest: date | None = None,
) -> tuple[BillingCycle, ...]:
    """Estimate every billing cycle from *earliest* up to the anchor cycle, and on to *latest*.

    Algorithm:
        1. From the anchor's start, step back one cycle at a time (using the length of the previous month's
           cycle) until reaching or passing *earliest*.
        2. Each estimated cycle ends the day before the next one starts.
        3. The anchor itself is included as given.
        4. If *latest* is after the anchor's end, step forward from the day after the anchor ends to cover
           *latest*. This handles a stale forecast whose cycle has already ended.

    Args:
        anchor: A known cycle, usually the current one. A ``Forecast`` uses its ``start_date`` and
            ``end_date``.
        earliest: Cover back to at least this date.
        latest: Cover forward to at least this date, or ``None`` to stop at the anchor.

    Returns:
        The cycles, oldest first. Always includes the anchor.

    """
    if isinstance(anchor, Forecast):
        anchor = BillingCycle(anchor.start_date, anchor.end_date)

    starts: list[date] = [anchor.start]
    current: date = anchor.start
    while current > earliest:
        previous_month: int = current.month - 1 or 12
        previous_year: int = current.year - (1 if current.month == 1 else 0)
        current -= timedelta(days=billing_cycle_length(date(previous_year, previous_month, 1)))
        starts.append(current)
    starts.reverse()

    cycles: list[BillingCycle] = [BillingCycle(starts[i], starts[i + 1] - timedelta(days=1)) for i in range(len(starts) - 1)]
    cycles.append(anchor)

    if latest is not None and latest > anchor.end:
        _LOGGER.debug("Billing cycle %s - %s is stale; projecting forward to cover %s", anchor.start, anchor.end, latest)
        current = anchor.end + timedelta(days=1)
        while current <= latest:
            end: date = current + timedelta(days=billing_cycle_length(current) - 1)
            cycles.append(BillingCycle(current, end))
            current = end + timedelta(days=1)

    return tuple(cycles)


def find_billing_cycle(day: date, cycles: Sequence[BillingCycle]) -> BillingCycle | None:
    """Return the cycle in *cycles* that contains *day*, or ``None`` if none does."""
    return next((cycle for cycle in cycles if cycle.contains(day)), None)


def _is_before(local: datetime, previous: datetime) -> bool:
    """Return whether *local* is earlier than *previous* both as an instant and on the local wall clock.

    Requiring both lets either labelling of the hours around a DST change through: a stream stepping in real
    time repeats wall-clock times at fall-back, and Green Button feeds sorted by wall clock carry times that
    don't exist (such as 02:45 on spring-forward day), which sit after the next hour as instants.
    """
    return local.timestamp() < previous.timestamp() and local.replace(tzinfo=None) < previous.replace(tzinfo=None)


def fixed_charges(plan: RatePlan, cycle: BillingCycle) -> Decimal:
    """Return the fixed (non-usage) charges for one billing cycle of *plan*, in dollars.

    - ``DailyCharge`` (electric Basic Facilities Charge): the daily amount for each day of the cycle, using the
      tariff period in effect on that day. Both ``cycle.start`` and ``cycle.end`` count.
    - ``MonthlyCharge`` (the electric Distributed Energy Resource Program charge and the gas Basic Facilities
      Charge): once per cycle, whatever the cycle's length or the usage. "Month" means one billing cycle. The
      amount comes from the tariff period in effect on the cycle's last day, the day the bill is rendered.

    Days with no tariff period in effect cost nothing, like ``price_usage``. Usage charges and the Rate 7 demand
    charge are not included.

    This is an estimate. The cycle's boundaries are usually estimated (see ``estimate_billing_cycles``) and may
    be a day or two off, which changes the daily total by that many days' charge. The cycle is charged for the
    dates it is given: pro-rating on a first or last bill and reconnection charges are out of scope, and the
    tariffs' minimum-bill rule for net-metered accounts is not modeled yet.

    Args:
        plan: Any period of the plan, usually the current one.
        cycle: The billing cycle to charge.

    Returns:
        The fixed charges, unrounded.

    Raises:
        ValueError: If ``cycle.end`` is before ``cycle.start``.

    """
    if cycle.end < cycle.start:
        msg = f"billing cycle ends ({cycle.end}) before it starts ({cycle.start})"
        raise ValueError(msg)
    total: Decimal = Decimal(0)
    for offset in range((cycle.end - cycle.start).days + 1):
        period: RatePlan | None = resolve_plan_for(plan, cycle.start + timedelta(days=offset))
        if period is not None:
            total += sum((c.amount for c in period.charges if isinstance(c, DailyCharge)), Decimal(0))
    billing_period: RatePlan | None = resolve_plan_for(plan, cycle.end)
    if billing_period is not None:
        total += sum((c.amount for c in billing_period.charges if isinstance(c, MonthlyCharge)), Decimal(0))
    return total


class UsagePricer:
    """Price a chronological stream of interval reads, tracking cycle-to-date usage.

    Reads must arrive in time order. Cycle-to-date usage resets whenever an interval's local date falls in a
    different billing cycle from the previous interval's. Dates outside every cycle count as one more cycle of
    their own. With no cycles, the usage never resets. Only tiered plans use cycle-to-date usage; for other
    plans the pricer simply prices each read.

    Example::

        cycles = estimate_billing_cycles(forecast, earliest=start.date(), latest=date.today())
        pricer = UsagePricer(RATE_8, cycles)
        for read in reads:  # sorted by start_time
            if already_recorded(read):
                pricer.observe(read.start_time, read.consumption, MeterUnit.WATT_HOUR)
            elif (cost := pricer.price(read.start_time, read.consumption, MeterUnit.WATT_HOUR)) is not None:
                record(cost.amount)
    """

    __slots__ = ("_current_cycle", "_cycle_usage", "_cycles", "_last_when", "_plan", "_therms_per_ccf")

    def __init__(
        self,
        plan: RatePlan,
        cycles: Sequence[BillingCycle] = (),
        *,
        therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF,
    ) -> None:
        """Create a pricer for *plan* with the billing *cycles* that reset cycle-to-date usage.

        Args:
            plan: Any period of the plan, usually the current one. Each read is priced with the period in
                effect at its own timestamp.
            cycles: Billing cycles, for example from ``estimate_billing_cycles``.
            therms_per_ccf: Therms per hundred cubic feet, used only for gas.

        """
        self._plan: RatePlan = plan
        self._cycles: tuple[BillingCycle, ...] = tuple(cycles)
        self._therms_per_ccf: Decimal = therms_per_ccf
        self._cycle_usage: Decimal = Decimal(0)
        self._current_cycle: BillingCycle | None = None
        self._last_when: datetime | None = None

    @property
    def cycle_usage(self) -> Decimal:
        """Usage counted so far in the current billing cycle, in the plan's billing unit (kWh or therm)."""
        return self._cycle_usage

    def observe(self, when: datetime, quantity: Decimal | float, unit: MeterUnit) -> None:
        """Count usage toward the cycle total without pricing it.

        Use this for reads whose cost is already recorded or is not wanted (for example before a cost start
        date), so later reads still land in the right tier.

        Raises:
            ValueError: If *when* is earlier than the previous read, or *unit* does not measure the plan's
                commodity.

        """
        billing_quantity: Decimal = self._to_billing_units(quantity, unit)
        self._advance(when)
        self._cycle_usage += billing_quantity

    def price(self, when: datetime, quantity: Decimal | float, unit: MeterUnit) -> UsageCost | None:
        """Price the interval starting at *when*, then count it toward the cycle total.

        Returns:
            The ``UsageCost``, or ``None`` when ``price_usage`` would return ``None`` (for example no tariff
            period in effect). The usage is counted either way.

        Raises:
            ValueError: If *when* is earlier than the previous read, *unit* does not measure the plan's
                commodity, or the plan in effect has more than one usage-based charge.

        """
        billing_quantity: Decimal = self._to_billing_units(quantity, unit)
        self._advance(when)
        cost: UsageCost | None = _price_billing_units(self._plan, when, billing_quantity, self._cycle_usage)
        self._cycle_usage += billing_quantity
        return cost

    def price_net(
        self, when: datetime, used: Decimal | float, generated: Decimal | float, unit: MeterUnit
    ) -> NetUsageCost | None:
        """Price the interval's usage and generation separately, net them, then count the net toward the cycle.

        Args:
            when: Start of the interval.
            used: Energy taken from the grid in *unit*.
            generated: Energy sent to the grid in *unit*; only its size counts, so a solar-export register's
                negative read can be passed as is.
            unit: The meter unit of *used* and *generated*.

        Returns:
            The ``NetUsageCost``, or ``None`` when ``price_usage`` would return ``None``. The net usage is
            counted either way.

        Raises:
            ValueError: As for ``price``.

        """
        billing_used: Decimal = self._to_billing_units(used, unit)
        billing_generated: Decimal = abs(self._to_billing_units(generated, unit))
        self._advance(when)
        cost: NetUsageCost | None = _price_net_billing_units(
            self._plan, when, billing_used, billing_generated, self._cycle_usage
        )
        self._cycle_usage += billing_used - billing_generated
        return cost

    def _to_billing_units(self, quantity: Decimal | float, unit: MeterUnit) -> Decimal:
        return to_billing_units(quantity, unit, self._plan, therms_per_ccf=self._therms_per_ccf)

    def _advance(self, when: datetime) -> None:
        """Check ordering and reset the cycle total when *when* starts a new billing cycle."""
        local: datetime = to_utility_local(when)
        if self._last_when is not None and _is_before(local, self._last_when):
            msg = f"reads must be in time order: {when} is before the previous read at {self._last_when}"
            raise ValueError(msg)
        self._last_when = local
        if self._cycles:
            cycle: BillingCycle | None = find_billing_cycle(local.date(), self._cycles)
            if cycle != self._current_cycle:
                self._current_cycle = cycle
                self._cycle_usage = Decimal(0)
