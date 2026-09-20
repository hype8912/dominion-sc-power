# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
Changes are recorded under `Unreleased` as they land on the development
branch, then moved under a version heading once `pyproject.toml`'s version is
bumped for a release.

## Unreleased

### Added

- Superseded tariff periods: `RATE_6_2025` and `RATE_8_2025` (in effect
  2025-07-23 to 2026-06-30) archive the prior Rate 6 / Rate 8 usage charges as
  `RatePlan` objects with `effective_to` set. They carry only the usage charge
  (the fixed charges then in force were not recorded).
- `get_rate_plan_history(code)` returns every known period for a rate code,
  oldest first (the last entry is the current plan), and
  `get_rate_plan_for_date(code, on)` returns the plan in effect on a date, so
  callers can price historical usage. `RATE_PLAN_HISTORY` exposes the mapping.
  `get_rate_plan` and `get_available_rate_plans` still return current plans only.
- `py.typed` marker (PEP 561): the package now ships inline type information,
  so consumers get proper static type checking against `dominionsc` instead
  of falling back to `Any` everywhere. `RegisterReads` is now also
  re-exported from the top-level `dominionsc` package (previously only
  reachable via `dominionsc.models`), matching `Forecast` and `UsageRead`.
- `RATE_1` in `dominionsc.rates`: Rate 1 — Residential Service: Good Cents
  Rate. Closed to new customers since January 15, 1996; only dwellings
  already certified under the Good Cents Program may remain on it. Current
  pricing matches `RATE_6`'s seasonal tiered schedule.
- `pilot_id` constructor parameter on `DominionSC`: allows callers (e.g. the
  Home Assistant integration) to override the Bidgely multi-tenant pilot ID
  per-instance instead of relying solely on the hardcoded
  `const.BIDGELY_PILOT_ID`. Falls back to the library default when not given.

### Fixed

- **Gas consumption was inflated 1000x.** The Green Button parser ignored the
  `powerOfTenMultiplier` declared on each feed's `ReadingType`. Dominion's gas
  feed reports cubic feet (`uom=119`) with a multiplier of `-3`, so raw values
  (thousandths of a cubic foot) were returned as cubic feet (a 5 CCF bill showed
  as roughly 500,000 ft³). The multiplier is now applied to every reading in the
  feed. Electric feeds declare no multiplier and are unaffected.

## [0.1.0] - 2026-09-14

### Added

- **Declarative Residential Rate Catalog**: Added a complete, data-only residential tariff catalog in `dominionsc.rates` for Dominion Energy South Carolina (effective July 2026).
  - Includes electric rates: `RATE_2` (Low Use), `RATE_5` (Time of Use), `RATE_6` (Energy Saver), `RATE_7` (Time of Use Demand), and `RATE_8` (Standard).
  - Includes gas rates: `RATE_32S` (Standard) and `RATE_32V` (Value).
  - Added lookup functions `get_rate_plan(code)` and `get_available_rate_plans()`.
- **Rate Plan Data Models**: Added robust, immutable data models in `dominionsc.models.rate_plan` to represent tariff structures using a discriminated union for charges:
  - `DailyCharge`, `MonthlyCharge`, `FlatUsageCharge`, `TieredUsageCharge`, `TimeOfUseCharge`, and `DemandCharge`.
  - Supporting models: `Commodity`, `UsageUnit`, `Season`, `UsageTier`, `TimeOfUsePeriod`, `TimeWindow`, `EligibilityRule`, and `Adjustment`.
- Comprehensive unit tests for the rate catalog and models in `tests/test_rates.py` with 100% code coverage.
- `async_get_register_reads(account, start, end)` on `DominionSC`: returns
  `list[RegisterReads]`, keeping each physical meter register (ESPI
  UsagePoint) separate. Net-metered solar accounts now expose grid-delivery
  and solar-export as distinct registers rather than a single merged stream.
- `RegisterReads` model (`usage_point_id`, `flow_direction`, `reads`),
  exported from `dominionsc.models`.
- `parse_registers()` in the Green Button parser: groups interval readings by
  UsagePoint, accumulating all daily entries per register.
- CLI: a `register` column in CSV output, and register-aware console output,
  so grid and solar rows are distinguishable within a single service.

### Changed

- **Breaking (CLI output):** the CSV format gained a `register` column and is
  now `service,register,start_time,end_time,consumption` (five columns, was
  four). Anything parsing the previous 4-column output must be updated.
- The CLI now uses `async_get_register_reads()` internally instead of the flat
  `async_get_usage_reads()`.
- Reading signs are preserved as reported by the API. Solar-export registers
  carry negative values; the library does not normalize or relabel them.

### Fixed

- **Bidgely pilot ID** was hardcoded to the wrong value in two places, causing
  requests to be routed to the wrong pilot and return incorrect (estimated,
  hourly-quantized) data. The correct value is now centralized in
  `const.BIDGELY_PILOT_ID`.
- **Timezone handling** in usage-read requests: request-window dates were
  labeled UTC instead of the utility's local timezone, silently shifting the
  requested window. They are now interpreted in the configured timezone.
- Green Button parser handled a single `IntervalReading` element incorrectly
  (xmltodict returns a dict, not a list, for a single child); a feed with
  exactly one reading no longer errors.

### Internal

- Package refactored into focused modules: `config`, `transport`, `headers`,
  `urls`, `auth`, `client`, `parsers/`, and `models/`. The `dominionsc`
  module is now a backward-compatible re-export shim; the public API surface
  (`dominionsc.__all__`) is unchanged.
- Login flow builds an `AccountInfo` model internally instead of a positional
  `[[types], addr]` list, converting to the legacy shape only at the
  `async_get_accounts()` boundary for backward compatibility.
- Test coverage raised to 100% (182 tests), including fixture-based parser
  tests against redacted real-structure Green Button XML.

### Known follow-ups (not yet done)

- `async_get_accounts()` still returns the legacy positional
  `[measurement_types, service_address]` list. Migrating it to return
  `AccountInfo` directly is a breaking change deferred until the
  `ha-dominion-sc` consumer is updated in a coordinated version bump.
- Transport unification (F1) and the shared JSON-decode helper (F4) from the
  refactor plan remain intentionally deferred. See `docs/REFACTOR_PLAN.md`.
