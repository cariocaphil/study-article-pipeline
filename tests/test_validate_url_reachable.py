"""
Tests for src/tools/validate_url_reachable.py.

Network I/O is mocked so these run quickly without external requests.
"""

import logging
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.tools.validate_url_reachable import validate_url_reachable


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, True),
        (204, True),
        (301, True),
        (399, True),
        (400, False),
        (404, False),
        (500, False),
    ],
)
def test_validate_url_reachable_status_codes(status, expected):
    response = SimpleNamespace(status=status)

    with patch("src.tools.validate_url_reachable.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        assert validate_url_reachable("https://example.com") is expected


def test_validate_url_reachable_treats_http_error_status_as_unreachable():
    error = urllib.error.HTTPError(
        url="https://example.com/missing",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )

    with patch("src.tools.validate_url_reachable.urllib.request.urlopen", side_effect=error):
        assert validate_url_reachable("https://example.com/missing") is False


def test_validate_url_reachable_returns_false_on_connection_failure():
    with patch(
        "src.tools.validate_url_reachable.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        assert validate_url_reachable("https://example.com") is False


def test_validate_url_reachable_returns_false_on_timeout():
    with patch(
        "src.tools.validate_url_reachable.urllib.request.urlopen",
        side_effect=TimeoutError("timed out"),
    ):
        assert validate_url_reachable("https://example.com") is False


def test_validate_url_reachable_returns_false_for_malformed_url():
    assert validate_url_reachable("not-a-valid-url") is False


def test_validate_url_reachable_logs_result(caplog):
    response = SimpleNamespace(status=200)

    with patch("src.tools.validate_url_reachable.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        with caplog.at_level(logging.INFO, logger="src.tools.validate_url_reachable"):
            validate_url_reachable("https://example.com/article")

    assert "https://example.com/article → reachable" in caplog.text


def test_validate_url_reachable_uses_head_request():
    response = SimpleNamespace(status=200)

    with patch("src.tools.validate_url_reachable.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = response
        validate_url_reachable("https://example.com")

    request = mock_urlopen.call_args.args[0]
    assert isinstance(request, urllib.request.Request)
    assert request.get_method() == "HEAD"
    assert request.full_url == "https://example.com"
    mock_urlopen.assert_called_once()
    assert mock_urlopen.call_args.kwargs["timeout"] == 5
