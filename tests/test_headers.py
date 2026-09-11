"""Tests for HTTP header builders in headers.py."""

from dominionsc.config import UtilityConfig
from dominionsc.headers import (
    bidgely_headers,
    dominion_ajax_headers,
    dominion_page_headers,
    user_agent_only,
)

_CONFIG = UtilityConfig(
    user_agent="TestAgent/1.0",
    pilot_id="99999",
    dominion_endpoint="https://example.com",
    bidgely_endpoint="https://bidgely.example.com",
)


def test_user_agent_only_returns_single_header():
    """user_agent_only builds a dict containing only the User-Agent key."""
    headers = user_agent_only(_CONFIG)

    assert headers == {"User-Agent": "TestAgent/1.0"}


def test_dominion_page_headers_contains_required_keys():
    """dominion_page_headers includes User-Agent, Host, and Referer."""
    headers = dominion_page_headers(_CONFIG, referer="https://example.com/prev")

    assert headers["User-Agent"] == "TestAgent/1.0"
    assert headers["Host"] == "account.dominionenergysc.com"
    assert headers["Referer"] == "https://example.com/prev"
    assert len(headers) == 3


def test_dominion_ajax_headers_without_origin_omits_origin_key():
    """dominion_ajax_headers produces all six required keys and omits Origin when not provided."""
    headers = dominion_ajax_headers(_CONFIG, verification_token="tok123", referer="https://example.com/page")

    assert "Origin" not in headers
    assert headers["User-Agent"] == "TestAgent/1.0"
    assert headers["__RequestVerificationToken"] == "tok123"
    assert headers["IsAjax"] == "true"
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["Host"] == "account.dominionenergysc.com"
    assert headers["Referer"] == "https://example.com/page"
    assert len(headers) == 6


def test_dominion_ajax_headers_with_origin_includes_origin_key():
    """dominion_ajax_headers includes Origin as the seventh key when a value is provided."""
    headers = dominion_ajax_headers(
        _CONFIG,
        verification_token="tok123",
        referer="https://example.com/",
        origin="https://example.com",
    )

    assert headers["Origin"] == "https://example.com"
    assert len(headers) == 7


def test_bidgely_headers_without_token_omits_authorization():
    """bidgely_headers produces all eight required keys and omits Authorization when no token given."""
    headers = bidgely_headers(_CONFIG)

    assert "Authorization" not in headers
    assert headers["User-Agent"] == "TestAgent/1.0"
    assert headers["IsAjax"] == "true"
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["Host"] == "desc-prodapi.bidgely.com"
    # Origin and Referer are hardcoded to the Dominion portal, not the Bidgely endpoint
    assert headers["Origin"] == "https://account.dominionenergysc.com"
    assert headers["Referer"] == "https://account.dominionenergysc.com/"
    assert headers["X-Bidgely-Client-Type"] == "WIDGETS"
    assert headers["X-Bidgely-Pilot-Id"] == "99999"
    assert len(headers) == 8


def test_bidgely_headers_with_token_adds_bearer_authorization():
    """bidgely_headers includes Authorization as the ninth key when a token is supplied."""
    headers = bidgely_headers(_CONFIG, access_token="mytoken")

    assert headers["Authorization"] == "Bearer mytoken"
    assert len(headers) == 9


def test_each_header_builder_returns_a_fresh_dict():
    """Successive calls to the same builder return independent dicts (no shared mutation)."""
    first = user_agent_only(_CONFIG)
    second = user_agent_only(_CONFIG)

    first["extra"] = "value"

    assert "extra" not in second
