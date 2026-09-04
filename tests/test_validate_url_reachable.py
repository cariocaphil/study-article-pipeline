"""
Tests for src/tools/validate_url_reachable.py.

Network I/O and DNS are mocked so these run quickly without external requests.
"""

from __future__ import annotations

import http.client
import ipaddress
import logging
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.tools.validate_url_reachable import (
    MAX_REDIRECTS,
    _head_opener,
    _NoRedirectHandler,
    validate_url_reachable,
)


def _public_resolve(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("93.184.216.34")]


@pytest.fixture(autouse=True)
def stub_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.url_safety.resolve_hostname_ips",
        _public_resolve,
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, True),
        (204, True),
        (299, True),
        (400, False),
        (404, False),
        (500, False),
    ],
)
def test_validate_url_reachable_status_codes(status: int, expected: bool) -> None:
    response = SimpleNamespace(status=status)
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = None
    opener = MagicMock()
    opener.open.return_value = context

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com") is expected


def test_validate_url_reachable_treats_http_error_status_as_unreachable():
    error = urllib.error.HTTPError(
        url="https://example.com/missing",
        code=404,
        msg="Not Found",
        hdrs=http.client.HTTPMessage(),
        fp=None,
    )
    opener = MagicMock()
    opener.open.side_effect = error

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/missing") is False


def test_validate_url_reachable_returns_false_on_connection_failure():
    opener = MagicMock()
    opener.open.side_effect = urllib.error.URLError("connection refused")

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com") is False


def test_validate_url_reachable_returns_false_on_timeout():
    opener = MagicMock()
    opener.open.side_effect = TimeoutError("timed out")

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com") is False


def test_validate_url_reachable_returns_false_for_malformed_url():
    assert validate_url_reachable("not-a-valid-url") is False


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost",
        "http://169.254.169.254",
        "file:///etc/passwd",
    ],
)
def test_validate_url_reachable_blocks_unsafe_urls_without_network(url: str) -> None:
    with patch("src.tools.validate_url_reachable._head_opener") as mock_opener_factory:
        assert validate_url_reachable(url) is False

    mock_opener_factory.assert_not_called()


def test_validate_url_reachable_logs_blocked_url(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="src.tools.validate_url_reachable"):
        assert validate_url_reachable("http://127.0.0.1") is False

    assert "http://127.0.0.1 → blocked" in caplog.text


def test_validate_url_reachable_logs_result(caplog: pytest.LogCaptureFixture) -> None:
    response = SimpleNamespace(status=200)
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = None
    opener = MagicMock()
    opener.open.return_value = context

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        with caplog.at_level(logging.INFO, logger="src.tools.validate_url_reachable"):
            validate_url_reachable("https://example.com/article")

    assert "https://example.com/article → reachable" in caplog.text


def test_validate_url_reachable_uses_head_request():
    response = SimpleNamespace(status=200)
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = None
    opener = MagicMock()
    opener.open.return_value = context

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        validate_url_reachable("https://example.com")

    request = opener.open.call_args.args[0]
    assert isinstance(request, urllib.request.Request)
    assert request.get_method() == "HEAD"
    assert request.full_url == "https://example.com"
    assert opener.open.call_args.kwargs["timeout"] == 5


def test_follows_safe_redirect_then_accepts_final_response():
    headers = http.client.HTTPMessage()
    headers["Location"] = "https://cdn.example.com/article"
    redirect = urllib.error.HTTPError(
        url="https://example.com/start",
        code=302,
        msg="Found",
        hdrs=headers,
        fp=None,
    )
    final = SimpleNamespace(status=200)
    final_ctx = MagicMock()
    final_ctx.__enter__.return_value = final
    final_ctx.__exit__.return_value = None

    opener = MagicMock()
    opener.open.side_effect = [redirect, final_ctx]

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/start") is True

    assert opener.open.call_count == 2
    assert opener.open.call_args_list[1].args[0].full_url == "https://cdn.example.com/article"


