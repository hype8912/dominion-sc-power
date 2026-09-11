"""Tests for the cache_buster utility in transport.py."""

import time

from dominionsc.transport import cache_buster


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
