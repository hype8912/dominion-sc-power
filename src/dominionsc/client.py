"""DominionSC client facade: composes auth, transport, headers/urls, and parsing.

This is the class most callers actually use. It orchestrates login (via
auth.LoginFlow), forecast/usage requests (via headers.py/urls.py/transport.py),
and response parsing -- it should not itself contain header dicts, URL
strings, or pilot-ID/timezone literals. See docs/REFACTOR_PLAN.md Phase 2.
"""

import json
import logging
import zoneinfo
from datetime import datetime
from typing import Any

import aiohttp
from aiohttp.client_exceptions import ClientError

from . import headers as _headers
from . import urls as _urls
from .auth import LoginFlow, find_verification_token
from .config import UtilityConfig
from .exceptions import ApiException, CannotConnect, InvalidAuth
from .models.forecast import Forecast
from .models.register_reads import RegisterReads
from .models.usage_read import UsageRead
from .parsers.forecast import parse_forecast
from .parsers.greenbutton import parse_registers, parse_usage_reads
from .transport import DominionSCURLHandler

_LOGGER = logging.getLogger(__file__)


class DominionSC:
    """Class that can get historical and forecasted usage from an utility."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        login_data: dict[str, str] | None = None,  # {token: tfa_token}
        pilot_id: str | None = None,
    ) -> None:
        """Initialize.

        Args:
            session:    Shared aiohttp session (see note below on why it is
                        not mutated with default headers).
            username:   Dominion Energy SC account username/email.
            password:   Dominion Energy SC account password.
            login_data: Cached TFA session token from a prior login, if any.
            pilot_id:   Override for the Bidgely multi-tenant pilot ID (see
                        ``const.BIDGELY_PILOT_ID``). Defaults to the library's
                        known-good value for Dominion Energy SC; only needs
                        overriding if Dominion re-routes accounts to a
                        different Bidgely pipeline.

        """
        # Note: Do not modify default headers since Home Assistant that uses this library needs to use
        # a default session for all integrations. Instead specify the headers for each request.
        self.session: aiohttp.ClientSession = session
        self.username: str = username
        self.password: str = password
        self.login_data: dict[str, str] = login_data or {}
        self.access_token: str | None = None
        self.user_id: str | None = None
        self.accounts: list[list[str] | str] = []

        # Utility configuration (formerly in DominionSCUtility)
        self._tfa_secret: str | None = None

        # Single source of truth for endpoints/pilot id/user agent, used by
        # the headers/urls/auth helper modules. self._dominion_endpoint,
        # self.bidgely_endpoint, and self.timezone below mirror its values
        # for backwards compatibility (existing callers, including
        # ha-dominion-sc, read them directly) -- they are derived from it,
        # not a second, independently hardcoded copy of its defaults.
        self._config: UtilityConfig = UtilityConfig(pilot_id=pilot_id) if pilot_id else UtilityConfig()
        self._dominion_endpoint: str = self._config.dominion_endpoint
        self.bidgely_endpoint: str = self._config.bidgely_endpoint
        self.timezone: str = self._config.timezone
        self.pilot_id: str = self._config.pilot_id

    def _find_verification_token(self, webpage: str, path: str, funct: str) -> str:
        """Find and extract the verification token from a webpage.

        Thin wrapper kept for backward compatibility -- the actual
        implementation lives in auth.find_verification_token so
        auth.LoginFlow can share it without depending on DominionSC.
        """
        return find_verification_token(webpage, path, funct)

    async def async_login(self) -> None:
        """Login to the utility website and authorize for access.

        :raises InvalidAuth: if login information is incorrect
        :raises MfaChallenge: if interactive MFA is required
        :raises CannotConnect: if we receive any HTTP error
        :raises ApiException: if API response cannot be parsed (API structure may have changed)
        """
        try:
            self.access_token, self.user_id, self.accounts = await self._async_login_internal(
                self.session, self.username, self.password, self.login_data
            )
        except ClientError as err:
            raise CannotConnect(
                "Failed to connect to API",
                url=getattr(err, "url", None),
                status=getattr(err, "status", None),
                response_text=getattr(err, "text", None),
            ) from err

    async def _async_login_internal(
        self, session: aiohttp.ClientSession, username: str, password: str, login_data: dict[str, str] | None = None
    ) -> tuple[str, str, list[list[str] | str]]:
        """Login to the utility website.

        Thin wrapper kept for backward compatibility -- the actual login
        sequence lives in auth.LoginFlow.execute() (see docs/REFACTOR_PLAN.md
        Phase 2). Signature and exceptions raised are unchanged.

        :raises InvalidAuth: if login information is incorrect
        :raises MfaChallenge: if interactive MFA is required
        :raises CannotConnect: if there is a retryable connection exception
        :raises ApiException: if API response cannot be parsed (API structure may have changed)
        """
        return await LoginFlow(self._config).execute(session, username, password, login_data)

    async def async_get_accounts(self) -> list[list[str] | str]:
        """Get the account details captured during login.

        Returns:
            The legacy two-element list ``[measurement_types, service_address]``,
            e.g. ``[["ELECTRIC", "GAS"], "123 MAIN ST (*-****-****0-4464)"]``.
            Each measurement type is a valid ``account`` argument for
            ``async_get_usage_reads`` / ``async_get_register_reads``. The list is
            empty until ``async_login`` succeeds.

        """
        return self.accounts

    def get_timezone(self) -> str:
        """Get the timezone used by the utility."""
        return self.timezone

    async def async_get_forecast(self) -> Forecast:
        """Get current and forecasted usage and cost for the current monthly bill.

        :raises InvalidAuth: if login information is incorrect
        :raises CannotConnect: if there is a retryable connection exception
        :raises ApiException: if API response cannot be parsed (API structure may have changed)
        """
        accounts: list[list[str] | str] = await self.async_get_accounts()
        if not accounts:
            raise InvalidAuth("User not logged in to retrieve async_get_forecast.")

        forecasted_data: dict[str, Any] = await self._async_get_forecast_internal(self.session)

        return Forecast(
            start_date=forecasted_data["start_date"],
            end_date=forecasted_data["end_date"],
            current_date=forecasted_data["current_date"],
            cost_to_date=forecasted_data["cost_to_date"],
            forecasted_cost=forecasted_data["forecasted_cost"],
            typical_cost=forecasted_data["typical_cost"],
        )

    async def _async_get_forecast_internal(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        """Retrieve account AMI usage alerts with forecasted data.

        Return a dictionary with relevant data.

        :raises CannotConnect: if there is a retryable connection exception
        :raises ApiException: if API response cannot be parsed (API structure may have changed)
        """
        url_handler: DominionSCURLHandler = DominionSCURLHandler(session=session)
        config: UtilityConfig = self._config

        page_headers: dict[str, str] = _headers.dominion_page_headers(config, referer=config.dominion_access_referer)
        r0: str = await url_handler.call_api("get", _urls.home_page_url(config), page_headers)
        verification_token: str = self._find_verification_token(r0, "/", "async_get_forecast")

        url1: str = _urls.get_ami_usage_alerts_url(config)
        ajax_headers: dict[str, str] = _headers.dominion_ajax_headers(
            config, verification_token=verification_token, referer=config.dominion_home_referer
        )
        r1: str = await url_handler.call_api("get", url1, ajax_headers)
        try:
            r1_json: dict[str, Any] = json.loads(r1)
        except Exception as err:
            raise ApiException("Failed to decode forecast data.", url=url1, response_text=r1) from err

        forecast: Forecast = parse_forecast(r1_json, url=url1)
        return {
            "start_date": forecast.start_date,
            "end_date": forecast.end_date,
            "current_date": forecast.current_date,
            "cost_to_date": forecast.cost_to_date,
            "forecasted_cost": forecast.forecasted_cost,
            "typical_cost": forecast.typical_cost,
        }

    async def async_get_usage_reads(
        self,
        account: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[UsageRead]:
        """Get the usage reads from bidgely endpoint as one flat list.

        Args:
            account: Measurement type to fetch, ``"ELECTRIC"`` or ``"GAS"`` (see
                ``async_get_accounts``).
            start_date: Start of the window; the time of day is ignored and the
                date is floored to local midnight.
            end_date: End of the window; floored to local midnight the same way.

        Returns:
            Every interval reading across all registers. For net-metered accounts
            prefer ``async_get_register_reads``, which keeps registers separate.

        Raises:
            ValueError: If ``start_date`` or ``end_date`` is missing.
            InvalidAuth: If called before a successful ``async_login``.
            CannotConnect: If there is a retryable connection exception.
            ApiException: If API response cannot be parsed (API structure may have changed).

        """
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date are required.")
        if self.user_id is None:
            raise InvalidAuth("User not logged in to retrieve async_get_usage_reads.")

        # Floor the dates to midnight in the utility's local timezone (see
        # docs/REFACTOR_PLAN.md / git history: this used to be mislabeled
        # as UTC, which silently shifted the requested window).
        start_date = datetime.combine(start_date, datetime.min.time())
        end_date = datetime.combine(end_date, datetime.min.time())
        start_time_timestamp: int = int(start_date.replace(tzinfo=zoneinfo.ZoneInfo(self.timezone)).timestamp())
        end_date_timestamp: int = int(end_date.replace(tzinfo=zoneinfo.ZoneInfo(self.timezone)).timestamp())
        url: str = _urls.gb_download_url(self._config, self.user_id, start_time_timestamp, end_date_timestamp, account)
        r: str = await self._async_get_request(url, self._get_headers())
        return parse_usage_reads(r, self.timezone, url=url)

    async def async_get_register_reads(
        self,
        account: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[RegisterReads]:
        """Get usage reads grouped by meter register (ESPI UsagePoint).

        Unlike async_get_usage_reads (which flattens everything into one
        list), this keeps each physical register separate. For a
        net-metered solar ELECTRIC account this returns one RegisterReads
        for grid delivery and another for solar export, each keyed on its
        stable UsagePoint id, with reading signs preserved. Single-register
        accounts (most homes, all gas) return a one-element list.

        The library does not label registers as grid vs solar -- that
        decision belongs to the consumer.

        Args:
            account: Measurement type to fetch, ``"ELECTRIC"`` or ``"GAS"``.
            start_date: Start of the window, floored to local midnight.
            end_date: End of the window, floored to local midnight.

        Returns:
            One ``RegisterReads`` per UsagePoint, in the order first seen.

        Raises:
            ValueError: If ``start_date`` or ``end_date`` is missing.
            InvalidAuth: If called before a successful ``async_login``.
            CannotConnect: If there is a retryable connection exception.
            ApiException: If API response cannot be parsed (API structure may have changed).

        """
        if start_date is None or end_date is None:
            raise ValueError("start_date and end_date are required.")
        if self.user_id is None:
            raise InvalidAuth("User not logged in to retrieve async_get_register_reads.")

        # Same local-midnight flooring as async_get_usage_reads.
        start_date = datetime.combine(start_date, datetime.min.time())
        end_date = datetime.combine(end_date, datetime.min.time())
        start_time_timestamp: int = int(start_date.replace(tzinfo=zoneinfo.ZoneInfo(self.timezone)).timestamp())
        end_date_timestamp: int = int(end_date.replace(tzinfo=zoneinfo.ZoneInfo(self.timezone)).timestamp())
        url: str = _urls.gb_download_url(self._config, self.user_id, start_time_timestamp, end_date_timestamp, account)
        r: str = await self._async_get_request(url, self._get_headers())
        return parse_registers(r, self.timezone, url=url)

    def _get_headers(self) -> dict[str, str]:
        """Return Bidgely headers carrying the bearer token from the last login."""
        return _headers.bidgely_headers(self._config, access_token=self.access_token)

    async def _async_get_request(self, url: str, headers: dict[str, str]) -> str:
        """Return the result of an api call.

        Note: this deliberately calls self.session.get directly rather
        than going through DominionSCURLHandler -- see the module
        docstring in transport.py (finding F1) for why that's left as
        a known inconsistency for now rather than unified in this pass.
        """
        try:
            async with self.session.get(url, headers=headers) as resp:
                result: str = await resp.text(encoding="utf-8")
        except ClientError as err:
            raise CannotConnect(
                f"Failed to connect to API: {err}",
                url=url,
                status=getattr(err, "status", None),
                response_text=getattr(err, "text", None),
            ) from err
        return result
