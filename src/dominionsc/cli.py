"""CLI logic for the dominionsc package.

Extracted from __main__.py so this module is importable and testable
without executing argparse or asyncio.run(). See docs/REFACTOR_PLAN.md Phase 5.

Fixes compared to the original __main__.py:
- CSV file is opened ONCE, outside the per-account loop -- the original
  opened with mode "w" inside the loop, silently overwriting every prior
  account's output on each iteration (finding F9).
- accounts[0] positional access replaced with named AccountInfo unpacking
  via async_get_accounts(), which still returns the legacy list format
  but is at least destructured explicitly here.
- A "service" column is added to CSV output so readings from different
  measurement types (ELECTRIC, GAS) are distinguishable in multi-account
  files.
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
from datetime import datetime, timedelta
from getpass import getpass

import aiohttp

from dominionsc import DominionSC, InvalidAuth, MfaChallenge, create_cookie_jar


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser.

    Separated from run() so it can be imported and tested independently.
    """
    parser = argparse.ArgumentParser(
        description="Fetch usage data from Dominion Energy SC.",
    )
    parser.add_argument(
        "--username",
        help="Username for logging into the utility's website. If not provided, you will be asked for it",
    )
    parser.add_argument(
        "--password",
        help="Password for logging into the utility's website. If not provided, you will be asked for it",
    )
    parser.add_argument(
        "--login_data_file",
        help="Where to store login data from MFA. If not provided, login data will not be saved.",
    )
    parser.add_argument(
        "--start_date",
        help="Start datetime for historical data. Defaults to 7 days ago",
        type=lambda s: datetime.fromisoformat(s),
        default=datetime.now() - timedelta(days=7),
    )
    parser.add_argument(
        "--end_date",
        help="end datetime for historical data. Defaults to now",
        type=lambda s: datetime.fromisoformat(s),
        default=datetime.now(),
    )
    parser.add_argument(
        "--csv",
        help="csv file to store data",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="enable verbose logging",
        action="count",
        default=0,
    )
    return parser


async def _handle_mfa(
    dominionsc: DominionSC,
    challenge: MfaChallenge,
    login_data_file: str | None,
) -> bool:
    """Interactively handle an MFA challenge.

    Returns True if MFA succeeded and login was retried, False on failure.
    """
    handler = challenge.handler
    print(f"TFA Challenge: {challenge}")

    options = await handler.async_get_tfa_options()
    if options:
        print("Please select an TFA option:")
        for i, (_, value) in enumerate(options.items()):
            print(f"  [{i + 1}] {value}")
        choice_index = int(input("Enter the number for your choice: ")) - 1
        choice_key = list(options.keys())[choice_index]
        await handler.async_select_tfa_option(choice_key)
        print(f"A security code has been sent via {options[choice_key]}.")

    code = input("Enter the security code: ")
    try:
        login_data = await handler.async_submit_tfa_code(code)
    except InvalidAuth:
        logging.exception("TFA failed")
        return False

    print("TFA validation successful.")
    if login_data_file:
        with open(login_data_file, "w") as file:
            json.dump(login_data, file, indent=4)
    dominionsc.login_data = login_data
    await dominionsc.async_login()
    return True


async def run(args: argparse.Namespace) -> int:
    """Execute the CLI with parsed arguments.

    Returns an exit code (0 = success, non-zero = error).
    Separated from __main__ so it can be tested without subprocess.
    """
    logging.basicConfig(level=logging.DEBUG - args.verbose + 1 if args.verbose > 0 else logging.INFO)

    username = args.username or input("Username: ")
    password = args.password or getpass("Password: ")

    login_data = None
    if args.login_data_file:
        try:
            with open(args.login_data_file) as file:
                login_data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
        dominionsc = DominionSC(session, username, password, login_data)

        try:
            await dominionsc.async_login()
        except MfaChallenge as challenge:
            if not await _handle_mfa(dominionsc, challenge, args.login_data_file):
                return 1
        except InvalidAuth:
            logging.exception("Login failed")
            return 1

        if not args.csv:
            forecast = await dominionsc.async_get_forecast()
            print("\nCurrent bill forecast:", forecast)

        # async_get_accounts() returns the legacy [[types], addr] list;
        # destructure explicitly so the intent is clear.
        measurement_types, _service_addr = await dominionsc.async_get_accounts()

        if args.csv:
            # Open the file ONCE, outside the per-account loop.
            # The original __main__.py opened with mode "w" inside the loop,
            # silently overwriting each prior account's output (finding F9).
            with open(args.csv, "w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["service", "start_time", "end_time", "consumption"])
                for account in measurement_types:
                    usage_data = await dominionsc.async_get_usage_reads(
                        account,
                        args.start_date,
                        args.end_date,
                    )
                    for usage_read in usage_data:
                        writer.writerow(
                            [
                                account,
                                usage_read.start_time,
                                usage_read.end_time,
                                usage_read.consumption,
                            ]
                        )
        else:
            for account in measurement_types:
                usage_data = await dominionsc.async_get_usage_reads(
                    account,
                    args.start_date,
                    args.end_date,
                )
                print(f"\n[{account}]")
                print("start_time\tend_time\tconsumption")
                for usage_read in usage_data:
                    print(f"{usage_read.start_time}\t{usage_read.end_time}\t{usage_read.consumption}")
    return 0


def main() -> None:
    """Entry point: parse args and run the async CLI."""
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))