def test_blocks_redirect_to_private_host_without_following():
    headers = http.client.HTTPMessage()
    headers["Location"] = "http://127.0.0.1/secret"
    redirect = urllib.error.HTTPError(
        url="https://example.com/start",
        code=302,
        msg="Found",
        hdrs=headers,
        fp=None,
    )
    opener = MagicMock()
    opener.open.side_effect = redirect

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/start") is False

    assert opener.open.call_count == 1


def test_blocks_redirect_to_hostname_that_resolves_privately(
    monkeypatch: pytest.MonkeyPatch,
):
    def resolve(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        if hostname == "evil.internal":
            return [ipaddress.ip_address("10.1.2.3")]
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr("src.tools.url_safety.resolve_hostname_ips", resolve)

    headers = http.client.HTTPMessage()
    headers["Location"] = "https://evil.internal/meta"
    redirect = urllib.error.HTTPError(
        url="https://example.com/start",
        code=301,
        msg="Moved",
        hdrs=headers,
        fp=None,
    )
    opener = MagicMock()
    opener.open.side_effect = redirect

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/start") is False


def test_rejects_when_redirect_limit_exceeded(stub_public_dns: None) -> None:
    headers = http.client.HTTPMessage()
    headers["Location"] = "https://example.com/next"

    def always_redirect(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.HTTPError(
            url="https://example.com/next",
            code=302,
            msg="Found",
            hdrs=headers,
            fp=None,
        )

    opener = MagicMock()
    opener.open.side_effect = always_redirect

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/start") is False

    assert opener.open.call_count == MAX_REDIRECTS + 1


def test_resolves_relative_redirect_location():
    headers = http.client.HTTPMessage()
    headers["Location"] = "/final"
    redirect = urllib.error.HTTPError(
        url="https://example.com/start",
        code=302,
        msg="Found",
        hdrs=headers,
        fp=None,
    )
    final = SimpleNamespace(status=200)
    final_ctx = MagicMock()
    final_ctx.__enter__.return_value = final
    final_ctx.__exit__.return_value = None
    opener = MagicMock()
    opener.open.side_effect = [redirect, final_ctx]

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com/start") is True

    assert opener.open.call_args_list[1].args[0].full_url == "https://example.com/final"


def test_uses_getcode_when_response_has_no_status_attribute():
    response = MagicMock(spec=["getcode"])
    response.getcode.return_value = 204
    context = MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = None
    opener = MagicMock()
    opener.open.return_value = context

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        assert validate_url_reachable("https://example.com") is True

    response.getcode.assert_called_once()


def test_redirect_without_location_is_unreachable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    headers = http.client.HTTPMessage()
    redirect = urllib.error.HTTPError(
        url="https://example.com/start",
        code=302,
        msg="Found",
        hdrs=headers,
        fp=None,
    )
    opener = MagicMock()
    opener.open.side_effect = redirect

    with patch("src.tools.validate_url_reachable._head_opener", return_value=opener):
        with caplog.at_level(logging.INFO, logger="src.tools.validate_url_reachable"):
            assert validate_url_reachable("https://example.com/start") is False

    assert "https://example.com/start → unreachable" in caplog.text
    assert opener.open.call_count == 1


def test_head_opener_returns_opener_director():
    opener = _head_opener()
    assert isinstance(opener, urllib.request.OpenerDirector)


def test_no_redirect_handler_raises_http_error_for_redirects():
    handler = _NoRedirectHandler()
    request = urllib.request.Request("https://example.com/start", method="HEAD")
    headers = http.client.HTTPMessage()
    headers["Location"] = "https://example.com/next"
    fp = MagicMock()

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        handler.redirect_request(
            request,
            fp=fp,
            code=302,
            msg="Found",
            headers=headers,
            newurl="https://example.com/next",
        )

    assert exc_info.value.code == 302
    assert exc_info.value.geturl() == "https://example.com/start"
