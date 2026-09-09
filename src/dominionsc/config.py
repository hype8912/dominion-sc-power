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
    """Immutable configuration bundle for one utility / Bidgely pilot deployment.

    All modules that build URLs (``urls.py``) or HTTP headers (``headers.py``)
    accept a ``UtilityConfig`` rather than reading module-level constants, so
    the full set of deployment parameters is visible in one place.

    In normal usage you do not need to instantiate this class -- ``DominionSC``
    creates ``DEFAULT_CONFIG`` internally. Override individual fields only when
    testing against a different environment or a different Bidgely pilot::

        from dominionsc.config import UtilityConfig

        staging_config = UtilityConfig(
            dominion_endpoint="https://staging.dominionenergysc.com",
            pilot_id="99999",
        )

    Attributes:
        name: Human-readable utility name, used for display purposes only.
        dominion_endpoint: Base URL for the Dominion Energy SC customer portal.
            All ``fusionapi`` paths are appended to this.
        bidgely_endpoint: Base URL for the Bidgely metering analytics API.
            ``wc-session`` and ``gb-download`` paths are appended to this.
        timezone: IANA timezone name for the utility's service territory.
            Interval timestamps are converted from UTC to this zone.
        pilot_id: Bidgely multi-tenant pilot identifier that routes requests
            to the correct Dominion SC data pipeline. See ``const.py`` for
            the history of this value and why it matters.
        user_agent: Browser User-Agent string sent with every request. See
            ``const.py`` for guidance on updating this value.

    """

    name: str = "Dominion Energy SC"
    dominion_endpoint: str = "https://account.dominionenergysc.com"
    bidgely_endpoint: str = "https://desc-prodapi.bidgely.com"
    timezone: str = "America/New_York"
    pilot_id: str = BIDGELY_PILOT_ID
    user_agent: str = USER_AGENT


DEFAULT_CONFIG = UtilityConfig()
"""Singleton ``UtilityConfig`` with all default values for Dominion Energy SC.

Import and use this when you need the config outside of a ``DominionSC``
instance, for example in standalone URL-building utilities.
"""
