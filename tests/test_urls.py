"""Tests for URL builders in urls.py."""

from unittest.mock import patch

from dominionsc.config import UtilityConfig
from dominionsc.urls import (
    authenticate_url,
    gb_download_url,
    get_account_listing_url,
    get_ami_usage_alerts_url,
    get_bidgely_sdk_init_url,
    home_page_url,
    init_account_url,
    init_authentication_url,
    login_page_url,
    send_pin_code_url,
    verify_2fa_token_url,
    verify_pin_url,
    wc_session_url,
)

_CONFIG = UtilityConfig(
    dominion_endpoint="https://dom.example.com",
    bidgely_endpoint="https://bidgely.example.com",
)


def test_login_page_url_points_to_login_fragment():
    """login_page_url appends the /access/#login fragment to the Dominion endpoint."""
    url = login_page_url(_CONFIG)

    assert url == "https://dom.example.com/access/#login"


def test_home_page_url_is_root_of_dominion_endpoint():
    """home_page_url returns the base Dominion endpoint with a trailing slash."""
    url = home_page_url(_CONFIG)

    assert url == "https://dom.example.com/"


def test_authenticate_url_targets_fusionapi_login():
    """authenticate_url points to the FusionAPI Authenticate endpoint."""
    url = authenticate_url(_CONFIG)

    assert url == "https://dom.example.com/fusionapi/LoginWebApi/Authenticate/"


def test_send_pin_code_url_targets_fusionapi_send_pin():
    """send_pin_code_url points to the FusionAPI SendPINCode endpoint."""
    url = send_pin_code_url(_CONFIG)

    assert url == "https://dom.example.com/fusionapi/LoginWebApi/SendPINCode/"


def test_verify_pin_url_targets_fusionapi_verify_pin():
    """verify_pin_url points to the FusionAPI VerifyPIN endpoint."""
    url = verify_pin_url(_CONFIG)

    assert url == "https://dom.example.com/fusionapi/LoginWebApi/VerifyPIN/"


def test_verify_2fa_token_url_embeds_token_and_cache_buster():
    """verify_2fa_token_url embeds the TFA token and a numeric cache-buster parameter."""
    with patch("dominionsc.urls.cache_buster", return_value="1234567890"):
        url = verify_2fa_token_url(_CONFIG, tfa_token="abc123")

    assert "token=abc123" in url
    assert "_=1234567890" in url
    assert url.startswith("https://dom.example.com/fusionapi/LoginWebApi/Verify2FAToken/")


def test_init_authentication_url_contains_cache_buster():
    """init_authentication_url includes a cache-buster query parameter."""
    with patch("dominionsc.urls.cache_buster", return_value="9999"):
        url = init_authentication_url(_CONFIG)

    assert url == "https://dom.example.com/fusionapi/LoginWebApi/InitAuthentication/?_=9999"


def test_init_account_url_contains_cache_buster():
    """init_account_url includes a cache-buster query parameter."""
    with patch("dominionsc.urls.cache_buster", return_value="1111"):
        url = init_account_url(_CONFIG)

    assert url.startswith("https://dom.example.com/fusionapi/AccountSummaryWebApi/InitAccount/")
    assert "_=1111" in url


def test_get_bidgely_sdk_init_url_includes_service_type():
    """get_bidgely_sdk_init_url includes service=E and serviceAccountType=R."""
    with patch("dominionsc.urls.cache_buster", return_value="0"):
        url = get_bidgely_sdk_init_url(_CONFIG)

    assert "service=E" in url
    assert "serviceAccountType=R" in url
    assert url.startswith("https://dom.example.com/fusionapi/BidgelyWebApi/GetBidgelySDKInit/")


def test_get_ami_usage_alerts_url_contains_cache_buster():
    """get_ami_usage_alerts_url includes a cache-buster query parameter."""
    with patch("dominionsc.urls.cache_buster", return_value="2222"):
        url = get_ami_usage_alerts_url(_CONFIG)

    assert url.startswith("https://dom.example.com/fusionapi/CommonWebApi/GetAccountAMIUsageAlerts/")
    assert "_=2222" in url


def test_wc_session_url_targets_bidgely_endpoint():
    """wc_session_url points to the Bidgely wc-session path, not the Dominion endpoint."""
    url = wc_session_url(_CONFIG)

    assert url == "https://bidgely.example.com/v2.0/web/wc-session"


def test_get_account_listing_url_contains_cache_buster():
    """get_account_listing_url targets the AccountManagement API and includes a cache buster."""
    with patch("dominionsc.urls.cache_buster", return_value="3333"):
        url = get_account_listing_url(_CONFIG)

    assert url.startswith("https://dom.example.com/fusionapi/AccountManagementWebApi/GetAccountListing/")
    assert "_=3333" in url


def test_gb_download_url_embeds_all_parameters():
    """gb_download_url encodes user ID, timestamps, and measurement type into the path and query."""
    url = gb_download_url(_CONFIG, user_id="u42", start_timestamp=1000, end_timestamp=2000, measurement_type="E")

    assert "/users/u42/gb-download" in url
    assert "start=1000" in url
    assert "end=2000" in url
    assert "measurement-type=E" in url
    assert "file-type=XML" in url
    assert url.startswith("https://bidgely.example.com/")
