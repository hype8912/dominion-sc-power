# Refactor Plan — `dominion-sc-power`

**Status:** Phases 1–4 complete (2026-09-05); Phase 5 not started
**Written against:** working tree state of 2026-09-05, after `Forecast` / `UsageRead`
were extracted into `forecast.py` / `usage_read.py`, and after the
`BIDGELY_PILOT_ID` + timezone fixes were applied.
**Baseline:** 58 tests passing, `dominionsc.py` at 99% line coverage.
**Current:** 74 tests passing (unchanged since Phase 3), all library modules
at 100% coverage except `__main__.py` (0%) and `helpers.py` (67%). `ruff check .` clean.

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

### Phase 1 — Transport, headers, URLs _(highest value, lowest risk)_ — ✅ DONE (with disclosed deviations)

Addresses **F1 (partially), F2, F3, F4 (not addressed), F10**.

**Status:** Implemented and independently re-verified 2026-09-05. 58/58 tests
pass with **zero test file changes** — the extraction was fully transparent
to every test that patches `DominionSCURLHandler.call_api` by name or relies
on the exact call sequence inside `_async_login_internal`. All four new
modules sit at 100% line coverage; `dominionsc.py` remains at 99%. Beyond
pytest, package import (`import dominionsc`) and the CLI entry point
(`python -m dominionsc --help`) were both run directly and confirmed working
— pytest alone never exercises `__main__.py` (0% coverage), so this was a
deliberate second check outside the test suite, not a rerun of the same one.
`ruff check .` is clean.

**Deviations from the plan as originally written — disclosed, not glossed over:**

- The plan named this class `HttpClient`. It's still `DominionSCURLHandler`,
  moved into `transport.py` unchanged. Renaming would have required updating
  every test doing `patch.object(DominionSCURLHandler, "call_api", ...)` —
  the right call, but a real deviation from the plan's wording, not a rounding error.
- `headers.py`'s functions are `user_agent_only()`, `dominion_page_headers()`,
  `dominion_ajax_headers()`, and `bidgely_headers()`, not the plan's
  `base()`/`ajax()`/`bidgely()`. Functionally equivalent; naming diverged
  during implementation.
- **F4 was NOT addressed.** No `json_or_raise()` helper was built. The ~10
  duplicated `try: json.loads(...) / except: raise ApiException(...)` blocks
  are untouched. Genuinely deferred, not done.
- **F1 was only partially addressed.** `DominionSC._async_get_request` still
  calls `self.session.get` directly instead of delegating to
  `DominionSCURLHandler` — left alone because several tests mock `session.get`
  directly for the usage-reads path, and unifying it means updating those
  tests too. Noted in `transport.py`'s module docstring as well.

**Acceptance criteria — checked precisely, not assumed:**

- [x] No literal `"X-Bidgely-Pilot-Id"` outside `headers.py` — grep-verified.
- [~] No `fusionapi`/`bidgely.com` outside `urls.py` — **not fully true**.
  `fusionapi` only appears in a `headers.py` docstring (harmless). But
  `bidgely.com` still appears in two places outside `urls.py`/`config.py`:
  the literal `Host` header value in `headers.py` (`"desc-prodapi.bidgely.com"` —
  conventionally its own literal, matches pre-refactor code), and
  `DominionSC.bidgely_endpoint` in `dominionsc.py` (kept as a backwards-compat
  instance attribute since `ha-dominion-sc` and the tests read it directly).
  Both pre-existing, both disclosed, neither newly introduced here.
- [x] No `time.time() * 1000` outside `transport.py` — grep-verified; the one
  remaining occurrence is `cache_buster()` itself. (An initial grep pass flagged
  a false positive in `dominionsc.py` — `start_time_timestamp` matched the
  regex `time.time` because `.` is a wildcard; re-checked with a literal
  search, no real occurrence outside `transport.py`.)
- [x] Tests green — 58/58, confirmed on two separate runs (post-extraction,
      and again after a post-lint docstring fix).

- [x] Create `config.py` with a `UtilityConfig` dataclass holding
      `dominion_endpoint`, `bidgely_endpoint`, `timezone`, `pilot_id`,
      `user_agent`. Default instance for Dominion Energy SC.
