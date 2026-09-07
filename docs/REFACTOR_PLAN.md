# Refactor Plan — `dominion-sc-power`

**Status:** proposed
**Written against:** working tree state of 2026-09-05, after `Forecast` / `UsageRead`
were extracted into `forecast.py` / `usage_read.py`, and after the
`BIDGELY_PILOT_ID` + timezone fixes were applied.
**Baseline:** 58 tests passing, `dominionsc.py` at 99% line coverage.

---

## 1. Purpose

The library works, but nearly all of its logic lives in a single ~490-line
module (`dominionsc.py`) that mixes three unrelated concerns: **authentication**,
**HTTP transport**, and **response parsing**.

This is not a style complaint. It cost real debugging time:

- A wrong hardcoded `X-Bidgely-Pilot-Id` existed in **two** places because header
  dictionaries are built inline in six different spots. A first attempt at
  fixing it silently patched the same location twice.
- Diagnosing whether bad usage data came from the API, the request window, or
  the parser required trial-and-error against the live API, because there is no
  seam at which parsing can be tested against a fixture.
- Support for multi-register (net-metered / solar) accounts is missing, and the
  gap is invisible because parsing is buried inside a method that also does date
  math, URL building, and network I/O.

The goal of this refactor is that each of those three concerns can be read,
tested, and changed independently.

**Non-goals:** no behaviour changes, no new features, no dependency changes.
Multi-register support is _enabled_ by this work but is tracked separately.

---

## 2. Current state

### 2.1 Module inventory

| File            | Contents                                                       | Coverage |
| --------------- | -------------------------------------------------------------- | -------- |
| `__init__.py`   | Public API re-exports                                          | 100%     |
| `__main__.py`   | CLI demo (argparse, login, CSV writing)                        | 0%       |
| `const.py`      | `USER_AGENT`, `BIDGELY_PILOT_ID`                               | 100%     |
| `dominionsc.py` | `DominionSCURLHandler`, `DominionSCTFAHandler`, `DominionSC`   | 99%      |
| `exceptions.py` | `CannotConnect`, `InvalidAuth`, `MfaChallenge`, `ApiException` | 84%      |
| `forecast.py`   | `Forecast` dataclass                                           | 100%     |
| `helpers.py`    | `create_cookie_jar`                                            | 67%      |
| `usage_read.py` | `UsageRead` dataclass                                          | 100%     |

### 2.2 Findings

Each item below is a concrete, located problem — not a general principle.

**F1 — Two competing HTTP implementations.**
`DominionSCURLHandler.call_api` and `DominionSC._async_get_request` both do:
open request → `await resp.text(encoding="utf-8")` → wrap `ClientError` in
`CannotConnect`. The only material difference is POST support. Two code paths
means two places for a transport-level bug to hide, and two places to add
retries/logging/timeouts later.

**F2 — Header dictionaries built inline in six places.**
`headers0`, `headers1`, `headers2`, `headers3` in `_async_login_internal`;
`headers0`, `headers1` in `_async_get_forecast_internal`; plus `_get_headers()`.
Several share an identical base (`User-Agent`, `IsAjax`, `X-Requested-With`,
`Host`, `Origin`, `Referer`). **This is the direct cause of the duplicated
pilot-ID bug.**

**F3 — URLs are string-concatenated inline in ~13 places.**
There is no single location that answers "what endpoints does this library
call?" Observed endpoints:

