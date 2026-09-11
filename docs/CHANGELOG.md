# Changelog

All notable changes to this project are documented here.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).
This project has not yet cut a versioned release for the changes below; they
are recorded here as they land on the development branch.

## Unreleased

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

- **Bidgely pilot id** was hardcoded to the wrong value in two places, causing
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
