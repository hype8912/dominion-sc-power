"""URL builders for Dominion Energy SC and Bidgely endpoints.

Every request path this library calls should be built here, not
constructed inline elsewhere -- this is the single, greppable source
of truth for "what endpoints does this library talk to." See
docs/REFACTOR_PLAN.md finding F3 for the full endpoint inventory this
was extracted from.
"""

from .config import UtilityConfig
from .transport import cache_buster


def login_page_url(config: UtilityConfig) -> str:
    """Login page, used to retrieve the initial verification token."""
    return config.dominion_endpoint + "/access/#login"


def home_page_url(config: UtilityConfig) -> str:
    """Return the authenticated home page URL, used to retrieve a fresh verification token."""
    return config.dominion_endpoint + "/"


def authenticate_url(config: UtilityConfig) -> str:
    """Submit username/password."""
    return config.dominion_endpoint + "/fusionapi/LoginWebApi/Authenticate/"


def verify_2fa_token_url(config: UtilityConfig, tfa_token: str) -> str:
    """Verify a previously-issued TFA token, skipping interactive TFA."""
    return config.dominion_endpoint + f"/fusionapi/LoginWebApi/Verify2FAToken/?token={tfa_token}&_={cache_buster()}"


def init_authentication_url(config: UtilityConfig) -> str:
    """Retrieve available TFA delivery options (phone/email)."""
    return config.dominion_endpoint + f"/fusionapi/LoginWebApi/InitAuthentication/?_={cache_buster()}"


def send_pin_code_url(config: UtilityConfig) -> str:
    """Trigger delivery of a TFA code to the selected option."""
    return config.dominion_endpoint + "/fusionapi/LoginWebApi/SendPINCode/"


def verify_pin_url(config: UtilityConfig) -> str:
    """Submit a user-entered TFA code."""
    return config.dominion_endpoint + "/fusionapi/LoginWebApi/VerifyPIN/"


def get_account_listing_url(config: UtilityConfig) -> str:
    """Confirm whether the account is a single-account (only supported case)."""
    return config.dominion_endpoint + f"/fusionapi/AccountManagementWebApi/GetAccountListing/?_={cache_buster()}"


def init_account_url(config: UtilityConfig) -> str:
    """Retrieve the service address and account number."""
    return config.dominion_endpoint + f"/fusionapi/AccountSummaryWebApi/InitAccount/?_={cache_buster()}"


def get_bidgely_sdk_init_url(config: UtilityConfig) -> str:
    """Retrieve the encrypted token used to exchange for a Bidgely bearer token."""
    return (
        config.dominion_endpoint
        + f"/fusionapi/BidgelyWebApi/GetBidgelySDKInit/?service=E&serviceAccountType=R&_={cache_buster()}"
    )


def get_ami_usage_alerts_url(config: UtilityConfig) -> str:
    """Retrieve current-bill usage/cost forecast data."""
    return config.dominion_endpoint + f"/fusionapi/CommonWebApi/GetAccountAMIUsageAlerts/?_={cache_buster()}"


def wc_session_url(config: UtilityConfig) -> str:
    """Exchange the encrypted token for a Bidgely bearer token."""
    return config.bidgely_endpoint + "/v2.0/web/wc-session"


def gb_download_url(
    config: UtilityConfig,
    user_id: str,
    start_timestamp: int,
    end_timestamp: int,
    measurement_type: str,
) -> str:
    """Green Button interval-data export for a given account/measurement type."""
    return (
        config.bidgely_endpoint
        + f"/v2.0/dashboard/users/{user_id}/gb-download"
        f"?start={start_timestamp}&end={end_timestamp}"
        f"&measurement-type={measurement_type}&file-type=XML"
    )
