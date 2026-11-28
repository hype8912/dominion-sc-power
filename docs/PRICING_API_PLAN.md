# Pricing API Plan — `dominion-sc-power`

**Status:** Library work complete; released as `0.4.0` (2026-11-27). The integration migration (§6) is done on branch
`refactor/adopt-pricing-api` of `ha-dominion-sc` (2026-11-27), not yet committed or released.

- **Done:** Phases 1-3, Phase 5 (`fixed_charges` using the Q4 decisions, and `closed_to_new_customers`), net
  metering (§4.9, added during implementation).
- **Resolved without a library change:** Phase 4. Q3 is answered: days with no data yet are absent from the feed,
  not zero-filled (§4.8).
- **Released:** `0.4.0` (§8), built as a wheel on branch `feat/pricing-api`; not published to PyPI.
- **Migrated:** `ha-dominion-sc` now uses the pricing API (§6.1). Both projects are still in development; the package
  will be published to PyPI when the maintainer judges it ready.
- Decisions that changed or extended this plan during implementation are in §5.1.

**Written against:** library `0.3.0` (`master` at `6f68652`) and the `ha-dominion-sc` working tree of 2026-11-27, which
pins `dominion-sc-power==0.3.0` and already routes time-of-use pricing through `get_time_of_use_rate()`.
**Target release:** `0.4.0`. Every change below is additive; nothing already exported is removed or changed.

---

## 1. Purpose

The library is supposed to be the only place that knows Dominion Energy SC's tariffs: dates, prices, seasons, period
rules, units and billing cycles. Consumers should be able to price usage without knowing how a `RatePlan` is structured
internally.

Today that isn't true. The Home Assistant integration (`ha-dominion-sc`) still carries its own copy of a lot of utility
and tariff logic. That has already cost a real bug: library 0.3.0 fixed the Rate 5/7 weekday, holiday and winter-midday
rules for the pre-July-2026 tariffs, and the integration kept pricing them wrongly. It had its own window-matching code
that didn't know about the new `TimeOfUsePeriod.applies_on()`. Weekend and holiday peak hours from September 2024 to
June 2026 were billed at roughly twice the correct price.

This plan moves the rest of that logic into the library, so a tariff fix in the library reaches every consumer without
code changes on their side.

**Non-goals:**

- Changing any rate data. Prices and dates in `rate_plans/` stay as they are.
- Removing or renaming anything that's already exported.
- Computing the Rate 7 demand charge, which needs billing-period peak demand, not per-interval pricing.
- Publishing to PyPI (see §8).
- **Account lifecycle events, now and in future:** pro-rating on a first or last bill, and the reconnection and
  seasonal-block charge (months disconnected times the basic facilities charge). The library reports on the usage
  data it is given and the billing dates it is given. If those dates describe a partial period, the result is for
  that period; the library doesn't try to reconstruct what Dominion would have billed for the account event.

---

## 2. Current state: tariff logic living in the integration

Each finding is something concrete in `ha-dominion-sc` that duplicates or works around knowledge the library should
own. Paths are relative to `ha-dominion-sc/custom_components/dominionsc/`. Impact is the maintenance cost of leaving it
there.

### F1 — The integration re-implements plan pricing (impact: high)

- **`cost.py`** (about 375 lines) prices usage itself:
  - It chooses tiered, time-of-use or flat pricing based on which `Charge` types a plan contains (`_rate_plan_is_tiered`,
    `_rate_plan_is_tou`, `_rate_plan_is_flat`).
  - It splits an interval that crosses a tier boundary (`_calculate_tiered_cost`).
  - It converts Wh↔kWh and ft³→therm, and decides to skip `DemandCharge`s.
- **`current_rate.py`** separately chooses the active tier from cycle-to-date usage for the "current rate" sensor.
- **Duplicated plan lookup:** both files repeat the "which tariff period is in effect" step:

  ```python
  if get_rate_plan_history(plan.code):
      plan_for_date = get_rate_plan_for_date(plan.code, day)
  else:
      plan_for_date = plan if day >= plan.effective_from else None
  ```

**Latent bug:** `_calculate_tiered_cost` hard-codes exactly two tiers (`tiers[0]` is bounded, `tiers[1]` is
everything above it). If a tariff adds a third tier, or a plan's first tier is unbounded, it either prices wrong with no
error or fails an `assert`.

**Why it matters:** every structural change to a tariff (a new `Charge` kind, a new tier, a new period rule) has to be
made in both projects. If the integration side is missed, nothing fails; the numbers are just wrong.

### F2 — The integration owns gas and electric unit conversion (impact: high)

- **ft³ to therms:** `cost.py` `_calculate_flat_cost` divides ft³ by 100 to get therms, and the integration's
  statistics are stored in Wh and ft³. The library is the side that actually knows the units: `parsers/greenbutton.py`
  reads `espi:uom` (72 = Wh, 119 = ft³) and `powerOfTenMultiplier`.
- **Units are dropped:** `UsageRead.consumption` doesn't say which unit it's in. Its docstring says "divide by 100 for
  therms (approximate; actual therm conversion varies by BTU content)".
- **Why it matters:** the 1000x gas inflation bug fixed in 0.2.0 was a unit-handling bug. Leaving units implicit and
  converting them in a second project is how that kind of bug happens again.

### F3 — Billing-cycle estimation lives in the integration (impact: medium-high)

- **The code:** `billing.py` (about 200 lines) encodes Dominion's observed meter-read schedule:
  - `_billing_cycle_get_gap`: cycle length by start month, including leap-year rules for April and June.
  - `_estimate_billing_cycles`: walks backward and forward from the forecast's current cycle.
  - `_find_billing_cycle_for_date`.
