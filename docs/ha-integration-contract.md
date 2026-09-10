# Home Assistant Integration Data Contract

This document describes **exactly what `ha-dominion-sc` receives from `dominion-sc-power`** — the method signatures, return types, data shapes, edge cases, and invariants the HA integration can rely on. It is the authoritative reference for anyone writing or maintaining the `ha-dominion-sc` side of the boundary.

---

## Table of Contents

1. [Session setup](#session-setup)
2. [Login and TFA](#login-and-tfa)
3. [`async_get_accounts()` — account list](#async_get_accounts--account-list)
4. [`async_get_forecast()` — bill forecast](#async_get_forecast--bill-forecast)
5. [`async_get_register_reads()` — metering data (preferred)](#async_get_register_reads--metering-data-preferred)
6. [`async_get_usage_reads()` — metering data (flat, legacy)](#async_get_usage_reads--metering-data-flat-legacy)
7. [Rate plans — static tariff data](#rate-plans--static-tariff-data)
8. [Exception contract](#exception-contract)
9. [Units and measurement conventions](#units-and-measurement-conventions)
10. [Known edge cases and invariants](#known-edge-cases-and-invariants)
11. [Backward-compatibility notes](#backward-compatibility-notes)

---

## Session setup

The HA integration must create the aiohttp session with the library's custom cookie jar. Using the default aiohttp jar will cause Dominion's session cookies to be silently corrupted (percent-encoded), breaking all subsequent authenticated requests.

```python
from dominionsc import DominionSC, create_cookie_jar
import aiohttp

# REQUIRED: use create_cookie_jar(), not aiohttp.CookieJar()
async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
    client = DominionSC(session, username, password, login_data=saved_tfa_data)
```

**HA note:** The library docstring for `DominionSC.__init__` states *"Do not modify default headers since Home Assistant that uses this library needs to use a default session for all integrations."* The library adds headers per-request rather than on the session, specifically to avoid interfering with HA's shared session pattern.

---

## Login and TFA

### Call pattern

```python
try:
    await client.async_login()
except MfaChallenge as challenge:
    # Interactive TFA required — see TFA section below
    ...
except InvalidAuth:
    # Wrong credentials — surface to user in HA config flow
    ...
except CannotConnect:
    # Retryable network failure
    ...
```

### What `async_login()` stores on the client

After a successful login, the following attributes are populated and used by subsequent calls:

| Attribute | Type | Description |
|-----------|------|-------------|
| `client.access_token` | `str` | Bidgely Bearer token. Required for all usage data requests. |
| `client.user_id` | `str` | Bidgely user ID. Embedded in the `gb-download` URL. |
| `client.accounts` | `list` | Legacy `[[types], address]` list. See [async_get_accounts()](#async_get_accounts--account-list). |

These attributes start as `None` / `[]` and are set only after `async_login()` succeeds. Any call to a data-retrieval method before login will raise `InvalidAuth`.

### TFA flow

When `MfaChallenge` is raised, the HA config flow must:

1. Retrieve the handler from `challenge.handler` (a `DominionSCTFAHandler` instance).
2. Call `await handler.async_get_tfa_options()` to get delivery options.
3. Let the user pick an option and call `await handler.async_select_tfa_option(option_id)`.
4. Prompt the user for the code and call `login_data = await handler.async_submit_tfa_code(code)`.
5. Save `login_data` (a `{"tfa_token": "<str>"}` dict) persistently in HA config entry data.
6. Set `client.login_data = login_data` and call `await client.async_login()` again to complete login.

**On subsequent HA restarts:** Pass the saved `login_data` dict to the `DominionSC` constructor. The library will attempt to verify the saved `tfa_token` and skip the interactive TFA step if it is still valid.

**TFA token expiry:** If the saved token has expired (e.g., after a password change or Dominion session invalidation), `MfaChallenge` will be raised again and the HA config flow must repeat the interactive TFA process.

---

## `async_get_accounts()` — account list

```python
result = await client.async_get_accounts()
# result: list  — always a 2-element list
measurement_types, service_address = result
```

### Return value

| Position | Name | Type | Example | Description |
|----------|------|------|---------|-------------|
| `result[0]` | `measurement_types` | `list[str]` | `["ELECTRIC"]` or `["ELECTRIC", "GAS"]` | Active measurement types. Each string is a valid `account` argument for `async_get_register_reads()`. |
| `result[1]` | `service_address` | `str` | `"123 MAIN ST (*-****-****0-4464)"` | Service address and masked account number from Dominion's portal. For display only. |

### Invariants the HA integration can rely on

- Always returns exactly 2 elements.
- `measurement_types` contains only `"ELECTRIC"` and/or `"GAS"` — no other strings will appear.
- `measurement_types` is never empty after a successful login (an account with no service types would not have been able to log in).
- `service_address` is always a non-empty string after a successful login.
- The library enforces single-account-only at login time (`singleAccount: true`). The HA integration will never receive multi-account data.

### Usage in HA

```python
measurement_types, service_address = await client.async_get_accounts()

# Use measurement_types to drive sensor creation:
for service in measurement_types:  # "ELECTRIC" or "GAS"
    registers = await client.async_get_register_reads(service, start, end)
    ...
```

---

## `async_get_forecast()` — bill forecast

```python
forecast = await client.async_get_forecast()
```

### Return type: `Forecast`

```python
from dominionsc import Forecast
from datetime import date

@dataclass
class Forecast:
    start_date: date          # First day of current billing period
    end_date: date            # Projected last day of billing period
    current_date: date        # Most recent date included in cost_to_date
    cost_to_date: float       # Dollars spent from start_date through current_date
    forecasted_cost: float    # Projected total bill for the full period
    typical_cost: float | None  # Last year's equivalent period total; None if unavailable
```

### Field details

| Field | Type | Can be None? | Notes |
|-------|------|-------------|-------|
| `start_date` | `date` | No | First day of the billing cycle. |
| `end_date` | `date` | No | Projected end; may change as the cycle progresses. |
| `current_date` | `date` | No | Typically 1-2 days behind real time due to metering latency. |
| `cost_to_date` | `float` | No | Dollar amount. Always ≥ 0. |
| `forecasted_cost` | `float` | No | Dollar amount. Calculated as `currentCostPerDay * numberOfDaysInCurrentBill`. |
| `typical_cost` | `float \| None` | **Yes** | `None` when Dominion has no prior-year data for comparison (new customers, or after certain account changes). HA sensors using this field must handle `None`. |

### HA sensor mapping

| Forecast field | Suggested HA sensor |
|----------------|---------------------|
| `cost_to_date` | `sensor.dominion_cost_to_date` |
| `forecasted_cost` | `sensor.dominion_forecasted_cost` |
| `typical_cost` | `sensor.dominion_typical_cost` (disable or show unavailable when `None`) |
| `start_date` | Attribute on the above sensors |
| `current_date` | Attribute on the above sensors |

---

## `async_get_register_reads()` — metering data (preferred)

```python
registers = await client.async_get_register_reads(
    account,      # str: "ELECTRIC" or "GAS"
    start_date,   # datetime — time component ignored, floored to midnight local
    end_date,     # datetime — time component ignored, floored to midnight local
)
# returns: list[RegisterReads]
```

### Return type: `list[RegisterReads]`

Each `RegisterReads` in the list corresponds to one physical meter register (ESPI UsagePoint):

```python
@dataclass
class RegisterReads:
    usage_point_id: str            # Stable ESPI UsagePoint ID (safe as a persistent key)
    flow_direction: str | None     # UNRELIABLE — do not use to identify register type
    reads: list[UsageRead]         # Interval readings for this register
```

Each `UsageRead` inside `reads`:

```python
@dataclass
class UsageRead:
    start_time: datetime    # Timezone-aware, in the utility's local timezone
    end_time: datetime      # Timezone-aware, inclusive (end = start + duration - 1 second)
    consumption: float      # Wh (electric) or ft³ (gas); negative for solar export
```

### How many RegisterReads will the HA integration receive?

| Account type | Number of registers | Notes |
|--------------|--------------------|----|
| Standard electric | 1 | Grid delivery only. Positive values. |
| Net-metered solar electric | 2 | One grid-delivery (positive), one solar-export (negative). Same `account="ELECTRIC"`. |
| Gas | 1 | Cubic feet. Always positive. |

**The list order is first-seen order from the XML.** Do not assume the grid-delivery register is always first. Use `usage_point_id` to identify registers across requests.

### `usage_point_id` — the stable key

`usage_point_id` is an ESPI UsagePoint identifier extracted from the `<link href>` path in the Green Button XML. It has been confirmed stable across separate exports months apart. Use it as a persistent key for:

- HA statistic IDs (e.g., `dominionsc:ELECTRIC_<usage_point_id>`)
- Distinguishing grid vs. solar registers in persistent storage
- Identifying which register a historical data point belongs to

Example IDs look like: `"4500123456"` (opaque string; exact format subject to change without notice).

### `flow_direction` — do not use for Dominion Energy SC

The ESPI `flowDirection` field is intended to indicate whether a register measures delivered (`1`) or generated (`19`) energy. **Dominion Energy SC reports `flowDirection=1` for both grid-delivery and solar-export registers.** The field is preserved in the model for other utilities where it may be accurate, but HA integration code for Dominion Energy SC **must not** rely on it.

Instead, distinguish registers by `usage_point_id` (which is stable) or by the sign of the `consumption` values (solar-export registers carry consistently negative values in practice — though this is a heuristic, not a guaranteed invariant).

### Date range behaviour

- The time component of `start_date` and `end_date` is **ignored**. Both are floored to midnight in the utility's local timezone (`America/New_York`).
- Pass `datetime` objects (not `date`). Using `date` objects will raise `TypeError`.
- Data availability: Bidgely typically provides the last 12-13 months. Requests beyond that return empty lists.
- Data latency: readings are typically delayed 24-48 hours. Data for yesterday may not yet be available.

```python
from datetime import datetime, timedelta

# Typical HA usage: last 30 days
end = datetime.now()
start = end - timedelta(days=30)
registers = await client.async_get_register_reads("ELECTRIC", start, end)
```

### Empty results

`async_get_register_reads()` returns an empty list (not an exception) when:
- The date range falls entirely within the 24-48 hour latency window.
- The date range is older than Bidgely's retention period (~13 months).
- The requested measurement type has no data for the given period.

HA code must handle an empty list without crashing.

---

## `async_get_usage_reads()` — metering data (flat, legacy)

```python
reads = await client.async_get_usage_reads(account, start_date, end_date)
# returns: list[UsageRead]
```

This is a flattened convenience wrapper around `async_get_register_reads()`. It concatenates readings from all registers into a single list.

**Use this only for single-register accounts** (standard electric with no solar, or gas). For net-metered solar accounts, this merges grid-delivery and solar-export readings into one list with overlapping timestamps and mixed positive/negative values, making it impossible to distinguish the two registers.

**Recommendation:** Use `async_get_register_reads()` for all new HA code. `async_get_usage_reads()` exists only for backward compatibility.

---

## Rate plans — static tariff data

The library ships a read-only catalog of current Dominion Energy SC residential rate plans. These are **pure data** — no API call is made to fetch them. The HA integration can use them to display pricing information, calculate estimated costs from interval reads, or let users identify which plan they are on.

### Importing

```python
from dominionsc import (
    get_rate_plan,
    get_available_rate_plans,
    RESIDENTIAL_RATE_PLANS,       # all plans keyed by code
    RESIDENTIAL_ELECTRIC_RATE_PLANS,
    RESIDENTIAL_GAS_RATE_PLANS,
    # Individual plan constants (if needed):
    RATE_2, RATE_5, RATE_6, RATE_7, RATE_8,   # electric
    RATE_32S, RATE_32V,                         # gas
)
```

### Available plans (effective July 1, 2026)

| Code | Commodity | Name | Who it applies to |
|------|-----------|------|-------------------|
| `"rate_2"` | Electric | Low Use Residential Service | Low-usage customers (≤400 kWh each of prior 12 months) |
| `"rate_5"` | Electric | Time of Use | Customers who can shift usage away from peak hours |
| `"rate_6"` | Electric | Energy Saver / Conservation Rate | Energy-efficient homes meeting insulation/equipment requirements |
| `"rate_7"` | Electric | Time-of-Use Demand | TOU rate + demand charge; typically for high-usage customers |
| `"rate_8"` | Electric | Standard Residential Service | Default plan for most residential customers |
| `"rate_32s"` | Gas | Gas Residential Standard Service | Default gas plan |
| `"rate_32v"` | Gas | Gas Residential Value Service | Lower rate; requires ≥10 therm average in June/July/August |

### Lookup

```python
# Look up by code (returns None for unknown codes)
plan = get_rate_plan("rate_8")

# Iterate all plans
for plan in get_available_rate_plans():
    print(plan.code, plan.commodity, plan.name)

# Filter by commodity
electric_plans = [p for p in get_available_rate_plans() if p.commodity == "electricity"]
```

### `RatePlan` fields the HA integration will use

| Field | Type | Notes |
|-------|------|-------|
| `code` | `str` | Stable key — safe to store in config or entity IDs |
| `name` | `str` | Human-readable name for display |
| `commodity` | `Commodity` | `"electricity"` or `"gas"` (StrEnum, compares equal to those strings) |
| `effective_from` | `date` | When this rate schedule took effect |
| `effective_to` | `date \| None` | When it expired; `None` means currently active |
| `charges` | `tuple[Charge, ...]` | See below |
| `eligibility_rules` | `tuple[EligibilityRule, ...]` | Informational eligibility text; safe to display to users |
| `adjustments` | `tuple[Adjustment, ...]` | Informational billing adjustment descriptions |

### Working with `charges`

Each charge in `plan.charges` is one of six concrete types, distinguished by the `kind` field:

| `kind` | Class | How to use it |
|--------|-------|--------------|
| `"daily"` | `DailyCharge` | `charge.amount * days_in_period` = fixed portion |
| `"monthly"` | `MonthlyCharge` | `charge.amount` = fixed portion per cycle |
| `"flat_usage"` | `FlatUsageCharge` | `charge.price_per_unit * total_kwh` = variable portion |
| `"tiered_usage"` | `TieredUsageCharge` | Apply `charge.tiers_by_season[Season.SUMMER]` or `[Season.WINTER]` tier breaks to cumulative usage |
| `"time_of_use"` | `TimeOfUseCharge` | Match each 15-min interval's local start time against `charge.periods_by_season[season]` windows |
| `"demand"` | `DemandCharge` | `charge.price_per_kw * peak_kw` where peak is the max 15-min average during `charge.qualifying_period` |

**Example — display all charges for a plan:**

```python
from dominionsc import get_rate_plan, DailyCharge, FlatUsageCharge, TieredUsageCharge, Season

plan = get_rate_plan("rate_8")
for charge in plan.charges:
    if charge.kind == "daily":
        print(f"Daily charge: ${charge.amount}/day")
    elif charge.kind == "flat_usage":
        print(f"Energy: ${charge.price_per_unit}/{charge.usage_unit}")
    elif charge.kind == "tiered_usage":
        for tier in charge.tiers_by_season[Season.SUMMER]:
            limit = f"up to {tier.upper_bound} kWh" if tier.upper_bound else "all remaining"
            print(f"Summer energy ({limit}): ${tier.price_per_unit}/kWh")
```

### What the HA integration should NOT do with rate plans

- **Do not treat them as live data** — they are static package data, not fetched from the API.
- **Do not assume they are current** — they have an `effective_from` date. If Dominion publishes a new tariff, a library update is required.
- **Do not compute final bills** — the library provides the rate structure; actual bill calculation requires knowledge of the customer's actual plan, billing dates, fuel adjustments (which vary monthly), and demand data. The `Adjustment` objects on each plan describe what adjustments are included in the published rates vs. billed separately.
- **Do not store rate plan data in HA persistent storage** — always read from the library at runtime so that library updates automatically flow through.

---

## Exception contract

The HA integration must handle these four exceptions from any library call:

| Exception | When raised | HA action |
|-----------|-------------|-----------|
| `MfaChallenge` | TFA required during login | Trigger the config flow TFA step |
| `InvalidAuth` | Wrong credentials, expired session, multi-account | Surface error to user; clear stored credentials or require re-auth |
| `CannotConnect` | Network failure, timeout | Mark entities unavailable; retry later |
| `ApiException` | API response structure changed | Log error with `err.url` and `err.response_text`; mark entities unavailable; may require library update |

### Catching exceptions

```python
from dominionsc import CannotConnect, InvalidAuth, MfaChallenge, ApiException

try:
    registers = await client.async_get_register_reads("ELECTRIC", start, end)
except CannotConnect as err:
    _LOGGER.warning("Cannot connect to Dominion: %s (url=%s)", err, err.url)
    # Mark entities unavailable, schedule retry
except ApiException as err:
    _LOGGER.error(
        "Dominion API response changed. Library update may be required. "
        "url=%s response=%s", err.url, err.response_text
    )
    # Mark entities unavailable
except InvalidAuth:
    _LOGGER.error("Dominion auth failed, re-auth required")
    # Trigger HA re-auth flow
```

---

## Units and measurement conventions

| Service | Field | Unit | Conversion |
|---------|-------|------|------------|
| ELECTRIC | `UsageRead.consumption` | Watt-hours (Wh) | Divide by 1000 for kWh |
| ELECTRIC (solar export) | `UsageRead.consumption` | Watt-hours (Wh), **negative** | Absolute value for energy exported |
| GAS | `UsageRead.consumption` | Cubic feet (ft³) | Divide by 100 for approximate therms (exact BTU conversion varies) |

### Datetime timezone

All `start_time` and `end_time` values on `UsageRead` are **timezone-aware** and set to the utility's local timezone (`America/New_York`, i.e., Eastern Time with DST). They are not UTC.

The `DominionSC.get_timezone()` method returns the IANA timezone name string if the HA integration needs it.

### Interval length

| Service | Interval | Duration |
|---------|----------|----------|
| ELECTRIC | 15 minutes | 900 seconds |
| GAS | 1 hour | 3600 seconds |

`end_time = start_time + duration - 1 second`. Two consecutive readings are back-to-back with no gap.

---

## Known edge cases and invariants

### Things the HA integration MUST handle

| Edge case | Description |
|-----------|-------------|
| `typical_cost` is `None` | New customers or after certain account changes. Do not assume it is always a float. |
| Empty `list[RegisterReads]` | No data in the requested date range. Do not assume at least one register is returned. |
| Single register for ELECTRIC | Most accounts have only one register. Only net-metered solar accounts have two. |
| `flow_direction` unreliable | Do not use to determine grid vs. solar for Dominion Energy SC. |
| `MfaChallenge` on any login | Even with a saved token, the token may have expired. |
| 24-48 hour data lag | Data for recent days may not yet be available. |

### Things the library guarantees

| Invariant | Guarantee |
|-----------|-----------|
| `usage_point_id` stability | The same physical register always reports the same `usage_point_id` across separate API calls. Safe as a persistent key. |
| `measurement_types` contents | Only `"ELECTRIC"` and `"GAS"` will ever appear in the list. |
| Return list length | `async_get_accounts()` always returns exactly 2 elements after successful login. |
| Timezone-aware datetimes | All `start_time` / `end_time` values are timezone-aware. Never naive datetimes. |
| Solar-export sign | Solar-export registers carry consistently negative `consumption` values in practice. |
| Single-account enforcement | The library raises `InvalidAuth` if the account has multiple service addresses; the HA integration will never receive mixed-address data. |

---

## Backward-compatibility notes

These are known breaking changes or interface quirks to be aware of when updating `dominion-sc-power`:

### `async_get_accounts()` return type

The method returns a raw `list` (`[[types], address]`), not the `AccountInfo` dataclass used internally. This is intentional backward compatibility. The current HA code destructures it as:

```python
accounts, service_addr = await client.async_get_accounts()
```

When this interface is eventually updated to return `AccountInfo` directly, `ha-dominion-sc` will need a corresponding update.

### `async_get_register_reads()` vs `async_get_usage_reads()`

`async_get_usage_reads()` was the original flat API. `async_get_register_reads()` was added later to support solar/net-metered accounts. New HA code should use `async_get_register_reads()` exclusively.

### `typical_cost: float | None`

Older versions of the library may have typed `typical_cost` as `float` (non-optional). It was corrected to `float | None` to match the API's actual behavior. Any HA code that assumed `typical_cost` is always a float must be updated to guard against `None`.
