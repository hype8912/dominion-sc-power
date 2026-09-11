"""Coverage tests for dominionsc exceptions."""

from dominionsc.exceptions import ApiException, CannotConnect, InvalidAuth, MfaChallenge


def test_cannot_connect_str_with_all():
    """Test CannotConnect __str__ with all optional fields set."""
    exc = CannotConnect("msg", url="http://x", status=404, response_text="bad")
    s = str(exc)
    assert "msg" in s
    assert "URL: http://x" in s
    assert "Status: 404" in s
    assert "Response: bad" in s


def test_api_exception_str_with_status():
    """ApiException __str__ includes message, URL, and status when status is set."""
    exc = ApiException("msg", url="http://x", status=500)
    s = str(exc)
    assert "msg" in s
    assert "URL: http://x" in s
    assert "Status: 500" in s


def test_api_exception_str_with_response_text():
    """ApiException __str__ includes message, URL, and response_text when response_text is set."""
    exc = ApiException("msg", url="http://x", response_text="oops")
    s = str(exc)
    assert "msg" in s
    assert "URL: http://x" in s
    assert "Response: oops" in s


def test_invalid_auth_without_message():
    """InvalidAuth with no message produces an empty string representation."""
    exc = InvalidAuth()
    assert str(exc) == ""


def test_invalid_auth_with_message():
    """InvalidAuth preserves its message in the string representation."""
    exc = InvalidAuth("bad credentials")
    assert str(exc) == "bad credentials"


def test_cannot_connect_defaults():
    """Test CannotConnect __str__ with default optional fields."""
    exc = CannotConnect("msg")
    assert str(exc) == "msg"


def test_api_exception_defaults():
    """Test ApiException __str__ with default optional fields."""
    exc = ApiException("msg", url="http://x")
    assert "Status" not in str(exc)
    assert "Response" not in str(exc)


def test_mfa_challenge():
    """Test MfaChallenge initialization and handler storage."""

    class FakeHandler:
        pass

    exc = MfaChallenge("challenge", handler=FakeHandler())
    assert exc.args[0] == "challenge"
    assert isinstance(exc.handler, FakeHandler)
