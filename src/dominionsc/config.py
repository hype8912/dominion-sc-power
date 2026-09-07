"""Configuration for the utility / Bidgely pilot being accessed.

This is the single object that carries endpoint hosts, the utility's
local timezone, the Bidgely pilot ID, and the user agent string used
throughout the package. Everything in headers.py and urls.py takes a
UtilityConfig rather than reading module-level constants directly, so
there's one place to see (and override, e.g. for a different utility
or a different Bidgely pilot) the values that identify this deployment.
"""

from dataclasses import dataclass

from .const import BIDGELY_PILOT_ID, USER_AGENT


@dataclass(frozen=True)
class UtilityConfig:
    """Static configuration for a utility / Bidgely pilot deployment."""

    name: str = "Dominion Energy SC"
    dominion_endpoint: str = "https://account.dominionenergysc.com"
    bidgely_endpoint: str = "https://desc-prodapi.bidgely.com"
    timezone: str = "America/New_York"
    pilot_id: str = BIDGELY_PILOT_ID
    user_agent: str = USER_AGENT


DEFAULT_CONFIG = UtilityConfig()
