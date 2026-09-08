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

## Limitations

- Only one service address per Dominion account is currently supported (mainly because I do not know what the API responses look like for users with multiple service addresses) - you will get an error if this applies to you - please report the error under issues which should include the relevant API response
- TFA is required (again mainly because I do not know what the flow without TFA looks like) - report this error under issues if it applies to you
- Data is delayed by 24-48 hours as this is when it is reported by Dominion

## Installation

```bash
pip install dominion-sc-power
```

## Development

Development uses [uv](https://docs.astral.sh/uv/) to manage the Python
virtual environment and dependencies. Install Python 3.11 or newer and uv
before starting. The committed `uv.lock` file keeps development installs
reproducible.

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/sctigercat1/dominion-sc-power.git
cd dominion-sc-power

# Create .venv and install the package plus development dependencies
uv sync --extra dev
```

The equivalent setup script is:

```bash
./scripts/setup
```

You can run commands without activating the environment by prefixing them
with `uv run`:

```bash
uv run python -m dominionsc --help
uv run pytest
uv run ruff check .
```

To activate the environment for a shell session, run
`source .venv/bin/activate` on macOS/Linux or `.venv\\Scripts\\activate` on
Windows.

See [CONTRIBUTING.md](CONTRIBUTING.md) for dependency-management guidance,
project conventions, testing details, and the complete developer workflow.

### Code Validation

After each change, run the repository scripts. The scripts use the project
virtual environment when it exists:

```bash
./scripts/lint
./scripts/test
```

The direct uv equivalents are:

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pytest
```

### Contributing

Contributions are welcome! Please submit a pull request with your proposed
changes. Before opening a pull request, update `uv.lock` when dependencies
change and run the lint and test commands above.

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
                    print(f"  {reading.start_time}: {reading.consumption} Wh")


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

## Handling two-Factor Authentication (TFA)

If your account has TFA enabled (see limitations above), you'll need to handle the `MfaChallenge` exception:

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