- **Why it's needed:** tiered pricing depends on it, because Rates 1, 6 and 8 reset the 800 kWh tier each cycle.
- **Two copies of the tracking loop:** the per-cycle cumulative-usage counter is written out twice, in
  `aggregation.py` `aggregate_hourly_data` and in `coordinator.py` `_recalculate_one_account` (around lines 1560–1590).
- **Why it matters:** this is a fact about Dominion, not about Home Assistant. Any other consumer would have to re-derive
  it, and the two loops can drift apart.

### F4 — Placeholder zero-usage days are filtered in the integration (impact: medium)

`coordinator.py` `_process_and_insert_statistics` (around lines 1152–1168) drops every day whose readings add up to
exactly zero, because the API returns zeros for days whose data isn't available yet.

- **Why it matters:** this is an API quirk every consumer has to know about.
- **Also a probable bug:** a gas account can legitimately use zero gas for a whole day in summer. Those real zero days
  get dropped, then show up as "missing" and are re-fetched on every poll.

### F5 — Hard-coded tariff values and plan details in the integration (impact: low, but already stale)

- **Stale default rate:** `const.py` sets `DEFAULT_FIXED_RATE = 0.14164`, commented as "matches the Rate 6 first-tier
  rate". That is the superseded `RATE_6_2025` price; the current `RATE_6` first tier is `0.15333`.
- **Copied label:** `rates.py` appends " (closed to new customers)" to Rate 1's label by hand. The library already
  records this as the `closed_to_new_customers` `EligibilityRule` on `RATE_1`.
- **Fine to keep:** Rate 7's " (energy cost only)" suffix and the plan display order are genuine HA presentation choices.

### F6 — Small API gaps (impact: low)

- **Timezone:** `LOCAL_TIMEZONE` is only reachable as `dominionsc.time_of_use.LOCAL_TIMEZONE`. The integration imports
  it from there and wraps it in its own `_utility_local_date()` helper.
- **Fixed charges:** the library models the Basic Facilities Charge (`DailyCharge`) and the DER charge (`MonthlyCharge`),
  but there's no helper to price them. The integration's README says fixed charges are left out of cost statistics.

---

## 3. Design principles

1. **Consumers pass meter data in; the library returns dollars.** A consumer supplies a plan, a timestamp, a quantity
   in the meter's unit, and cycle-to-date usage. It never looks at `tiers_by_season`, `periods_by_season` or
   `price_per_unit`.
2. **The library chooses the tariff period.** Every pricing entry point resolves the period in effect at the timestamp.
   Passing the current `RATE_5` for a 2025 date must give the 2025 price.
3. **Dates are local to the utility.** Every date decision (tariff period, season, holiday, billing cycle) uses
   `America/New_York` local time. Aware timestamps are converted; naive ones are read as local, as
   `get_time_of_use_rate` already does.
4. **`Decimal` in, `Decimal` out.** Return `Decimal`. Accept `Decimal | float | int` for quantities, because consumers
   (HA statistics) hold floats.
5. **Additive only.** Existing exports keep working. New names are added to `__all__` and covered by
   `tests/test_public_api.py`.

---

## 4. API

All new public names are re-exported from `dominionsc/__init__.py`.

### 4.1 Utility-local time (`dominionsc/local_time.py`) — done

```python
UTILITY_TIMEZONE: ZoneInfo  # the existing LOCAL_TIMEZONE, exported; keep LOCAL_TIMEZONE as an alias


def utility_local_date(when: datetime) -> date:
    """Calendar date of *when* in the utility's timezone. Naive values are read as local."""
```

`get_time_of_use_rate` should use `utility_local_date` internally, so there is a single implementation.

### 4.2 Tariff period resolution (`dominionsc/rates.py`) — done

```python
def resolve_plan_for(plan: RatePlan, when: datetime | date) -> RatePlan | None:
    """Return the tariff period of *plan* in effect at *when*.

    Catalog plans (code has history): ``get_rate_plan_for_date(plan.code, local_date)``.
    Non-catalog plans: *plan* itself when local_date is inside its effective dates, else None.
    """
```

This replaces the duplicated lookup in F1. Unlike the integration's version, it also checks `effective_to` for
non-catalog plans.

### 4.3 Units (`dominionsc/models/units.py`, `dominionsc/units.py`, `dominionsc/parsers/greenbutton.py`) — done

```python
class MeterUnit(StrEnum):
    WATT_HOUR = "Wh"  # ESPI uom 72
    CUBIC_FOOT = "ft3"  # ESPI uom 119


def to_billing_units(
    quantity: Decimal | float, unit: MeterUnit, plan: RatePlan, *, therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF
) -> Decimal:
    """Convert a meter quantity into the plan's billing unit (kWh or therm).

    Raises ValueError for a unit/commodity mismatch (e.g. ft3 on an electric plan).
    """


DEFAULT_THERMS_PER_CCF: Decimal = Decimal("1.036")  # EIA South Carolina average heat content; see open question Q1
```

Parser changes:

- Add `unit: MeterUnit | None = None` to `UsageRead`, as the **last** field with a default, so positional construction
  still works. The parser fills it from `espi:uom`.
- Add the same `unit` field to `RegisterReads`.
- An unknown `uom` gives `None` and logs one warning per feed. This follows the same "visible, not silent" rule as
  `_resolve_scale_factor`.

### 4.4 Pricing (`dominionsc/pricing.py`) — done

