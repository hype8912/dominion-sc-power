"""Exceptions."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dominionsc import DominionSCTFAHandler


class CannotConnect(Exception):
    """Error to indicate we cannot connect. This is a retryable exception."""

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status: int | None = None,
        response_text: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable description of the failure.
            url: Request URL that failed, if known.
            status: HTTP status code, if one was received.
            response_text: Response body, if one was received.

        """
        super().__init__(message)
        self.url: str | None = url
        self.status: int | None = status
        self.response_text: str | None = response_text

    def __str__(self) -> str:
        """Return a string representation of the exception."""
        parts: list[str] = [super().__str__()]
        if self.url is not None:
            parts.append(f"URL: {self.url}")
        if self.status is not None:
            parts.append(f"Status: {self.status}")
        if self.response_text is not None:
            parts.append(f"Response: {self.response_text}")
        return "\n".join(parts)


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


class MfaChallenge(Exception):
    """Raised when MFA is required and user interaction is needed.

    Catch it and use ``handler`` to finish TFA, then retry ``async_login``.
    """

    def __init__(self, message: str, handler: "DominionSCTFAHandler") -> None:
        """Initialize the exception.

        Args:
            message: Human-readable reason MFA is needed.
            handler: TFA handler bound to the interrupted login session.

        """
        super().__init__(message)
        self.handler: DominionSCTFAHandler = handler


class ApiException(Exception):
    """Raised during problems talking to the API (response received but not as expected)."""

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status: int | None = None,
        response_text: str | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable description of what could not be parsed.
            url: Request URL whose response was unexpected, if known.
            status: HTTP status code, if known.
            response_text: The unexpected response body, for debugging.

        """
        super().__init__(message)
        self.url = url
        self.status = status
        self.response_text = response_text

    def __str__(self) -> str:
        """Return a string representation of the exception."""
        parts = [super().__str__()]
        if self.url is not None:
            parts.append(f"URL: {self.url}")
        if self.status is not None:
            parts.append(f"Status: {self.status}")
        if self.response_text is not None:
            parts.append(f"Response: {self.response_text}")
        return "\n".join(parts)
