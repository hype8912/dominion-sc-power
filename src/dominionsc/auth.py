"""Authentication: verification-token scraping, TFA challenge/response, login flow.

DominionSCTFAHandler and the full login sequence used to live inline in
dominionsc.py; this module isolates them so auth can be read and tested
without touching usage/forecast parsing (see docs/REFACTOR_PLAN.md Phase 2).
"""

import json
import logging
import re

import aiohttp

from . import headers as _headers
from . import urls as _urls
from .config import UtilityConfig
from .exceptions import ApiException, CannotConnect, InvalidAuth, MfaChallenge
from .transport import DominionSCURLHandler

_LOGGER = logging.getLogger(__file__)


def find_verification_token(webpage: str, path: str, funct: str) -> str | None:
    """Find and extract the verification token from a webpage."""
    try:
        token_search = re.findall(r'<input name="__RequestVerificationToken" type="hidden" value="(.*)" \/>', webpage)
        return token_search[0].split('" />', 1)[0]
    except Exception as err:
        raise CannotConnect(f"Cannot retrieve request verification token (path={path}, funct={funct}).") from err


class DominionSCTFAHandler:
    """TFA Handler for utility."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        dominion_endpoint: str,
        headers: dict[str, str],
        url_handler: DominionSCURLHandler,
    ):
        """Initialize the TFA handler."""
        self._session = session
        self._dominion_endpoint: str = dominion_endpoint
        self._headers: dict[str, str] = headers
        self._url_handler: DominionSCURLHandler = url_handler
        self._tfa_options: dict[str, str] = {}

    @property
    def _config(self) -> UtilityConfig:
        """Throwaway config carrying just the endpoint, for url builders."""
        return UtilityConfig(dominion_endpoint=self._dominion_endpoint)

    async def async_get_tfa_options(self) -> dict[str, str]:
        """Return a dictionary of TFA options available to the user.

        The key is a stable identifier for the option, and the value is a
        user-friendly description (e.g., {"sms_1": "Text message to ******1234"}).

        The returned dictionary can be empty if no TFA options are available, i.e. the utility
        immediately asks for the code after login.
        """
        tfa_options: dict[str, str] = {}
        url1 = _urls.init_authentication_url(self._config)
        r1 = await self._url_handler.call_api("get", url1, self._headers)
        try:
            _tfa_options = json.loads(r1)["data"]["userInfo"]
        except Exception as err:
            raise ApiException("Unable to decode InitAuthentication (TFA) userInfo", url=url1, response_text=r1) from err
        tfa_phone = _tfa_options["phoneNumbers"]
        tfa_email = _tfa_options["emailAddresses"]

        if tfa_phone:
            tfa_options[tfa_phone[0]] = tfa_phone[0]

        if tfa_email:
            tfa_options[tfa_email[0]] = tfa_email[0]

        self._tfa_options = tfa_options
        return tfa_options

    async def async_select_tfa_option(self, option_id: str) -> None:
        """Select an TFA option and trigger the code delivery.

        :raises CannotConnect: if the selection fails for reasons other than bad credentials.
        """
        _LOGGER.debug("Selecting TFA option %s", option_id)
        url1 = _urls.send_pin_code_url(self._config)
        data1 = {"sendMethod": option_id, "_df": ""}
        r1 = await self._url_handler.call_api("post", url1, self._headers, data1)
        if not json.loads(r1)["data"]:
            raise ApiException("Error with TFA option selection.", url=url1, response_text=r1)

        _LOGGER.debug("Successfully selected TFA option")

    async def async_submit_tfa_code(self, code: str) -> dict[str, str] | None:
        """Submit the user-provided code.

        On success, return login data that can be passed to async_login in order to skip TFA.
        On failure, raise InvalidAuth.

        :raises InvalidAuth: if the code is incorrect.
        """
        _LOGGER.debug("Submitting TFA code")

        url1 = _urls.verify_pin_url(self._config)
        data1 = {"PINcode": code, "registerDevice": True, "_df": ""}
        r1 = await self._url_handler.call_api("post", url1, self._headers, data1)
        try:
            if json.loads(r1)["data"]["isVerified"]:
                # tfa_token SUCCESS
                return {"tfa_token": json.loads(r1)["data"]["token"]}
        except Exception as err:
            raise ApiException("Unable to decode VerifyPIN isVerified", url=url1, response_text=r1) from err

        raise InvalidAuth(f"Invalid TFA code: {r1}")


class LoginFlow:
    """Executes the full Dominion + Bidgely login sequence for one config."""

    def __init__(self, config: UtilityConfig) -> None:
        """Initialize with the utility config to log in against."""
        self._config = config

    async def execute(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        login_data: dict[str, str] | None = None,
    ) -> tuple[str, str, list | None]:
        """Login to the utility website.

        Return the access token or None

        :raises InvalidAuth: if login information is incorrect
        :raises MfaChallenge: if interactive MFA is required
        :raises CannotConnect: if there is a retryable connection exception
        :raises ApiException: if API response cannot be parsed (API structure may have changed)
        """
        if login_data is None:
            login_data = {}  # {tfa_token: tfa_token}
        tfa_token: str = str(login_data.get("tfa_token", ""))

        url_handler = DominionSCURLHandler(session=session)
        config = self._config

        # Load login page and retrieve verification token
        r0 = await url_handler.call_api("get", _urls.login_page_url(config), _headers.user_agent_only(config))
        verification_token = find_verification_token(r0, "/access", "async_login")

        # Initial authentication test
        url1 = _urls.authenticate_url(config)
        ajax_headers = _headers.dominion_ajax_headers(
            config,
            verification_token=verification_token,
            referer="https://account.dominionenergysc.com/access/",
            origin="https://account.dominionenergysc.com",
        )
        body = {"userName": username, "password": password, "_df": ""}
        r1 = await url_handler.call_api("post", url1, ajax_headers, body)
        try:
            r1_status = json.loads(r1)["data"]["status"]
        except Exception as err:
            raise ApiException("Unable to decode Authenticate data status.", url=url1, response_text=r1) from err
        if r1_status == "failed":
            raise InvalidAuth(f"Invalid credentials, please try again. {r1}")
        if r1_status != "twoFA":
            raise InvalidAuth(
                "Unsuccessful authentication (possible no TFA required, please "
                f"report on github if you get this error): resp={r1}"
            )

        # TFA
        # Do we have a TFA token?
        if tfa_token != "":
            url2 = _urls.verify_2fa_token_url(config, tfa_token)
            r2 = await url_handler.call_api("get", url2, ajax_headers)
            # Was token accepted?
            if not json.loads(r2)["data"]:
                tfa_token = None

        if not tfa_token:
            # Regenerate TFA token
            raise MfaChallenge(
                "Need new TFA token",
                DominionSCTFAHandler(session, config.dominion_endpoint, ajax_headers, url_handler),
            )

        # Here we assume that the TFA token authorization was successful
        page_headers = _headers.dominion_page_headers(config, referer="https://account.dominionenergysc.com/access/")
        r3 = await url_handler.call_api("get", _urls.home_page_url(config), page_headers)
        verification_token = find_verification_token(r3, "/", "async_login")

        # Subsequent authenticated calls use a fresh verification token, a
        # new referer, and no Origin header (equivalent to the original
        # code's del headers1["Origin"]).
        ajax_headers = _headers.dominion_ajax_headers(
            config,
            verification_token=verification_token,
            referer="https://account.dominionenergysc.com/",
        )

        url4 = _urls.get_account_listing_url(config)
        r4 = await url_handler.call_api("get", url4, ajax_headers)
        try:
            _ = json.loads(r4)["data"]["singleAccount"]
        except Exception as err:
            raise ApiException("Unable to decode GetAccountListing singleAccount.", url=url4, response_text=r4) from err
        if json.loads(r4)["data"]["singleAccount"] is not True:
            raise InvalidAuth(f"User has multiple accounts, not currently implemented (please report on github): {r4}")

        url5 = _urls.init_account_url(config)
        r5 = await url_handler.call_api("get", url5, ajax_headers)

        try:
            serviceAddressAndAccountNo = json.loads(r5)["data"]["account"]["serviceAddressAndAccountNo"]
        except Exception as err:
            raise ApiException("Unable to decode InitAccount serviceAddr.", url=url5, response_text=r5) from err

        url6 = _urls.get_bidgely_sdk_init_url(config)
        r6 = await url_handler.call_api("get", url6, ajax_headers)
        try:
            encryptedToken = json.loads(r6)["data"]["payload"]
        except Exception as err:
            raise ApiException("Unable to decode GetBidgelySDKInit encToken", url=url6, response_text=r6) from err

        # Finally get bearer
        url7 = _urls.wc_session_url(config)
        bidgely_login_headers = _headers.bidgely_headers(config)
        body2 = {"clientId": "prod_desc_widget", "encryptedData": encryptedToken}

        r7 = await url_handler.call_api("post", url7, bidgely_login_headers, body2)
        try:
            r7_json = json.loads(r7)
            accessToken = r7_json["payload"]["tokenDetails"]["accessToken"]
            userId = r7_json["payload"]["userProfileDetails"]["userId"]
        except Exception as err:
            raise ApiException("Unable to get accessToken or userId.", url=url7, response_text=r7) from err

        accounts = [[]]
        accounts.append(serviceAddressAndAccountNo)
        try:
            for dataTypes in json.loads(r7)["payload"]["userTypeDetails"]["measurementToUserTypeMappings"]:
                if dataTypes["measurementType"] in ["ELECTRIC", "GAS"]:
                    accounts[0].append(dataTypes["measurementType"])
        except Exception as err:
            raise ApiException("Unable to decode measurement type from wc-session.", url=url7, response_text=r7) from err

        return accessToken, userId, accounts