```python
@dataclass(frozen=True, slots=True)
class RateQuote:
    """The price in force at one moment."""

    plan: RatePlan  # the tariff period actually used
    price_per_unit: Decimal  # $/kWh or $/therm
    usage_unit: UsageUnit
    season: Season | None  # None for plans with no seasonal charge
    period: str | None  # TOU period name, e.g. "on_peak"
    tier: str | None  # UsageTier.name
    tier_upper_bound: Decimal | None
    unpriced_charges: tuple[str, ...] = ()  # e.g. ("On-Peak Billing Demand",)


@dataclass(frozen=True, slots=True)
class UsageCost:
    """The cost of one quantity of usage."""

    amount: Decimal  # dollars
    quantity: Decimal  # in the plan's billing unit, after conversion
    plan: RatePlan
    season: Season | None
    period: str | None
    tiers: tuple[str, ...]  # every tier the quantity touched, in order
    unpriced_charges: tuple[str, ...] = ()


def rate_at(plan: RatePlan, when: datetime, cycle_usage: Decimal | float | None = None) -> RateQuote | None:
    """Price per billing unit at *when*. ``cycle_usage`` (billing units, cycle-to-date)
    picks the tier for tiered plans; ``None`` reports the first tier.
    Returns None when no tariff period is in effect."""


def price_usage(
    plan: RatePlan,
    when: datetime,
    quantity: Decimal | float,
    unit: MeterUnit,
    *,
    cycle_usage_before: Decimal | float = 0,
    therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF,
) -> UsageCost | None:
    """Cost of *quantity* (meter units) starting at *when*.
    ``cycle_usage_before`` is cycle-to-date usage in the same meter unit, before this interval.
    Returns None when no tariff period is in effect."""
```

**Behaviour:**

- **Plan period:** both functions start with `resolve_plan_for(plan, when)`.
- **Tiered (`TieredUsageCharge`):** season from `season_for(utility_local_date(when))`. Walk the season's tiers
  **generically**: for N tiers, split the quantity across every boundary it crosses. A tier with
  `upper_bound=None` takes all remaining usage. This fixes the two-tier assumption.
- **Time-of-use (`TimeOfUseCharge`):** delegate to `get_time_of_use_rate`. If it raises `ValueError` (no fallback
  period, say), return `None` and log at debug.
- **Flat (`FlatUsageCharge`):** quantity × price.
- **One usage charge per plan.** If a plan ever has more than one usage-based charge, raise `ValueError`. Don't silently
  use only the first, which is what the integration does today. All current plans have exactly one.
- **No usage charge.** A plan with only fixed (or demand) charges prices usage at zero: `price_usage` returns a
  `UsageCost` with `amount` 0 and `rate_at` a `RateQuote` with `price_per_unit` 0. `None` is kept for "no tariff
  period in effect" and "the time-of-use or tier data can't price this moment".
- **Negative quantities** (solar export) are credited at the same rate usage costs at that moment. Tiered amounts
  are the difference in cumulative cost before and after the interval, so pricing +10 and −5 gives exactly the same
  total as pricing +5, even across a tier boundary. See §4.9.
- **Excluded charges:** `DemandCharge`, `DailyCharge` and `MonthlyCharge` never go into `amount`.
  - `DemandCharge` names are listed in `unpriced_charges`, so consumers can tell users about them.
  - Daily and monthly charges are covered by §4.6.
- **No rounding.** Consumers round for display.

### 4.5 Billing cycles (`dominionsc/billing.py`) — done

Move `ha-dominion-sc/custom_components/dominionsc/billing.py` over **without changing the algorithm**, and wrap it in
types:

```python
@dataclass(frozen=True, slots=True)
class BillingCycle:
    start: date
    end: date   # inclusive
    def contains(self, day: date) -> bool: ...

def billing_cycle_length(start: date) -> int:               # was _billing_cycle_get_gap
def estimate_billing_cycles(anchor: BillingCycle | Forecast, earliest: date,
                            latest: date | None = None) -> tuple[BillingCycle, ...]:
def find_billing_cycle(day: date, cycles: Sequence[BillingCycle]) -> BillingCycle | None:
```

Passing a `Forecast` uses `start_date` and `end_date` as the anchor. Keep the module docstring's "Accuracy" section: it
is an estimate, possibly off by a day or two at cycle edges.

**Stateful pricer.** This removes both copies of the cumulative-usage loop from F3:

```python
class UsagePricer:
    """Prices a chronological stream of interval reads, resetting cycle-to-date usage at
    each billing-cycle boundary (only matters for tiered plans)."""

    def __init__(
        self, plan: RatePlan, cycles: Sequence[BillingCycle] = (), *, therms_per_ccf: Decimal = DEFAULT_THERMS_PER_CCF
    ) -> None: ...

    def observe(self, when: datetime, quantity: Decimal | float, unit: MeterUnit) -> None:
        """Count usage toward the cycle total without pricing it (already-recorded hours,
        rows before a cost start date)."""

    def price(self, when: datetime, quantity: Decimal | float, unit: MeterUnit) -> UsageCost | None:
        """Price the interval, then count it toward the cycle total."""
```

**Rules:**

- **Chronological input:** reads must arrive in time order. If a timestamp goes backwards, raise `ValueError` rather
  than produce wrong tier splits. "Backwards" means earlier both as an instant and on the local wall clock, so both
  labellings of the hours around a DST change are accepted (see §5.1).
- **Cycle reset:** usage resets when the interval's `utility_local_date` falls in a different `BillingCycle` from the
  previous interval.
- **Dates outside every cycle:** treated as their own cycle. This matches today's behaviour, where
  `_find_billing_cycle_for_date` returning `None` also triggers a reset.

### 4.6 Fixed charges (Phase 5) — done

