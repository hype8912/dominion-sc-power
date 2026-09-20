# dominion-sc-power

A Python library for accessing historical and forecasted energy usage and cost data for Dominion Energy South Carolina customers.

This library is used by the custom [Home Assistant Integration for Dominion Energy SC](https://github.com/sctigercat1/ha-dominion-sc).

## Features

- Retrieve historical energy usage data (electric and gas)
- Separate readings by meter register (ESPI UsagePoint), so net-metered
  solar accounts can distinguish grid-delivery from solar-export data
- Get current bill forecasts with cost projections
- Support for two-factor authentication (TFA)
- Async/await architecture using aiohttp
- Support for multiple energy sources (electric and gas)
- Declarative residential rate plan catalog, including superseded tariff periods
  for pricing historical usage

## Supported Rate Plans

The library ships declarative pricing for the following Dominion Energy SC
residential tariffs (see [`src/dominionsc/rates.py`](src/dominionsc/rates.py)):

**Electric**

| Code | Name |
|------|------|
| `rate_1` | Rate 1 - Residential Service: Good Cents Rate (closed to new customers since 1996) |
| `rate_2` | Rate 2 - Low Use Residential Service |
| `rate_5` | Rate 5 - Residential Service: Time of Use |
| `rate_6` | Rate 6 - Residential Service: Energy Saver/Conservation Rate |
| `rate_7` | Rate 7 - Residential Service: Time-of-Use Demand |
| `rate_8` | Rate 8 - Residential Service |

**Natural Gas**

| Code | Name |
|------|------|
| `rate_32s` | Rate 32S - Gas Residential Standard Service |
| `rate_32v` | Rate 32V - Gas Residential Value Service |

```python
from datetime import date

from dominionsc import get_rate_plan, get_rate_plan_for_date

plan = get_rate_plan("rate_8")  # the current plan
print(plan.name)  # "Rate 8 - Residential Service"

# The plan that was in effect on a past date (None if no plan is recorded for it)
old_plan = get_rate_plan_for_date("rate_8", date(2025, 9, 1))
```

`get_rate_plan()` and `get_available_rate_plans()` return current plans only.
Superseded periods are available through `get_rate_plan_history()` and
`get_rate_plan_for_date()`; see the [API reference](docs/api-reference.md#rate-plans).

## Limitations

- Only one service address per Dominion account is currently supported, because the API responses for
  accounts with multiple service addresses are not known. If this applies to you, you will get an error.
  Please report it under issues and include the relevant API response.
- TFA is required, because the login flow without TFA is not known. If this applies to you, please report the
  error under issues.
- Data is delayed by 24-48 hours, because that is when Dominion reports it.

## Installation

Requires Python 3.11 or higher.

```bash
pip install dominion-sc-power
```

## Development

Contributions are welcome! For environment setup, the daily development
workflow, testing, and the complete contribution checklist, see
[CONTRIBUTING.md](CONTRIBUTING.md). For an in-depth tour of how the library
is structured and how its pieces fit together, see the
[Developer Guide](docs/developer-guide.md).

## Documentation

- [API reference](docs/api-reference.md): the complete public API
- [Troubleshooting](docs/troubleshooting.md): common errors and how to resolve them
- [Home Assistant integration contract](docs/ha-integration-contract.md): what `ha-dominion-sc` can rely on
- [Architecture](docs/architecture/README.md): diagrams of the library's structure and data flow
- [Changelog](docs/CHANGELOG.md)

## Command Line Interface

The library includes a CLI for quick data retrieval:

```bash
# Basic usage (will prompt for credentials)
python -m dominionsc

# With credentials
python -m dominionsc --username your_username --password your_password

# Get historical data and save to CSV
python -m dominionsc --start_date 2025-02-01 --end_date 2025-02-08 --csv output.csv

# Store TFA token for reuse
python -m dominionsc --login_data_file data.json

# Verbose logging
python -m dominionsc -vv
```

### CLI Arguments

- `--username`: Username for the utility website
- `--password`: Password for the utility website
- `--login_data_file`: JSON file to store/load TFA tokens
- `--start_date`: Start date for historical data (ISO format, default: 7 days ago)
- `--end_date`: End date for historical data (ISO format, default: now)
- `--csv`: Output CSV file path for usage data
- `-v, --verbose`: Enable verbose logging (use multiple times for more verbosity)

### CSV output format

The CSV has five columns:

```
service,register,start_time,end_time,consumption
```

- `service` -- the measurement type (`ELECTRIC` or `GAS`)
- `register` -- the ESPI UsagePoint id, which distinguishes physical meters
  within a single service. A net-metered solar account has two ELECTRIC
  registers (grid delivery and solar export); they share the same `service`
  value but different `register` values. Solar-export rows carry negative
  `consumption` values.
- `consumption` -- Wh for electric, ft³ for gas

## Sample Implementation

```python
import asyncio
import aiohttp
from dominionsc import DominionSC, create_cookie_jar
from datetime import datetime, timedelta


async def main():
    username = "your_username"
    password = "your_password"

    async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
        client = DominionSC(session, username, password)

        # Login
        await client.async_login()

        # ** Handle TFA (see below) **

        # Get forecast
        forecast = await client.async_get_forecast()
        print(f"Forecasted cost: ${forecast.forecasted_cost}")

        # async_get_accounts() returns [measurement_types, service_address]
        measurement_types, service_address = await client.async_get_accounts()
        print(f"Service address: {service_address}")

        start = datetime.now() - timedelta(days=7)
        end = datetime.now()

        for account in measurement_types:  # e.g. "ELECTRIC", "GAS"
            # Register-aware: keeps each physical meter (ESPI UsagePoint)
            # separate. A net-metered solar ELECTRIC account returns two
            # registers -- grid delivery and solar export (negative values).
            registers = await client.async_get_register_reads(account, start, end)
            for register in registers:
                print(f"{account} register {register.usage_point_id}:")
                for reading in register.reads:
                    # Wh for ELECTRIC, ft³ for GAS
                    print(f"  {reading.start_time}: {reading.consumption}")


asyncio.run(main())
```

### Flat (single-list) usage reads

If you don't need per-register separation -- for example a single-meter
account with no solar -- `async_get_usage_reads()` returns a flat list of
`UsageRead` objects across all registers:

```python
usage = await client.async_get_usage_reads("ELECTRIC", start_date=start, end_date=end)
for reading in usage:
    print(f"{reading.start_time}: {reading.consumption} Wh")
```

> **Note for net-metered / solar accounts:** a single `ELECTRIC` request can
> contain multiple meter registers (grid delivery + solar export). The flat
> `async_get_usage_reads()` merges them into one list, producing overlapping
> timestamps and mixed positive/negative values with no way to tell the
> registers apart. Use `async_get_register_reads()` if that distinction
> matters to you.

## Handling Two-Factor Authentication (TFA)

TFA is required (see [Limitations](#limitations)), so you need to handle the `MfaChallenge` exception when logging in:

```python
from dominionsc import MfaChallenge, InvalidAuth

try:
    await client.async_login()
except MfaChallenge as e:
    handler = e.handler

    # Get available TFA options
    options = await handler.async_get_tfa_options()
    print("Available TFA methods:", options)

    # Select an option (e.g., SMS or email)
    option_id = list(options.keys())[0]
    await handler.async_select_tfa_option(option_id)

    # Get code from user
    code = input("Enter the security code: ")

    # Submit code and get login data for future use
    login_data = await handler.async_submit_tfa_code(code)

    # Save login_data to skip TFA next time
    # Pass it as: DominionSC(session, username, password, login_data)

    # Retry login
    client.login_data = login_data
    await client.async_login()
```

## Credits

This project was inspired by [Opower](https://github.com/tronikos/opower). Much appreciated!

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This is an unofficial integration and is not affiliated with, endorsed by, or connected to Dominion Energy SC. Use at your own risk. The authors are not responsible for any issues that may arise from using this integration.
