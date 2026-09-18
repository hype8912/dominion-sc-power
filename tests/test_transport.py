"""Tests for the cache_buster utility and DominionSCURLHandler timeout handling in transport.py."""

import time
from unittest.mock import Mock

import aiohttp

from dominionsc.transport import DominionSCURLHandler, cache_buster


def test_cache_buster_returns_a_string():
    """cache_buster returns a str, as required by the URL query-parameter builders."""
    result = cache_buster()

    assert isinstance(result, str)


def test_cache_buster_value_is_all_digits():
    """cache_buster returns only decimal digits (a millisecond-resolution Unix timestamp)."""
    result = cache_buster()

    assert result.isdigit()


def test_cache_buster_is_in_millisecond_range():
    """cache_buster returns a value close to the current wall-clock time in milliseconds."""
    before = int(time.time() * 1000)
    result = cache_buster()
    after = int(time.time() * 1000)

    assert before <= int(result) <= after


def test_cache_buster_calls_return_non_decreasing_values():
    """Two successive cache_buster calls return equal or increasing values (time never goes back)."""
    first = int(cache_buster())
    second = int(cache_buster())

    assert second >= first


def test_url_handler_accepts_an_explicit_client_timeout_instance():
    """Passing a ready-made aiohttp.ClientTimeout is stored as-is, not rewrapped."""
    session = Mock(spec=aiohttp.ClientSession)
    timeout = aiohttp.ClientTimeout(total=45)

    handler = DominionSCURLHandler(session, timeout=timeout)

    assert handler._timeout is timeout


def test_url_handler_wraps_a_float_timeout():
    """Passing a bare number of seconds is wrapped into a ClientTimeout(total=...)."""
    session = Mock(spec=aiohttp.ClientSession)

    handler = DominionSCURLHandler(session, timeout=10.0)

    assert isinstance(handler._timeout, aiohttp.ClientTimeout)
    assert handler._timeout.total == 10.0


def test_url_handler_defaults_to_a_30_second_timeout():
    """Omitting timeout entirely defaults to a 30-second ClientTimeout."""
    session = Mock(spec=aiohttp.ClientSession)

    handler = DominionSCURLHandler(session)

    assert isinstance(handler._timeout, aiohttp.ClientTimeout)
    assert handler._timeout.total == 30