```python
def fixed_charges(plan: RatePlan, cycle: BillingCycle) -> Decimal:
    """Daily charges x days in cycle + monthly charges, using the period in effect on each day."""
```

Implemented in `dominionsc/billing.py`, with these rules (Q4 decisions, 2026-11-27):

- **"Month" means one billing cycle**, not a calendar month. Twelve cycles and twelve months give the same yearly
  total, so lining them up exactly would not change it.
- **`MonthlyCharge`** (the $1.00 DER charge, and the gas $10.90 Basic Facilities Charge) is charged **once per
  cycle**, whatever the cycle's length and whatever the usage. The gas charge is the connection charge for having
  service, the same at 0 therms or 100. Not pro-rated.
- **`DailyCharge`** (the electric Basic Facilities Charge) is charged for each day of the cycle, both ends counted,
  using the tariff period in effect **that day**. This matches how usage is priced.
- **A cycle spanning a tariff change:** the daily charge follows the day-by-day rule above, and the monthly charge
  comes from the period in effect on the cycle's last day, when the bill is rendered. The tariffs say "bills
  rendered on or after the first billing cycle of July 2026", so Dominion may bill the whole straddling cycle at one
  rate. That is unverified (see Q2).
- **Cycle length is whatever the cycle says.** Dominion sets it, and only the current cycle comes from the
  forecast; earlier ones are estimated and may be a day or two off, which moves the daily total by that many days'
  charge (about $0.36 each on a typical electric plan).
- **Out of scope:** pro-rating on a first or last bill (see the non-goals in §1). A cycle is charged for the dates
  it is given.
- **Deferred:** the tariffs' "monthly minimum charge" as a floor on net-metered credits. It isn't modeled yet, and
  isn't being chased now.
- **Accuracy:** Dominion doesn't publish its billing algorithms, so these rules are reverse-engineered from the
  tariffs and observed patterns. The goal is to be as close as the evidence allows, not to match a bill exactly. The
  untested points (a cycle spanning a tariff change, the minimum-bill floor) can be tightened if a bill or other
  evidence shows a better rule.

### 4.7 Plan metadata (small) — done

```python
# RatePlan
@property
def closed_to_new_customers(self) -> bool:   # any(rule.code == "closed_to_new_customers")
```

No library change is needed for F5's default fixed rate. The integration can use
`rate_at(get_rate_plan("rate_6"), now).price_per_unit` instead of a constant.

### 4.8 Unavailable-data days (Phase 4) — resolved, no library change

**Outcome (2026-11-27):** a live `gb-download` capture answered Q3. Days with no data yet are **missing** from the
feed, so no trimming option was added; only the documentation changed. The original proposal is kept below for
reference.

- **Captures:** electric and gas, 2026-11-20 to 2026-11-27 (requested on 11-27) and 2026-07-01 to 2026-08-15.
- **Newest day:** both recent feeds end at 2026-11-26. The capture day has no entry at all.
- **Completeness:** every returned day had its full reading count (192 per day for the two-register electric
  account, 24 for gas). No all-zero day appeared in any capture.
- **Zeros are real:** hours with no gas use come back as zero-valued readings (812 of 1,104 hourly gas readings in
  the summer capture), and the parser keeps them.
- **Fixture:** `tests/fixtures/greenbutton_gas_recent.xml` (the recent gas capture trimmed to 11-25 and 11-26, ids
  redacted), tested in `tests/test_data_availability.py`, including an all-zero day being kept.
- **Caveat:** only a one-day lag was observed. If a longer outage is ever seen to return zero-filled days, revisit
  this.

**Original proposal:**

Proposed: add `trailing_zero_days_trimmed: bool = True` to `async_get_usage_reads` and `async_get_register_reads`, or
add an `available: bool` flag per read. The default would drop only **trailing** whole days that are all zero, meaning
the most recent days, where the API has no data yet. Zero days in the middle of the range are real data (gas in summer)
and are kept.

**This needs a fixture first.** Capture a raw `gb-download` response for a range that covers the most recent day or two,
and check whether unavailable days come back as zero-valued `IntervalReading`s or are simply missing (Q3). If they're
missing, no library change is needed beyond documentation, and the integration's filter is just a bug to delete.


### 4.9 Net metering (added during implementation) — done

Solar generation is credited at the same rate as usage in that hour: the same tier and season on tiered plans, the
same time-of-use period on Rate 5 and 7. It offsets usage, and on tiered plans it lowers cycle-to-date usage. Each
side gets its own result and the two net together:

```python
@dataclass(frozen=True, slots=True)
class NetUsageCost:
    usage: UsageCost  # cost of the energy used
    generation: UsageCost  # credit for the energy generated (negative amount and quantity)
    amount: Decimal  # usage.amount + generation.amount
    quantity: Decimal  # net, in the billing unit


def price_net_usage(
    plan, when, used, generated, unit, *, cycle_usage_before=0, therms_per_ccf=DEFAULT_THERMS_PER_CCF
) -> NetUsageCost | None: ...


class UsagePricer:
    def price_net(self, when, used, generated, unit) -> NetUsageCost | None:
        """Price both sides, then add the net to cycle-to-date usage."""
```

- `generated` is a size; a solar-export register's negative reads can be passed as is.
- Generation is priced after the interval's usage, so on a tiered plan it offsets the highest-tier energy first.
- The net `amount` always equals `price_usage` of the net quantity. An hour that exports more than it uses is a net
  credit (negative `amount`).

---

## 5. Implementation phases

Each phase is a separately reviewable change with its own tests. Phases 1–3 deliver most of the value.

### Phase 1 — Local time, plan resolution, units (done)

