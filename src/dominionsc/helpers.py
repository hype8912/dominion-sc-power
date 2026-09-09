"""Shared utility helpers used throughout the dominionsc package."""

import aiohttp


def create_cookie_jar() -> aiohttp.CookieJar:
    """Create an aiohttp cookie jar suitable for Dominion Energy SC sessions.

    Dominion Energy SC's login endpoint sets cookies whose values contain
    characters (such as ``=``) that aiohttp's default ``CookieJar`` would
    automatically percent-encode. That re-encoding changes the cookie value
    and causes subsequent authenticated requests to be rejected by the server.

    Passing ``quote_cookie=False`` instructs aiohttp to store and resend
    cookie values exactly as the server sent them, which matches the
    browser behaviour the site expects.

    Always pass the returned jar to ``aiohttp.ClientSession``::

        async with aiohttp.ClientSession(cookie_jar=create_cookie_jar()) as session:
            client = DominionSC(session, username, password)

    Returns:
        An ``aiohttp.CookieJar`` configured for Dominion's cookie format.

    """
    return aiohttp.CookieJar(quote_cookie=False)
