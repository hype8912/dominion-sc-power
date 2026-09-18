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
        config.timezone = "UTC"  # ty: ignore[invalid-assignment]


def test_utility_config_supports_field_overrides():
    """Individual UtilityConfig fields can be overridden while keeping other defaults."""
    custom = UtilityConfig(dominion_endpoint="https://staging.example.com", pilot_id="00001")

    assert custom.dominion_endpoint == "https://staging.example.com"
    assert custom.pilot_id == "00001"
    assert custom.timezone == DEFAULT_CONFIG.timezone
    assert custom.user_agent == DEFAULT_CONFIG.user_agent


def test_default_config_referers_derive_from_dominion_endpoint():
    """DEFAULT_CONFIG's Referer defaults are built from its own dominion_endpoint."""
    assert DEFAULT_CONFIG.dominion_access_referer == "https://account.dominionenergysc.com/access/"
    assert DEFAULT_CONFIG.dominion_home_referer == "https://account.dominionenergysc.com/"


def test_referer_properties_follow_an_overridden_dominion_endpoint():
    """Overriding dominion_endpoint alone still produces consistent Referer values.

    This is the whole point of deriving them as properties rather than
    hardcoding a second copy of the hostname: a staging config can't end up
    sending Referer headers that point at the production host.
    """
    custom = UtilityConfig(dominion_endpoint="https://staging.example.com")

    assert custom.dominion_access_referer == "https://staging.example.com/access/"
    assert custom.dominion_home_referer == "https://staging.example.com/"


def test_referer_properties_cannot_be_set_directly():
    """dominion_access_referer/dominion_home_referer are read-only properties, not fields.

    Nothing in this codebase overrides them independently of
    dominion_endpoint, so they can't drift out of sync with it -- there is
    no separate value to override.
    """
    config = UtilityConfig()

    with pytest.raises(AttributeError):
        config.dominion_access_referer = "https://custom.example.com/login"  # ty: ignore[invalid-assignment]
