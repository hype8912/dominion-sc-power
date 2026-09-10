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
6. [Utilities](#utilities)

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
)
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session` | `aiohttp.ClientSession` | An aiohttp session created with `create_cookie_jar()`. The library uses this session for all HTTP requests and does not close it. |
| `username` | `str` | The email address or username for `account.dominionenergysc.com`. |
| `password` | `str` | The account password. |
| `login_data` | `dict[str, str] \| None` | Optional saved TFA token from a previous successful MFA flow. Pass `{"tfa_token": "<token>"}` to skip interactive TFA. Default: `None`. |

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
| `MfaChallenge` | TFA is required and no valid `login_data` was provided. The exception carries a `DominionSCTFAHandler` — see [DominionSCTFAHandler](#dominionsclfahandler--tfa-handler) for the TFA flow. |
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
| `start_date` | `datetime \| None` | Start of the requested window. The time component is ignored — the library floors to midnight in the utility's local timezone. |
| `end_date` | `datetime \| None` | End of the requested window. Same flooring applies. |

**Returns:** `list[RegisterReads]` — one `RegisterReads` per distinct ESPI UsagePoint. Most accounts return a one-element list. Net-metered solar accounts return two elements (grid delivery and solar export).

**Raises:** `CannotConnect`, `ApiException`.

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

**Raises:** `CannotConnect`, `ApiException`.

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
await handler.async_submit_tfa_code(code: str) -> dict[str, str] | None
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
| `consumption` | `float` | Energy or volume consumed. **Electric:** Watt-hours (Wh). Divide by 1000 for kWh. **Gas:** Cubic feet (ft³). **Solar export:** Negative Wh values. |

**Interval length:** Dominion Energy SC reports 15-minute intervals for electric accounts. Gas intervals are typically 1 hour.

---

### RegisterReads

```python
from dominionsc.models.register_reads import RegisterReads
```

Interval readings grouped by physical meter register (ESPI UsagePoint).

| Field | Type | Description |
|-------|------|-------------|
| `usage_point_id` | `str` | Stable ESPI UsagePoint identifier. Confirmed constant across separate exports. Safe to use as a persistent key (e.g., for Home Assistant statistic IDs). |
| `flow_direction` | `str \| None` | ESPI `flowDirection` from the register's `ReadingType`. **Unreliable for Dominion Energy SC** — both grid and solar registers report `flowDirection=1`. Do not use this to distinguish registers. |
| `reads` | `list[UsageRead]` | Interval readings for this register in the order encountered. |

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
| `message` | `str` | Human-readable error message (from `str(exception)`). |
| `url` | `str \| None` | The URL that was being requested. |
| `status` | `int \| None` | HTTP status code, if a response was received. |
| `response_text` | `str \| None` | Response body text, if available. |

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
| `url` | `str` | The URL whose response triggered the error. |
| `status` | `int \| None` | HTTP status code. |
| `response_text` | `str \| None` | Raw response body for debugging. |

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
            # charge is TimeOfUseCharge
            ...
```

#### `TieredUsageCharge.tiers_by_season`

Maps `Season.SUMMER` and `Season.WINTER` to a tuple of `UsageTier`:

```python
tiered = rate_plan.charges[2]  # TieredUsageCharge
summer_tiers = tiered.tiers_by_season[Season.SUMMER]
for tier in summer_tiers:
    print(f"{tier.name}: ${tier.price_per_unit}/kWh up to {tier.upper_bound or '∞'} kWh")
```

#### `TimeOfUseCharge.periods_by_season`

Maps `Season` to a tuple of `TimeOfUsePeriod`:

```python
tou = rate_plan.charges[1]  # TimeOfUseCharge
summer_periods = tou.periods_by_season[Season.SUMMER]
for period in summer_periods:
    if period.fallback:
        print(f"{period.name}: ${period.price_per_unit}/kWh (all other hours)")
    else:
        for window in period.windows:
            print(f"{period.name}: ${period.price_per_unit}/kWh from {window.start} to {window.end}")
```

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

Dominion Energy SC's published tariffs define summer as **June through September** and winter as **October through May**. The library does not determine which season applies to a given date — that decision belongs to the consumer. When calculating costs from interval reads, check the billing month against these ranges to select the correct `tiers_by_season` or `periods_by_season` entry.

---

### Rate plan catalog

```python
from dominionsc import (
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

Return all catalogued residential rate plans as a tuple.

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
