"""HTTP transport primitives.

DominionSCURLHandler is the shared, mockable transport used throughout
the login and forecast flows (DominionSC._async_login_internal,
DominionSCTFAHandler, DominionSC._async_get_forecast_internal). Tests
patch DominionSCURLHandler.call_api directly and rely on the exact
number and order of calls made by those flows, so its signature and
behavior here are intentionally unchanged from the pre-refactor
implementation -- only its location moved.

Note: DominionSC.async_get_usage_reads currently calls
self.session.get directly via DominionSC._async_get_request rather
than going through DominionSCURLHandler. That's a pre-existing
inconsistency (see docs/REFACTOR_PLAN.md, finding F1) left alone in
this phase because several tests mock session.get directly for that
path; unifying it requires updating those tests and is deferred.
"""

import time

import aiohttp

from .exceptions import CannotConnect


def cache_buster() -> str:
    """Return a millisecond-resolution timestamp string.

    Several Dominion endpoints require a cache-busting ``_`` query
    parameter. This is the one place that timestamp gets generated;
    urls.py calls this rather than each URL builder rolling its own.
    """
    return str(int(time.time() * 1000))


class DominionSCURLHandler:
    """Centralizes and handles all web communication."""

    def __init__(self, session: aiohttp.ClientSession, timeout: aiohttp.ClientTimeout | float | None = None) -> None:
        """Initialize the handler."""
        self._session = session
        self._timeout = timeout if timeout is not None else aiohttp.ClientTimeout(total=30)

    async def call_api(
        self, method: str, url: str, headers: dict[str, str], json_data: dict[str, str] | None = None
    ) -> str | None:
        """Return the result of an api call."""
        api_func = None
        if method == "post":
            api_func = self._session.post
        elif method == "get":
            api_func = self._session.get
        else:
            raise ValueError(f"Improper method for API call: {method}. Must be GET or POST.")

        try:
            async with api_func(url, json=json_data, headers=headers, timeout=self._timeout) as resp:
                result = await resp.text(encoding="utf-8")
        except aiohttp.ClientError as err:
            raise CannotConnect(
                "Failed to make an API call due to network error.",
                url=url,
                status=getattr(err, "status", None),
                response_text=getattr(err, "text", None),
            ) from err
        return result