| Host     | Path                                                        |
| -------- | ----------------------------------------------------------- |
| dominion | `GET /access/#login`                                        |
| dominion | `GET /`                                                     |
| dominion | `POST /fusionapi/LoginWebApi/Authenticate/`                 |
| dominion | `GET /fusionapi/LoginWebApi/InitAuthentication/`            |
| dominion | `GET /fusionapi/LoginWebApi/Verify2FAToken/`                |
| dominion | `POST /fusionapi/LoginWebApi/SendPINCode/`                  |
| dominion | `POST /fusionapi/LoginWebApi/VerifyPIN/`                    |
| dominion | `GET /fusionapi/AccountManagementWebApi/GetAccountListing/` |
| dominion | `GET /fusionapi/AccountSummaryWebApi/InitAccount/`          |
| dominion | `GET /fusionapi/BidgelyWebApi/GetBidgelySDKInit/`           |
| dominion | `GET /fusionapi/CommonWebApi/GetAccountAMIUsageAlerts/`     |
| bidgely  | `POST /v2.0/web/wc-session`                                 |
| bidgely  | `GET /v2.0/dashboard/users/{user_id}/gb-download`           |

**F4 — Repeated boilerplate.**

- `tt = str(int(time.time() * 1000))` cache-buster: 6 occurrences.
- `try: json.loads(...) / except Exception: raise ApiException(...)`: ~10
  occurrences with near-identical shape.
- `json.loads(r7)` re-parses the same response string 3 times in
  `_async_login_internal`; `json.loads(r4)` twice.
- "fetch page, then `_find_verification_token`": 3 occurrences.

**F5 — Parsing is welded to fetching.**
`async_get_usage_reads` performs: date normalisation → timezone conversion →
URL construction → HTTP GET → `xmltodict.parse` → object construction, in one
method. `_async_get_forecast_internal` is the same pattern for JSON. Neither
parser can be exercised without a live call or an HTTP mock.

**F6 — `accounts` has a heterogeneous positional shape.**
`_async_login_internal` returns `accounts = [[...measurement types...],
serviceAddressAndAccountNo]` — annotated `list[str]`, actually
`list[list[str] | str]`, read positionally by callers as `accounts[0]` /
`accounts[1]`. Positional access to a structure that can grow is the same
fragility class as index-based CSV parsing.

**F7 — Dead reference in `exceptions.py`.**
`if TYPE_CHECKING: from .utility import DominionSCTFAHandler` — there is no
`utility.py`. Invisible at runtime (guard is false), but unresolvable for
`ty`/`mypy`.

**F8 — Shared mutable header state.**
`_async_login_internal` mutates `headers1` in place
(`headers1["__RequestVerificationToken"] = ...`, `del headers1["Origin"]`) and
passes that same dict into `DominionSCTFAHandler`. Ordering-dependent and hard
to reason about.

**F9 — CLI is untested and holds library logic.**
`__main__.py` is at 0% coverage and contains a real defect: the CSV file is
opened with mode `"w"` _inside_ the per-account loop, so each account
overwrites the previous account's output.

**F10 — Configuration is split across two mechanisms.**
`USER_AGENT` and `BIDGELY_PILOT_ID` live in `const.py`, while
`_dominion_endpoint`, `bidgely_endpoint`, and `timezone` are assigned as
instance attributes in `DominionSC.__init__`.

---

## 3. Target structure

```
src/dominionsc/
├── __init__.py          # public API surface (unchanged exports)
├── __main__.py          # thin entry point: argparse -> cli.run()
├── cli.py               # CLI logic, importable and testable
├── config.py            # UtilityConfig: endpoints, timezone, pilot id
├── const.py             # USER_AGENT, BIDGELY_PILOT_ID, defaults
├── exceptions.py        # unchanged behaviour; stale import removed
├── transport.py         # HttpClient — the ONLY place that performs I/O
├── headers.py           # header builders — single source of truth
├── urls.py              # endpoint builders — single source of truth
├── auth.py              # LoginFlow + DominionSCTFAHandler
├── client.py            # DominionSC facade, composes the modules below
├── models/
│   ├── __init__.py
│   ├── account.py       # NEW: AccountInfo (replaces the positional list)
│   ├── forecast.py      # (moved) Forecast
│   └── usage_read.py    # (moved) UsageRead
└── parsers/
    ├── __init__.py
    ├── greenbutton.py   # ESPI XML -> list[UsageRead]; no network
    └── forecast.py      # AMI JSON -> Forecast; no network
```

### Dependency direction