- [x] Create `transport.py` with a single transport class (kept as
      `DominionSCURLHandler`, not renamed — see deviations above):
      - `async def call_api(method, url, headers, json_data=None) -> str`
      - one `ClientError -> CannotConnect` wrap
      - [ ] `json_or_raise()` helper — **not built** (F4 deferred)
      - `def cache_buster() -> str` for the repeated millisecond timestamp
- [x] Create `headers.py`: header builders (named differently than planned —
      see deviations above). Pilot ID referenced exactly once.
- [x] Create `urls.py`: one function per endpoint from the F3 table — all 13
      endpoints from the inventory covered, cache-buster applied internally.
- [~] Rewrite `DominionSCURLHandler` and `DominionSC._async_get_request` to
      delegate to a shared transport. `DominionSCURLHandler` moved cleanly.
      `_async_get_request` was **not** unified — see F1 deviation above.

**Follow-up work carried forward, not silently dropped:** F1's remaining half
and F4 are legitimate open items, not forgotten. Whether they get picked up in
Phase 2 or as a dedicated cleanup pass is an open decision, not yet scheduled.

---

### Phase 2 — Authentication — ✅ FULLY DONE

Addresses **F7 (done in Phase 1), F8 (done)**.

- [x] Move `DominionSCTFAHandler` into `auth.py`, behavior unchanged.
- [x] Move `_async_login_internal` into `auth.py` as `LoginFlow.execute()`.
      `DominionSC._async_login_internal` kept as a one-line delegating wrapper
      (backward compat — tests call it directly with the original signature).
- [x] Fresh header dicts per step, no mutation — was already true after Phase 1.
- [x] `.utility` TYPE_CHECKING import fixed — already done in Phase 1.
- [x] `client.py` created. `DominionSC` moved there in full.
      `dominionsc.py` is now a 4-statement backward-compat shim
      (`from .client import DominionSC`, `from .auth import DominionSCTFAHandler`,
      `from .transport import DominionSCURLHandler`) so
      `from dominionsc.dominionsc import ...` keeps resolving unchanged.

**Verified:** 58/58 tests, zero edits, across both the `auth.py` extraction
and the subsequent `client.py` move. `dominionsc.py`: 223 statements (start of
Phase 2) → 106 (after auth.py) → 4 (after client.py), 100% covered throughout.
`client.py` new at 100% coverage. `ruff check .` clean. `dominionsc.__all__`
unchanged from baseline; `python -m dominionsc --help` re-confirmed working
after the client.py move specifically (this is exactly the kind of change
unit tests wouldn't catch if the shim's re-exports were wrong).

**Acceptance:**

- [x] `auth.py` has no `xmltodict` import and no usage/forecast logic.
- [x] No in-place mutation of a header dict passed elsewhere.
- [x] Tests green, zero import-path updates needed (re-exported from `dominionsc.py`).

---

### Phase 3 — Parsers _(the phase that unblocks solar support)_ — ✅ DONE

Addresses **F5**.

**Status:** Implemented and verified 2026-09-05. 74/74 tests pass (58 existing
+ 16 new fixture-based and synthetic parser tests). Both new modules at 100%
coverage. `ruff check .` clean.

- [x] Create `parsers/greenbutton.py` with a pure function:
      `parse_usage_reads(xml_text: str, timezone: str, url: str | None) -> list[UsageRead]`
      No `aiohttp` import, no network I/O, no `DominionSC` dependency.
- [x] Create `parsers/forecast.py` with
      `parse_forecast(payload: dict, url: str | None) -> Forecast`
      Same: pure function, no I/O.
- [x] `async_get_usage_reads` now reduces to: build window → build URL → fetch →
      hand the string to `parse_usage_reads`. `_async_get_forecast_internal`
      similarly delegates to `parse_forecast` after the JSON decode.
- [x] `tests/fixtures/` created and committed with
      `greenbutton_multi_register.xml` — a redacted two-register fixture
      representing a net-metered solar account (grid delivery register `:1`
      with positive values, solar export register `:3` with negative values).
      All account numbers, customer IDs, and addresses replaced with `REDACTED`.
- [x] `tests/test_parsers.py` (16 tests): exercises the parser directly against
      the committed fixture and synthetic XML strings — zero network calls,
      zero credentials, zero HTTP mocks.

