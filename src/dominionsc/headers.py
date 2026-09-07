"""Header builders for Dominion Energy SC and Bidgely requests.

Every header dict this library sends should be assembled here, not
built inline elsewhere. In particular, this is the ONLY module that
should reference the literal "X-Bidgely-Pilot-Id" header name -- see
docs/REFACTOR_PLAN.md finding F2, which is exactly how a wrong
hardcoded pilot ID ended up duplicated in two places and briefly
survived one fix attempt.

Unlike the pre-refactor code, these functions always return a fresh
dict rather than mutating and reusing one across calls (finding F8).
"""

from .config import UtilityConfig


def user_agent_only(config: UtilityConfig) -> dict[str, str]:
    """Bare header set used for the initial, unauthenticated login page fetch."""
    return {"User-Agent": config.user_agent}


def dominion_page_headers(config: UtilityConfig, referer: str) -> dict[str, str]:
    """Headers for a plain (non-AJAX) Dominion page fetch."""
    return {
        "User-Agent": config.user_agent,
        "Host": "account.dominionenergysc.com",
        "Referer": referer,
    }


def dominion_ajax_headers(
    config: UtilityConfig,
    verification_token: str,
    referer: str,
    origin: str | None = None,
) -> dict[str, str]:
    """Headers for an authenticated AJAX call to Dominion's fusionapi.

    ``origin`` is only present on the earliest calls in the login flow
    (before the authenticated home-page reload); pass None to omit it,
    matching the original code's ``del headers1["Origin"]`` step.
    """
    result = {
        "User-Agent": config.user_agent,
        "__RequestVerificationToken": verification_token,
        "IsAjax": "true",
        "X-Requested-With": "XMLHttpRequest",
        "Host": "account.dominionenergysc.com",
        "Referer": referer,
    }
    if origin is not None:
        result["Origin"] = origin
    return result


def bidgely_headers(config: UtilityConfig, access_token: str | None = None) -> dict[str, str]:
    """Headers for a Bidgely request (login token exchange or gb-download)."""
    result = {
        "User-Agent": config.user_agent,
        "IsAjax": "true",
        "X-Requested-With": "XMLHttpRequest",
        "Host": "desc-prodapi.bidgely.com",
        "Origin": "https://account.dominionenergysc.com",
        "Referer": "https://account.dominionenergysc.com/",
        "X-Bidgely-Client-Type": "WIDGETS",
        "X-Bidgely-Pilot-Id": config.pilot_id,
    }
    if access_token:
        result["Authorization"] = f"Bearer {access_token}"
    return result