1. Export `UTILITY_TIMEZONE` and add `utility_local_date` (§4.1). Switch `get_time_of_use_rate` to use it.
2. Add `resolve_plan_for` (§4.2).
3. Add `MeterUnit`, the `unit` field on `UsageRead` and `RegisterReads`, parser support, and `to_billing_units` (§4.3).

**Tests:**

- `utility_local_date`: an aware UTC timestamp that crosses local midnight (2026-07-01 02:00 UTC gives 2026-06-30), a
  naive timestamp, and both DST transitions.
- `resolve_plan_for`: a catalog plan before, on and after each period boundary; a non-catalog plan before
  `effective_from` and after `effective_to`.
- Parser: the existing gas and electric fixtures in `tests/fixtures/` produce `CUBIC_FOOT` and `WATT_HOUR`; an unknown
  `uom` gives `None` and logs a warning.
- `to_billing_units`: Wh to kWh, ft³ to therm with the default and a custom factor, and a commodity mismatch raising
  `ValueError`.

### Phase 2 — Pricing (`rate_at`, `price_usage`) (done)

1. Add `RateQuote`, `UsageCost`, `rate_at` and `price_usage` (§4.4).
2. Implement the generic N-tier split.

**Tests (in `tests/test_pricing.py`):**

- **Port the integration's tests.** Port the pricing cases from `ha-dominion-sc/tests/test_cost.py`,
  `tests/test_current_rate.py` and `tests/test_rates.py`. They cover tiered, flat, time-of-use, every superseded
  period, zero cost before the earliest period, and the 2026-07-01 switch-over. Expected values carry over unchanged.
- **Tier splits:** a three-tier synthetic plan (an interval crossing two boundaries in one call), an interval ending
  exactly on a boundary, and `cycle_usage_before` already above the last bound.
- **Seasons:** a tiered plan in May (summer) and October (winter), including a UTC timestamp near local midnight on
  2026-04-30 or 2026-09-30.
- **Demand:** Rate 7 reports `"On-Peak Billing Demand"` in `unpriced_charges`, and the demand charge isn't in `amount`.
- **Edge cases:** a plan with two usage charges raises `ValueError`; a time-of-use plan with no fallback period returns
  `None`.

### Phase 3 — Billing cycles and `UsagePricer` (done)

1. Move `billing.py` with its algorithm unchanged (§4.5). Port the billing-cycle tests from
   `ha-dominion-sc/tests/test_coordinator.py`. Search there for `_estimate_billing_cycles` and `_billing_cycle_get_gap`.
2. Add `UsagePricer`.

**Tests:**

- **Cycle reset:** usage resets at a cycle boundary, and a 15-minute stream crossing the 800 kWh tier mid-cycle is split
  correctly.
- **`observe()`:** observed usage affects later tiers but isn't priced.
- **Ordering:** out-of-order input raises `ValueError`.
- **Equivalence test (important):** generate a year of synthetic 15-minute electric reads plus hourly gas reads. Price
  them for every catalog plan through `UsagePricer`, and through a frozen copy of the integration's 0.3.0-era logic
  (`aggregate_hourly_data` plus `_calculate_cost_for_wh`). Totals must agree within `1e-9` USD. The frozen copy can live
  under `tests/legacy/` and be deleted once the integration has migrated. Any difference must be a documented, intended
  fix.

### Phase 4 — Unavailable-data days (after Q3 is answered) (resolved, no library change)

Implement §4.8 if the fixture shows zero-valued placeholder days. Add a fixture-based test with a trailing all-zero day
and a mid-range all-zero gas day.

The fixture showed missing days, not zero-valued ones, so nothing was implemented. The fixture and tests were added
anyway, to lock in that behaviour and that an all-zero day is kept (§4.8).

### Phase 5 — Fixed charges and plan metadata (optional) (done)

Implement `fixed_charges` (§4.6) and `RatePlan.closed_to_new_customers` (§4.7). Both are done.

### Every phase

- Update `docs/api-reference.md`, `docs/ha-integration-contract.md` and the `Unreleased` section of
  `docs/CHANGELOG.md`.
- Add each new public name to `__all__` and `tests/test_public_api.py`.
- `ruff check`, `ruff format --check` and `mypy --strict` pass, and every new module has 100% coverage.

### 5.1 Implementation record (2026-11-27)

**Result for phases 1-5:** 487 tests pass (276 before), 100% line and branch coverage, `ruff check` and
`ruff format --check` clean. `mypy --strict` reports nothing in new code; the 6 errors it does report (5 in `auth.py`, and
missing `types-xmltodict` stubs) are identical on a clean `master`.

**Files:**

| File | Contents |
| --- | --- |
| `src/dominionsc/local_time.py` (new) | `UTILITY_TIMEZONE`, `utility_local_date`, internal `to_utility_local` |
| `src/dominionsc/models/units.py` (new) | `MeterUnit` |
| `src/dominionsc/units.py` (new) | `to_billing_units`, `DEFAULT_THERMS_PER_CCF` |
| `src/dominionsc/pricing.py` (new) | `RateQuote`, `UsageCost`, `NetUsageCost`, `rate_at`, `price_usage`, `price_net_usage` |
| `src/dominionsc/billing.py` (new) | `BillingCycle`, `billing_cycle_length`, `estimate_billing_cycles`, `find_billing_cycle`, `fixed_charges`, `UsagePricer` |
| `src/dominionsc/rates.py` | `resolve_plan_for` |
| `src/dominionsc/time_of_use.py` | uses `to_utility_local`; `LOCAL_TIMEZONE` kept as an alias of `UTILITY_TIMEZONE` |
| `src/dominionsc/models/rate_plan.py` | `RatePlan.closed_to_new_customers` |
| `src/dominionsc/models/usage_read.py`, `register_reads.py` | `unit: MeterUnit \| None = None`, last field |
| `src/dominionsc/parsers/greenbutton.py` | resolves `espi:uom` per feed (`_resolve_unit`) |
| `tests/test_local_time.py`, `test_units.py`, `test_pricing.py`, `test_billing.py` (new) | tests for the above |
| `tests/fixtures/greenbutton_gas_recent.xml`, `tests/test_data_availability.py` (new) | Phase 4: real redacted capture showing unavailable days are absent, and all-zero days are kept |
| `tests/legacy/ha_pricing.py` (new) | frozen copy of the integration's 0.3.0-era pricing, for the equivalence test only |

