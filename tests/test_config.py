"""Tests for UtilityConfig and DEFAULT_CONFIG in config.py."""

import dataclasses

import pytest

from dominionsc.config import DEFAULT_CONFIG, UtilityConfig
from dominionsc.const import BIDGELY_PILOT_ID, USER_AGENT


def test_default_config_name():
    """DEFAULT_CONFIG identifies the utility by its human-readable name."""
    assert DEFAULT_CONFIG.name == "Dominion Energy SC"


def test_default_config_dominion_endpoint():
    """DEFAULT_CONFIG points to the live Dominion Energy SC customer portal."""
    assert DEFAULT_CONFIG.dominion_endpoint == "https://account.dominionenergysc.com"


def test_default_config_bidgely_endpoint():
    """DEFAULT_CONFIG points to the live Bidgely metering analytics API."""
    assert DEFAULT_CONFIG.bidgely_endpoint == "https://desc-prodapi.bidgely.com"


def test_default_config_timezone_is_eastern():
    """DEFAULT_CONFIG uses the America/New_York IANA timezone for SC service territory."""
    assert DEFAULT_CONFIG.timezone == "America/New_York"


def test_default_config_pilot_id_matches_const():
    """DEFAULT_CONFIG pilot_id is taken from the BIDGELY_PILOT_ID constant."""
    assert DEFAULT_CONFIG.pilot_id == BIDGELY_PILOT_ID


def test_default_config_user_agent_matches_const():
    """DEFAULT_CONFIG user_agent is taken from the USER_AGENT constant."""
    assert DEFAULT_CONFIG.user_agent == USER_AGENT


def test_utility_config_is_frozen():
    """UtilityConfig is immutable; assigning a field raises FrozenInstanceError."""
    config = UtilityConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        config.timezone = "UTC"  # type: ignore[misc]


def test_utility_config_supports_field_overrides():
    """Individual UtilityConfig fields can be overridden while keeping other defaults."""
    custom = UtilityConfig(dominion_endpoint="https://staging.example.com", pilot_id="00001")

    assert custom.dominion_endpoint == "https://staging.example.com"
    assert custom.pilot_id == "00001"
    assert custom.timezone == DEFAULT_CONFIG.timezone
    assert custom.user_agent == DEFAULT_CONFIG.user_agent
