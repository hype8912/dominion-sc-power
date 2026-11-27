# API Reference

This document covers the complete public API of the `dominionsc` package. Everything listed here is importable directly from `dominionsc`.

---

## Table of Contents

1. [DominionSC — main client](#dominionsc--main-client)
2. [DominionSCTFAHandler — TFA handler](#dominionsctfahandler--tfa-handler)
3. [Data models](#data-models)
   - [UsageRead](#usageread)
   - [RegisterReads](#registerreads)
   - [Forecast](#forecast)
4. [Exceptions](#exceptions)
5. [Rate plans](#rate-plans)
   - [RatePlan and related types](#rateplan-and-related-types)
   - [Rate plan catalog](#rate-plan-catalog)
   - [Catalog lookup functions](#catalog-lookup-functions)
   - [Time-of-use rate lookup](#time-of-use-rate-lookup)
6. [Pricing usage](#pricing-usage)
   - [Utility-local time](#utility-local-time)
   - [`resolve_plan_for()`](#resolve_plan_for)
   - [Units](#units)
   - [`rate_at()` and `price_usage()`](#rate_at-and-price_usage) (and `price_net_usage()`)
   - [Billing cycles and `UsagePricer`](#billing-cycles-and-usagepricer)
7. [Utilities](#utilities)

---

## DominionSC — main client

```python
from dominionsc import DominionSC
```

`DominionSC` is the primary entry point for all library operations. Create one instance per session.

### Constructor

```python
DominionSC(
    session: aiohttp.ClientSession,
    username: str,
    password: str,
    login_data: dict[str, str] | None = None,
    pilot_id: str | None = None,
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session` | `aiohttp.ClientSession` | An aiohttp session created with `create_cookie_jar()`. The library uses this session for all HTTP requests and does not close it. |
| `username` | `str` | The email address or username for `account.dominionenergysc.com`. |
| `password` | `str` | The account password. |
| `login_data` | `dict[str, str] \| None` | Optional saved TFA token from a previous successful MFA flow. Pass `{"tfa_token": "<token>"}` to skip interactive TFA. Default: `None`. |
| `pilot_id` | `str \| None` | Override for the Bidgely multi-tenant pilot ID (see `const.BIDGELY_PILOT_ID`). Defaults to the library's known-good value for Dominion Energy SC; only needs overriding if Dominion re-routes accounts to a different Bidgely pipeline. Default: `None`. |

**Important:** Always create the session with `cookie_jar=create_cookie_jar()`:

```python
import aiohttp
from dominionsc import DominionSC, create_cookie_jar

async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
    client = DominionSC(session, username, password)
```

---

### `async_login()`

```python
await client.async_login() -> None
```

Log in to the Dominion Energy SC portal. This method must be called before any data retrieval method.

**Raises:**

| Exception | Reason |
|-----------|--------|
| `MfaChallenge` | TFA is required and no valid `login_data` was provided. The exception carries a `DominionSCTFAHandler` — see [DominionSCTFAHandler](#dominionsctfahandler--tfa-handler) for the TFA flow. |
| `InvalidAuth` | Wrong username or password, or multi-account setup not supported. |
| `CannotConnect` | Network failure or timeout. Retryable. |
| `ApiException` | The API response structure has changed unexpectedly. |

**Example — with TFA handling:**

```python
from dominionsc import DominionSC, MfaChallenge, InvalidAuth, create_cookie_jar
import aiohttp

async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
    client = DominionSC(session, "user@example.com", "hunter2")
    try:
        await client.async_login()
    except MfaChallenge as challenge:
        handler = challenge.handler
        options = await handler.async_get_tfa_options()
        await handler.async_select_tfa_option(list(options)[0])
        code = input("Enter security code: ")
        login_data = await handler.async_submit_tfa_code(code)
        client.login_data = login_data  # update for retry
        await client.async_login()
    except InvalidAuth as err:
        print(f"Bad credentials: {err}")
```

---

### `async_get_accounts()`

```python
await client.async_get_accounts() -> list
```

Return the list of active measurement types and the service address/account number.

**Returns:** `[measurement_types, service_address]` where:

- `measurement_types` is `list[str]` — the measurement types active for this account (e.g., `["ELECTRIC"]` or `["ELECTRIC", "GAS"]`).
- `service_address` is `str` — the service address and account number string (e.g., `"123 MAIN ST (*-****-****0-1234)"`).

**Usage:**

```python
measurement_types, service_address = await client.async_get_accounts()
print(f"Service at: {service_address}")
for mtype in measurement_types:  # "ELECTRIC" or "GAS"
    ...
```

**Note:** This method returns a legacy two-element list for backward compatibility with the `ha-dominion-sc` Home Assistant integration. Must be called after `async_login()`.

---

### `async_get_forecast()`

```python
await client.async_get_forecast() -> Forecast
```

Retrieve the current billing period's usage and cost forecast.

**Returns:** A [`Forecast`](#forecast) dataclass.

**Raises:** `InvalidAuth`, `CannotConnect`, `ApiException`.

**Example:**

```python
forecast = await client.async_get_forecast()
print(f"Bill period: {forecast.start_date} to {forecast.end_date}")
print(f"Cost to date: ${forecast.cost_to_date:.2f}")
print(f"Projected total: ${forecast.forecasted_cost:.2f}")
if forecast.typical_cost is not None:
    print(f"Last year typical: ${forecast.typical_cost:.2f}")
```

---

### `async_get_register_reads()`

```python
await client.async_get_register_reads(
    account: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[RegisterReads]
```

Retrieve interval meter readings grouped by physical register (ESPI UsagePoint). This is the preferred method for fetching usage data because it preserves per-register separation.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `account` | `str` | The measurement type to query: `"ELECTRIC"` or `"GAS"`. Use values from `measurement_types` returned by `async_get_accounts()`. |
| `start_date` | `datetime \| None` | Start of the requested window. Required despite the `None` default (see **Raises**). The time component is ignored — the library floors to midnight in the utility's local timezone. |
| `end_date` | `datetime \| None` | End of the requested window. Required; the same flooring applies. |

**Returns:** `list[RegisterReads]` — one `RegisterReads` per distinct ESPI UsagePoint. Most accounts return a one-element list. Net-metered solar accounts return two elements (grid delivery and solar export).

**Raises:** `ValueError` if `start_date` or `end_date` is `None`. `InvalidAuth` if called before a successful `async_login()`. `CannotConnect`, `ApiException`.

**Example:**

```python
from datetime import datetime, timedelta

start = datetime.now() - timedelta(days=7)
end = datetime.now()

registers = await client.async_get_register_reads("ELECTRIC", start, end)
for reg in registers:
    print(f"Register: {reg.usage_point_id}")
    for read in reg.reads:
        print(f"  {read.start_time}: {read.consumption} Wh")
```

**Solar note:** Solar-export registers carry **negative** `consumption` values. The library does not label registers as "grid" or "solar" — use the stable `usage_point_id` to distinguish them in your application.

**Days with no data yet:** the most recent day or days, whose readings Dominion hasn't published yet, are
**absent** from the result. They are not returned as zero-valued readings (confirmed against a live capture on
2026-11-27, see `tests/fixtures/greenbutton_gas_recent.xml`). Every day that is returned is complete. A day whose
readings are all zero is a real no-usage day, common for gas in summer, and must not be treated as "not available
yet".

---

### `async_get_usage_reads()`

```python
await client.async_get_usage_reads(
    account: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[UsageRead]
```

Retrieve interval meter readings as a flat list, merging all registers.

**Returns:** `list[UsageRead]` — all readings from all registers concatenated.

**Warning:** For net-metered solar accounts, this merges grid-delivery and solar-export readings into one list with overlapping timestamps. Use `async_get_register_reads()` instead if per-register separation matters.

**Raises:** The same exceptions as [`async_get_register_reads()`](#async_get_register_reads): `ValueError`, `InvalidAuth`, `CannotConnect`, `ApiException`.

---

### `get_timezone()`

```python
client.get_timezone() -> str
```

Return the utility's local IANA timezone name (e.g., `"America/New_York"`).

---

## DominionSCTFAHandler — TFA handler

```python
from dominionsc import DominionSCTFAHandler
```

You do not instantiate `DominionSCTFAHandler` directly. It is provided to you via the `MfaChallenge` exception's `handler` attribute:

```python
try:
    await client.async_login()
except MfaChallenge as challenge:
    handler = challenge.handler  # DominionSCTFAHandler instance
```

---

### `async_get_tfa_options()`

```python
await handler.async_get_tfa_options() -> dict[str, str]
```

Return available TFA delivery options for the account.

**Returns:** `dict[str, str]` mapping option ID to human-readable description. Empty dict if no options are configured (the portal goes straight to code entry).

**Example response:** `{"******1234": "******1234", "us**@example.com": "us**@example.com"}`

**Raises:** `ApiException`.

---

### `async_select_tfa_option()`

```python
await handler.async_select_tfa_option(option_id: str) -> None
```

Trigger delivery of a TFA code to the selected option (SMS or email).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `option_id` | `str` | A key from the dict returned by `async_get_tfa_options()`. |

**Raises:** `ApiException` if the selection fails.

---

### `async_submit_tfa_code()`

```python
await handler.async_submit_tfa_code(code: str) -> dict[str, str]
```

Submit the security code the user received.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `code` | `str` | The numeric security code from SMS or email. |

**Returns:** On success, `{"tfa_token": "<token>"}` — save this dict and pass it as `login_data` to the next `DominionSC()` constructor call to skip TFA.

**Raises:** `InvalidAuth` if the code is incorrect. `ApiException` if the response cannot be parsed.

**Saving the token for future logins:**

```python
import json

login_data = await handler.async_submit_tfa_code(code)

# Save to file
with open("login_data.json", "w") as f:
    json.dump(login_data, f)

# Next time, load it and pass to DominionSC
with open("login_data.json") as f:
    saved = json.load(f)
client = DominionSC(session, username, password, login_data=saved)
```

---

## Data models

### UsageRead

```python
from dominionsc import UsageRead
```

A single interval meter reading.

| Field | Type | Description |
|-------|------|-------------|
| `start_time` | `datetime` | Timezone-aware start of the measurement interval. |
| `end_time` | `datetime` | Timezone-aware end of the interval (inclusive; one second before the next interval's start). |
| `consumption` | `float` | Energy or volume consumed, in `unit`. **Electric:** Watt-hours (Wh). **Gas:** Cubic feet (ft³). **Solar export:** Negative Wh values. Use [`to_billing_units()`](#units) or [`price_usage()`](#rate_at-and-price_usage) rather than converting by hand. |
| `unit` | `MeterUnit \| None` | Unit of `consumption`, from the feed's `espi:uom` (`72` → `WATT_HOUR`, `119` → `CUBIC_FOOT`). `None` when the feed declares no unit, an unknown one (logged as a warning once per feed), or several. Added in 0.4.0; last field with a default, so positional construction is unchanged. |

**Interval length:** Dominion Energy SC reports 15-minute intervals for electric accounts. Gas intervals are typically 1 hour.

---

### RegisterReads

```python
from dominionsc import RegisterReads
```

Interval readings grouped by physical meter register (ESPI UsagePoint).

| Field | Type | Description |
|-------|------|-------------|
| `usage_point_id` | `str` | Stable ESPI UsagePoint identifier. Confirmed constant across separate exports. Safe to use as a persistent key (e.g., for Home Assistant statistic IDs). |
| `flow_direction` | `str \| None` | ESPI `flowDirection` from the register's `ReadingType`. **Unreliable for Dominion Energy SC** — both grid and solar registers report `flowDirection=1`. Do not use this to distinguish registers. |
| `reads` | `list[UsageRead]` | Interval readings for this register in the order encountered. |
| `unit` | `MeterUnit \| None` | Unit of every reading's `consumption` (same rules as `UsageRead.unit`). Added in 0.4.0. |

**Usage:**

```python
for register in registers:
    print(f"Register ID: {register.usage_point_id}")
    print(f"Reading count: {len(register.reads)}")
    for read in register.reads:
        print(f"  {read.start_time}: {read.consumption}")
```

---

### Forecast

```python
from dominionsc import Forecast
```

Bill forecast for the current monthly billing period.

| Field | Type | Description |
|-------|------|-------------|
| `start_date` | `date` | First day of the current billing period. |
| `end_date` | `date` | Projected last day of the billing period. |
| `current_date` | `date` | Most recent date included in `cost_to_date` (1–2 days behind real time). |
| `cost_to_date` | `float` | Dollar cost accrued from `start_date` through `current_date`. |
| `forecasted_cost` | `float` | Projected total dollar cost for the full billing period. |
| `typical_cost` | `float \| None` | Last year's total for the equivalent billing period, or `None` if unavailable. |

---

## Exceptions

```python
from dominionsc import CannotConnect, InvalidAuth, MfaChallenge, ApiException
```

### `CannotConnect`

Raised when a network-level failure prevents the request from completing. This is a **retryable** exception — the server may be temporarily unavailable.

| Attribute | Type | Description |
|-----------|------|-------------|
| `url` | `str \| None` | The URL that was being requested. |
| `status` | `int \| None` | HTTP status code, if a response was received. |
| `response_text` | `str \| None` | Response body text, if available. |

`str(err)` returns the message followed by the URL, status, and response text on separate lines, for whichever of those are set.

### `InvalidAuth`

Raised when credentials are wrong, a session has expired, or a multi-account setup is encountered. **Not retryable** without correcting the underlying issue.

### `MfaChallenge`

Raised when TFA is required and no valid saved token exists.

| Attribute | Type | Description |
|-----------|------|-------------|
| `handler` | `DominionSCTFAHandler` | Use this to interactively complete the TFA flow. |

### `ApiException`

Raised when the API returns a response (network was fine) but the response cannot be parsed because its structure has changed. This usually means the Dominion or Bidgely API has changed and the library needs updating.

| Attribute | Type | Description |
|-----------|------|-------------|
| `url` | `str \| None` | The URL whose response triggered the error. |
| `status` | `int \| None` | HTTP status code. |
| `response_text` | `str \| None` | Raw response body for debugging. Not every error sets it (for example, forecast structure errors carry only the URL). |

**Recommended exception handling pattern:**

```python
from dominionsc import CannotConnect, InvalidAuth, MfaChallenge, ApiException

try:
    await client.async_login()
    forecast = await client.async_get_forecast()
except MfaChallenge as challenge:
    # Handle interactively (see DominionSCTFAHandler section)
    ...
except InvalidAuth as err:
    # Bad credentials — do not retry without fixing them
    print(f"Auth failed: {err}")
except CannotConnect as err:
    # Network issue — safe to retry after a delay
    print(f"Could not reach server at {err.url}: {err}")
except ApiException as err:
    # API structure changed — library needs updating
    print(f"Unexpected API response from {err.url}")
    print(f"Response body: {err.response_text}")
```

---

## Rate plans

### RatePlan and related types

```python
from dominionsc import (
    RatePlan,
    Charge,
    DailyCharge,
    MonthlyCharge,
    FlatUsageCharge,
    TieredUsageCharge,
    TimeOfUseCharge,
    DemandCharge,
    UsageTier,
    TimeOfUsePeriod,
    TimeWindow,
    Holiday,
    EligibilityRule,
    Adjustment,
    Commodity,
    UsageUnit,
    Season,
)
```

#### `RatePlan`

| Field | Type | Description |
|-------|------|-------------|
| `code` | `str` | Short identifier (e.g., `"rate_8"`). Key in `RESIDENTIAL_RATE_PLANS`. |
| `name` | `str` | Official tariff name. |
| `commodity` | `Commodity` | `Commodity.ELECTRICITY` or `Commodity.GAS`. |
| `effective_from` | `date` | First date this rate is effective. |
| `effective_to` | `date \| None` | Last effective date, or `None` if still current. |
| `charges` | `tuple[Charge, ...]` | Ordered charge components. |
| `eligibility_rules` | `tuple[EligibilityRule, ...]` | Eligibility requirements (informational). |
| `adjustments` | `tuple[Adjustment, ...]` | Billing adjustments (informational). |
| `description` | `str` | Optional free-text description. |
| `source_url` | `str` | Link to the published tariff document this plan was transcribed from, for future reference. Empty string when not recorded. |

`RatePlan.closed_to_new_customers` (property, added in 0.4.0) is `True` when the plan has a `closed_to_new_customers`
eligibility rule. Only Rate 1 does.

#### `Charge` union type

The `Charge` type alias represents any of six concrete charge classes:

| Class | `kind` discriminant | Description |
|-------|---------------------|-------------|
| `DailyCharge` | `"daily"` | Fixed charge per service day. |
| `MonthlyCharge` | `"monthly"` | Fixed charge per billing cycle. |
| `FlatUsageCharge` | `"flat_usage"` | Uniform price per unit of consumption. |
| `TieredUsageCharge` | `"tiered_usage"` | Tiered pricing that can vary by season. |
| `TimeOfUseCharge` | `"time_of_use"` | Price depends on time of day and season. |
| `DemandCharge` | `"demand"` | Charge based on peak measured demand (kW). |

**Dispatching on charge type:**

```python
for charge in rate_plan.charges:
    match charge.kind:
        case "daily":
            # charge is DailyCharge
            monthly_fixed = charge.amount * days_in_period
        case "tiered_usage":
            # charge is TieredUsageCharge
            summer_tiers = charge.tiers_by_season[Season.SUMMER]
        case "time_of_use":
            # charge is TimeOfUseCharge; price each interval by its local start time
            rate = get_time_of_use_rate(rate_plan, interval_start)
            energy_cost = rate.price_per_kwh * interval_kwh
```

#### `TieredUsageCharge.tiers_by_season`

Maps `Season.SUMMER` and `Season.WINTER` to a tuple of `UsageTier`:

```python
tiered = next(c for c in rate_plan.charges if c.kind == "tiered_usage")  # TieredUsageCharge
summer_tiers = tiered.tiers_by_season[Season.SUMMER]
for tier in summer_tiers:
    print(f"{tier.name}: ${tier.price_per_unit}/kWh up to {tier.upper_bound or '∞'} kWh")
```

#### `TimeOfUseCharge.periods_by_season`

Maps `Season` to a tuple of `TimeOfUsePeriod`:

```python
tou = next(c for c in rate_plan.charges if c.kind == "time_of_use")  # TimeOfUseCharge
summer_periods = tou.periods_by_season[Season.SUMMER]
for period in summer_periods:
    if period.fallback:
        print(f"{period.name}: ${period.price_per_unit}/kWh (all other hours)")
    else:
        for window in period.windows:
            print(f"{period.name}: ${period.price_per_unit}/kWh from {window.start} to {window.end}")
```

A period can also be limited by day. `weekdays_only` restricts its windows to Monday-Friday, and `excluded_holidays`
(a tuple of `Holiday`) removes the named holidays; `period.applies_on(local_date)` reports whether a period is in
force on a date. Intervals on days a period does not apply to are billed by the other periods, ending with the
fallback period. Rate 5 and Rate 7 tariffs before July 2026 use this for on-peak; the July 2026 tariffs apply
on-peak every day.

To price an interval, use `get_time_of_use_rate(plan, interval_start)` rather than matching periods yourself. It
applies the season, the windows, and these day rules in one call (see
[Time-of-use rate lookup](#time-of-use-rate-lookup)):

```python
rate = get_time_of_use_rate(plan, datetime(2025, 11, 27, 7))  # Thanksgiving, 7 AM
rate.period  # "off_peak": the 2025 tariff drops on-peak on holidays
```

`Holiday.date_in(year)` returns a holiday's date. It is the holiday's actual date; the tariffs describe no observed date.

#### `Commodity`

```python
Commodity.ELECTRICITY  # value: "electricity"
Commodity.GAS  # value: "gas"
```

#### `UsageUnit`

```python
UsageUnit.KWH  # value: "kWh"
UsageUnit.THERM  # value: "therm"
```

#### `Season`

```python
Season.SUMMER  # value: "summer"
Season.WINTER  # value: "winter"
```

Dominion Energy SC's published tariffs define summer as **billing months May through September** and winter as **billing months October through April** — the wording printed on each seasonal rate schedule (Rates 5, 6, 7 and 8). `season_for(day)` maps a date to a season by its **calendar** month, which is what `get_time_of_use_rate` uses (see [Time-of-use rate lookup](#time-of-use-rate-lookup)). To follow the tariff wording exactly, check the billing month against these ranges instead and select the matching `tiers_by_season` or `periods_by_season` entry yourself.

Getting this boundary wrong is a silent mispricing rather than an error: the two seasons share the same first-800 kWh price, so a wrong month mapping only shows up above 800 kWh, where the summer and winter rates diverge.

---

### Rate plan catalog

```python
from dominionsc import (
    RATE_1,
    RATE_2,
    RATE_5,
    RATE_6,
    RATE_7,
    RATE_8,  # Electric plans
    RATE_32S,
    RATE_32V,  # Gas plans
    RESIDENTIAL_ELECTRIC_RATE_PLANS,
    RESIDENTIAL_GAS_RATE_PLANS,
    RESIDENTIAL_RATE_PLANS,
)
```

#### Residential electric plans (effective July 1, 2026)

| Constant | Code | Name |
|----------|------|------|
| `RATE_1` | `"rate_1"` | Rate 1 — Residential Service: Good Cents Rate (tiered; closed to new customers since 1996, grandfathered dwellings only) |
| `RATE_2` | `"rate_2"` | Rate 2 — Low Use Residential Service (flat rate, ≤400 kWh/month) |
| `RATE_5` | `"rate_5"` | Rate 5 — Residential Service: Time of Use |
| `RATE_6` | `"rate_6"` | Rate 6 — Residential Service: Energy Saver/Conservation Rate (tiered, energy-efficient homes) |
| `RATE_7` | `"rate_7"` | Rate 7 — Residential Service: Time-of-Use Demand (TOU + demand charge) |
| `RATE_8` | `"rate_8"` | Rate 8 — Residential Service (standard tiered, default plan) |

#### Residential gas plans (effective July 1, 2026)

| Constant | Code | Name |
|----------|------|------|
| `RATE_32S` | `"rate_32s"` | Rate 32S — Gas Residential Standard Service |
| `RATE_32V` | `"rate_32v"` | Rate 32V — Gas Residential Value Service (lower rate, ≥10 therm/month average summer usage) |

#### Catalog mappings

| Name | Type | Contents |
|------|------|----------|
| `RESIDENTIAL_ELECTRIC_RATE_PLANS` | `Mapping[str, RatePlan]` | All electric plans keyed by code. Read-only. |
| `RESIDENTIAL_GAS_RATE_PLANS` | `Mapping[str, RatePlan]` | All gas plans keyed by code. Read-only. |
| `RESIDENTIAL_RATE_PLANS` | `Mapping[str, RatePlan]` | All plans (electric + gas) keyed by code. Read-only. |
| `RATE_PLAN_HISTORY` | `Mapping[str, tuple[RatePlan, ...]]` | Every known tariff period per code, oldest first; the last entry is the current plan. Codes with no superseded periods map to a one-element tuple. Read-only. |

#### Superseded tariff periods

```python
from dominionsc import (
    RATE_1_2025,
    RATE_2_2025,
    RATE_5_2024,
    RATE_5_2025,
    RATE_6_2025,
    RATE_7_2025,
    RATE_8_2025,
    RATE_32S_2025,
    RATE_32V_2025,
    RATE_PLAN_HISTORY,
)
```

| Constant | Code | Effective |
|----------|------|-----------|
| `RATE_1_2025` | `"rate_1"` | 2025-07-23 to 2026-06-30 |
| `RATE_2_2025` | `"rate_2"` | 2025-07-23 to 2026-06-30 |
| `RATE_5_2024` | `"rate_5"` | 2024-09-01 to 2025-04-30 |
| `RATE_5_2025` | `"rate_5"` | 2025-05-01 to 2026-06-30 |
| `RATE_6_2025` | `"rate_6"` | 2025-07-23 to 2026-06-30 |
| `RATE_7_2025` | `"rate_7"` | 2025-07-23 to 2026-06-30 |
| `RATE_8_2025` | `"rate_8"` | 2025-07-23 to 2026-06-30 |
| `RATE_32S_2025` | `"rate_32s"` | 2025-09-01 to 2026-06-30 |
| `RATE_32V_2025` | `"rate_32v"` | 2025-09-01 to 2026-06-30 |

These carry `effective_to` and a `source_url`. Each is a complete plan: the Basic Facilities Charge, the Distributed Energy Resource Program charge (electric plans), the usage / time-of-use / demand charges, and the adjustments. Rate 5's May 2025 tariff and July 23, 2025 revision publish the same prices, so they are the single period `RATE_5_2025`; the May tariff gives no calendar date ("first billing cycle of May 2025"), so it starts on 2025-05-01. Rate 32V's tariff is likewise effective from the "1st billing cycle of September 2025", so `RATE_32V_2025` starts on 2025-09-01, as does `RATE_32S_2025`. Dates before a schedule's earliest recorded period return `None`. They are **not** included in `RESIDENTIAL_*_RATE_PLANS`, `get_rate_plan()`, or `get_available_rate_plans()`; reach them through `RATE_PLAN_HISTORY` or the lookup functions below.

---

### Catalog lookup functions

#### `get_rate_plan()`

```python
from dominionsc import get_rate_plan

plan = get_rate_plan("rate_8")  # -> RatePlan | None
```

Look up a rate plan by its code string. Returns `None` for unknown codes.

#### `get_available_rate_plans()`

```python
from dominionsc import get_available_rate_plans

plans = get_available_rate_plans()  # -> tuple[RatePlan, ...]
for plan in plans:
    print(f"{plan.code}: {plan.name} ({plan.commodity})")
```

Return all cataloged residential rate plans as a tuple. Only current plans
are returned; superseded tariff periods are available via the history lookups
below.

#### `get_rate_plan_history()`

```python
from dominionsc import get_rate_plan_history

get_rate_plan_history("rate_8")  # -> (RATE_8_2025, RATE_8)
get_rate_plan_history("rate_5")  # -> (RATE_5_2024, RATE_5_2025, RATE_5)
```

Return every known tariff period for a rate code as a tuple, oldest first. The
last entry is the current plan. Returns an empty tuple for unknown codes.
See [Superseded tariff periods](#superseded-tariff-periods) for the archived
entries.

#### `get_rate_plan_for_date()`

```python
from datetime import date
from dominionsc import get_rate_plan_for_date

plan = get_rate_plan_for_date("rate_8", date(2025, 9, 1))  # -> RatePlan | None
```

Return the plan for a code that was in effect on the given date. Period
boundaries are inclusive: a plan applies from `effective_from` through
`effective_to`, and a plan with `effective_to=None` applies from `effective_from`
onward. Returns `None` when the code is unknown or the date falls before the
earliest recorded period (or in a gap between periods). For example,
`get_rate_plan_for_date("rate_2", date(2025, 7, 1))` is `None` because `rate_2`'s
earliest recorded period starts on July 23, 2025.

### Time-of-use rate lookup

```python
from datetime import datetime
from dominionsc import get_rate_plan_for_date, get_time_of_use_rate, season_for

when = datetime(2025, 11, 27, 7, 0)  # Thanksgiving morning
plan = get_rate_plan_for_date("rate_5", when.date())
if plan is None:
    raise LookupError("no rate_5 tariff recorded for that date")
rate = get_time_of_use_rate(plan, when)
print(rate.period, rate.price_per_kwh, rate.season)  # off_peak 0.13701 winter
```

`get_time_of_use_rate(plan, when)` returns a `TimeOfUseRate` (`period`, `price_per_kwh`, `season`) for the
moment `when`. It applies the season, the clock windows, and each period's weekday and holiday rules
(`TimeOfUsePeriod.applies_on`). A naive `datetime` is read as local time; an aware one is converted to
`America/New_York`. For interval data, pass the interval's start time.

Pass the plan that was in effect at `when` (`get_rate_plan_for_date`), because the rules differ between tariff
periods. `get_rate_plan_for_date` returns `None` when no period is recorded, so check for that first. To skip that
step, use [`rate_at()` or `price_usage()`](#rate_at-and-price_usage), which resolve the period in effect themselves and
return `None` instead of raising.

`get_time_of_use_rate` raises `ValueError` if the plan has no time-of-use charge (anything other than Rates 5
and 7), if `when` falls outside the plan's effective dates, or if the plan has no periods or no fallback period
for the season. Clock windows are half-open (`[start, end)`), and a window whose end is before its start
crosses midnight.

`season_for(day)` returns `Season.SUMMER` for May-September and `Season.WINTER` otherwise. It uses the
**calendar** month of `day`, not the billing month the tariffs name, so each interval is priced by the month it
falls in and a billing cycle that spans a season boundary is split between seasons. To price by billing month
instead, pick the season yourself and read `TimeOfUseCharge.periods_by_season` directly.

---

## Pricing usage

Added in 0.4.0. These functions price meter usage without the caller knowing how a `RatePlan` is structured:
pass a plan, a timestamp, a quantity in the meter's unit and (for tiered plans) cycle-to-date usage, and get
dollars back. Every entry point resolves the tariff period in effect at the timestamp, so a fix to a tariff in
the library reaches every consumer without code changes.

```python
from datetime import datetime
from dominionsc import RATE_8, MeterUnit, price_usage, rate_at

cost = price_usage(RATE_8, datetime(2026, 8, 1, 14, 0), 2000, MeterUnit.WATT_HOUR, cycle_usage_before=799_000)
print(cost.amount, cost.tiers)  # 0.33320 ('First 800 kWh', 'Over 800 kWh')

quote = rate_at(RATE_8, datetime.now(), cycle_usage=812.4)  # cycle_usage in kWh
print(quote.price_per_unit, quote.tier)
```

All dates (tariff period, season, holiday, billing cycle) are taken in `America/New_York`. Naive `datetime`
values are read as local time; aware values are converted. Amounts are `Decimal` and unrounded. Quantities may
be `Decimal`, `float` or `int`; floats are converted through `str`, so `0.1` is `Decimal("0.1")`.

### Utility-local time

```python
from dominionsc import UTILITY_TIMEZONE, utility_local_date
```

- `UTILITY_TIMEZONE`: `ZoneInfo("America/New_York")`. `dominionsc.time_of_use.LOCAL_TIMEZONE` remains as an
  alias.
- `utility_local_date(when) -> date`: the calendar date of `when` in that zone. `2026-07-01 02:00 UTC` gives
  `2026-06-30`.

### `resolve_plan_for()`

```python
resolve_plan_for(plan: RatePlan, when: datetime | date) -> RatePlan | None
```

Returns the tariff period of `plan` in effect at `when`. For catalog codes this is
`get_rate_plan_for_date(plan.code, local_date)`, so passing `RATE_5` for a 2025 date returns `RATE_5_2025`.
A plan whose code is not in the catalog is returned as is when the local date is within its
`effective_from`..`effective_to` (inclusive), else `None`. A `date` is used as given; a `datetime` is converted
to its local date.

### Units

```python
from dominionsc import DEFAULT_THERMS_PER_CCF, MeterUnit, to_billing_units
```

| Name | Description |
|------|-------------|
| `MeterUnit.WATT_HOUR` (`"Wh"`) | Electric meter unit (ESPI `uom` 72). |
| `MeterUnit.CUBIC_FOOT` (`"ft3"`) | Gas meter unit (ESPI `uom` 119). |
| `DEFAULT_THERMS_PER_CCF` | `Decimal("1.036")`: estimated therms per hundred cubic feet (1,036 BTU per cubic foot, the 24-month average for South Carolina gas deliveries from the U.S. EIA). The integration's historical `ft³ / 100` is a factor of exactly `1`. |

`to_billing_units(quantity, unit, plan, *, therms_per_ccf=DEFAULT_THERMS_PER_CCF) -> Decimal` converts a meter
quantity into the plan's billing unit: Wh → kWh for electric plans, ft³ → therms for gas plans. The gas factor is
an approximation: Dominion converts using the average heat content of its gas over each billing cycle (tariff
section III.B), which changes every cycle and is normally 0.95 to 1.40 therms per CCF. The default of 1.036 is the
average heat content of South Carolina gas deliveries over September 2024 to August 2026 (1,033 to 1,041 in every
month, per the EIA), not Dominion's own figure. Pass `therms_per_ccf` when you know the factor for a cycle (therms divided by CCF on a bill). It raises
`ValueError` when the unit doesn't measure the plan's commodity (for example ft³ on an electric plan).

### `rate_at()` and `price_usage()`

```python
rate_at(plan, when, cycle_usage=None) -> RateQuote | None
price_usage(plan, when, quantity, unit, *, cycle_usage_before=0, therms_per_ccf=DEFAULT_THERMS_PER_CCF) -> UsageCost | None
```

`rate_at` answers "what does the next unit cost at `when`?". `cycle_usage` is cycle-to-date usage in the
**billing unit** (kWh or therm) and picks the tier for tiered plans; `None` reports the first tier.

`price_usage` prices `quantity` (in the **meter unit**) for an interval starting at `when`. It works for any
interval length; the whole interval is priced as of its start. `cycle_usage_before` is cycle-to-date usage in
the same meter unit, before this interval.

Both return `None` when no tariff period is in effect at `when`, or when the plan's time-of-use or tier data
can't price that moment (for example a time-of-use plan with no fallback period). A plan with no usage charge
(only fixed charges) prices usage at zero. Both raise `ValueError` if the plan in effect has more than one usage-based charge; `price_usage`
also raises it for a unit/commodity mismatch.

How each charge is priced:

| Charge | Pricing |
|--------|---------|
| `TieredUsageCharge` | Season from `season_for(local date)`. The quantity is split across every tier boundary it crosses, for any number of tiers. A tier with `upper_bound=None` (or the last tier) takes all remaining usage. |
| `TimeOfUseCharge` | `get_time_of_use_rate(resolved_plan, when)`. |
| `FlatUsageCharge` | quantity × price. |
| `DemandCharge` | Never priced; its name is listed in `unpriced_charges` (Rate 7: `"On-Peak Billing Demand"`). |
| `DailyCharge`, `MonthlyCharge` | Not included. |

**Solar generation (net metering).** Generation is credited at the same rate usage costs at that moment: the
same tier and season on tiered plans, the same time-of-use period on Rate 5 and 7. It offsets usage, and on
tiered plans it also lowers cycle-to-date usage.

Use `price_net_usage` to price an interval's usage and generation together:

```python
price_net_usage(plan, when, used, generated, unit, *, cycle_usage_before=0, therms_per_ccf=...) -> NetUsageCost | None
```

```python
result = price_net_usage(RATE_8, when, 10_000, 5_000, MeterUnit.WATT_HOUR)  # 10 kWh used, 5 kWh generated
result.usage.amount  # cost of the 10 kWh used
result.generation.amount  # credit for the 5 kWh generated (negative)
result.amount  # net: the same as pricing 5 kWh
```

`NetUsageCost` has `usage` and `generation` (each a full `UsageCost`), plus the net `amount` and net
`quantity`. `generated` is a size; a solar-export register's negative read can be passed as is. Generation is
priced after the interval's usage, so on a tiered plan it offsets the highest-tier energy first. The net
`amount` always equals pricing the net quantity directly, including when the hour crosses a tier boundary, and
an hour that exports more than it uses is a net credit (negative `amount`). `price_usage` also accepts a
negative quantity and credits it the same way.

**`RateQuote`** fields: `plan` (the period actually used), `price_per_unit`, `usage_unit`, `season` (`None` for
flat plans), `period` (time-of-use period name or `None`), `tier` and `tier_upper_bound` (`None` for non-tiered
plans), `unpriced_charges`.

**`UsageCost`** fields: `amount` (dollars), `quantity` (in the billing unit, after conversion), `plan`, `season`,
`period`, `tiers` (every tier the quantity touched, in order; a zero quantity reports the current tier),
`unpriced_charges`.

### Billing cycles and `UsagePricer`

```python
from dominionsc import (
    BillingCycle,
    UsagePricer,
    billing_cycle_length,
    estimate_billing_cycles,
    find_billing_cycle,
    fixed_charges,
)
```

Dominion doesn't expose past billing-cycle boundaries, so they are estimated from the forecast's current
cycle using the observed meter-read schedule. The estimate can be off by a day or two at cycle edges.

| Name | Description |
|------|-------------|
| `BillingCycle(start, end)` | One cycle; `end` is inclusive. `contains(day)` tests membership. |
| `billing_cycle_length(start) -> int` | Estimated length of the cycle starting on `start`. |
| `estimate_billing_cycles(anchor, earliest, latest=None)` | Tuple of cycles, oldest first, from `earliest` through the anchor and on to `latest`. `anchor` is a `BillingCycle` or a `Forecast` (its `start_date`/`end_date`). |
| `find_billing_cycle(day, cycles)` | The cycle containing `day`, or `None`. |
| `fixed_charges(plan, cycle)` | Fixed charges for one cycle; see below. |

`UsagePricer(plan, cycles=(), *, therms_per_ccf=...)` prices a chronological stream of reads and keeps the
cycle-to-date counter that tiered plans need:

```python
cycles = estimate_billing_cycles(forecast, earliest=start.date(), latest=date.today())
pricer = UsagePricer(RATE_8, cycles)
for read in sorted(reads, key=lambda r: r.start_time):
    if already_recorded(read):
        pricer.observe(read.start_time, read.consumption, MeterUnit.WATT_HOUR)  # counts, doesn't price
    elif (cost := pricer.price(read.start_time, read.consumption, MeterUnit.WATT_HOUR)) is not None:
        record(read.start_time, cost.amount)
```

- The counter resets when a read's local date is in a different cycle from the previous read's. Dates outside
  every cycle count as one more cycle of their own; with no cycles the counter never resets.
- `cycle_usage` is the counter, in billing units.
- Reads must be in time order. A read is rejected with `ValueError` only when it is earlier than the previous
  read both as an instant and on the local wall clock, so either labelling of the hours around a DST change is
  accepted.
- `price()` counts the usage even when it returns `None`.

**Fixed charges.** `fixed_charges(plan, cycle) -> Decimal` returns the non-usage charges for one billing cycle:

- Daily charges (the electric Basic Facilities Charge) are charged for each day of the cycle, both ends counted,
  using the tariff period in effect on each day.
- Monthly charges (the electric $1.00 Distributed Energy Resource charge and the gas $10.90 Basic Facilities
  Charge) are charged **once per billing cycle**, whatever its length and whatever the usage. "Month" means
  billing cycle. The amount comes from the period in effect on the cycle's last day.
- Days with no tariff period in effect cost nothing. Usage charges and Rate 7's demand charge are not included.
- It is an estimate. The cycle's boundaries are usually estimated and may be a day or two off, which moves the daily
  total by that many days' charge. Dominion doesn't publish its billing algorithms, so these rules are inferred from
  the tariffs and observed patterns and won't match every bill exactly. A cycle is charged for the dates it is given;
  pro-rating on a first or last bill and reconnection charges are out of scope. The tariffs' minimum-bill rule for
  net-metered accounts is not modeled yet.
- A cycle with `end` before `start` raises `ValueError`.
- For a net-metered account, `price_net(when, used, generated, unit)` prices each interval's usage and
  generation separately, returns a `NetUsageCost`, and adds the net to `cycle_usage`.

---

## Utilities

### `create_cookie_jar()`

```python
from dominionsc import create_cookie_jar
import aiohttp

cookie_jar = create_cookie_jar()
async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
    client = DominionSC(session, username, password)
```

Create an `aiohttp.CookieJar` configured for Dominion Energy SC's session cookies. **Must** be used instead of the default aiohttp cookie jar — see [helpers.py](../src/dominionsc/helpers.py) for why `quote_cookie=False` is required.

**Returns:** `aiohttp.CookieJar`