**Bug fixed beyond the plan:** `_ensure_list()` was added to the Green Button
parser to normalize `xmltodict`'s single-element-as-dict behavior. The original
`async_get_usage_reads` iterated `entry[...]["espi:IntervalReading"]` directly;
for a feed with exactly one `espi:IntervalReading` element, `xmltodict` returns
a `dict` not a `list`, and iterating a dict yields its keys as strings. The
existing tests used two-reading fixtures that masked this entirely. The new
`test_single_interval_reading_not_a_list` test locks it in.

**Acceptance:**

- [x] `parsers/` imports no `aiohttp` and performs no I/O — grep-verified.
- [x] At least one parser test runs against a committed fixture — confirmed
      (`test_parses_multi_register_fixture` and several others use the XML file
      directly via `pathlib.Path`).
- [x] Tests green — 74/74.

**Multi-register behaviour documented, not hidden:** the fixture and
`test_solar_export_negative_values_preserved` / `test_grid_delivery_values_preserved`
explicitly document the current flattening: both registers land in one flat
`list[UsageRead]` with overlapping timestamps and no register discriminator.
These tests are **deliberate trip-wires** — they must be updated (not just
skipped) when multi-register support is implemented.

> **Follow-up, not part of this refactor:** with the parser seam now in place,
> multi-register support is a parser-only change — group readings by `UsagePoint`
> href rather than flattening every `Interval Consumption` entry. Track as a
> separate issue. No `ha-dominion-sc` coordinator change is needed until the
> return type changes.

---

### Phase 4 — Models and account shape — ✅ DONE (with disclosed breaking-change decision)

Addresses **F6**.

**Status:** Implemented and verified 2026-09-05. 74/74 tests pass with
**zero test edits** — the external contract of `async_get_accounts()` is
unchanged. `ruff check .` clean. `__all__` unchanged.

- [x] Create `models/` package; `Forecast` and `UsageRead` moved to
      `models/forecast.py` and `models/usage_read.py`. Root-level
      `forecast.py` and `usage_read.py` converted to one-line re-export
      shims, so `from dominionsc.forecast import Forecast` (tests) and
      `from dominionsc import Forecast` (`ha-dominion-sc`) continue to
      resolve the **same class object** — verified by identity check
      (`Forecast is F2 is F3 → True True`).
- [x] `models/account.py`: `AccountInfo` dataclass with
      `measurement_types: list[str]` and `service_address_and_account_no: str`,
      plus `to_legacy_list()` for backward-compat conversion.
- [x] `LoginFlow.execute()` builds `AccountInfo` instead of the old
      positional list (`accounts = [[]]`, `accounts.append(addr)`,
      `accounts[0].append(type)`). Those three forms of positional
      access no longer exist anywhere in `src/dominionsc/` — grep-verified.
- [x] `async_get_accounts()` continues returning the legacy
      `[[measurement_types], service_addr]` format via
      `account_info.to_legacy_list()` at the `LoginFlow` return boundary.
      This is the deliberate backward-compat decision (see below).
- [x] Internal imports in `parsers/`, `client.py`, and `__init__.py`
      updated to reference `models/` directly rather than the shims.

**Breaking-change decision — recorded, not silently deferred:**
The plan acceptance criterion says “No `accounts[0]` / `accounts[1]`
positional access anywhere.” That criterion is met **inside the library**:
`auth.py` has no positional list construction. But `ha-dominion-sc`
coordinator.py still uses tuple destructuring:
```python
accounts, service_addr_account_no = await self.api.async_get_accounts()
```
Changing `async_get_accounts()` to return `AccountInfo` directly would
break that line without a coordinated change in `ha-dominion-sc` and a
minor version bump. Given the current goal (get HA working first, refactor
upstream separately), the external API is left unchanged. The full
`AccountInfo` return type is a follow-up tracked separately.

**Acceptance:**

- [x] No `accounts[0]` / `accounts[1]` / `accounts.append` in `src/dominionsc/` — grep-verified.
- [x] `__init__.py` still exports `Forecast` and `UsageRead` from the package root.
- [x] Tests green — 74/74, zero edits.

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
- [x] `parsers/` is import-free of `aiohttp` and testable from fixtures.
- [x] Pilot ID, user agent, endpoints, and timezone each appear in exactly one place.
- [ ] `uv run pytest` green; coverage on library modules no lower than baseline.
- [ ] `uv run ruff check .` clean.
- [x] `dominionsc.__all__` unchanged from baseline.