**Equivalence test:** 16 months of synthetic reads (2025-07-01 to 2026-11-14: 15-minute electric, hourly gas, stepping
in UTC so both DST changes are covered) for all 8 catalog plans, through `UsagePricer` and through the frozen legacy
code. Per-read and total differences are under 1e-9 USD. No intended differences showed up. The gas cases pin
`therms_per_ccf=1` to match the legacy `ft³ / 100`; the library's own default is 1.036 (decision 12), which is the
one intended difference from the integration.

**Decisions made while implementing:**

1. **Module layout.** `MeterUnit` lives in `models/units.py` rather than `units.py`, because `UsageRead` needs it and
   `units.py` imports `RatePlan`; putting it in `units.py` would create an import cycle. `units.py` re-exports it.
2. **Float quantities** go through `str` on the way to `Decimal`, so `0.1` becomes `Decimal("0.1")`, not the binary
   expansion.
3. **Unit parsing.** A feed with no `uom` gives `None` without a warning (debug log only). An unknown code, or more
   than one distinct code in one feed, gives `None` with one warning per feed. `tests/fixtures/greenbutton_multi_register.xml`
   gained `<espi:uom>72</espi:uom>`, matching real electric feeds.
4. **DST and read ordering.** The plan's "raise if a timestamp goes backwards" needed a definition. Real Green Button
   data labels a reading 02:45 on spring-forward day, a wall time that doesn't exist; as an instant it falls after the
   following 03:00 reading. A true UTC stream, by contrast, goes from 01:45 EDT to 01:00 EST at fall-back, which
   repeats wall-clock times. Comparing only instants rejects the first, comparing only wall clocks rejects the second.
   `UsagePricer` therefore rejects a read only when it is earlier on **both**. The equivalence test found this:
   the first version rejected every read on the fall-back date.
5. **Tiers.** A tier with `upper_bound=None`, or the last tier if every tier is bounded, takes all remaining usage.
   Tiers after the first unbounded one are ignored. A season with no tiers can't be priced (`None`).
6. **No usage charge prices at zero** (user decision). See §4.4.
7. **Net metering** (user decision): generation is credited at the same rate as usage in that hour and nets against
   it, with each side reported separately. Added as §4.9.
8. **`UsagePricer` extras:** a read-only `cycle_usage` property (billing units), and `price()` / `price_net()` count
   usage even when they return `None`.
9. **Fixed charges** (user decisions, Q4): "month" means billing cycle; monthly charges once per cycle whatever its
   length or usage; daily charges per day at that day's tariff period; the monthly amount from the period on the
   cycle's last day. See §4.6.
10. **Days with no data yet** are absent from the feed (Q3, from a live capture), so Phase 4 needed no library
    change. See §4.8.
11. **Scope** (user decision): pro-rating and reconnection or seasonal-block charges are permanent non-goals (§1).
    The minimum-bill floor for net-metered credits and Q2 are deferred.
12. **Gas therm factor** (Q1): the default is 1.036 therms per CCF, the EIA's 24-month South Carolina average, kept
    as one flat number by user decision. A per-month table and a runtime fetch were considered and declined.
13. **Accuracy standard** (user direction): Dominion doesn't publish its billing math, so the library
    reverse-engineers it and aims to be as close as the evidence allows, documenting each approximation.

---

## 6. Integration migration (`ha-dominion-sc`) after 0.4.0

The table below is the plan as written. What was actually done, and where it differed, is in §6.1.

For reference, so the library API is shaped around what the integration actually needs. The integration must pin
`dominion-sc-power==0.4.0` (in both `manifest.json` and `pyproject.toml`) before using any of this.

