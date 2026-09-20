# Troubleshooting

This guide covers common errors, their root causes, and how to resolve them.

---

## Table of Contents

1. [Authentication errors](#authentication-errors)
2. [Network and connection errors](#network-and-connection-errors)
3. [API structure errors](#api-structure-errors)
4. [TFA (two-factor authentication) issues](#tfa-two-factor-authentication-issues)
5. [Usage data issues](#usage-data-issues)
6. [CLI issues](#cli-issues)
7. [Development and testing issues](#development-and-testing-issues)

---

## Authentication errors

### `InvalidAuth: Invalid credentials, please try again`

**Symptom:** `async_login()` raises `InvalidAuth` immediately after posting credentials.

**Cause:** The username or password is wrong.

**Fix:**
1. Verify you can log in manually at [account.dominionenergysc.com](https://account.dominionenergysc.com).
2. Check for typos — passwords are case-sensitive.
3. If using a password manager, ensure it has not filled in an old password.
4. If you recently changed your password on the Dominion portal, update the password in your script or `.json` login file.

---

### `InvalidAuth: User has multiple accounts, not currently implemented`

**Symptom:** Login succeeds (credentials accepted, TFA completed) but raises `InvalidAuth` during account listing.

**Cause:** The Dominion account is linked to more than one service address. The library currently only supports single-account setups.

**Fix:** This is a known limitation. Please open a GitHub issue and include the sanitized error output (remove any personal information). The issue is tracked in the [developer guide](developer-guide.md#known-limitations-and-technical-debt).

---

### `InvalidAuth: Unsuccessful authentication (possible no TFA required ...)`

**Symptom:** Login raises `InvalidAuth` with a message about TFA not being required.

**Cause:** The Dominion portal returned an authentication status other than `"twoFA"`. The library currently requires TFA to be enabled.

**Fix:** This is a known limitation. Please open a GitHub issue with the error message (it includes the API response status). The issue is tracked in the [developer guide](developer-guide.md#known-limitations-and-technical-debt).

---

### `CannotConnect: Cannot retrieve request verification token`

**Symptom:** Login fails at a token extraction step: either on the login page fetch (before any credentials are sent) or on the authenticated home page fetch later in the login sequence.

**Cause:** The login page HTML did not contain the expected `<input name="__RequestVerificationToken" ...>` element. This can happen if:
- The Dominion portal changed its login page HTML structure.
- The User-Agent string is being blocked or triggering a different page.
- A temporary server-side issue returned an error page instead of the login page.

**Fix:**
1. Try again — the portal may be temporarily down.
2. Open `account.dominionenergysc.com/access/#login` in a browser and check whether the page loads normally.
3. If the page loads normally in a browser but not via the library, update `USER_AGENT` in `src/dominionsc/const.py` to a current browser UA string. Copy the exact value from your browser's DevTools (Network tab → any Dominion request → Request Headers → `User-Agent`).
4. If the issue persists, open a GitHub issue — the login page HTML may have changed.

---

## Network and connection errors

### `CannotConnect: Failed to make an API call due to network error`

**Symptom:** Any method raises `CannotConnect` with a network error message.

**Cause:** The library could not reach the Dominion or Bidgely server. Common causes:
- No internet connection.
- DNS resolution failure.
- Firewall or proxy blocking the connection.
- TLS/SSL certificate issue.
- The remote server is temporarily down.

**Fix:**
1. Verify you have internet access: `curl https://account.dominionenergysc.com`
2. Check the `err.url` attribute to see which endpoint failed.
3. `CannotConnect` is a **retryable** exception — implement a retry with backoff (e.g., wait 30 seconds and try again).
4. Check [Dominion Energy SC's service status](https://account.dominionenergysc.com) for outages.

---

### Requests time out

**Symptom:** `CannotConnect` is raised and the error message mentions a timeout.

**Cause:** Login, TFA, and forecast requests use a 30-second timeout. Usage data requests do not set a timeout of their own, so they fall back to the `aiohttp` session's default. The Dominion or Bidgely API occasionally responds slowly.

**Fix:**
- `CannotConnect` is retryable — try again later.
- If timeouts are consistently happening, open a GitHub issue.

---

## API structure errors

### `ApiException: Unable to decode ... data`

**Symptom:** Any method raises `ApiException` with a message like `"Unable to decode Authenticate data status"` or `"Unable to parse XML in parse_registers"`.

**Cause:** The API returned a response the library could not parse. This typically means the Dominion or Bidgely API has changed its response format and the library needs updating.

**Fix:**
1. Check the `err.response_text` attribute — it usually contains the raw API response. (The forecast parser's "Failed to decode forecast data." error carries only `err.url`; see [Forecast returns unexpected values](#forecast-returns-unexpected-values).)
2. Open a GitHub issue and include:
   - The full exception message.
   - The `err.url` value.
   - A sanitized (no personal info) copy of `err.response_text`.
3. If you are a developer, compare `err.response_text` to the corresponding parser code in `src/dominionsc/parsers/` or `src/dominionsc/auth.py` and update the key paths.

---

### Forecast returns unexpected values

**Symptom:** The `Forecast` object has `None` for `typical_cost` or the cost values seem wrong.

**Cause:**
- `typical_cost` is `None` when no prior-year data is available. This is normal early in a service relationship or after an account change.
- The forecast is computed as `currentCostPerDay * numberOfDaysInCurrentBill`. If Dominion's API returns an unusual `currentCostPerDay`, the projected cost will be off.

**Fix:** This is normally an API data issue, not a library bug. If parsing fails, `ApiException` reports "Failed to decode forecast data." with the request URL; the forecast parser does not attach the response body, so capture the `GetAccountAMIUsageAlerts` response from your browser's DevTools (Network tab) to inspect the raw values.

---

## TFA (two-factor authentication) issues

### `MfaChallenge` is raised every time

**Symptom:** Every call to `async_login()` raises `MfaChallenge` even when passing saved `login_data`.

**Cause:** The saved `tfa_token` has expired or been invalidated. Dominion invalidates TFA tokens when:
- You log out of the portal manually.
- You change your password.
- Dominion's session management expires old tokens.

**Fix:**
1. Delete the saved `login_data.json` (or the `tfa_token` entry from it).
2. Run through the interactive TFA flow again to obtain a new token.
3. Save the new `tfa_token` for future use.

---

### TFA code not received

**Symptom:** `async_select_tfa_option()` succeeds but the SMS or email code never arrives.

**Fix:**
1. Wait up to 2 minutes — carrier delays are common.
2. Check spam/junk folders for email codes.
3. Call `async_select_tfa_option()` again to trigger re-delivery.
4. Try a different delivery option from `async_get_tfa_options()`.

---

### `InvalidAuth: Invalid TFA code`

**Symptom:** `async_submit_tfa_code()` raises `InvalidAuth`.

**Cause:** The code was entered incorrectly, or it expired (TFA codes typically expire after 5–10 minutes).

**Fix:**
1. Request a new code via `async_select_tfa_option()`.
2. Enter the code promptly after it arrives.
3. Ensure there are no leading/trailing spaces in the code.

---

## Usage data issues

### Empty register reads or usage reads

**Symptom:** `async_get_register_reads()` returns an empty list, or `RegisterReads.reads` is empty.

**Cause:**
- The date range has no data yet (data is delayed 24–48 hours).
- The date range is too old (Bidgely typically retains 12–13 months).
- The `start_date` and `end_date` are equal or reversed.
- The account type (`ELECTRIC`/`GAS`) does not match the account's active services.

**Fix:**
1. Use a date range ending at least 2 days in the past:
   ```python
   from datetime import datetime, timedelta

   end = datetime.now() - timedelta(days=2)
   start = end - timedelta(days=7)
   ```
2. Verify the measurement type with `async_get_accounts()` — only use types present in `measurement_types`.
3. Check the date range is valid: `start_date < end_date`.

---

### Solar account readings look wrong

**Symptom:** Solar export values are positive, or grid and solar readings seem mixed together.

**Cause:** Using `async_get_usage_reads()` instead of `async_get_register_reads()` merges all registers into one flat list.

**Fix:** Switch to `async_get_register_reads()`, which returns one `RegisterReads` per physical meter. Solar-export registers carry negative `consumption` values. Use `usage_point_id` to identify each register consistently across requests.

---

### Gas consumption values are 1000 times too large

**Symptom:** Gas `consumption` values are far larger than your bill suggests (for example, roughly 500,000 ft³ for a 5 CCF billing period).

**Cause:** Older versions of the library ignored the `powerOfTenMultiplier` that Dominion's gas feed declares (`-3`, so raw values are thousandths of a cubic foot) and returned the raw values as cubic feet. Electric data was never affected.

**Fix:** Upgrade to a version that includes the fix (see the "Fixed" entry under Unreleased in the [changelog](CHANGELOG.md)). Values you already stored from an affected version need to be divided by 1000.

---

### Wrong pilot ID / smoothed hourly data instead of 15-minute reads

**Symptom:** Usage reads are in 1-hour intervals instead of 15-minute intervals, and values look averaged/smoothed rather than actual metered values.

**Cause:** The `BIDGELY_PILOT_ID` constant in `src/dominionsc/const.py` may be pointing to the wrong Bidgely data pipeline. The correct value for Dominion Energy SC is `"10078"`. The wrong value (`"10106"`) was used previously and caused this exact symptom.

**Fix:**
1. Verify `BIDGELY_PILOT_ID = "10078"` in `src/dominionsc/const.py`.
2. If the value is correct but the issue persists, capture the `gb-download` request URL from your browser's DevTools while logged into the Dominion portal and check which pilot ID appears in the `X-Bidgely-Pilot-Id` request header.
3. If your account needs a different pilot ID than the library default (e.g. a distinct Bidgely pipeline), pass the correct value directly instead of patching `const.py`: `DominionSC(session, username, password, pilot_id="<correct_id>")`.

---

## CLI issues

### `python -m dominionsc` not found

**Symptom:** `python -m dominionsc: No module named dominionsc`.

**Fix:** Install the package in your environment:
```bash
# As a user
pip install dominion-sc-power

# As a contributor, with uv
uv sync --extra dev

# As a contributor, with pip
pip install -e ".[dev]"

# Or run via uv run (no activation needed)
uv run python -m dominionsc --help
```

---

### CSV file is empty or missing data

**Symptom:** The CSV file is created but contains only the header row, or only the last account's data.

**Fix:** The library writes all accounts into a single CSV file in a single pass. If the file is empty, no data was returned (see [Empty register reads](#empty-register-reads-or-usage-reads)). The bug where each account overwrote the previous one (the CSV was opened with `mode="w"` inside the account loop) was fixed in the current code.

---

### Login prompt appears even when `--username` / `--password` are provided

**Symptom:** The CLI prompts for credentials even though they were passed as arguments.

**Cause:** The CLI prompts whenever the value it receives is missing or empty. A common cause is a shell variable that is unset or empty, which expands to an empty string (for example `--password "$DOMINION_PASSWORD"`).

**Fix:** Check that the values reach the CLI, and quote them so special characters in a password are not interpreted by the shell:
```bash
python -m dominionsc --username "your@email.com" --password "your_password"
```

---

## Development and testing issues

### Tests fail with `asyncio` or event loop errors

**Symptom:** Tests fail with errors about the event loop being closed or `RuntimeWarning: Enable tracemalloc`.

**Fix:** The test suite uses `pytest-asyncio` in `auto` mode (`asyncio_mode = "auto"` in `pyproject.toml`). Ensure `pytest-asyncio` is installed:
```bash
uv sync --extra dev
uv run pytest
```

---

### `ruff` reports errors after editing source files

**Symptom:** `ruff check .` fails after making changes.

**Fix:** Run the auto-fix tools:
```bash
uv run ruff format .          # format first
uv run ruff check . --fix     # then auto-fix lint issues
uv run ruff check .           # verify clean
```

If errors remain after `--fix`, they require manual resolution. The error messages include the file, line, and rule code (e.g., `E501` for line too long).

---

### Import errors after refactoring

**Symptom:** `ImportError` or `ModuleNotFoundError` after moving code between modules.

**Fix:** Check the backward-compatibility shims in `src/dominionsc/dominionsc.py`, `src/dominionsc/forecast.py`, and `src/dominionsc/usage_read.py`. These shims re-export the classes from their new canonical locations. If you moved a class to a new module, update the relevant shim.

---

### Cannot reproduce a production API issue locally

**Symptom:** The library works in the test suite but fails against the real API.

**Fix:**
1. Enable debug logging (the library logs a few debug messages, such as TFA option selection; it does not log full HTTP requests or responses):
   ```bash
   python -m dominionsc -vv
   ```
2. Add temporary print statements to the relevant parser or auth step.
3. Capture the raw API response with `err.response_text` from the exception.
4. Compare the captured response to the parser code to identify which field path has changed.
