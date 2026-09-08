"""Tests for helpers.py."""

import aiohttp
import pytest

from dominionsc.helpers import create_cookie_jar


@pytest.mark.asyncio
async def test_create_cookie_jar_returns_cookie_jar():
    """create_cookie_jar returns an aiohttp CookieJar instance."""
    jar = create_cookie_jar()
    assert isinstance(jar, aiohttp.CookieJar)


@pytest.mark.asyncio
async def test_create_cookie_jar_does_not_quote_cookies():
    """The jar is configured with quote_cookie=False (required for the Bidgely flow)."""
    jar = create_cookie_jar()
    # aiohttp stores the flag on the private _quote_cookie attribute.
    assert jar._quote_cookie is False