```
__main__ -> cli -> client -> auth ------> transport -> (network)
                     |         |     \
                     |         |      -> headers, urls
                     |         v
                     |       models
                     v
                  parsers -> models
```

Rules:

- `parsers/` imports **nothing** from `transport`, `auth`, or `aiohttp`.
- `transport.py` knows nothing about Dominion or Bidgely semantics.
- `client.py` is orchestration only — no inline URL strings, no header dicts,
  no `xmltodict`.

---

## 4. Phased execution

Each phase is independently mergeable and ends with `uv run pytest` green.
Do not batch phases. The existing 58 tests are the regression net; if a test
must change, understand why before changing it.

### Phase 0 — Prep

- [ ] Branch: `refactor/modularize`
- [ ] Confirm baseline green: `uv run pytest -v`
- [ ] Confirm lint baseline: `uv run ruff check .`
- [ ] Record baseline coverage numbers for comparison

**Acceptance:** baseline reproduced and recorded.

---

### Phase 1 — Transport, headers, URLs _(highest value, lowest risk)_

Addresses **F1, F2, F3, F4, F10**.

- [ ] Create `config.py` with a `UtilityConfig` dataclass holding
      `dominion_endpoint`, `bidgely_endpoint`, `timezone`, `pilot_id`,
      `user_agent`. Default instance for Dominion Energy SC.
- [ ] Create `transport.py` with a single `HttpClient`: - `async def get(url, headers) -> str` - `async def post(url, headers, json_data) -> str` - one `ClientError -> CannotConnect` wrap - `def json_or_raise(text, message, url) -> dict` helper to collapse the
      ~10 duplicated try/except blocks - `def cache_buster() -> str` for the repeated millisecond timestamp
- [ ] Create `headers.py`: `base(config)`, `ajax(config, token=None)`,
      `bidgely(config, access_token=None)`. Pilot ID referenced exactly once.
- [ ] Create `urls.py`: one function per endpoint from the F3 table, cache-buster
      applied internally.
- [ ] Rewrite `DominionSCURLHandler` and `DominionSC._async_get_request` to
      delegate to `HttpClient`. Keep `DominionSCURLHandler` as a thin shim if any
      test references it directly.

**Acceptance:**

- No literal `"X-Bidgely-Pilot-Id"` outside `headers.py`.
- No `fusionapi` / `bidgely.com` path strings outside `urls.py`.
- No `time.time() * 1000` outside `transport.py`.
- Tests green.

---

### Phase 2 — Authentication

Addresses **F7, F8**.

- [ ] Move `DominionSCTFAHandler` into `auth.py` unchanged in behaviour.
- [ ] Move `_async_login_internal` into `auth.py` as `LoginFlow.execute()`.
- [ ] Build fresh header dicts per step (via `headers.py`) instead of mutating
      and re-passing `headers1`.
- [ ] Fix the `.utility` TYPE_CHECKING import in `exceptions.py` to point at
      `.auth`.
- [ ] `client.py` gains `DominionSC`, delegating login to `LoginFlow`.

**Acceptance:**

- `auth.py` has no `xmltodict` import and no usage/forecast logic.
- No in-place mutation of a header dict that is passed elsewhere.
- Tests green (login tests may need import-path updates only).

---

### Phase 3 — Parsers _(the phase that unblocks solar support)_

Addresses **F5**.

- [ ] Create `parsers/greenbutton.py` with a pure function:
      `parse_usage_reads(xml_text: str, timezone: str) -> list[UsageRead]`
- [ ] Create `parsers/forecast.py` with
      `parse_forecast(payload: dict) -> Forecast`
- [ ] `async_get_usage_reads` reduces to: build window → build URL → fetch →
      hand the string to the parser.
- [ ] Add `tests/fixtures/` and commit a **redacted** real Green Button XML
      sample. Test the parser directly against it — no network, no credentials.
- [ ] Add a fixture for a multi-register (net-metered) account to document the
      current flattening behaviour.