| Integration code | Replace with | Removes |
| --- | --- | --- |
| `cost.py` `_calculate_tiered_cost`, `_calculate_tou_cost`, `_calculate_flat_cost`, `_calculate_plan_cost`, the `_rate_plan_is_*` helpers, the plan-for-date block in `_calculate_cost_for_wh`, `_utility_local_date` | `price_usage(...)`. `_calculate_cost_for_wh` keeps only the `none`/`fixed` modes | ~250 lines; the two-tier bug; the ft³/100 conversion |
| `current_rate.py` `_plan_in_effect`, `_tiered`, `_time_of_use` | `rate_at(plan, now, cycle_kwh)`, then map the `RateQuote` fields into sensor attributes | ~70 lines |
| `billing.py` | `dominionsc.billing` | the whole module (~200 lines) |
| Cycle-tracking loops in `aggregation.py` `aggregate_hourly_data` and `coordinator.py` `_recalculate_one_account` | `UsagePricer.observe()` / `.price()` | two copies of the loop |
| Fixed charges (README says they're left out of cost statistics) | `fixed_charges(plan, cycle)`, if the integration wants them. Attributing a per-cycle amount to hourly statistics is the integration's decision | n/a |
| Zero-day filter in `coordinator.py` `_process_and_insert_statistics` | nothing: delete it. Unavailable days are absent from the feed (§4.8), so the filter only ever drops real zero-usage days | the gas zero-day re-fetch bug |
| `const.py` `DEFAULT_FIXED_RATE` | `rate_at(get_rate_plan("rate_6"), now).price_per_unit` when building the form default | a stale hard-coded rate |
| `rates.py` Rate 1 label suffix | `plan.closed_to_new_customers` | a copied tariff fact |
| Solar-export registers, if the integration prices them | `UsagePricer.price_net(when, used, generated, unit)` | hand-netting grid and solar reads |

**Integration details to keep in mind:**

- **Units:** electric statistics are stored in Wh and gas in ft³. Hourly rows re-read from the recorder during "Recalculate
  History" carry no unit, so the integration passes `MeterUnit.WATT_HOUR` or `MeterUnit.CUBIC_FOOT` based on the
  account type.
- **Recalculation granularity:** "Recalculate History" prices **hourly** aggregated rows with UTC timestamps, not
  15-minute reads. `price_usage` and `UsagePricer` must work for any interval length, and the timestamp is the
  interval's start.
- **Floats:** the integration works in `float`, so it converts `UsageCost.amount` with `float()`.
- **Re-pricing stored history:** any pricing change only reaches stored statistics after the user runs Recalculate
  History, so the integration's release notes should say so.
- **Gas costs rise about 3.6%:** the library converts at 1.036 therms per CCF, the integration at exactly 1
  (`ft³ / 100`). This is intended (decision 12) and belongs in the release notes.
- **Zero-day filter:** delete it rather than replace it (§4.8).

---

## 7. Open questions

- **Q1 — Gas therm factor.** *Answered in principle (2026-11-27), value still approximate.* Dominion's Gas General
  Terms and Conditions (section III.B) convert cubic feet to therms using the weighted average heat content (BTU per
  cubic foot) of the gas entering its system over the days of the customer's billing cycle, divided by 1,000. So the
  factor is **not** exactly 1 therm per CCF: it is that average BTU / 1,000, it changes every billing cycle, and it
  is normally between 0.95 and 1.40 (the tariff's 950 to 1,400 BTU per cubic foot range). The value isn't in the
  tariff or in the Green Button feed (checked: the feed has only volume, uom 119), and Dominion doesn't publish a
  monthly figure that we could find. The best evidence is the U.S. EIA's monthly series for heat content of natural
  gas deliveries to South Carolina consumers (`NGA_EPG0_VGTH_SSC_BTUCF`): September 2024 to August 2026 averaged
  1,036 BTU per cubic foot, never leaving 1,033 to 1,041 (under 1% spread). Dominion's own conversion chart rounds
  to 1,000 BTU per cubic foot, which is where the integration's `/ 100` (a factor of exactly 1) comes from. So the
  default is now **1.036**, about 3.6% above the old conversion. It is a statewide estimate, not Dominion's billed
  figure; a gas bill shows therms and CCF for a cycle, and their ratio is the exact factor.
  **Decision (2026-11-27): keep the single flat 1.036.** Two refinements were considered and declined: a bundled
  month-by-month table from the same EIA series, and fetching the EIA page at runtime. Monthly values stay within
  about ±0.5% of the average (typically ±0.2%), the newest months are always missing from EIA's data (it publishes
  about two months behind), and the page can only be scraped, so the gain is a few cents on a typical gas bill.
  Revisit only if Dominion's actual per-cycle factor becomes available, for example from a gas bill. Per-cycle factors, if wanted, would need
  `UsagePricer` to take a factor per cycle instead of one factor.
- **Q2 — Where tariff-period changes fall within a billing cycle.** *Open, deferred (2026-11-27): not being chased
  now.* The tariffs say "bills rendered on or after" or "service rendered on or after". Today every period switches
  on a calendar day. Should the tiered cycle-to-date count reset when the tariff period changes mid-cycle? Current
  behaviour: no. Keep it unless a tariff says otherwise. The rate sheets and the gas general terms and conditions
  both say "effective on and after the first billing cycle of ...", which suggests Dominion switches rates by billing
  cycle, but nothing says how a cycle that spans the change is billed, so it isn't confirmed. It affects one cycle
  per tariff change. Resolve it if a bill for such a cycle becomes available.
- **Q3 — What "no data yet" looks like.** *Answered (2026-11-27):* missing from the feed, not zero-valued. See §4.8.
- **Source for gas billing rules:** Dominion Energy South Carolina, *Gas General Terms and Conditions*, effective on
  and after the first billing cycle of October 2023 (Order No. 2023-737(A)); copy at
  `docs/reference/general-terms-and-conditions-gas.pdf`. It defines a billing month as the period
  between two regular meter readings of 28 to 34 days (section I.B), which confirms that "month" in the rate
  schedules means billing cycle and that cycle length varies. It states rates are "on a monthly basis". An estimated
  bill uses the preceding 60 days' average use and is corrected at the next actual read (IV.A). It also sets a
  reconnection charge and a seasonal-block charge, which are out of scope (§1). It has **no** pro-rating rule and
  **nothing on how a rate change applies to a cycle that spans it**, so Q2 is not answered by it.
- **Q4 — Fixed charges.** *Answered (2026-11-27):* the DER and gas charges are once per billing cycle regardless of
  length or usage, and "month" means billing cycle. A cycle spanning a tariff change is charged day by day, which is
  unverified against a real bill; revisit if evidence shows a better rule. See §4.6.
- **Q5 — Where this work lands.** *Resolved (2026-11-27):* on the fork (`hype8912/dominion-sc-power`). The upstream
  owner hasn't responded to repeated contact, so no upstream PR is planned.

---

## 8. Versioning and release

- **Version:** `0.4.0`, because the changes only add API. Record each phase under `Unreleased` in
  `docs/CHANGELOG.md` as it lands.
- **Not on PyPI yet:** `0.4.0` is not to be published there until the publishing hold is lifted. The integration's
  maintainer installs the built wheel into the HA instance's `deps` directory by hand.
- **Compatibility:** keep `requires-python = ">=3.14"` and `aiohttp>=3.14.4`. That ties consumers to Home Assistant
  2026.10.0 or newer, the oldest release whose pinned `aiohttp` satisfies this.

### 6.1 Migration record (2026-11-27)

**Result:** `ha-dominion-sc` branch `refactor/adopt-pricing-api`, uncommitted. Production code is about 600 lines
shorter (+255 / −861 across 10 files). 321 tests pass at 100% line and branch coverage; `ruff check` and
`ruff format --check` are clean. The pin is `dominion-sc-power==0.4.0` in `manifest.json` and `pyproject.toml`.

**Equivalence check:** the integration's code at `HEAD` (before the migration) and after it were run side by side on
16 months of synthetic reads (2025-07-01 to 2026-11-14), with timestamps both as true instants and as the parser's
wall-clock labels, so both DST changes are covered:

- **Statistics path** (`aggregate_hourly_data`, 15-minute electric and hourly gas reads): every hourly cost agrees
  within 2.2e-16 USD for all six electric plans, fixed and none, with and without already-recorded hours and a cost
  start date. Billing-cycle resets and tier splits are exercised by about 1,900 kWh a month.
- **Recalculate History** (hourly UTC rows, window starting mid-cycle): every emitted row agrees within 2.2e-16 USD.
- **Current-rate sensor:** for every hour of the 16 months, every plan, and cycle usage of unknown, 0, 500, 799.999,
  800 and 1,500 kWh, price and attributes are identical.
- **Gas** agrees with the old result times 1.036 (within 3e-14), the one intended change.

**Done as planned:**

| Integration code | Now |
| --- | --- |
| `billing.py` | Deleted. `dominionsc.estimate_billing_cycles` replaces it. |
| `cost.py` pricing (`_calculate_tiered_cost`, `_calculate_tou_cost`, `_calculate_flat_cost`, `_calculate_plan_cost`, `_rate_plan_is_*`, `_utility_local_date`, the plan-for-date block) | Deleted, about 250 lines. `cost.py` keeps the options-to-config helpers and a small `IntervalCostCalculator`. |
| `current_rate.py` `_plan_in_effect`, `_tiered`, `_time_of_use` | Replaced by `rate_at`; the module only maps a `RateQuote` to sensor attributes. |
| Cycle-tracking loops in `aggregation.py` and `coordinator.py` | Both replaced by `IntervalCostCalculator`, which wraps `UsagePricer` (`observe()` / `price()`). |
| Zero-day filter in `_process_and_insert_statistics` | Deleted, not replaced. A test now checks that an all-zero day reaches aggregation. |
| `DEFAULT_FIXED_RATE` | Removed. `rates.default_fixed_rate()` reads `rate_at(rate_6, now)`, currently 0.15333 instead of the stale 0.14164. |
| Rate 1 label suffix | Now from `plan.closed_to_new_customers`. |

**Differences from the plan:**

1. **`IntervalCostCalculator` wrapper.** The plan called `UsagePricer` directly. The integration also has `none` and
   `fixed` cost modes that have no plan, so one small class in `cost.py` handles all three modes behind the same
   `observe()` / `price()` calls, and holds the account's `MeterUnit`.
2. **Tier flag removed.** `is_tiered_rate` (and the unused `is_electric` parameter of `aggregate_hourly_data`) are gone.
   The pricer ignores cycles for non-tiered plans, so the flag had no job. The recalculation path still fetches the
   forecast only when a rate plan is selected, to avoid an extra network call for fixed-rate users.
3. **Units by account type.** Hourly rows re-read from the recorder carry no unit, so `meter_unit_for(account)` gives
   `WATT_HOUR` for electric and `CUBIC_FOOT` for gas.
4. **Cycle-kWh guard.** `_async_electric_cycle_kwh` used `_rate_plan_is_tiered`; it now asks `rate_at` whether the quote
   has a tier.
5. **`season` on the current-rate sensor.** `RateQuote.season` is `None` for plans whose price doesn't depend on it
   (flat plans), but the sensor used to report the season for every plan and users may rely on it. The integration
   keeps reporting it for every plan, using `season_for(utility_local_date(now))` when the quote has none.
6. **Stored fixed rate of 0.** The options form default now distinguishes "not set" from a stored `0.0`, which the old
   `.get(..., default)` also did and a naive `or` would not.

**Intended behaviour changes (for the integration's release notes):**

- Gas costs rise about 3.6% (1.036 therms per CCF instead of `ft³ / 100`). Tests that pinned the old gas values were
  updated.
- Stored history keeps its old prices until the user runs Recalculate History.
- The fixed-rate form default changes from 0.14164 to the current Rate 6 first-tier price.

**Left for a later change:**

- Fixed charges (`fixed_charges`) are not added to cost statistics. The README still says they are excluded.
- `net` pricing (`price_net`) is not used, because the integration records each register as its own statistic.
- Publishing `dominion-sc-power` to PyPI is deferred until the maintainer feels it is ready. Until then the
  integration's `manifest.json` pin (`==0.4.0`) can't be installed by a stock Home Assistant, and development runs
  against the sibling checkout (`[tool.uv.sources]` in `pyproject.toml`).
