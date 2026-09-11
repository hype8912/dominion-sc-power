# Developer Guide

This guide is written for developers of all experience levels who need to understand, maintain, or extend the `dominion-sc-power` library. It covers how the code is structured, how the individual modules relate to each other, and how to perform common maintenance tasks.

---

## Table of Contents

1. [What this library does](#what-this-library-does)
2. [Project layout](#project-layout)
3. [Setting up the development environment](#setting-up-the-development-environment)
4. [How the library works — end-to-end walkthrough](#how-the-library-works--end-to-end-walkthrough)
5. [Module reference](#module-reference)
6. [Testing](#testing)
7. [Common maintenance tasks](#common-maintenance-tasks)
8. [Important design decisions](#important-design-decisions)
9. [Known limitations and technical debt](#known-limitations-and-technical-debt)

---

## What this library does

Dominion Energy South Carolina customers can view their energy usage history and bill forecasts on the customer portal at `account.dominionenergysc.com`. This library automates that process programmatically by:

1. Logging in to the Dominion portal (including two-factor authentication).
2. Exchanging the Dominion session for a Bidgely access token (Bidgely is a third-party energy analytics platform Dominion uses to store metering data).
3. Downloading metering data as Green Button ESPI XML from Bidgely's API.
4. Parsing the XML into structured Python objects that callers can work with.

The primary consumer of this library is the [ha-dominion-sc](https://github.com/sctigercat1/ha-dominion-sc) Home Assistant integration.

---

## Project layout

```
dominion-sc-power/
├── pyproject.toml          # Package metadata, dependencies, tool configuration
├── uv.lock                 # Locked dependency versions (commit this file)
├── README.md               # User-facing documentation
├── CONTRIBUTING.md         # Developer setup and workflow
│
├── src/dominionsc/         # Main package source code
│   ├── __init__.py         # Public API surface — what callers import
│   ├── __main__.py         # `python -m dominionsc` entry point
│   ├── client.py           # DominionSC: the main class callers use
│   ├── auth.py             # Login flow and TFA handling
│   ├── transport.py        # HTTP transport layer (aiohttp wrapper)
│   ├── urls.py             # All URL builders in one place
│   ├── headers.py          # All HTTP header builders in one place
│   ├── config.py           # UtilityConfig dataclass
│   ├── const.py            # USER_AGENT and BIDGELY_PILOT_ID constants
│   ├── exceptions.py       # Exception hierarchy
│   ├── helpers.py          # create_cookie_jar() utility
│   ├── cli.py              # CLI argument parser and runner
│   ├── rates.py            # Residential rate plan catalog
│   │
│   ├── models/             # Pure data classes (no network, no logic)
│   │   ├── account.py      # AccountInfo
│   │   ├── forecast.py     # Forecast
│   │   ├── usage_read.py   # UsageRead
│   │   ├── register_reads.py  # RegisterReads
│   │   └── rate_plan.py    # Full rate plan type system
│   │
│   └── parsers/            # Pure parsing functions (no network)
│       ├── forecast.py     # parse_forecast(): JSON dict → Forecast
│       └── greenbutton.py  # parse_registers(): ESPI XML → RegisterReads
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   └── greenbutton_multi_register.xml
│   ├── test_dominionsc.py
│   ├── test_parsers.py
│   ├── test_cli.py
│   ├── test_rates.py
│   ├── test_helpers.py
│   ├── test_headers.py
│   ├── test_urls.py
│   ├── test_config.py
│   ├── test_account.py
│   ├── test_transport.py
│   ├── test_exceptions_coverage.py
│   └── test_main_coverage.py
│
├── docs/
│   ├── developer-guide.md  # This file
│   ├── api-reference.md    # Full public API reference
│   ├── troubleshooting.md  # Common errors and solutions
│   ├── CHANGELOG.md
│   └── architecture/       # Mermaid architecture diagrams
│
└── scripts/
    ├── setup               # Creates .venv via uv sync
    ├── lint                # Runs ruff format + check
    └── test                # Runs pytest
```

### Backward-compatibility shims

Three files exist only to preserve old import paths for existing callers:

| File | Old import path | Now lives in |
|------|-----------------|--------------|
| `dominionsc.py` | `from dominionsc.dominionsc import DominionSC` | `client.py` |
| `forecast.py` | `from dominionsc.forecast import Forecast` | `models/forecast.py` |
| `usage_read.py` | `from dominionsc.usage_read import UsageRead` | `models/usage_read.py` |

Do not add new code to these shims. New code belongs in the appropriate module.

---

## Setting up the development environment

This project uses [uv](https://docs.astral.sh/uv/) for dependency management. Install Python 3.11+ and uv before starting.

```bash
# Clone the repository
git clone https://github.com/sctigercat1/dominion-sc-power.git
cd dominion-sc-power

# Create .venv and install all dependencies (including dev tools)
uv sync --extra dev

# Verify the setup — run the full test suite
uv run pytest
```

### Daily development commands

```bash
# Run tests
uv run pytest
uv run pytest tests/test_parsers.py -v           # one module
uv run pytest -k "test_login" -v                 # by name pattern

# Lint and format
uv run ruff format .                              # auto-format
uv run ruff check . --fix                         # lint + apply safe fixes
uv run ruff check .                               # lint only (no changes)

# Type checking
uv run mypy src/dominionsc

# Build (creates dist/ — don't commit it)
uv build
```

The `./scripts/lint` and `./scripts/test` wrappers run the same commands above.

---

## How the library works — end-to-end walkthrough

This section walks through exactly what happens when a caller runs:

```python
client = DominionSC(session, username, password)
await client.async_login()
registers = await client.async_get_register_reads("ELECTRIC", start, end)
```

### Step 1: Construction (`DominionSC.__init__`)

`DominionSC` stores credentials and creates a `UtilityConfig` object. The config is the single carrier of endpoint hostnames, the Bidgely pilot ID, the timezone, and the User-Agent string. Nothing else in the library holds these as local variables.

### Step 2: Login (`async_login`)

`async_login` delegates to `LoginFlow.execute()` in `auth.py`. The login sequence has 9 HTTP requests:

| # | Method | Endpoint | Purpose |
|---|--------|----------|---------|
| 1 | GET | `/access/#login` | Fetch the login page; extract `__RequestVerificationToken` via regex |
| 2 | POST | `/fusionapi/LoginWebApi/Authenticate/` | Submit username + password |
| 3 | GET | `/fusionapi/LoginWebApi/Verify2FAToken/` | Verify a saved TFA token (skips interactive TFA if valid) |
| — | — | — | *If no valid token: raise `MfaChallenge` — caller handles TFA interactively* |
| 4 | GET | `/` (home page) | Get a fresh `__RequestVerificationToken` for authenticated calls |
| 5 | GET | `/fusionapi/AccountManagementWebApi/GetAccountListing/` | Confirm single-account constraint |
| 6 | GET | `/fusionapi/AccountSummaryWebApi/InitAccount/` | Retrieve service address |
| 7 | GET | `/fusionapi/BidgelyWebApi/GetBidgelySDKInit/` | Get encrypted Bidgely token |
| 8 | POST | `desc-prodapi.bidgely.com/v2.0/web/wc-session` | Exchange encrypted token for Bidgely Bearer token + user ID |

After login, `DominionSC` holds `access_token`, `user_id`, and `accounts` (the legacy `[[types], address]` list).

**The verification token** (`__RequestVerificationToken`) is a CSRF protection mechanism. It is embedded as a hidden input field in the HTML of both the login page and the authenticated home page. The library extracts it with a regex in `find_verification_token()` (`auth.py`) and sends it as an HTTP header on all AJAX calls.

**TFA flow:** After the username/password POST, the server always responds with `status: "twoFA"`. The library checks whether a saved `tfa_token` is available in `login_data`. If valid, it is verified with request #3 and login continues. If not valid or absent, `MfaChallenge` is raised carrying a `DominionSCTFAHandler` instance. The caller uses the handler to select a delivery option (SMS/email), deliver the code, and submit it. Successful submission returns a new `tfa_token` that can be saved to a JSON file for the next run.

### Step 3: Fetching register reads (`async_get_register_reads`)

1. Floor the requested date range to midnight in the utility's local timezone.
2. Convert to Unix timestamps (seconds since the UTC epoch).
3. Build the Bidgely `gb-download` URL in `urls.py` using the user ID, timestamps, and measurement type (`ELECTRIC` or `GAS`).
4. Add Bidgely headers (including the `Authorization: Bearer <access_token>`) from `headers.py`.
5. HTTP GET the URL. The response is a Green Button ESPI XML document.
6. Pass the XML to `parse_registers()` in `parsers/greenbutton.py`.
7. Return a `list[RegisterReads]`, one per distinct ESPI UsagePoint.

### Step 4: Parsing Green Button XML (`parse_registers`)

The Green Button ESPI XML has this general shape:

```xml
<feed>
  <entry>
    <title>Interval Consumption</title>
    <link href=".../UsagePoint/abc123/..."/>
    <content>
      <espi:IntervalBlock>
        <espi:IntervalReading>
          <espi:timePeriod>
            <espi:start>1748736000</espi:start>     <!-- UTC epoch seconds -->
            <espi:duration>900</espi:duration>       <!-- 15 minutes = 900 seconds -->
          </espi:timePeriod>
          <espi:value>350</espi:value>               <!-- Wh -->
        </espi:IntervalReading>
        <!-- ... more readings ... -->
      </espi:IntervalBlock>
    </content>
  </entry>
  <!-- ... more entries, possibly for a second UsagePoint ... -->
</feed>
```

The parser:
1. Converts the XML to a dict using `xmltodict`.
2. Filters entries to those with title `"Interval Consumption"`.
3. Extracts the UsagePoint ID from the `<link href>` path using a regex.
4. Groups all entries by UsagePoint ID into `RegisterReads` objects.
5. Converts UTC epoch seconds to timezone-aware `datetime` objects.

The `_ensure_list()` helper normalizes `xmltodict`'s behavior: it returns a `dict` when there is only one child element, but a `list` when there are multiple. Calling `_ensure_list()` makes callers work correctly in both cases.

---

## Module reference

### `client.py` — `DominionSC`

The class that library users instantiate. It holds all session state after login. It should not contain URL strings, header dicts, or pilot ID/timezone literals — those belong in `urls.py`, `headers.py`, and `config.py` respectively.

**Key methods:**

- `async_login()` — Run the full login sequence. Raises `MfaChallenge` if TFA is needed.
- `async_get_accounts()` — Returns the `[[types], address]` legacy list. Do not change the return type without coordinating with `ha-dominion-sc`.
- `async_get_forecast()` — Returns a `Forecast` for the current billing period.
- `async_get_register_reads(account, start_date, end_date)` — Returns `list[RegisterReads]` (preferred).
- `async_get_usage_reads(account, start_date, end_date)` — Flattened `list[UsageRead]` (backward compat).

### `auth.py` — `LoginFlow`, `DominionSCTFAHandler`

Contains the full multi-step login sequence in `LoginFlow.execute()` and the interactive TFA handler `DominionSCTFAHandler`. Extracted from the original `dominionsc.py` monolith so auth can be read and tested independently.

`find_verification_token(webpage, path, funct)` is a module-level function shared between `LoginFlow` and `DominionSC._find_verification_token()`.

### `transport.py` — `DominionSCURLHandler`

A thin `aiohttp` wrapper with a 30-second default timeout. `call_api(method, url, headers, json_data)` dispatches GET or POST, reads the response as UTF-8 text, and wraps `ClientError` into `CannotConnect`. All login and forecast flows use this; usage reads use `session.get` directly (a known inconsistency documented in the module).

`cache_buster()` returns a millisecond timestamp string used as the `_` query parameter on several endpoints that must not be cached.

### `urls.py` — URL builders

One function per endpoint. Each function takes a `UtilityConfig` and returns a complete URL string. This is the single greppable source of truth for "what endpoints does this library call." If an endpoint path changes, update only this file.

### `headers.py` — Header builders

Four functions that return fresh `dict[str, str]` instances. Never mutate the returned dict. The Bidgely pilot ID is added only here — never in any other module.

### `config.py` — `UtilityConfig`

A frozen dataclass that bundles endpoint hostnames, timezone, pilot ID, and User-Agent. A singleton `DEFAULT_CONFIG` is provided. `DominionSC` constructs one internally; you generally never need to create one yourself.

### `const.py` — Constants

Two values: `USER_AGENT` (Chrome browser string) and `BIDGELY_PILOT_ID`. See the comments in that file for the history of why the pilot ID matters.

### `exceptions.py` — Exception hierarchy

| Exception | When raised | Retryable? |
|-----------|-------------|------------|
| `CannotConnect` | Network failure, timeout, or connection error | Yes |
| `InvalidAuth` | Wrong credentials, expired session, multi-account | No |
| `MfaChallenge` | TFA is required and no valid saved token exists | — (caller must handle interactively) |
| `ApiException` | API response received but structure has changed | No |

`MfaChallenge.handler` carries a `DominionSCTFAHandler` instance. `CannotConnect` and `ApiException` carry `url`, `status`, and `response_text` for debugging.

### `parsers/greenbutton.py` — ESPI XML parser

Pure functions — no network, no aiohttp. Takes raw XML text, returns structured objects. The main entry point for register-aware parsing is `parse_registers(xml_text, timezone)`. The backward-compat flattening wrapper is `parse_usage_reads(xml_text, timezone)`.

### `parsers/forecast.py` — AMI JSON parser

Pure function `parse_forecast(payload, url)`. Takes the already-decoded JSON dict from `GetAccountAMIUsageAlerts`, returns a `Forecast`. Forecasted cost is computed as `currentCostPerDay * numberOfDaysInCurrentBill`.

### `models/` — Data classes

All pure data with no business logic.

**Usage and account models** (`models/usage_read.py`, `models/register_reads.py`, `models/forecast.py`, `models/account.py`):

| Model | Key fields |
|-------|-----------|
| `UsageRead` | `start_time`, `end_time`, `consumption` (Wh or ft³) |
| `RegisterReads` | `usage_point_id`, `flow_direction`, `reads: list[UsageRead]` |
| `Forecast` | `start_date`, `end_date`, `cost_to_date`, `forecasted_cost`, `typical_cost: float \| None` |
| `AccountInfo` | `measurement_types`, `service_address_and_account_no`; `to_legacy_list()` |

**Rate plan models** (`models/rate_plan.py`) — see the `rates.py` section above for the full type hierarchy:

| Model | Role |
|-------|------|
| `RatePlan` | Top-level tariff definition |
| `DailyCharge` | Fixed $/day charge component |
| `MonthlyCharge` | Fixed $/billing-cycle charge component |
| `FlatUsageCharge` | Uniform $/unit charge component |
| `TieredUsageCharge` | Tiered blocks that can vary by `Season` |
| `UsageTier` | One cumulative tier within `TieredUsageCharge` |
| `TimeOfUseCharge` | Time-of-day pricing that can vary by `Season` |
| `TimeOfUsePeriod` | One named period (on-peak / off-peak / super-off-peak) |
| `TimeWindow` | A `[start, end)` clock-time range within a `TimeOfUsePeriod` |
| `DemandCharge` | Peak kW demand charge |
| `EligibilityRule` | Informational eligibility requirement |
| `Adjustment` | Informational billing adjustment |
| `Commodity` | `ELECTRICITY` / `GAS` enum |
| `UsageUnit` | `KWH` / `THERM` enum |
| `Season` | `SUMMER` / `WINTER` enum |

### `rates.py` — Rate plan catalog

Declarative, hard-coded definitions of all current Dominion Energy SC residential tariffs (effective July 1, 2026). No network calls, no parsing — purely data. The plan constants (`RATE_2`, `RATE_5`, etc.) are assembled from types defined in `models/rate_plan.py` and stored in three read-only `MappingProxyType` dicts:

| Name | Contents |
|------|----------|
| `RESIDENTIAL_ELECTRIC_RATE_PLANS` | Rate 2, 5, 6, 7, 8 — keyed by code string |
| `RESIDENTIAL_GAS_RATE_PLANS` | Rate 32S, 32V — keyed by code string |
| `RESIDENTIAL_RATE_PLANS` | All of the above merged |

**Lookup functions:** `get_rate_plan(code)` returns a `RatePlan | None`; `get_available_rate_plans()` returns a `tuple[RatePlan, ...]` of all plans.

**Rate plan breakdown:**

| Constant | Code | Commodity | Summary |
|----------|------|-----------|---------|
| `RATE_2` | `"rate_2"` | Electric | Low Use — flat rate; requires ≤400 kWh each of the prior 12 billing periods |
| `RATE_5` | `"rate_5"` | Electric | Time of Use — three price tiers by time-of-day, varies summer/winter |
| `RATE_6` | `"rate_6"` | Electric | Energy Saver — tiered rate for energy-efficient homes meeting insulation/equipment requirements |
| `RATE_7` | `"rate_7"` | Electric | TOU Demand — time-of-use energy rate plus a kW demand charge |
| `RATE_8` | `"rate_8"` | Electric | Standard — tiered (two tiers per season); the default plan for most residential customers |
| `RATE_32S` | `"rate_32s"` | Gas | Standard Gas — monthly fixed + flat per-therm rate |
| `RATE_32V` | `"rate_32v"` | Gas | Value Gas — lower per-therm rate; requires ≥10 therm average in June/July/August |

### `models/rate_plan.py` — Rate plan type system

Defines all the dataclasses and enums that compose a `RatePlan`. All types are frozen (`frozen=True`) and slotted (`slots=True`). The `Charge` type alias is a discriminated union of the six concrete charge types, keyed on the `kind` literal field:

```
RatePlan
├── charges: tuple[Charge, ...]
│   ├── DailyCharge          kind="daily"       — fixed $/day
│   ├── MonthlyCharge        kind="monthly"     — fixed $/cycle
│   ├── FlatUsageCharge      kind="flat_usage"  — uniform $/kWh or $/therm
│   ├── TieredUsageCharge    kind="tiered_usage"— tiered blocks, varies by Season
│   │   └── tiers_by_season: {Season → tuple[UsageTier, ...]}
│   ├── TimeOfUseCharge      kind="time_of_use" — rate by time-of-day, varies by Season
│   │   └── periods_by_season: {Season → tuple[TimeOfUsePeriod, ...]}
│   │       └── TimeOfUsePeriod
│   │           └── windows: tuple[TimeWindow, ...]
│   └── DemandCharge         kind="demand"      — $/kW of peak demand
├── eligibility_rules: tuple[EligibilityRule, ...]  — informational
└── adjustments: tuple[Adjustment, ...]             — informational
```

**Enums:**
- `Commodity` — `ELECTRICITY` / `GAS` (StrEnum values: `"electricity"` / `"gas"`)
- `UsageUnit` — `KWH` / `THERM` (StrEnum values: `"kWh"` / `"therm"`)
- `Season` — `SUMMER` / `WINTER` (StrEnum values: `"summer"` / `"winter"`)

### `cli.py` — Command-line interface

Separated from `__main__.py` so it can be imported and tested without running argparse or `asyncio.run()`. `build_parser()` returns an `argparse.ArgumentParser`. `run(args)` is the async main function. `main()` is the entry point called by `__main__.py`.

### `helpers.py`

Single function: `create_cookie_jar()`. Always pass the result to `aiohttp.ClientSession`. See the function docstring for why `quote_cookie=False` is required.

---

## Testing

The test suite is in `tests/` and uses `pytest` with `pytest-asyncio` (in `auto` mode).

```bash
# Run all tests with coverage
uv run pytest

# Run a specific file
uv run pytest tests/test_parsers.py -v

# Run tests matching a name pattern
uv run pytest -k "login" -v

# Show coverage report in terminal
uv run pytest --cov=dominionsc --cov-report=term-missing
```

### Test categories

| File | What it tests | How |
|------|---------------|-----|
| `test_dominionsc.py` | `DominionSC`, `DominionSCURLHandler`, `DominionSCTFAHandler` | Mocks HTTP via `AsyncMock`/`patch` |
| `test_parsers.py` | `parse_registers()`, `parse_usage_reads()`, `parse_forecast()` | Pure/fixture-based |
| `test_cli.py` | `build_parser()`, `run()`, `_handle_mfa()` | Mocked async |
| `test_rates.py` | Rate plan catalog | Pure assertions |
| `test_helpers.py` | `create_cookie_jar()` | Pure assertions |
| `test_headers.py` | All header builder functions | Pure assertions |
| `test_urls.py` | All URL builder functions | Pure assertions with mocked `cache_buster` |
| `test_config.py` | `UtilityConfig`, `DEFAULT_CONFIG` | Pure assertions |
| `test_account.py` | `AccountInfo`, `to_legacy_list()` | Pure assertions |
| `test_transport.py` | `cache_buster()` | Pure assertions |
| `test_exceptions_coverage.py` | Exception `__str__` formatting | Pure assertions |
| `test_main_coverage.py` | `python -m dominionsc` entry point | Mock |

### Test fixtures

`tests/fixtures/greenbutton_multi_register.xml` is a redacted real-structure Green Button XML with two UsagePoints (grid delivery and solar export). Use it to test multi-register parsing. If you add new parsing behaviour, add a corresponding fixture or extend the XML.

### Mocking HTTP

Tests mock HTTP at the `DominionSCURLHandler.call_api` level for the login/forecast flows, and at `session.get` for the usage reads flow. See the existing tests in `test_dominionsc.py` for examples of the required `AsyncMock` setup.

---

## Common maintenance tasks

### Update the User-Agent string

If the Dominion portal starts rejecting requests, update `USER_AGENT` in `src/dominionsc/const.py`. Copy the value from your browser's DevTools (Network tab → any Dominion request → Request Headers → `User-Agent`).

### Add a new endpoint

1. Add the URL builder function in `src/dominionsc/urls.py`. Follow the existing function signature: `def my_endpoint_url(config: UtilityConfig) -> str:`.
2. Add the corresponding header dict function in `src/dominionsc/headers.py` if the endpoint needs different headers from existing builders.
3. Call the new URL and header functions from `auth.py` or `client.py` as appropriate.
4. Add a test in `tests/test_dominionsc.py` that mocks the new HTTP call.

### Add a new model field

1. Add the field to the dataclass in `src/dominionsc/models/`.
2. Update the parser that populates the model (`parsers/forecast.py` or `parsers/greenbutton.py`).
3. Update any tests that assert on the model's fields.
4. Add the new field to the public documentation in `docs/api-reference.md`.

### Update rate plans

Rate plans are defined in `src/dominionsc/rates.py` using types from `src/dominionsc/models/rate_plan.py`. Dominion Energy SC typically publishes updated tariffs on July 1 each year.

**When rates change (price adjustments only):**

1. Update `_EFFECTIVE_FROM = date(YYYY, 7, 1)` at the top of `rates.py`.
2. Update the `Decimal` amounts in the affected `RATE_*` constants (e.g., `DailyCharge(amount=Decimal("0.36164"))`).
3. Update `tests/test_rates.py` — find the assertions for the changed plan and update the expected values.

**When a new charge type or structure is added:**

1. If the new structure doesn't map to any existing `Charge` subclass, add a new frozen dataclass in `models/rate_plan.py` following the existing pattern (add a `kind: Literal["..."]` discriminant field).
2. Add the new type to the `Charge` type alias in `models/rate_plan.py`.
3. Export the new type from `src/dominionsc/__init__.py` and add it to `__all__`.
4. Use the new type in the relevant `RATE_*` constant in `rates.py`.
5. Add tests in `test_rates.py`.
6. Document the new type in `docs/api-reference.md` under the Charge union table.

**When a new plan is added:**

1. Define a new `RATE_XX = RatePlan(...)` constant in `rates.py`.
2. Add it to the appropriate dict (`RESIDENTIAL_ELECTRIC_RATE_PLANS` or `RESIDENTIAL_GAS_RATE_PLANS`).
3. Export the new constant from `__init__.py` and `__all__`.
4. Add tests in `test_rates.py`.
5. Document it in `docs/api-reference.md` under the rate plan catalog table.

**When a plan is removed or superseded:**

1. Remove the constant from `rates.py` and from the relevant dict.
2. Remove the export from `__init__.py` and `__all__`.
3. If the `effective_to` date is known, set it rather than deleting the constant — this preserves the historical record.
4. Update `tests/test_rates.py` and `docs/api-reference.md`.

Rate plans are purely declarative data — changing them does not affect the API communication logic.

### Add TFA support for a new delivery method

The `DominionSCTFAHandler.async_get_tfa_options()` method currently maps phone numbers and email addresses from the API response to a `dict[str, str]`. If Dominion adds new TFA delivery methods (e.g., authenticator apps), update that method in `src/dominionsc/auth.py` to include the new option.

### Debug a login failure

1. Run the CLI with `-vv` for debug-level logging: `python -m dominionsc -vv`
2. Check the exception type and the `url`/`response_text` fields:
   - `CannotConnect` → network issue (DNS, timeout, TLS)
   - `InvalidAuth` → wrong credentials or multi-account setup
   - `ApiException` → the API response structure has changed; compare `response_text` to the parser code
   - `MfaChallenge` → expected; the caller must handle TFA interactively

---

## Important design decisions

### Why two APIs?

Dominion Energy SC uses Bidgely as a third-party energy analytics platform. The customer portal handles authentication, account management, and bill forecasts. Actual metering data (15-minute interval reads) is stored and served by Bidgely. The login sequence must bridge both systems: Dominion issues an encrypted token that Bidgely accepts to issue a Bearer token.

### Why `quote_cookie=False`?

`aiohttp`'s default `CookieJar` percent-encodes characters in cookie values. Dominion's session cookies contain raw `=` characters that must not be encoded. Using `quote_cookie=False` preserves the exact cookie value that the server sends. Always use `create_cookie_jar()` when constructing the `aiohttp.ClientSession`.

### Why keep the `[[types], address]` return format?

`async_get_accounts()` returns a heterogeneous list (`[list[str], str]`) rather than the `AccountInfo` dataclass that the login flow now uses internally. This is intentional backward compatibility for `ha-dominion-sc`, which destructures the return as `accounts, service_addr = await api.async_get_accounts()`. Changing this return type is a breaking change and requires a coordinated update to the consumer.

### Why separate `parse_registers` from `parse_usage_reads`?

Solar/net-metered accounts have two physical registers in the same API response: one for grid delivery (positive values) and one for solar export (negative values). Merging them with `parse_usage_reads` produces overlapping timestamps and mixed signs with no way to distinguish the registers. `parse_registers` keeps them separate so consumers can handle each register independently.

### Why is `flow_direction` in `RegisterReads` but unreliable?

The ESPI specification includes a `flowDirection` field to indicate whether a register measures delivered or generated energy. Dominion Energy SC reports `flowDirection=1` for both the grid-delivery and solar-export registers, making it useless for distinguishing them. The field is preserved in case other utilities' data populates it correctly, but Dominion Energy SC consumers must not rely on it.

---

## Known limitations and technical debt

| Issue | Location | Notes |
|-------|----------|-------|
| Usage reads use `session.get` directly rather than `DominionSCURLHandler` | `client.py:_async_get_request` | Pre-existing inconsistency; changing it requires updating test mocks |
| `async_get_accounts()` returns a legacy list format | `client.py` | Needs coordinated breaking-change update with `ha-dominion-sc` |
| Single-account constraint is hard-coded | `auth.py` | Multi-account support unknown; report if you encounter it |
| TFA is always expected | `auth.py` | Accounts without TFA raise `InvalidAuth`; report if you encounter it |
| Bidgely pilot ID is hard-coded | `const.py` | Ideally discovered per-account; see note in `const.py` |
| Data is delayed 24–48 hours | External | Bidgely's metering pipeline delay; nothing the library can change |