**Acceptance:**

- `parsers/` imports no `aiohttp` and performs no I/O.
- At least one parser test runs against a committed fixture.
- Tests green.

> **Follow-up, not part of this refactor:** with a testable parser in place,
> add multi-register support — group readings by `UsagePoint` /
> `espi:flowDirection` rather than flattening every `Interval Consumption`
> entry into one list. Track as a separate issue.

---

### Phase 4 — Models and account shape

Addresses **F6**.

- [ ] Create `models/` package; move `forecast.py` and `usage_read.py` into it.
- [ ] Add `models/account.py` with an `AccountInfo` dataclass:
      `measurement_types: list[str]`, `service_address_and_account_no: str`.
- [ ] Change `LoginFlow` to return `AccountInfo` instead of the positional list.
- [ ] Update `async_get_accounts` and any consumer access accordingly.

**Acceptance:**

- No `accounts[0]` / `accounts[1]` positional access anywhere.
- `__init__.py` still exports `Forecast` and `UsageRead` from the package root.
- Tests green.

> **Breaking-change note:** `async_get_accounts()` currently returns the
> positional list and `ha-dominion-sc` calls it as
> `accounts, service_addr = await self.api.async_get_accounts()`. Either keep a
> backwards-compatible return shape or coordinate a matching change in
> `ha-dominion-sc` and bump the minor version. **Decide before starting Phase 4.**

---

### Phase 5 — CLI

Addresses **F9**.

- [ ] Move logic from `__main__.py` into `cli.py`; leave `__main__.py` as a
      three-line entry point.
- [ ] Fix the CSV overwrite defect: open the output file **once**, outside the
      per-account loop.
- [ ] Add a `service` / register column to CSV output (needed once multi-register
      accounts are supported).
- [ ] Add at least a smoke test for argument parsing and CSV writing.

**Acceptance:**

- `__main__.py` coverage no longer 0%.
- Multi-account runs produce one file containing all accounts.

---

## 5. Constraints

**Keep the public API stable.** `ha-dominion-sc` imports `DominionSC`,
`DominionSCTFAHandler`, `Forecast`, `UsageRead`, `create_cookie_jar`,
`ApiException`, `CannotConnect`, `InvalidAuth`, and `MfaChallenge` from the
package root. As long as `__init__.py` continues to export those names, this
refactor is invisible to the integration. Verify after every phase:

```bash
uv run python -c "import dominionsc; print(sorted(dominionsc.__all__))"
```

**Separate the PRs.** If contributing upstream, send the bugfix
(pilot ID + timezone) as its own small PR first. A tight bugfix merges quickly;
the same fix buried inside a multi-file reorganisation stalls.

**Behaviour-preserving.** If a phase requires changing a test assertion, stop
and confirm the old assertion was wrong (as was the case for the hardcoded
`"10106"` pilot-ID assertion) rather than adjusting the test to fit new code.

---

## 6. Risks

| Risk                                     | Mitigation                                                                                                     |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Silent behaviour change during a move    | Move code verbatim first; refactor its internals in a separate commit                                          |
| Hidden coupling surfaces mid-phase       | Phases are independently mergeable; stop and merge what works                                                  |
| Breaking `ha-dominion-sc`                | Public-API check after each phase; Phase 4 decision made up front                                              |
| Find/replace hitting the wrong duplicate | Verify every edit by line number, not by diff context alone — this already happened once with the pilot-ID fix |
| Committing real account data in fixtures | Redact account numbers, addresses, and user IDs before committing any XML/CSV sample                           |

---

## 7. Definition of done

- [ ] No module exceeds ~200 lines.
- [ ] `parsers/` is import-free of `aiohttp` and testable from fixtures.
- [ ] Pilot ID, user agent, endpoints, and timezone each appear in exactly one place.
- [ ] `uv run pytest` green; coverage on library modules no lower than baseline.
- [ ] `uv run ruff check .` clean.
- [ ] `dominionsc.__all__` unchanged from baseline.
